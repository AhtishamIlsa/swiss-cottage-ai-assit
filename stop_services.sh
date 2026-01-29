#!/bin/bash
# Stop FastAPI and Streamlit services

set -e

echo "=== Stopping Swiss Cottage AI Services ==="
echo ""

# Stop FastAPI
echo "🛑 Stopping FastAPI..."
pkill -f "uvicorn.*chatbot.api.main" || echo "   No FastAPI process found"
sleep 2

# Stop Streamlit
echo "🛑 Stopping Streamlit..."
pkill -f "streamlit.*rag_chatbot" || echo "   No Streamlit process found"
sleep 2

# Verify ports are free
if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1 || netstat -tuln 2>/dev/null | grep -q ":8000 " || ss -tuln 2>/dev/null | grep -q ":8000 "; then
    echo "⚠️  Port 8000 is still in use"
else
    echo "✅ Port 8000 is free"
fi

if lsof -Pi :8501 -sTCP:LISTEN -t >/dev/null 2>&1 || netstat -tuln 2>/dev/null | grep -q ":8501 " || ss -tuln 2>/dev/null | grep -q ":8501 "; then
    echo "⚠️  Port 8501 is still in use"
else
    echo "✅ Port 8501 is free"
fi

echo ""
echo "✅ Services stopped"
echo ""
