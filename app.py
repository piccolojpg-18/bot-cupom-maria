from flask import Flask, request
import requests
from bs4 import BeautifulSoup
import os
import re
import logging
import time
import google.generativeai as genai
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

app = Flask(__name__)

# CONFIGURAÇÕES
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', "8538755291:AAG2dmZW8KcAN7DnC7pnMIqoSqh490F1YiY")
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', "SUA_CHAVE_GEMINI_AQUI")
WP_URL = "https://cupomemaria.com.br"
WP_USER = os.environ.get('WP_USER')
WP_APP_PASSWORD = os.environ.get('WP_APP_PASSWORD')

# Configurar Gemini
if GEMINI_API_KEY and GEMINI_API_KEY != "SUA_CHAVE_GEMINI_AQUI":
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-pro')
    GEMINI_ATIVO = True
else:
    GEMINI_ATIVO = False
    logger.warning("⚠️ Gemini não configurado - usando template padrão")

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
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    
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
    """Extrai dados do Mercado Livre"""
    driver = None
    try:
        logger.info(f"📱 [ML] Processando: {url}")
        driver = criar_driver()
        if not driver:
            return None, None
        
        driver.get(url)
        time.sleep(4)
        
        # Clicar no botão "Ir para produto"
        try:
            botoes = driver.find_elements(By.XPATH, "//*[contains(text(), 'Ir para produto')]")
            if botoes:
                driver.execute_script("arguments[0].click();", botoes[0])
                logger.info("✅ [ML] Clique no botão Ir para produto")
                time.sleep(3)
        except Exception as e:
            logger.error(f"Erro ao clicar: {e}")
            try:
                links = driver.find_elements(By.XPATH, "//a[contains(@href, '/p/')]")
                if links:
                    driver.execute_script("arguments[0].click();", links[0])
                    logger.info("✅ [ML] Clique em link de produto")
                    time.sleep(3)
            except:
                pass
        
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
        if meta_price:
            preco = meta_price.get('content', '')
            logger.info(f"💰 [ML] Preço (meta): {preco}")
        else:
            preco_span = soup.find('span', class_='andes-money-amount__fraction')
            if preco_span:
                preco = preco_span.get_text(strip=True)
                centavos = soup.find('span', class_='andes-money-amount__cents')
                if centavos:
                    preco = f"{preco}.{centavos.get_text(strip=True)}"
                logger.info(f"💰 [ML] Preço (span): {preco}")
        
        return nome, preco
        
    except Exception as e:
        logger.error(f"❌ [ML] Erro: {e}")
        return None, None
    finally:
        if driver:
            driver.quit()

def processar_amazon(url):
    """Extrai dados da Amazon"""
    driver = None
    try:
        logger.info(f"📱 [AMZ] Processando: {url}")
        driver = criar_driver()
        if not driver:
            return None, None
        
        driver.get(url)
        time.sleep(3)
        
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

def gerar_texto_gemini(nome, preco, link_original):
    """Gera texto promocional usando Gemini"""
    if not GEMINI_ATIVO:
        return None
    
    try:
        prompt = f"""
        Crie um texto de divulgação para WhatsApp/Telegram sobre este produto:
        
        Produto: {nome}
        Preço: {preco}
        Link: {link_original}
        
        REGRAS:
        1. Texto curto e impactante (máx 300 caracteres)
        2. Use emojis estratégicos
        3. Crie senso de urgência
        4. Destaque o benefício principal
        5. Inclua call-to-action clara
        
        Formato que DEVE ser seguido:
        🎀✨🛍️[NOME DO PRODUTO]
        
        💸 por: [PREÇO] 🔥🚨
        
        Compre usando o Link 👉 ([LINK])
        
        _*Essa promo pode acabar a qualquer momento*_
        
        Gere APENAS o texto final, sem explicações.
        """
        
        response = model.generate_content(prompt)
        texto_gerado = response.text.strip()
        logger.info(f"✅ Gemini gerou texto: {texto_gerado[:50]}...")
        return texto_gerado
        
    except Exception as e:
        logger.error(f"Erro Gemini: {e}")
        return None

def criar_post_wordpress(titulo, preco, link_original, loja):
    """
    CRIA POST NO WORDPRESS COM CAMPOS ACF
    """
    try:
        logger.info(f"📝 [WP] Criando post...")
        
        # Tentar gerar texto com Gemini (se disponível)
        texto_promocional = gerar_texto_gemini(titulo, preco, link_original)
        
        # Se não tiver Gemini, usar template padrão
        if not texto_promocional:
            texto_promocional = f"🎀✨🛍️{titulo}\n\n💸 por: {preco} 🔥🚨\n\nCompre usando o Link 👉 ({link_original})\n\n_*Essa promo pode acabar a qualquer momento*_"
        
        # Montar conteúdo HTML para o post
        conteudo_html = f"""
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background: #fff; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
    {texto_promocional.replace(chr(10), '<br>')}
</div>
        """
        
        # Dados do post - FORMATO CORRETO para WordPress com ACF
        post_data = {
            'title': titulo[:100],
            'status': 'publish',
            'content': conteudo_html,
            'preco_novo': preco,              # ← Campo ACF direto
            'link_afiliado': link_original,    # ← Campo ACF direto
            'loja': loja,                       # ← Campo ACF direto
            'acf': {                             # ← Alguns plugins aceitam assim
                'preco_novo': preco,
                'link_afiliado': link_original,
                'loja': loja
            }
        }
        
        logger.info(f"📦 Enviando para WordPress: {post_data['title']}")
        logger.info(f"💰 Preço: {preco}")
        logger.info(f"🔗 Link: {link_original[:50]}...")
        
        # Enviar para WordPress
        wp_api_url = f"{WP_URL}/wp-json/wp/v2/posts"
        auth = (WP_USER, WP_APP_PASSWORD)
        
        response = requests.post(wp_api_url, json=post_data, auth=auth, timeout=10)
        
        if response.status_code in [200, 201]:
            post_data = response.json()
            post_link = post_data.get('link', '')
            logger.info(f"✅ [WP] Post criado: {post_link}")
            logger.info(f"✅ [WP] ID do post: {post_data.get('id')}")
            return post_link
        else:
            logger.error(f"❌ [WP] Erro {response.status_code}")
            logger.error(f"Resposta: {response.text[:200]}")  # Primeiros 200 caracteres
            return None
            
    except Exception as e:
        logger.error(f"❌ [WP] Erro: {e}")
        return None

@app.route('/', methods=['GET'])
def home():
    status_gemini = "✅ Ativo" if GEMINI_ATIVO else "❌ Não configurado"
    return f"✅ Bot Funcional - Gemini: {status_gemini}"

@app.route('/healthz')
def health_check():
    """Endpoint para manter o bot ativo"""
    return {'status': 'ok', 'gemini': GEMINI_ATIVO, 'timestamp': time.time()}

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
                status_gemini = "✅ com Gemini" if GEMINI_ATIVO else "❌ sem Gemini"
                enviar_telegram(chat_id, 
                    f"🤖 *Bot Inteligente {status_gemini}*\n\n"
                    "Envie links do Mercado Livre ou Amazon que eu:\n"
                    "1️⃣ Extraio os dados\n"
                    "2️⃣ Gero texto com IA\n"
                    "3️⃣ Publico no WordPress\n"
                    "4️⃣ Te dou o link do post!"
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
            
            if nome and preco and nome != "Nome não encontrado":
                preco = formatar_preco_br(preco)
                logger.info(f"✅ Dados OK: {nome[:50]}... - {preco}")
                
                # Criar post no WordPress
                post_link = criar_post_wordpress(nome, preco, texto, loja)
                
                if post_link:
                    # Mensagem de confirmação
                    msg = f"🎀✨🛍️{nome}\n\n"
                    msg += f"💸 por: {preco} 🔥🚨\n\n"
                    msg += f"Compre usando o Link 👉 ({post_link})\n\n"
                    msg += "_*Essa promo pode acabar a qualquer momento*_"
                    
                    enviar_telegram(chat_id, msg)
                    logger.info(f"✅ Processo concluído para: {nome[:50]}")
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
    logger.info(f"🤖 Gemini: {'✅ ATIVO' if GEMINI_ATIVO else '❌ DESATIVADO'}")
    app.run(host='0.0.0.0', port=port)