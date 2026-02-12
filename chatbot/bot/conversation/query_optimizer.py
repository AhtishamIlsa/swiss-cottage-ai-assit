"""Query optimization for RAG retrieval."""

import re
import time
from typing import Any, TYPE_CHECKING, Union, Optional, Dict

from helpers.log import get_logger

if TYPE_CHECKING:
    from bot.client.lama_cpp_client import LamaCppClient
    from bot.client.groq_client import GroqClient
    from bot.conversation.intent_router import IntentType

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


def extract_entities_for_retrieval(query: str) -> Dict[str, Any]:
    """
    Extract entities from query for better retrieval filtering.
    
    Args:
        query: User query text
        
    Returns:
        Dictionary with extracted entities (cottage_id, dates, group_size)
    """
    entities = {
        "cottage_id": None,
        "dates": None,
        "group_size": None
    }
    
    query_lower = query.lower()
    
    # Extract cottage_id (7, 9, or 11)
    for num in [7, 9, 11]:
        if f"cottage {num}" in query_lower or f"cottage{num}" in query_lower:
            entities["cottage_id"] = num
            break
    
    # Extract group size (numbers with "people", "guests", "members", "persons")
    group_patterns = [
        r'(\d+)\s*(?:people|guests|members|persons|person)',
        r'(?:people|guests|members|persons|person)\s*(\d+)',
        r'(\d+)\s*(?:adults|adult)',
        r'(?:adults|adult)\s*(\d+)',
    ]
    for pattern in group_patterns:
        match = re.search(pattern, query_lower)
        if match:
            try:
                entities["group_size"] = int(match.group(1))
                break
            except (ValueError, IndexError):
                continue
    
    # Extract dates (basic patterns - can be enhanced)
    date_patterns = [
        r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}',  # MM/DD/YYYY or DD/MM/YYYY
        r'\d{4}[/-]\d{1,2}[/-]\d{1,2}',  # YYYY/MM/DD
        r'(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}',  # Month day
    ]
    for pattern in date_patterns:
        match = re.search(pattern, query_lower)
        if match:
            entities["dates"] = match.group(0)
            break
    
    return entities


def optimize_query_for_retrieval(
    query: str,
    intent: "IntentType",
    entities: Dict[str, Any],
    use_llm: bool = False,
    llm: Optional[Union["LamaCppClient", "GroqClient", Any]] = None,
    max_new_tokens: int = 128,
    timeout_seconds: float = 2.0
) -> str:
    """
    Optimize query for better vector retrieval using intent-based enhancement.
    
    Uses hybrid approach: rule-based first (always), LLM optimization optional.
    
    Args:
        query: Original query
        intent: Detected intent type
        entities: Extracted entities (cottage_id, dates, group_size)
        use_llm: Whether to use LLM for optimization (default: False)
        llm: LLM client (required if use_llm=True)
        max_new_tokens: Maximum tokens for LLM optimization
        timeout_seconds: Timeout for LLM optimization
        
    Returns:
        Optimized query string
    """
    if not query or not query.strip():
        return query
    
    # Stage 1: Rule-based intent-specific enhancement (always)
    enhanced_query = query
    
    # Add domain terms based on intent
    intent_terms = {
        "pricing": ["PKR", "weekday", "weekend", "per night", "rate", "cost", "pricing"],
        "availability": ["available", "booking", "vacancy", "dates", "availability"],
        "safety": ["security", "guards", "gated community", "safe", "safety"],
        "rooms": ["cottage", "bedroom", "property", "accommodation", "cottage type"],
        "facilities": ["facility", "amenity", "kitchen", "terrace", "amenities"],
        "location": ["location", "nearby", "attractions", "Bhurban", "Murree"],
        "booking": ["book", "booking", "reserve", "reservation"],
    }
    
    # Get intent string value
    intent_str = intent.value if hasattr(intent, 'value') else str(intent)
    
    if intent_str in intent_terms:
        # Add relevant domain terms to query
        terms = intent_terms[intent_str]
        # Only add terms that aren't already in the query
        query_lower = query.lower()
        missing_terms = [term for term in terms if term.lower() not in query_lower]
        if missing_terms:
            enhanced_query = f"{query} {' '.join(missing_terms[:3])}"  # Add up to 3 terms
    
    # Add extracted entities to query
    if entities.get("cottage_id"):
        cottage_term = f"cottage {entities['cottage_id']}"
        if cottage_term.lower() not in enhanced_query.lower():
            enhanced_query = f"{enhanced_query} {cottage_term}"
    
    if entities.get("group_size"):
        group_term = f"{entities['group_size']} guests"
        if group_term.lower() not in enhanced_query.lower():
            enhanced_query = f"{enhanced_query} {group_term}"
    
    # Stage 2: Optional LLM optimization (only for complex/ambiguous queries)
    if use_llm and llm is not None:
        try:
            # Use existing LLM optimization function
            llm_optimized = optimize_query_for_rag(
                llm,
                enhanced_query,
                max_new_tokens=max_new_tokens,
                timeout_seconds=timeout_seconds
            )
            return llm_optimized
        except Exception as e:
            logger.warning(f"LLM query optimization failed: {e}, using rule-based optimization")
            return enhanced_query
    
    return enhanced_query


def get_retrieval_filter(intent: "IntentType", entities: Dict[str, Any]) -> Dict[str, str]:
    """
    Build metadata filter for vector retrieval.
    
    Args:
        intent: Detected intent type
        entities: Extracted entities (cottage_id, dates, group_size)
        
    Returns:
        Metadata filter dictionary for ChromaDB
    """
    # Get intent string value
    intent_str = intent.value if hasattr(intent, 'value') else str(intent)
    
    base_filter = {"intent": intent_str}
    
    # Add cottage_id filter if extracted
    if entities.get("cottage_id"):
        base_filter["cottage_id"] = str(entities["cottage_id"])
    
    return base_filter


def is_complex_query(query: str) -> bool:
    """
    Determine if a query is complex and might benefit from LLM optimization.
    
    Args:
        query: User query
        
    Returns:
        True if query is complex, False otherwise
    """
    query_lower = query.lower()
    
    # Complex patterns that might need LLM disambiguation
    complex_patterns = [
        r'\d+',  # Contains numbers (might be ambiguous)
        r'\b(?:which|what|how|when|where|why)\b',  # Question words
        r'\b(?:best|better|compare|difference|versus|vs)\b',  # Comparison words
        r'\b(?:and|or|but)\b',  # Multiple clauses
    ]
    
    # Count complex indicators
    complex_count = sum(1 for pattern in complex_patterns if re.search(pattern, query_lower))
    
    # Consider complex if:
    # - Has 2+ complex indicators
    # - Is longer than 50 characters
    # - Contains ambiguous numbers
    is_complex = (
        complex_count >= 2 or
        len(query) > 50 or
        (re.search(r'\d+', query_lower) and 'cottage' not in query_lower)
    )
    
    return is_complex
