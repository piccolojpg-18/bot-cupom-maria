from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
import telegram
import asyncio
import os
import re
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

app = Flask(__name__)

# CONFIGURAÇÕES
TELEGRAM_TOKEN = "8538755291:AAG2dmZW8KcAN7DnC7pnMIqoSqh490F1YiY"
TELEGRAM_CHAT_ID = None

# Credenciais do Mercado Livre (via variáveis de ambiente)
ML_CLIENT_ID = os.environ.get('ML_CLIENT_ID')
ML_CLIENT_SECRET = os.environ.get('ML_CLIENT_SECRET')
ML_ACCESS_TOKEN = None  # Será obtido automaticamente

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Headers para simular navegador (para seguir redirects)
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
}

# Cache para tokens e URLs
token_cache = {
    'access_token': None,
    'expires_at': None
}
url_cache = {}

# Pool de threads
executor = ThreadPoolExecutor(max_workers=4)

# Inicializar bot
bot = telegram.Bot(token=TELEGRAM_TOKEN)

def obter_token_ml():
    """Obtém token de acesso à API do Mercado Livre"""
    global token_cache
    
    # Verificar se token ainda é válido (dura 6 horas)
    if token_cache['access_token'] and token_cache['expires_at']:
        if datetime.now().timestamp() < token_cache['expires_at']:
            logger.info("Usando token em cache")
            return token_cache['access_token']
    
    logger.info("Obtendo novo token da API do ML")
    
    url = "https://api.mercadolibre.com/oauth/token"
    payload = {
        'grant_type': 'client_credentials',
        'client_id': ML_CLIENT_ID,
        'client_secret': ML_CLIENT_SECRET
    }
    
    try:
        response = requests.post(url, data=payload)
        response.raise_for_status()
        data = response.json()
        
        # Guardar token e tempo de expiração (6 horas = 21600 segundos)
        token_cache['access_token'] = data['access_token']
        token_cache['expires_at'] = datetime.now().timestamp() + data['expires_in']
        
        logger.info("Token obtido com sucesso")
        return data['access_token']
    except Exception as e:
        logger.error(f"Erro ao obter token ML: {e}")
        return None

def extrair_id_produto_ml(url):
    """
    Extrai o ID do produto (MLB123456789) de qualquer URL do Mercado Livre
    """
    # Padrão 1: /p/MLB123456789
    match = re.search(r'/p/(ML[B|C]\d+)', url)
    if match:
        return match.group(1)
    
    # Padrão 2: MLB123456789 na URL
    match = re.search(r'(ML[B|C]\d{9,})', url)
    if match:
        return match.group(1)
    
    # Padrão 3: ID numérico simples
    match = re.search(r'/ML[B|C]?-?(\d+)', url)
    if match:
        return f"MLB{match.group(1)}"
    
    return None

def formatar_preco_real(valor):
    """Converte preço para formato brasileiro"""
    try:
        if isinstance(valor, (int, float)):
            valor = f"{valor:.2f}"
        
        valor = str(valor).replace('.', ',')
        if ',' in valor:
            partes = valor.split(',')
            if len(partes[0]) > 3:
                reais = re.sub(r'(\d)(?=(\d{3})+(?!\d))', r'\1.', partes[0])
                return f"R$ {reais},{partes[1]}"
        return f"R$ {valor}"
    except:
        return f"R$ {valor}"

def consultar_produto_ml(item_id):
    """
    Consulta a API do Mercado Livre usando o ID do produto
    """
    token = obter_token_ml()
    if not token:
        return None, "Erro ao obter token de acesso"
    
    url = f"https://api.mercadolibre.com/items/{item_id}"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        logger.info(f"API ML retornou dados para {item_id}")
        
        # Extrair informações principais
        nome = data.get('title', 'Nome não encontrado')
        preco_atual = data.get('price', 0)
        preco_anterior = data.get('original_price', preco_atual)
        
        # Parcelamento
        parcelamento = "Não informado"
        if 'installments' in data and data['installments']:
            quant = data['installments'].get('quantity', 0)
            valor = data['installments'].get('amount', 0)
            if quant and valor:
                parcelamento = f"{quant}x R$ {valor:.2f} sem juros"
        
        # Frete grátis
        frete_gratis = False
        if 'shipping' in data:
            frete_gratis = data['shipping'].get('free_shipping', False)
        
        # Formatar preços
        preco_atual_str = formatar_preco_real(preco_atual)
        preco_anterior_str = formatar_preco_real(preco_anterior)
        
        return {
            'nome': nome,
            'preco_atual': preco_atual_str,
            'preco_anterior': preco_anterior_str,
            'parcelamento': parcelamento,
            'frete_gratis': frete_gratis,
            'desconto': ((preco_anterior - preco_atual) / preco_anterior * 100) if preco_anterior > preco_atual else 0,
            'link': data.get('permalink', '')
        }, None
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro na API ML: {e}")
        return None, f"Erro na consulta: {str(e)}"
    except Exception as e:
        logger.error(f"Erro inesperado: {e}")
        return None, f"Erro inesperado: {str(e)}"

def seguir_redirects_rapido(url):
    """Segue redirecionamentos de forma otimizada"""
    if url in url_cache:
        return url_cache[url]
    
    try:
        session = requests.Session()
        response = session.head(url, allow_redirects=True, timeout=8, headers=HEADERS)
        url_final = response.url
        url_cache[url] = url_final
        return url_final
    except:
        try:
            session = requests.Session()
            response = session.get(url, allow_redirects=True, timeout=8, headers=HEADERS, stream=True)
            url_final = response.url
            response.close()
            url_cache[url] = url_final
            return url_final
        except:
            return url

def extrair_dados_amazon_rapido(url):
    """Extrai dados da Amazon (fallback)"""
    try:
        logger.info(f"Extraindo Amazon: {url}")
        
        session = requests.Session()
        response = session.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        nome = None
        nome_tag = soup.find('span', {'id': 'productTitle'})
        if nome_tag:
            nome = nome_tag.get_text(strip=True)
        
        preco_atual = None
        preco_anterior = None
        
        preco_tag = soup.find('span', {'class': 'a-price-whole'})
        if preco_tag:
            preco_atual = preco_tag.get_text(strip=True)
            centavos = soup.find('span', {'class': 'a-price-fraction'})
            if centavos:
                preco_atual = f"{preco_atual}.{centavos.get_text(strip=True)}"
            preco_atual = formatar_preco_real(preco_atual)
        
        antigo_tag = soup.find('span', {'class': 'a-text-price'})
        if antigo_tag:
            antigo_text = antigo_tag.get_text()
            match = re.search(r'R\$\s*([\d.,]+)', antigo_text)
            if match:
                preco_anterior = formatar_preco_real(match.group(1))
        
        if not preco_anterior:
            preco_anterior = preco_atual
        
        parcelamento = "Não informado"
        parcela_tag = soup.find(string=re.compile(r'\d+x\s*R\$\s*[\d.,]+', re.I))
        if parcela_tag:
            parcelamento = parcela_tag.strip()
        
        frete_gratis = False
        frete_text = soup.find(string=re.compile(r'frete\s*grátis|Frete\s*GRÁTIS', re.I))
        if frete_text:
            frete_gratis = True
        
        nome = nome if nome else "Nome não encontrado"
        
        return {
            'nome': nome,
            'preco_atual': preco_atual,
            'preco_anterior': preco_anterior,
            'parcelamento': parcelamento,
            'frete_gratis': frete_gratis
        }, None
        
    except Exception as e:
        logger.error(f"Erro Amazon: {e}")
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
    <h1>🤖 Bot de Preços - Versão Oficial</h1>
    <p>Usando API oficial do Mercado Livre</p>
    <p>Envie links pelo Telegram: @seu_bot</p>
    '''

@app.route('/webhook', methods=['POST'])
def webhook():
    """Webhook principal"""
    try:
        update = request.get_json()
        
        if 'message' in update:
            chat_id = update['message']['chat']['id']
            text = update['message'].get('text', '')
            
            global TELEGRAM_CHAT_ID
            TELEGRAM_CHAT_ID = chat_id
            
            logger.info(f"Mensagem recebida: {text}")
            
            if text.startswith('/start'):
                asyncio.run(enviar_telegram_rapido(
                    "🤖 *Bot de Preços - API Oficial* ⚡\n\n"
                    "Envie um link do Mercado Livre ou Amazon!\n\n"
                    "📌 *Exemplos:*\n"
                    "• https://mercadolivre.com/sec/2cNNseM\n"
                    "• https://amzn.to/46hzWsh"
                ))
            else:
                if any(x in text for x in ['http', 'amzn.to', 'mercadolivre.com/sec']):
                    
                    asyncio.run(enviar_telegram_rapido("⏳ Processando..."))
                    
                    url_final = seguir_redirects_rapido(text)
                    
                    # Identificar site
                    if 'amazon' in url_final.lower() or 'amzn' in url_final.lower():
                        # Usar Amazon fallback
                        future = executor.submit(extrair_dados_amazon_rapido, url_final)
                        dados, erro = future.result(timeout=15)
                        
                        if dados:
                            msg = f"📦 *{dados['nome']}*\n\n"
                            if dados['preco_anterior'] != dados['preco_atual']:
                                msg += f"~~{dados['preco_anterior']}~~ 💰 *{dados['preco_atual']}*\n"
                            else:
                                msg += f"💰 *{dados['preco_atual']}*\n"
                            
                            if dados['parcelamento'] != "Não informado":
                                msg += f"💳 {dados['parcelamento']}\n"
                            
                            if dados['frete_gratis']:
                                msg += "🚚 *Frete Grátis*\n"
                            
                            asyncio.run(enviar_telegram_rapido(msg))
                        else:
                            asyncio.run(enviar_telegram_rapido(f"❌ Erro: {erro}"))
                    
                    elif any(x in url_final.lower() for x in ['mercadolivre', 'mercadolibre']):
                        # Extrair ID do produto
                        produto_id = extrair_id_produto_ml(url_final)
                        
                        if not produto_id:
                            asyncio.run(enviar_telegram_rapido("❌ Não foi possível extrair o ID do produto da URL"))
                            return 'ok', 200
                        
                        logger.info(f"ID do produto: {produto_id}")
                        
                        # Consultar API do ML
                        dados, erro = consultar_produto_ml(produto_id)
                        
                        if dados:
                            msg = f"📦 *{dados['nome']}*\n\n"
                            
                            if dados['preco_anterior'] != dados['preco_atual']:
                                msg += f"~~{dados['preco_anterior']}~~ 💰 *{dados['preco_atual']}*\n"
                            else:
                                msg += f"💰 *{dados['preco_atual']}*\n"
                            
                            if dados['parcelamento'] != "Não informado":
                                msg += f"💳 {dados['parcelamento']}\n"
                            
                            if dados['frete_gratis']:
                                msg += "🚚 *Frete Grátis*\n"
                            
                            if dados['desconto'] > 0:
                                msg += f"📉 *{dados['desconto']:.0f}% OFF*\n"
                            
                            asyncio.run(enviar_telegram_rapido(msg))
                        else:
                            asyncio.run(enviar_telegram_rapido(f"❌ Erro: {erro}"))
                    else:
                        asyncio.run(enviar_telegram_rapido("❌ Link não suportado"))
                else:
                    asyncio.run(enviar_telegram_rapido("❌ Envie um link válido!"))
        
        return 'ok', 200
        
    except Exception as e:
        logger.error(f"Erro webhook: {e}")
        return 'erro', 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🚀 Bot com API oficial do ML iniciado na porta {port}")
    logger.info(f"✅ ML_CLIENT_ID configurado: {ML_CLIENT_ID[:5]}..." if ML_CLIENT_ID else "❌ ML_CLIENT_ID não encontrado")
    app.run(host='0.0.0.0', port=port, threaded=True)