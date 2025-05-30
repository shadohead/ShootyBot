#!/bin/bash
# One-time setup script for ShootyBot

echo "🤖 Setting up ShootyBot..."
echo "📂 Working directory: $(pwd)"

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed"
    exit 1
fi

echo "✅ Python 3 found: $(python3 --version)"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
    echo "✅ Virtual environment created"
else
    echo "✅ Virtual environment already exists"
fi

# Activate virtual environment
source venv/bin/activate
echo "✅ Virtual environment activated"

# Install dependencies
echo "📦 Installing dependencies..."
pip install -r requirements.txt
echo "✅ Dependencies installed"

# Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "✅ Created .env file from .env.example"
        echo "⚠️  Please edit .env file and add your Discord bot token"
    else
        echo "❌ .env.example not found. Creating basic .env file..."
        cat > .env << EOF
BOT_TOKEN=your_discord_bot_token_here
SHOOTY_ROLE_CODE=<@&your_role_id>
HENRIK_API_KEY=your_henrik_key_here
LOG_LEVEL=INFO
EOF
        echo "✅ Created basic .env file"
        echo "⚠️  Please edit .env file and add your Discord bot token"
    fi
else
    echo "✅ .env file already exists"
fi

# Create data directory if it doesn't exist
if [ ! -d "data" ]; then
    mkdir -p data
    echo "✅ Created data directory"
else
    echo "✅ Data directory already exists"
fi

echo ""
echo "🎉 Setup complete!"
echo ""
echo "📝 Next steps:"
echo "1. Edit .env file and add your Discord bot token"
echo "2. Run the bot with: ./run.sh"
echo ""
echo "💡 For development, you can also run: python3 bot.py"
echo "💡 To run tests: pytest --cov=. --cov-report=html"