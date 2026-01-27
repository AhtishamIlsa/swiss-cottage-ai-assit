#!/bin/bash
# Simple script to run the RAG chatbot with FAQ knowledge base

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== RAG Chatbot Startup Script ==="
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
    echo "   pip3 install streamlit"
    exit 1
fi

# Check if llama-cpp-python is available
if ! python3 -c "from llama_cpp import Llama" 2>/dev/null; then
    echo "⚠️  llama-cpp-python is not installed"
    echo ""
    echo "💡 To install all dependencies, run:"
    echo "   ./install_dependencies.sh"
    exit 1
fi

# Kill any existing Streamlit processes to avoid conflicts
echo "Checking for existing processes..."
if pgrep -f "streamlit.*rag_chatbot" > /dev/null; then
    echo "⚠️  Found existing Streamlit processes. Killing them..."
    pkill -f "streamlit.*rag_chatbot" 2>/dev/null || true
    sleep 2
    echo "✓ Cleaned up existing processes"
fi

# Check if vector store exists
VECTOR_STORE="vector_store"
if [ ! -d "$VECTOR_STORE" ]; then
    echo "⚠️  Vector store not found: $VECTOR_STORE"
    echo "💡 Please build the vector index first:"
    echo "   python chatbot/pdf_faq_extractor.py --pdf 'Swiss Cottages FAQS - Google Sheets.pdf' --output docs/faq"
    exit 1
fi

# Default parameters
MODEL="${1:-llama-3.1}"
K="${2:-5}"
STRATEGY="${3:-create-and-refine}"  # Changed from async-tree-summarization (too slow)
MAX_TOKENS="${4:-512}"

# Load environment variables from .env file if it exists
if [ -f .env ]; then
    echo "📝 Loading environment variables from .env file..."
    set -a  # automatically export all variables
    source .env
    set +a
fi

# Groq API Key (from .env file or environment variable)
if [ -z "$GROQ_API_KEY" ]; then
    echo "⚠️  WARNING: GROQ_API_KEY not set!"
    echo "   Please create a .env file with: GROQ_API_KEY=your-api-key"
    echo "   Or copy .env.example to .env and add your API key"
    echo "   Or set it with: export GROQ_API_KEY='your-api-key'"
    exit 1
fi
export GROQ_API_KEY

echo "🚀 Starting RAG Chatbot with:"
echo "   Model: $MODEL"
echo "   Retrieval count (k): $K"
echo "   Synthesis strategy: $STRATEGY"
echo "   Max tokens: $MAX_TOKENS"
echo "   Using: Groq API (fast mode) ⚡"
echo ""
echo "⏳ Starting application..."
echo "   - Using Groq API - no model loading needed! ⚡"
echo "   - The browser will open automatically when ready"
echo "   - Look for 'You can now view your Streamlit app' message"
echo "   - Press Ctrl+C to stop"
echo ""

# Use system Python's streamlit to match the ChromaDB version used to build the vector store
# This ensures version compatibility
PYTHON3_STREAMLIT=$(python3 -c "import streamlit; import sys; print(sys.executable)" 2>/dev/null || echo "python3")
echo "Using: $PYTHON3_STREAMLIT"

# Run the RAG chatbot
$PYTHON3_STREAMLIT -m streamlit run chatbot/rag_chatbot_app.py -- --model "$MODEL" --k "$K" --synthesis-strategy "$STRATEGY" --max-new-tokens "$MAX_TOKENS"
