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
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

app = Flask(__name__)

# CONFIGURAÇÕES
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', "8538755291:AAG2dmZW8KcAN7DnC7pnMIqoSqh490F1YiY")
WP_URL = "https://cupomemaria.com.br"
WP_USER = os.environ.get('WP_USER')
WP_APP_PASSWORD = os.environ.get('WP_APP_PASSWORD')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

processed_urls = {}

def enviar_telegram(chat_id, texto):
    """Envia mensagem para o Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={'chat_id': chat_id, 'text': texto, 'parse_mode': 'Markdown'}, timeout=5)
        return True
    except Exception as e:
        logger.error(f"Erro Telegram: {e}")
        return False

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
    except Exception as e:
        logger.error(f"Erro Chrome: {e}")
        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            return driver
        except Exception as e2:
            logger.error(f"Erro fallback: {e2}")
            return None

https://mercadolivre.com/sec/28i2LGt

def processar_amazon(url):
    """
    1. Entra no link
    2. Pega nome e preço atual
    """
    driver = None
    try:
        logger.info(f"📱 Processando Amazon: {url}")
        driver = criar_driver()
        if not driver:
            return None, None
        
        driver.get(url)
        time.sleep(3)
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # Nome
        nome = None
        titulo = soup.find('span', {'id': 'productTitle'})
        if titulo:
            nome = titulo.get_text(strip=True)
        
        # Preço atual
        preco = None
        preco_span = soup.find('span', {'class': 'a-price-whole'})
        if preco_span:
            preco = preco_span.get_text(strip=True)
            centavos = soup.find('span', {'class': 'a-price-fraction'})
            if centavos:
                preco = f"{preco}.{centavos.get_text(strip=True)}"
            preco = formatar_preco_br(preco)
        
        return nome, preco
        
    except Exception as e:
        logger.error(f"Erro processamento Amazon: {e}")
        return None, None
    finally:
        if driver:
            driver.quit()

def criar_post_wordpress(titulo, preco, link_original, loja):
    """Cria post no WordPress com link original"""
    try:
        logger.info(f"📝 Criando post para: {titulo[:50]}")
        
        post_data = {
            'title': titulo[:100],
            'status': 'publish',
            'meta': {
                'preco_novo': preco,
                'link_afiliado': link_original,
                'loja': loja
            }
        }
        
        response = requests.post(
            f"{WP_URL}/wp-json/wp/v2/posts",
            json=post_data,
            auth=(WP_USER, WP_APP_PASSWORD),
            timeout=10
        )
        
        if response.status_code in [200, 201]:
            post_link = response.json().get('link', '')
            logger.info(f"✅ Post criado: {post_link}")
            return post_link
        else:
            logger.error(f"Erro WP: {response.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"Erro ao criar post: {e}")
        return None

def formatar_preco_br(valor):
    """Formata preço para R$ 1.234,56"""
    if not valor:
        return "Preço não encontrado"
    
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

def formatar_mensagem_telegram(dados, post_link):
    """Template fixo de mensagem"""
    msg = f"🎀✨🛍️{dados['nome']}\n\n"
    msg += f"💸 por: {dados['preco']} 🔥🚨\n\n"
    msg += f"Compre usando o Link 👉 ({post_link})\n\n"
    msg += "_*Essa promo pode acabar a qualquer momento*_"
    return msg

@app.route('/', methods=['GET'])
def home():
    return "✅ Bot Funcional - Mercado Livre e Amazon"

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        
        if 'message' in data:
            chat_id = data['message']['chat']['id']
            texto = data['message'].get('text', '').strip()
            
            # Evitar duplicatas (5 minutos de cooldown)
            if texto in processed_urls:
                if time.time() - processed_urls[texto] < 300:
                    logger.info("URL já processada recentemente")
                    return 'ok', 200
            
            processed_urls[texto] = time.time()
            
            if texto == '/start':
                enviar_telegram(chat_id, 
                    "🤖 *Bot Funcional*\n\n"
                    "Envie links que eu:\n"
                    "1️⃣ Entro no link\n"
                    "2️⃣ Pego nome e preço\n"
                    "3️⃣ Publico no site\n"
                    "4️⃣ Te dou o link do post\n\n"
                    "📌 Mercado Livre e Amazon"
                )
                return 'ok', 200
            
            enviar_telegram(chat_id, "⏳ Processando...")
            
            nome = None
            preco = None
            loja = None
            
            # Identificar site e processar
            if 'mercadolivre' in texto.lower() or 'mercadolivre.com/sec' in texto.lower():
                loja = 'Mercado Livre'
                nome, preco = processar_mercadolivre(texto)
            elif 'amazon' in texto.lower() or 'amzn.to' in texto.lower():
                loja = 'Amazon'
                nome, preco = processar_amazon(texto)
            else:
                enviar_telegram(chat_id, "❌ Envie link do Mercado Livre ou Amazon")
                return 'ok', 200
            
            if nome and preco and nome != "Nome não encontrado":
                # Criar post no WordPress
                post_link = criar_post_wordpress(nome, preco, texto, loja)
                
                if post_link:
                    dados = {'nome': nome, 'preco': preco}
                    msg = formatar_mensagem_telegram(dados, post_link)
                    enviar_telegram(chat_id, msg)
                    logger.info(f"✅ Processo concluído para: {nome[:50]}")
                else:
                    enviar_telegram(chat_id, "❌ Erro ao criar post no site")
            else:
                enviar_telegram(chat_id, "❌ Não consegui encontrar nome e preço do produto")
        
        return 'ok', 200
        
    except Exception as e:
        logger.error(f"Erro webhook: {e}")
        return 'ok', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🚀 Bot funcional iniciado na porta {port}")
    app.run(host='0.0.0.0', port=port)