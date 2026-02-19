from flask import Flask, request
import requests
from bs4 import BeautifulSoup
import os
import re
import logging
from datetime import datetime
import urllib.parse

app = Flask(__name__)

# CONFIGURAÇÕES
TELEGRAM_TOKEN = "8538755291:AAG2dmZW8KcAN7DnC7pnMIqoSqh490F1YiY"
ML_CLIENT_ID = os.environ.get('ML_CLIENT_ID')
ML_CLIENT_SECRET = os.environ.get('ML_CLIENT_SECRET')

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Headers
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

# Cache para token
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
        logger.error(f"Erro Telegram: {e}")
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
    except Exception as e:
        logger.error(f"Erro token: {e}")
        return None

def extrair_nome_da_pagina(url_encurtada):
    """
    Extrai o nome do produto da página de perfil do afiliado
    """
    try:
        logger.info(f"Acessando página: {url_encurtada}")
        response = requests.get(url_encurtada, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Procurar pelo título do produto (geralmente é o primeiro texto grande)
        possiveis_titulos = []
        
        # H1
        for h1 in soup.find_all('h1'):
            texto = h1.get_text(strip=True)
            if texto and len(texto) > 15:
                possiveis_titulos.append(texto)
        
        # H2
        for h2 in soup.find_all('h2'):
            texto = h2.get_text(strip=True)
            if texto and len(texto) > 15:
                possiveis_titulos.append(texto)
        
        # Meta tags
        meta_title = soup.find('meta', {'property': 'og:title'})
        if meta_title and meta_title.get('content'):
            possiveis_titulos.append(meta_title.get('content'))
        
        if possiveis_titulos:
            nome = possiveis_titulos[0]
            logger.info(f"Nome extraído: {nome[:100]}")
            return nome
        
        logger.warning("Nenhum nome encontrado")
        return None
        
    except Exception as e:
        logger.error(f"Erro ao extrair nome: {e}")
        return None

def buscar_produto_ml(nome_produto, token):
    """
    Busca o produto pelo nome na API do Mercado Livre
    """
    # Limpar e codificar o nome para URL
    nome_limpo = re.sub(r'[^\w\s]', '', nome_produto)
    nome_codificado = urllib.parse.quote(nome_limpo)
    
    url = f"https://api.mercadolibre.com/sites/MLB/search?q={nome_codificado}&limit=5"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        logger.info(f"Buscando na API: {nome_limpo[:50]}")
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        
        if data.get('results') and len(data['results']) > 0:
            # Pegar o primeiro resultado
            produto = data['results'][0]
            logger.info(f"Produto encontrado: {produto['title'][:50]}")
            return produto
        else:
            logger.warning("Nenhum resultado na busca")
            return None
            
    except Exception as e:
        logger.error(f"Erro na busca: {e}")
        return None

def formatar_preco(valor):
    """Formata preço para R$ 1.234,56"""
    try:
        return f"R$ {valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    except:
        return f"R$ {valor}"

@app.route('/', methods=['GET'])
def home():
    return "✅ Bot de Preços - Versão Busca por Nome"

@app.route('/webhook', methods=['POST'])
def webhook():
    """Recebe mensagens do Telegram"""
    try:
        data = request.get_json()
        
        if 'message' in data:
            chat_id = data['message']['chat']['id']
            texto = data['message'].get('text', '').strip()
            
            logger.info(f"Mensagem: {texto}")
            enviar_telegram(chat_id, "🔍 Buscando produto...")
            
            # Comando /start
            if texto == '/start':
                enviar_telegram(chat_id, "🤖 *Bot de Preços*\n\nEnvie links do Mercado Livre ou Amazon!")
                return 'ok', 200
            
            # MERCADO LIVRE
            if 'mercadolivre' in texto or 'mercadolivre.com/sec' in texto:
                # Extrair nome do produto da página
                nome_produto = extrair_nome_da_pagina(texto)
                
                if not nome_produto:
                    enviar_telegram(chat_id, "❌ Não foi possível encontrar o nome do produto na página")
                    return 'ok', 200
                
                # Obter token
                token = obter_token_ml()
                if not token:
                    enviar_telegram(chat_id, "❌ Erro de autenticação com Mercado Livre")
                    return 'ok', 200
                
                # Buscar produto na API
                produto = buscar_produto_ml(nome_produto, token)
                
                if produto:
                    nome = produto.get('title', 'Nome não encontrado')
                    preco = formatar_preco(produto.get('price', 0))
                    preco_original = formatar_preco(produto.get('original_price', produto.get('price', 0)))
                    
                    # Parcelamento
                    parcelas = produto.get('installments', {})
                    parcelamento = f"{parcelas.get('quantity', 0)}x R$ {parcelas.get('amount', 0):.2f}".replace('.', ',') if parcelas else "Sem parcelamento"
                    
                    # Frete grátis
                    frete = produto.get('shipping', {}).get('free_shipping', False)
                    
                    # Link
                    link = produto.get('permalink', '')
                    
                    msg = f"📦 *{nome}*\n\n"
                    
                    if preco_original != preco:
                        msg += f"~~{preco_original}~~ 💰 *{preco}*\n"
                    else:
                        msg += f"💰 *{preco}*\n"
                    
                    msg += f"💳 {parcelamento}\n"
                    
                    if frete:
                        msg += "🚚 *Frete Grátis*\n"
                    
                    # Desconto
                    if produto.get('original_price') and produto.get('price'):
                        desc = ((produto['original_price'] - produto['price']) / produto['original_price']) * 100
                        if desc > 0:
                            msg += f"📉 *{desc:.0f}% OFF*\n"
                    
                    msg += f"\n🔗 [Ver produto]({link})"
                    
                    enviar_telegram(chat_id, msg)
                else:
                    enviar_telegram(chat_id, "❌ Produto não encontrado na API do Mercado Livre")
            
            # AMAZON (mantido)
            elif 'amzn.to' in texto or 'amazon' in texto:
                enviar_telegram(chat_id, "⏳ Processando Amazon...")
                # Aqui vai o código da Amazon que já funcionou
            
            else:
                enviar_telegram(chat_id, "❌ Envie um link do Mercado Livre ou Amazon")
        
        return 'ok', 200
        
    except Exception as e:
        logger.error(f"Erro: {e}")
        return 'ok', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)