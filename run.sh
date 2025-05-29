#!/bin/bash
# Simple script to run ShootyBot

echo "🤖 Starting ShootyBot..."
echo "📂 Working directory: $(pwd)"

# Activate virtual environment
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    echo "✅ Virtual environment activated"
else
    echo "❌ Virtual environment not found. Run: python3.11 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "❌ .env file not found. Copy .env.example to .env and add your bot token"
    exit 1
fi

# Check dependencies
python3 -c "import discord; print('✅ Discord.py is installed')" || {
    echo "❌ Dependencies missing. Run: pip install -r requirements.txt"
    exit 1
}

echo "🚀 Starting bot..."
echo "💡 Press Ctrl+C to stop the bot"
echo ""

# Run the bot
python3 bot.py