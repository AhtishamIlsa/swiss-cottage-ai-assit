"""Refinement detector for identifying constraint/refinement requests."""

import re
from typing import TYPE_CHECKING
from bot.conversation.chat_history import ChatHistory
from helpers.log import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class RefinementDetector:
    """Detects if a query is a refinement/constraint request."""
    
    # Constraint keywords that indicate refinement
    CONSTRAINT_KEYWORDS = [
        "just", "only", "for", "on", "during", "in",
        "cheaper", "lower", "minimum", "maximum", "best", "worst",
        "specific", "particular", "exact", "precise"
    ]
    
    # Time constraint patterns
    TIME_CONSTRAINTS = [
        "weekdays", "weekday", "weekends", "weekend",
        "peak season", "peak", "holidays", "holiday",
        "summer", "winter", "spring", "autumn", "fall",
        "january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december"
    ]
    
    # Quantity constraint patterns
    QUANTITY_PATTERNS = [
        r"for\s+(\d+)\s+(?:people|person|guests|members)",
        r"for\s+(\d+)\s+(?:days|day|nights|night)",
        r"(\d+)\s+(?:people|person|guests|members)",
        r"(\d+)\s+(?:days|day|nights|night)",
    ]
    
    # Price constraint patterns
    PRICE_CONSTRAINTS = [
        "cheaper", "cheapest", "lower", "lowest", "minimum", "min",
        "expensive", "expensive", "higher", "highest", "maximum", "max",
        "budget", "affordable", "cost-effective"
    ]
    
    # Topic keywords that indicate what was asked about
    PRICING_TOPICS = [
        "price", "pricing", "cost", "rate", "rates", "payment",
        "per night", "per day", "total", "amount", "fee", "charges"
    ]
    
    CAPACITY_TOPICS = [
        "capacity", "accommodate", "fit", "suit", "suitable",
        "people", "guests", "members", "group", "party"
    ]
    
    BOOKING_TOPICS = [
        "book", "booking", "reserve", "reservation", "available",
        "availability", "dates", "stay", "check-in", "check-out"
    ]
    
    def is_refinement_request(self, query: str, chat_history: ChatHistory) -> bool:
        """
        Check if a query is a refinement/constraint request.
        
        Args:
            query: Current user query
            chat_history: Chat history to check previous context
            
        Returns:
            True if query is a refinement request, False otherwise
        """
        query_lower = query.lower().strip()
        words = query_lower.split()
        
        # Must have chat history to be a refinement
        if not chat_history or len(chat_history) == 0:
            return False
        
        # Get previous question from chat history
        previous_question = self._get_previous_question(chat_history)
        if not previous_question:
            return False
        
        previous_question_lower = previous_question.lower()
        
        # Check if query is very short (1-5 words) - likely a constraint
        if len(words) <= 5:
            # Check for constraint keywords
            has_constraint_keyword = any(
                keyword in query_lower for keyword in self.CONSTRAINT_KEYWORDS
            )
            
            # Check for time constraints
            has_time_constraint = any(
                time_word in query_lower for time_word in self.TIME_CONSTRAINTS
            )
            
            # Check for quantity constraints
            has_quantity_constraint = any(
                re.search(pattern, query_lower) for pattern in self.QUANTITY_PATTERNS
            )
            
            # Check for price constraints
            has_price_constraint = any(
                price_word in query_lower for price_word in self.PRICE_CONSTRAINTS
            )
            
            logger.debug(f"Refinement check - query: '{query}', has_constraint: {has_constraint_keyword}, has_time: {has_time_constraint}, has_quantity: {has_quantity_constraint}, has_price: {has_price_constraint}")
            logger.debug(f"Previous question: '{previous_question}'")
            
            # If it has constraint indicators, check if previous question was about relevant topic
            if has_constraint_keyword or has_time_constraint or has_quantity_constraint or has_price_constraint:
                # Check if previous question was about pricing, capacity, or booking
                is_pricing_question = any(
                    topic in previous_question_lower for topic in self.PRICING_TOPICS
                )
                is_capacity_question = any(
                    topic in previous_question_lower for topic in self.CAPACITY_TOPICS
                )
                is_booking_question = any(
                    topic in previous_question_lower for topic in self.BOOKING_TOPICS
                )
                
                logger.debug(f"Topic check - pricing: {is_pricing_question}, capacity: {is_capacity_question}, booking: {is_booking_question}")
                
                # If previous question was about relevant topic, this is likely a refinement
                if is_pricing_question or is_capacity_question or is_booking_question:
                    logger.info(f"Detected refinement request: '{query}' (constraint added to previous question about pricing/capacity/booking)")
                    return True
        
        # Check for specific refinement patterns
        refinement_patterns = [
            r"^just\s+(?:on\s+)?(?:weekdays?|weekends?|peak|holidays?)",
            r"^only\s+(?:weekdays?|weekends?|peak|holidays?)",
            r"^(?:for|with)\s+\d+\s+(?:people|person|guests|members|days|nights)",
            r"^(?:cheaper|lower|minimum|maximum|best|worst)",
            r"^(?:during|in)\s+(?:peak|summer|winter|holidays?)",
        ]
        
        for pattern in refinement_patterns:
            if re.match(pattern, query_lower):
                # Check if previous question was relevant
                previous_question_lower = previous_question.lower()
                is_relevant_previous = (
                    any(topic in previous_question_lower for topic in self.PRICING_TOPICS) or
                    any(topic in previous_question_lower for topic in self.CAPACITY_TOPICS) or
                    any(topic in previous_question_lower for topic in self.BOOKING_TOPICS)
                )
                
                if is_relevant_previous:
                    logger.info(f"Detected refinement request via pattern: '{query}'")
                    return True
        
        return False
    
    def _get_previous_question(self, chat_history: ChatHistory) -> str:
        """
        Extract the previous question from chat history.
        
        Args:
            chat_history: Chat history object
            
        Returns:
            Previous question string, or empty string if not found
        """
        if not chat_history or len(chat_history) == 0:
            return ""
        
        # Chat history format: "question: {question}, answer: {answer}"
        # Get the last entry
        last_entry = chat_history[-1]
        
        # Extract question from format "question: {question}, answer: {answer}"
        if "question:" in last_entry:
            parts = last_entry.split("question:", 1)
            if len(parts) > 1:
                question_part = parts[1].split(", answer:", 1)[0].strip()
                return question_part
        
        return ""


# Global instance for easy access
_refinement_detector: RefinementDetector = None


def get_refinement_detector() -> RefinementDetector:
    """
    Get or create the global refinement detector instance.
    
    Returns:
        RefinementDetector instance
    """
    global _refinement_detector
    if _refinement_detector is None:
        _refinement_detector = RefinementDetector()
    return _refinement_detector
