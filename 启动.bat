@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt
if not exist ".env" (
  copy .env.example .env
)
python -m streamlit run app.py
pause
