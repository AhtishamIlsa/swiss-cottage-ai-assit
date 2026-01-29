#!/bin/bash
# Startup script for FastAPI chatbot server

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== FastAPI Chatbot Server Startup ==="
echo ""

# Load .env file if it exists
if [ -f .env ]; then
    echo "📝 Loading environment variables from .env file..."
    set -a  # automatically export all variables
    source .env
    set +a
fi

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed or not in PATH"
    exit 1
fi

# Check if Poetry is available and use it if possible
if command -v poetry &> /dev/null; then
    # Check if required packages are installed in Poetry environment
    if ! poetry run python3 -c "import fastapi" 2>/dev/null; then
        echo "⚠️  FastAPI is not installed in Poetry environment"
        echo "💡 Please install dependencies first:"
        echo "   poetry install"
        exit 1
    fi
    PYTHON_CMD="poetry run python3"
else
    # Fallback to system Python
if ! python3 -c "import fastapi" 2>/dev/null; then
    echo "⚠️  FastAPI is not installed"
    echo "💡 Please install dependencies first:"
    echo "   poetry install"
    echo "   or"
    echo "   pip install fastapi uvicorn pydantic"
    exit 1
    fi
    PYTHON_CMD="python3"
fi

# Set defaults
API_HOST="${API_HOST:-0.0.0.0}"
API_PORT="${API_PORT:-8000}"

echo "🚀 Starting FastAPI server..."
echo "   Host: $API_HOST"
echo "   Port: $API_PORT"
echo "   API URL: http://$API_HOST:$API_PORT"
echo "   Docs: http://$API_HOST:$API_PORT/docs"
echo ""
echo "⏳ Starting server..."
echo "   Press Ctrl+C to stop"
echo ""

# Run FastAPI with uvicorn
$PYTHON_CMD -m uvicorn chatbot.api.main:app \
    --host "$API_HOST" \
    --port "$API_PORT" \
    --reload
