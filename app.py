from flask import Flask, request
import requests
from bs4 import BeautifulSoup
import os
import re
import logging

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

def extrair_primeiro_produto_da_pagina(url_afiliado):
    """
    Acessa a página de perfil do afiliado e extrai os dados do PRIMEIRO produto da lista.
    """
    try:
        logger.info(f"Acessando página de perfil: {url_afiliado}")
        response = requests.get(url_afiliado, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # ===== ENCONTRAR O PRIMEIRO PRODUTO =====
        primeiro_produto = None
        
        # Método 1: Procurar pelo primeiro preço
        primeiro_preco = soup.find('span', class_='andes-money-amount__fraction')
        if primeiro_preco:
            # Subir até o container do produto
            container = primeiro_preco.find_parent(['div', 'section', 'li'], 
                                                  class_=re.compile(r'ui-search-layout__item|andes-card|product', re.I))
            if container:
                primeiro_produto = container
                logger.info("Produto encontrado via preço")
        
        # Método 2: Procurar pelo primeiro link de produto
        if not primeiro_produto:
            links_produto = soup.find_all('a', href=re.compile(r'/p/|/MLB-'))
            if links_produto:
                primeiro_produto = links_produto[0].find_parent(['div', 'section', 'li'])
                logger.info("Produto encontrado via link")
        
        if not primeiro_produto:
            logger.warning("Nenhum produto encontrado")
            return None
        
        # ===== EXTRAIR NOME =====
        nome = "Nome não encontrado"
        nome_tag = primeiro_produto.find(['h2', 'h3'], class_=re.compile(r'title|name|product', re.I))
        if nome_tag:
            nome = nome_tag.get_text(strip=True)
        else:
            # Tentar qualquer heading
            heading = primeiro_produto.find(['h2', 'h3', 'h4'])
            if heading:
                nome = heading.get_text(strip=True)
        
        # ===== EXTRAIR PREÇO =====
        preco = "Preço não encontrado"
        preco_tag = primeiro_produto.find('span', class_='andes-money-amount__fraction')
        if preco_tag:
            preco_num = preco_tag.get_text(strip=True)
            # Verificar centavos
            centavos_tag = primeiro_produto.find('span', class_='andes-money-amount__cents')
            if centavos_tag:
                preco = f"{preco_num}.{centavos_tag.get_text(strip=True)}"
            else:
                preco = preco_num
        
        # ===== EXTRAIR PARCELAMENTO =====
        parcelas = "Não informado"
        # Procurar por texto com formato "Xx R$ YY,ZZ"
        parcela_text = primeiro_produto.find(string=re.compile(r'\d+x\s*R\$\s*[\d.,]+', re.I))
        if parcela_text:
            parcelas = parcela_text.strip()
        else:
            # Procurar em spans
            parcela_tag = primeiro_produto.find('span', class_=re.compile(r'installment', re.I))
            if parcela_tag:
                parcelas = parcela_tag.get_text(strip=True)
        
        # ===== EXTRAIR FRETE GRÁTIS =====
        frete_gratis = False
        frete_text = primeiro_produto.find(string=re.compile(r'Frete grátis|Frete GRÁTIS', re.I))
        if frete_text:
            frete_gratis = True
        
        # ===== FORMATAR PREÇO =====
        if preco and preco != "Preço não encontrado":
            # Remover pontos de milhar e converter vírgula
            if '.' in preco and ',' in preco:
                # Formato 1.234,56
                preco = preco.replace('.', '').replace(',', '.')
            elif ',' in preco:
                # Formato 1234,56
                preco = preco.replace(',', '.')
            
            # Garantir duas casas decimais
            if '.' in preco:
                partes = preco.split('.')
                if len(partes) == 2:
                    if len(partes[1]) == 1:
                        preco = f"{partes[0]}.{partes[1]}0"
                    elif len(partes[1]) > 2:
                        preco = f"{partes[0]}.{partes[1][:2]}"
            else:
                if len(preco) > 2:
                    preco = f"{preco[:-2]}.{preco[-2:]}"
                else:
                    preco = f"0.{preco.zfill(2)}"
            
            # Converter para formato brasileiro
            if '.' in preco:
                reais, centavos = preco.split('.')
                # Adicionar pontos de milhar
                if len(reais) > 3:
                    reais = re.sub(r'(\d)(?=(\d{3})+(?!\d))', r'\1.', reais)
                preco = f"R$ {reais},{centavos}"
        
        logger.info(f"✅ Extraído: {nome[:50]}... - {preco}")
        
        return {
            'nome': nome,
            'preco': preco,
            'parcelas': parcelas,
            'frete_gratis': frete_gratis
        }
        
    except Exception as e:
        logger.error(f"Erro na extração: {e}")
        return None

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
        
        # Formatar preço da Amazon
        if preco != "Preço não encontrado":
            preco = f"R$ {preco}"
        
        return nome, preco
    except Exception as e:
        logger.error(f"Erro Amazon: {e}")
        return "Erro", "Erro na Amazon"

@app.route('/', methods=['GET'])
def home():
    return "✅ Bot de Preços - Versão Definitiva"

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
                enviar_telegram(chat_id, 
                    "🤖 *Bot de Preços - Versão Definitiva*\n\n"
                    "Envie links que eu mostro o primeiro produto da página!\n\n"
                    "📌 *Exemplos:*\n"
                    "• https://mercadolivre.com/sec/2TCy2TB\n"
                    "• https://amzn.to/46hzWsh"
                )
                return 'ok', 200
            
            # MERCADO LIVRE
            if 'mercadolivre' in texto or 'mercadolivre.com/sec' in texto:
                enviar_telegram(chat_id, "🔍 Buscando primeiro produto da página...")
                
                dados = extrair_primeiro_produto_da_pagina(texto)
                
                if dados and dados['nome'] != "Nome não encontrado":
                    msg = f"📦 *{dados['nome']}*\n\n"
                    msg += f"💰 *{dados['preco']}*\n"
                    
                    if dados['parcelas'] != "Não informado":
                        msg += f"💳 {dados['parcelas']}\n"
                    
                    if dados['frete_gratis']:
                        msg += "🚚 *Frete Grátis*\n"
                    
                    enviar_telegram(chat_id, msg)
                else:
                    enviar_telegram(chat_id, 
                        "❌ Não consegui encontrar um produto na página.\n\n"
                        "Pode ser que:\n"
                        "• O link seja inválido\n"
                        "• A página não tenha produtos\n"
                        "• O Mercado Livre mudou o layout"
                    )
            
            # AMAZON
            elif 'amzn.to' in texto or 'amazon' in texto:
                enviar_telegram(chat_id, "📦 Buscando na Amazon...")
                nome, preco = extrair_dados_amazon(texto)
                msg = f"📦 *Amazon*\n\n{nome}\n💰 {preco}"
                enviar_telegram(chat_id, msg)
            
            # Link não reconhecido
            else:
                enviar_telegram(chat_id, 
                    "❌ Link não reconhecido.\n\n"
                    "Envie links do:\n"
                    "• Mercado Livre (mercadolivre.com/sec/...)\n"
                    "• Amazon (amzn.to/...)"
                )
        
        return 'ok', 200
        
    except Exception as e:
        logger.error(f"Erro no webhook: {e}")
        return 'ok', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🚀 Bot definitivo iniciado na porta {port}")
    app.run(host='0.0.0.0', port=port)