#!/usr/bin/env python3
"""Test script to verify Groq API connection."""

import os
import sys
from pathlib import Path

# Load .env file if it exists
def load_env_file():
    """Load environment variables from .env file."""
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key.strip()] = value.strip()

# Load .env file before importing other modules
load_env_file()

# Add chatbot to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "chatbot"))

from bot.client.groq_client import GroqClient
from bot.model.model_registry import get_model_settings

def test_groq_api():
    """Test Groq API connection."""
    print("=" * 60)
    print("Testing Groq API Connection")
    print("=" * 60)
    
    # Get API key from environment variable (loaded from .env or system env)
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("❌ Error: GROQ_API_KEY not set!")
        print("   Please create a .env file with: GROQ_API_KEY=your-api-key")
        print("   Or copy .env.example to .env and add your API key")
        print("   Or set it with: export GROQ_API_KEY='your-api-key'")
        print("   Or run: ./setup_groq_api.sh YOUR_API_KEY")
        sys.exit(1)
    else:
        env_source = "environment variable"
        if (Path(__file__).parent / ".env").exists():
            env_source = ".env file"
        print(f"✅ Using GROQ_API_KEY from {env_source}")
    
    print(f"API Key (first 20 chars): {api_key[:20]}...")
    print()
    
    try:
        # Initialize client
        print("1. Initializing Groq client...")
        model_settings = get_model_settings("llama-3.1")
        client = GroqClient(
            api_key=api_key,
            model_name="llama-3.1-8b-instant",
            model_settings=model_settings
        )
        print("   ✅ Groq client initialized successfully")
        print()
        
        # Test simple generation
        print("2. Testing API call with simple prompt...")
        test_prompt = "Say hello in one sentence."
        print(f"   Prompt: '{test_prompt}'")
        response = client.generate_answer(test_prompt, max_new_tokens=50)
        print(f"   ✅ API call successful!")
        print(f"   Response: {response}")
        print()
        
        # Test streaming
        print("3. Testing streaming...")
        print("   Streaming response: ", end="", flush=True)
        stream = client.start_answer_iterator_streamer("Count to 5", max_new_tokens=30)
        streamed_text = ""
        for token_dict in stream:
            token = client.parse_token(token_dict)
            streamed_text += token
            print(token, end="", flush=True)
        print()
        print(f"   ✅ Streaming successful!")
        print()
        
        print("=" * 60)
        print("✅ ALL TESTS PASSED - Groq API is working correctly!")
        print("=" * 60)
        return True
        
    except ValueError as e:
        print(f"❌ Configuration Error: {e}")
        print()
        print("💡 Solution:")
        print("   Set the GROQ_API_KEY environment variable:")
        print("   export GROQ_API_KEY='your-api-key-here'")
        return False
        
    except Exception as e:
        print(f"❌ API Error: {e}")
        print(f"   Error type: {type(e).__name__}")
        print()
        
        # Check for common errors
        error_str = str(e).lower()
        if "api key" in error_str or "authentication" in error_str or "401" in error_str:
            print("💡 This looks like an authentication error.")
            print("   - Check if your API key is valid")
            print("   - Get a new API key from: https://console.groq.com/keys")
        elif "rate limit" in error_str or "429" in error_str:
            print("💡 Rate limit exceeded. Wait a moment and try again.")
        elif "model" in error_str:
            print("💡 Model name might be incorrect. Using: llama-3.1-8b-instant")
        else:
            print("💡 Check your internet connection and API key validity")
        
        return False

if __name__ == "__main__":
    success = test_groq_api()
    sys.exit(0 if success else 1)
