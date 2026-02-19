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

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Headers MAIS realistas (simulando Chrome)
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Cache-Control': 'max-age=0',
    'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"'
}

# Cache simples para URLs
url_cache = {}

# Pool de threads
executor = ThreadPoolExecutor(max_workers=4)

# Inicializar bot
bot = telegram.Bot(token=TELEGRAM_TOKEN)

def formatar_preco_real(valor_raw):
    """Converte qualquer formato de preço para Real brasileiro (R$ 1.234,56)"""
    if not valor_raw or valor_raw == "Preço não encontrado":
        return "Preço não encontrado"
    
    try:
        valor_raw = str(valor_raw).strip()
        
        # Caso 1: Formato 1.234,56 (já em formato brasileiro)
        if '.' in valor_raw and ',' in valor_raw:
            partes = valor_raw.split(',')
            if len(partes) == 2:
                reais = partes[0].replace('.', '')
                centavos = partes[1].ljust(2, '0')[:2]
                if len(reais) > 3:
                    reais = re.sub(r'(\d)(?=(\d{3})+(?!\d))', r'\1.', reais)
                return f"R$ {reais},{centavos}"
        
        # Caso 2: Formato 1234.56 (padrão americano)
        elif '.' in valor_raw and not ',' in valor_raw:
            partes = valor_raw.split('.')
            if len(partes) == 2:
                reais = partes[0]
                centavos = partes[1].ljust(2, '0')[:2]
                if len(reais) > 3:
                    reais = re.sub(r'(\d)(?=(\d{3})+(?!\d))', r'\1.', reais)
                return f"R$ {reais},{centavos}"
        
        # Caso 3: Formato 1234,56
        elif ',' in valor_raw and not '.' in valor_raw:
            partes = valor_raw.split(',')
            if len(partes) == 2:
                reais = partes[0]
                centavos = partes[1].ljust(2, '0')[:2]
                if len(reais) > 3:
                    reais = re.sub(r'(\d)(?=(\d{3})+(?!\d))', r'\1.', reais)
                return f"R$ {reais},{centavos}"
        
        # Caso 4: Apenas números (ex: 14699)
        elif valor_raw.replace('.', '').isdigit():
            numeros = valor_raw.replace('.', '')
            if len(numeros) > 2:
                reais = numeros[:-2]
                centavos = numeros[-2:]
                if len(reais) > 3:
                    reais = re.sub(r'(\d)(?=(\d{3})+(?!\d))', r'\1.', reais)
                return f"R$ {reais},{centavos}"
            else:
                return f"R$ 0,{numeros.zfill(2)}"
        
        return f"R$ {valor_raw}"
        
    except Exception as e:
        logger.error(f"Erro ao formatar preço: {e}")
        return f"R$ {valor_raw}"

def seguir_redirects_rapido(url):
    """Segue redirecionamentos de forma otimizada"""
    if url in url_cache:
        logger.info(f"Cache hit: {url}")
        return url_cache[url]
    
    try:
        session = requests.Session()
        response = session.head(url, allow_redirects=True, timeout=8, headers=HEADERS)
        url_final = response.url
        url_cache[url] = url_final
        logger.info(f"Redirect: {url} -> {url_final}")
        return url_final
    except:
        try:
            session = requests.Session()
            response = session.get(url, allow_redirects=True, timeout=8, headers=HEADERS, stream=True)
            url_final = response.url
            response.close()
            url_cache[url] = url_final
            logger.info(f"Redirect (GET): {url} -> {url_final}")
            return url_final
        except Exception as e:
            logger.error(f"Erro redirect: {e}")
            return url

def identificar_site_rapido(url):
    """Identifica site de forma otimizada"""
    url_lower = url.lower()
    
    if 'amazon' in url_lower or 'amzn' in url_lower:
        return 'amazon'
    elif any(x in url_lower for x in ['mercadolivre', 'mercadolibre', 'mercadolivre.com/sec']):
        return 'mercadolivre'
    return None

def extrair_dados_perfil_ml(url):
    """
    Extrai dados completos da página de perfil do Mercado Livre
    Versão final com busca inteligente
    """
    try:
        logger.info("="*50)
        logger.info(f"Iniciando extração para URL: {url}")
        logger.info("="*50)
        
        session = requests.Session()
        response = session.get(url, headers=HEADERS, timeout=15)
        
        logger.info(f"Status code: {response.status_code}")
        logger.info(f"Tamanho da resposta: {len(response.text)} caracteres")
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # ===== INICIALIZAR VARIÁVEIS =====
        nome = "Não encontrado"
        preco_anterior = "Não encontrado"
        preco_atual = "Não encontrado"
        parcelamento = "Não informado"
        frete_gratis = False
        
        # ===== 1. ENCONTRAR NOME DO PRODUTO =====
        # Procurar por textos longos (provavelmente o nome do produto)
        textos_longos = []
        for elem in soup.find_all(['h1', 'h2', 'h3', 'h4', 'p', 'span', 'div']):
            texto = elem.get_text(strip=True)
            if texto and len(texto) > 30 and 'R$' not in texto and 'x' not in texto:
                textos_longos.append(texto)
        
        if textos_longos:
            nome = textos_longos[0]
            logger.info(f"Nome encontrado: {nome[:100]}")
        
        # ===== 2. ENCONTRAR TODOS OS PREÇOS =====
        todos_precos = []
        for elem in soup.find_all(['span', 'div', 'p', 'h3', 'h4']):
            texto = elem.get_text()
            # Procurar por padrões de preço
            matches = re.findall(r'R\$\s*([\d.,]+)', texto)
            for match in matches:
                if match not in todos_precos:  # Evitar duplicatas
                    todos_precos.append(match)
        
        logger.info(f"Preços encontrados: {todos_precos}")
        
        # ===== 3. CLASSIFICAR PREÇOS =====
        if len(todos_precos) >= 2:
            # Converter para float para comparar
            precos_float = []
            precos_originais = []
            
            for p in todos_precos:
                p_clean = p.replace('.', '').replace(',', '.')
                try:
                    precos_float.append(float(p_clean))
                    precos_originais.append(p)
                except:
                    pass
            
            if len(precos_float) >= 2:
                # Encontrar o maior (provável preço anterior) e menor (provável atual)
                max_idx = precos_float.index(max(precos_float))
                min_idx = precos_float.index(min(precos_float))
                
                preco_anterior = formatar_preco_real(precos_originais[max_idx])
                preco_atual = formatar_preco_real(precos_originais[min_idx])
                
                logger.info(f"Preço anterior: {preco_anterior}")
                logger.info(f"Preço atual: {preco_atual}")
        
        elif len(todos_precos) == 1:
            preco_atual = formatar_preco_real(todos_precos[0])
            preco_anterior = preco_atual
            logger.info(f"Preço único: {preco_atual}")
        
        # ===== 4. ENCONTRAR PARCELAMENTO =====
        for elem in soup.find_all(['span', 'div', 'p', 'h3']):
            texto = elem.get_text()
            # Procurar padrão como "5x R$ 29,40"
            match = re.search(r'(\d+x\s*R\$\s*[\d.,]+)', texto, re.I)
            if match:
                parcelamento = match.group(1)
                logger.info(f"Parcelamento encontrado: {parcelamento}")
                break
        
        # ===== 5. ENCONTRAR FRETE GRÁTIS =====
        for elem in soup.find_all(['span', 'div', 'p', 'small']):
            texto = elem.get_text().lower()
            if 'frete grátis' in texto or 'frete gratis' in texto:
                frete_gratis = True
                logger.info("Frete grátis encontrado")
                break
        
        # ===== MONTAR MENSAGEM =====
        logger.info("="*50)
        logger.info("RESULTADO FINAL:")
        logger.info(f"Nome: {nome[:100]}")
        logger.info(f"Preço anterior: {preco_anterior}")
        logger.info(f"Preço atual: {preco_atual}")
        logger.info(f"Parcelamento: {parcelamento}")
        logger.info(f"Frete grátis: {frete_gratis}")
        logger.info("="*50)
        
        mensagem = f"📦 *{nome}*\n\n"
        
        if preco_anterior and preco_anterior != preco_atual and preco_anterior != "Não encontrado":
            mensagem += f"~~{preco_anterior}~~ 💰 *{preco_atual}*\n"
        else:
            mensagem += f"💰 *{preco_atual}*\n"
        
        if parcelamento and parcelamento != "Não informado":
            mensagem += f"💳 {parcelamento}\n"
        
        if frete_gratis:
            mensagem += "🚚 *Frete Grátis*\n"
        
        # Calcular desconto
        if preco_anterior and preco_atual and preco_anterior != preco_atual and preco_anterior != "Não encontrado" and preco_atual != "Não encontrado":
            try:
                ant_num = re.sub(r'[^\d.,]', '', preco_anterior).replace('.', '').replace(',', '.')
                atu_num = re.sub(r'[^\d.,]', '', preco_atual).replace('.', '').replace(',', '.')
                
                ant_float = float(ant_num)
                atu_float = float(atu_num)
                
                if ant_float > 0:
                    desconto = ((ant_float - atu_float) / ant_float) * 100
                    mensagem += f"📉 *{desconto:.0f}% OFF*\n"
            except:
                pass
        
        return mensagem
        
    except Exception as e:
        logger.error(f"Erro ao extrair perfil ML: {e}")
        return f"❌ Erro ao processar: {str(e)}"

def extrair_dados_amazon_rapido(url):
    """Extrai dados da Amazon"""
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
        mensagem = f"📦 *{nome}*\n\n"
        
        if preco_anterior and preco_anterior != preco_atual:
            mensagem += f"~~{preco_anterior}~~ 💰 *{preco_atual}*\n"
        else:
            mensagem += f"💰 *{preco_atual}*\n"
        
        if parcelamento and parcelamento != "Não informado":
            mensagem += f"💳 {parcelamento}\n"
        
        if frete_gratis:
            mensagem += "🚚 *Frete Grátis*\n"
        
        return mensagem
        
    except Exception as e:
        logger.error(f"Erro Amazon: {e}")
        return f"❌ Erro ao processar Amazon: {str(e)}"

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
    <h1>🤖 Bot de Preços - Versão Final</h1>
    <p>Envie links pelo Telegram: @seu_bot</p>
    <p>📌 Extrai automaticamente:</p>
    <ul>
        <li>📦 Nome do produto</li>
        <li>💰 Preço anterior e atual</li>
        <li>💳 Parcelamento</li>
        <li>🚚 Frete grátis</li>
        <li>📉 Percentual de desconto</li>
    </ul>
    '''

@app.route('/webhook', methods=['POST'])
def webhook():
    """Webhook otimizado"""
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
                    "🤖 *Bot de Preços - Versão Final* ⚡\n\n"
                    "Envie um link que eu extraio:\n"
                    "📌 Nome do produto\n"
                    "💰 Preço anterior e atual\n"
                    "💳 Parcelamento\n"
                    "🚚 Frete grátis\n"
                    "📉 Desconto\n\n"
                    "📌 *Exemplos:*\n"
                    "• https://amzn.to/46hzWsh\n"
                    "• https://mercadolivre.com/sec/2cNNseM"
                ))
            else:
                if any(x in text for x in ['http', 'amzn.to', 'mercadolivre.com/sec']):
                    
                    url_final = seguir_redirects_rapido(text)
                    site = identificar_site_rapido(url_final)
                    
                    asyncio.run(enviar_telegram_rapido("⏳ Processando..."))
                    
                    if site == 'amazon':
                        future = executor.submit(extrair_dados_amazon_rapido, url_final)
                        mensagem = future.result(timeout=15)
                        
                    elif site == 'mercadolivre':
                        future = executor.submit(extrair_dados_perfil_ml, url_final)
                        mensagem = future.result(timeout=15)
                    else:
                        mensagem = "❌ Link não suportado. Envie apenas Amazon ou Mercado Livre."
                    
                    asyncio.run(enviar_telegram_rapido(mensagem))
                    
                else:
                    asyncio.run(enviar_telegram_rapido(
                        "❌ Envie um link válido!\n\n"
                        "Exemplos:\n"
                        "• https://amzn.to/46hzWsh\n"
                        "• https://mercadolivre.com/sec/2cNNseM"
                    ))
        
        return 'ok', 200
        
    except Exception as e:
        logger.error(f"Erro webhook: {e}")
        return 'erro', 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🚀 Bot final iniciado na porta {port}")
    logger.info("✅ Versão final com suporte completo para Mercado Livre e Amazon")
    app.run(host='0.0.0.0', port=port, threaded=True)