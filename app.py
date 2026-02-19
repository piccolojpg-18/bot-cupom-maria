from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
import telegram
import asyncio
import os
import re

app = Flask(__name__)

# CONFIGURAÇÕES - COLE SEU TOKEN AQUI
TELEGRAM_TOKEN = "8538755291:AAG2dmZW8KcAN7DnC7pnMIqoSqh490F1YiY"  # ← COLE SEU TOKEN ENTRE AS ASPAS
TELEGRAM_CHAT_ID = None  # Será preenchido quando você mandar mensagem

# Headers para simular navegador
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8'
}

# Inicializar bot do Telegram
bot = telegram.Bot(token=TELEGRAM_TOKEN)

def extrair_dados_amazon(url):
    """Extrai nome e preço da Amazon"""
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Nome do produto
        nome = soup.find('span', {'id': 'productTitle'})
        if not nome:
            nome = soup.find('h1', {'class': 'a-size-large'})
        
        # Preço
        preco = soup.find('span', {'class': 'a-price-whole'})
        if not preco:
            preco = soup.find('span', {'class': 'a-offscreen'})
        
        nome_texto = nome.get_text(strip=True) if nome else "Não encontrado"
        preco_texto = preco.get_text(strip=True) if preco else "Não encontrado"
        
        return nome_texto, preco_texto
    except Exception as e:
        return None, str(e)

def extrair_dados_mercadolivre(url):
    """Extrai nome e preço do Mercado Livre"""
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Nome do produto
        nome = soup.find('h1', {'class': 'ui-pdp-title'})
        if not nome:
            nome = soup.find('h1', {'itemprop': 'name'})
        
        # Preço
        preco = soup.find('meta', {'itemprop': 'price'})
        if preco:
            preco_texto = preco.get('content')
        else:
            preco = soup.find('span', {'class': 'andes-money-amount__fraction'})
            preco_texto = preco.get_text(strip=True) if preco else "Não encontrado"
        
        nome_texto = nome.get_text(strip=True) if nome else "Não encontrado"
        
        return nome_texto, preco_texto
    except Exception as e:
        return None, str(e)

def identificar_site(url):
    """Identifica se é Amazon ou Mercado Livre"""
    if 'amazon' in url.lower():
        return 'amazon'
    elif 'mercadolivre' in url.lower() or 'mercadolibre' in url.lower():
        return 'mercadolivre'
    else:
        return None

async def enviar_telegram(mensagem):
    """Envia mensagem para o Telegram"""
    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=mensagem)
        return True
    except:
        return False

@app.route('/', methods=['GET'])
def home():
    return '''
    <h1>Bot de Preços</h1>
    <p>Envie links pelo Telegram: @seu_bot</p>
    '''

@app.route('/webhook', methods=['POST'])
def webhook():
    """Recebe mensagens do Telegram"""
    update = request.get_json()
    
    if 'message' in update:
        chat_id = update['message']['chat']['id']
        text = update['message'].get('text', '')
        
        global TELEGRAM_CHAT_ID
        TELEGRAM_CHAT_ID = chat_id
        
        # Processar a mensagem
        if text.startswith('/start'):
            asyncio.run(enviar_telegram(
                "🤖 Bot de Preços Ativo!\n\n"
                "Envie um link da Amazon ou Mercado Livre que eu te respondo com o nome e preço."
            ))
        else:
            # Verificar se é uma URL
            site = identificar_site(text)
            
            if site == 'amazon':
                nome, preco = extrair_dados_amazon(text)
                if nome:
                    msg = f"📦 *Amazon*\n\n📌 {nome}\n💰 Preço: R$ {preco}"
                else:
                    msg = f"❌ Erro: {preco}"
                asyncio.run(enviar_telegram(msg))
                
            elif site == 'mercadolivre':
                nome, preco = extrair_dados_mercadolivre(text)
                if nome:
                    msg = f"📦 *Mercado Livre*\n\n📌 {nome}\n💰 Preço: R$ {preco}"
                else:
                    msg = f"❌ Erro: {preco}"
                asyncio.run(enviar_telegram(msg))
                
            else:
                asyncio.run(enviar_telegram("❌ Envie um link válido da Amazon ou Mercado Livre"))
    
    return 'ok', 200

if __name__ == '__main__':
    print("🤖 Bot iniciado! Configure o webhook no Telegram:")
    print(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook?url=SEU_URL_AQUI/webhook")
    app.run(host='0.0.0.0', port=10000)