"""Capacity query handler for processing capacity/suitability questions."""

from typing import Dict, List, Optional
from entities.document import Document
from bot.conversation.cottage_capacity import CottageCapacityMapper, get_capacity_mapper
from bot.conversation.number_extractor import NumberExtractor, ExtractCapacityQuery
from bot.conversation.date_extractor import DateExtractor
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
        self.date_extractor = DateExtractor()
    
    def is_capacity_query(self, question: str) -> bool:
        """
        Check if a question is about capacity or suitability.
        
        Args:
            question: User's question string
            
        Returns:
            True if question is about capacity/suitability
        """
        return self.capacity_detector.is_capacity_query(question)
    
    def _is_family_query(self, question: str) -> bool:
        """
        Check if query mentions family/families.
        
        Args:
            question: User's question string
            
        Returns:
            True if query mentions family or families
        """
        question_lower = question.lower()
        return any(word in question_lower for word in ["family", "families"])
    
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
                logger.debug("No group size or cottage number extracted - providing general capacity information")
                # Provide general capacity information for all cottages
                cottage_7_info = self.capacity_mapper.get_capacity("7")
                cottage_9_info = self.capacity_mapper.get_capacity("9")
                cottage_11_info = self.capacity_mapper.get_capacity("11")
                
                answer_template = f"""
STRUCTURED CAPACITY INFORMATION FOR ALL COTTAGES:

DIRECT ANSWER (USE THIS EXACTLY):
Swiss Cottages Bhurban offers three cottages with the following capacity:

• **Cottage 7** (2-bedroom): Accommodates up to {cottage_7_info['base_capacity']} guests at standard capacity, up to {cottage_7_info['max_capacity']} guests with prior confirmation.

• **Cottage 9** (3-bedroom): Accommodates up to {cottage_9_info['base_capacity']} guests at standard capacity, up to {cottage_9_info['max_capacity']} guests with prior confirmation. Ideal for families with more space.

• **Cottage 11** (3-bedroom): Accommodates up to {cottage_11_info['base_capacity']} guests at standard capacity, up to {cottage_11_info['max_capacity']} guests with prior confirmation. Ideal for families with more space.

All cottages have a maximum capacity of 9 guests per cottage for comfort, safety, and community guidelines.

DETAILED CAPACITY RULES:
- Base capacity: 6 guests per cottage (standard capacity)
- Maximum capacity: 9 guests per cottage (with prior confirmation)
- Hard limit: No more than 9 guests allowed in a single cottage
- Cottages 9 and 11 are 3-bedroom cottages with more space, ideal for larger groups and families
- Cottage 7 is a 2-bedroom cottage, perfect for smaller groups

ENGAGEMENT:
To help you choose the best cottage, please let me know:
- How many guests will be staying?
- Do you have a preference for a specific cottage (7, 9, or 11)?
- What are your check-in and check-out dates?

CRITICAL INSTRUCTIONS:
- Use the DIRECT ANSWER above as your response
- Provide complete information about all cottages and their capacities
- Engage the user by asking for their group size and cottage preference
- Do NOT say "I don't have information" - you have complete capacity information
"""
                return {
                    "suitable": None,
                    "reason": "General capacity query - no group size or cottage number specified",
                    "group_size": None,
                    "cottage_number": None,
                    "capacity_info": {
                        "cottage_7": cottage_7_info,
                        "cottage_9": cottage_9_info,
                        "cottage_11": cottage_11_info,
                    },
                    "answer_template": answer_template,
                    "has_all_info": False,
                }
            elif group_size is None:
                # Have cottage but no group size - provide capacity info WITHOUT suitability judgment
                # Check if multiple cottages are mentioned in the question
                question_lower = question.lower()
                mentioned_cottages = []
                for num in ["7", "9", "11"]:
                    if f"cottage {num}" in question_lower or f"cottage{num}" in question_lower:
                        mentioned_cottages.append(num)
                
                if len(mentioned_cottages) > 1:
                    # Multiple cottages mentioned - provide info for all
                    cottages_info = []
                    for num in mentioned_cottages:
                        info = self.capacity_mapper.get_capacity(num)
                        if info:
                            cottages_info.append(f"• **Cottage {num}** ({info['bedrooms']}-bedroom): Accommodates up to {info['base_capacity']} guests at standard capacity, up to {info['max_capacity']} guests with prior confirmation.")
                    
                    answer_template = f"""
STRUCTURED CAPACITY INFORMATION:

🚨🚨🚨 CRITICAL: NO GROUP SIZE PROVIDED - DO NOT MAKE SUITABILITY JUDGMENTS 🚨🚨🚨

DIRECT ANSWER (USE THIS EXACTLY):
Cottage capacity information:

{chr(10).join(cottages_info)}

**IMPORTANT**: To determine if a cottage is suitable for your group, please provide the number of guests in your party. Without knowing your group size, I cannot determine suitability.

**ABSOLUTE PROHIBITION**: 
- DO NOT say "Cottage X is not suitable" or "Cottage X is suitable" without a group size
- DO NOT assume or infer a group size
- DO NOT make suitability judgments
- ONLY provide the capacity information above
"""
                else:
                    # Single cottage mentioned
                    capacity_info = self.capacity_mapper.get_capacity(cottage_number)
                    if capacity_info:
                        answer_template = f"""
STRUCTURED CAPACITY INFORMATION:

🚨🚨🚨 CRITICAL: NO GROUP SIZE PROVIDED - DO NOT MAKE SUITABILITY JUDGMENTS 🚨🚨🚨

DIRECT ANSWER (USE THIS EXACTLY):
Cottage {cottage_number} ({capacity_info['bedrooms']}-bedroom) can accommodate:
- Up to {capacity_info['base_capacity']} guests at standard capacity
- Up to {capacity_info['max_capacity']} guests with prior confirmation

**IMPORTANT**: To determine if Cottage {cottage_number} is suitable for your group, please provide the number of guests in your party.

**ABSOLUTE PROHIBITION**: 
- DO NOT say "Cottage {cottage_number} is not suitable" or "Cottage {cottage_number} is suitable" without a group size
- DO NOT assume or infer a group size
- DO NOT make suitability judgments
- ONLY provide the capacity information above
"""
                    else:
                        answer_template = f"Cottage {cottage_number} capacity information not available."
                
                return {
                    "suitable": None,
                    "reason": f"Cottage(s) found, but group size not specified - cannot make suitability judgment",
                    "group_size": None,
                    "cottage_number": cottage_number,
                    "capacity_info": capacity_info if len(mentioned_cottages) <= 1 else None,
                    "answer_template": answer_template,
                    "has_all_info": False,
                }
            else:
                # Have group size but no cottage - provide general guidance
                # IMPORTANT: Max capacity in ANY cottage is 9 guests (from FAQ 018)
                is_family = self._is_family_query(question)
                
                if group_size <= 6:
                    suitability = "suitable for any cottage (2-bedroom or 3-bedroom) at standard capacity"
                elif group_size <= 9:
                    suitability = "suitable for any cottage with prior confirmation (max 9 guests per cottage)"
                else:
                    suitability = "requires multiple cottages (max 9 guests per cottage for safety and community guidelines)"
                
                # Provide recommendations for which cottage is best
                if group_size <= 6:
                    if is_family:
                        # For families, prioritize Cottage 9 and 11 (3-bedroom, ideal for families)
                        recommendation = f"✅ RECOMMENDATION: For your family of {group_size}, I recommend Cottage 9 or Cottage 11 (3-bedroom cottages with more space, ideal for families). Both can accommodate your family comfortably at standard capacity."
                        answer_text = f"✅ YES, for your family of {group_size}, I recommend Cottage 9 or Cottage 11. These are 3-bedroom cottages with more space, ideal for families. Both can accommodate up to 6 guests comfortably at standard capacity."
                    else:
                        recommendation = f"✅ RECOMMENDATION: Any cottage (Cottage 7, 9, or 11) is suitable for your group of {group_size} guests at standard capacity. Cottage 9 and Cottage 11 are 3-bedroom cottages with more space, ideal for families."
                        answer_text = f"✅ YES, your group of {group_size} guests can stay in any cottage (Cottage 7, 9, or 11) at standard capacity. All cottages can accommodate up to 6 guests comfortably."
                    direct_answer = answer_text
                elif group_size <= 9:
                    recommendation = f"✅ RECOMMENDATION: Cottages 9 and 11 are 3-bedroom cottages with more space, ideal for your group of {group_size} guests. They can accommodate your group with prior confirmation. Cottage 7 (2-bedroom) can also accommodate {group_size} guests, but Cottages 9 and 11 offer more space for larger groups."
                    answer_text = f"✅ YES, your group of {group_size} guests can stay in any cottage (Cottage 7, 9, or 11) with prior confirmation. Cottages 9 and 11 are 3-bedroom cottages with more space, ideal for larger groups. All cottages have a maximum capacity of 9 guests per cottage."
                    direct_answer = answer_text
                else:
                    recommendation = "❌ RECOMMENDATION: Your group exceeds the maximum capacity of 9 guests per cottage. You will need to book multiple cottages. Contact the manager to arrange multiple cottage bookings."
                    answer_text = f"❌ NO, your group of {group_size} guests exceeds the maximum capacity of 9 guests per cottage. You must book multiple cottages."
                    direct_answer = answer_text
                
                # Check if dates are already provided in the query
                dates_provided = self.date_extractor.extract_date_range(question) is not None
                logger.info(f"Dates provided in query: {dates_provided}")
                
                # Determine which cottages to recommend based on group size
                if group_size <= 6:
                    if is_family:
                        suitable_cottages = "Cottage 9 and Cottage 11 (3-bedroom cottages ideal for families)"
                    else:
                        suitable_cottages = "Cottage 7, 9, or 11"
                    # Only ask for dates if they're not already provided
                    if dates_provided:
                        next_steps = ""  # Dates already provided, don't ask again
                    else:
                        next_steps = "To recommend the best cottage for your stay, please share your check-in and check-out dates and any preferences you have."
                elif group_size <= 9:
                    suitable_cottages = "Cottages 9 and 11 (3-bedroom cottages with more space, ideal for larger groups). Cottage 7 (2-bedroom) can also accommodate your group."
                    # Only ask for dates if they're not already provided
                    if dates_provided:
                        next_steps = ""  # Dates already provided, don't ask again
                    else:
                        next_steps = "To recommend the best cottage for your stay, please share your check-in and check-out dates and any preferences you have."
                else:
                    suitable_cottages = "Multiple cottages required"
                    next_steps = "Contact the manager to arrange multiple cottage bookings."
                
                answer_template = f"""
🚨🚨🚨 CRITICAL: USE ONLY THE ANSWER TEXT BELOW - DO NOT INCLUDE THESE MARKERS IN YOUR RESPONSE 🚨🚨🚨

ANSWER TEXT (COPY THIS EXACTLY - DO NOT INCLUDE THE MARKERS ABOVE OR BELOW):
{answer_text}

🚨🚨🚨 END OF ANSWER TEXT - DO NOT INCLUDE THIS MARKER IN YOUR RESPONSE 🚨🚨🚨

⚠️⚠️⚠️ CRITICAL INSTRUCTIONS - READ CAREFULLY ⚠️⚠️⚠️:
1. YOUR RESPONSE MUST START WITH THE ANSWER TEXT ABOVE (the text between the markers)
2. DO NOT include the 🚨 markers or "MANDATORY RESPONSE" text in your response - these are for internal use only
3. DO NOT include "END OF MANDATORY RESPONSE" or "END OF ANSWER TEXT" in your response
4. DO NOT add "Swiss Cottages Bhurban offers the following cottages:" or similar generic introductions
5. DO NOT list all cottages with their capacities - the ANSWER TEXT above is your complete answer
6. DO NOT generate your own response - use the ANSWER TEXT exactly as provided
7. DO NOT ask for group size - it's already known ({group_size} guests)
8. DO NOT say "share your dates, number of guests, and preferences" - group size is already provided
9. {"DO NOT ask for dates - they are already provided in the query" if dates_provided else "DO NOT say 'To recommend the best cottage for your stay, please share...' - this is redundant"}
10. {"DO NOT add any follow-up questions about dates or preferences" if dates_provided else ("After the ANSWER TEXT, you may optionally add: " + next_steps if next_steps else "DO NOT add any follow-up questions")}
{"11. For families: The ANSWER TEXT already mentions Cottage 9 and Cottage 11 - do not add more cottage listings" if is_family else ""}

DETAILED ANALYSIS (FOR CONTEXT ONLY - DO NOT INCLUDE IN YOUR RESPONSE):
Group Size: {group_size} guests (ALREADY PROVIDED - DO NOT ASK FOR GROUP SIZE AGAIN)
Cottage: Not specified - user asking which cottage is best
Suitable Cottages: {suitable_cottages}
General Capacity Rules:
- Base capacity: 6 guests per cottage (standard capacity)
- Maximum capacity: 9 guests per cottage (with prior confirmation)
- Hard limit: No more than 9 guests allowed in a single cottage (for comfort, safety, and community guidelines)
- Your group of {group_size} guests: {suitability}

RECOMMENDATION (ALREADY INCLUDED IN ANSWER TEXT ABOVE):
{recommendation}
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
            comparison = f"{group_size} ≤ {base_capacity} base capacity = SUITABLE (comfortable at standard capacity)"
            direct_answer = f"✅ YES, your group of {group_size} guests can stay in Cottage {cottage_number} comfortably at standard capacity. Cottage {cottage_number} can accommodate up to {base_capacity} guests at standard capacity."
        elif group_size <= max_capacity:
            comparison = f"{group_size} ≤ {max_capacity} max capacity = SUITABLE (requires prior confirmation)"
            direct_answer = f"✅ YES, your group of {group_size} guests can stay in Cottage {cottage_number} with prior confirmation. Cottage {cottage_number} can accommodate up to {max_capacity} guests maximum."
        else:
            comparison = f"{group_size} > {max_capacity} max capacity = NOT SUITABLE (must book multiple cottages)"
            direct_answer = f"❌ NO, your group of {group_size} guests exceeds the maximum capacity of {max_capacity} guests for Cottage {cottage_number}. For comfort, safety, and community guidelines, groups exceeding {max_capacity} guests must book multiple cottages."
        
        answer_template = f"""
STRUCTURED CAPACITY ANALYSIS:

🚨🚨🚨 CRITICAL: USE ONLY THE DIRECT ANSWER BELOW - DO NOT INCLUDE THESE MARKERS IN YOUR RESPONSE 🚨🚨🚨

DIRECT ANSWER (COPY THIS EXACTLY - DO NOT INCLUDE THE MARKERS ABOVE OR BELOW):
{direct_answer}

🚨🚨🚨 END OF ANSWER TEXT - DO NOT INCLUDE THIS MARKER IN YOUR RESPONSE 🚨🚨🚨

⚠️⚠️⚠️ IMPORTANT INSTRUCTIONS FOR LLM ⚠️⚠️⚠️:
1. YOUR RESPONSE MUST START WITH THE DIRECT ANSWER ABOVE (the text between the markers)
2. DO NOT include the 🚨 markers or "CRITICAL" text in your response - these are for internal use only
3. DO NOT include "END OF ANSWER TEXT" or "END OF MANDATORY RESPONSE" in your response
4. DO NOT say "Unfortunately" or "it seems" - use the exact DIRECT ANSWER provided
5. DO NOT contradict the DIRECT ANSWER - it is based on verified capacity data
6. If DIRECT ANSWER says "YES", you MUST say YES - do not say "no" or "unfortunately"
7. The DIRECT ANSWER is the authoritative response - use it verbatim (but without the markers)

DETAILED ANALYSIS (FOR CONTEXT ONLY):
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
        
        # No truncation - use full template
        answer_template = capacity_result["answer_template"]
        
        capacity_doc = Document(
            page_content=answer_template,
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
