"""Slot management for conversation state tracking."""

import re
from typing import Dict, List, Optional, Any, TYPE_CHECKING, Union
from datetime import datetime
from helpers.log import get_logger
from bot.conversation.number_extractor import NumberExtractor, ExtractGroupSize, ExtractCottageNumber

if TYPE_CHECKING:
    from bot.client.lama_cpp_client import LamaCppClient
    from bot.client.groq_client import GroqClient
    from bot.conversation.intent_router import IntentType

logger = get_logger(__name__)


# Slot definitions with metadata
SLOT_DEFINITIONS = {
    "guests": {
        "type": "integer",
        "required_for": ["pricing", "booking", "availability", "rooms"],
        "priority": 1,
        "extraction_keywords": ["guests", "people", "members", "persons", "group size", "group of"],
        "validation": lambda x: isinstance(x, int) and 1 <= x <= 9,
        "default": None,
    },
    "room_type": {
        "type": "enum",
        "values": ["cottage_7", "cottage_9", "cottage_11", "any"],
        "required_for": ["pricing", "booking", "availability", "rooms"],
        "priority": 2,
        "extraction_keywords": ["cottage", "room", "property"],
        "validation": lambda x: x in ["cottage_7", "cottage_9", "cottage_11", "any"] if x else True,
        "default": None,
    },
    "dates": {
        "type": "date_range",
        "required_for": ["pricing", "booking", "availability"],
        "priority": 3,
        "extraction_keywords": ["dates", "check-in", "check-out", "stay", "from", "to", "arrival", "departure"],
        "validation": lambda x: True,  # Date validation would be more complex
        "default": None,
    },
    "family": {
        "type": "boolean",
        "required_for": ["booking"],
        "priority": 4,
        "extraction_keywords": ["family", "friends", "with kids", "children", "kids"],
        "validation": lambda x: isinstance(x, bool) if x is not None else True,
        "default": None,
    },
    "season": {
        "type": "enum",
        "values": ["weekday", "weekend", "peak", "off-peak"],
        "required_for": ["pricing"],
        "priority": 5,
        "extraction_keywords": ["weekday", "weekend", "peak", "season", "off-peak"],
        "validation": lambda x: x in ["weekday", "weekend", "peak", "off-peak"] if x else True,
        "default": None,
    },
    "nights": {
        "type": "integer",
        "required_for": ["pricing", "booking"],
        "priority": 4,
        "extraction_keywords": ["nights", "nights stay", "stay", "days"],
        "validation": lambda x: isinstance(x, int) and x > 0 if x else True,
        "default": None,
    },
    "budget": {
        "type": "optional",
        "required_for": [],
        "priority": 6,
        "extraction_keywords": ["budget", "price", "cost", "afford"],
        "validation": lambda x: True,
        "default": None,
    },
    "preferences": {
        "type": "optional",
        "required_for": [],
        "priority": 7,
        "extraction_keywords": ["prefer", "like", "want", "need"],
        "validation": lambda x: True,
        "default": None,
    },
}


class SlotManager:
    """Manages short-term memory for slots across conversation."""
    
    def __init__(self, session_id: str, llm: Optional[Union["LamaCppClient", "GroqClient", Any]] = None):
        """
        Initialize the slot manager.
        
        Args:
            session_id: Unique session identifier
            llm: Optional LLM client for complex slot extraction
        """
        self.session_id = session_id
        self.llm = llm
        self.slots: Dict[str, Any] = {}
        self.slot_history: List[Dict[str, Any]] = []  # Track when slots were filled
        
        # Initialize extractors
        self.number_extractor = NumberExtractor()
        self.group_size_extractor = ExtractGroupSize()
        self.cottage_extractor = ExtractCottageNumber()
    
    def extract_slots(self, query: str, intent: "IntentType") -> Dict[str, Any]:
        """
        Extract slots from user query using pattern matching + LLM.
        
        Args:
            query: User query string
            intent: Detected intent type
            
        Returns:
            Dictionary of extracted slots
        """
        extracted = {}
        query_lower = query.lower()
        
        # Extract guests (group size)
        if "guests" not in self.slots or self.slots["guests"] is None:
            group_size = self.group_size_extractor.extract_group_size(query)
            if group_size:
                extracted["guests"] = group_size
                logger.debug(f"Extracted guests slot: {group_size}")
        
        # Extract room_type (cottage number)
        if "room_type" not in self.slots or self.slots["room_type"] is None:
            cottage_num = self.cottage_extractor.extract_cottage_number(query)
            if cottage_num:
                # Map cottage number to room_type enum
                if cottage_num == "7":
                    extracted["room_type"] = "cottage_7"
                elif cottage_num == "9":
                    extracted["room_type"] = "cottage_9"
                elif cottage_num == "11":
                    extracted["room_type"] = "cottage_11"
                else:
                    extracted["room_type"] = "any"
                logger.debug(f"Extracted room_type slot: {extracted['room_type']}")
        
        # Extract dates (enhanced pattern matching for various date formats)
        if "dates" not in self.slots or self.slots["dates"] is None:
            date_patterns = [
                # Standard date formats: "from 2/6/2024 to 5/6/2024"
                r"(?:from|arrival|check-in|starting)\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
                r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s+(?:to|until|till|check-out|departure)",
                r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s+to\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
                # Natural language: "from 2 to 6 feb", "from 2 to 6 february"
                r"(?:from|arrival|check-in|starting)\s+(\d{1,2})\s+to\s+(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|may|june|july|august|september|october|november|december)",
                # "next week from X to Y"
                r"next\s+week\s+(?:from|arrival|check-in|starting)?\s*(\d{1,2})\s+to\s+(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|may|june|july|august|september|october|november|december)",
                # "from X to Y [month]" without "from" keyword
                r"(\d{1,2})\s+to\s+(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|may|june|july|august|september|october|november|december)",
            ]
            for pattern in date_patterns:
                match = re.search(pattern, query_lower)
                if match:
                    if len(match.groups()) == 2:
                        # Extract both start and end dates
                        start_date = match.group(1)
                        end_date = match.group(2)
                        # If month name is in the match, construct full date string
                        if any(month in query_lower[match.start():match.end()] for month in ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]):
                            # Find month name in the match
                            month_match = re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|may|june|july|august|september|october|november|december)", query_lower[match.start():match.end()])
                            if month_match:
                                month = month_match.group(1)
                                extracted["dates"] = {"start": f"{start_date} {month}", "end": f"{end_date} {month}"}
                            else:
                                extracted["dates"] = {"start": start_date, "end": end_date}
                        else:
                            extracted["dates"] = {"start": start_date, "end": end_date}
                    else:
                        extracted["dates"] = {"start": match.group(1), "end": None}
                    logger.debug(f"Extracted dates slot: {extracted['dates']}")
                    break
        
        # Extract family (boolean)
        if "family" not in self.slots or self.slots["family"] is None:
            family_keywords = ["family", "with kids", "children", "kids", "child"]
            friends_keywords = ["friends", "colleagues", "group"]
            
            # Check for "in which X are children" pattern
            if re.search(r"in\s+which\s+\d+\s+are\s+(?:children|kids|child)", query_lower):
                extracted["family"] = True
                logger.debug("Extracted family slot: True (from 'in which X are children' pattern)")
            elif any(keyword in query_lower for keyword in family_keywords):
                extracted["family"] = True
                logger.debug("Extracted family slot: True")
            elif any(keyword in query_lower for keyword in friends_keywords):
                extracted["family"] = False
                logger.debug("Extracted family slot: False")
        
        # Extract season
        if "season" not in self.slots or self.slots["season"] is None:
            if "weekday" in query_lower or "week day" in query_lower:
                extracted["season"] = "weekday"
            elif "weekend" in query_lower or "week end" in query_lower:
                extracted["season"] = "weekend"
            elif "peak" in query_lower:
                extracted["season"] = "peak"
            elif "off-peak" in query_lower or "off peak" in query_lower:
                extracted["season"] = "off-peak"
            
            if "season" in extracted:
                logger.debug(f"Extracted season slot: {extracted['season']}")
        
        # Extract number of nights
        if "nights" not in self.slots or self.slots["nights"] is None:
            nights_patterns = [
                r"if\s+stay\s+(\d+)\s+nights?",
                r"stay\s+(\d+)\s+nights?",
                r"(\d+)\s+nights?\s+stay",
                r"(\d+)\s+nights?",
                r"for\s+(\d+)\s+nights?",
                r"(\d+)\s+days?\s+stay",
                r"stay\s+(\d+)\s+days?",
            ]
            for pattern in nights_patterns:
                match = re.search(pattern, query_lower)
                if match:
                    try:
                        nights = int(match.group(1))
                        if nights > 0:
                            extracted["nights"] = nights
                            logger.debug(f"Extracted nights slot: {nights}")
                            break
                    except (ValueError, IndexError):
                        continue
        
        # Use LLM for complex extraction if available
        if self.llm and (not extracted or len(extracted) < 2):
            llm_extracted = self._extract_slots_with_llm(query, intent)
            # Merge LLM results, preferring pattern matching results
            for key, value in llm_extracted.items():
                if key not in extracted and value is not None:
                    extracted[key] = value
        
        return extracted
    
    def _extract_slots_with_llm(self, query: str, intent: "IntentType") -> Dict[str, Any]:
        """
        Use LLM to extract slots from complex queries.
        
        Args:
            query: User query string
            intent: Detected intent type
            
        Returns:
            Dictionary of extracted slots
        """
        if not self.llm:
            return {}
        
        # Get required slots for this intent
        required_slots = self.get_required_slots(intent)
        
        prompt = f"""Extract relevant information from the user query for a Swiss Cottages booking system.

User query: "{query}"
Detected intent: {intent.value if hasattr(intent, 'value') else str(intent)}

Extract the following information if mentioned:
- guests: number of guests/people/members (integer 1-9)
- room_type: cottage number (7, 9, 11, or "any")
- dates: check-in and check-out dates (format: start_date to end_date)
- family: true if for family/with kids, false if for friends/colleagues
- season: weekday, weekend, peak, or off-peak

Respond in JSON format with only the fields that are explicitly mentioned:
{{
  "guests": <integer or null>,
  "room_type": "<cottage_7|cottage_9|cottage_11|any|null>",
  "dates": {{"start": "<date>", "end": "<date>"}} or null,
  "family": <true|false|null>,
  "season": "<weekday|weekend|peak|off-peak|null>"
}}

Only include fields that are clearly mentioned in the query. Return null for fields not mentioned."""
        
        try:
            response = self.llm.generate_answer(prompt, max_new_tokens=256)
            # Parse JSON response (simplified - would need proper JSON parsing)
            # For now, return empty dict - can be enhanced
            logger.debug(f"LLM slot extraction response: {response[:200]}")
            return {}
        except Exception as e:
            logger.warning(f"LLM slot extraction failed: {e}")
            return {}
    
    def update_slots(self, extracted_slots: Dict[str, Any]) -> None:
        """
        Update slot memory with extracted slots.
        
        Args:
            extracted_slots: Dictionary of extracted slots
        """
        for slot_name, slot_value in extracted_slots.items():
            if slot_name in SLOT_DEFINITIONS:
                # Validate slot value
                validator = SLOT_DEFINITIONS[slot_name].get("validation")
                if validator and slot_value is not None:
                    if not validator(slot_value):
                        logger.warning(f"Invalid slot value for {slot_name}: {slot_value}")
                        continue
                
                # Update slot
                old_value = self.slots.get(slot_name)
                self.slots[slot_name] = slot_value
                
                # Track in history
                if old_value != slot_value:
                    self.slot_history.append({
                        "slot": slot_name,
                        "value": slot_value,
                        "timestamp": datetime.now().isoformat(),
                    })
                    logger.info(f"Updated slot {slot_name}: {old_value} -> {slot_value}")
    
    def get_required_slots(self, intent: "IntentType") -> List[str]:
        """
        Get list of required slots for an intent.
        
        Args:
            intent: Intent type
            
        Returns:
            List of required slot names
        """
        intent_name = intent.value if hasattr(intent, 'value') else str(intent)
        required = []
        
        for slot_name, slot_def in SLOT_DEFINITIONS.items():
            if intent_name in slot_def.get("required_for", []):
                required.append(slot_name)
        
        # Sort by priority
        required.sort(key=lambda s: SLOT_DEFINITIONS[s]["priority"])
        return required
    
    def get_missing_slots(self, intent: "IntentType") -> List[str]:
        """
        Return list of missing required slots for intent, sorted by priority.
        
        Args:
            intent: Intent type
            
        Returns:
            List of missing slot names, sorted by priority
        """
        required_slots = self.get_required_slots(intent)
        missing = []
        
        for slot_name in required_slots:
            if slot_name not in self.slots or self.slots[slot_name] is None:
                missing.append(slot_name)
        
        # Already sorted by priority from get_required_slots
        return missing
    
    def get_most_important_missing_slot(self, intent: "IntentType") -> Optional[str]:
        """
        Get the highest priority missing slot.
        
        Args:
            intent: Intent type
            
        Returns:
            Slot name or None if no missing slots
        """
        missing = self.get_missing_slots(intent)
        return missing[0] if missing else None
    
    def has_enough_booking_info(self) -> bool:
        """
        Check if enough information is available for booking nudge.
        
        Returns:
            True if enough slots filled for booking
        """
        booking_slots = ["guests", "dates", "room_type"]
        filled_count = sum(1 for slot in booking_slots if slot in self.slots and self.slots[slot] is not None)
        return filled_count >= 2  # At least 2 out of 3 key slots
    
    def clear_slots(self) -> None:
        """Clear all slots (e.g., after booking completion)."""
        self.slots.clear()
        self.slot_history.clear()
        logger.info(f"Cleared all slots for session {self.session_id}")
    
    def get_slots(self) -> Dict[str, Any]:
        """Get current slot values."""
        return self.slots.copy()
    
    def get_slot(self, slot_name: str) -> Any:
        """Get value of a specific slot."""
        return self.slots.get(slot_name)
    
    def set_slot(self, slot_name: str, slot_value: Any) -> None:
        """Manually set a slot value."""
        if slot_name in SLOT_DEFINITIONS:
            validator = SLOT_DEFINITIONS[slot_name].get("validation")
            if validator and slot_value is not None:
                if not validator(slot_value):
                    logger.warning(f"Invalid slot value for {slot_name}: {slot_value}")
                    return
            
            self.slots[slot_name] = slot_value
            logger.debug(f"Manually set slot {slot_name} to {slot_value}")


def get_slot_manager(session_id: str, llm: Optional[Union["LamaCppClient", "GroqClient", Any]] = None) -> SlotManager:
    """
    Get or create a slot manager for a session.
    
    Args:
        session_id: Session identifier
        llm: Optional LLM client
        
    Returns:
        SlotManager instance
    """
    # This will be integrated with SessionManager later
    # For now, create a new instance (will be cached in SessionManager)
    return SlotManager(session_id, llm)
