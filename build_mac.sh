#!/bin/bash
# Đóng gói thành "Trading Journal.app" (chạy trên máy Mac của bạn)
set -e
cd "$(dirname "$0")"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt pywebview pyinstaller
pyinstaller --noconfirm --windowed --name "Trading Journal" --osx-bundle-identifier com.tradingjournal.app \
  --icon icon.icns \
  --add-data "static:static" \
  --hidden-import webview --hidden-import lxml.html --hidden-import lxml.etree --hidden-import lxml._elementpath \
  app.py
echo ""
echo "Xong. App nằm ở: $(pwd)/dist/Trading Journal.app"
echo "Kéo app vào thư mục Applications để dùng."
