"""
Streamlit Cloud entry point for RAG Chatbot.
This file is used by Streamlit Community Cloud to run the app.
"""
import sys
from pathlib import Path

# Add chatbot directory to path
chatbot_dir = Path(__file__).parent / "chatbot"
if str(chatbot_dir) not in sys.path:
    sys.path.insert(0, str(chatbot_dir))

# Import and run the main Streamlit app
from rag_chatbot_app import main, get_args
import argparse

# Create default arguments for Streamlit Cloud
# (Streamlit Cloud doesn't support command-line arguments)
default_args = argparse.Namespace(
    model="llama-3.1-8b-instant",
    synthesis_strategy="create-and-refine",
    k=2,
    max_new_tokens=512,
    groq_api_key=None  # Will use GROQ_API_KEY from environment
)

# Run the main function
if __name__ == "__main__":
    main(default_args)
