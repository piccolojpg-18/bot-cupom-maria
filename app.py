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
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
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
    """
    FLUXO MERCADO LIVRE:
    1️⃣ Abre link de afiliado
    2️⃣ Clica no botão azul "Ir para produto"
    3️⃣ Pega nome e preço da página do produto
    """
    driver = None
    try:
        logger.info(f"📱 [ML] Processando: {url}")
        driver = criar_driver()
        if not driver:
            return None, None
        
        # 1️⃣ Abrir link de afiliado
        driver.get(url)
        time.sleep(4)
        
        # 2️⃣ PROCURAR E CLICAR NO BOTÃO AZUL "IR PARA PRODUTO"
        botao_encontrado = False
        
        # Método 1: Procurar por botão com texto exato "Ir para produto"
        try:
            botoes = driver.find_elements(By.XPATH, "//*[contains(text(), 'Ir para produto')]")
            for botao in botoes:
                # Verificar se é um botão azul (pela cor ou classe)
                cor = botao.value_of_css_property('background-color')
                classe = botao.get_attribute('class') or ''
                if 'blue' in cor or 'rgb(0, 123, 255)' in cor or 'botao' in classe.lower() or 'btn' in classe.lower():
                    driver.execute_script("arguments[0].click();", botao)
                    logger.info("✅ [ML] Clique no botão 'Ir para produto'")
                    botao_encontrado = True
                    break
        except Exception as e:
            logger.error(f"Erro método 1: {e}")
        
        # Método 2: Procurar por link que parece botão
        if not botao_encontrado:
            try:
                links = driver.find_elements(By.TAG_NAME, "a")
                for link in links:
                    classe = link.get_attribute('class') or ''
                    texto = link.text.strip()
                    if 'botao' in classe.lower() or 'btn' in classe.lower() or 'ir para produto' in texto.lower():
                        driver.execute_script("arguments[0].click();", link)
                        logger.info("✅ [ML] Clique em link com aparência de botão")
                        botao_encontrado = True
                        break
            except Exception as e:
                logger.error(f"Erro método 2: {e}")
        
        # Método 3: Fallback - clicar no primeiro link de produto
        if not botao_encontrado:
            try:
                links = driver.find_elements(By.XPATH, "//a[contains(@href, '/p/') or contains(@href, '/MLB-')]")
                if links:
                    driver.execute_script("arguments[0].click();", links[0])
                    logger.info("✅ [ML] Clique em link de produto (fallback)")
                    botao_encontrado = True
            except Exception as e:
                logger.error(f"Erro método 3: {e}")
        
        if not botao_encontrado:
            logger.error("❌ [ML] Nenhum botão/link encontrado")
            return None, None
        
        # Aguardar página do produto carregar
        time.sleep(3)
        
        # 3️⃣ Extrair nome e preço da página do produto
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # NOME
        nome = "Nome não encontrado"
        titulo = soup.find('h1', class_='ui-pdp-title')
        if not titulo:
            titulo = soup.find('h1')
        if titulo:
            nome = titulo.get_text(strip=True)
            logger.info(f"📌 [ML] Nome: {nome[:50]}...")
        
        # PREÇO
        preco = "Preço não encontrado"
        
        # Método 1: Meta tag
        meta_price = soup.find('meta', {'itemprop': 'price'})
        if meta_price and meta_price.get('content'):
            preco = meta_price.get('content')
            logger.info(f"💰 [ML] Preço (meta): {preco}")
        
        # Método 2: Span de preço
        if preco == "Preço não encontrado":
            preco_span = soup.find('span', class_='andes-money-amount__fraction')
            if preco_span:
                preco = preco_span.get_text(strip=True)
                centavos = soup.find('span', class_='andes-money-amount__cents')
                if centavos:
                    preco = f"{preco}.{centavos.get_text(strip=True)}"
                logger.info(f"💰 [ML] Preço (span): {preco}")
        
        # Método 3: Texto com R$
        if preco == "Preço não encontrado":
            texto_preco = soup.find(string=re.compile(r'R\$\s*[\d.,]+'))
            if texto_preco:
                match = re.search(r'R\$\s*([\d.,]+)', texto_preco)
                if match:
                    preco = match.group(1)
                    logger.info(f"💰 [ML] Preço (texto): {preco}")
        
        # Formatar preço
        if preco and preco != "Preço não encontrado":
            preco = formatar_preco_br(preco)
        
        logger.info(f"✅ [ML] Final: {preco}")
        return nome, preco
        
    except Exception as e:
        logger.error(f"❌ [ML] Erro: {e}")
        return None, None
    finally:
        if driver:
            driver.quit()

def processar_amazon(url):
    """FLUXO AMAZON"""
    driver = None
    try:
        logger.info(f"📱 [AMZ] Processando: {url}")
        driver = criar_driver()
        if not driver:
            return None, None
        
        driver.get(url)
        time.sleep(3)
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # NOME
        nome = "Nome não encontrado"
        titulo = soup.find('span', {'id': 'productTitle'})
        if titulo:
            nome = titulo.get_text(strip=True)
            logger.info(f"📌 [AMZ] Nome: {nome[:50]}...")
        
        # PREÇO
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
            if len(valor) > 2:
                reais = valor[:-2]
                centavos = valor[-2:]
                if len(reais) > 3:
                    reais = re.sub(r'(\d)(?=(\d{3})+(?!\d))', r'\1.', reais)
                return f"R$ {reais},{centavos}"
            else:
                return f"R$ {valor},00"
    except:
        return f"R$ {valor}"

def criar_post_wordpress(titulo, preco, link_original, loja):
    """Cria post no WordPress"""
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
            logger.info(f"✅ [WP] Post criado: {post_link}")
            return post_link
        else:
            logger.error(f"❌ [WP] Erro {response.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"❌ [WP] Erro: {e}")
        return None

def formatar_mensagem_telegram(nome, preco, post_link):
    """Template fixo de mensagem"""
    msg = f"🎀✨🛍️{nome}\n\n"
    msg += f"💸 por: {preco} 🔥🚨\n\n"
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
            
            # Evitar duplicatas (5 minutos)
            if texto in processed_urls:
                if time.time() - processed_urls[texto] < 300:
                    logger.info("⏱️ URL já processada")
                    return 'ok', 200
            
            processed_urls[texto] = time.time()
            
            if texto == '/start':
                enviar_telegram(chat_id, 
                    "🤖 *Bot Funcional*\n\n"
                    "✅ Mercado Livre: clica no botão azul\n"
                    "✅ Amazon: pega preço direto\n\n"
                    "Envie qualquer link que eu processo!"
                )
                return 'ok', 200
            
            enviar_telegram(chat_id, "⏳ Processando...")
            
            nome = None
            preco = None
            loja = None
            
            # Identificar site
            if 'mercadolivre' in texto.lower() or 'mercadolivre.com/sec' in texto.lower():
                loja = 'Mercado Livre'
                nome, preco = processar_mercadolivre(texto)
            elif 'amazon' in texto.lower() or 'amzn.to' in texto.lower():
                loja = 'Amazon'
                nome, preco = processar_amazon(texto)
            else:
                enviar_telegram(chat_id, "❌ Envie link do Mercado Livre ou Amazon")
                return 'ok', 200
            
            # Validar dados
            if nome and preco and nome != "Nome não encontrado" and preco != "Preço não encontrado":
                logger.info(f"✅ Dados OK - Nome: {nome[:30]}... Preço: {preco}")
                
                # Criar post
                post_link = criar_post_wordpress(nome, preco, texto, loja)
                
                if post_link:
                    msg = formatar_mensagem_telegram(nome, preco, post_link)
                    enviar_telegram(chat_id, msg)
                else:
                    enviar_telegram(chat_id, "❌ Erro ao criar post no WordPress")
            else:
                logger.warning(f"❌ Dados inválidos - Nome: {nome}, Preço: {preco}")
                enviar_telegram(chat_id, "❌ Não consegui encontrar nome e preço do produto")
        
        return 'ok', 200
        
    except Exception as e:
        logger.error(f"❌ Erro webhook: {e}")
        return 'ok', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🚀 Bot iniciado na porta {port}")
    app.run(host='0.0.0.0', port=port)