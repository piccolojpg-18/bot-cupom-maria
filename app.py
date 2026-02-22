from flask import Flask, request
import requests
from bs4 import BeautifulSoup
import os
import re
import logging
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

app = Flask(__name__)

# ============================================
# CONFIGURAÇÕES
# ============================================
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', "8538755291:AAG2dmZW8KcAN7DnC7pnMIqoSqh490F1YiY")
WP_URL = "https://cupomemaria.com.br"
WP_USER = os.environ.get('WP_USER')
WP_APP_PASSWORD = os.environ.get('WP_APP_PASSWORD')

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================
# FUNÇÕES TELEGRAM
# ============================================
def enviar_telegram(chat_id, texto):
    """Envia mensagem para o Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': texto,
        'parse_mode': 'Markdown'
    }
    try:
        requests.post(url, json=payload, timeout=3)
        return True
    except:
        return False

# ============================================
# FUNÇÃO PARA CRIAR POST NO WORDPRESS (CORRIGIDA)
# ============================================
def criar_post_wordpress(dados_produto, link_original):
    """
    Cria um post no WordPress com os campos ACF preenchidos
    """
    try:
        logger.info("📝 Criando post no WordPress...")
        
        # Preparar dados
        titulo = dados_produto['nome'][:100]
        
        # Converter preços para número (formato que o ACF aceita)
        preco_novo_num = None
        if dados_produto.get('preco_atual'):
            preco_str = dados_produto['preco_atual'].replace('R$', '').replace('.', '').replace(',', '.').strip()
            try:
                preco_novo_num = float(preco_str)
            except:
                preco_novo_num = None
        
        preco_antigo_num = None
        if dados_produto.get('preco_antigo'):
            preco_str = dados_produto['preco_antigo'].replace('R$', '').replace('.', '').replace(',', '.').strip()
            try:
                preco_antigo_num = float(preco_str)
            except:
                preco_antigo_num = None
        
        # Extrair parcelamento
        parcelas_texto = ""
        if dados_produto.get('parcelas') and dados_produto['parcelas'] != "Não informado":
            match = re.search(r'(\d+x\s*R\$\s*[\d.,]+)', dados_produto['parcelas'])
            if match:
                parcelas_texto = match.group(1)
        
        # Montar o array de meta fields (formato correto do ACF via REST API)
        meta_data = {}
        if preco_antigo_num:
            meta_data['preco_antigo'] = preco_antigo_num
        if preco_novo_num:
            meta_data['preco_novo'] = preco_novo_num
        if dados_produto.get('percentual'):
            meta_data['percentual'] = dados_produto['percentual']
        if dados_produto.get('loja'):
            meta_data['loja'] = dados_produto['loja']
        if link_original:
            meta_data['link_afiliado'] = link_original
        if parcelas_texto:
            meta_data['parcelas'] = parcelas_texto
        meta_data['tempo'] = "há 0h"
        
        # Dados completos do post
        post_data = {
            'title': titulo,
            'status': 'publish',
            'meta': meta_data
        }
        
        logger.info(f"Enviando para WordPress: {post_data}")
        
        # Enviar para WordPress
        wp_api_url = f"{WP_URL}/wp-json/wp/v2/posts"
        auth = (WP_USER, WP_APP_PASSWORD)
        
        response = requests.post(wp_api_url, json=post_data, auth=auth, timeout=10)
        
        if response.status_code in [200, 201]:
            post_data = response.json()
            post_link = post_data.get('link', '')
            logger.info(f"✅ Post criado: {post_link}")
            return post_link
        else:
            logger.error(f"Erro WordPress: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Erro ao criar post: {e}")
        return None

# ============================================
# FUNÇÕES DO CHROME (OTIMIZADAS)
# ============================================
def criar_driver():
    """Configura o Chrome de forma otimizada"""
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    
    chrome_path = "/opt/render/project/.chrome/opt/google/chrome/google-chrome"
    if os.path.exists(chrome_path):
        chrome_options.binary_location = chrome_path
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        return driver
    except:
        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            return driver
        except:
            return None

# ============================================
# EXTRAÇÃO MERCADO LIVRE (OTIMIZADA)
# ============================================
def extrair_dados_ml(url_afiliado):
    """Extrai dados do Mercado Livre de forma otimizada"""
    driver = None
    try:
        driver = criar_driver()
        if not driver:
            return None
        
        # Acessar página
        driver.get(url_afiliado)
        time.sleep(3)
        
        # Clicar no primeiro produto
        try:
            link = driver.find_element(By.XPATH, "//a[contains(@href, '/p/')]")
            driver.execute_script("arguments[0].click();", link)
            time.sleep(2)
        except:
            pass
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # Nome
        nome = "Nome não encontrado"
        titulo = soup.find('h1', class_='ui-pdp-title')
        if titulo:
            nome = titulo.get_text(strip=True)
        
        # Preço atual
        preco_atual = "Preço não encontrado"
        meta_price = soup.find('meta', {'itemprop': 'price'})
        if meta_price and meta_price.get('content'):
            preco_atual = meta_price.get('content')
        else:
            preco_span = soup.find('span', class_='andes-money-amount__fraction')
            if preco_span:
                preco_atual = preco_span.get_text(strip=True)
                centavos = soup.find('span', class_='andes-money-amount__cents')
                if centavos:
                    preco_atual = f"{preco_atual}.{centavos.get_text(strip=True)}"
        
        # Preço antigo
        preco_antigo = None
        antigo = soup.find('span', class_='andes-money-amount--previous')
        if antigo:
            valor = antigo.find('span', class_='andes-money-amount__fraction')
            if valor:
                preco_antigo = valor.get_text(strip=True)
        
        # Parcelamento
        parcelas = "Não informado"
        parcela_text = soup.find('span', class_='ui-pdp-installments')
        if parcela_text:
            parcelas = parcela_text.get_text(strip=True)
        
        # Percentual
        percentual = None
        if preco_antigo and preco_atual and preco_atual != "Preço não encontrado":
            try:
                antigo_num = float(preco_antigo.replace('.', '').replace(',', '.'))
                atual_num = float(preco_atual.replace('.', '').replace(',', '.'))
                percentual = round(((antigo_num - atual_num) / antigo_num) * 100)
            except:
                pass
        
        # Formatar preços
        preco_atual_fmt = formatar_preco_br(preco_atual)
        preco_antigo_fmt = formatar_preco_br(preco_antigo) if preco_antigo else None
        
        return {
            'nome': nome,
            'preco_atual': preco_atual_fmt,
            'preco_antigo': preco_antigo_fmt,
            'parcelas': parcelas,
            'percentual': percentual,
            'loja': 'Mercado Livre'
        }
        
    except Exception as e:
        logger.error(f"Erro ML: {e}")
        return None
    finally:
        if driver:
            driver.quit()

# ============================================
# EXTRAÇÃO AMAZON (OTIMIZADA)
# ============================================
def extrair_dados_amazon(url):
    """Extrai dados da Amazon de forma otimizada"""
    driver = None
    try:
        driver = criar_driver()
        if not driver:
            return None
        
        driver.get(url)
        time.sleep(3)
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # Nome
        nome = "Nome não encontrado"
        titulo = soup.find('span', {'id': 'productTitle'})
        if titulo:
            nome = titulo.get_text(strip=True)
        
        # Preço atual
        preco_atual = "Preço não encontrado"
        preco_span = soup.find('span', {'class': 'a-price-whole'})
        if preco_span:
            preco_atual = preco_span.get_text(strip=True)
            centavos = soup.find('span', {'class': 'a-price-fraction'})
            if centavos:
                preco_atual = f"{preco_atual}.{centavos.get_text(strip=True)}"
        
        # Preço antigo
        preco_antigo = None
        antigo = soup.find('span', {'class': 'a-text-price'})
        if antigo:
            span = antigo.find('span', {'class': 'a-offscreen'})
            if span:
                texto = span.get_text()
                match = re.search(r'R\$\s*([\d.,]+)', texto)
                if match:
                    preco_antigo = match.group(1)
        
        # Parcelamento
        parcelas = "Não informado"
        parcela_text = soup.find(string=re.compile(r'\d+x\s*R\$\s*[\d.,]+', re.I))
        if parcela_text:
            parcelas = parcela_text.strip()
        
        # Percentual
        percentual = None
        if preco_antigo and preco_atual and preco_atual != "Preço não encontrado":
            try:
                antigo_num = float(preco_antigo.replace('.', '').replace(',', '.'))
                atual_num = float(preco_atual.replace('.', '').replace(',', '.'))
                percentual = round(((antigo_num - atual_num) / antigo_num) * 100)
            except:
                pass
        
        # Formatar preços
        preco_atual_fmt = formatar_preco_br(preco_atual)
        preco_antigo_fmt = formatar_preco_br(preco_antigo) if preco_antigo else None
        
        return {
            'nome': nome,
            'preco_atual': preco_atual_fmt,
            'preco_antigo': preco_antigo_fmt,
            'parcelas': parcelas,
            'percentual': percentual,
            'loja': 'Amazon'
        }
        
    except Exception as e:
        logger.error(f"Erro Amazon: {e}")
        return None
    finally:
        if driver:
            driver.quit()

# ============================================
# FORMATAR PREÇO
# ============================================
def formatar_preco_br(valor):
    """Formata preço para R$ 1.234,56"""
    if not valor or valor == "Preço não encontrado":
        return valor
    
    try:
        valor = re.sub(r'[^\d.,]', '', str(valor))
        
        if ',' in valor and '.' in valor:
            valor = valor.replace('.', '').replace(',', '.')
        elif ',' in valor:
            valor = valor.replace(',', '.')
        
        if '.' in valor:
            reais, centavos = valor.split('.')
            if len(reais) > 3:
                reais = re.sub(r'(\d)(?=(\d{3})+(?!\d))', r'\1.', reais)
            return f"R$ {reais},{centavos[:2]}"
        else:
            return f"R$ {valor},00"
    except:
        return f"R$ {valor}"

# ============================================
# FORMATAR MENSAGEM (TEMPLATE FIXO)
# ============================================
def formatar_mensagem_telegram(dados, post_link):
    """Formata mensagem no template fixo"""
    msg = f"🎀✨🛍️{dados['nome']}\n\n"
    
    if dados.get('preco_antigo'):
        msg += f"~de: {dados['preco_antigo']}~\n"
    
    msg += f"💸 por: {dados['preco_atual']} 🔥🚨\n"
    
    if dados.get('parcelas') and dados['parcelas'] != "Não informado":
        msg += f"💳 ou {dados['parcelas']}\n"
    
    msg += f"\nCompre usando o Link 👉 ({post_link})\n\n"
    msg += "_*Essa promo pode acabar a qualquer momento*_"
    
    return msg

# ============================================
# ROTAS
# ============================================
@app.route('/', methods=['GET'])
def home():
    return "✅ Bot Automático - Versão Corrigida"

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        
        if 'message' in data:
            chat_id = data['message']['chat']['id']
            texto = data['message'].get('text', '').strip()
            
            logger.info(f"Mensagem: {texto[:50]}")
            
            if texto == '/start':
                enviar_telegram(chat_id, "🤖 *Bot Automático*\n\nEnvie um link do Mercado Livre ou Amazon")
                return 'ok', 200
            
            enviar_telegram(chat_id, "⏳ Processando...")
            
            # Extrair dados
            dados = None
            if 'mercadolivre' in texto.lower():
                dados = extrair_dados_ml(texto)
            elif 'amazon' in texto.lower() or 'amzn.to' in texto.lower():
                dados = extrair_dados_amazon(texto)
            else:
                enviar_telegram(chat_id, "❌ Envie link do Mercado Livre ou Amazon")
                return 'ok', 200
            
            if dados and dados['nome'] != "Nome não encontrado":
                # Criar post
                enviar_telegram(chat_id, "📝 Criando post...")
                post_link = criar_post_wordpress(dados, texto)
                
                if post_link:
                    msg = formatar_mensagem_telegram(dados, post_link)
                    enviar_telegram(chat_id, msg)
                else:
                    enviar_telegram(chat_id, "❌ Erro ao criar post no site")
            else:
                enviar_telegram(chat_id, "❌ Não consegui extrair os dados")
        
        return 'ok', 200
        
    except Exception as e:
        logger.error(f"Erro: {e}")
        return 'ok', 200

# ============================================
# INICIALIZAÇÃO
# ============================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🚀 Bot iniciado na porta {port}")
    app.run(host='0.0.0.0', port=port)