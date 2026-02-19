from flask import Flask, request
import requests
from bs4 import BeautifulSoup
import os
import re
import logging
import time

app = Flask(__name__)

# CONFIGURAÇÕES
TELEGRAM_TOKEN = "8538755291:AAG2dmZW8KcAN7DnC7pnMIqoSqh490F1YiY"

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Headers realistas
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Connection': 'keep-alive',
}

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

def seguir_ate_produto_real(url_afiliado):
    """
    Segue redirecionamentos até chegar na página REAL do produto
    """
    try:
        logger.info(f"Seguindo link: {url_afiliado}")
        
        # Primeiro redirecionamento (sec -> perfil)
        r1 = requests.get(url_afiliado, headers=HEADERS, allow_redirects=True, timeout=10)
        url_perfil = r1.url
        logger.info(f"URL do perfil: {url_perfil}")
        
        # Extrair link do produto da página de perfil
        soup = BeautifulSoup(r1.text, 'html.parser')
        
        # Procurar por links que levam a produto
        links_produto = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            if '/p/' in href or '/MLB-' in href or 'mercadolivre.com.br/' in href:
                if 'produto' not in href and 'perfil' not in href:
                    links_produto.append(href)
        
        if links_produto:
            # Pega o primeiro link de produto
            url_produto = links_produto[0]
            if not url_produto.startswith('http'):
                url_produto = 'https://www.mercadolivre.com.br' + url_produto
            
            logger.info(f"URL do produto encontrada: {url_produto}")
            
            # Acessar a página do produto
            r2 = requests.get(url_produto, headers=HEADERS, timeout=10)
            return r2.text, url_produto
        
        return r1.text, url_perfil
        
    except Exception as e:
        logger.error(f"Erro ao seguir: {e}")
        return None, url_afiliado

def extrair_dados_ml(html, url):
    """Extrai dados da página do Mercado Livre"""
    try:
        soup = BeautifulSoup(html, 'html.parser')
        
        # NOME
        nome = None
        titulo = soup.find('h1', class_='ui-pdp-title')
        if titulo:
            nome = titulo.get_text(strip=True)
        
        if not nome:
            titulo = soup.find('h1', class_='vjs-title')
            if titulo:
                nome = titulo.get_text(strip=True)
        
        # PREÇO ATUAL
        preco_atual = None
        preco_element = soup.find('meta', {'itemprop': 'price'})
        if preco_element:
            preco_atual = preco_element.get('content')
        
        if not preco_atual:
            preco_element = soup.find('span', class_='andes-money-amount__fraction')
            if preco_element:
                preco_atual = preco_element.get_text(strip=True)
                centavos = soup.find('span', class_='andes-money-amount__cents')
                if centavos:
                    preco_atual = f"{preco_atual}.{centavos.get_text(strip=True)}"
        
        # PREÇO ANTIGO
        preco_antigo = None
        antigo_element = soup.find('span', class_='andes-money-amount--previous')
        if antigo_element:
            valor = antigo_element.find('span', class_='andes-money-amount__fraction')
            if valor:
                preco_antigo = valor.get_text(strip=True)
        
        # PARCELAMENTO
        parcelas = "Não informado"
        parcela_element = soup.find('span', class_='ui-pdp-installments')
        if parcela_element:
            parcelas = parcela_element.get_text(strip=True)
        
        # FRETE GRÁTIS
        frete_gratis = False
        frete_text = soup.find(string=re.compile(r'Frete grátis|Frete GRÁTIS', re.I))
        if frete_text:
            frete_gratis = True
        
        # Formatar preços
        if preco_atual:
            if '.' in preco_atual:
                reais, centavos = preco_atual.split('.')
                preco_atual = f"{reais},{centavos[:2]}"
            preco_atual = f"R$ {preco_atual}"
        
        if preco_antigo:
            preco_antigo = f"R$ {preco_antigo}"
        
        nome = nome if nome else "Nome não encontrado"
        preco_atual = preco_atual if preco_atual else "Preço não encontrado"
        
        return {
            'nome': nome,
            'preco_atual': preco_atual,
            'preco_antigo': preco_antigo,
            'parcelas': parcelas,
            'frete_gratis': frete_gratis,
            'url': url
        }
        
    except Exception as e:
        logger.error(f"Erro extração: {e}")
        return None

def extrair_dados_amazon(url):
    """Extrai dados da Amazon"""
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        nome = soup.find('span', {'id': 'productTitle'})
        nome = nome.get_text(strip=True) if nome else "Nome não encontrado"
        
        preco = soup.find('span', {'class': 'a-price-whole'})
        preco = preco.get_text(strip=True) if preco else "Preço não encontrado"
        preco = f"R$ {preco}"
        
        return nome, preco
    except:
        return "Erro", "Erro"

@app.route('/', methods=['GET'])
def home():
    return "✅ BOT FUNCIONAL"

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        
        if 'message' in data:
            chat_id = data['message']['chat']['id']
            texto = data['message'].get('text', '').strip()
            
            logger.info(f"Mensagem: {texto}")
            enviar_telegram(chat_id, "⏳ Processando...")
            
            # AMAZON
            if 'amzn.to' in texto or 'amazon' in texto:
                nome, preco = extrair_dados_amazon(texto)
                msg = f"📦 *Amazon*\n\n{nome}\n💰 {preco}"
                enviar_telegram(chat_id, msg)
            
            # MERCADO LIVRE - NOVA VERSÃO
            elif 'mercadolivre' in texto or 'mercadolivre.com/sec' in texto:
                # Seguir até a página real do produto
                html, url_real = seguir_ate_produto_real(texto)
                
                if html:
                    dados = extrair_dados_ml(html, url_real)
                    
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
                        enviar_telegram(chat_id, "❌ Não foi possível extrair os dados do produto")
                else:
                    enviar_telegram(chat_id, "❌ Erro ao acessar o link")
            
            # COMANDO START
            elif texto == '/start':
                enviar_telegram(chat_id, "🤖 *Bot Funcional*\n\nEnvie links da Amazon ou Mercado Livre!")
            
            else:
                enviar_telegram(chat_id, "❌ Envie um link da Amazon ou Mercado Livre")
        
        return 'ok', 200
        
    except Exception as e:
        logger.error(f"Erro: {e}")
        return 'ok', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)