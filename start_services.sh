#!/bin/bash
# Start FastAPI and Streamlit services

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Starting Swiss Cottage AI Services ==="
echo ""

# Check if Poetry is available
if ! command -v poetry &> /dev/null; then
    echo "❌ Poetry is not installed or not in PATH"
    exit 1
fi

# Load .env file
if [ -f .env ]; then
    echo "📝 Loading environment variables from .env file..."
    set -a
    source .env
    set +a
fi

# Check if ports are already in use
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1 || netstat -tuln 2>/dev/null | grep -q ":$port " || ss -tuln 2>/dev/null | grep -q ":$port "; then
        return 0  # Port is in use
    else
        return 1  # Port is free
    fi
}

# Start FastAPI if not running
if check_port 8000; then
    echo "⚠️  Port 8000 is already in use (FastAPI might be running)"
else
    echo "🚀 Starting FastAPI server on port 8000..."
    nohup poetry run python3 -m uvicorn chatbot.api.main:app --host 0.0.0.0 --port 8000 > /tmp/fastapi.log 2>&1 &
    FASTAPI_PID=$!
    echo "   FastAPI started (PID: $FASTAPI_PID)"
    echo "   Logs: /tmp/fastapi.log"
    
    # Wait longer for FastAPI to fully initialize (models, vector store, etc.)
    echo "   ⏳ Waiting for FastAPI to initialize..."
    sleep 8
    
    # Verify it started - check both port and HTTP response
    if check_port 8000; then
        # Also check if it responds to HTTP requests
        if curl -s http://localhost:8000/docs > /dev/null 2>&1; then
            echo "   ✅ FastAPI is running and responding"
        else
            echo "   ⚠️  FastAPI port is open but not responding yet (may still be initializing)"
            echo "   💡 Check logs: tail -f /tmp/fastapi.log"
        fi
    else
        echo "   ❌ FastAPI failed to start. Check logs: /tmp/fastapi.log"
        tail -20 /tmp/fastapi.log
    fi
fi

# Start Streamlit if not running
if check_port 8501; then
    echo "⚠️  Port 8501 is already in use (Streamlit might be running)"
else
    echo "🚀 Starting Streamlit app on port 8501..."
    nohup poetry run streamlit run chatbot/rag_chatbot_app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true > /tmp/streamlit.log 2>&1 &
    STREAMLIT_PID=$!
    echo "   Streamlit started (PID: $STREAMLIT_PID)"
    echo "   Logs: /tmp/streamlit.log"
    sleep 5
    
    # Verify it started
    if check_port 8501; then
        echo "   ✅ Streamlit is running"
    else
        echo "   ❌ Streamlit failed to start. Check logs: /tmp/streamlit.log"
        tail -20 /tmp/streamlit.log
    fi
fi

echo ""
echo "📋 Service Status:"
echo "   FastAPI:  http://127.0.0.1:8000 (PID: $FASTAPI_PID)"
echo "   Streamlit: http://127.0.0.1:8501 (PID: $STREAMLIT_PID)"
echo ""
echo "📝 To check logs:"
echo "   tail -f /tmp/fastapi.log"
echo "   tail -f /tmp/streamlit.log"
echo ""
echo "📝 To stop services:"
echo "   ./stop_services.sh"
echo ""
