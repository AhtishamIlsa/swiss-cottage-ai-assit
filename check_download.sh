#!/bin/bash
# Script to check model download status

MODEL_FILE="models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"
EXPECTED_SIZE_URL="https://huggingface.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF/resolve/main/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"

echo "=== Model Download Status Check ==="
echo ""

if [ -f "$MODEL_FILE" ]; then
    CURRENT_SIZE=$(stat -f%z "$MODEL_FILE" 2>/dev/null || stat -c%s "$MODEL_FILE" 2>/dev/null)
    CURRENT_SIZE_GB=$(echo "scale=2; $CURRENT_SIZE / 1024 / 1024 / 1024" | bc)
    FILE_TIME=$(stat -f%Sm "$MODEL_FILE" 2>/dev/null || stat -c%y "$MODEL_FILE" 2>/dev/null)
    
    echo "✅ Model file exists: $MODEL_FILE"
    echo "📦 Current size: ${CURRENT_SIZE_GB} GB ($(numfmt --to=iec-i --suffix=B $CURRENT_SIZE))"
    echo "🕒 Last modified: $FILE_TIME"
    echo ""
    
    # Try to get expected size from URL
    EXPECTED_SIZE=$(curl -sI "$EXPECTED_SIZE_URL" 2>/dev/null | grep -i "content-length" | awk '{print $2}' | tr -d '\r\n')
    
    if [ ! -z "$EXPECTED_SIZE" ] && [ "$EXPECTED_SIZE" != "0" ]; then
        EXPECTED_SIZE_GB=$(echo "scale=2; $EXPECTED_SIZE / 1024 / 1024 / 1024" | bc)
        PERCENTAGE=$(echo "scale=1; $CURRENT_SIZE * 100 / $EXPECTED_SIZE" | bc)
        
        echo "📊 Expected size: ${EXPECTED_SIZE_GB} GB ($(numfmt --to=iec-i --suffix=B $EXPECTED_SIZE))"
        echo "📈 Download progress: ${PERCENTAGE}%"
        echo ""
        
        if [ "$CURRENT_SIZE" -ge "$EXPECTED_SIZE" ]; then
            echo "✅ Download appears COMPLETE!"
        else
            echo "⏳ Download is IN PROGRESS..."
        fi
    else
        echo "⚠️  Could not determine expected file size from server"
        echo "💡 Typical size for this model: ~4.8-5.0 GB"
        if (( $(echo "$CURRENT_SIZE_GB < 4.0" | bc -l) )); then
            echo "⏳ File size seems small - download may still be in progress"
        else
            echo "✅ File size looks reasonable - download likely complete"
        fi
    fi
else
    echo "❌ Model file not found: $MODEL_FILE"
    echo "⏳ Download has not started yet"
fi

echo ""
echo "=== Streamlit Process Status ==="
if pgrep -f "streamlit.*chatbot_app.py" > /dev/null; then
    echo "✅ Streamlit is running"
    ps aux | grep "streamlit.*chatbot_app.py" | grep -v grep | awk '{print "   PID: " $2 ", CPU: " $3 "%, Memory: " $4 "%"}'
else
    echo "❌ Streamlit is not running"
fi
