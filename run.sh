#!/bin/bash
# Simple script to run ShootyBot

echo "🤖 Starting ShootyBot..."
echo "📂 Working directory: $(pwd)"

# Check for existing bot instances
existing_pids=$(pgrep -f "python.*bot.py" 2>/dev/null)
if [ ! -z "$existing_pids" ]; then
    echo "⚠️  Found existing bot instance(s) with PID(s): $existing_pids"
    echo "🛑 Stopping existing instances..."
    pkill -f "python.*bot.py" 2>/dev/null
    sleep 2
    echo "✅ Existing instances stopped"
fi

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

# Install/update dependencies
echo "📦 Checking and updating dependencies..."
pip install -r requirements.txt --quiet --upgrade
if [ $? -eq 0 ]; then
    echo "✅ Dependencies are up to date"
else
    echo "❌ Failed to install dependencies"
    exit 1
fi

echo "🚀 Starting bot..."
echo "💡 Press Ctrl+C to stop the bot"
echo ""

# Run the bot
python3 bot.py