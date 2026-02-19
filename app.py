def extrair_dados_ml_rapido(url):
    """Extrai dados do Mercado Livre - VERSÃO COM FORMATAÇÃO EM REAL (R$ 1.234,56)"""
    try:
        logger.info(f"Extraindo ML: {url}")
        
        session = requests.Session()
        response = session.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # ===== NOME DO PRODUTO =====
        nome = None
        
        # Título principal
        titulo = soup.find('h1', class_='ui-pdp-title')
        if titulo:
            nome = titulo.get_text(strip=True)
            logger.info(f"Título encontrado: {nome[:50]}")
        
        if not nome:
            titulo = soup.find('h1', class_='vjs-title')
            if titulo:
                nome = titulo.get_text(strip=True)
        
        if not nome:
            meta_og = soup.find('meta', property='og:title')
            if meta_og:
                nome = meta_og.get('content')
        
        # ===== PREÇO DO PRODUTO =====
        preco = None
        preco_raw = None  # Valor bruto encontrado
        
        # MÉTODO 1: Meta tag price
        meta_price = soup.find('meta', {'itemprop': 'price'})
        if meta_price and meta_price.get('content'):
            preco_raw = meta_price.get('content')
            logger.info(f"Preço encontrado (meta): {preco_raw}")
        
        # MÉTODO 2: Classe andes-money-amount
        if not preco_raw:
            andes_price = soup.find('span', class_='andes-money-amount__fraction')
            if andes_price:
                preco_raw = andes_price.get_text(strip=True)
                # Verificar centavos
                centavos = soup.find('span', class_='andes-money-amount__cents')
                if centavos and centavos.get_text(strip=True) != '00':
                    preco_raw = f"{preco_raw}.{centavos.get_text(strip=True)}"
                logger.info(f"Preço encontrado (andes): {preco_raw}")
        
        # MÉTODO 3: Procurar por R$
        if not preco_raw:
            for elemento in soup.find_all(['span', 'div', 'p']):
                texto = elemento.get_text()
                if 'R$' in texto:
                    numeros = re.findall(r'R\$\s*([\d.,]+)', texto)
                    if numeros:
                        preco_raw = numeros[0]
                        logger.info(f"Preço encontrado (R$): {preco_raw}")
                        break
        
        # ===== FORMATAÇÃO DO PREÇO PARA REAL BRASILEIRO =====
        if preco_raw:
            # Converter para formato numérico primeiro
            preco_raw = str(preco_raw).strip()
            
            # Caso 1: Formato 1234.56 (padrão americano)
            if '.' in preco_raw and not ',' in preco_raw:
                partes = preco_raw.split('.')
                if len(partes) == 2:
                    reais = partes[0]
                    centavos = partes[1].ljust(2, '0')[:2]
                    # Adicionar pontos de milhar
                    if len(reais) > 3:
                        reais = re.sub(r'(\d)(?=(\d{3})+(?!\d))', r'\1.', reais)
                    preco = f"{reais},{centavos}"
            
            # Caso 2: Formato 1.234,56 (já em formato brasileiro)
            elif '.' in preco_raw and ',' in preco_raw:
                # Já está no formato correto, só garantir 2 casas decimais
                preco = preco_raw
                if ',' in preco:
                    partes = preco.split(',')
                    if len(partes) == 2:
                        if len(partes[1]) == 1:
                            preco = f"{partes[0]},{partes[1]}0"
                        elif len(partes[1]) > 2:
                            preco = f"{partes[0]},{partes[1][:2]}"
            
            # Caso 3: Formato 1234,56
            elif ',' in preco_raw and not '.' in preco_raw:
                partes = preco_raw.split(',')
                if len(partes) == 2:
                    reais = partes[0]
                    centavos = partes[1].ljust(2, '0')[:2]
                    # Adicionar pontos de milhar
                    if len(reais) > 3:
                        reais = re.sub(r'(\d)(?=(\d{3})+(?!\d))', r'\1.', reais)
                    preco = f"{reais},{centavos}"
            
            # Caso 4: Apenas números (ex: 123456)
            elif preco_raw.isdigit():
                if len(preco_raw) > 2:
                    reais = preco_raw[:-2]
                    centavos = preco_raw[-2:]
                    # Adicionar pontos de milhar
                    if len(reais) > 3:
                        reais = re.sub(r'(\d)(?=(\d{3})+(?!\d))', r'\1.', reais)
                    preco = f"{reais},{centavos}"
                else:
                    preco = f"0,{preco_raw.zfill(2)}"
            
            else:
                # Se não conseguiu formatar, usa o raw
                preco = preco_raw
            
            logger.info(f"Preço formatado em REAL: R$ {preco}")
        else:
            preco = "Preço não encontrado"
        
        # ===== RESULTADO FINAL =====
        if not nome:
            nome = "Nome não encontrado"
        
        # Garantir que o preço tenha o formato correto
        if preco != "Preço não encontrado" and not preco.startswith('R$'):
            preco = f"R$ {preco}"
        
        logger.info(f"Resultado final: {nome[:30]}... {preco}")
        return nome, preco
        
    except Exception as e:
        logger.error(f"Erro ML: {e}")
        return None, str(e)