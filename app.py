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
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
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
        logger.info("Novo token obtido")
        return data['access_token']
    except Exception as e:
        logger.error(f"Erro ao obter token: {e}")
        return None

def extrair_id_verdadeiro_ml(url_encurtada):
    """
    Extrai o ID verdadeiro do produto a partir do link encurtado
    Segue o redirect e encontra o MLB12345678 real
    """
    try:
        logger.info(f"Seguindo link encurtado: {url_encurtada}")
        
        # 1. Seguir o redirecionamento
        response = requests.get(url_encurtada, headers=HEADERS, timeout=10, allow_redirects=True)
        url_real = response.url
        logger.info(f"URL real encontrada: {url_real}")
        
        # 2. Tentar extrair ID da URL real (formato /p/MLB12345678)
        match = re.search(r'/p/(ML[B|C]\d+)', url_real)
        if match:
            id_encontrado = match.group(1)
            logger.info(f"✅ ID encontrado na URL: {id_encontrado}")
            return id_encontrado, url_real
        
        # 3. Se não achou na URL, procurar no HTML da página
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Meta tag (mais confiável)
        meta = soup.find('meta', {'property': 'product:retailer_item_id'})
        if meta and meta.get('content'):
            id_encontrado = meta.get('content')
            logger.info(f"✅ ID encontrado em meta tag: {id_encontrado}")
            return id_encontrado, url_real
        
        # Links da página
        for link in soup.find_all('a', href=True):
            match = re.search(r'/(ML[B|C]\d+)/', link['href'])
            if match:
                id_encontrado = match.group(1)
                logger.info(f"✅ ID encontrado em link: {id_encontrado}")
                return id_encontrado, url_real
        
        logger.warning("❌ Nenhum ID encontrado na página")
        return None, url_real
        
    except Exception as e:
        logger.error(f"Erro ao extrair ID: {e}")
        return None, url_encurtada

def consultar_api_ml(item_id):
    """Consulta produto na API do ML"""
    token = obter_token_ml()
    if not token:
        return None
    
    url = f"https://api.mercadolibre.com/items/{item_id}"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        logger.info(f"API retornou: {data.get('title', 'Sem título')[:50]}")
        return data
    except Exception as e:
        logger.error(f"Erro na API: {e}")
        return None

def formatar_preco(valor):
    """Formata preço para R$ 1.234,56"""
    try:
        if isinstance(valor, (int, float)):
            return f"R$ {valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        return f"R$ {valor}"
    except:
        return f"R$ {valor}"

def extrair_dados_amazon(url):
    """Extrai dados da Amazon"""
    try:
        logger.info(f"Extraindo Amazon: {url}")
        response = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        nome = soup.find('span', {'id': 'productTitle'})
        nome = nome.get_text(strip=True) if nome else "Nome não encontrado"
        
        preco = soup.find('span', {'class': 'a-price-whole'})
        preco = preco.get_text(strip=True) if preco else "Preço não encontrado"
        
        return nome, preco
    except Exception as e:
        logger.error(f"Erro Amazon: {e}")
        return "Erro", "Erro na Amazon"

def seguir_redirect(url):
    """Segue redirecionamentos simples"""
    try:
        response = requests.head(url, allow_redirects=True, timeout=5)
        return response.url
    except:
        return url

@app.route('/', methods=['GET'])
def home():
    return "✅ Bot de Preços Funcionando!"

@app.route('/webhook', methods=['POST'])
def webhook():
    """Recebe mensagens do Telegram"""
    try:
        data = request.get_json()
        
        if 'message' in data:
            chat_id = data['message']['chat']['id']
            texto = data['message'].get('text', '').strip()
            
            logger.info(f"Mensagem recebida: {texto}")
            
            # Resposta imediata
            enviar_telegram(chat_id, "⏳ Processando...")
            
            # Comando /start
            if texto == '/start':
                enviar_telegram(chat_id, "🤖 *Bot de Preços*\n\nEnvie links da Amazon ou Mercado Livre!")
                return 'ok', 200
            
            # AMAZON
            if 'amzn.to' in texto or 'amazon' in texto:
                url_final = seguir_redirect(texto)
                nome, preco = extrair_dados_amazon(url_final)
                msg = f"📦 *Amazon*\n\n{nome}\n💰 {preco}"
                enviar_telegram(chat_id, msg)
            
            # MERCADO LIVRE
            elif 'mercadolivre' in texto or 'mercadolibre' in texto or 'mercadolivre.com/sec' in texto:
                # Extrair ID verdadeiro seguindo o link
                produto_id, url_real = extrair_id_verdadeiro_ml(texto)
                
                if produto_id:
                    logger.info(f"Consultando API com ID: {produto_id}")
                    dados = consultar_api_ml(produto_id)
                    
                    if dados:
                        nome = dados.get('title', 'Nome não encontrado')
                        preco_atual = formatar_preco(dados.get('price', 0))
                        preco_anterior = formatar_preco(dados.get('original_price', dados.get('price', 0)))
                        
                        # Parcelamento
                        parcelamento = "Não informado"
                        if 'installments' in dados and dados['installments']:
                            quant = dados['installments'].get('quantity', 0)
                            valor = dados['installments'].get('amount', 0)
                            if quant and valor:
                                parcelamento = f"{quant}x R$ {valor:.2f}".replace('.', ',')
                        
                        # Frete grátis
                        frete_gratis = dados.get('shipping', {}).get('free_shipping', False)
                        
                        # Montar mensagem
                        msg = f"📦 *{nome}*\n\n"
                        
                        if preco_anterior != preco_atual:
                            msg += f"~~{preco_anterior}~~ 💰 *{preco_atual}*\n"
                        else:
                            msg += f"💰 *{preco_atual}*\n"
                        
                        if parcelamento != "Não informado":
                            msg += f"💳 {parcelamento}\n"
                        
                        if frete_gratis:
                            msg += "🚚 *Frete Grátis*\n"
                        
                        # Calcular desconto
                        if dados.get('original_price') and dados.get('price'):
                            desconto = ((dados['original_price'] - dados['price']) / dados['original_price']) * 100
                            if desconto > 0:
                                msg += f"📉 *{desconto:.0f}% OFF*\n"
                        
                    else:
                        msg = "❌ Erro ao consultar API do Mercado Livre"
                else:
                    msg = "❌ Não foi possível encontrar o ID do produto. O link pode ser inválido."
                
                enviar_telegram(chat_id, msg)
            
            # Link não reconhecido
            else:
                enviar_telegram(chat_id, "❌ Envie um link da Amazon ou Mercado Livre")
        
        return 'ok', 200
        
    except Exception as e:
        logger.error(f"Erro no webhook: {e}")
        return 'ok', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🚀 Bot iniciado na porta {port}")
    app.run(host='0.0.0.0', port=port)