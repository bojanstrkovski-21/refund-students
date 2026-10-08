@echo off
cd /d "%~dp0"
echo Starting student travel refunds...
start "Refund students" python app.py
timeout /t 2 /nobreak >nul
start http://127.0.0.1:5050
