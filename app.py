def processar_mercadolivre(url):
    """
    FLUXO CORRETO:
    1️⃣ Abre link de afiliado
    2️⃣ Clica no botão azul "Ir para produto"
    3️⃣ Pega nome e preço da página do produto
    """
    driver = None
    try:
        logger.info(f"📱 [ML] Processando: {url}")
        driver = criar_driver()
        if not driver:
            return None, None
        
        # 1️⃣ Abrir link de afiliado
        driver.get(url)
        time.sleep(4)
        
        # 2️⃣ PROCURAR E CLICAR NO BOTÃO AZUL "IR PARA PRODUTO"
        botao_encontrado = False
        
        # Método 1: Procurar por botão com texto exato "Ir para produto"
        try:
            botoes = driver.find_elements(By.XPATH, "//*[contains(text(), 'Ir para produto')]")
            for botao in botoes:
                # Verificar se é um botão azul (pela cor ou classe)
                cor = botao.value_of_css_property('background-color')
                if 'blue' in cor or 'rgb(0, 123, 255)' in cor or 'botao' in botao.get_attribute('class').lower():
                    driver.execute_script("arguments[0].click();", botao)
                    logger.info("✅ Clique no botão 'Ir para produto'")
                    botao_encontrado = True
                    break
        except:
            pass
        
        # Método 2: Procurar por link que parece botão
        if not botao_encontrado:
            try:
                links = driver.find_elements(By.TAG_NAME, "a")
                for link in links:
                    classe = link.get_attribute('class') or ''
                    texto = link.text.strip()
                    if 'botao' in classe.lower() or 'btn' in classe.lower() or 'ir para produto' in texto.lower():
                        driver.execute_script("arguments[0].click();", link)
                        logger.info("✅ Clique em link com aparência de botão")
                        botao_encontrado = True
                        break
            except:
                pass
        
        # Método 3: Fallback - clicar no primeiro link de produto
        if not botao_encontrado:
            try:
                links = driver.find_elements(By.XPATH, "//a[contains(@href, '/p/') or contains(@href, '/MLB-')]")
                if links:
                    driver.execute_script("arguments[0].click();", links[0])
                    logger.info("✅ Clique em link de produto (fallback)")
                    botao_encontrado = True
            except:
                pass
        
        if not botao_encontrado:
            logger.error("❌ Nenhum botão/link encontrado")
            return None, None
        
        # Aguardar página do produto carregar
        time.sleep(3)
        
        # 3️⃣ Extrair nome e preço da página do produto
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # NOME
        nome = "Nome não encontrado"
        titulo = soup.find('h1', class_='ui-pdp-title')
        if not titulo:
            titulo = soup.find('h1')
        if titulo:
            nome = titulo.get_text(strip=True)
            logger.info(f"📌 Nome: {nome[:50]}...")
        
        # PREÇO
        preco = "Preço não encontrado"
        
        # Método 1: Meta tag
        meta_price = soup.find('meta', {'itemprop': 'price'})
        if meta_price and meta_price.get('content'):
            preco = meta_price.get('content')
            logger.info(f"💰 Preço (meta): {preco}")
        
        # Método 2: Span de preço
        if preco == "Preço não encontrado":
            preco_span = soup.find('span', class_='andes-money-amount__fraction')
            if preco_span:
                preco = preco_span.get_text(strip=True)
                centavos = soup.find('span', class_='andes-money-amount__cents')
                if centavos:
                    preco = f"{preco}.{centavos.get_text(strip=True)}"
                logger.info(f"💰 Preço (span): {preco}")
        
        # Método 3: Texto com R$
        if preco == "Preço não encontrado":
            texto_preco = soup.find(string=re.compile(r'R\$\s*[\d.,]+'))
            if texto_preco:
                match = re.search(r'R\$\s*([\d.,]+)', texto_preco)
                if match:
                    preco = match.group(1)
                    logger.info(f"💰 Preço (texto): {preco}")
        
        # Formatar preço
        if preco and preco != "Preço não encontrado":
            # Limpar e formatar
            preco_limpo = re.sub(r'[^\d.,]', '', str(preco))
            if '.' in preco_limpo and ',' in preco_limpo:
                preco_limpo = preco_limpo.replace('.', '').replace(',', '.')
            elif ',' in preco_limpo:
                preco_limpo = preco_limpo.replace(',', '.')
            
            if '.' in preco_limpo:
                reais, centavos = preco_limpo.split('.')
                if len(reais) > 3:
                    reais = re.sub(r'(\d)(?=(\d{3})+(?!\d))', r'\1.', reais)
                preco = f"R$ {reais},{centavos[:2]}"
            else:
                if len(preco_limpo) > 2:
                    reais = preco_limpo[:-2]
                    centavos = preco_limpo[-2:]
                    if len(reais) > 3:
                        reais = re.sub(r'(\d)(?=(\d{3})+(?!\d))', r'\1.', reais)
                    preco = f"R$ {reais},{centavos}"
                else:
                    preco = f"R$ {preco_limpo},00"
        
        logger.info(f"✅ Preço final: {preco}")
        return nome, preco
        
    except Exception as e:
        logger.error(f"❌ Erro: {e}")
        return None, None
    finally:
        if driver:
            driver.quit()