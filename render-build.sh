#!/usr/bin/env bash
echo "🚀 Iniciando build..."

# Instalar dependências Python PRIMEIRO
echo "📦 Instalando dependências Python..."
pip install -r requirements.txt

# Instalar Chrome
echo "📦 Instalando Chrome..."
curl -LO https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
mkdir -p /opt/render/project/.chrome
dpkg -x google-chrome-stable_current_amd64.deb /opt/render/project/.chrome
rm google-chrome-stable_current_amd64.deb

# Verificar instalação
echo "✅ Verificando instalações..."
pip list | grep flask
ls -la /opt/render/project/.chrome/opt/google/chrome/ || echo "Chrome não encontrado"

echo "✅ Build concluído!"