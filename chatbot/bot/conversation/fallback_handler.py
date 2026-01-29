"""Enhanced fallback handler for weak RAG context."""

from typing import List, Optional, TYPE_CHECKING, Union, Any
from entities.document import Document
from helpers.log import get_logger
from bot.conversation.confidence_scorer import ConfidenceScorer

if TYPE_CHECKING:
    from bot.client.lama_cpp_client import LamaCppClient
    from bot.client.groq_client import GroqClient

logger = get_logger(__name__)


class FallbackHandler:
    """Provides safe fallback responses when RAG context is weak."""
    
    def __init__(
        self,
        confidence_scorer: Optional[ConfidenceScorer] = None,
        llm: Optional[Union["LamaCppClient", "GroqClient", Any]] = None
    ):
        """
        Initialize the fallback handler.
        
        Args:
            confidence_scorer: Optional confidence scorer
            llm: Optional LLM client
        """
        self.confidence_scorer = confidence_scorer
        self.llm = llm
        
        # Safe fallback responses
        self.fallback_responses = {
            "general": (
                "I apologize, but I'm having trouble finding specific information about that in our knowledge base. "
                "Could you please rephrase your question or ask about a specific aspect of Swiss Cottages Bhurban?\n\n"
                "I can help you with:\n"
                "- Pricing and availability\n"
                "- Facilities and amenities\n"
                "- Location and nearby attractions\n"
                "- Booking and payment information\n\n"
                "What would you like to know?"
            ),
            "pricing": (
                "I don't have specific pricing information for that request in our knowledge base. "
                "Pricing depends on factors like:\n"
                "- Number of guests\n"
                "- Dates (weekday vs weekend vs peak season)\n"
                "- Cottage selection\n\n"
                "Could you provide more details about your group size and preferred dates? "
                "Or would you like to contact us directly for a personalized quote?"
            ),
            "booking": (
                "I don't have complete booking information for that specific request. "
                "To help you with booking, I'd need to know:\n"
                "- Number of guests\n"
                "- Check-in and check-out dates\n"
                "- Preferred cottage (if any)\n\n"
                "You can also book directly through our website or contact us for assistance."
            ),
            "availability": (
                "I don't have real-time availability information in our knowledge base. "
                "To check availability, please provide:\n"
                "- Your preferred dates\n"
                "- Number of guests\n\n"
                "You can check availability on our website or contact us directly for the most up-to-date information."
            ),
            "location": (
                "I don't have specific location information for that in our knowledge base. "
                "Swiss Cottages is located in Bhurban, Pakistan. "
                "For detailed location information, directions, or nearby attractions, "
                "please visit our website or contact us directly."
            ),
            "facilities": (
                "I don't have complete information about those specific facilities in our knowledge base. "
                "Swiss Cottages offers various amenities including kitchens, terraces, balconies, and more. "
                "Would you like to know about specific facilities, or would you prefer to contact us for detailed information?"
            ),
        }
    
    def should_use_fallback(
        self,
        query: str,
        retrieved_documents: List[Document],
        answer: str,
        similarity_scores: Optional[List[float]] = None
    ) -> bool:
        """
        Determine if fallback should be used.
        
        Args:
            query: User query
            retrieved_documents: Retrieved documents
            answer: Generated answer
            similarity_scores: Optional similarity scores
            
        Returns:
            True if fallback should be used
        """
        if not self.confidence_scorer:
            # If no confidence scorer, use simple heuristics
            if not retrieved_documents:
                return True
            if "don't have information" in answer.lower() or "i don't know" in answer.lower():
                return True
            return False
        
        # Use confidence scorer
        retrieval_confidence = self.confidence_scorer.score_retrieval(
            query, retrieved_documents, similarity_scores
        )
        answer_relevance = self.confidence_scorer.score_answer_relevance(query, answer)
        
        return self.confidence_scorer.should_use_fallback(retrieval_confidence, answer_relevance)
    
    def generate_fallback_response(
        self,
        query: str,
        intent: Optional[str] = None
    ) -> str:
        """
        Generate safe fallback response.
        
        Args:
            query: User query
            intent: Optional detected intent
            
        Returns:
            Fallback response string
        """
        # Determine intent category for appropriate fallback
        query_lower = query.lower()
        
        # Map intent to fallback type
        if intent:
            intent_lower = intent.lower()
            if "pricing" in intent_lower or "price" in intent_lower:
                return self.fallback_responses["pricing"]
            elif "booking" in intent_lower or "book" in intent_lower:
                return self.fallback_responses["booking"]
            elif "availability" in intent_lower or "available" in intent_lower:
                return self.fallback_responses["availability"]
            elif "location" in intent_lower or "where" in intent_lower:
                return self.fallback_responses["location"]
            elif "facilit" in intent_lower or "amenit" in intent_lower:
                return self.fallback_responses["facilities"]
        
        # Check query keywords
        if any(word in query_lower for word in ["price", "pricing", "cost", "rate", "how much"]):
            return self.fallback_responses["pricing"]
        elif any(word in query_lower for word in ["book", "booking", "reserve", "reservation"]):
            return self.fallback_responses["booking"]
        elif any(word in query_lower for word in ["available", "availability", "free", "vacant"]):
            return self.fallback_responses["availability"]
        elif any(word in query_lower for word in ["where", "location", "address", "nearby"]):
            return self.fallback_responses["location"]
        elif any(word in query_lower for word in ["facility", "amenity", "feature", "what is available"]):
            return self.fallback_responses["facilities"]
        
        # Default fallback
        return self.fallback_responses["general"]
    
    def suggest_related_topics(self, query: str) -> List[str]:
        """
        Suggest related topics user might be interested in.
        
        Args:
            query: User query
            
        Returns:
            List of suggested topics
        """
        query_lower = query.lower()
        suggestions = []
        
        # Topic mapping
        if any(word in query_lower for word in ["price", "pricing", "cost"]):
            suggestions.extend(["availability", "booking process", "payment methods"])
        elif any(word in query_lower for word in ["book", "booking"]):
            suggestions.extend(["pricing", "availability", "cottage options"])
        elif any(word in query_lower for word in ["cottage", "room", "property"]):
            suggestions.extend(["pricing", "facilities", "availability"])
        elif any(word in query_lower for word in ["facility", "amenity"]):
            suggestions.extend(["cottage options", "pricing", "location"])
        else:
            suggestions.extend(["pricing", "availability", "facilities", "booking"])
        
        return suggestions[:3]  # Return top 3 suggestions
    
    def offer_human_support(self) -> str:
        """
        Generate message offering human support.
        
        Returns:
            Support offer message
        """
        return (
            "\n\n💬 **Need more help?** "
            "If you'd like personalized assistance or have specific questions, "
            "you can contact our team directly through our website or WhatsApp. "
            "We're here to help make your stay perfect!"
        )


def get_fallback_handler(
    confidence_scorer: Optional[ConfidenceScorer] = None,
    llm: Optional[Union["LamaCppClient", "GroqClient", Any]] = None
) -> FallbackHandler:
    """
    Get or create a fallback handler.
    
    Args:
        confidence_scorer: Optional confidence scorer
        llm: Optional LLM client
        
    Returns:
        FallbackHandler instance
    """
    return FallbackHandler(confidence_scorer, llm)
