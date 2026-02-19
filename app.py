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
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # Caminho do Chrome no Render (definido no render-start.sh)
    chrome_path = "/opt/render/project/.chrome/opt/google/chrome/google-chrome"
    if os.path.exists(chrome_path):
        chrome_options.binary_location = chrome_path
        logger.info(f"Usando Chrome em: {chrome_path}")
    
    try:
        # Tentar primeiro com Chrome instalado
        driver = webdriver.Chrome(options=chrome_options)
        logger.info("Chrome iniciado com sucesso")
        return driver
    except Exception as e:
        logger.error(f"Erro ao iniciar Chrome: {e}")
        # Fallback para webdriver-manager
        try:
            logger.info("Tentando fallback com webdriver-manager...")
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            logger.info("Chrome iniciado com webdriver-manager")
            return driver
        except Exception as e2:
            logger.error(f"Erro no fallback: {e2}")
            return None

def extrair_com_selenium(url_afiliado):
    """
    Usa Selenium para:
    1. Abrir a página de perfil
    2. Clicar no botão "Ir para produto" do primeiro produto
    3. Extrair dados da página do produto real
    """
    driver = None
    try:
        logger.info(f"Iniciando Selenium para: {url_afiliado}")
        driver = criar_driver()
        
        if not driver:
            return None
        
        # PASSO 1: Abrir página de perfil
        logger.info("Abrindo página de perfil...")
        driver.get(url_afiliado)
        time.sleep(5)  # Aguardar carregamento completo
        
        # PASSO 2: Procurar e clicar no botão/link do primeiro produto
        logger.info("Procurando link do primeiro produto...")
        
        # Método 1: Procurar por link com '/p/' (página de produto)
        try:
            links_produto = driver.find_elements(By.XPATH, "//a[contains(@href, '/p/')]")
            if links_produto:
                link = links_produto[0]
                href = link.get_attribute('href')
                logger.info(f"Link de produto encontrado: {href}")
                driver.execute_script("arguments[0].click();", link)
                logger.info("Clique no link realizado!")
            else:
                # Método 2: Procurar por texto "Ir para produto"
                botoes = driver.find_elements(By.XPATH, "//*[contains(text(), 'Ir para produto')]")
                if botoes:
                    logger.info(f"Botão 'Ir para produto' encontrado")
                    driver.execute_script("arguments[0].click();", botoes[0])
                    logger.info("Clique no botão realizado!")
                else:
                    # Método 3: Qualquer link que pareça de produto
                    todos_links = driver.find_elements(By.TAG_NAME, "a")
                    for link in todos_links[:20]:  # Limitar para não travar
                        href = link.get_attribute('href') or ""
                        if 'MLB' in href or '/p/' in href:
                            logger.info(f"Link potencial encontrado: {href[:100]}")
                            driver.execute_script("arguments[0].click();", link)
                            logger.info("Clique realizado!")
                            break
                    else:
                        logger.warning("Nenhum link de produto encontrado")
        except Exception as e:
            logger.error(f"Erro ao clicar: {e}")
        
        # PASSO 3: Aguardar página do produto carregar
        time.sleep(5)
        
        # PASSO 4: Extrair dados da página atual
        page_source = driver.page_source
        url_final = driver.current_url
        logger.info(f"URL final: {url_final}")
        
        soup = BeautifulSoup(page_source, 'html.parser')
        
        # NOME DO PRODUTO
        nome = "Nome não encontrado"
        
        # Título principal
        titulo = soup.find('h1', class_='ui-pdp-title')
        if titulo:
            nome = titulo.get_text(strip=True)
        else:
            # Meta tag
            meta = soup.find('meta', {'property': 'og:title'})
            if meta:
                nome = meta.get('content', '')
        
        # PREÇO ATUAL
        preco_atual = "Preço não encontrado"
        
        # Meta tag price
        meta_price = soup.find('meta', {'itemprop': 'price'})
        if meta_price:
            preco_atual = meta_price.get('content', '')
        else:
            # Span de preço
            preco_span = soup.find('span', class_='andes-money-amount__fraction')
            if preco_span:
                preco_atual = preco_span.get_text(strip=True)
                # Verificar centavos
                centavos = soup.find('span', class_='andes-money-amount__cents')
                if centavos:
                    preco_atual = f"{preco_atual}.{centavos.get_text(strip=True)}"
        
        # PREÇO ANTIGO
        preco_antigo = None
        antigo = soup.find('span', class_='andes-money-amount--previous')
        if antigo:
            valor = antigo.find('span', class_='andes-money-amount__fraction')
            if valor:
                preco_antigo = valor.get_text(strip=True)
        
        # PARCELAMENTO
        parcelas = "Não informado"
        parcela_text = soup.find('span', class_='ui-pdp-installments')
        if parcela_text:
            parcelas = parcela_text.get_text(strip=True)
        else:
            # Procurar por texto com parcelamento
            texto_parcela = soup.find(string=re.compile(r'\d+x\s*R\$\s*[\d.,]+', re.I))
            if texto_parcela:
                parcelas = texto_parcela.strip()
        
        # FRETE GRÁTIS
        frete_gratis = False
        if soup.find(string=re.compile(r'Frete grátis|Frete GRÁTIS', re.I)):
            frete_gratis = True
        
        # FORMATAR PREÇOS
        if preco_atual and preco_atual != "Preço não encontrado":
            if isinstance(preco_atual, str):
                # Remover pontos de milhar e converter vírgula
                preco_atual = re.sub(r'[^\d.,]', '', preco_atual)
                if ',' in preco_atual and '.' in preco_atual:
                    preco_atual = preco_atual.replace('.', '').replace(',', '.')
                elif ',' in preco_atual:
                    preco_atual = preco_atual.replace(',', '.')
                
                # Formatar para Real
                if '.' in preco_atual:
                    reais, centavos = preco_atual.split('.')
                    if len(reais) > 3:
                        reais = re.sub(r'(\d)(?=(\d{3})+(?!\d))', r'\1.', reais)
                    preco_atual = f"R$ {reais},{centavos[:2]}"
                else:
                    preco_atual = f"R$ {preco_atual},00"
        
        if preco_antigo:
            preco_antigo = f"R$ {preco_antigo},00"
        
        logger.info(f"Dados extraídos: {nome[:50]}... - {preco_atual}")
        
        return {
            'nome': nome,
            'preco_atual': preco_atual,
            'preco_antigo': preco_antigo,
            'parcelas': parcelas,
            'frete_gratis': frete_gratis,
            'url': url_final
        }
        
    except Exception as e:
        logger.error(f"Erro no Selenium: {e}")
        return None
    finally:
        if driver:
            driver.quit()
            logger.info("Driver fechado")

@app.route('/', methods=['GET'])
def home():
    return "✅ Robô de Preços Funcionando!"

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        
        if 'message' in data:
            chat_id = data['message']['chat']['id']
            texto = data['message'].get('text', '').strip()
            
            logger.info(f"Mensagem recebida: {texto}")
            
            if texto == '/start':
                enviar_telegram(chat_id, 
                    "🤖 *Robô de Preços*\n\n"
                    "Envie um link do Mercado Livre que eu:\n"
                    "1️⃣ Abro a página\n"
                    "2️⃣ Clico no primeiro produto\n"
                    "3️⃣ Pego todos os dados\n\n"
                    "📌 *Exemplo:*\n"
                    "https://mercadolivre.com/sec/2TCy2TB"
                )
                return 'ok', 200
            
            if 'mercadolivre' in texto:
                enviar_telegram(chat_id, "🤖 Iniciando robô...")
                
                dados = extrair_com_selenium(texto)
                
                if dados and dados['nome'] != "Nome não encontrado":
                    msg = f"📦 *{dados['nome']}*\n\n"
                    
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
                    enviar_telegram(chat_id, 
                        "❌ Não consegui extrair os dados.\n\n"
                        "Pode ser que:\n"
                        "• A página demorou muito para carregar\n"
                        "• O layout mudou\n"
                        "• O link é inválido"
                    )
            else:
                enviar_telegram(chat_id, "❌ Envie um link do Mercado Livre")
        
        return 'ok', 200
        
    except Exception as e:
        logger.error(f"Erro no webhook: {e}")
        return 'ok', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🚀 Robô iniciado na porta {port}")
    app.run(host='0.0.0.0', port=port)