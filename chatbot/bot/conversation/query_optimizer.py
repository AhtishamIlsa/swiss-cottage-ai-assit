"""Query optimization for RAG retrieval."""

import time
from typing import Any, TYPE_CHECKING, Union

from helpers.log import get_logger

if TYPE_CHECKING:
    from bot.client.lama_cpp_client import LamaCppClient
    from bot.client.groq_client import GroqClient

logger = get_logger(__name__)


def optimize_query_for_rag(
    llm: Union["LamaCppClient", "GroqClient", Any],
    query: str,
    max_new_tokens: int = 128,
    timeout_seconds: float = 2.0
) -> str:
    """
    Optimize user query for better RAG retrieval.
    
    This function enhances queries by:
    - Disambiguating numbers (e.g., "4 people" vs "cottage 4")
    - Expanding domain terms (e.g., "price" → "pricing rates weekday weekend")
    - Adding relevant keywords for better semantic matching
    - Preserving core intent while enhancing searchability
    
    Args:
        llm: The language model client for query optimization.
        query: The original query to optimize.
        max_new_tokens: Maximum tokens for optimization response (default: 128).
        timeout_seconds: Maximum time to wait for optimization (default: 2.0 seconds).
        
    Returns:
        str: The optimized query, or original query if optimization fails.
    """
    if not query or not query.strip():
        logger.warning("Empty query provided, returning as-is")
        return query
    
    try:
        start_time = time.time()
        
        # Generate optimization prompt
        from bot.client.prompt import QUERY_OPTIMIZATION_PROMPT_TEMPLATE
        optimization_prompt = QUERY_OPTIMIZATION_PROMPT_TEMPLATE.format(query=query)
        
        logger.debug(f"Optimizing query: '{query}'")
        
        # Generate optimized query
        optimized_query = llm.generate_answer(optimization_prompt, max_new_tokens=max_new_tokens)
        
        # Check timeout
        elapsed_time = time.time() - start_time
        if elapsed_time > timeout_seconds:
            logger.warning(f"Query optimization took {elapsed_time:.2f}s (exceeded {timeout_seconds}s), using original query")
            return query
        
        # Clean up the response
        optimized_query = optimized_query.strip()
        
        # Remove common prefixes that LLM might add
        prefixes_to_remove = [
            "optimized query:",
            "optimized:",
            "rewritten query:",
            "rewritten:",
            "query:",
        ]
        for prefix in prefixes_to_remove:
            if optimized_query.lower().startswith(prefix):
                optimized_query = optimized_query[len(prefix):].strip()
        
        # Validate optimized query
        if not optimized_query or len(optimized_query) < 3:
            logger.warning(f"Optimized query is too short or empty, using original query")
            return query
        
        # If optimized query is too different (more than 3x length), it might be wrong
        if len(optimized_query) > len(query) * 3:
            logger.warning(f"Optimized query is suspiciously long ({len(optimized_query)} vs {len(query)}), using original query")
            return query
        
        logger.info(f"Query optimized successfully: '{query}' → '{optimized_query}' (took {elapsed_time:.2f}s)")
        return optimized_query
        
    except Exception as e:
        logger.error(f"Error optimizing query '{query}': {e}", exc_info=True)
        logger.info("Falling back to original query")
        return query
