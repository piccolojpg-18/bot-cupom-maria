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
TELEGRAM_TOKEN = "8538755291:AAG2dmZW8KcAN7DnC7pnMIqoSqh490F1YiY"

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
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Caminho do Chrome no Render
    chrome_path = "/opt/render/project/.chrome/opt/google/chrome/google-chrome"
    if os.path.exists(chrome_path):
        chrome_options.binary_location = chrome_path
        logger.info(f"Usando Chrome em: {chrome_path}")
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        logger.info("Chrome iniciado com sucesso")
        return driver
    except Exception as e:
        logger.error(f"Erro ao iniciar Chrome: {e}")
        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            return driver
        except:
            return None

def extrair_mercadolivre_com_selenium(url_afiliado):
    """
    Usa Selenium para Mercado Livre
    """
    driver = None
    try:
        logger.info(f"Iniciando Selenium ML: {url_afiliado}")
        driver = criar_driver()
        
        if not driver:
            return None
        
        # Abrir página de perfil
        driver.get(url_afiliado)
        time.sleep(5)
        
        # Clicar no primeiro produto
        try:
            links_produto = driver.find_elements(By.XPATH, "//a[contains(@href, '/p/')]")
            if links_produto:
                driver.execute_script("arguments[0].click();", links_produto[0])
                time.sleep(3)
        except:
            pass
        
        # Extrair dados
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
        
        # PREÇO ANTIGO (CORRIGIDO)
        preco_antigo = None
        logger.info("Procurando preço antigo no ML...")
        
        # Método 1: Classe andes-money-amount--previous
        antigo = soup.find('span', class_='andes-money-amount--previous')
        if antigo:
            valor = antigo.find('span', class_='andes-money-amount__fraction')
            if valor:
                preco_antigo = valor.get_text(strip=True)
        
        # Método 2: Procurar por dois preços diferentes
        if not preco_antigo:
            todos_precos = soup.find_all(string=re.compile(r'R\$\s*[\d.,]+'))
            if len(todos_precos) >= 2:
                match = re.search(r'R\$\s*([\d.,]+)', str(todos_precos[0]))
                if match:
                    preco_antigo = match.group(1)
        
        # PARCELAMENTO
        parcelas = "Não informado"
        parcela_text = soup.find('span', class_='ui-pdp-installments')
        if parcela_text:
            parcelas = parcela_text.get_text(strip=True)
        
        # FRETE GRÁTIS
        frete_gratis = bool(soup.find(string=re.compile(r'Frete grátis', re.I)))
        
        # FORMATAR PREÇOS
        preco_atual = formatar_preco_br(preco_atual)
        preco_antigo = formatar_preco_br(preco_antigo) if preco_antigo else None
        
        return {
            'site': 'mercadolivre',
            'nome': nome,
            'preco_atual': preco_atual,
            'preco_antigo': preco_antigo,
            'parcelas': parcelas,
            'frete_gratis': frete_gratis
        }
        
    except Exception as e:
        logger.error(f"Erro no ML: {e}")
        return None
    finally:
        if driver:
            driver.quit()

def extrair_amazon_com_selenium(url):
    """
    Usa Selenium para Amazon
    """
    driver = None
    try:
        logger.info(f"Iniciando Selenium Amazon: {url}")
        driver = criar_driver()
        
        if not driver:
            return None
        
        # Abrir página do produto
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
        
        # Tentar diferentes seletores da Amazon
        preco_span = soup.find('span', {'class': 'a-price-whole'})
        if preco_span:
            preco_atual = preco_span.get_text(strip=True)
            centavos = soup.find('span', {'class': 'a-price-fraction'})
            if centavos:
                preco_atual = f"{preco_atual}.{centavos.get_text(strip=True)}"
        
        # PREÇO ANTIGO (Amazon)
        preco_antigo = None
        logger.info("Procurando preço antigo na Amazon...")
        
        # Método 1: Preço riscado
        antigo = soup.find('span', {'class': 'a-text-price'})
        if antigo:
            span = antigo.find('span', {'class': 'a-offscreen'})
            if span:
                texto = span.get_text()
                match = re.search(r'R\$\s*([\d.,]+)', texto)
                if match:
                    preco_antigo = match.group(1)
        
        # Método 2: Procurar por "De: R$"
        if not preco_antigo:
            texto_antigo = soup.find(string=re.compile(r'De:\s*R\$\s*[\d.,]+', re.I))
            if texto_antigo:
                match = re.search(r'R\$\s*([\d.,]+)', texto_antigo)
                if match:
                    preco_antigo = match.group(1)
        
        # PARCELAMENTO (Amazon)
        parcelas = "Não informado"
        parcela_text = soup.find(string=re.compile(r'\d+x\s*R\$\s*[\d.,]+', re.I))
        if parcela_text:
            parcelas = parcela_text.strip()
        
        # FRETE GRÁTIS (Amazon)
        frete_gratis = bool(soup.find(string=re.compile(r'Frete GRÁTIS|Frete grátis', re.I)))
        
        # FORMATAR PREÇOS
        preco_atual = formatar_preco_br(preco_atual)
        preco_antigo = formatar_preco_br(preco_antigo) if preco_antigo else None
        
        return {
            'site': 'amazon',
            'nome': nome,
            'preco_atual': preco_atual,
            'preco_antigo': preco_antigo,
            'parcelas': parcelas,
            'frete_gratis': frete_gratis
        }
        
    except Exception as e:
        logger.error(f"Erro na Amazon: {e}")
        return None
    finally:
        if driver:
            driver.quit()

def formatar_preco_br(valor):
    """Formata preço para R$ 1.234,56"""
    if not valor or valor == "Preço não encontrado":
        return valor
    
    try:
        # Limpar string
        valor = re.sub(r'[^\d.,]', '', str(valor))
        
        # Converter para formato numérico
        if ',' in valor and '.' in valor:
            valor = valor.replace('.', '').replace(',', '.')
        elif ',' in valor:
            valor = valor.replace(',', '.')
        
        # Formatar
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
    return "✅ Robô de Preços - Amazon e Mercado Livre"

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        
        if 'message' in data:
            chat_id = data['message']['chat']['id']
            texto = data['message'].get('text', '').strip()
            
            logger.info(f"Mensagem: {texto}")
            
            if texto == '/start':
                enviar_telegram(chat_id, 
                    "🤖 *Robô de Preços*\n\n"
                    "Envie links que eu mostro os dados!\n\n"
                    "📌 *Exemplos:*\n"
                    "• https://mercadolivre.com/sec/2TCy2TB\n"
                    "• https://amzn.to/46hzWsh"
                )
                return 'ok', 200
            
            enviar_telegram(chat_id, "🤖 Iniciando robô...")
            
            dados = None
            
            # MERCADO LIVRE
            if 'mercadolivre' in texto or 'mercadolivre.com/sec' in texto:
                dados = extrair_mercadolivre_com_selenium(texto)
            
            # AMAZON
            elif 'amzn.to' in texto or 'amazon' in texto:
                dados = extrair_amazon_com_selenium(texto)
            
            else:
                enviar_telegram(chat_id, "❌ Envie um link do Mercado Livre ou Amazon")
                return 'ok', 200
            
            if dados and dados['nome'] != "Nome não encontrado":
                emoji = "📦" if dados['site'] == 'mercadolivre' else "🛒"
                msg = f"{emoji} *{dados['nome']}*\n\n"
                
                if dados['preco_antigo']:
                    msg += f"~~{dados['preco_antigo']}~~ 💰 *{dados['preco_atual']}*\n"
                else:
                    msg += f"💰 *{dados['preco_atual']}*\n"
                
                if dados['parcelas'] != "Não informado":
                    msg += f"💳 {dados['parcelas']}\n"
                
                if dados['frete_gratis']:
                    msg += "🚚 *Frete Grátis*\n"
                
                enviar_telegram(chat_id, msg)
            else:
                enviar_telegram(chat_id, "❌ Não consegui extrair os dados do produto")
        
        return 'ok', 200
        
    except Exception as e:
        logger.error(f"Erro: {e}")
        return 'ok', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🚀 Robô iniciado na porta {port}")
    app.run(host='0.0.0.0', port=port)