from flask import Flask, request
import requests
from bs4 import BeautifulSoup
import os
import re
import logging

app = Flask(__name__)

# CONFIGURAÇÕES - SEUS DADOS
TELEGRAM_TOKEN = "8538755291:AAG2dmZW8KcAN7DnC7pnMIqoSqh490F1YiY"
ML_CLIENT_ID = os.environ.get('ML_CLIENT_ID')
ML_CLIENT_SECRET = os.environ.get('ML_CLIENT_SECRET')

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def enviar_telegram(chat_id, texto):
    """Envia mensagem para o Telegram (versão simples, sem asyncio)"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': texto,
        'parse_mode': 'Markdown'
    }
    try:
        requests.post(url, json=payload, timeout=5)
        return True
    except:
        return False

@app.route('/', methods=['GET'])
def home():
    return "Bot de Preços - Versão Simplificada 🚀"

@app.route('/webhook', methods=['POST'])
def webhook():
    """Versão simplificada sem asyncio"""
    try:
        data = request.get_json()
        
        if 'message' in data:
            chat_id = data['message']['chat']['id']
            texto = data['message'].get('text', '')
            
            logger.info(f"Mensagem de {chat_id}: {texto}")
            
            # Resposta imediata para teste
            enviar_telegram(chat_id, f"✅ Mensagem recebida: {texto[:50]}...")
            
        return 'ok', 200
    except Exception as e:
        logger.error(f"Erro: {e}")
        return 'ok', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)