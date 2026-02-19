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
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

app = Flask(__name__)

# CONFIGURAÇÕES DO TELEGRAM
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', "8538755291:AAG2dmZW8KcAN7DnC7pnMIqoSqh490F1YiY")

# CONFIGURAÇÕES DO WORDPRESS (via variáveis de ambiente)
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

def gerar_slug_unico():
    """Gera um slug aleatório tipo 0Q1uKa4jrY"""
    caracteres = string.ascii_letters + string.digits
    return ''.join(random.choices(caracteres, k=10))

def criar_link_wordpress(link_afiliado, nome_produto):
    """
    Cria um Pretty Link no WordPress via API
    """
    if not WP_USER or not WP_APP_PASSWORD:
        logger.warning("Sem credenciais WordPress - usando link direto")
        return link_afiliado
    
    try:
        # Criar slug amigável
        nome_limpo = re.sub(r'[^\w\s]', '', nome_produto)
        palavras = nome_limpo.split()[:3]
        slug_base = '-'.join(palavras).lower()
        slug = slug_base[:30]
        
        if not slug or len(slug) < 3:
            slug = gerar_slug_unico()
        
        logger.info(f"Criando link: {slug}")
        
        data = {
            'title': nome_produto[:100],
            'slug': slug,
            'url': link_afiliado,
            'redirect_type': '302',
            'no_follow': True,
            'sponsored': True
        }
        
        auth = (WP_USER, WP_APP_PASSWORD)
        wp_api_url = f"{WP_URL}/wp-json/pretty-links/v1/links"
        response = requests.post(wp_api_url, json=data, auth=auth, timeout=10)
        
        if response.status_code in [200, 201]:
            link_data = response.json()
            return f"{WP_URL}/{link_data.get('slug', slug)}"
        else:
            return f"{WP_URL}/p/{slug}"
            
    except Exception as e:
        logger.error(f"Erro ao criar link: {e}")
        return link_afiliado

def formatar_mensagem_completa(dados, link_curto, site):
    """
    Formata a mensagem no padrão correto:
    - Amazon: "De: ~R$52,79~" quando tem preço antigo
    - Mercado Livre: "~R$599~" quando tem preço antigo
    - Se não tem preço antigo, não mostra nada
    """
    emojis_inicio = "🎀✨🛍️"
    
    msg = f"{emojis_inicio}{dados['nome']}\n\n"
    
    # Só mostra preço antigo SE existir
    if dados.get('preco_antigo'):
        if site == 'amazon':
            # Amazon: formato "De: ~R$52,79~"
            msg += f"De: ~{dados['preco_antigo']}~  \n"
        else:
            # Mercado Livre: formato "~R$599~"
            msg += f"~{dados['preco_antigo']}~  \n"
    
    # Preço atual sempre aparece
    msg += f"💸 por {dados['preco_atual']} 🔥🚨\n"
    
    # Parcelamento (se existir)
    if dados.get('parcelas') and dados['parcelas'] != "Não informado":
        match = re.search(r'(\d+x\s*R\$\s*[\d.,]+)', dados['parcelas'])
        if match:
            parcela = match.group(1)
            msg += f"💳 ou {parcela}\n"
    
    msg += f"\nCompre usando o Link 👉 {link_curto}\n\n"
    msg += "_*Essa promo pode acabar a qualquer momento*_"
    
    return msg

def criar_driver():
    """Configura o Chrome para rodar no Render"""
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    
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

def extrair_mercadolivre_com_selenium(url_afiliado):
    """Extrai dados do Mercado Livre"""
    driver = None
    try:
        logger.info(f"📦 Extraindo Mercado Livre")
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
        
        # NOME
        nome = "Nome não encontrado"
        titulo = soup.find('h1', class_='ui-pdp-title')
        if titulo:
            nome = titulo.get_text(strip=True)
        
        # PREÇO ATUAL
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
        
        # PREÇO ANTIGO
        preco_antigo = None
        antigo = soup.find('span', class_='andes-money-amount--previous')
        if antigo:
            valor = antigo.find('span', class_='andes-money-amount__fraction')
            if valor:
                preco_antigo = valor.get_text(strip=True)
        
        # PARCELAMENTO
        parcelas = "Não informado"
        parcela_text = soup.find('span', class_='ui-pdp-installments')
        if parcela_text:
            parcelas = parcela_text.get_text(strip=True)
        
        # FORMATAR PREÇOS
        preco_atual = formatar_preco_br(preco_atual)
        preco_antigo = formatar_preco_br(preco_antigo) if preco_antigo else None
        
        return {
            'nome': nome,
            'preco_atual': preco_atual,
            'preco_antigo': preco_antigo,
            'parcelas': parcelas
        }
        
    except Exception as e:
        logger.error(f"Erro ML: {e}")
        return None
    finally:
        if driver:
            driver.quit()

def extrair_amazon_com_selenium(url):
    """Extrai dados da Amazon"""
    driver = None
    try:
        logger.info(f"🛒 Extraindo Amazon")
        driver = criar_driver()
        if not driver:
            return None
        
        driver.get(url)
        time.sleep(5)
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # NOME
        nome = "Nome não encontrado"
        titulo = soup.find('span', {'id': 'productTitle'})
        if titulo:
            nome = titulo.get_text(strip=True)
        
        # PREÇO ATUAL
        preco_atual = "Preço não encontrado"
        preco_span = soup.find('span', {'class': 'a-price-whole'})
        if preco_span:
            preco_atual = preco_span.get_text(strip=True)
            centavos = soup.find('span', {'class': 'a-price-fraction'})
            if centavos:
                preco_atual = f"{preco_atual}.{centavos.get_text(strip=True)}"
        
        # PREÇO ANTIGO (Amazon - formato "De: R$ XX,XX")
        preco_antigo = None
        antigo = soup.find('span', {'class': 'a-text-price'})
        if antigo:
            span = antigo.find('span', {'class': 'a-offscreen'})
            if span:
                texto = span.get_text()
                match = re.search(r'R\$\s*([\d.,]+)', texto)
                if match:
                    preco_antigo = match.group(1)
        
        # PARCELAMENTO
        parcelas = "Não informado"
        parcela_text = soup.find(string=re.compile(r'\d+x\s*R\$\s*[\d.,]+', re.I))
        if parcela_text:
            parcelas = parcela_text.strip()
        
        # FORMATAR PREÇOS
        preco_atual = formatar_preco_br(preco_atual)
        preco_antigo = formatar_preco_br(preco_antigo) if preco_antigo else None
        
        return {
            'nome': nome,
            'preco_atual': preco_atual,
            'preco_antigo': preco_antigo,
            'parcelas': parcelas
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
    return "✅ Robô de Preços - Versão Final"

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        
        if 'message' in data:
            chat_id = data['message']['chat']['id']
            texto = data['message'].get('text', '').strip()
            
            logger.info(f"📩 Mensagem: {texto[:50]}...")
            
            if texto == '/start':
                enviar_telegram(chat_id, 
                    "🤖 *Robô de Preços - Versão Final*\n\n"
                    "Envie links que eu mostro os dados!\n\n"
                    "📌 *Exemplos:*\n"
                    "• https://mercadolivre.com/sec/2TCy2TB\n"
                    "• https://amzn.to/46hzWsh"
                )
                return 'ok', 200
            
            enviar_telegram(chat_id, "🤖 Processando...")
            
            dados = None
            link_original = texto
            site = None
            
            # Extrair dados conforme o site
            if 'mercadolivre' in texto:
                site = 'mercadolivre'
                dados = extrair_mercadolivre_com_selenium(texto)
            elif 'amazon' in texto or 'amzn.to' in texto:
                site = 'amazon'
                dados = extrair_amazon_com_selenium(texto)
            else:
                enviar_telegram(chat_id, "❌ Envie link do Mercado Livre ou Amazon")
                return 'ok', 200
            
            if dados and dados['nome'] != "Nome não encontrado":
                # Criar link curto
                link_curto = criar_link_wordpress(link_original, dados['nome'])
                
                # Formatar mensagem
                mensagem_final = formatar_mensagem_completa(dados, link_curto, site)
                
                # Enviar
                enviar_telegram(chat_id, mensagem_final)
                logger.info("✅ Mensagem enviada")
            else:
                enviar_telegram(chat_id, "❌ Não consegui extrair os dados do produto")
        
        return 'ok', 200
        
    except Exception as e:
        logger.error(f"Erro: {e}")
        return 'ok', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🚀 Robô final iniciado na porta {port}")
    app.run(host='0.0.0.0', port=port)