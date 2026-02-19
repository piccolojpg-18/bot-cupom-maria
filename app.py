from flask import Flask, request
import requests
from bs4 import BeautifulSoup
import os
import re
import logging
from datetime import datetime

app = Flask(__name__)

# CONFIGURAÇÕES
TELEGRAM_TOKEN = "8538755291:AAG2dmZW8KcAN7DnC7pnMIqoSqh490F1YiY"
ML_CLIENT_ID = os.environ.get('ML_CLIENT_ID')
ML_CLIENT_SECRET = os.environ.get('ML_CLIENT_SECRET')

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Headers para requisições
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

# Cache simples
token_cache = {'access_token': None, 'expires_at': None}

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
        logger.error(f"Erro ao enviar Telegram: {e}")
        return False

def obter_token_ml():
    """Obtém token da API do Mercado Livre"""
    if token_cache['access_token'] and token_cache['expires_at']:
        if datetime.now().timestamp() < token_cache['expires_at']:
            return token_cache['access_token']
    
    url = "https://api.mercadolibre.com/oauth/token"
    payload = {
        'grant_type': 'client_credentials',
        'client_id': ML_CLIENT_ID,
        'client_secret': ML_CLIENT_SECRET
    }
    
    try:
        response = requests.post(url, data=payload)
        data = response.json()
        token_cache['access_token'] = data['access_token']
        token_cache['expires_at'] = datetime.now().timestamp() + data['expires_in']
        return data['access_token']
    except:
        return None

def extrair_id_produto_ml(url):
    """Extrai ID do produto da URL"""
    match = re.search(r'(ML[B|C]\d+)', url)
    if match:
        return match.group(1)
    return None

def consultar_api_ml(item_id):
    """Consulta produto na API do ML"""
    token = obter_token_ml()
    if not token:
        return None
    
    url = f"https://api.mercadolibre.com/items/{item_id}"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.get(url, headers=headers)
        data = response.json()
        return data
    except:
        return None

def formatar_preco(valor):
    """Formata preço para R$ 1.234,56"""
    try:
        return f"R$ {valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    except:
        return f"R$ {valor}"

def extrair_dados_amazon(url):
    """Extrai dados da Amazon"""
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        nome = soup.find('span', {'id': 'productTitle'})
        nome = nome.get_text(strip=True) if nome else "Nome não encontrado"
        
        preco = soup.find('span', {'class': 'a-price-whole'})
        preco = preco.get_text(strip=True) if preco else "Preço não encontrado"
        
        return nome, preco
    except:
        return "Erro", "Erro na Amazon"

def seguir_redirect(url):
    """Segue redirecionamentos"""
    try:
        response = requests.head(url, allow_redirects=True, timeout=5)
        return response.url
    except:
        return url

@app.route('/', methods=['GET'])
def home():
    return "✅ Bot funcionando!"

@app.route('/webhook', methods=['POST'])
def webhook():
    """Recebe mensagens do Telegram"""
    try:
        data = request.get_json()
        
        if 'message' in data:
            chat_id = data['message']['chat']['id']
            texto = data['message'].get('text', '').strip()
            
            logger.info(f"Mensagem: {texto}")
            
            # Resposta imediata (já funcionou!)
            enviar_telegram(chat_id, "⏳ Processando...")
            
            # Verificar se é link da Amazon
            if 'amzn.to' in texto or 'amazon' in texto:
                url_final = seguir_redirect(texto)
                nome, preco = extrair_dados_amazon(url_final)
                msg = f"📦 *Amazon*\n\n{nome}\n💰 {preco}"
                enviar_telegram(chat_id, msg)
            
            # Verificar se é link do Mercado Livre
            elif 'mercadolivre' in texto or 'mercadolibre' in texto:
                url_final = seguir_redirect(texto)
                produto_id = extrair_id_produto_ml(url_final)
                
                if produto_id:
                    dados = consultar_api_ml(produto_id)
                    if dados:
                        nome = dados.get('title', 'N/A')
                        preco = formatar_preco(dados.get('price', 0))
                        msg = f"📦 *Mercado Livre*\n\n{nome}\n💰 {preco}"
                    else:
                        msg = "❌ Erro ao consultar API"
                else:
                    msg = "❌ ID do produto não encontrado"
                
                enviar_telegram(chat_id, msg)
            
            # Comando /start
            elif texto == '/start':
                enviar_telegram(chat_id, "🤖 Bot de Preços\n\nEnvie links da Amazon ou Mercado Livre!")
            
            # Qualquer outra coisa
            else:
                enviar_telegram(chat_id, "❌ Envie um link da Amazon ou Mercado Livre")
        
        return 'ok', 200
        
    except Exception as e:
        logger.error(f"Erro: {e}")
        return 'ok', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)