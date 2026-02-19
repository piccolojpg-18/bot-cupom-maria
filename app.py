from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
import telegram
import asyncio
import os
import re
import logging
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)

# CONFIGURAÇÕES
TELEGRAM_TOKEN = "8538755291:AAG2dmZW8KcAN7DnC7pnMIqoSqh490F1YiY"
TELEGRAM_CHAT_ID = None

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Headers otimizados
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1'
}

# Cache simples para URLs
url_cache = {}

# Pool de threads
executor = ThreadPoolExecutor(max_workers=4)

# Inicializar bot
bot = telegram.Bot(token=TELEGRAM_TOKEN)

def seguir_redirects_rapido(url):
    """Segue redirecionamentos de forma otimizada"""
    if url in url_cache:
        logger.info(f"Cache hit: {url}")
        return url_cache[url]
    
    try:
        session = requests.Session()
        response = session.head(url, allow_redirects=True, timeout=8, headers=HEADERS)
        url_final = response.url
        url_cache[url] = url_final
        logger.info(f"Redirect: {url} -> {url_final}")
        return url_final
    except:
        try:
            session = requests.Session()
            response = session.get(url, allow_redirects=True, timeout=8, headers=HEADERS, stream=True)
            url_final = response.url
            response.close()
            url_cache[url] = url_final
            logger.info(f"Redirect (GET): {url} -> {url_final}")
            return url_final
        except Exception as e:
            logger.error(f"Erro redirect: {e}")
            return url

def identificar_site_rapido(url):
    """Identifica site de forma otimizada"""
    url_lower = url.lower()
    
    if 'amazon' in url_lower or 'amzn' in url_lower:
        return 'amazon'
    elif any(x in url_lower for x in ['mercadolivre', 'mercadolibre', 'mercadolivre.com/sec']):
        return 'mercadolivre'
    return None

def extrair_dados_amazon_rapido(url):
    """Extrai dados da Amazon de forma otimizada"""
    try:
        logger.info(f"Extraindo Amazon: {url}")
        
        session = requests.Session()
        response = session.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Nome do produto
        nome = None
        nome_selectors = [
            ('span', {'id': 'productTitle'}),
            ('h1', {'class': 'a-size-large'}),
            ('meta', {'name': 'title'})
        ]
        
        for tag, attrs in nome_selectors:
            element = soup.find(tag, attrs)
            if element:
                if tag == 'meta':
                    nome = element.get('content')
                else:
                    nome = element.get_text(strip=True)
                break
        
        # Preço
        preco = None
        preco_selectors = [
            ('span', {'class': 'a-price-whole'}),
            ('span', {'class': 'a-offscreen'}),
            ('meta', {'property': 'product:price:amount'})
        ]
        
        for tag, attrs in preco_selectors:
            element = soup.find(tag, attrs)
            if element:
                if tag == 'meta':
                    preco = element.get('content')
                else:
                    preco_text = element.get_text(strip=True)
                    preco = re.sub(r'[^\d.,]', '', preco_text)
                    if ',' in preco and '.' not in preco:
                        preco = preco.replace(',', '.')
                break
        
        nome = nome if nome else "Não encontrado"
        preco = preco if preco else "Não encontrado"
        
        logger.info(f"Amazon OK: {nome[:50]}... R$ {preco}")
        return nome, preco
        
    except Exception as e:
        logger.error(f"Erro Amazon: {e}")
        return None, str(e)

def extrair_dados_ml_rapido(url):
    """Extrai dados do Mercado Livre de forma otimizada - VERSÃO CORRIGIDA"""
    try:
        logger.info(f"Extraindo ML: {url}")
        
        session = requests.Session()
        response = session.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # ===== NOME DO PRODUTO =====
        nome = None
        
        # Método 1: Título principal do produto (mais comum)
        titulo = soup.find('h1', class_='ui-pdp-title')
        if titulo:
            nome = titulo.get_text(strip=True)
            logger.info(f"Título encontrado: {nome[:50]}")
        
        # Método 2: Classe alternativa
        if not nome:
            titulo = soup.find('h1', class_='vjs-title')
            if titulo:
                nome = titulo.get_text(strip=True)
        
        # Método 3: Meta tag OG
        if not nome:
            meta_og = soup.find('meta', property='og:title')
            if meta_og:
                nome = meta_og.get('content')
        
        # ===== PREÇO DO PRODUTO =====
        preco = None
        
        # Método 1: Preço inteiro (parte principal)
        preco_inteiro = soup.find('span', class_='andes-money-amount__fraction')
        if preco_inteiro:
            preco = preco_inteiro.get_text(strip=True)
            
            # Verificar centavos
            centavos = soup.find('span', class_='andes-money-amount__cents')
            if centavos and centavos.get_text(strip=True) != '00':
                preco = f"{preco}.{centavos.get_text(strip=True)}"
            
            logger.info(f"Preço encontrado: {preco}")
        
        # Método 2: Meta tag price
        if not preco:
            meta_price = soup.find('meta', {'itemprop': 'price'})
            if meta_price:
                preco = meta_price.get('content')
        
        # Método 3: Outra classe comum de preço
        if not preco:
            price_tag = soup.find('span', class_='price-tag-fraction')
            if price_tag:
                preco = price_tag.get_text(strip=True)
        
        # Método 4: Procurar por qualquer elemento com preço
        if not preco:
            possiveis_precos = soup.find_all(['span', 'div', 'meta'], 
                                           class_=re.compile(r'price|preco|valor|amount', re.I))
            for elem in possiveis_precos:
                texto = elem.get_text(strip=True)
                if 'R$' in texto or re.search(r'\d+[,.]\d{2}', texto):
                    preco = re.search(r'[\d,.]+', texto).group()
                    break
        
        # ===== FORMATAÇÃO FINAL =====
        if not nome:
            nome = "Nome não encontrado"
            logger.warning("Nome não encontrado")
        
        if not preco:
            preco = "Preço não encontrado"
            logger.warning("Preço não encontrado")
        else:
            # Limpar e formatar preço
            preco = re.sub(r'[^\d.,]', '', str(preco))
            # Garantir formato brasileiro
            if '.' in preco and ',' in preco:
                preco = preco.replace(',', '')
            elif ',' in preco and '.' not in preco:
                preco = preco.replace(',', '.')
            
            # Adicionar ,00 se necessário
            if '.' in preco:
                reais, centavos = preco.split('.')
                if len(centavos) == 1:
                    preco = f"{reais}.{centavos}0"
                elif len(centavos) > 2:
                    preco = f"{reais}.{centavos[:2]}"
            elif preco.isdigit():
                preco = f"{preco}.00"
        
        logger.info(f"ML OK: {nome[:30]}... R$ {preco}")
        return nome, preco
        
    except Exception as e:
        logger.error(f"Erro ML: {e}")
        return None, str(e)

async def enviar_telegram_rapido(mensagem):
    """Envia mensagem de forma assíncrona"""
    try:
        if TELEGRAM_CHAT_ID:
            await bot.send_message(
                chat_id=TELEGRAM_CHAT_ID, 
                text=mensagem,
                parse_mode='Markdown'
            )
            return True
    except Exception as e:
        logger.error(f"Erro Telegram: {e}")
    return False

@app.route('/', methods=['GET'])
def home():
    return '''
    <h1>Bot de Preços Rápido ⚡</h1>
    <p>Envie links pelo Telegram: @seu_bot</p>
    <p>Links suportados: Amazon (amzn.to) e Mercado Livre (mercadolivre.com/sec)</p>
    '''

@app.route('/webhook', methods=['POST'])
def webhook():
    """Webhook otimizado"""
    try:
        update = request.get_json()
        
        if 'message' in update:
            chat_id = update['message']['chat']['id']
            text = update['message'].get('text', '')
            
            global TELEGRAM_CHAT_ID
            TELEGRAM_CHAT_ID = chat_id
            
            logger.info(f"Mensagem: {text[:50]}...")
            
            if text.startswith('/start'):
                asyncio.run(enviar_telegram_rapido(
                    "🤖 *Bot de Preços Rápido* ⚡\n\n"
                    "Envie um link que eu respondo em segundos!\n\n"
                    "📌 *Exemplos:*\n"
                    "• https://amzn.to/46hzWsh\n"
                    "• https://mercadolivre.com/sec/267Mk5q"
                ))
            else:
                # Verificar se é link
                if any(x in text for x in ['http', 'amzn.to', 'mercadolivre.com/sec']):
                    
                    # Seguir redirect rápido
                    url_final = seguir_redirects_rapido(text)
                    site = identificar_site_rapido(url_final)
                    
                    # Enviar "processando" imediatamente
                    asyncio.run(enviar_telegram_rapido("⏳ Processando..."))
                    
                    if site == 'amazon':
                        future = executor.submit(extrair_dados_amazon_rapido, url_final)
                        nome, preco = future.result(timeout=15)
                        
                        if nome and nome != "Não encontrado" and nome != "Nome não encontrado":
                            msg = f"📦 *Amazon*\n\n📌 {nome}\n💰 *Preço:* R$ {preco}"
                        else:
                            msg = f"❌ Erro ao extrair dados: {preco}"
                        
                    elif site == 'mercadolivre':
                        future = executor.submit(extrair_dados_ml_rapido, url_final)
                        nome, preco = future.result(timeout=15)
                        
                        if nome and nome != "Não encontrado" and nome != "Nome não encontrado":
                            msg = f"📦 *Mercado Livre*\n\n📌 {nome}\n💰 *Preço:* R$ {preco}"
                        else:
                            msg = f"❌ Erro ao extrair dados: {preco}"
                    else:
                        msg = "❌ Link não suportado. Envie apenas Amazon ou Mercado Livre."
                    
                    # Enviar resposta
                    asyncio.run(enviar_telegram_rapido(msg))
                    
                else:
                    asyncio.run(enviar_telegram_rapido(
                        "❌ Envie um link válido!\n\n"
                        "Exemplos:\n"
                        "• https://amzn.to/46hzWsh\n"
                        "• https://mercadolivre.com/sec/267Mk5q"
                    ))
        
        return 'ok', 200
        
    except Exception as e:
        logger.error(f"Erro webhook: {e}")
        return 'erro', 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🚀 Bot rápido iniciado na porta {port}")
    app.run(host='0.0.0.0', port=port, threaded=True)