"""
Query Complexity Classifier Module

This module classifies queries as "simple" or "reasoning" to route them
to appropriate models (fast model for simple, reasoning model for complex).
"""

from typing import TYPE_CHECKING
from helpers.log import get_logger

if TYPE_CHECKING:
    from bot.conversation.intent_router import IntentType

logger = get_logger(__name__)


class QueryComplexityClassifier:
    """
    Classifies queries based on complexity to determine which model to use.
    
    Uses hybrid approach:
    - Intent-based classification (PRICING, CAPACITY, BOOKING with calculations)
    - Keyword-based classification (calculation keywords, comparison keywords)
    - Query length and structure analysis
    """
    
    def __init__(self):
        """Initialize the complexity classifier."""
        # Keywords that indicate reasoning/complex queries
        self.reasoning_keywords = [
            "calculate", "calculation", "compute", "total", "total cost", "total price",
            "how much", "how many nights", "how many days", "suitable for", "can we stay",
            "can i stay", "accommodate", "capacity", "fit", "compare", "comparison",
            "difference", "better", "best for", "which is", "should i choose",
            "recommend", "recommendation", "pricing for", "price for", "cost for",
            "from X to Y", "between", "range", "if we stay", "if i stay",
            "total amount", "final price", "final cost"
        ]
        
        # Keywords that indicate simple queries
        self.simple_keywords = [
            "what is", "what are", "tell me about", "describe", "explain",
            "list", "show", "give me", "do you have", "is there", "are there",
            "yes", "no", "thanks", "hello", "hi", "help"
        ]
        
        # Intent types that typically require reasoning
        self.reasoning_intents = [
            "pricing",  # Pricing calculations
            "capacity",  # Capacity analysis (though not in IntentType enum, handled separately)
        ]
        
        # Intent types that are typically simple
        self.simple_intents = [
            "greeting", "help", "statement", "affirmative", "negative"
        ]
    
    def classify_complexity(self, query: str, intent: "IntentType") -> str:
        """
        Classify query complexity.
        
        Args:
            query: User query string
            intent: IntentType from intent router
            
        Returns:
            "simple" or "reasoning"
        """
        query_lower = query.lower()
        intent_str = intent.value if hasattr(intent, 'value') else str(intent)
        
        # Check intent-based classification first
        if intent_str in self.reasoning_intents:
            logger.debug(f"Query classified as reasoning based on intent: {intent_str}")
            return "reasoning"
        
        if intent_str in self.simple_intents:
            logger.debug(f"Query classified as simple based on intent: {intent_str}")
            return "simple"
        
        # Special handling for PRICING and BOOKING intents
        # Only use reasoning if they involve calculations
        if intent_str == "pricing":
            # Check if pricing query involves calculations
            if any(keyword in query_lower for keyword in ["calculate", "total", "how much", "from", "to", "nights", "days"]):
                logger.debug(f"Pricing query with calculations → reasoning")
                return "reasoning"
            else:
                logger.debug(f"Simple pricing query → simple")
                return "simple"
        
        if intent_str == "booking":
            # Booking with dates/calculations → reasoning
            if any(keyword in query_lower for keyword in ["from", "to", "nights", "days", "calculate", "total"]):
                logger.debug(f"Booking query with calculations → reasoning")
                return "reasoning"
            else:
                logger.debug(f"Simple booking query → simple")
                return "simple"
        
        # Check for capacity/suitability queries (often handled separately but check here)
        if any(keyword in query_lower for keyword in ["suitable", "can we stay", "can i stay", "accommodate", "fit", "capacity"]):
            logger.debug(f"Capacity/suitability query → reasoning")
            return "reasoning"
        
        # Keyword-based classification
        reasoning_keyword_count = sum(1 for keyword in self.reasoning_keywords if keyword in query_lower)
        simple_keyword_count = sum(1 for keyword in self.simple_keywords if keyword in query_lower)
        
        # If query has reasoning keywords, classify as reasoning
        if reasoning_keyword_count > 0:
            logger.debug(f"Query classified as reasoning based on keywords (count: {reasoning_keyword_count})")
            return "reasoning"
        
        # Check query structure
        # Long queries (> 15 words) with numbers/dates are likely reasoning
        word_count = len(query.split())
        has_numbers = any(char.isdigit() for char in query)
        has_dates = any(word in query_lower for word in ["feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec", "january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"])
        
        if word_count > 15 and (has_numbers or has_dates):
            logger.debug(f"Long query with numbers/dates → reasoning")
            return "reasoning"
        
        # Default to simple for everything else
        logger.debug(f"Query classified as simple (default)")
        return "simple"


# Global instance
_complexity_classifier: QueryComplexityClassifier = None


def get_complexity_classifier() -> QueryComplexityClassifier:
    """Get or create the global complexity classifier instance."""
    global _complexity_classifier
    if _complexity_classifier is None:
        _complexity_classifier = QueryComplexityClassifier()
    return _complexity_classifier
