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

# Removed: IntentRouter, ctx_strategy (simplified architecture)
# from bot.conversation.intent_router import IntentRouter
# from bot.conversation.ctx_strategy import (
#     BaseSynthesisStrategy,
#     get_ctx_synthesis_strategy as get_ctx_synthesis_strategy_original,
# )
from bot.conversation.tools import get_tools_config, get_tools_map
from bot.memory.embedder import Embedder
from bot.memory.vector_database.chroma import Chroma
from bot.model.model_registry import get_model_settings, get_models
from helpers.log import get_logger

logger = get_logger(__name__)

# Cache for initialized components
_llm_client: Optional[GroqClient] = None  # Type hint simplified since LamaCppClient may not be available
_fast_llm_client: Optional[GroqClient] = None  # Fast model for simple queries
_reasoning_llm_client: Optional[GroqClient] = None  # Reasoning model for complex queries
_vector_store: Optional[Chroma] = None
# Removed: _intent_router, _ctx_synthesis_strategy (simplified architecture)


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


def is_intent_filtering_enabled() -> bool:
    """
    Check if intent-based filtering is enabled via environment variable.
    
    This controls whether the new intent-based architecture is used:
    - Intent-based query optimization
    - Metadata filtering in vector retrieval
    - Intent-specific prompts
    
    Returns:
        bool: True if intent filtering is enabled (default: True)
    """
    return os.getenv("USE_INTENT_FILTERING", "true").lower() == "true"


def get_model_folder() -> Path:
    """Get the model folder path."""
    return get_root_folder() / "models"


def get_vector_store_path() -> Path:
    """Get the vector store path."""
    root_folder = get_root_folder()
    faq_vector_store = root_folder / "vector_store"
    docs_index_vector_store = root_folder / "vector_store" / "docs_index"
    
    # Check if vector store directory exists and has collections
    # ChromaDB may not always create chroma.sqlite3 immediately, so check directory existence
    if faq_vector_store.exists():
        # Check if it has any ChromaDB files or collections
        try:
            import chromadb
            client = chromadb.PersistentClient(path=str(faq_vector_store))
            collections = client.list_collections()
            if collections:
                return faq_vector_store
        except Exception:
            # If we can't check, but directory exists, assume it's valid
            if (faq_vector_store / "chroma.sqlite3").exists() or any(faq_vector_store.glob("*.sqlite*")):
                return faq_vector_store
            # If directory exists but no SQLite file, still return it (ChromaDB will create it)
            if faq_vector_store.is_dir():
                return faq_vector_store
    
    if docs_index_vector_store.exists():
        try:
            import chromadb
            client = chromadb.PersistentClient(path=str(docs_index_vector_store))
            collections = client.list_collections()
            if collections:
                return docs_index_vector_store
        except Exception:
            if (docs_index_vector_store / "chroma.sqlite3").exists() or any(docs_index_vector_store.glob("*.sqlite*")):
                return docs_index_vector_store
            if docs_index_vector_store.is_dir():
                return docs_index_vector_store
    
    # Default to faq_vector_store if directory exists
    if faq_vector_store.exists():
        return faq_vector_store
    
    raise FileNotFoundError(
        "Vector store not found! Please build the vector index first: "
        "python3 excel_faq_extractor.py --excel 'Swiss Cottages FAQS.xlsx' --output docs/faq"
    )


def get_llm_client(
    model_name: str = "llama-3.1",
    use_groq: bool = True,
) -> GroqClient:  # Return type simplified - will always use Groq if llama_cpp not available
    """
    Get or initialize LLM client (cached) - legacy function for backward compatibility.
    Returns fast model by default.
    
    Args:
        model_name: Model name to use
        use_groq: Whether to use Groq API (default: True)
        
    Returns:
        LLM client instance (fast model)
    """
    return get_fast_llm_client(model_name, use_groq)


def get_fast_llm_client(
    model_name: str = "llama-3.1",
    use_groq: bool = True,
) -> GroqClient:
    """
    Get or initialize fast LLM client for simple queries (cached).
    
    Args:
        model_name: Model name to use
        use_groq: Whether to use Groq API (default: True)
        
    Returns:
        Fast LLM client instance (llama-3.1-8b-instant)
    """
    global _fast_llm_client
    
    if _fast_llm_client is None:
        model_folder = get_model_folder()
        groq_api_key = os.getenv("GROQ_API_KEY")
        
        # Get fast model name from env var (default: llama-3.1-8b-instant)
        fast_model_name = os.getenv("FAST_MODEL_NAME", "llama-3.1-8b-instant")
        
        if use_groq:
            try:
                model_settings = get_model_settings(model_name)
                _fast_llm_client = GroqClient(
                    api_key=groq_api_key,
                    model_name=fast_model_name,
                    model_settings=model_settings
                )
                logger.info(f"✅ Fast LLM client initialized ({fast_model_name})")
            except Exception as e:
                logger.warning(f"Failed to initialize fast Groq client: {e}. Falling back to local model.")
                use_groq = False
        
        if not use_groq:
            if LamaCppClient is None:
                logger.error("llama_cpp module not installed. Cannot use local model. Falling back to Groq.")
                # Fallback to Groq if llama_cpp not available
                model_settings = get_model_settings(model_name)
                _fast_llm_client = GroqClient(
                    api_key=groq_api_key,
                    model_name=fast_model_name,
                    model_settings=model_settings
                )
                logger.info(f"✅ Fast LLM client initialized (fallback - {fast_model_name})")
            else:
                model_settings = get_model_settings(model_name)
                _fast_llm_client = LamaCppClient(model_folder=model_folder, model_settings=model_settings)
                logger.info("✅ Fast LLM client initialized (local model)")
    
    return _fast_llm_client


def get_reasoning_llm_client(
    model_name: str = "llama-3.1",
    use_groq: bool = True,
) -> GroqClient:
    """
    Get or initialize reasoning LLM client for complex queries (cached).
    
    Args:
        model_name: Model name to use
        use_groq: Whether to use Groq API (default: True)
        
    Returns:
        Reasoning LLM client instance (configurable via REASONING_MODEL_NAME env var)
    """
    global _reasoning_llm_client
    
    if _reasoning_llm_client is None:
        model_folder = get_model_folder()
        groq_api_key = os.getenv("GROQ_API_KEY")
        
        # Get reasoning model name from env var (default: llama-3.1-70b-versatile)
        reasoning_model_name = os.getenv("REASONING_MODEL_NAME", "llama-3.1-70b-versatile")
        
        if use_groq:
            try:
                # Determine model settings based on the actual model name
                # Extract base model name for settings lookup
                # Note: Groq uses full model IDs like "openai/gpt-oss-20b" - keep the full name
                if "gpt-oss" in reasoning_model_name.lower() or "openai/gpt-oss" in reasoning_model_name.lower():
                    # For GPT-OSS models, use llama settings as fallback (similar architecture)
                    settings_model_name = "llama-3.1"
                elif "llama" in reasoning_model_name.lower():
                    settings_model_name = "llama-3.1"
                elif "qwen" in reasoning_model_name.lower():
                    settings_model_name = "qwen-2.5:3b"
                else:
                    # Default to llama-3.1 settings for unknown models
                    settings_model_name = model_name
                
                logger.info(f"Initializing reasoning LLM client with model: {reasoning_model_name}, settings: {settings_model_name}")
                model_settings = get_model_settings(settings_model_name)
                _reasoning_llm_client = GroqClient(
                    api_key=groq_api_key,
                    model_name=reasoning_model_name,
                    model_settings=model_settings
                )
                logger.info(f"✅ Reasoning LLM client initialized ({reasoning_model_name}) with settings from {settings_model_name}")
            except Exception as e:
                logger.error(f"Failed to initialize reasoning Groq client with model '{reasoning_model_name}': {e}")
                logger.warning(f"Falling back to fast model.")
                # Fallback to fast model if reasoning model fails
                return get_fast_llm_client(model_name, use_groq)
        
        if not use_groq:
            if LamaCppClient is None:
                logger.error("llama_cpp module not installed. Cannot use local model. Falling back to Groq.")
                # Fallback to Groq if llama_cpp not available
                # Determine model settings based on the actual model name
                if "gpt-oss" in reasoning_model_name.lower() or "openai" in reasoning_model_name.lower():
                    settings_model_name = "llama-3.1"
                elif "llama" in reasoning_model_name.lower():
                    settings_model_name = "llama-3.1"
                elif "qwen" in reasoning_model_name.lower():
                    settings_model_name = "qwen-2.5:3b"
                else:
                    settings_model_name = model_name
                model_settings = get_model_settings(settings_model_name)
                _reasoning_llm_client = GroqClient(
                    api_key=groq_api_key,
                    model_name=reasoning_model_name,
                    model_settings=model_settings
                )
                logger.info(f"✅ Reasoning LLM client initialized (fallback - {reasoning_model_name})")
            else:
                model_settings = get_model_settings(model_name)
                _reasoning_llm_client = LamaCppClient(model_folder=model_folder, model_settings=model_settings)
                logger.info("✅ Reasoning LLM client initialized (local model)")
    
    return _reasoning_llm_client


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
        # Clear the global cache to force fresh load
        _vector_store = None
        vector_store_path = get_vector_store_path()
        embedding = Embedder()
        
        try:
            _vector_store = Chroma(persist_directory=str(vector_store_path), embedding=embedding)
            doc_count = _vector_store.collection.count()
            
            # If count is 0, try to verify if collection actually has data
            if doc_count == 0:
                try:
                    sample = _vector_store.collection.get(limit=1)
                    if sample.get('ids') and len(sample['ids']) > 0:
                        # Collection has data but count() returned 0
                        all_data = _vector_store.collection.get()
                        actual_count = len(all_data.get('ids', []))
                        logger.info(f"Successfully loaded vector store with {actual_count} documents (count() returned 0 but data exists)")
                    else:
                        logger.info(f"Successfully loaded vector store with {doc_count} documents")
                except Exception:
                    logger.info(f"Successfully loaded vector store with {doc_count} documents")
            else:
                logger.info(f"Successfully loaded vector store with {doc_count} documents")
        except RuntimeError as e:
            error_msg = str(e).lower()
            # Check if it's a schema error RuntimeError
            if "schema error" in error_msg or "rebuild" in error_msg:
                logger.error(f"ChromaDB schema error: {e}")
                # Don't try to access collection if there's a schema error - it will fail
                # Just raise the error and let the user rebuild
                raise
            else:
                raise
        except Exception as e:
            error_msg = str(e).lower()
            logger.error(f"Error loading vector store: {e}")
            if "no such column" in error_msg or "topic" in error_msg or "operationalerror" in error_msg:
                logger.error("ChromaDB schema mismatch detected! Attempting to delete corrupted database and reload...")
                # Delete the corrupted SQLite database file
                import os
                import shutil
                sqlite_file = vector_store_path / "chroma.sqlite3"
                if sqlite_file.exists():
                    logger.info(f"Deleting corrupted database file: {sqlite_file}")
                    try:
                        os.remove(sqlite_file)
                    except Exception as del_err:
                        logger.warning(f"Could not delete SQLite file: {del_err}")
                # Also try to remove the entire directory if it's corrupted
                try:
                    if vector_store_path.exists():
                        # Check if directory is empty or only has the SQLite file
                        remaining_files = list(vector_store_path.iterdir())
                        if len(remaining_files) == 0 or (len(remaining_files) == 1 and remaining_files[0].name == "chroma.sqlite3"):
                            logger.info(f"Removing corrupted vector store directory: {vector_store_path}")
                            shutil.rmtree(vector_store_path)
                except Exception as dir_err:
                    logger.warning(f"Could not remove vector store directory: {dir_err}")
                
                # Clear cache and try once more
                _vector_store = None
                try:
                    _vector_store = Chroma(persist_directory=str(vector_store_path), embedding=embedding)
                    doc_count = _vector_store.collection.count()
                    logger.info(f"Successfully reloaded vector store with {doc_count} documents after database cleanup")
                except Exception as e2:
                    logger.error(f"Failed to reload vector store: {e2}")
                    raise RuntimeError(
                        "Vector store schema error detected. Please rebuild the vector index: "
                        "python3 chatbot/memory_builder.py --chunk-size 512 --chunk-overlap 25"
                    )
            else:
                raise
    
    return _vector_store


# Removed: get_intent_router, get_ctx_synthesis_strategy (simplified architecture)


def get_tools_config_dependency() -> list:
    """Get tools configuration for LLM (dependency function)."""
    return get_tools_config()


def get_tools_map_dependency() -> dict:
    """Get tools function map (dependency function)."""
    return get_tools_map()
