#!/bin/bash

cd "$(dirname "$0")"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo "🎨 Starting AI Art Gallery Services..."

# Start Ollama
echo "1. Starting Ollama..."
ollama serve > logs/ollama.log 2>&1 &
OLLAMA_PID=$!
sleep 5

# Pull model if needed
ollama pull gemma:2b > logs/model_pull.log 2>&1 &

# Start Flask server
echo "2. Starting Flask server..."
source venv/bin/activate
python3 server.py > logs/flask.log 2>&1 &
FLASK_PID=$!
sleep 3

# Check services
echo ""
echo "📊 Service Status:"
echo "-----------------"

if curl -s http://localhost:11434/api/tags > /dev/null; then
    echo -e "${GREEN}✅ Ollama is running${NC}"
else
    echo -e "${RED}❌ Ollama is not responding${NC}"
fi

if curl -s http://localhost:5000/api/health > /dev/null; then
    echo -e "${GREEN}✅ Flask server is running${NC}"
    
    # Get stats
    STATS=$(curl -s http://localhost:5000/api/health)
    ARTWORKS=$(echo $STATS | grep -o '"artworks":[0-9]*' | cut -d: -f2)
    echo "   Artworks loaded: $ARTWORKS"
else
    echo -e "${RED}❌ Flask server is not responding${NC}"
fi

echo ""
echo "🌐 URLs:"
echo "   Main Interface: http://localhost:5000"
echo "   Analytics Dashboard: http://localhost:5000/analytics"
echo ""
echo "🛑 To stop: pkill -f \"ollama serve\" && pkill -f \"python3 server.py\""
