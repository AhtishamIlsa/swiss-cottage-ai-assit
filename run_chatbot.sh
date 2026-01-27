#!/bin/bash
# Simple script to run the chatbot

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Chatbot Startup Script ==="
echo ""

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed or not in PATH"
    exit 1
fi

# Check if Streamlit is available
if ! python3 -c "import streamlit" 2>/dev/null; then
    echo "❌ Streamlit is not installed"
    echo "💡 Please install dependencies first:"
    echo "   poetry install"
    echo "   or"
    echo "   pip install streamlit"
    exit 1
fi

# Check if llama-cpp-python is available
if ! python3 -c "from llama_cpp import Llama" 2>/dev/null; then
    echo "⚠️  llama-cpp-python is not installed"
    echo ""
    echo "💡 To install all dependencies, run:"
    echo "   ./install_dependencies.sh"
    echo ""
    echo "💡 Or install manually:"
    echo "   # Install build dependencies first:"
    echo "   sudo apt-get install -y build-essential cmake ninja-build python3-dev"
    echo "   # Then install llama-cpp-python:"
    echo "   pip3 install --user llama-cpp-python"
    exit 1
fi

# Check if model exists
MODEL_FILE="models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"
if [ ! -f "$MODEL_FILE" ]; then
    echo "⚠️  Model file not found: $MODEL_FILE"
    echo "💡 The model will be downloaded automatically when you start the chatbot"
    echo "   (This may take a while as the file is ~4-5 GB)"
    echo ""
fi

# Default model
MODEL="${1:-llama-3.1}"
MAX_TOKENS="${2:-512}"

echo "🚀 Starting chatbot with:"
echo "   Model: $MODEL"
echo "   Max tokens: $MAX_TOKENS"
echo ""
echo "📝 The chatbot will open in your browser"
echo "   Press Ctrl+C to stop"
echo ""

# Run the chatbot
streamlit run chatbot/chatbot_app.py -- --model "$MODEL" --max-new-tokens "$MAX_TOKENS"
