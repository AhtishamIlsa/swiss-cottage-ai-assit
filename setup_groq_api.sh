#!/bin/bash
# Helper script to set up Groq API key
# Usage: ./setup_groq_api.sh YOUR_API_KEY

if [ -z "$1" ]; then
    echo "❌ Error: API key required!"
    echo "Usage: ./setup_groq_api.sh YOUR_API_KEY"
    echo ""
    echo "This will create/update the .env file with your API key."
    exit 1
fi

API_KEY="$1"

echo "Setting up Groq API key..."

# Create or update .env file
if [ -f .env ]; then
    # Update existing .env file
    if grep -q "^GROQ_API_KEY=" .env; then
        # Replace existing key
        sed -i "s|^GROQ_API_KEY=.*|GROQ_API_KEY=$API_KEY|" .env
        echo "✅ Updated GROQ_API_KEY in .env file"
    else
        # Add new key
        echo "GROQ_API_KEY=$API_KEY" >> .env
        echo "✅ Added GROQ_API_KEY to .env file"
    fi
else
    # Create new .env file
    cat > .env << EOF
# Groq API Key
GROQ_API_KEY=$API_KEY
EOF
    echo "✅ Created .env file with GROQ_API_KEY"
fi

# Also set for current session
export GROQ_API_KEY="$API_KEY"

echo ""
echo "✅ Groq API key is now set in .env file!"
echo ""
echo "The .env file will be automatically loaded by run_rag_chatbot.sh"
echo ""
echo "To use in current session, run:"
echo "  source .env"
echo ""
echo "Or just run:"
echo "  ./run_rag_chatbot.sh"
