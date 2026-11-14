#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

echo "[1/4] Creating virtual environment..."
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate

echo "[2/4] Installing dependencies..."
python -m pip install --upgrade pip
pip install -r requirements.txt pywebview pyinstaller

echo "[3/4] Building Trading Journal for Linux..."
pyinstaller --noconfirm --windowed \
  --name "Trading Journal" \
  --add-data "static:static" \
  --hidden-import webview \
  --hidden-import lxml.html \
  --hidden-import lxml.etree \
  --hidden-import lxml._elementpath \
  app.py

echo "[4/4] Done."
echo "App: $(pwd)/dist/Trading Journal/Trading Journal"
