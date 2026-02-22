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

# CONFIGURAÇÕES
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', "8538755291:AAG2dmZW8KcAN7DnC7pnMIqoSqh490F1YiY")
WP_URL = "https://cupomemaria.com.br"
WP_USER = os.environ.get('WP_USER')
WP_APP_PASSWORD = os.environ.get('WP_APP_PASSWORD')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cache simples para evitar duplicatas
processed_urls = {}

def enviar_telegram(chat_id, texto):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={'chat_id': chat_id, 'text': texto, 'parse_mode': 'Markdown'}, timeout=5)
        return True
    except Exception as e:
        logger.error(f"Erro Telegram: {e}")
        return False

def criar_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
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

def extrair_preco_ml(url):
    driver = None
    try:
        logger.info(f"Acessando: {url}")
        driver = criar_driver()
        if not driver:
            return None, None
        
        driver.get(url)
        time.sleep(5)
        
        # Clicar no primeiro produto
        try:
            links = driver.find_elements(By.XPATH, "//a[contains(@href, '/p/')]")
            if links:
                driver.execute_script("arguments[0].click();", links[0])
                time.sleep(3)
        except Exception as e:
            logger.error(f"Erro ao clicar: {e}")
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # Nome
        nome = "Nome não encontrado"
        titulo = soup.find('h1', class_='ui-pdp-title')
        if titulo:
            nome = titulo.get_text(strip=True)
            logger.info(f"Nome: {nome[:50]}")
        
        # Preço atual
        preco = "Preço não encontrado"
        preco_span = soup.find('span', class_='andes-money-amount__fraction')
        if preco_span:
            preco = preco_span.get_text(strip=True)
            centavos = soup.find('span', class_='andes-money-amount__cents')
            if centavos:
                preco = f"{preco}.{centavos.get_text(strip=True)}"
            logger.info(f"Preço: {preco}")
        
        return nome, preco
        
    except Exception as e:
        logger.error(f"Erro: {e}")
        return None, None
    finally:
        if driver:
            driver.quit()

def criar_post_wordpress(titulo, preco, link_original):
    try:
        post_data = {
            'title': titulo[:100],
            'status': 'publish',
            'meta': {
                'preco_novo': preco,
                'link_afiliado': link_original
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
            logger.info(f"Post criado: {post_link}")
            return post_link
        else:
            logger.error(f"Erro WP: {response.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"Erro ao criar post: {e}")
        return None

@app.route('/', methods=['GET'])
def home():
    return "Bot ML funcionando"

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        
        if 'message' in data:
            chat_id = data['message']['chat']['id']
            texto = data['message'].get('text', '').strip()
            
            # Evitar duplicatas
            if texto in processed_urls:
                if time.time() - processed_urls[texto] < 300:  # 5 minutos
                    logger.info("URL já processada recentemente")
                    return 'ok', 200
            
            processed_urls[texto] = time.time()
            
            if texto == '/start':
                enviar_telegram(chat_id, "Envie um link do Mercado Livre")
                return 'ok', 200
            
            if 'mercadolivre' in texto.lower():
                enviar_telegram(chat_id, "🔍 Buscando preço...")
                
                nome, preco = extrair_preco_ml(texto)
                
                if nome and preco and nome != "Nome não encontrado":
                    # Criar post
                    post_link = criar_post_wordpress(nome, preco, texto)
                    
                    if post_link:
                        msg = f"🎀✨🛍️{nome}\n\n"
                        msg += f"💸 por: R$ {preco} 🔥🚨\n\n"
                        msg += f"Compre usando o Link 👉 ({post_link})\n\n"
                        msg += "_*Essa promo pode acabar a qualquer momento*_"
                        
                        enviar_telegram(chat_id, msg)
                    else:
                        enviar_telegram(chat_id, "❌ Erro ao criar post no site")
                else:
                    enviar_telegram(chat_id, "❌ Não consegui encontrar o preço")
            else:
                enviar_telegram(chat_id, "❌ Envie apenas links do Mercado Livre por enquanto")
        
        return 'ok', 200
        
    except Exception as e:
        logger.error(f"Erro webhook: {e}")
        return 'ok', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)