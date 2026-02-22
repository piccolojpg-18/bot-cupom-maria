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

def processar_mercadolivre(url):
    driver = None
    try:
        logger.info(f"📱 [ML] Processando: {url}")
        driver = criar_driver()
        if not driver:
            return None, None
        
        driver.get(url)
        time.sleep(4)
        
        # Tentar clicar no link do produto
        try:
            link = driver.find_element(By.XPATH, "//a[contains(@href, '/p/')]")
            driver.execute_script("arguments[0].click();", link)
            time.sleep(3)
        except:
            try:
                link = driver.find_element(By.XPATH, "//a[contains(@href, '/MLB-')]")
                driver.execute_script("arguments[0].click();", link)
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
        
        return nome, preco
        
    except Exception as e:
        logger.error(f"Erro ML: {e}")
        return None, None
    finally:
        if driver:
            driver.quit()

def processar_amazon(url):
    driver = None
    try:
        logger.info(f"📱 [AMZ] Processando: {url}")
        driver = criar_driver()
        if not driver:
            return None, None
        
        driver.get(url)
        time.sleep(3)
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        nome = "Nome não encontrado"
        titulo = soup.find('span', {'id': 'productTitle'})
        if titulo:
            nome = titulo.get_text(strip=True)
        
        preco = "Preço não encontrado"
        preco_span = soup.find('span', {'class': 'a-price-whole'})
        if preco_span:
            preco = preco_span.get_text(strip=True)
            centavos = soup.find('span', {'class': 'a-price-fraction'})
            if centavos:
                preco = f"{preco}.{centavos.get_text(strip=True)}"
        
        return nome, preco
        
    except Exception as e:
        logger.error(f"Erro Amazon: {e}")
        return None, None
    finally:
        if driver:
            driver.quit()

def formatar_preco_br(valor):
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

def criar_post_wordpress(titulo, preco, link_original, loja):
    try:
        logger.info(f"📝 [WP] Criando post...")
        
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
            return post_link
        else:
            return None
            
    except Exception as e:
        logger.error(f"Erro WP: {e}")
        return None

def formatar_mensagem_telegram(nome, preco, post_link):
    msg = f"🎀✨🛍️{nome}\n\n"
    msg += f"💸 por: {preco} 🔥🚨\n\n"
    msg += f"Compre usando o Link 👉 ({post_link})\n\n"
    msg += "_*Essa promo pode acabar a qualquer momento*_"
    return msg

@app.route('/', methods=['GET'])
def home():
    return "✅ Bot Estável"

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        
        if 'message' in data:
            chat_id = data['message']['chat']['id']
            texto = data['message'].get('text', '').strip()
            
            if texto in processed_urls:
                if time.time() - processed_urls[texto] < 300:
                    return 'ok', 200
            
            processed_urls[texto] = time.time()
            
            if texto == '/start':
                enviar_telegram(chat_id, "🤖 Bot Estável\n\nEnvie links do Mercado Livre ou Amazon")
                return 'ok', 200
            
            enviar_telegram(chat_id, "⏳ Processando...")
            
            nome = None
            preco = None
            loja = None
            
            if 'mercadolivre' in texto.lower():
                loja = 'Mercado Livre'
                nome, preco = processar_mercadolivre(texto)
            elif 'amazon' in texto.lower() or 'amzn.to' in texto.lower():
                loja = 'Amazon'
                nome, preco = processar_amazon(texto)
            else:
                enviar_telegram(chat_id, "❌ Envie link do Mercado Livre ou Amazon")
                return 'ok', 200
            
            if nome and preco and nome != "Nome não encontrado":
                preco = formatar_preco_br(preco)
                post_link = criar_post_wordpress(nome, preco, texto, loja)
                
                if post_link:
                    msg = formatar_mensagem_telegram(nome, preco, post_link)
                    enviar_telegram(chat_id, msg)
                else:
                    enviar_telegram(chat_id, "❌ Erro ao criar post")
            else:
                enviar_telegram(chat_id, "❌ Não consegui encontrar os dados")
        
        return 'ok', 200
        
    except Exception as e:
        logger.error(f"Erro: {e}")
        return 'ok', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)