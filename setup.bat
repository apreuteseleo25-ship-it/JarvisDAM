@echo off
echo 🧠 Second Brain CLI - Setup Script
echo ==================================
echo.

echo Checking Python version...
python --version
if %errorlevel% neq 0 (
    echo ❌ Python is not installed or not in PATH
    exit /b 1
)
echo ✅ Python found
echo.

echo Creating virtual environment...
python -m venv venv
call venv\Scripts\activate.bat
echo ✅ Virtual environment created
echo.

echo Installing dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt
echo ✅ Dependencies installed
echo.

echo Checking Ollama...
curl -s http://localhost:11434/api/tags >nul 2>&1
if %errorlevel% equ 0 (
    echo ✅ Ollama is running
) else (
    echo ⚠️  Ollama is not running. Please start it with: ollama serve
)
echo.

if not exist "config.yaml" (
    echo ⚠️  config.yaml not found. Please create it from config.yaml template
    echo    Don't forget to add your Telegram bot token!
) else (
    echo ✅ config.yaml found
)
echo.

echo ==================================
echo ✅ Setup complete!
echo.
echo Next steps:
echo 1. Edit config.yaml with your bot token
echo 2. Make sure Ollama is running: ollama serve
echo 3. Run the bot: python main.py
echo.
echo To activate the virtual environment:
echo   venv\Scripts\activate.bat
echo.
pause
