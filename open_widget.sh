#!/bin/bash
# Script to start API server and open widget test page

echo "=== Starting FastAPI Server ==="
echo ""

# Check if server is already running
if curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
    echo "✅ API server is already running"
else
    echo "🚀 Starting API server in background..."
    ./run_api.sh > /tmp/fastapi.log 2>&1 &
    API_PID=$!
    echo "   Server PID: $API_PID"
    echo "   Waiting for server to start..."
    
    # Wait for server to be ready
    for i in {1..30}; do
        if curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
            echo "✅ Server is ready!"
            break
        fi
        sleep 1
    done
fi

echo ""
echo "=== Opening Widget Test Page ==="
echo ""
echo "The widget test page will open in your browser."
echo "Look for the chat button in the bottom-right corner!"
echo ""

# Open test page in browser
if command -v xdg-open > /dev/null; then
    xdg-open "file://$(pwd)/test_widget.html"
elif command -v open > /dev/null; then
    open "file://$(pwd)/test_widget.html"
else
    echo "Please open this file in your browser:"
    echo "  file://$(pwd)/test_widget.html"
    echo ""
    echo "Or visit: http://localhost:8000/static/ (if serving static files)"
fi

echo ""
echo "API Server URL: http://localhost:8000"
echo "API Docs: http://localhost:8000/docs"
echo ""
echo "To stop the server, press Ctrl+C or run: pkill -f uvicorn"
