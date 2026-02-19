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
    com debug detalhado
    """
    try:
        logger.info("="*50)
        logger.info(f"Iniciando extração para URL: {url}")
        logger.info("="*50)
        
        session = requests.Session()
        response = session.get(url, headers=HEADERS, timeout=10)
        
        # DEBUG: Informações da requisição
        logger.info(f"Status code: {response.status_code}")
        logger.info(f"Tamanho da resposta: {len(response.text)} caracteres")
        logger.info(f"URL final após redirects: {response.url}")
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # DEBUG: Título da página
        title = soup.title.string if soup.title else "Sem título"
        logger.info(f"Título da página: {title}")
        
        # DEBUG: Verificar se há elementos com "MAIS VENDIDO"
        mais_vendido = soup.find(string=re.compile(r'MAIS VENDIDO', re.I))
        if mais_vendido:
            logger.info("✓ Encontrou 'MAIS VENDIDO' na página")
        else:
            logger.warning("✗ Não encontrou 'MAIS VENDIDO'")
        
        # DEBUG: Listar todos os headings (h1, h2, h3)
        headings = soup.find_all(['h1', 'h2', 'h3'])
        logger.info(f"Encontrou {len(headings)} headings:")
        for i, h in enumerate(headings[:5]):  # Primeiros 5
            texto = h.get_text(strip=True)
            if texto:
                logger.info(f"  Heading {i+1}: {texto[:100]}")
        
        # DEBUG: Procurar por preços
        precos = soup.find_all(string=re.compile(r'R\$\s*[\d.,]+'))
        logger.info(f"Encontrou {len(precos)} ocorrências de preços (R$):")
        for i, p in enumerate(precos[:5]):
            logger.info(f"  Preço {i+1}: {p}")
        
        # DEBUG: Procurar por parcelamento
        parcelas = soup.find_all(string=re.compile(r'\d+x\s*R\$\s*[\d.,]+', re.I))
        logger.info(f"Encontrou {len(parcelas)} ocorrências de parcelamento:")
        for i, parc in enumerate(parcelas[:3]):
            logger.info(f"  Parcela {i+1}: {parc}")
        
        # DEBUG: Procurar por frete grátis
        frete = soup.find_all(string=re.compile(r'frete\s*grátis|frete\s*gratis', re.I))
        logger.info(f"Encontrou {len(frete)} ocorrências de 'frete grátis'")
        
        # DEBUG: Procurar por cards de produto
        cards = soup.find_all(['div', 'section', 'article'], 
                            class_=re.compile(r'card|product|item|andes-card', re.I))
        logger.info(f"Encontrou {len(cards)} possíveis cards de produto")
        
        # ===== TENTAR EXTRAIR DADOS =====
        nome = "Não encontrado"
        preco_anterior = "Não encontrado"
        preco_atual = "Não encontrado"
        parcelamento = "Não informado"
        frete_gratis = False
        
        # Tentar encontrar o primeiro produto
        if cards:
            primeiro_card = cards[0]
            logger.info("Analisando primeiro card...")
            
            # Nome
            nome_tag = primeiro_card.find(['h2', 'h3', 'h4', 'p'], 
                                        class_=re.compile(r'title|nome|product|name', re.I))
            if nome_tag:
                nome = nome_tag.get_text(strip=True)
                logger.info(f"Nome encontrado no card: {nome[:100]}")
            
            # Preços
            precos_card = primeiro_card.find_all(string=re.compile(r'R\$\s*[\d.,]+'))
            logger.info(f"Preços no card: {len(precos_card)}")
            
            if len(precos_card) >= 2:
                # Pega o primeiro e segundo preço
                preco1 = re.search(r'R\$\s*([\d.,]+)', precos_card[0])
                preco2 = re.search(r'R\$\s*([\d.,]+)', precos_card[1])
                
                if preco1 and preco2:
                    p1 = preco1.group(1)
                    p2 = preco2.group(1)
                    logger.info(f"Preço 1: {p1}, Preço 2: {p2}")
                    
                    # Converter para comparar
                    p1_num = float(p1.replace('.', '').replace(',', '.'))
                    p2_num = float(p2.replace('.', '').replace(',', '.'))
                    
                    if p1_num > p2_num:
                        preco_anterior = formatar_preco_real(p1)
                        preco_atual = formatar_preco_real(p2)
                    else:
                        preco_anterior = formatar_preco_real(p2)
                        preco_atual = formatar_preco_real(p1)
            
            elif len(precos_card) == 1:
                p = re.search(r'R\$\s*([\d.,]+)', precos_card[0])
                if p:
                    preco_atual = formatar_preco_real(p.group(1))
                    preco_anterior = preco_atual
            
            # Parcelamento
            parc_card = primeiro_card.find(string=re.compile(r'\d+x\s*R\$\s*[\d.,]+', re.I))
            if parc_card:
                parcelamento = parc_card.strip()
                logger.info(f"Parcelamento: {parcelamento}")
            
            # Frete grátis
            if primeiro_card.find(string=re.compile(r'frete\s*grátis', re.I)):
                frete_gratis = True
                logger.info("Frete grátis encontrado")
        
        # ===== MONTAR MENSAGEM =====
        logger.info("="*50)
        logger.info("RESULTADO FINAL:")
        logger.info(f"Nome: {nome[:100] if nome != 'Não encontrado' else nome}")
        logger.info(f"Preço anterior: {preco_anterior}")
        logger.info(f"Preço atual: {preco_atual}")
        logger.info(f"Parcelamento: {parcelamento}")
        logger.info(f"Frete grátis: {frete_gratis}")
        logger.info("="*50)
        
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
                ant_num = re.sub(r'[^\d.,]', '', preco_anterior).replace('.', '').replace(',', '.')
                atu_num = re.sub(r'[^\d.,]', '', preco_atual).replace('.', '').replace(',', '.')
                
                ant_float = float(ant_num)
                atu_float = float(atu_num)
                
                if ant_float > 0:
                    desconto = ((ant_float - atu_float) / ant_float) * 100
                    mensagem += f"📉 *{desconto:.0f}% OFF*\n"
            except:
                pass
        
        logger.info("Mensagem gerada com sucesso")
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
    <h1>Bot de Preços - Versão Debug ⚡</h1>
    <p>Envie links pelo Telegram: @seu_bot</p>
    <p>📌 Modo debug ativado - verifique os logs!</p>
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
                    "🤖 *Bot de Preços - Modo Debug* ⚡\n\n"
                    "Envie um link do Mercado Livre que eu vou:\n"
                    "1️⃣ Processar com debug detalhado\n"
                    "2️⃣ Mostrar nos logs o que encontrei\n"
                    "3️⃣ Tentar extrair os dados\n\n"
                    "📌 *Exemplo:*\n"
                    "https://mercadolivre.com/sec/2cNNseM"
                ))
            else:
                if any(x in text for x in ['http', 'amzn.to', 'mercadolivre.com/sec']):
                    
                    url_final = seguir_redirects_rapido(text)
                    site = identificar_site_rapido(url_final)
                    
                    asyncio.run(enviar_telegram_rapido("⏳ Processando com debug... Verifique os logs!"))
                    
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
                        "Exemplo:\n"
                        "https://mercadolivre.com/sec/2cNNseM"
                    ))
        
        return 'ok', 200
        
    except Exception as e:
        logger.error(f"Erro webhook: {e}")
        return 'erro', 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🚀 Bot debug iniciado na porta {port}")
    logger.info("📋 Modo debug ativado - todos os passos serão logados")
    app.run(host='0.0.0.0', port=port, threaded=True)