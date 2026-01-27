#!/bin/bash
# Helper script to set up Groq API key
# Usage: ./setup_groq_api.sh YOUR_API_KEY

if [ -z "$1" ]; then
    echo "❌ Error: API key required!"
    echo "Usage: ./setup_groq_api.sh YOUR_API_KEY"
    echo "Or set environment variable: export GROQ_API_KEY='your-api-key'"
    exit 1
fi

API_KEY="$1"

echo "Setting up Groq API key..."
export GROQ_API_KEY="$API_KEY"

# Add to ~/.bashrc if not already present
if ! grep -q "GROQ_API_KEY" ~/.bashrc 2>/dev/null; then
    echo "" >> ~/.bashrc
    echo "# Groq API Key for RAG Chatbot" >> ~/.bashrc
    echo "export GROQ_API_KEY='$API_KEY'" >> ~/.bashrc
    echo "✅ Added GROQ_API_KEY to ~/.bashrc"
else
    echo "ℹ️  GROQ_API_KEY already exists in ~/.bashrc"
fi

echo ""
echo "✅ Groq API key is now set!"
echo ""
echo "Current session: export GROQ_API_KEY='$API_KEY'"
echo ""
echo "To use in current session, run:"
echo "  source ~/.bashrc"
echo ""
echo "Or run your app with:"
echo "  export GROQ_API_KEY='$API_KEY' && streamlit run chatbot/rag_chatbot_app.py"
