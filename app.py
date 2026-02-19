from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
import telegram
import asyncio
import os
import re
import time
from urllib.parse import urlparse

app = Flask(__name__)

# CONFIGURAÇÕES - COLE SEU TOKEN AQUI
TELEGRAM_TOKEN = "8538755291:AAG2dmZW8KcAN7DnC7pnMIqoSqh490F1YiY"  ← SEU TOKEN
TELEGRAM_CHAT_ID = None  # Será preenchido quando você mandar mensagem

# Headers para simular navegador
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8'
}

# Inicializar bot do Telegram
bot = telegram.Bot(token=TELEGRAM_TOKEN)

def seguir_redirects(url):
    """Segue redirecionamentos e retorna a URL final"""
    try:
        print(f"Seguindo redirecionamentos de: {url}")
        
        # Primeiro tenta com HEAD (mais leve)
        response = requests.head(url, allow_redirects=True, timeout=15, headers=HEADERS)
        url_final = response.url
        print(f"URL final (HEAD): {url_final}")
        return url_final
    except requests.exceptions.RequestException:
        # Se HEAD falhar, tenta com GET
        try:
            response = requests.get(url, allow_redirects=True, timeout=15, headers=HEADERS)
            url_final = response.url
            print(f"URL final (GET): {url_final}")
            return url_final
        except Exception as e:
            print(f"Erro ao seguir redirect: {e}")
            return url  # Retorna a original se tudo falhar

def identificar_site(url):
    """Identifica se é Amazon ou Mercado Livre"""
    url_lower = url.lower()
    
    if 'amazon' in url_lower or 'amzn' in url_lower:
        return 'amazon'
    elif 'mercadolivre' in url_lower or 'mercadolibre' in url_lower or 'mercadolivre.com/sec' in url_lower:
        return 'mercadolivre'
    else:
        return None

def extrair_dados_amazon(url):
    """Extrai nome e preço da Amazon"""
    try:
        print(f"Extraindo dados da Amazon: {url}")
        
        # Headers específicos para Amazon
        amazon_headers = HEADERS.copy()
        amazon_headers.update({
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Referer': 'https://www.google.com/'
        })
        
        response = requests.get(url, headers=amazon_headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Tentar encontrar nome do produto
        nome = None
        
        # Método 1: ID productTitle
        nome_tag = soup.find('span', {'id': 'productTitle'})
        if nome_tag:
            nome = nome_tag.get_text(strip=True)
        
        # Método 2: Classe a-size-large
        if not nome:
            nome_tag = soup.find('h1', {'class': 'a-size-large'})
            if nome_tag:
                nome = nome_tag.get_text(strip=True)
        
        # Método 3: Meta tag title
        if not nome:
            meta_title = soup.find('meta', {'name': 'title'})
            if meta_title:
                nome = meta_title.get('content')
        
        # Tentar encontrar preço
        preco = None
        
        # Método 1: Classe a-price-whole
        preco_tag = soup.find('span', {'class': 'a-price-whole'})
        if preco_tag:
            preco_texto = preco_tag.get_text(strip=True)
            # Verificar se tem centavos
            centavos_tag = soup.find('span', {'class': 'a-price-fraction'})
            if centavos_tag:
                preco = f"{preco_texto}.{centavos_tag.get_text(strip=True)}"
            else:
                preco = preco_texto
        
        # Método 2: Classe a-offscreen
        if not preco:
            preco_tag = soup.find('span', {'class': 'a-offscreen'})
            if preco_tag:
                preco = preco_tag.get_text(strip=True)
        
        # Método 3: Meta tag price
        if not preco:
            meta_price = soup.find('meta', {'property': 'product:price:amount'})
            if meta_price:
                preco = meta_price.get('content')
        
        # Limpar preço (manter só números e vírgula/ponto)
        if preco:
            preco_limpo = re.sub(r'[^\d.,]', '', preco)
            # Trocar vírgula por ponto se necessário
            if ',' in preco_limpo and '.' in preco_limpo:
                preco_limpo = preco_limpo.replace(',', '')
            elif ',' in preco_limpo:
                preco_limpo = preco_limpo.replace(',', '.')
        else:
            preco_limpo = "Não encontrado"
        
        nome_limpo = nome if nome else "Não encontrado"
        
        print(f"Nome encontrado: {nome_limpo}")
        print(f"Preço encontrado: {preco_limpo}")
        
        return nome_limpo, preco_limpo
        
    except Exception as e:
        print(f"Erro ao extrair dados da Amazon: {str(e)}")
        return None, str(e)

def extrair_dados_mercadolivre(url):
    """Extrai nome e preço do Mercado Livre"""
    try:
        print(f"Extraindo dados do Mercado Livre: {url}")
        
        response = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Tentar encontrar nome do produto
        nome = None
        
        # Método 1: Classe ui-pdp-title
        nome_tag = soup.find('h1', {'class': 'ui-pdp-title'})
        if nome_tag:
            nome = nome_tag.get_text(strip=True)
        
        # Método 2: Meta tag title
        if not nome:
            meta_title = soup.find('meta', {'name': 'title'})
            if meta_title:
                nome = meta_title.get('content')
        
        # Método 3: Classe vjs-title
        if not nome:
            nome_tag = soup.find('h1', {'class': 'vjs-title'})
            if nome_tag:
                nome = nome_tag.get_text(strip=True)
        
        # Tentar encontrar preço
        preco = None
        
        # Método 1: Meta tag price
        meta_price = soup.find('meta', {'itemprop': 'price'})
        if meta_price:
            preco = meta_price.get('content')
        
        # Método 2: Classe andes-money-amount__fraction
        if not preco:
            preco_tag = soup.find('span', {'class': 'andes-money-amount__fraction'})
            if preco_tag:
                preco = preco_tag.get_text(strip=True)
                
                # Verificar se tem centavos
                centavos_tag = soup.find('span', {'class': 'andes-money-amount__cents'})
                if centavos_tag:
                    preco = f"{preco}.{centavos_tag.get_text(strip=True)}"
        
        # Método 3: Classe price-tag-fraction
        if not preco:
            preco_tag = soup.find('span', {'class': 'price-tag-fraction'})
            if preco_tag:
                preco = preco_tag.get_text(strip=True)
        
        nome_limpo = nome if nome else "Não encontrado"
        preco_limpo = preco if preco else "Não encontrado"
        
        print(f"Nome encontrado: {nome_limpo}")
        print(f"Preço encontrado: {preco_limpo}")
        
        return nome_limpo, preco_limpo
        
    except Exception as e:
        print(f"Erro ao extrair dados do Mercado Livre: {str(e)}")
        return None, str(e)

async def enviar_telegram(mensagem):
    """Envia mensagem para o Telegram"""
    try:
        global TELEGRAM_CHAT_ID
        if TELEGRAM_CHAT_ID:
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=mensagem)
            return True
        return False
    except Exception as e:
        print(f"Erro ao enviar Telegram: {e}")
        return False

@app.route('/', methods=['GET'])
def home():
    return '''
    <h1>Bot de Preços</h1>
    <p>Envie links pelo Telegram: @seu_bot</p>
    <p>Links suportados: Amazon (amzn.to) e Mercado Livre (mercadolivre.com/sec)</p>
    '''

@app.route('/webhook', methods=['POST'])
def webhook():
    """Recebe mensagens do Telegram"""
    try:
        update = request.get_json()
        
        if 'message' in update:
            chat_id = update['message']['chat']['id']
            text = update['message'].get('text', '')
            
            global TELEGRAM_CHAT_ID
            TELEGRAM_CHAT_ID = chat_id
            
            print(f"Mensagem recebida: {text}")
            print(f"Chat ID: {chat_id}")
            
            # Processar a mensagem
            if text.startswith('/start'):
                asyncio.run(enviar_telegram(
                    "🤖 Bot de Preços Ativo!\n\n"
                    "Envie um link da Amazon ou Mercado Livre que eu te respondo com o nome e preço.\n\n"
                    "📌 Links suportados:\n"
                    "• Amazon: amzn.to/...\n"
                    "• Mercado Livre: mercadolivre.com/sec/..."
                ))
            else:
                # Verificar se parece um link
                if 'http' in text or 'amzn.to' in text or 'mercadolivre.com/sec' in text:
                    
                    # Seguir redirecionamentos do link encurtado
                    url_final = seguir_redirects(text)
                    print(f"URL final: {url_final}")
                    
                    # Identificar o site
                    site = identificar_site(url_final)
                    print(f"Site identificado: {site}")
                    
                    if site == 'amazon':
                        nome, preco = extrair_dados_amazon(url_final)
                        if nome and nome != "Não encontrado":
                            msg = f"📦 *Amazon*\n\n📌 {nome}\n💰 Preço: R$ {preco}"
                        else:
                            msg = f"❌ Não foi possível extrair os dados. Erro: {preco}"
                        asyncio.run(enviar_telegram(msg))
                        
                    elif site == 'mercadolivre':
                        nome, preco = extrair_dados_mercadolivre(url_final)
                        if nome and nome != "Não encontrado":
                            msg = f"📦 *Mercado Livre*\n\n📌 {nome}\n💰 Preço: R$ {preco}"
                        else:
                            msg = f"❌ Não foi possível extrair os dados. Erro: {preco}"
                        asyncio.run(enviar_telegram(msg))
                        
                    else:
                        asyncio.run(enviar_telegram(
                            "❌ Site não suportado.\n\n"
                            "Envie links apenas de:\n"
                            "• Amazon (amzn.to)\n"
                            "• Mercado Livre (mercadolivre.com/sec)"
                        ))
                else:
                    asyncio.run(enviar_telegram(
                        "❌ Envie um link válido da Amazon ou Mercado Livre.\n\n"
                        "Exemplos:\n"
                        "• https://amzn.to/46hzWsh\n"
                        "• https://mercadolivre.com/sec/2cNNseM"
                    ))
        
        return 'ok', 200
        
    except Exception as e:
        print(f"Erro no webhook: {str(e)}")
        return 'erro', 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    print(f"🤖 Bot iniciado na porta {port}!")
    print(f"Token configurado: {TELEGRAM_TOKEN[:10]}...")
    print("Webhook configurado! Aguardando mensagens...")
    app.run(host='0.0.0.0', port=port)