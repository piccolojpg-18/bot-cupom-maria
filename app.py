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
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', "SUA_CHAVE_AQUI")  ← COLE SUA CHAVE GEMINI
WP_URL = "https://cupomemaria.com.br"
WP_USER = os.environ.get('WP_USER')
WP_APP_PASSWORD = os.environ.get('WP_APP_PASSWORD')

# Configurar Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-pro')  # Modelo gratuito

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
    except:
        try:
            service = Service(ChromeDriverManager().install())
            return webdriver.Chrome(service=service, options=chrome_options)
        except:
            return None

def processar_mercadolivre(url):
    driver = None
    try:
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
                time.sleep(3)
        except:
            try:
                links = driver.find_elements(By.XPATH, "//a[contains(@href, '/p/')]")
                if links:
                    driver.execute_script("arguments[0].click();", links[0])
                    time.sleep(3)
            except:
                pass
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        nome = soup.find('h1', class_='ui-pdp-title')
        nome = nome.get_text(strip=True) if nome else "Nome não encontrado"
        
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
        driver = criar_driver()
        if not driver:
            return None, None
        
        driver.get(url)
        time.sleep(3)
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        nome = soup.find('span', {'id': 'productTitle'})
        nome = nome.get_text(strip=True) if nome else "Nome não encontrado"
        
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

def gerar_texto_gemini(nome, preco, link_original):
    """
    🤖 Usa GEMINI para gerar texto de divulgação automático
    """
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
        # Fallback para o template padrão
        return f"🎀✨🛍️{nome}\n\n💸 por: {preco} 🔥🚨\n\nCompre usando o Link 👉 ({link_original})\n\n_*Essa promo pode acabar a qualquer momento*_"

def criar_post_wordpress(titulo, preco, link_original, loja):
    """Cria post no WordPress com template bonito"""
    try:
        # Usar Gemini para gerar o texto
        texto_promocional = gerar_texto_gemini(titulo, preco, link_original)
        
        # Preparar HTML bonito para o post
        conteudo = f"""
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background: #fff; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
    {texto_promocional.replace(chr(10), '<br>')}
</div>
        """
        
        post_data = {
            'title': titulo[:100],
            'content': conteudo,
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
            return response.json().get('link', '')
        else:
            logger.error(f"Erro WP: {response.status_code}")
            return None
    except Exception as e:
        logger.error(f"Erro WP: {e}")
        return None

@app.route('/', methods=['GET'])
def home():
    return "✅ Bot com Gemini funcionando!"

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
                enviar_telegram(chat_id, 
                    "🤖 *Bot com Inteligência Artificial*\n\n"
                    "✅ Gemini gera textos automáticos!\n"
                    "✅ Posts bonitos no WordPress!\n\n"
                    "Envie qualquer link do Mercado Livre ou Amazon."
                )
                return 'ok', 200
            
            enviar_telegram(chat_id, "⏳ Processando com IA...")
            
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
            
            if nome and preco:
                preco = formatar_preco_br(preco)
                
                # Criar post no WordPress (já chama Gemini internamente)
                post_link = criar_post_wordpress(nome, preco, texto, loja)
                
                if post_link:
                    # Resposta no Telegram
                    msg = f"🎀✨🛍️{nome}\n\n"
                    msg += f"💸 por: {preco} 🔥🚨\n\n"
                    msg += f"Compre usando o Link 👉 ({post_link})\n\n"
                    msg += "_*Essa promo pode acabar a qualquer momento*_"
                    enviar_telegram(chat_id, msg)
                else:
                    enviar_telegram(chat_id, "❌ Erro ao criar post")
            else:
                enviar_telegram(chat_id, "❌ Não consegui encontrar os dados")
        
        return 'ok', 200
    except Exception as e:
        logger.error(f"Erro: {e}")
        return 'ok', 200

@app.route('/healthz')
def health_check():
    """Endpoint para manter o bot ativo"""
    return {'status': 'ok', 'timestamp': time.time()}

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)