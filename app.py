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

    chrome_path = "/opt/render/project/.chrome/opt/google/chrome/google-chrome"
    if os.path.exists(chrome_path):
        chrome_options.binary_location = chrome_path

    try:
        return webdriver.Chrome(options=chrome_options)
    except Exception as e:
        logger.error(f"Erro Chrome: {e}")
        try:
            service = Service(ChromeDriverManager().install())
            return webdriver.Chrome(service=service, options=chrome_options)
        except Exception as e2:
            logger.error(f"Erro fallback: {e2}")
            return None

def extrair_preco_primeiro_produto(url):
    """
    Extrai o nome e o preço do PRIMEIRO produto da página de perfil.
    """
    driver = None
    try:
        logger.info(f"Acessando página de perfil: {url}")
        driver = criar_driver()
        if not driver:
            return None, None

        driver.get(url)
        time.sleep(5)  # Aguarda carregar

        soup = BeautifulSoup(driver.page_source, 'html.parser')

        # --- Estratégia para encontrar o primeiro produto ---
        primeiro_produto = None

        # 1. Tenta encontrar pelo "MAIS VENDIDO" (é um bom indicador)
        mais_vendido = soup.find('span', string=re.compile(r'MAIS VENDIDO', re.I))
        if mais_vendido:
            primeiro_produto = mais_vendido.find_parent(['div', 'li', 'section'])
            logger.info("Produto encontrado pela tag 'MAIS VENDIDO'")

        # 2. Se não achou, pega o primeiro card de produto que tiver um preço
        if not primeiro_produto:
            cards = soup.find_all(['div', 'li', 'section'], class_=re.compile(r'ui-search-layout__item|andes-card|product', re.I))
            if cards:
                primeiro_produto = cards[0]
                logger.info("Produto encontrado pelo primeiro card da lista")

        if not primeiro_produto:
            logger.warning("Nenhum card de produto encontrado na página.")
            return None, None

        # --- Extrair Nome ---
        nome = "Nome não encontrado"
        nome_tag = primeiro_produto.find(['h2', 'h3'], class_=re.compile(r'title|name|product', re.I))
        if nome_tag:
            nome = nome_tag.get_text(strip=True)
            logger.info(f"Nome extraído: {nome[:50]}...")
        else:
            # Fallback: pegar qualquer heading
            heading = primeiro_produto.find(['h2', 'h3', 'h4'])
            if heading:
                nome = heading.get_text(strip=True)

        # --- Extrair Preço ---
        preco = "Preço não encontrado"
        # Procura por um elemento que tenha 'R$' e números
        precos = primeiro_produto.find_all(string=re.compile(r'R\$\s*[\d.,]+'))
        if precos:
            # Pega o primeiro preço encontrado (geralmente o principal)
            preco_texto = precos[0].strip()
            # Extrai apenas os números, pontos e vírgulas
            match = re.search(r'R\$\s*([\d.,]+)', preco_texto)
            if match:
                preco_raw = match.group(1)
                # Formata o preço
                preco = formatar_preco_br(preco_raw)
                logger.info(f"Preço extraído: {preco}")
            else:
                preco = preco_texto
        else:
            # Fallback: procurar por span de preço (ML)
            preco_span = primeiro_produto.find('span', class_='andes-money-amount__fraction')
            if preco_span:
                preco_raw = preco_span.get_text(strip=True)
                preco = formatar_preco_br(preco_raw)
                logger.info(f"Preço extraído (span): {preco}")

        return nome, preco

    except Exception as e:
        logger.error(f"Erro na extração: {e}")
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
            logger.error(f"Erro WP: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        logger.error(f"Erro ao criar post: {e}")
        return None

@app.route('/', methods=['GET'])
def home():
    return "Bot Funcional - Extrai o primeiro produto da página"

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()

        if 'message' in data:
            chat_id = data['message']['chat']['id']
            texto = data['message'].get('text', '').strip()

            # Evitar duplicatas
            if texto in processed_urls:
                if time.time() - processed_urls[texto] < 300:
                    logger.info("URL já processada recentemente")
                    return 'ok', 200

            processed_urls[texto] = time.time()

            if texto == '/start':
                enviar_telegram(chat_id, "Envie um link do Mercado Livre (mesmo de afiliado)!")
                return 'ok', 200

            if 'mercadolivre' in texto.lower():
                enviar_telegram(chat_id, "🔍 Buscando preço do primeiro produto...")

                nome, preco = extrair_preco_primeiro_produto(texto)

                if nome and preco and nome != "Nome não encontrado":
                    # Criar post
                    post_link = criar_post_wordpress(nome, preco, texto)

                    if post_link:
                        msg = f"🎀✨🛍️{nome}\n\n"
                        msg += f"💸 por: {preco} 🔥🚨\n\n"
                        msg += f"Compre usando o Link 👉 ({post_link})\n\n"
                        msg += "_*Essa promo pode acabar a qualquer momento*_"

                        enviar_telegram(chat_id, msg)
                    else:
                        enviar_telegram(chat_id, "❌ Erro ao criar post no site")
                else:
                    enviar_telegram(chat_id, "❌ Não consegui encontrar o preço do primeiro produto.")
            else:
                enviar_telegram(chat_id, "❌ No momento, só funciono com links do Mercado Livre.")

        return 'ok', 200

    except Exception as e:
        logger.error(f"Erro webhook: {e}")
        return 'ok', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)