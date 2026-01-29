"""Confidence scoring for RAG retrieval and answer relevance."""

from typing import List, Optional, TYPE_CHECKING, Union, Any
from entities.document import Document
from helpers.log import get_logger

if TYPE_CHECKING:
    from bot.client.lama_cpp_client import LamaCppClient
    from bot.client.groq_client import GroqClient

logger = get_logger(__name__)


class ConfidenceScorer:
    """Scores RAG retrieval confidence and answer relevance."""
    
    def __init__(self, llm: Optional[Union["LamaCppClient", "GroqClient", Any]] = None):
        """
        Initialize the confidence scorer.
        
        Args:
            llm: Optional LLM client for complex confidence scoring
        """
        self.llm = llm
    
    def score_retrieval(
        self, 
        query: str, 
        retrieved_documents: List[Document],
        similarity_scores: Optional[List[float]] = None
    ) -> float:
        """
        Score confidence in RAG retrieval.
        
        Args:
            query: User query
            retrieved_documents: Retrieved documents
            similarity_scores: Optional similarity scores from vector search
            
        Returns:
            Confidence score between 0.0 and 1.0
        """
        if not retrieved_documents:
            return 0.0
        
        # Base confidence on number of documents
        doc_count_score = min(len(retrieved_documents) / 5.0, 1.0)  # Max at 5 docs
        
        # If similarity scores available, use them
        if similarity_scores:
            avg_similarity = sum(similarity_scores) / len(similarity_scores)
            # Normalize similarity (assuming range 0-1, adjust if different)
            similarity_score = min(avg_similarity, 1.0)
        else:
            # Default similarity if not provided
            similarity_score = 0.7
        
        # Combine scores (weighted average)
        confidence = (doc_count_score * 0.3) + (similarity_score * 0.7)
        
        logger.debug(f"Retrieval confidence: {confidence:.2f} (docs={len(retrieved_documents)}, similarity={similarity_score:.2f})")
        return confidence
    
    def score_answer_relevance(self, query: str, answer: str) -> float:
        """
        Score how relevant the answer is to the query.
        
        Args:
            query: User query
            answer: Generated answer
            
        Returns:
            Relevance score between 0.0 and 1.0
        """
        if not answer or not query:
            return 0.0
        
        query_lower = query.lower()
        answer_lower = answer.lower()
        
        # Extract key terms from query
        query_words = set(query_lower.split())
        # Remove common stop words
        stop_words = {"the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
                     "have", "has", "had", "do", "does", "did", "will", "would", "could",
                     "should", "may", "might", "can", "what", "where", "when", "who",
                     "why", "how", "which", "this", "that", "these", "those", "i", "you",
                     "he", "she", "it", "we", "they", "me", "him", "her", "us", "them"}
        query_keywords = query_words - stop_words
        
        if not query_keywords:
            # If no keywords, default to medium confidence
            return 0.5
        
        # Count how many query keywords appear in answer
        matching_keywords = sum(1 for keyword in query_keywords if keyword in answer_lower)
        keyword_score = matching_keywords / len(query_keywords) if query_keywords else 0.0
        
        # Check for answer quality indicators
        quality_indicators = [
            "i don't have information" in answer_lower,
            "i don't know" in answer_lower,
            "i cannot" in answer_lower,
            "i'm sorry" in answer_lower,
            "i apologize" in answer_lower,
        ]
        
        # Negative indicators reduce confidence
        has_negative_indicator = any(quality_indicators)
        if has_negative_indicator:
            keyword_score *= 0.5  # Reduce confidence if negative indicators present
        
        # Use LLM for complex cases if available
        if self.llm and len(query_keywords) > 3:
            llm_score = self._score_with_llm(query, answer)
            if llm_score is not None:
                # Combine keyword score with LLM score
                final_score = (keyword_score * 0.6) + (llm_score * 0.4)
                logger.debug(f"Answer relevance: {final_score:.2f} (keyword={keyword_score:.2f}, llm={llm_score:.2f})")
                return final_score
        
        logger.debug(f"Answer relevance: {keyword_score:.2f} (keywords matched: {matching_keywords}/{len(query_keywords)})")
        return keyword_score
    
    def _score_with_llm(self, query: str, answer: str) -> Optional[float]:
        """
        Use LLM to score answer relevance.
        
        Args:
            query: User query
            answer: Generated answer
            
        Returns:
            Relevance score between 0.0 and 1.0, or None if scoring fails
        """
        if not self.llm:
            return None
        
        prompt = f"""Rate how relevant this answer is to the user's question on a scale of 0.0 to 1.0.

User question: "{query}"

Answer: "{answer[:500]}"

Consider:
- Does the answer address the question?
- Is the answer specific to what was asked?
- Does the answer contain relevant information?

Respond with ONLY a number between 0.0 and 1.0 (e.g., 0.85):"""
        
        try:
            response = self.llm.generate_answer(prompt, max_new_tokens=10).strip()
            # Extract number from response
            import re
            match = re.search(r'(\d+\.?\d*)', response)
            if match:
                score = float(match.group(1))
                # Normalize to 0-1 range
                score = max(0.0, min(1.0, score))
                return score
        except Exception as e:
            logger.warning(f"LLM relevance scoring failed: {e}")
        
        return None
    
    def get_confidence_level(self, confidence: float) -> str:
        """
        Get human-readable confidence level.
        
        Args:
            confidence: Confidence score (0.0-1.0)
            
        Returns:
            Confidence level string
        """
        if confidence >= 0.8:
            return "high"
        elif confidence >= 0.5:
            return "medium"
        else:
            return "low"
    
    def should_use_fallback(self, retrieval_confidence: float, answer_relevance: float) -> bool:
        """
        Determine if fallback response should be used.
        
        Args:
            retrieval_confidence: Retrieval confidence score
            answer_relevance: Answer relevance score
            
        Returns:
            True if fallback should be used
        """
        # Use fallback if both scores are low
        return retrieval_confidence < 0.3 and answer_relevance < 0.3


def get_confidence_scorer(llm: Optional[Union["LamaCppClient", "GroqClient", Any]] = None) -> ConfidenceScorer:
    """
    Get or create a confidence scorer.
    
    Args:
        llm: Optional LLM client
        
    Returns:
        ConfidenceScorer instance
    """
    return ConfidenceScorer(llm)
