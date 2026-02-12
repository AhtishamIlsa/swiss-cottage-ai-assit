"""Slot management for conversation state tracking."""

import re
import json
from typing import Dict, List, Optional, Any, TYPE_CHECKING, Union, Tuple
from datetime import datetime
from helpers.log import get_logger
from bot.conversation.number_extractor import NumberExtractor, ExtractGroupSize, ExtractCottageNumber
from bot.conversation.date_extractor import DateExtractor, get_date_extractor

if TYPE_CHECKING:
    from bot.client.lama_cpp_client import LamaCppClient
    from bot.client.groq_client import GroqClient
    from bot.conversation.intent_router import IntentType

logger = get_logger(__name__)


# Slot definitions with metadata
SLOT_DEFINITIONS = {
    "guests": {
        "type": "integer",
        "required_for": ["booking", "availability", "rooms"],  # Removed "pricing" - guests optional for pricing (defaults to 6)
        "priority": 1,
        "extraction_keywords": ["guests", "people", "members", "persons", "group size", "group of"],
        "validation": lambda x: isinstance(x, int) and 1 <= x <= 9,
        "default": None,
    },
    "cottage_id": {
        "type": "enum",
        "values": ["cottage_7", "cottage_9", "cottage_11", "any"],
        "required_for": ["pricing", "booking", "availability", "rooms"],
        "priority": 2,
        "extraction_keywords": ["cottage", "property"],
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
        self.current_cottage: Optional[str] = None  # Track current cottage being discussed
        
        # Initialize extractors
        self.number_extractor = NumberExtractor()
        self.group_size_extractor = ExtractGroupSize()
        self.cottage_extractor = ExtractCottageNumber()
        self.date_extractor = get_date_extractor()
    
    def should_use_current_cottage(self, query: str, intent: "IntentType") -> bool:
        """
        Determine if current_cottage should be used for cottage_id slot.
        
        Only use current_cottage when:
        1. Query explicitly mentions a cottage, OR
        2. Intent requires cottage_id AND query is a specific calculation (not general info)
        
        Args:
            query: User query string
            intent: Detected intent type
            
        Returns:
            True if current_cottage should be used, False otherwise
        """
        query_lower = query.lower()
        intent_name = intent.value if hasattr(intent, 'value') else str(intent)
        
        # Check if query explicitly mentions a cottage
        if any(word in query_lower for word in ["cottage 7", "cottage 9", "cottage 11", "cottage7", "cottage9", "cottage11"]):
            return True
        
        # For general info intents (LOCATION, FACILITIES, FAQ_QUESTION), NEVER use current_cottage
        general_info_intents = ["location", "facilities", "faq_question"]
        if intent_name in general_info_intents:
            return False
        
        # Check if intent requires cottage_id
        requires_cottage = intent_name in SLOT_DEFINITIONS.get("cottage_id", {}).get("required_for", [])
        if not requires_cottage:
            return False
        
        # Only use current_cottage for specific calculations, not general info queries
        # General info patterns that should NOT use current_cottage
        general_info_patterns = [
            "what is", "what are", "tell me about", "tell me the", "explain", "describe",
            "how can", "how do", "is there", "are there", "do you have", "can i",
            "who is", "who are", "where is", "where are", "when is", "when are",
            "are", "is"  # Questions like "are restaurants nearby", "is it safe"
        ]
        
        # Check if this is a general info query (check if query starts with or contains these patterns)
        is_general_info = any(
            query_lower.startswith(pattern) or 
            (pattern in query_lower and len(query_lower.split()) <= 8)  # Short queries with these words are likely general
            for pattern in general_info_patterns
        )
        
        # If it's a general info query, don't use current_cottage
        if is_general_info:
            # Exception: if query explicitly asks "for this cottage" or "for cottage X"
            if not any(phrase in query_lower for phrase in ["for this", "for cottage", "for the cottage"]):
                return False
        
        # For specific calculations (e.g., "pricing for 4 guests", "book for dates")
        # Check if query has calculation keywords
        calculation_keywords = ["for", "with", "when", "dates", "guests", "book", "calculate", "pricing for", "cost for"]
        is_specific_calculation = any(keyword in query_lower for keyword in calculation_keywords)
        
        # Use current_cottage for specific calculations that require cottage_id
        return is_specific_calculation
    
    def should_extract_slots(self, intent: "IntentType", query: str) -> bool:
        """
        Check if query requires slot extraction (specific calculation) vs general info.
        
        General info queries don't need slots - they're asking about policies, processes, descriptions.
        Specific calculation queries need slots - they're asking for a specific price/booking.
        
        Args:
            intent: Detected intent type
            query: User query string
            
        Returns:
            True if slots should be extracted, False for general info queries
        """
        query_lower = query.lower()
        intent_name = intent.value if hasattr(intent, 'value') else str(intent)
        
        # General info patterns that don't need slots
        general_info_patterns = [
            "what is", "what are", "tell me about", "tell me the", "explain", "describe",
            "how can", "how do", "is there", "are there", "do you have", "can i",
            "who is", "who are", "where is", "where are", "when is", "when are"
        ]
        
        # Check if this is a general info query
        is_general_info = any(query_lower.startswith(pattern) for pattern in general_info_patterns)
        
        if is_general_info:
            # Check if it's asking for specific calculation (e.g., "what is pricing for 4 guests")
            calculation_keywords = ["for", "with", "when", "dates", "guests", "book", "calculate"]
            has_calculation_keywords = any(keyword in query_lower for keyword in calculation_keywords)
            
            # If it has calculation keywords, it's a specific calculation
            if has_calculation_keywords:
                return True
            
            # Otherwise, it's general info - no slots needed
            return False
        
        # Specific calculation queries need slots
        calculation_keywords = ["for", "with", "when", "dates", "guests", "book", "calculate", "pricing for", "cost for"]
        if any(keyword in query_lower for keyword in calculation_keywords):
            return True
        
        # For certain intents, always extract slots if required
        requires_slots = intent_name in ["pricing", "booking", "availability"]
        if requires_slots:
            # But still check if it's a general question
            if any(word in query_lower for word in ["what is", "what are", "tell me", "explain"]):
                # General pricing/booking question - no slots needed
                return False
        
        # Default: extract slots for pricing/booking/availability intents
        return requires_slots
    
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
                logger.info(f"✅ Extracted guests slot: {group_size}")
            else:
                # Also try LLM extraction as fallback for complex patterns
                logger.debug(f"Pattern extraction failed, will try LLM extraction if available")
        
        # Extract cottage_id (cottage number)
        cottage_num = self.cottage_extractor.extract_cottage_number(query)
        if cottage_num:
            # Update current cottage being discussed
            self.current_cottage = cottage_num
            logger.debug(f"Updated current_cottage to: {cottage_num}")
            
            # Map cottage number to cottage_id enum
            if "cottage_id" not in self.slots or self.slots["cottage_id"] is None:
                if cottage_num == "7":
                    extracted["cottage_id"] = "cottage_7"
                elif cottage_num == "9":
                    extracted["cottage_id"] = "cottage_9"
                elif cottage_num == "11":
                    extracted["cottage_id"] = "cottage_11"
                else:
                    extracted["cottage_id"] = "any"
                logger.debug(f"Extracted cottage_id slot: {extracted['cottage_id']}")
        elif self.current_cottage and self.should_use_current_cottage(query, intent):
            # Only use current_cottage if query explicitly mentions cottage or is specific calculation
            # This prevents contamination: general info queries shouldn't use current_cottage
            if "cottage_id" not in self.slots or self.slots["cottage_id"] is None:
                if self.current_cottage == "7":
                    extracted["cottage_id"] = "cottage_7"
                elif self.current_cottage == "9":
                    extracted["cottage_id"] = "cottage_9"
                elif self.current_cottage == "11":
                    extracted["cottage_id"] = "cottage_11"
                logger.debug(f"Using current_cottage {self.current_cottage} for cottage_id slot (query is specific calculation)")
            else:
                logger.debug(f"Not using current_cottage {self.current_cottage} - query is general info or cottage_id already set")
        
        # Extract dates using DateExtractor (regex-based)
        # Only extract if dates are not already in slots (persist across turns)
        if "dates" not in self.slots or self.slots["dates"] is None:
            date_range = self.date_extractor.extract_date_range(query)
            if date_range:
                # Store full date range info (including parsed dates, nights, etc.)
                extracted["dates"] = date_range
                logger.info(f"✅ Extracted dates slot: {date_range.get('start_date')} to {date_range.get('end_date')}, {date_range.get('nights')} nights")
            else:
                logger.debug(f"Could not extract dates from query: {query}")
        else:
            logger.debug(f"Dates already in slots: {self.slots['dates'].get('start_date') if isinstance(self.slots.get('dates'), dict) else 'N/A'} to {self.slots['dates'].get('end_date') if isinstance(self.slots.get('dates'), dict) else 'N/A'}")
        
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
                r"if\s+stays?\s+(\d+)\s+(?:nights?|days?)",  # "if we stays 5 days"
                r"stay\s+(\d+)\s+nights?",
                r"stays?\s+(\d+)\s+(?:nights?|days?)",  # "stays 5 days" or "stay 5 days"
                r"(\d+)\s+nights?\s+stay",
                r"(\d+)\s+nights?",
                r"for\s+(\d+)\s+nights?",
                r"(\d+)\s+days?\s+stay",
                r"stay\s+(\d+)\s+days?",
                r"(\d+)\s+days?",  # "5 days" anywhere in query
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
        
        # Use LLM for complex extraction if available (optional fallback)
        if self.llm and (not extracted or len(extracted) < 2):
            llm_extracted = self._extract_slots_with_llm(query, intent)
            # Merge LLM results, preferring pattern matching results
            for key, value in llm_extracted.items():
                if key not in extracted and value is not None:
                    extracted[key] = value
        
        return extracted
    
    def _extract_slots_with_llm(self, query: str, intent: "IntentType") -> Dict[str, Any]:
        """
        Use LLM to extract slots from complex queries, especially dates in various formats.
        
        Args:
            query: User query string
            intent: Detected intent type
            
        Returns:
            Dictionary of extracted slots
        """
        if not self.llm:
            return {}
        
        # Enhanced prompt for date extraction with various format support
        prompt = f"""Extract booking information from the user query for Swiss Cottages.

User query: "{query}"
Intent: {intent.value if hasattr(intent, 'value') else str(intent)}

Extract the following information if mentioned:
1. guests: Number of guests/people/members (1-9)
2. cottage_id: Cottage number (7, 9, 11, or "any")
3. dates: Check-in and check-out dates - CRITICAL: Extract dates ONLY if explicitly mentioned in the query.
   🚨 ABSOLUTE PROHIBITION: DO NOT generate, invent, or assume dates if the user doesn't mention any dates. Return null for dates if no dates are mentioned.
   🚨 DO NOT create example dates like "23 march" or "march 23" - only extract dates that the user actually says.
   If user says "these days" or "those dates", return null for dates (they should come from conversation context).
4. family: true if for family/with kids, false if for friends/colleagues
5. season: weekday, weekend, peak, or off-peak

🚨 CRITICAL FOR DATES: If the user does NOT mention any dates in their query, you MUST return null for dates. DO NOT create example dates or assume dates.

Respond in JSON format with only the fields that are explicitly mentioned:
{{
  "guests": <integer or null>,
  "cottage_id": "<cottage_7|cottage_9|cottage_11|any|null>",
  "dates": {{
    "start": "<start date ONLY if user mentions dates>",
    "end": "<end date ONLY if user mentions dates>",
    "raw_text": "<original date text from query ONLY if user mentions dates>"
  }} or null,
  "family": <true|false|null>,
  "season": "<weekday|weekend|peak|off-peak|null>"
}}

🚨 CRITICAL REMINDER: For dates, return null if the user does NOT mention any dates. DO NOT use example dates.

Only include fields explicitly mentioned. Return null for fields not mentioned.
IMPORTANT: Return ONLY valid JSON, no additional text before or after."""

        try:
            response = self.llm.generate_answer(prompt, max_new_tokens=512)
            logger.debug(f"LLM slot extraction raw response: {response[:300]}")
            
            # Extract JSON from response (might have extra text)
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                extracted = json.loads(json_str)
                
                # Process dates: if LLM extracted dates, use DateExtractor to parse them properly
                if extracted.get("dates") and isinstance(extracted["dates"], dict):
                    date_info = extracted["dates"]
                    start_text = date_info.get("start", "")
                    end_text = date_info.get("end", "")
                    raw_text = date_info.get("raw_text", "")
                    
                    # Try to parse dates using DateExtractor
                    date_range = None
                    
                    # First try: use start and end text if both available
                    if start_text and end_text:
                        date_query = f"{start_text} to {end_text}"
                        date_range = self.date_extractor.extract_date_range(date_query)
                    
                    # Second try: use raw text if available
                    if not date_range and raw_text:
                        date_range = self.date_extractor.extract_date_range(raw_text)
                    
                    # Third try: use original query
                    if not date_range:
                        date_range = self.date_extractor.extract_date_range(query)
                    
                    if date_range:
                        extracted["dates"] = date_range
                        logger.info(f"✅ LLM extracted and parsed dates: {date_range.get('start_date')} to {date_range.get('end_date')}")
                    else:
                        logger.warning(f"LLM extracted dates but DateExtractor couldn't parse: start={start_text}, end={end_text}, raw={raw_text}")
                        extracted["dates"] = None
                elif extracted.get("dates") is None:
                    # Dates not found by LLM - this is fine, will fallback to regex
                    logger.debug("LLM did not find dates in query")
                
                # Process cottage_id: convert to proper format
                if extracted.get("cottage_id"):
                    cottage_id = extracted["cottage_id"].lower()
                    if cottage_id in ["7", "cottage_7", "cottage 7"]:
                        extracted["cottage_id"] = "cottage_7"
                        self.current_cottage = "7"
                    elif cottage_id in ["9", "cottage_9", "cottage 9"]:
                        extracted["cottage_id"] = "cottage_9"
                        self.current_cottage = "9"
                    elif cottage_id in ["11", "cottage_11", "cottage 11"]:
                        extracted["cottage_id"] = "cottage_11"
                        self.current_cottage = "11"
                    elif cottage_id in ["any", "none", "null"]:
                        extracted["cottage_id"] = "any"
                        # Don't clear current_cottage if set to "any" - keep previous cottage
                    else:
                        extracted["cottage_id"] = None
                # Also handle legacy "room_type" key for backward compatibility
                elif extracted.get("room_type"):
                    room_type = extracted["room_type"].lower()
                    if room_type in ["7", "cottage_7", "cottage 7"]:
                        extracted["cottage_id"] = "cottage_7"
                        self.current_cottage = "7"
                    elif room_type in ["9", "cottage_9", "cottage 9"]:
                        extracted["cottage_id"] = "cottage_9"
                        self.current_cottage = "9"
                    elif room_type in ["11", "cottage_11", "cottage 11"]:
                        extracted["cottage_id"] = "cottage_11"
                        self.current_cottage = "11"
                    elif room_type in ["any", "none", "null"]:
                        extracted["cottage_id"] = "any"
                    else:
                        extracted["cottage_id"] = None
                    # Remove legacy key
                    extracted.pop("room_type", None)
                
                logger.info(f"✅ LLM extracted slots: {list(extracted.keys())}")
                return extracted
            else:
                logger.warning(f"Could not find JSON in LLM response: {response[:200]}")
                return {}
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error in LLM extraction: {e}, response: {response[:200]}")
            return {}
        except Exception as e:
            logger.warning(f"LLM slot extraction failed: {e}", exc_info=True)
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
                
                # Update current_cottage when cottage_id changes
                if slot_name == "cottage_id" and slot_value:
                    if slot_value == "cottage_7":
                        self.current_cottage = "7"
                    elif slot_value == "cottage_9":
                        self.current_cottage = "9"
                    elif slot_value == "cottage_11":
                        self.current_cottage = "11"
                    elif slot_value == "any":
                        # Don't clear current_cottage if set to "any" - keep previous cottage
                        pass
                # Handle legacy room_type for backward compatibility
                elif slot_name == "room_type" and slot_value:
                    # Migrate to cottage_id
                    if slot_value == "cottage_7":
                        self.slots["cottage_id"] = "cottage_7"
                        self.current_cottage = "7"
                    elif slot_value == "cottage_9":
                        self.slots["cottage_id"] = "cottage_9"
                        self.current_cottage = "9"
                    elif slot_value == "cottage_11":
                        self.slots["cottage_id"] = "cottage_11"
                        self.current_cottage = "11"
                    elif slot_value == "any":
                        self.slots["cottage_id"] = "any"
                    # Remove legacy key
                    self.slots.pop("room_type", None)
                
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
        booking_slots = ["guests", "dates", "cottage_id"]
        filled_count = sum(1 for slot in booking_slots if slot in self.slots and self.slots[slot] is not None)
        return filled_count >= 2  # At least 2 out of 3 key slots
    
    def clear_slots(self) -> None:
        """Clear all slots (e.g., after booking completion)."""
        self.slots.clear()
        self.slot_history.clear()
        self.current_cottage = None
        logger.info(f"Cleared all slots for session {self.session_id}")
    
    def get_slots(self) -> Dict[str, Any]:
        """Get current slot values."""
        return self.slots.copy()
    
    def get_slot(self, slot_name: str) -> Any:
        """Get value of a specific slot."""
        return self.slots.get(slot_name)
    
    def get_current_cottage(self) -> Optional[str]:
        """
        Get the current cottage number being discussed in the conversation.
        
        Returns:
            Cottage number as string (e.g., "7", "9", "11") or None if not set
        """
        return self.current_cottage
    
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
    
    def validate_slots_for_intent(self, intent: "IntentType") -> Dict[str, Any]:
        """
        Validate all required slots for an intent.
        
        Args:
            intent: Intent type
            
        Returns:
            Dictionary with keys:
            - valid: bool - Whether all required slots are present and valid
            - missing_slots: List[str] - List of missing required slot names
            - errors: List[str] - List of validation error messages
        """
        required_slots = self.get_required_slots(intent)
        missing_slots = []
        errors = []
        
        logger.info(f"Validating slots for intent {intent.value if hasattr(intent, 'value') else str(intent)}. Required: {required_slots}, Current slots: {list(self.slots.keys())}")
        
        for slot_name in required_slots:
            slot_value = self.slots.get(slot_name)
            if slot_value is None:
                missing_slots.append(slot_name)
                logger.debug(f"Missing required slot: {slot_name}")
            else:
                # Validate slot value
                slot_def = SLOT_DEFINITIONS.get(slot_name, {})
                logger.debug(f"Validating slot {slot_name}: {type(slot_value).__name__}")
                validator = slot_def.get("validation")
                
                if validator:
                    try:
                        if not validator(slot_value):
                            errors.append(f"Invalid value for {slot_name}: {slot_value}")
                    except Exception as e:
                        errors.append(f"Validation error for {slot_name}: {e}")
                
                # Special validation for dates
                if slot_name == "dates":
                    if isinstance(slot_value, dict):
                        # Check if dates were parsed successfully
                        if "parsed_start" in slot_value and "parsed_end" in slot_value:
                            # Dates are already parsed - validate the range
                            start_parsed = slot_value.get("parsed_start")
                            end_parsed = slot_value.get("parsed_end")
                            if start_parsed and end_parsed:
                                is_valid, error_msg = self.date_extractor.validate_date_range(start_parsed, end_parsed)
                                if not is_valid:
                                    errors.append(f"Invalid date range: {error_msg}")
                                else:
                                    logger.debug(f"Dates validated successfully: {slot_value.get('start_date')} to {slot_value.get('end_date')}")
                            else:
                                errors.append("Date range has None parsed dates")
                        elif "start_date" in slot_value and "end_date" in slot_value:
                            # Try to parse dates if not already parsed
                            start_parsed = self.date_extractor.parse_date_string(slot_value["start_date"])
                            end_parsed = self.date_extractor.parse_date_string(slot_value["end_date"])
                            if not start_parsed or not end_parsed:
                                errors.append(f"Could not parse date range: {slot_value.get('start_date')} to {slot_value.get('end_date')}")
                            else:
                                # Validate date range
                                is_valid, error_msg = self.date_extractor.validate_date_range(start_parsed, end_parsed)
                                if not is_valid:
                                    errors.append(f"Invalid date range: {error_msg}")
                        else:
                            errors.append(f"Date range format is invalid. Keys: {list(slot_value.keys())}")
                    else:
                        errors.append(f"Dates slot is not a dict: {type(slot_value).__name__}")
        
        return {
            "valid": len(missing_slots) == 0 and len(errors) == 0,
            "missing_slots": missing_slots,
            "errors": errors,
        }


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
