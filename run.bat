@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PY=
where py >nul 2>nul && set PY=py
if not defined PY where python >nul 2>nul && set PY=python
if not defined PY (
  echo Chua cai Python. Hay tai tai https://www.python.org/downloads/ va tich "Add python.exe to PATH" khi cai.
  pause
  exit /b
)
%PY% -m pip install -r requirements.txt
start /b cmd /c "timeout /t 3 >nul && start http://127.0.0.1:5000"
%PY% app.py
pause
