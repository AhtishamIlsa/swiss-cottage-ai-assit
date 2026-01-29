"""FastAPI dependencies for chatbot components."""

import os
import sys
from pathlib import Path
from functools import lru_cache
from typing import Optional

# Add chatbot directory to path
chatbot_dir = Path(__file__).parent.parent
if str(chatbot_dir) not in sys.path:
    sys.path.insert(0, str(chatbot_dir))

from bot.client.groq_client import GroqClient
# Lazy import for LamaCppClient to avoid requiring llama_cpp module
try:
    from bot.client.lama_cpp_client import LamaCppClient
except ImportError:
    # llama_cpp not installed - will use Groq only
    LamaCppClient = None

from bot.conversation.intent_router import IntentRouter
from bot.conversation.ctx_strategy import (
    BaseSynthesisStrategy,
    get_ctx_synthesis_strategy as get_ctx_synthesis_strategy_original,
)
from bot.memory.embedder import Embedder
from bot.memory.vector_database.chroma import Chroma
from bot.model.model_registry import get_model_settings, get_models
from helpers.log import get_logger

logger = get_logger(__name__)

# Cache for initialized components
_llm_client: Optional[GroqClient] = None  # Type hint simplified since LamaCppClient may not be available
_vector_store: Optional[Chroma] = None
_intent_router: Optional[IntentRouter] = None
_ctx_synthesis_strategy: Optional[BaseSynthesisStrategy] = None


def clear_vector_store_cache():
    """Clear the cached vector store instance (useful after rebuilding)."""
    global _vector_store
    _vector_store = None
    logger.info("Vector store cache cleared")


def clear_vector_store_cache():
    """Clear the cached vector store instance (useful after rebuilding)."""
    global _vector_store
    _vector_store = None
    logger.info("Vector store cache cleared")


def get_root_folder() -> Path:
    """Get the root folder of the project."""
    return Path(__file__).resolve().parent.parent.parent


def is_query_optimization_enabled() -> bool:
    """
    Check if query optimization is enabled via environment variable.
    
    Returns:
        bool: True if query optimization is enabled (default: True)
    """
    return os.getenv("ENABLE_QUERY_OPTIMIZATION", "true").lower() == "true"


def get_model_folder() -> Path:
    """Get the model folder path."""
    return get_root_folder() / "models"


def get_vector_store_path() -> Path:
    """Get the vector store path."""
    root_folder = get_root_folder()
    faq_vector_store = root_folder / "vector_store"
    docs_index_vector_store = root_folder / "vector_store" / "docs_index"
    
    if (faq_vector_store / "chroma.sqlite3").exists():
        return faq_vector_store
    elif (docs_index_vector_store / "chroma.sqlite3").exists():
        return docs_index_vector_store
    else:
        raise FileNotFoundError(
            "Vector store not found! Please build the vector index first: "
            "python chatbot/pdf_faq_extractor.py --pdf 'Swiss Cottages FAQS - Google Sheets.pdf' --output docs/faq"
        )


def get_llm_client(
    model_name: str = "llama-3.1",
    use_groq: bool = True,
) -> GroqClient:  # Return type simplified - will always use Groq if llama_cpp not available
    """
    Get or initialize LLM client (cached).
    
    Args:
        model_name: Model name to use
        use_groq: Whether to use Groq API (default: True)
        
    Returns:
        LLM client instance
    """
    global _llm_client
    
    if _llm_client is None:
        model_folder = get_model_folder()
        groq_api_key = os.getenv("GROQ_API_KEY")
        
        if use_groq:
            try:
                model_settings = get_model_settings(model_name)
                _llm_client = GroqClient(
                    api_key=groq_api_key,
                    model_name="llama-3.1-8b-instant",
                    model_settings=model_settings
                )
                logger.info("✅ Using Groq API (fast mode)")
            except Exception as e:
                logger.warning(f"Failed to initialize Groq client: {e}. Falling back to local model.")
                use_groq = False
        
        if not use_groq:
            if LamaCppClient is None:
                logger.error("llama_cpp module not installed. Cannot use local model. Falling back to Groq.")
                # Fallback to Groq if llama_cpp not available
                model_settings = get_model_settings(model_name)
                _llm_client = GroqClient(
                    api_key=groq_api_key,
                    model_name="llama-3.1-8b-instant",
                    model_settings=model_settings
                )
                logger.info("✅ Using Groq API (fallback - llama_cpp not available)")
            else:
                model_settings = get_model_settings(model_name)
                _llm_client = LamaCppClient(model_folder=model_folder, model_settings=model_settings)
                logger.info("✅ Using local model (llama.cpp)")
    
    return _llm_client


def get_vector_store(force_reload: bool = False) -> Chroma:
    """
    Get or initialize vector store (cached).
    
    Args:
        force_reload: If True, force reload even if cached
    
    Returns:
        Chroma vector store instance
    """
    global _vector_store
    
    if _vector_store is None or force_reload:
        if force_reload:
            _vector_store = None
        vector_store_path = get_vector_store_path()
        embedding = Embedder()
        
        try:
            _vector_store = Chroma(persist_directory=str(vector_store_path), embedding=embedding)
            doc_count = _vector_store.collection.count()
            logger.info(f"Successfully loaded vector store with {doc_count} documents")
        except Exception as e:
            error_msg = str(e).lower()
            logger.error(f"Error loading vector store: {e}")
            if "no such column" in error_msg or "topic" in error_msg or "operationalerror" in error_msg:
                logger.error("ChromaDB schema mismatch detected! Attempting to clear cache and reload...")
                # Clear cache and try once more
                _vector_store = None
                try:
                    _vector_store = Chroma(persist_directory=str(vector_store_path), embedding=embedding)
                    doc_count = _vector_store.collection.count()
                    logger.info(f"Successfully reloaded vector store with {doc_count} documents after cache clear")
                except Exception as e2:
                    logger.error(f"Failed to reload vector store: {e2}")
                    raise RuntimeError(
                        "Vector store schema error detected. Please rebuild the vector index: "
                        "python3 chatbot/memory_builder.py --chunk-size 512 --chunk-overlap 25"
                    )
            else:
                raise
    
    return _vector_store


def get_intent_router() -> IntentRouter:
    """
    Get or initialize intent router (cached).
    
    Returns:
        IntentRouter instance
    """
    global _intent_router
    
    if _intent_router is None:
        llm = get_llm_client()
        _intent_router = IntentRouter(llm=llm, use_llm_fallback=True)
        logger.info("✅ Intent router initialized")
    
    return _intent_router


def get_ctx_synthesis_strategy(
    strategy_name: str = "create-and-refine",
) -> BaseSynthesisStrategy:
    """
    Get or initialize context synthesis strategy (cached).
    
    Args:
        strategy_name: Name of the synthesis strategy
        
    Returns:
        BaseSynthesisStrategy instance
    """
    global _ctx_synthesis_strategy
    
    if _ctx_synthesis_strategy is None:
        llm = get_llm_client()
        _ctx_synthesis_strategy = get_ctx_synthesis_strategy_original(strategy_name, llm=llm)
        logger.info(f"✅ Context synthesis strategy '{strategy_name}' initialized")
    
    return _ctx_synthesis_strategy
