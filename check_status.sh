#!/bin/bash
# Quick status check for all services

echo "=== Service Status Check ==="
echo ""

# Check FastAPI
echo "📋 FastAPI (port 8000):"
if curl -s http://127.0.0.1:8000/api/health > /dev/null 2>&1; then
    echo "   ✅ Running"
    curl -s http://127.0.0.1:8000/api/health | python3 -m json.tool 2>/dev/null || echo "   Response: $(curl -s http://127.0.0.1:8000/api/health)"
else
    echo "   ❌ Not responding"
fi
echo ""

# Check Streamlit
echo "📋 Streamlit (port 8501):"
if curl -s http://127.0.0.1:8501/ > /dev/null 2>&1; then
    echo "   ✅ Running"
else
    echo "   ❌ Not responding"
fi
echo ""

# Check Nginx
echo "📋 Nginx:"
if systemctl is-active --quiet nginx; then
    echo "   ✅ Running"
else
    echo "   ❌ Not running"
fi
echo ""

# Check HTTPS
echo "📋 HTTPS Site:"
if curl -s -k https://swisscottaggesai.ilsainteractive.com.pk/ > /dev/null 2>&1; then
    echo "   ✅ Accessible"
else
    echo "   ❌ Not accessible"
fi
echo ""

# Check processes
echo "📋 Running Processes:"
ps aux | grep -E "(uvicorn|streamlit)" | grep -v grep | awk '{print "   PID:", $2, "-", $11, $12, $13, $14}'
echo ""
