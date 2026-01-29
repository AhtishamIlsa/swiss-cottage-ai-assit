"""Sentiment analysis for user queries."""

import re
from enum import Enum
from typing import Optional, TYPE_CHECKING, Union, Any
from helpers.log import get_logger

if TYPE_CHECKING:
    from bot.client.lama_cpp_client import LamaCppClient
    from bot.client.groq_client import GroqClient

logger = get_logger(__name__)


class Sentiment(Enum):
    """Sentiment types."""
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    FRUSTRATED = "frustrated"
    CONFUSED = "confused"
    SATISFIED = "satisfied"


class SentimentAnalyzer:
    """Detects user sentiment and adjusts tone accordingly."""
    
    def __init__(self, llm: Optional[Union["LamaCppClient", "GroqClient", Any]] = None):
        """
        Initialize the sentiment analyzer.
        
        Args:
            llm: Optional LLM client for complex sentiment analysis
        """
        self.llm = llm
        
        # Frustration indicators
        self.frustration_patterns = [
            r"why (?:can'?t|cannot|won'?t|doesn'?t|didn'?t)",
            r"this (?:is|doesn'?t|can'?t) (?:not|wrong|bad|terrible|awful)",
            r"(?:not|never) (?:working|helping|answering|responding)",
            r"(?:still|again) (?:not|can'?t|cannot)",
            r"useless|worthless|terrible|awful|horrible",
            r"can'?t (?:understand|get|find|see)",
            r"doesn'?t (?:work|help|make sense)",
            r"what (?:the|is) (?:hell|heck)",
            r"so (?:confusing|frustrating|annoying)",
            r"very (?:frustrated|annoyed|angry|upset)",
        ]
        
        # Confusion indicators
        self.confusion_patterns = [
            r"what (?:do you|does this|is this|are you) (?:mean|talking about)",
            r"i (?:don'?t|do not) (?:understand|get|see|know)",
            r"confused|unclear|unclear|not sure",
            r"what (?:is|are|does|did|will)",
            r"can you (?:explain|clarify|help me understand)",
            r"i'm (?:confused|lost|not following)",
            r"doesn'?t (?:make sense|seem right)",
        ]
        
        # Satisfaction indicators
        self.satisfaction_patterns = [
            r"thank (?:you|u)",
            r"thanks|thx|ty",
            r"great|excellent|perfect|wonderful|awesome",
            r"that'?s (?:great|perfect|excellent|helpful|good)",
            r"exactly (?:what|what i) (?:i|needed|wanted)",
            r"very (?:helpful|useful|good|nice)",
            r"appreciate|appreciated",
        ]
        
        # Positive indicators
        self.positive_patterns = [
            r"good|nice|great|excellent|perfect|wonderful",
            r"love|like|enjoy",
            r"helpful|useful|informative",
            r"thanks|thank you",
        ]
    
    def analyze(self, query: str) -> Sentiment:
        """
        Analyze sentiment of user query.
        
        Args:
            query: User query string
            
        Returns:
            Detected sentiment
        """
        query_lower = query.lower()
        
        # Check for frustration first (highest priority)
        for pattern in self.frustration_patterns:
            if re.search(pattern, query_lower):
                logger.debug(f"Detected frustration in query: {query[:50]}")
                return Sentiment.FRUSTRATED
        
        # Check for confusion
        for pattern in self.confusion_patterns:
            if re.search(pattern, query_lower):
                logger.debug(f"Detected confusion in query: {query[:50]}")
                return Sentiment.CONFUSED
        
        # Check for satisfaction
        for pattern in self.satisfaction_patterns:
            if re.search(pattern, query_lower):
                logger.debug(f"Detected satisfaction in query: {query[:50]}")
                return Sentiment.SATISFIED
        
        # Check for positive
        positive_count = sum(1 for pattern in self.positive_patterns if re.search(pattern, query_lower))
        if positive_count >= 2:
            logger.debug(f"Detected positive sentiment in query: {query[:50]}")
            return Sentiment.POSITIVE
        
        # Use LLM for complex cases if available
        if self.llm:
            llm_sentiment = self._analyze_with_llm(query)
            if llm_sentiment:
                return llm_sentiment
        
        # Default to neutral
        return Sentiment.NEUTRAL
    
    def _analyze_with_llm(self, query: str) -> Optional[Sentiment]:
        """
        Use LLM to analyze sentiment for complex cases.
        
        Args:
            query: User query string
            
        Returns:
            Detected sentiment or None
        """
        if not self.llm:
            return None
        
        prompt = f"""Analyze the sentiment of this user query for a customer service chatbot.

User query: "{query}"

Classify the sentiment as one of:
- frustrated: User is frustrated, annoyed, or angry
- confused: User is confused or doesn't understand
- satisfied: User is satisfied or appreciative
- positive: User has positive sentiment
- neutral: Neutral sentiment

Respond with ONLY the sentiment word (frustrated, confused, satisfied, positive, or neutral):"""
        
        try:
            response = self.llm.generate_answer(prompt, max_new_tokens=10).strip().lower()
            
            # Map response to Sentiment enum
            if "frustrated" in response or "frustrat" in response:
                return Sentiment.FRUSTRATED
            elif "confused" in response or "confus" in response:
                return Sentiment.CONFUSED
            elif "satisfied" in response or "satisf" in response:
                return Sentiment.SATISFIED
            elif "positive" in response:
                return Sentiment.POSITIVE
            else:
                return Sentiment.NEUTRAL
        except Exception as e:
            logger.warning(f"LLM sentiment analysis failed: {e}")
            return None
    
    def adjust_tone(self, response: str, sentiment: Sentiment) -> str:
        """
        Adjust response tone based on sentiment.
        
        Args:
            response: Original response text
            sentiment: Detected sentiment
            
        Returns:
            Adjusted response
        """
        if sentiment == Sentiment.FRUSTRATED:
            # Add empathetic opening and offer escalation
            if not response.startswith("I understand"):
                response = "I understand this can be frustrating. " + response
            # Add escalation offer at the end if not already present
            if "contact" not in response.lower() and "help" not in response.lower():
                response += "\n\nIf you'd like, I can connect you with our team for personalized assistance."
        
        elif sentiment == Sentiment.CONFUSED:
            # Add clarification offer
            if not response.startswith("Let me clarify"):
                response = "Let me clarify that for you. " + response
            # Add offer to explain further
            if "explain" not in response.lower() and "clarify" not in response.lower():
                response += "\n\nWould you like me to explain any part in more detail?"
        
        elif sentiment == Sentiment.SATISFIED:
            # Keep positive tone, maybe add appreciation
            if "glad" not in response.lower() and "happy" not in response.lower():
                # Don't modify satisfied responses too much - they're already good
                pass
        
        elif sentiment == Sentiment.POSITIVE:
            # Maintain friendly, helpful tone (already good)
            pass
        
        # Neutral - no adjustment needed
        return response
    
    def should_escalate(self, sentiment: Sentiment) -> bool:
        """
        Determine if sentiment warrants escalation to human support.
        
        Args:
            sentiment: Detected sentiment
            
        Returns:
            True if escalation recommended
        """
        return sentiment == Sentiment.FRUSTRATED


def get_sentiment_analyzer(llm: Optional[Union["LamaCppClient", "GroqClient", Any]] = None) -> SentimentAnalyzer:
    """
    Get or create a sentiment analyzer.
    
    Args:
        llm: Optional LLM client
        
    Returns:
        SentimentAnalyzer instance
    """
    return SentimentAnalyzer(llm)
