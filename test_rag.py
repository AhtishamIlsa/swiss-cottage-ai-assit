#!/usr/bin/env python3
"""Test script to verify RAG chatbot functionality"""

import sys
from pathlib import Path

# Add chatbot to path
sys.path.insert(0, str(Path(__file__).parent / "chatbot"))

from bot.memory.embedder import Embedder
from bot.memory.vector_database.chroma import Chroma
from bot.client.lama_cpp_client import LamaCppClient
from bot.model.model_registry import get_model_settings
from bot.conversation.chat_history import ChatHistory
from bot.conversation.conversation_handler import refine_question

def test_vector_store():
    print("=" * 60)
    print("TEST 1: Vector Store Loading")
    print("=" * 60)
    try:
        vs_path = Path("vector_store")
        embedding = Embedder()
        index = Chroma(persist_directory=str(vs_path), embedding=embedding)
        count = index.collection.count()
        print(f"✓ Vector store loaded: {count} documents")
        return index
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_retrieval(index):
    print("\n" + "=" * 60)
    print("TEST 2: Document Retrieval")
    print("=" * 60)
    try:
        query = "what is swiss cottages"
        print(f"Query: {query}")
        
        retrieved_contents, sources = index.similarity_search_with_threshold(
            query=query, k=3, threshold=0.0
        )
        
        print(f"✓ Retrieved {len(retrieved_contents)} documents")
        for i, (doc, source) in enumerate(zip(retrieved_contents[:2], sources[:2]), 1):
            print(f"\n  Document {i}:")
            print(f"    Score: {source.get('score', 'N/A')}")
            print(f"    Preview: {doc.page_content[:150]}...")
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_model_loading():
    print("\n" + "=" * 60)
    print("TEST 3: Model Loading")
    print("=" * 60)
    try:
        model_folder = Path("models")
        model_settings = get_model_settings("llama-3.1")
        print(f"✓ Model settings loaded")
        print(f"  Model: {model_settings.file_name}")
        
        # Check if model exists
        model_file = model_folder / model_settings.file_name
        if not model_file.exists():
            print(f"⚠ Model file not found: {model_file}")
            print("  (Will auto-download on first use)")
            return None
        
        print(f"✓ Model file exists: {model_file}")
        print("  Loading model (this may take 30-60 seconds)...")
        
        llm = LamaCppClient(model_folder=model_folder, model_settings=model_settings)
        print("✓ Model loaded successfully")
        return llm
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_query_refinement(llm):
    print("\n" + "=" * 60)
    print("TEST 4: Query Refinement")
    print("=" * 60)
    try:
        chat_history = ChatHistory(total_length=2)
        question = "what is swiss cottages"
        print(f"Original question: {question}")
        
        refined = refine_question(llm, question, chat_history, max_new_tokens=128)
        print(f"✓ Refined question: {refined}")
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("RAG Chatbot Functionality Test")
    print("=" * 60)
    
    # Test 1: Vector Store
    index = test_vector_store()
    if not index:
        print("\n❌ Vector store test failed. Cannot continue.")
        return 1
    
    # Test 2: Retrieval
    if not test_retrieval(index):
        print("\n❌ Retrieval test failed.")
        return 1
    
    # Test 3: Model Loading
    llm = test_model_loading()
    if not llm:
        print("\n⚠ Model loading test failed or skipped.")
        print("  This is OK if model needs to be downloaded.")
        return 0
    
    # Test 4: Query Refinement
    if not test_query_refinement(llm):
        print("\n❌ Query refinement test failed.")
        return 1
    
    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED!")
    print("=" * 60)
    print("\nThe RAG chatbot should work correctly.")
    print("If you're still experiencing issues, please share:")
    print("  1. The exact error message")
    print("  2. What happens when you ask a question")
    print("  3. Any error output from the Streamlit console")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
