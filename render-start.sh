#!/usr/bin/env bash
echo "🚀 Iniciando robô..."

# Adicionar Chrome ao PATH
export PATH="/opt/render/project/.chrome/opt/google/chrome:$PATH"
echo "Chrome PATH: $PATH"

# Verificar Chrome
if [ -f "/opt/render/project/.chrome/opt/google/chrome/google-chrome" ]; then
    echo "✅ Chrome encontrado!"
    /opt/render/project/.chrome/opt/google/chrome/google-chrome --version
else
    echo "❌ Chrome não encontrado em /opt/render/project/.chrome/opt/google/chrome/"
    ls -la /opt/render/project/.chrome/opt/google/chrome/ || echo "Diretório não existe"
fi

# Verificar se Flask está instalado
echo "🔍 Verificando Flask..."
python -c "import flask; print('✅ Flask instalado:', flask.__version__)" || pip install flask==3.0.3

# Iniciar o bot
echo "✅ Robô pronto para receber mensagens!"
python app.py