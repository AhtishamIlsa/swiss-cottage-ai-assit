"""Refinement handler for processing constraint/refinement requests."""

import re
from typing import Dict, Optional, TYPE_CHECKING, Union, Any
from bot.conversation.chat_history import ChatHistory
from bot.conversation.refinement_detector import RefinementDetector
from helpers.log import get_logger

if TYPE_CHECKING:
    from bot.client.lama_cpp_client import LamaCppClient
    from bot.client.groq_client import GroqClient

logger = get_logger(__name__)


class RefinementHandler:
    """Handles refinement requests by combining previous questions with constraints."""
    
    def __init__(self, llm: Optional[Union["LamaCppClient", "GroqClient", Any]] = None):
        """
        Initialize the refinement handler.
        
        Args:
            llm: LLM client for combining questions (optional, will use refine_question if not provided)
        """
        self.llm = llm
        self.detector = RefinementDetector()
    
    def process_refinement(
        self, 
        query: str, 
        chat_history: ChatHistory,
        llm: Optional[Union["LamaCppClient", "GroqClient", Any]] = None
    ) -> Dict:
        """
        Process a refinement request by combining previous question with constraint.
        
        Args:
            query: Current refinement query (e.g., "just on weekdays")
            chat_history: Chat history containing previous question
            llm: LLM client for question combination (optional)
            
        Returns:
            Dictionary with keys:
            - combined_question: str - Combined question with constraint
            - constraint: str - Extracted constraint
            - previous_question: str - Previous question from history
        """
        # Get previous question from chat history
        previous_question = self._extract_previous_question(chat_history)
        
        if not previous_question:
            logger.warning("No previous question found in chat history for refinement")
            return {
                "combined_question": query,  # Fallback to original query
                "constraint": query,
                "previous_question": "",
            }
        
        # Extract constraint from current query
        constraint = self._extract_constraint(query)
        
        # Combine previous question with constraint
        combined_question = self._combine_question_with_constraint(
            previous_question, constraint, query, llm
        )
        
        logger.info(f"Refinement: '{previous_question}' + '{constraint}' → '{combined_question}'")
        
        return {
            "combined_question": combined_question,
            "constraint": constraint,
            "previous_question": previous_question,
        }
    
    def _extract_previous_question(self, chat_history: ChatHistory) -> str:
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
    
    def _extract_constraint(self, query: str) -> str:
        """
        Extract the constraint from the refinement query.
        
        Args:
            query: Refinement query (e.g., "just on weekdays")
            
        Returns:
            Extracted constraint string
        """
        query_lower = query.lower().strip()
        
        # Remove common filler words at the start
        fillers = ["just", "only", "for", "on", "during", "in", "with"]
        words = query_lower.split()
        
        # If starts with filler, keep it as part of constraint
        # Otherwise, return the whole query as constraint
        return query.strip()
    
    def _combine_question_with_constraint(
        self,
        previous_question: str,
        constraint: str,
        original_query: str,
        llm: Optional[Union["LamaCppClient", "GroqClient", Any]] = None
    ) -> str:
        """
        Combine previous question with new constraint.
        
        Args:
            previous_question: Previous question from chat history
            constraint: Extracted constraint
            original_query: Original refinement query
            llm: LLM client for intelligent combination (optional)
            
        Returns:
            Combined question string
        """
        # Simple rule-based combination first
        previous_lower = previous_question.lower()
        constraint_lower = constraint.lower()
        
        # Time constraints
        if any(word in constraint_lower for word in ["weekday", "weekend", "peak", "holiday", "summer", "winter"]):
            # Add time constraint to question
            if "weekday" in constraint_lower or "weekend" in constraint_lower:
                if "weekday" in constraint_lower:
                    time_constraint = "on weekdays only"
                else:
                    time_constraint = "on weekends only"
            elif "peak" in constraint_lower:
                time_constraint = "during peak season"
            elif "holiday" in constraint_lower:
                time_constraint = "during holidays"
            else:
                time_constraint = constraint
            
            # Check if question already has time constraint
            if not any(word in previous_lower for word in ["weekday", "weekend", "peak", "holiday"]):
                # Add time constraint
                if "?" in previous_question:
                    combined = previous_question.replace("?", f" {time_constraint}?")
                else:
                    combined = f"{previous_question} {time_constraint}"
                return combined
        
        # Quantity constraints
        quantity_match = re.search(r"(\d+)\s+(?:people|person|guests|members|days|day|nights|night)", constraint_lower)
        if quantity_match:
            # Check if previous question already has this quantity
            number = quantity_match.group(1)
            if number not in previous_lower:
                # Add quantity constraint
                if "?" in previous_question:
                    combined = previous_question.replace("?", f" {constraint}?")
                else:
                    combined = f"{previous_question} {constraint}"
                return combined
        
        # Price constraints
        if any(word in constraint_lower for word in ["cheaper", "lower", "minimum", "maximum", "best", "worst"]):
            # Add price constraint
            if "?" in previous_question:
                combined = previous_question.replace("?", f" ({constraint})?")
            else:
                combined = f"{previous_question} ({constraint})"
            return combined
        
        # Default: append constraint to previous question
        if "?" in previous_question:
            combined = previous_question.replace("?", f" {constraint}?")
        else:
            combined = f"{previous_question} {constraint}"
        
        return combined


# Global instance for easy access
_refinement_handler: Optional[RefinementHandler] = None


def get_refinement_handler(
    llm: Optional[Union["LamaCppClient", "GroqClient", Any]] = None
) -> RefinementHandler:
    """
    Get or create the global refinement handler instance.
    
    Args:
        llm: Optional LLM client for question combination
        
    Returns:
        RefinementHandler instance
    """
    global _refinement_handler
    if _refinement_handler is None:
        _refinement_handler = RefinementHandler(llm)
    elif llm is not None and _refinement_handler.llm is None:
        _refinement_handler.llm = llm
    return _refinement_handler
