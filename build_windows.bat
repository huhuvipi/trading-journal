@echo off
setlocal
cd /d "%~dp0"

echo [1/4] Creating virtual environment...
if not exist .venv\Scripts\python.exe py -m venv .venv
call .venv\Scripts\activate.bat

echo [2/4] Installing dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt pywebview pyinstaller

echo [3/4] Building Trading Journal for Windows...
set "ICON_ARGS="
if exist icon.ico set "ICON_ARGS=--icon icon.ico"
python -m PyInstaller --noconfirm --windowed --name "Trading Journal" ^
  %ICON_ARGS% ^
  --add-data "static;static" ^
  --hidden-import webview ^
  --hidden-import lxml.html ^
  --hidden-import lxml.etree ^
  --hidden-import lxml._elementpath ^
  app.py

echo [4/4] Done.
echo App: %CD%\dist\Trading Journal\Trading Journal.exe
pause
