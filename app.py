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
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    
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

# ============================================
# FUNÇÃO MERCADO LIVRE
# ============================================
def processar_mercadolivre(url):
    """
    FLUXO MERCADO LIVRE:
    1️⃣ Entra no link original de afiliado
    2️⃣ Clica em "Ir para produto"
    3️⃣ Pega nome e preço
    """
    driver = None
    try:
        logger.info(f"📱 [ML] Processando: {url}")
        driver = criar_driver()
        if not driver:
            return None, None
        
        # 1️⃣ Entrar no link de afiliado
        driver.get(url)
        time.sleep(4)
        
        # 2️⃣ Procurar e clicar em "Ir para produto"
        link_encontrado = False
        
        # Método 1: Link que contém '/p/'
        try:
            link = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//a[contains(@href, '/p/')]"))
            )
            driver.execute_script("arguments[0].click();", link)
            logger.info("✅ [ML] Clique via link /p/")
            link_encontrado = True
        except:
            pass
        
        # Método 2: Link que contém 'MLB-'
        if not link_encontrado:
            try:
                link = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//a[contains(@href, '/MLB-')]"))
                )
                driver.execute_script("arguments[0].click();", link)
                logger.info("✅ [ML] Clique via link /MLB-/")
                link_encontrado = True
            except:
                pass
        
        # Método 3: Botão com texto "Ir para produto"
        if not link_encontrado:
            try:
                botoes = driver.find_elements(By.XPATH, "//*[contains(text(), 'Ir para produto') or contains(text(), 'Ver produto')]")
                if botoes:
                    driver.execute_script("arguments[0].click();", botoes[0])
                    logger.info("✅ [ML] Clique via botão de texto")
                    link_encontrado = True
            except:
                pass
        
        if not link_encontrado:
            logger.error("❌ [ML] Nenhum link/botão encontrado")
            return None, None
        
        time.sleep(3)
        
        # 3️⃣ Pegar nome e preço
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # Nome
        nome = "Nome não encontrado"
        titulo = soup.find('h1', class_='ui-pdp-title')
        if titulo:
            nome = titulo.get_text(strip=True)
            logger.info(f"📌 [ML] Nome: {nome[:50]}...")
        
        # Preço
        preco = "Preço não encontrado"
        meta_price = soup.find('meta', {'itemprop': 'price'})
        if meta_price and meta_price.get('content'):
            preco = meta_price.get('content')
        else:
            preco_span = soup.find('span', class_='andes-money-amount__fraction')
            if preco_span:
                preco = preco_span.get_text(strip=True)
                centavos = soup.find('span', class_='andes-money-amount__cents')
                if centavos:
                    preco = f"{preco}.{centavos.get_text(strip=True)}"
        
        preco = formatar_preco_br(preco)
        logger.info(f"💰 [ML] Preço: {preco}")
        
        return nome, preco
        
    except Exception as e:
        logger.error(f"❌ [ML] Erro: {e}")
        return None, None
    finally:
        if driver:
            driver.quit()

# ============================================
# FUNÇÃO AMAZON
# ============================================
def processar_amazon(url):
    """
    FLUXO AMAZON:
    1️⃣ Entra no link
    2️⃣ Pega nome e preço direto
    """
    driver = None
    try:
        logger.info(f"📱 [AMZ] Processando: {url}")
        driver = criar_driver()
        if not driver:
            return None, None
        
        # 1️⃣ Entrar no link
        driver.get(url)
        time.sleep(3)
        
        # 2️⃣ Pegar nome e preço
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # Nome
        nome = "Nome não encontrado"
        titulo = soup.find('span', {'id': 'productTitle'})
        if titulo:
            nome = titulo.get_text(strip=True)
            logger.info(f"📌 [AMZ] Nome: {nome[:50]}...")
        
        # Preço
        preco = "Preço não encontrado"
        preco_span = soup.find('span', {'class': 'a-price-whole'})
        if preco_span:
            preco = preco_span.get_text(strip=True)
            centavos = soup.find('span', {'class': 'a-price-fraction'})
            if centavos:
                preco = f"{preco}.{centavos.get_text(strip=True)}"
        
        preco = formatar_preco_br(preco)
        logger.info(f"💰 [AMZ] Preço: {preco}")
        
        return nome, preco
        
    except Exception as e:
        logger.error(f"❌ [AMZ] Erro: {e}")
        return None, None
    finally:
        if driver:
            driver.quit()

# ============================================
# FUNÇÕES COMPARTILHADAS
# ============================================
def criar_post_wordpress(titulo, preco, link_original, loja):
    """
    3️⃣ Publica link original no WordPress
    """
    try:
        logger.info(f"📝 [WP] Criando post para: {titulo[:50]}...")
        
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
            logger.info(f"✅ [WP] Post criado: {post_link}")
            return post_link
        else:
            logger.error(f"❌ [WP] Erro {response.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"❌ [WP] Erro: {e}")
        return None

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

def formatar_mensagem_telegram(nome, preco, post_link):
    """
    4️⃣ Retorna link WordPress do post no Telegram
    """
    msg = f"🎀✨🛍️{nome}\n\n"
    msg += f"💸 por: {preco} 🔥🚨\n\n"
    msg += f"Compre usando o Link 👉 ({post_link})\n\n"
    msg += "_*Essa promo pode acabar a qualquer momento*_"
    return msg

# ============================================
# WEBHOOK PRINCIPAL
# ============================================
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
            
            # Evitar duplicatas (5 minutos)
            if texto in processed_urls:
                if time.time() - processed_urls[texto] < 300:
                    logger.info("⏱️ URL já processada recentemente")
                    return 'ok', 200
            
            processed_urls[texto] = time.time()
            
            if texto == '/start':
                enviar_telegram(chat_id, 
                    "🤖 *Bot Funcional*\n\n"
                    "**MERCADO LIVRE**\n"
                    "1️⃣ Entra no link de afiliado\n"
                    "2️⃣ Clica em Ir para produto\n"
                    "3️⃣ Pega nome e preço\n"
                    "4️⃣ Publica no WordPress\n"
                    "5️⃣ Retorna link do post\n\n"
                    "**AMAZON**\n"
                    "1️⃣ Entra no link\n"
                    "2️⃣ Pega nome e preço\n"
                    "3️⃣ Publica no WordPress\n"
                    "4️⃣ Retorna link do post"
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
                # Publicar no WordPress com link original
                post_link = criar_post_wordpress(nome, preco, texto, loja)
                
                if post_link:
                    # Retornar link do post no Telegram
                    msg = formatar_mensagem_telegram(nome, preco, post_link)
                    enviar_telegram(chat_id, msg)
                    logger.info(f"✅ Processo concluído para: {nome[:50]}")
                else:
                    enviar_telegram(chat_id, "❌ Erro ao criar post no WordPress")
            else:
                enviar_telegram(chat_id, "❌ Não consegui encontrar nome e preço do produto")
        
        return 'ok', 200
        
    except Exception as e:
        logger.error(f"❌ Erro webhook: {e}")
        return 'ok', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🚀 Bot funcional iniciado na porta {port}")
    app.run(host='0.0.0.0', port=port)