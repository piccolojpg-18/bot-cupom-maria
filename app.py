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

def formatar_preco_real(valor_raw):
    """Converte qualquer formato de preço para Real brasileiro (R$ 1.234,56)"""
    if not valor_raw or valor_raw == "Preço não encontrado":
        return "Preço não encontrado"
    
    try:
        valor_raw = str(valor_raw).strip()
        logger.info(f"Formatando preço raw: {valor_raw}")
        
        # Caso 1: Formato 1.234,56 (já em formato brasileiro)
        if '.' in valor_raw and ',' in valor_raw:
            # Já está no formato correto, só garantir 2 casas decimais
            partes = valor_raw.split(',')
            if len(partes) == 2:
                reais = partes[0].replace('.', '')
                centavos = partes[1].ljust(2, '0')[:2]
                # Adicionar pontos de milhar de volta
                if len(reais) > 3:
                    reais = re.sub(r'(\d)(?=(\d{3})+(?!\d))', r'\1.', reais)
                preco = f"R$ {reais},{centavos}"
                return preco
        
        # Caso 2: Formato 1234.56 (padrão americano)
        elif '.' in valor_raw and not ',' in valor_raw:
            partes = valor_raw.split('.')
            if len(partes) == 2:
                reais = partes[0]
                centavos = partes[1].ljust(2, '0')[:2]
                # Adicionar pontos de milhar
                if len(reais) > 3:
                    reais = re.sub(r'(\d)(?=(\d{3})+(?!\d))', r'\1.', reais)
                return f"R$ {reais},{centavos}"
        
        # Caso 3: Formato 1234,56
        elif ',' in valor_raw and not '.' in valor_raw:
            partes = valor_raw.split(',')
            if len(partes) == 2:
                reais = partes[0]
                centavos = partes[1].ljust(2, '0')[:2]
                # Adicionar pontos de milhar
                if len(reais) > 3:
                    reais = re.sub(r'(\d)(?=(\d{3})+(?!\d))', r'\1.', reais)
                return f"R$ {reais},{centavos}"
        
        # Caso 4: Apenas números (ex: 123456)
        elif valor_raw.replace('.', '').isdigit():
            # Remove pontos existentes
            numeros = valor_raw.replace('.', '')
            if len(numeros) > 2:
                reais = numeros[:-2]
                centavos = numeros[-2:]
                # Adicionar pontos de milhar
                if len(reais) > 3:
                    reais = re.sub(r'(\d)(?=(\d{3})+(?!\d))', r'\1.', reais)
                return f"R$ {reais},{centavos}"
            else:
                return f"R$ 0,{numeros.zfill(2)}"
        
        # Caso 5: Formato com R$ na frente
        elif 'R$' in valor_raw:
            # Extrair apenas números
            numeros = re.findall(r'[\d.,]+', valor_raw)
            if numeros:
                return formatar_preco_real(numeros[0])
        
        return f"R$ {valor_raw}"
        
    except Exception as e:
        logger.error(f"Erro ao formatar preço: {e}")
        return f"R$ {valor_raw}"

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
        preco_raw = None
        preco_selectors = [
            ('span', {'class': 'a-price-whole'}),
            ('span', {'class': 'a-offscreen'}),
            ('meta', {'property': 'product:price:amount'})
        ]
        
        for tag, attrs in preco_selectors:
            element = soup.find(tag, attrs)
            if element:
                if tag == 'meta':
                    preco_raw = element.get('content')
                else:
                    preco_text = element.get_text(strip=True)
                    preco_raw = re.sub(r'[^\d.,]', '', preco_text)
                break
        
        nome = nome if nome else "Nome não encontrado"
        preco = formatar_preco_real(preco_raw) if preco_raw else "Preço não encontrado"
        
        logger.info(f"Amazon OK: {nome[:50]}... {preco}")
        return nome, preco
        
    except Exception as e:
        logger.error(f"Erro Amazon: {e}")
        return None, str(e)

def extrair_dados_ml_rapido(url):
    """Extrai dados do Mercado Livre - VERSÃO COM FORMATAÇÃO EM REAL"""
    try:
        logger.info(f"Extraindo ML: {url}")
        
        session = requests.Session()
        response = session.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # ===== NOME DO PRODUTO =====
        nome = None
        
        # Título principal
        titulo = soup.find('h1', class_='ui-pdp-title')
        if titulo:
            nome = titulo.get_text(strip=True)
            logger.info(f"Título encontrado: {nome[:50]}")
        
        if not nome:
            titulo = soup.find('h1', class_='vjs-title')
            if titulo:
                nome = titulo.get_text(strip=True)
        
        if not nome:
            meta_og = soup.find('meta', property='og:title')
            if meta_og:
                nome = meta_og.get('content')
        
        # ===== PREÇO DO PRODUTO =====
        preco_raw = None
        
        # MÉTODO 1: Meta tag price
        meta_price = soup.find('meta', {'itemprop': 'price'})
        if meta_price and meta_price.get('content'):
            preco_raw = meta_price.get('content')
            logger.info(f"Preço encontrado (meta): {preco_raw}")
        
        # MÉTODO 2: Classe andes-money-amount
        if not preco_raw:
            andes_price = soup.find('span', class_='andes-money-amount__fraction')
            if andes_price:
                preco_raw = andes_price.get_text(strip=True)
                # Verificar centavos
                centavos = soup.find('span', class_='andes-money-amount__cents')
                if centavos and centavos.get_text(strip=True) != '00':
                    preco_raw = f"{preco_raw}.{centavos.get_text(strip=True)}"
                logger.info(f"Preço encontrado (andes): {preco_raw}")
        
        # MÉTODO 3: Procurar por R$
        if not preco_raw:
            for elemento in soup.find_all(['span', 'div', 'p']):
                texto = elemento.get_text()
                if 'R$' in texto:
                    numeros = re.findall(r'R\$\s*([\d.,]+)', texto)
                    if numeros:
                        preco_raw = numeros[0]
                        logger.info(f"Preço encontrado (R$): {preco_raw}")
                        break
        
        # MÉTODO 4: Classe price-tag
        if not preco_raw:
            price_tag = soup.find('span', class_='price-tag-fraction')
            if price_tag:
                preco_raw = price_tag.get_text(strip=True)
                logger.info(f"Preço encontrado (price-tag): {preco_raw}")
        
        # ===== RESULTADO FINAL =====
        if not nome:
            nome = "Nome não encontrado"
        
        preco = formatar_preco_real(preco_raw)
        
        logger.info(f"Resultado final ML: {nome[:30]}... {preco}")
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
            
            logger.info(f"Mensagem recebida: {text[:50]}...")
            
            if text.startswith('/start'):
                asyncio.run(enviar_telegram_rapido(
                    "🤖 *Bot de Preços Rápido* ⚡\n\n"
                    "Envie um link que eu respondo em segundos!\n\n"
                    "📌 *Exemplos:*\n"
                    "• https://amzn.to/46hzWsh\n"
                    "• https://mercadolivre.com/sec/267Mk5q\n\n"
                    "💰 *Preços formatados em Real brasileiro* (R$ 1.234,56)"
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
                        
                        if nome and nome != "Nome não encontrado":
                            msg = f"📦 *Amazon*\n\n📌 {nome}\n💰 *Preço:* {preco}"
                        else:
                            msg = f"❌ Erro ao extrair dados: {preco}"
                        
                    elif site == 'mercadolivre':
                        future = executor.submit(extrair_dados_ml_rapido, url_final)
                        nome, preco = future.result(timeout=15)
                        
                        if nome and nome != "Nome não encontrado":
                            msg = f"📦 *Mercado Livre*\n\n📌 {nome}\n💰 *Preço:* {preco}"
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
    logger.info("💰 Formatação de preços em Real brasileiro (R$ 1.234,56)")
    app.run(host='0.0.0.0', port=port, threaded=True)