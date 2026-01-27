#!/bin/bash
# Simple script to check model download status

MODEL_FILE="models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"

echo "=== Model Download Status ==="
echo ""

if [ -f "$MODEL_FILE" ]; then
    # Get file size in bytes
    CURRENT_SIZE=$(stat -c%s "$MODEL_FILE" 2>/dev/null || stat -f%z "$MODEL_FILE" 2>/dev/null)
    CURRENT_SIZE_GB=$(awk "BEGIN {printf \"%.2f\", $CURRENT_SIZE / 1024 / 1024 / 1024}")
    CURRENT_SIZE_MB=$(awk "BEGIN {printf \"%.0f\", $CURRENT_SIZE / 1024 / 1024}")
    FILE_TIME=$(stat -c%y "$MODEL_FILE" 2>/dev/null | cut -d'.' -f1)
    
    echo "✅ File: $MODEL_FILE"
    echo "📦 Size: ${CURRENT_SIZE_GB} GB (${CURRENT_SIZE_MB} MB)"
    echo "🕒 Last modified: $FILE_TIME"
    echo ""
    
    # Check if file is still being written (size changing)
    echo "Checking if download is still active..."
    sleep 2
    NEW_SIZE=$(stat -c%s "$MODEL_FILE" 2>/dev/null || stat -f%z "$MODEL_FILE" 2>/dev/null)
    
    if [ "$CURRENT_SIZE" != "$NEW_SIZE" ]; then
        NEW_SIZE_GB=$(awk "BEGIN {printf \"%.2f\", $NEW_SIZE / 1024 / 1024 / 1024}")
        echo "⏳ DOWNLOAD IN PROGRESS"
        echo "   Size changed from ${CURRENT_SIZE_GB} GB to ${NEW_SIZE_GB} GB"
        echo "   File is still being downloaded..."
    else
        echo "✅ Download appears COMPLETE"
        echo "   File size is stable (not changing)"
        echo ""
        echo "💡 For Llama 3.1 8B Q4_K_M, expected size is typically:"
        echo "   - Around 4.8-5.0 GB for complete download"
        if (( $(echo "$CURRENT_SIZE_GB < 2.0" | bc -l) )); then
            echo "   ⚠️  Current file seems too small - check your download"
        fi
    fi
else
    echo "❌ Model file not found!"
    echo "   Location: $MODEL_FILE"
    echo "   Download has not started yet"
fi

echo ""
echo "=== Quick Access ==="
echo "📱 Streamlit URL: http://localhost:8501"
echo "   (or http://YOUR_SERVER_IP:8501)"
