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

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
}

def enviar_telegram(chat_id, texto):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {'chat_id': chat_id, 'text': texto, 'parse_mode': 'Markdown'}
    try:
        requests.post(url, json=payload, timeout=5)
    except:
        pass

def achar_qualquer_produto(url):
    """Método BRUTAL: varre a página até achar qualquer coisa que pareça um produto"""
    try:
        logger.info(f"ACESSANDO: {url}")
        response = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # SALVAR HTML PARA DEBUG (opcional, comente se não quiser)
        with open('pagina.html', 'w', encoding='utf-8') as f:
            f.write(response.text)
        logger.info("HTML salvo para debug")
        
        # ==========================================
        # MÉTODO 1: PROCURAR POR PREÇO (MAIS CONFIÁVEL)
        # ==========================================
        precos = soup.find_all(['span', 'div', 'p'], string=re.compile(r'R\$\s*\d+'))
        logger.info(f"Encontrados {len(precos)} elementos com preço")
        
        if precos:
            # Pega o primeiro preço
            preco_element = precos[0]
            preco_text = preco_element.get_text(strip=True)
            
            # Tenta encontrar o nome do produto perto deste preço
            nome = "Produto encontrado"
            
            # Sobe 5 níveis procurando um nome
            atual = preco_element
            for _ in range(5):
                if atual:
                    # Procura por headings dentro deste elemento
                    heading = atual.find(['h1', 'h2', 'h3', 'h4'])
                    if heading:
                        nome = heading.get_text(strip=True)
                        break
                    atual = atual.parent
                else:
                    break
            
            # Se não achou heading, pega qualquer texto grande próximo
            if nome == "Produto encontrado":
                pai = preco_element.parent
                textos = pai.find_all(string=True)
                for t in textos:
                    t = t.strip()
                    if len(t) > 20 and 'R$' not in t:
                        nome = t
                        break
            
            # Limpar preço
            preco_match = re.search(r'R\$\s*([\d.,]+)', preco_text)
            if preco_match:
                preco = preco_match.group(1)
                if ',' in preco and '.' in preco:
                    preco = preco.replace('.', '').replace(',', '.')
                elif ',' in preco:
                    preco = preco.replace(',', '.')
                preco = f"R$ {preco}"
            else:
                preco = preco_text
            
            return nome, preco
        
        # ==========================================
        # MÉTODO 2: PROCURAR POR IMAGENS DE PRODUTO
        # ==========================================
        imagens = soup.find_all('img', alt=True)
        for img in imagens:
            alt = img.get('alt', '')
            if len(alt) > 20 and 'R$' not in alt:
                # Achou uma imagem com texto alternativo longo
                # Tenta encontrar preço perto desta imagem
                pai = img.parent
                for _ in range(3):
                    texto_pai = pai.get_text()
                    preco_match = re.search(r'R\$\s*([\d.,]+)', texto_pai)
                    if preco_match:
                        preco = preco_match.group(1)
                        if ',' in preco and '.' in preco:
                            preco = preco.replace('.', '').replace(',', '.')
                        elif ',' in preco:
                            preco = preco.replace(',', '.')
                        return alt, f"R$ {preco}"
                    pai = pai.parent
                return alt, "Preço encontrado próximo"
        
        # ==========================================
        # MÉTODO 3: QUALQUER TEXTO GRANDE COM NÚMERO
        # ==========================================
        todos_textos = soup.find_all(string=True)
        for texto in todos_textos:
            texto = texto.strip()
            if len(texto) > 30 and re.search(r'\d+', texto):
                # Tem texto longo com número - provavelmente é produto
                preco_match = re.search(r'R\$\s*([\d.,]+)', texto)
                if preco_match:
                    preco = preco_match.group(1)
                    return texto[:100], f"R$ {preco}"
                return texto[:100], "Preço não encontrado"
        
        return None, None
        
    except Exception as e:
        logger.error(f"Erro BRUTAL: {e}")
        return None, None

@app.route('/', methods=['GET'])
def home():
    return "🔥 BOT RADICAL FUNCIONANDO"

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        
        if 'message' in data:
            chat_id = data['message']['chat']['id']
            texto = data['message'].get('text', '').strip()
            
            logger.info(f"RECEBIDO: {texto}")
            enviar_telegram(chat_id, "⚡ Processando...")
            
            if texto == '/start':
                enviar_telegram(chat_id, "🔥 *BOT RADICAL*\n\nEnvia qualquer link do Mercado Livre que eu acho o produto!")
                return 'ok', 200
            
            if 'mercadolivre' in texto:
                enviar_telegram(chat_id, "🔍 Varrendo a página...")
                
                nome, preco = achar_qualquer_produto(texto)
                
                if nome:
                    msg = f"📦 *{nome}*\n\n"
                    if preco:
                        msg += f"💰 *{preco}*"
                    else:
                        msg += "💰 Preço não encontrado"
                    enviar_telegram(chat_id, msg)
                else:
                    enviar_telegram(chat_id, "❌ Não achei nada. Manda o link de novo?")
            
            elif 'amzn' in texto:
                enviar_telegram(chat_id, "📦 Amazon (vou implementar depois)")
            
            else:
                enviar_telegram(chat_id, "❌ Manda link do Mercado Livre")
        
        return 'ok', 200
        
    except Exception as e:
        logger.error(f"ERRO: {e}")
        return 'ok', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)