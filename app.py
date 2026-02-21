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

# CONFIGURAÇÕES
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', "8538755291:AAG2dmZW8KcAN7DnC7pnMIqoSqh490F1YiY")

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
        logger.info("Usando Chrome do sistema")
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        return driver
    except Exception as e:
        logger.error(f"Erro Chrome: {e}")
        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            return driver
        except:
            return None

def extrair_preco_ml(url_afiliado):
    """Extrai preço do Mercado Livre"""
    driver = None
    try:
        logger.info("Extraindo Mercado Livre")
        driver = criar_driver()
        if not driver:
            return None, None
        
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
        
        # Preço
        preco = "Preço não encontrado"
        meta_price = soup.find('meta', {'itemprop': 'price'})
        if meta_price:
            preco = meta_price.get('content', '')
        else:
            preco_span = soup.find('span', class_='andes-money-amount__fraction')
            if preco_span:
                preco = preco_span.get_text(strip=True)
                centavos = soup.find('span', class_='andes-money-amount__cents')
                if centavos:
                    preco = f"{preco}.{centavos.get_text(strip=True)}"
        
        preco = formatar_preco_br(preco)
        return nome, preco
        
    except Exception as e:
        logger.error(f"Erro ML: {e}")
        return None, None
    finally:
        if driver:
            driver.quit()

def extrair_preco_amazon(url):
    """Extrai preço da Amazon"""
    driver = None
    try:
        logger.info("Extraindo Amazon")
        driver = criar_driver()
        if not driver:
            return None, None
        
        driver.get(url)
        time.sleep(5)
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # Nome
        nome = "Nome não encontrado"
        titulo = soup.find('span', {'id': 'productTitle'})
        if titulo:
            nome = titulo.get_text(strip=True)
        
        # Preço
        preco = "Preço não encontrado"
        preco_span = soup.find('span', {'class': 'a-price-whole'})
        if preco_span:
            preco = preco_span.get_text(strip=True)
            centavos = soup.find('span', {'class': 'a-price-fraction'})
            if centavos:
                preco = f"{preco}.{centavos.get_text(strip=True)}"
        
        preco = formatar_preco_br(preco)
        return nome, preco
        
    except Exception as e:
        logger.error(f"Erro Amazon: {e}")
        return None, None
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
    return "✅ Bot de Preços Online"

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
                    "🤖 *Bot de Preços*\n\n"
                    "Envie um link do Mercado Livre ou Amazon\n"
                    "Que eu mostro o nome e o preço!"
                )
                return 'ok', 200
            
            enviar_telegram(chat_id, "🔍 Buscando preço...")
            
            nome = None
            preco = None
            
            if 'mercadolivre' in texto:
                nome, preco = extrair_preco_ml(texto)
            elif 'amazon' in texto or 'amzn.to' in texto:
                nome, preco = extrair_preco_amazon(texto)
            else:
                enviar_telegram(chat_id, "❌ Envie link do Mercado Livre ou Amazon")
                return 'ok', 200
            
            if nome and preco:
                msg = f"📦 *{nome}*\n\n💰 *{preco}*"
                enviar_telegram(chat_id, msg)
            else:
                enviar_telegram(chat_id, "❌ Não consegui encontrar o preço")
        
        return 'ok', 200
        
    except Exception as e:
        logger.error(f"Erro: {e}")
        return 'ok', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🚀 Bot iniciado na porta {port}")
    app.run(host='0.0.0.0', port=port)