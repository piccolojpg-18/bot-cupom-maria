def processar_mercadolivre(url):
    """
    1. Entra no link de afiliado
    2. Encontra e clica no link do primeiro produto (3 métodos de fallback)
    3. Extrai nome e preço
    """
    driver = None
    try:
        logger.info(f"📱 Processando Mercado Livre: {url}")
        driver = criar_driver()
        if not driver:
            return None, None

        # PASSO 1: Abrir link de afiliado
        driver.get(url)
        time.sleep(4)  # Aguarda carregamento

        # --- PASSO 2: Encontrar e clicar no link do produto (Múltiplas tentativas) ---
        link_encontrado = False

        # Método 1: Link que contém '/p/' (padrão de produto)
        try:
            link_produto = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//a[contains(@href, '/p/')]"))
            )
            driver.execute_script("arguments[0].click();", link_produto)
            logger.info("✅ Clique realizado via link /p/")
            link_encontrado = True
        except:
            logger.warning("Método 1 falhou (link /p/)")

        if not link_encontrado:
            # Método 2: Link que contém 'MLB-' (outro padrão de produto)
            try:
                link_produto = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//a[contains(@href, '/MLB-')]"))
                )
                driver.execute_script("arguments[0].click();", link_produto)
                logger.info("✅ Clique realizado via link /MLB-/")
                link_encontrado = True
            except:
                logger.warning("Método 2 falhou (link /MLB-/)")

        if not link_encontrado:
            # Método 3: Botão com texto "Ir para produto"
            try:
                botoes = driver.find_elements(By.XPATH, "//*[contains(text(), 'Ir para produto') or contains(text(), 'Ver produto')]")
                if botoes:
                    driver.execute_script("arguments[0].click();", botoes[0])
                    logger.info("✅ Clique realizado via botão de texto")
                    link_encontrado = True
            except:
                logger.warning("Método 3 falhou (botão de texto)")

        if not link_encontrado:
            # Método 4: Qualquer link que pareça de produto (fallback final)
            try:
                links = driver.find_elements(By.TAG_NAME, "a")
                for link in links[:15]:  # Limita para não travar
                    href = link.get_attribute('href') or ""
                    if any(x in href for x in ['/p/', '/MLB-', 'produto']):
                        driver.execute_script("arguments[0].click();", link)
                        logger.info("✅ Clique realizado via link genérico")
                        link_encontrado = True
                        break
            except:
                logger.warning("Método 4 falhou (link genérico)")

        if not link_encontrado:
            logger.error("❌ Nenhum método de clique funcionou.")
            # Se não conseguir clicar, tenta extrair dados da própria página de perfil? 
            # (Improvável, melhor retornar erro)
            return None, None

        # Aguarda a página do produto carregar
        time.sleep(3)

        # PASSO 3: Extrair dados da página do produto
        soup = BeautifulSoup(driver.page_source, 'html.parser')

        # Nome
        nome = "Nome não encontrado"
        titulo = soup.find('h1', class_='ui-pdp-title')
        if titulo:
            nome = titulo.get_text(strip=True)
            logger.info(f"Nome extraído: {nome[:50]}...")
        else:
            # Fallback para título
            titulo_h1 = soup.find('h1')
            if titulo_h1:
                nome = titulo_h1.get_text(strip=True)

        # Preço atual
        preco = "Preço não encontrado"
        meta_price = soup.find('meta', {'itemprop': 'price'})
        if meta_price and meta_price.get('content'):
            preco = meta_price.get('content')
            logger.info(f"Preço extraído via meta: {preco}")
        else:
            preco_span = soup.find('span', class_='andes-money-amount__fraction')
            if preco_span:
                preco_raw = preco_span.get_text(strip=True)
                centavos = soup.find('span', class_='andes-money-amount__cents')
                if centavos:
                    preco = f"{preco_raw}.{centavos.get_text(strip=True)}"
                else:
                    preco = preco_raw
                logger.info(f"Preço extraído via span: {preco}")

        if preco and preco != "Preço não encontrado":
            preco = formatar_preco_br(preco)

        return nome, preco

    except Exception as e:
        logger.error(f"❌ Erro no processamento do Mercado Livre: {e}")
        return None, None
    finally:
        if driver:
            driver.quit()