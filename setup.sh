#!/bin/bash

echo "🧠 Second Brain CLI - Setup Script"
echo "=================================="
echo ""

# Check Python version
echo "Checking Python version..."
python_version=$(python3 --version 2>&1 | awk '{print $2}')
required_version="3.11"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "❌ Python 3.11+ is required. Current version: $python_version"
    exit 1
fi

echo "✅ Python version: $python_version"
echo ""

# Create virtual environment
echo "Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate
echo "✅ Virtual environment created"
echo ""

# Install dependencies
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt
echo "✅ Dependencies installed"
echo ""

# Check if Ollama is running
echo "Checking Ollama..."
if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "✅ Ollama is running"
else
    echo "⚠️  Ollama is not running. Please start it with: ollama serve"
fi
echo ""

# Check config
if [ ! -f "config.yaml" ]; then
    echo "⚠️  config.yaml not found. Please create it from config.yaml template"
    echo "   Don't forget to add your Telegram bot token!"
else
    echo "✅ config.yaml found"
fi
echo ""

echo "=================================="
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit config.yaml with your bot token"
echo "2. Make sure Ollama is running: ollama serve"
echo "3. Run the bot: python main.py"
echo ""
echo "To activate the virtual environment:"
echo "  source venv/bin/activate"
