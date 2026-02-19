from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
import telegram
import asyncio
import os
import re
import logging
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)

# CONFIGURAÇÕES
TELEGRAM_TOKEN = "8538755291:AAG2dmZW8KcAN7DnC7pnMIqoSqh490F1YiY"
TELEGRAM_CHAT_ID = None

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Headers otimizados
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1'
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
        logger.info(f"Formatando preço raw: {valor_raw}")
        
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
    Extrai dados completos da página de perfil do Mercado Livre:
    - Nome completo do produto (laranja) ✅
    - Preço anterior (amarelo) ✅
    - Preço atual (rosa) ✅
    - Parcelamento (roxo) ✅
    - Frete grátis (verde) ✅
    """
    try:
        logger.info(f"Extraindo dados de perfil ML: {url}")
        
        session = requests.Session()
        response = session.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # ===== INICIALIZAR VARIÁVEIS =====
        nome = "Não encontrado"
        preco_anterior = "Não encontrado"
        preco_atual = "Não encontrado"
        parcelamento = "Não informado"
        frete_gratis = False
        
        # ===== ENCONTRAR O PRIMEIRO PRODUTO (MAIS VENDIDO) =====
        produto_container = None
        
        # Método 1: Procurar pelo "MAIS VENDIDO"
        mais_vendido = soup.find(string=re.compile(r'MAIS VENDIDO', re.I))
        if mais_vendido:
            produto_container = mais_vendido.find_parent(['div', 'section', 'article'])
            logger.info("Encontrou 'MAIS VENDIDO'")
        
        # Método 2: Se não achou, pegar o primeiro card de produto
        if not produto_container:
            cards = soup.find_all(['div', 'section', 'article'], 
                                 class_=re.compile(r'card|product|item|andes-card', re.I))
            if cards:
                produto_container = cards[0]
                logger.info("Usando primeiro card de produto")
        
        if produto_container:
            # ===== NOME DO PRODUTO (LARANJA) =====
            nome_tag = produto_container.find(['h2', 'h3', 'h4', 'p', 'a'], 
                                            class_=re.compile(r'title|nome|product|name', re.I))
            if nome_tag:
                nome = nome_tag.get_text(strip=True)
                logger.info(f"Nome encontrado: {nome[:50]}")
            
            # ===== PREÇOS =====
            # Encontrar todos os textos com R$
            textos_preco = produto_container.find_all(string=re.compile(r'R\$\s*[\d.,]+'))
            
            precos_encontrados = []
            for texto in textos_preco:
                parent = texto.parent
                texto_completo = parent.get_text()
                match = re.search(r'R\$\s*([\d.,]+)', texto_completo)
                if match:
                    precos_encontrados.append(match.group(1))
            
            logger.info(f"Preços encontrados: {precos_encontrados}")
            
            # Classificar preços (assumindo que o menor é o atual, maior é o anterior)
            if len(precos_encontrados) >= 2:
                # Converter para float para comparar
                precos_float = []
                for p in precos_encontrados:
                    p_clean = p.replace('.', '').replace(',', '.')
                    try:
                        precos_float.append(float(p_clean))
                    except:
                        pass
                
                if len(precos_float) >= 2:
                    preco_atual_val = min(precos_float)
                    preco_anterior_val = max(precos_float)
                    
                    preco_atual = formatar_preco_real(str(preco_atual_val).replace('.', ','))
                    preco_anterior = formatar_preco_real(str(preco_anterior_val).replace('.', ','))
                    
                    logger.info(f"Preço atual: {preco_atual}, Preço anterior: {preco_anterior}")
            elif len(precos_encontrados) == 1:
                preco_atual = formatar_preco_real(precos_encontrados[0])
                preco_anterior = preco_atual  # Se só tem um, usa o mesmo
                logger.info(f"Apenas um preço encontrado: {preco_atual}")
            
            # ===== PARCELAMENTO (ROXO) =====
            parcelamento_text = produto_container.find(string=re.compile(r'\d+x\s*R\$\s*[\d.,]+', re.I))
            if parcelamento_text:
                parent = parcelamento_text.parent
                parcelamento = parent.get_text(strip=True)
                logger.info(f"Parcelamento: {parcelamento}")
            
            # ===== FRETE GRÁTIS (VERDE) =====
            frete_text = produto_container.find(string=re.compile(r'frete\s*grátis|frete\s*gratis', re.I))
            if frete_text:
                frete_gratis = True
                logger.info("Frete grátis encontrado")
        
        # ===== MONTAR MENSAGEM =====
        mensagem = f"📦 *{nome}*\n\n"
        
        if preco_anterior and preco_anterior != preco_atual:
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
                # Extrair números para calcular desconto
                ant_num = re.sub(r'[^\d.,]', '', preco_anterior).replace('.', '').replace(',', '.')
                atu_num = re.sub(r'[^\d.,]', '', preco_atual).replace('.', '').replace(',', '.')
                
                ant_float = float(ant_num)
                atu_float = float(atu_num)
                
                if ant_float > 0:
                    desconto = ((ant_float - atu_float) / ant_float) * 100
                    mensagem += f"📉 *{desconto:.0f}% OFF*\n"
            except:
                pass
        
        logger.info(f"Mensagem gerada: {mensagem[:100]}...")
        return mensagem
        
    except Exception as e:
        logger.error(f"Erro ao extrair perfil ML: {e}")
        return f"❌ Erro ao processar: {str(e)}"

def extrair_dados_amazon_rapido(url):
    """Extrai dados da Amazon (adaptar para mesmo formato)"""
    try:
        logger.info(f"Extraindo Amazon: {url}")
        
        session = requests.Session()
        response = session.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Nome
        nome = None
        nome_tag = soup.find('span', {'id': 'productTitle'})
        if nome_tag:
            nome = nome_tag.get_text(strip=True)
        
        # Preços
        preco_atual = None
        preco_anterior = None
        
        # Preço atual
        preco_tag = soup.find('span', {'class': 'a-price-whole'})
        if preco_tag:
            preco_atual = preco_tag.get_text(strip=True)
            centavos = soup.find('span', {'class': 'a-price-fraction'})
            if centavos:
                preco_atual = f"{preco_atual}.{centavos.get_text(strip=True)}"
            preco_atual = formatar_preco_real(preco_atual)
        
        # Preço anterior (riscado)
        antigo_tag = soup.find('span', {'class': 'a-text-price'})
        if antigo_tag:
            antigo_text = antigo_tag.get_text()
            match = re.search(r'R\$\s*([\d.,]+)', antigo_text)
            if match:
                preco_anterior = formatar_preco_real(match.group(1))
        
        if not preco_anterior:
            preco_anterior = preco_atual
        
        # Parcelamento
        parcelamento = "Não informado"
        parcela_tag = soup.find(string=re.compile(r'\d+x\s*R\$\s*[\d.,]+', re.I))
        if parcela_tag:
            parcelamento = parcela_tag.strip()
        
        # Frete grátis
        frete_gratis = False
        frete_text = soup.find(string=re.compile(r'frete\s*grátis|Frete\s*GRÁTIS', re.I))
        if frete_text:
            frete_gratis = True
        
        # Montar mensagem
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
    <h1>Bot de Preços Completo ⚡</h1>
    <p>Envie links pelo Telegram: @seu_bot</p>
    <p>📌 Extrai: Nome, Preço anterior, Preço atual, Parcelamento, Frete grátis</p>
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
            
            logger.info(f"Mensagem recebida: {text[:50]}...")
            
            if text.startswith('/start'):
                asyncio.run(enviar_telegram_rapido(
                    "🤖 *Bot de Preços Completo* ⚡\n\n"
                    "Envie um link que eu extraio:\n"
                    "📌 Nome do produto\n"
                    "💰 Preço anterior e atual\n"
                    "💳 Parcelamento\n"
                    "🚚 Frete grátis\n\n"
                    "📌 *Exemplos:*\n"
                    "• https://amzn.to/46hzWsh\n"
                    "• https://mercadolivre.com/sec/267Mk5q"
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
                        "• https://mercadolivre.com/sec/267Mk5q"
                    ))
        
        return 'ok', 200
        
    except Exception as e:
        logger.error(f"Erro webhook: {e}")
        return 'erro', 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🚀 Bot completo iniciado na porta {port}")
    app.run(host='0.0.0.0', port=port, threaded=True)