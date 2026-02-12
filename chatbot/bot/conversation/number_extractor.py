"""Number extraction utilities for capacity queries."""

import re
from typing import Optional
from helpers.log import get_logger

logger = get_logger(__name__)


class ExtractGroupSize:
    """Extract group size (number of people/members/guests) from questions."""
    
    @staticmethod
    def extract_group_size(question: str) -> Optional[int]:
        """
        Extract number of people/members/guests from a question.
        
        Patterns:
        - "6 members"
        - "we are 6"
        - "group of 6"
        - "6 people"
        - "6 guests"
        - "for 6"
        - "6 person"
        
        Args:
            question: User's question string
            
        Returns:
            Group size as integer, or None if not found
        """
        question_lower = question.lower()
        
        # CRITICAL: First check if any numbers are clearly cottage numbers
        # Extract all cottage numbers mentioned to exclude them from group size extraction
        cottage_numbers = re.findall(r"cottage\s*(?:number|no|#)?\s*(\d+)", question_lower)
        
        # Pattern 1: "6 members", "6 people", "6 guests", "6 person"
        # IMPORTANT: More specific patterns should come first
        patterns = [
            # Pattern for "we are 6 guest" or "we are 6 guests" - number followed by guest/guests (MOST SPECIFIC)
            r"(?:we\s+are|group\s+of|party\s+of)\s+(\d+)\s+(?:guest|guests|member|members|people|person)",
            r"(\d+)\s*(?:members?|people|guests?|persons?|person)",
            # Pattern for "we are family of 5" (without "a") - must come before generic "we are" pattern
            r"we\s+are\s+family\s+of\s+(\d+)",  # "we are family of 5" pattern
            r"(?:we\s+are|group\s+of|party\s+of|with)\s+(\d+)",
            r"group\s+(\d+)",  # "group 7" pattern
            r"family\s+of\s+(\d+)",  # "family of 7" pattern
            r"(\d+)\s*(?:member|people|guest|person)",
            r"for\s+(\d+)",
            r"(\d+)\s*(?:of\s+us|people|guests)",
            # Pattern for "we are 6 in which 2 are children" - extract the first number (total)
            r"we\s+are\s+(\d+)\s+(?:in\s+which|where|of\s+which)",
            r"(\d+)\s+(?:in\s+which|where|of\s+which)\s+\d+",
            r"we\s+are\s+a\s+(?:group|family)\s+of\s+(\d+)",  # "we are a group of 7" or "we are a family of 7"
            r"we\s+are\s+a\s+group\s+(\d+)",  # "we are a group 7"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, question_lower)
            if match:
                try:
                    size = int(match.group(1))
                    # CRITICAL: Exclude if this number is a cottage number
                    if str(size) in cottage_numbers:
                        logger.debug(f"Skipping {size} - it's a cottage number, not group size")
                        continue
                    # Sanity check: reasonable group size (1-50)
                    if 1 <= size <= 50:
                        logger.info(f"Extracted group size: {size} from pattern: {pattern} (question: '{question[:100]}')")
                        return size
                except (ValueError, IndexError):
                    continue
        
        # Pattern 2: Look for numbers near capacity-related words
        capacity_words = ["accommodate", "fit", "suit", "capacity", "stay", "book"]
        for word in capacity_words:
            # Find number before or after the word
            before_pattern = rf"(\d+)\s+{word}"
            after_pattern = rf"{word}\s+(\d+)"
            
            for pattern in [before_pattern, after_pattern]:
                match = re.search(pattern, question_lower)
                if match:
                    try:
                        size = int(match.group(1))
                        # CRITICAL: Exclude if this number is a cottage number
                        if str(size) in cottage_numbers:
                            logger.debug(f"Skipping {size} - it's a cottage number, not group size")
                            continue
                        if 1 <= size <= 50:
                            logger.debug(f"Extracted group size: {size} from capacity word pattern")
                            return size
                    except (ValueError, IndexError):
                        continue
        
        logger.debug(f"Could not extract group size from: {question}")
        return None


class ExtractCottageNumber:
    """Extract cottage number from questions."""
    
    @staticmethod
    def extract_cottage_number(question: str) -> Optional[str]:
        """
        Extract cottage number from a question.
        
        CRITICAL: Only extract if "cottage" keyword is explicitly mentioned.
        Do NOT extract numbers that are clearly group sizes (e.g., "4 people" is NOT "Cottage 4").
        
        Patterns:
        - "cottage 3"
        - "cottage3"
        - "cottage number 3"
        - "cottage #3"
        - "cottage no 3"
        
        Args:
            question: User's question string
            
        Returns:
            Cottage number as string (e.g., "3", "7", "9"), or None if not found
        """
        question_lower = question.lower()
        
        # CRITICAL: Check if question mentions group size indicators - if so, don't extract as cottage
        group_size_indicators = ["people", "person", "guests", "guest", "members", "member", "group", "party"]
        has_group_size_context = any(indicator in question_lower for indicator in group_size_indicators)
        
        # Pattern 1: "cottage 3", "cottage3", "cottage number 3", "cottage #3", "this cottage 9", "that cottage 7"
        # These patterns REQUIRE "cottage" keyword, so they're safe
        patterns = [
            r"(?:this|that|the)\s+cottage\s*(?:number|no|#)?\s*(\d+)",  # "this cottage 9", "that cottage 7"
            r"cottage\s*(?:number|no|#)?\s*(\d+)",
            r"cottage(\d+)",
            r"(\d+)\s*(?:bedroom|bed)\s*cottage",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, question_lower)
            if match:
                try:
                    cottage_num = match.group(1)
                    # Sanity check: reasonable cottage number (1-20)
                    if 1 <= int(cottage_num) <= 20:
                        # Double-check: if there's group size context and number is small (1-10), 
                        # make sure "cottage" is explicitly mentioned
                        if has_group_size_context and int(cottage_num) <= 10:
                            # Check if "cottage" appears before the number in the match
                            match_start = match.start()
                            text_before = question_lower[:match_start]
                            if "cottage" not in text_before[-20:]:  # Check last 20 chars before match
                                logger.debug(f"Skipping cottage number extraction - '{cottage_num}' likely refers to group size, not cottage number")
                                continue
                        
                        logger.debug(f"Extracted cottage number: {cottage_num} from pattern: {pattern}")
                        return cottage_num
                except (ValueError, IndexError):
                    continue
        
        # Pattern 2: Look for "cottage" followed by a number within 5 words
        # Only if "cottage" keyword is present
        cottage_match = re.search(r"cottage", question_lower)
        if cottage_match:
            start_pos = cottage_match.end()
            # Look for number in next 5 words (but not if it's clearly a group size)
            next_text = question_lower[start_pos:start_pos + 30]
            num_match = re.search(r"(\d+)", next_text)
            if num_match:
                try:
                    cottage_num = num_match.group(1)
                    # Check if number is followed by group size indicators
                    num_end = num_match.end()
                    text_after_num = next_text[num_end:num_end + 15]
                    if not any(indicator in text_after_num for indicator in group_size_indicators):
                        if 1 <= int(cottage_num) <= 20:
                            logger.debug(f"Extracted cottage number: {cottage_num} from nearby text")
                            return cottage_num
                except (ValueError, IndexError):
                    pass
        
        logger.debug(f"Could not extract cottage number from: {question}")
        return None


class ExtractCapacityQuery:
    """Detect if a question is about capacity/suitability."""
    
    # Keywords that indicate capacity queries
    CAPACITY_KEYWORDS = [
        "suit", "suitable", "suitability",
        "accommodate", "accommodation",
        "fit", "fitting",
        "capacity",
        "members", "people", "guests", "person",
        "group", "party",
        "stay", "book",
        "how many", "can we", "will it",
    ]
    
    # Phrases that indicate capacity queries
    CAPACITY_PHRASES = [
        "will suit",
        "is suitable",
        "can accommodate",
        "can fit",
        "how many can",
        "good for",
        "right for",
        "enough for",
    ]
    
    @staticmethod
    def is_capacity_query(question: str) -> bool:
        """
        Check if a question is about capacity or suitability.
        
        CRITICAL: Only return True if the question EXPLICITLY asks about capacity/suitability.
        General questions like "tell me about swiss cottages" should NOT trigger this.
        
        Args:
            question: User's question string
            
        Returns:
            True if question is explicitly about capacity/suitability, False otherwise
        """
        question_lower = question.lower()
        
        # Exclude general questions that might contain capacity keywords incidentally
        general_question_patterns = [
            r"tell me about",
            r"what is",
            r"what are",
            r"describe",
            r"information about",
            r"tell me",
        ]
        
        # If it's a general question, don't treat as capacity query unless it explicitly asks about capacity
        is_general = any(re.search(pattern, question_lower) for pattern in general_question_patterns)
        
        # Check for explicit capacity phrases first (these are strong indicators)
        for phrase in ExtractCapacityQuery.CAPACITY_PHRASES:
            if phrase in question_lower:
                logger.debug(f"Detected capacity query via phrase: {phrase}")
                return True
        
        # Check for "which cottage" or "what cottage" - these are almost always capacity queries
        if "which cottage" in question_lower or "what cottage" in question_lower:
            logger.debug("Detected capacity query via 'which/what cottage'")
            return True
        
        # Check for capacity keywords, but be more strict
        # Require capacity keywords to be in context of asking about suitability/capacity
        capacity_keywords_strict = [
            "suit", "suitable", "suitability",
            "accommodate", "accommodation",
            "fit", "fitting",
            "capacity",
            "group size",  # "group size capacity", "what's the group size"
            "how many can",
            "can we",
            "will it",
            "good for",
            "right for",
            "enough for",
            "best for",  # "best for X people" is about capacity
        ]
        
        for keyword in capacity_keywords_strict:
            if keyword in question_lower:
                if re.search(rf"\b{re.escape(keyword)}\b", question_lower):
                    logger.debug(f"Detected capacity query via strict keyword: {keyword}")
                    return True
        
        # For general questions, only trigger if there's a number with people/guests/members
        # OR if it explicitly asks "which cottage" (usually about suitability)
        if is_general:
            # Check if question contains a number with group size indicators
            has_number_with_group = re.search(r"\d+\s+(people|person|guests?|members?|group)", question_lower)
            has_which_cottage = "which cottage" in question_lower or "what cottage" in question_lower
            has_best_for = "best for" in question_lower
            # Also check for "we are X", "group of X", "group X", or "family of X" patterns
            has_group_pattern = re.search(r"(we are|group of|party of|family of|group)\s+(?:a\s+)?\d+", question_lower)
            if has_number_with_group or has_which_cottage or has_best_for or has_group_pattern:
                logger.debug(f"Detected capacity query in general question: number={has_number_with_group is not None}, which_cottage={has_which_cottage}, best_for={has_best_for}, group_pattern={has_group_pattern is not None}")
                return True
            # Otherwise, don't treat general questions as capacity queries
            return False
        
        # Check for remaining capacity keywords (less strict)
        remaining_keywords = ["members", "people", "guests", "person", "group", "party", "stay", "book"]
        for keyword in remaining_keywords:
            if keyword in question_lower:
                # Only trigger if there's a number or explicit capacity question
                if re.search(rf"\b{re.escape(keyword)}\b", question_lower):
                    # Check if there's a number nearby or explicit capacity question
                    has_number = re.search(r"\d+", question_lower)
                    has_capacity_question = any(word in question_lower for word in ["how many", "can", "will", "suit", "fit"])
                    if has_number or has_capacity_question:
                        logger.debug(f"Detected capacity query via keyword with number/question: {keyword}")
                        return True
        
        return False
        
        # Check for capacity phrases
        for phrase in ExtractCapacityQuery.CAPACITY_PHRASES:
            if phrase in question_lower:
                logger.debug(f"Detected capacity query via phrase: {phrase}")
                return True
        
        # Check if question has numbers (likely capacity-related if it does)
        has_numbers = bool(re.search(r"\d+", question_lower))
        has_cottage = "cottage" in question_lower
        
        if has_numbers and has_cottage:
            # Likely asking about capacity for a specific cottage
            logger.debug("Detected capacity query: has numbers and cottage mention")
            return True
        
        return False


class NumberExtractor:
    """Combined number extractor for capacity queries."""
    
    def __init__(self):
        self.group_size_extractor = ExtractGroupSize()
        self.cottage_extractor = ExtractCottageNumber()
        self.capacity_detector = ExtractCapacityQuery()
    
    def extract_all(self, question: str) -> dict:
        """
        Extract all relevant numbers from a capacity query.
        
        CRITICAL: Cottage numbers should NOT be extracted as group sizes.
        For example, "Cottage 11" should NOT be interpreted as "11 guests".
        
        Args:
            question: User's question string
            
        Returns:
            Dictionary with keys:
            - group_size: int or None
            - cottage_number: str or None
            - is_capacity_query: bool
        """
        # First, extract cottage numbers to exclude them from group size extraction
        cottage_number = self.cottage_extractor.extract_cottage_number(question)
        
        # Extract potential group size
        potential_group_size = self.group_size_extractor.extract_group_size(question)
        
        # CRITICAL: If the extracted group size matches a cottage number mentioned in the question,
        # it's likely a false positive (e.g., "Cottage 11" being interpreted as "11 guests")
        # Check if the number appears in a cottage context
        question_lower = question.lower()
        if potential_group_size is not None:
            # Check if this number appears as a cottage number in the question
            cottage_patterns = [
                rf"cottage\s*{potential_group_size}\b",
                rf"cottage\s*number\s*{potential_group_size}\b",
                rf"cottage\s*#{potential_group_size}\b",
                rf"cottage\s*no\s*{potential_group_size}\b",
            ]
            
            is_cottage_number = any(re.search(pattern, question_lower) for pattern in cottage_patterns)
            
            # Also check if multiple cottages are mentioned (e.g., "cottage 9 and cottage 11")
            # In this case, numbers are definitely cottage numbers, not group sizes
            cottage_mentions = re.findall(r"cottage\s*(?:number|no|#)?\s*(\d+)", question_lower)
            has_multiple_cottages = len(cottage_mentions) > 1
            
            if is_cottage_number or has_multiple_cottages:
                logger.info(f"Excluding {potential_group_size} as group size - it's a cottage number (cottage={cottage_number}, mentions={cottage_mentions})")
                potential_group_size = None
        
        return {
            "group_size": potential_group_size,
            "cottage_number": cottage_number,
            "is_capacity_query": self.capacity_detector.is_capacity_query(question),
        }
