#!/usr/bin/env bash
echo "🚀 Iniciando robô..."

# Adicionar Chrome ao PATH
export PATH="/opt/render/project/.chrome/opt/google/chrome:$PATH"
echo "Chrome PATH: $PATH"

# Verificar Chrome
which google-chrome || echo "Chrome não encontrado"
google-chrome --version || echo "Erro ao verificar versão do Chrome"

# Iniciar o bot
echo "✅ Robô pronto para receber mensagens!"
python app.py