from flask import Flask, request
import requests
from bs4 import BeautifulSoup
import os
import re
import logging
import time
import random
import string
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

app = Flask(__name__)

# CONFIGURAÇÕES
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', "8538755291:AAG2dmZW8KcAN7DnC7pnMIqoSqh490F1YiY")

# CONFIGURAÇÕES DO WORDPRESS
WP_URL = "https://cupomemaria.com.br"
WP_USER = os.environ.get('WP_USER')
WP_APP_PASSWORD = os.environ.get('WP_APP_PASSWORD')

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def enviar_telegram(chat_id, texto):
    """Envia mensagem para o Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': texto,
        'parse_mode': 'Markdown'
    }
    try:
        requests.post(url, json=payload, timeout=5)
        return True
    except Exception as e:
        logger.error(f"Erro Telegram: {e}")
        return False

def criar_post_wordpress(dados_produto, link_original):
    """
    Cria um post no WordPress com os campos ACF preenchidos
    """
    try:
        logger.info("📝 Criando post no WordPress...")
        
        titulo = dados_produto['nome'][:100]
        
        slug = re.sub(r'[^\w\s]', '', titulo.lower())
        slug = '-'.join(slug.split()[:5])[:50]
        slug = slug.replace('--', '-').strip('-')
        
        # Extrair parcelamento
        parcelas = dados_produto.get('parcelas', '')
        parcela_texto = ''
        if parcelas and parcelas != "Não informado":
            match = re.search(r'(\d+x\s*R\$\s*[\d.,]+)', parcelas)
            if match:
                parcela_texto = match.group(1)
        
        # Converter preços para número (sem R$, sem pontos)
        preco_novo_num = None
        if dados_produto.get('preco_atual'):
            preco_str = dados_produto['preco_atual'].replace('R$', '').strip()
            preco_str = preco_str.replace('.', '').replace(',', '.')
            try:
                preco_novo_num = float(preco_str)
            except:
                preco_novo_num = None
        
        preco_antigo_num = None
        if dados_produto.get('preco_antigo'):
            preco_str = dados_produto['preco_antigo'].replace('R$', '').strip()
            preco_str = preco_str.replace('.', '').replace(',', '.')
            try:
                preco_antigo_num = float(preco_str)
            except:
                preco_antigo_num = None
        
        # Dados do post com ACF
        post_data = {
            'title': titulo,
            'status': 'publish',
            'slug': slug,
            'meta': {
                'preco_antigo': preco_antigo_num,
                'preco_novo': preco_novo_num,
                'percentual': dados_produto.get('percentual'),
                'loja': dados_produto.get('loja'),
                'link_afiliado': link_original,
                'parcelas': parcela_texto
            }
        }
        
        logger.info(f"Dados enviados: {post_data}")
        
        # Enviar para WordPress
        wp_api_url = f"{WP_URL}/wp-json/wp/v2/posts"
        auth = (WP_USER, WP_APP_PASSWORD)
        
        response = requests.post(wp_api_url, json=post_data, auth=auth)
        
        if response.status_code in [200, 201]:
            post_data = response.json()
            post_link = post_data['link']
            logger.info(f"✅ Post criado: {post_link}")
            return post_link
        else:
            logger.error(f"Erro WordPress: {response.status_code}")
            logger.error(f"Resposta: {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Erro ao criar post: {e}")
        return None
def formatar_mensagem_telegram(dados, post_link):
    """
    Formata a mensagem no template FIXO:
    
    🎀✨🛍️(nome do produto)
    
    ~de: ~
    💸 por:  🔥🚨
    💳 ou x de R$
    
    Compre usando o Link 👉 (link)
    
    _*Essa promo pode acabar a qualquer momento*_
    """
    
    msg = f"🎀✨🛍️{dados['nome']}\n\n"
    
    if dados.get('preco_antigo'):
        msg += f"~de: {dados['preco_antigo']}~\n"
    
    msg += f"💸 por: {dados['preco_atual']} 🔥🚨\n"
    
    # Parcelamento
    if dados.get('parcelas') and dados['parcelas'] != "Não informado":
        msg += f"💳 ou {dados['parcelas']}\n"
    elif dados.get('parcelas_formatadas'):
        msg += f"💳 ou {dados['parcelas_formatadas']}\n"
    
    msg += f"\nCompre usando o Link 👉 ({post_link})\n\n"
    msg += "_*Essa promo pode acabar a qualquer momento*_"
    
    return msg

def criar_driver():
    """Configura o Chrome"""
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    
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

def extrair_dados_ml(url_afiliado):
    """Extrai dados completos do Mercado Livre"""
    driver = None
    try:
        driver = criar_driver()
        if not driver:
            return None
        
        driver.get(url_afiliado)
        time.sleep(5)
        
        # Clicar no primeiro produto
        try:
            links = driver.find_elements(By.XPATH, "//a[contains(@href, '/p/')]")
            if links:
                driver.execute_script("arguments[0].click();", links[0])
                time.sleep(3)
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
        if meta_price:
            preco_atual = meta_price.get('content', '')
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
        if preco_antigo and preco_atual:
            try:
                antigo_num = float(preco_antigo.replace('.', '').replace(',', '.'))
                atual_num = float(preco_atual.replace('.', '').replace(',', '.'))
                percentual = round(((antigo_num - atual_num) / antigo_num) * 100)
            except:
                pass
        
        # Loja
        loja = "Mercado Livre"
        
        return {
            'nome': nome,
            'preco_atual': formatar_preco_br(preco_atual),
            'preco_antigo': formatar_preco_br(preco_antigo) if preco_antigo else None,
            'parcelas': parcelas,
            'percentual': percentual,
            'loja': loja
        }
        
    except Exception as e:
        logger.error(f"Erro ML: {e}")
        return None
    finally:
        if driver:
            driver.quit()

def extrair_dados_amazon(url):
    """Extrai dados completos da Amazon"""
    driver = None
    try:
        driver = criar_driver()
        if not driver:
            return None
        
        driver.get(url)
        time.sleep(5)
        
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
        if preco_antigo and preco_atual:
            try:
                antigo_num = float(preco_antigo.replace('.', '').replace(',', '.'))
                atual_num = float(preco_atual.replace('.', '').replace(',', '.'))
                percentual = round(((antigo_num - atual_num) / antigo_num) * 100)
            except:
                pass
        
        # Loja
        loja = "Amazon"
        
        return {
            'nome': nome,
            'preco_atual': formatar_preco_br(preco_atual),
            'preco_antigo': formatar_preco_br(preco_antigo) if preco_antigo else None,
            'parcelas': parcelas,
            'percentual': percentual,
            'loja': loja
        }
        
    except Exception as e:
        logger.error(f"Erro Amazon: {e}")
        return None
    finally:
        if driver:
            driver.quit()

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

@app.route('/', methods=['GET'])
def home():
    return "✅ Bot com Template Fixo"

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        
        if 'message' in data:
            chat_id = data['message']['chat']['id']
            texto = data['message'].get('text', '').strip()
            
            logger.info(f"Mensagem: {texto[:50]}")
            
            if texto == '/start':
                enviar_telegram(chat_id, 
                    "🤖 *Bot com Template Fixo*\n\n"
                    "Envie um link que eu:\n"
                    "1️⃣ Extraio os dados\n"
                    "2️⃣ Crio post no site\n"
                    "3️⃣ Respondo com o template:\n\n"
                    "🎀✨🛍️(nome)\n"
                    "~de: ~\n"
                    "💸 por: 🔥🚨\n"
                    "💳 ou x de R$\n"
                    "Link 👉 (link do post)"
                )
                return 'ok', 200
            
            enviar_telegram(chat_id, "🔍 Processando...")
            
            dados = None
            
            if 'mercadolivre' in texto.lower():
                dados = extrair_dados_ml(texto)
            elif 'amazon' in texto.lower() or 'amzn.to' in texto.lower():
                dados = extrair_dados_amazon(texto)
            else:
                enviar_telegram(chat_id, "❌ Envie link do Mercado Livre ou Amazon")
                return 'ok', 200
            
            if dados and dados['nome'] != "Nome não encontrado":
                # Criar post no WordPress
                enviar_telegram(chat_id, "📝 Criando post no site...")
                
                post_link = criar_post_wordpress(dados, texto)
                
                if post_link:
                    # Formatar mensagem com o template FIXO
                    msg_template = formatar_mensagem_telegram(dados, post_link)
                    enviar_telegram(chat_id, msg_template)
                else:
                    enviar_telegram(chat_id, "❌ Erro ao criar post no site")
            else:
                enviar_telegram(chat_id, "❌ Não consegui extrair os dados")
        
        return 'ok', 200
        
    except Exception as e:
        logger.error(f"Erro: {e}")
        return 'ok', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🚀 Bot com template fixo iniciado na porta {port}")
    app.run(host='0.0.0.0', port=port)