@echo off
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
  echo 未找到 Python。请先安装 Python 3.10 或更高版本，安装时勾选 Add to PATH。
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo 正在创建虚拟环境...
  python -m venv .venv
  if errorlevel 1 (
    echo 创建虚拟环境失败。
    pause
    exit /b 1
  )
)

echo 正在安装依赖，请稍等（第一次可能要几分钟）...
".venv\Scripts\python.exe" -m pip install -U pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo 依赖安装失败。请检查网络后重新双击本文件。
  pause
  exit /b 1
)

if not exist ".env" (
  copy .env.example .env >nul
)

".venv\Scripts\python.exe" -m streamlit run app.py --browser.gatherUsageStats false
pause
