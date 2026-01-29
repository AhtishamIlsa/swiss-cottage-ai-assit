"""Capacity query handler for processing capacity/suitability questions."""

from typing import Dict, List, Optional
from entities.document import Document
from bot.conversation.cottage_capacity import CottageCapacityMapper, get_capacity_mapper
from bot.conversation.number_extractor import NumberExtractor, ExtractCapacityQuery
from helpers.log import get_logger

logger = get_logger(__name__)


class CapacityQueryHandler:
    """Handles capacity queries with structured logic."""
    
    def __init__(self, capacity_mapper: Optional[CottageCapacityMapper] = None):
        """
        Initialize the capacity query handler.
        
        Args:
            capacity_mapper: Optional CottageCapacityMapper instance. If None, creates a new one.
        """
        self.capacity_mapper = capacity_mapper or get_capacity_mapper()
        self.number_extractor = NumberExtractor()
        self.capacity_detector = ExtractCapacityQuery()
    
    def is_capacity_query(self, question: str) -> bool:
        """
        Check if a question is about capacity or suitability.
        
        Args:
            question: User's question string
            
        Returns:
            True if question is about capacity/suitability
        """
        return self.capacity_detector.is_capacity_query(question)
    
    def process_capacity_query(
        self, 
        question: str, 
        retrieved_contents: List[Document]
    ) -> Dict:
        """
        Process a capacity query using structured logic.
        
        Args:
            question: User's question string
            retrieved_contents: List of retrieved documents from RAG
            
        Returns:
            Dictionary with keys:
            - suitable: bool - Whether the group size is suitable
            - reason: str - Explanation of suitability
            - group_size: int or None - Extracted group size
            - cottage_number: str or None - Extracted cottage number
            - capacity_info: dict or None - Capacity information for the cottage
            - answer_template: str - Structured answer template to add to context
            - has_all_info: bool - Whether we have both group size and cottage number
        """
        # Extract numbers from question
        extracted = self.number_extractor.extract_all(question)
        group_size = extracted["group_size"]
        cottage_number = extracted["cottage_number"]
        is_capacity_query = extracted["is_capacity_query"]
        
        logger.info(f"Processing capacity query - Group size: {group_size}, Cottage: {cottage_number}")
        
        # Check if we have enough information
        has_all_info = group_size is not None and cottage_number is not None
        
        if not has_all_info:
            # Partial information - still generate helpful context
            if group_size is None and cottage_number is None:
                logger.debug("No group size or cottage number extracted")
                return {
                    "suitable": None,
                    "reason": "Could not extract group size or cottage number from question",
                    "group_size": None,
                    "cottage_number": None,
                    "capacity_info": None,
                    "answer_template": "",
                    "has_all_info": False,
                }
            elif group_size is None:
                # Have cottage but no group size
                capacity_info = self.capacity_mapper.get_capacity(cottage_number)
                if capacity_info:
                    answer_template = f"""
STRUCTURED CAPACITY ANALYSIS:
Cottage: {cottage_number}
Capacity: {capacity_info['base_capacity']} guests at base price, up to {capacity_info['max_capacity']} guests with prior confirmation
Bedrooms: {capacity_info['bedrooms']}
Note: Group size not specified in question. Please provide number of guests for suitability check.
"""
                else:
                    answer_template = f"Cottage {cottage_number} capacity information not available."
                
                return {
                    "suitable": None,
                    "reason": f"Cottage {cottage_number} found, but group size not specified",
                    "group_size": None,
                    "cottage_number": cottage_number,
                    "capacity_info": capacity_info,
                    "answer_template": answer_template,
                    "has_all_info": False,
                }
            else:
                # Have group size but no cottage - provide general guidance
                # IMPORTANT: Max capacity in ANY cottage is 9 guests (from FAQ 018)
                if group_size <= 6:
                    suitability = "suitable for any cottage (2-bedroom or 3-bedroom) at base price"
                elif group_size <= 9:
                    suitability = "suitable for any cottage with prior confirmation and adjusted pricing (max 9 guests per cottage)"
                else:
                    suitability = "requires multiple cottages (max 9 guests per cottage for safety and community guidelines)"
                
                # Provide recommendations for which cottage is best
                if group_size <= 6:
                    recommendation = f"✅ RECOMMENDATION: Any cottage (Cottage 7, 9, or 11) is suitable for your group of {group_size} guests at base price. Cottage 9 and Cottage 11 are 3-bedroom cottages with more space, ideal for families."
                    answer_text = f"✅ YES, your group of {group_size} guests can stay in any cottage (Cottage 7, 9, or 11) at base price. All cottages can accommodate up to 6 guests comfortably."
                elif group_size <= 9:
                    recommendation = f"✅ RECOMMENDATION: Any cottage (Cottage 7, 9, or 11) can accommodate your group of {group_size} guests with prior confirmation and adjusted pricing. Cottage 9 and Cottage 11 are 3-bedroom cottages with more space, ideal for larger groups."
                    answer_text = f"✅ YES, your group of {group_size} guests can stay in any cottage (Cottage 7, 9, or 11) with prior confirmation and adjusted pricing. All cottages have a maximum capacity of 9 guests per cottage."
                else:
                    recommendation = "❌ RECOMMENDATION: Your group exceeds the maximum capacity of 9 guests per cottage. You will need to book multiple cottages. Contact the manager to arrange multiple cottage bookings."
                    answer_text = f"❌ NO, your group of {group_size} guests exceeds the maximum capacity of 9 guests per cottage. You must book multiple cottages."
                
                answer_template = f"""
STRUCTURED CAPACITY ANALYSIS FOR USER QUESTION:
Question: "which cottage is best for {group_size} people" or similar capacity query

DIRECT ANSWER (USE THIS EXACTLY):
{answer_text}

DETAILED ANALYSIS:
Group Size: {group_size} guests
Cottage: Not specified - user asking which cottage is best
General Capacity Rules:
- Base capacity: 6 guests per cottage (comfortable at base price)
- Maximum capacity: 9 guests per cottage (with prior confirmation and adjusted pricing)
- Hard limit: No more than 9 guests allowed in a single cottage (for comfort, safety, and community guidelines)
- Your group of {group_size} guests: {suitability}

RECOMMENDATION (USE THIS IN YOUR ANSWER):
{recommendation}

CRITICAL: When answering "which cottage is best for X people", use the RECOMMENDATION above. Do NOT say "no suitable cottage" if the recommendation says "any cottage" is suitable.
"""
                return {
                    "suitable": group_size <= 9,  # Suitable if within max limit
                    "reason": f"Group size {group_size} found, but cottage number not specified. {suitability}",
                    "group_size": group_size,
                    "cottage_number": None,
                    "capacity_info": {"base_capacity": 6, "max_capacity": 9, "bedrooms": "varies"},
                    "answer_template": answer_template,
                    "has_all_info": False,
                }
        
        # We have both group size and cottage number - perform structured comparison
        # Validate cottage number exists
        if cottage_number not in ["3", "7", "9", "11"]:
            # Unknown cottage number - treat as group-only query
            logger.warning(f"Unknown cottage number: {cottage_number}. Treating as group-only query.")
            return self.process_capacity_query(question.replace(f"cottage {cottage_number}", "").replace(f"cottage{cottage_number}", "").strip(), retrieved_contents)
        
        capacity_info = self.capacity_mapper.get_capacity(cottage_number)
        if not capacity_info:
            return {
                "suitable": None,
                "reason": f"Cottage {cottage_number} capacity information not available",
                "group_size": group_size,
                "cottage_number": cottage_number,
                "capacity_info": None,
                "answer_template": f"Cottage {cottage_number} capacity information not available in the system.",
                "has_all_info": True,
            }
        
        # Perform suitability check
        suitable, reason = self.capacity_mapper.is_suitable(group_size, cottage_number)
        
        # Generate structured answer template
        base_capacity = capacity_info["base_capacity"]
        max_capacity = capacity_info["max_capacity"]
        bedrooms = capacity_info["bedrooms"]
        
        # Create detailed comparison
        if group_size <= base_capacity:
            comparison = f"{group_size} ≤ {base_capacity} base capacity = SUITABLE (comfortable at base price)"
        elif group_size <= max_capacity:
            comparison = f"{group_size} ≤ {max_capacity} max capacity = SUITABLE (requires prior confirmation and adjusted pricing)"
        else:
            comparison = f"{group_size} > {max_capacity} max capacity = NOT SUITABLE (must book multiple cottages)"
        
        answer_template = f"""
STRUCTURED CAPACITY ANALYSIS:
Group Size: {group_size} guests
Cottage: {cottage_number} ({bedrooms}-bedroom)
Base Capacity: {base_capacity} guests
Max Capacity: {max_capacity} guests
Comparison: {comparison}
Result: {"SUITABLE" if suitable else "NOT SUITABLE"}
Reason: {reason}
"""
        
        logger.info(f"Capacity check result: {group_size} guests for Cottage {cottage_number} = {suitable} ({reason})")
        
        return {
            "suitable": suitable,
            "reason": reason,
            "group_size": group_size,
            "cottage_number": cottage_number,
            "capacity_info": capacity_info,
            "answer_template": answer_template,
            "has_all_info": True,
        }
    
    def enhance_context_with_capacity_info(
        self,
        retrieved_contents: List[Document],
        capacity_result: Dict
    ) -> List[Document]:
        """
        Enhance retrieved documents with structured capacity information.
        
        Args:
            retrieved_contents: List of retrieved documents
            capacity_result: Result from process_capacity_query()
            
        Returns:
            List of documents with capacity info prepended to first document
        """
        if not capacity_result.get("answer_template"):
            return retrieved_contents
        
        # Create a new document with capacity analysis
        from entities.document import Document
        
        capacity_doc = Document(
            page_content=capacity_result["answer_template"],
            metadata={
                "source": "structured_capacity_analysis",
                "type": "capacity_analysis",
                "group_size": capacity_result.get("group_size"),
                "cottage_number": capacity_result.get("cottage_number"),
            }
        )
        
        # Prepend capacity analysis to retrieved contents
        enhanced_contents = [capacity_doc] + retrieved_contents
        
        logger.debug(f"Enhanced context with capacity analysis for {len(enhanced_contents)} documents")
        
        return enhanced_contents


# Global instance for easy access
_capacity_handler: Optional[CapacityQueryHandler] = None


def get_capacity_handler(
    capacity_mapper: Optional[CottageCapacityMapper] = None
) -> CapacityQueryHandler:
    """
    Get or create the global capacity handler instance.
    
    Args:
        capacity_mapper: Optional CottageCapacityMapper instance
        
    Returns:
        CapacityQueryHandler instance
    """
    global _capacity_handler
    if _capacity_handler is None:
        _capacity_handler = CapacityQueryHandler(capacity_mapper)
    return _capacity_handler
