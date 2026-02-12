"""Pricing query handler for processing pricing questions."""

from typing import Dict, List, Optional
from entities.document import Document
from bot.conversation.pricing_calculator import PricingCalculator, get_pricing_calculator
from bot.conversation.number_extractor import NumberExtractor, ExtractGroupSize, ExtractCottageNumber
from helpers.log import get_logger

logger = get_logger(__name__)


class PricingQueryHandler:
    """Handles pricing queries with structured logic."""
    
    def __init__(self, pricing_calculator: Optional[PricingCalculator] = None):
        """
        Initialize the pricing query handler.
        
        Args:
            pricing_calculator: Optional PricingCalculator instance. If None, creates a new one.
        """
        self.pricing_calculator = pricing_calculator or get_pricing_calculator()
        self.number_extractor = NumberExtractor()
        self.group_size_extractor = ExtractGroupSize()
        self.cottage_extractor = ExtractCottageNumber()
    
    def _get_start_date_for_next_week(self) -> "datetime":
        """Get the start date for next week (next Monday)."""
        from datetime import datetime, timedelta
        today = datetime.now()
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7  # If today is Monday, use next Monday
        return today + timedelta(days=days_until_monday)
    
    def _calculate_weekday_weekend_breakdown(self, start_date: "datetime", end_date: "datetime") -> tuple[int, int]:
        """Calculate weekday and weekend nights breakdown."""
        from datetime import timedelta
        weekday_nights = 0
        weekend_nights = 0
        current_date = start_date
        while current_date < end_date:
            if current_date.weekday() < 5:  # Monday-Friday
                weekday_nights += 1
            else:  # Saturday-Sunday
                weekend_nights += 1
            current_date += timedelta(days=1)
        return weekday_nights, weekend_nights
    
    def _create_date_range_for_weekdays(
        self, start_date: "datetime", nights: int
    ) -> "datetime":
        """Create end date for N consecutive weekday nights starting from start_date."""
        from datetime import timedelta
        end_date = start_date
        nights_counted = 0
        while nights_counted < nights:
            if end_date.weekday() < 5:  # Monday-Friday
                nights_counted += 1
            if nights_counted < nights:
                end_date += timedelta(days=1)
        return end_date
    
    def _ensure_weekday(self, date: "datetime") -> "datetime":
        """Ensure date is a weekday (Monday-Friday)."""
        from datetime import timedelta
        while date.weekday() >= 5:  # Saturday (5) or Sunday (6)
            date += timedelta(days=1)
        return date
    
    def _create_dates_dict(
        self, start_date: "datetime", end_date: "datetime", nights: int
    ) -> Dict:
        """Create dates dictionary with proper formatting."""
        weekday_nights, weekend_nights = self._calculate_weekday_weekend_breakdown(start_date, end_date)
        return {
            "start_date": start_date.strftime("%d %b %Y"),
            "end_date": end_date.strftime("%d %b %Y"),
            "nights": nights,
            "weekday_nights": weekday_nights,
            "weekend_nights": weekend_nights,
            "parsed_start": start_date,
            "parsed_end": end_date,
        }
    
    def _load_pricing_from_faq_files(self, cottage_number: Optional[str] = None) -> Optional[str]:
        """
        Load pricing directly from FAQ files as a fallback.
        
        Args:
            cottage_number: Optional cottage number to filter pricing info
            
        Returns:
            Formatted string with general pricing rates, or None if not found
        """
        from pathlib import Path
        import re
        
        # Find FAQ directory
        # pricing_handler.py is in: chatbot/bot/conversation/
        # So parent.parent.parent = chatbot/
        # But docs/faq is at the root level, not under chatbot/
        current_file = Path(__file__).resolve()
        # Go up: conversation -> bot -> chatbot -> root
        root_dir = current_file.parent.parent.parent.parent
        faq_dir = root_dir / "docs" / "faq"
        
        if not faq_dir.exists():
            logger.warning(f"FAQ directory not found: {faq_dir}")
            return None
        
        pricing_info = []
        seen_cottages = set()
        
        # Look for pricing FAQ files
        for faq_file in sorted(faq_dir.glob("pricing_payments_faq_*.md")):
            try:
                content = faq_file.read_text(encoding='utf-8')
                content_lower = content.lower()
                
                # Extract cottage number from content
                cottage_match = re.search(r"cottage\s+(\d+)", content_lower)
                if not cottage_match:
                    continue
                
                file_cottage = cottage_match.group(1)
                
                # Check if this file is about the requested cottage
                if cottage_number:
                    if file_cottage != cottage_number:
                        continue
                else:
                    # If no specific cottage requested, collect all cottages
                    if file_cottage in seen_cottages:
                        continue
                    seen_cottages.add(file_cottage)
                
                # Extract pricing using same patterns as _extract_general_pricing_from_context
                weekend_pattern = r"(?:approximately\s+)?pkr\s+([\d,]+)\s+per\s+night\s+on\s+weekends?"
                weekday_pattern = r"(?:approximately\s+)?pkr\s+([\d,]+)\s+per\s+night\s+on\s+weekdays?"
                
                weekend_match = re.search(weekend_pattern, content_lower)
                weekday_match = re.search(weekday_pattern, content_lower)
                
                if weekend_match or weekday_match:
                    weekend_rate = weekend_match.group(1).replace(",", "") if weekend_match else None
                    weekday_rate = weekday_match.group(1).replace(",", "") if weekday_match else None
                    
                    if weekday_rate and weekend_rate:
                        cottage_info = f"Cottage {file_cottage}"
                        pricing_info.append(f"{cottage_info}: PKR {int(weekday_rate):,} per night on weekdays, PKR {int(weekend_rate):,} per night on weekends")
                        
                        # If specific cottage requested, we found it - break
                        if cottage_number:
                            break
            except Exception as e:
                logger.warning(f"Error reading FAQ file {faq_file}: {e}")
                continue
        
        if pricing_info:
            logger.info(f"Loaded pricing from FAQ files: {pricing_info}")
            return "\n".join(pricing_info)
        
        return None
    
    def _extract_general_pricing_from_context(
        self, retrieved_contents: List[Document], cottage_number: Optional[str] = None
    ) -> Optional[str]:
        """
        Extract general pricing information from retrieved documents.
        
        Args:
            retrieved_contents: List of retrieved documents
            cottage_number: Optional cottage number to filter pricing info
            
        Returns:
            Formatted string with general pricing rates, or None if not found
        """
        import re
        
        pricing_info = []
        seen_cottages = set()
        
        # Look for pricing information in documents
        for doc in retrieved_contents:
            content = doc.page_content  # Keep original case for cottage number matching
            content_lower = content.lower()
            
            # Extract cottage number from content if not specified
            cottage_in_content = None
            if not cottage_number:
                cottage_match = re.search(r"cottage\s+(\d+)", content_lower)
                if cottage_match:
                    cottage_in_content = cottage_match.group(1)
                    # Skip if we've already processed this cottage
                    if cottage_in_content in seen_cottages:
                        continue
                    seen_cottages.add(cottage_in_content)
            
            target_cottage = cottage_number or cottage_in_content
            
            # Improved regex patterns to match FAQ format:
            # "PKR 32,000 per night on weekends and PKR 26,000 per night on weekdays"
            # "PKR 38,000 per night on weekends and PKR 33,000 per night on weekdays"
            # "approximately PKR 38,000 per night on weekends and PKR 33,000 per night on weekdays"
            
            # Pattern 1: Match "PKR X,XXX per night on weekends" and "PKR X,XXX per night on weekdays"
            # Allow optional words like "approximately" before PKR
            weekend_pattern = r"(?:approximately\s+)?pkr\s+([\d,]+)\s+per\s+night\s+on\s+weekends?"
            weekday_pattern = r"(?:approximately\s+)?pkr\s+([\d,]+)\s+per\s+night\s+on\s+weekdays?"
            
            # Pattern 2: Match "PKR X,XXX per night" followed by "weekend" or "weekday" context
            weekend_pattern2 = r"weekends?.*?(?:approximately\s+)?pkr\s+([\d,]+)\s+per\s+night"
            weekday_pattern2 = r"weekdays?.*?(?:approximately\s+)?pkr\s+([\d,]+)\s+per\s+night"
            
            # Pattern 3: More flexible - match "PKR X,XXX" near "weekend/weekday" and "per night"
            weekend_pattern3 = r"pkr\s+([\d,]+).*?(?:weekends?|per\s+night.*?weekends?)"
            weekday_pattern3 = r"pkr\s+([\d,]+).*?(?:weekdays?|per\s+night.*?weekdays?)"
            
            weekday_rate = None
            weekend_rate = None
            
            # Try pattern 1 first (more specific)
            weekend_match = re.search(weekend_pattern, content_lower)
            weekday_match = re.search(weekday_pattern, content_lower)
            
            if weekend_match:
                weekend_rate = weekend_match.group(1).replace(",", "")
            if weekday_match:
                weekday_rate = weekday_match.group(1).replace(",", "")
            
            # If pattern 1 didn't work, try pattern 2
            if not weekend_rate:
                weekend_match2 = re.search(weekend_pattern2, content_lower)
                if weekend_match2:
                    weekend_rate = weekend_match2.group(1).replace(",", "")
            
            if not weekday_rate:
                weekday_match2 = re.search(weekday_pattern2, content_lower)
                if weekday_match2:
                    weekday_rate = weekday_match2.group(1).replace(",", "")
            
            # If still not found, try pattern 3 (more flexible)
            if not weekend_rate:
                weekend_match3 = re.search(weekend_pattern3, content_lower)
                if weekend_match3:
                    weekend_rate = weekend_match3.group(1).replace(",", "")
            
            if not weekday_rate:
                weekday_match3 = re.search(weekday_pattern3, content_lower)
                if weekday_match3:
                    weekday_rate = weekday_match3.group(1).replace(",", "")
            
            # If cottage-specific query, verify cottage number matches
            # But be lenient - if we have a cottage number, prioritize matching documents but don't skip all
            if cottage_number:
                # Check if this document is about the requested cottage
                # Look for "Cottage 9" or "cottage 9" (case-insensitive)
                cottage_mentioned = re.search(rf"cottage\s+{cottage_number}\b", content_lower, re.IGNORECASE)
                # Also check in original case content for better matching
                cottage_mentioned_original = re.search(rf"cottage\s+{cottage_number}\b", content, re.IGNORECASE)
                
                if not cottage_mentioned and not cottage_mentioned_original:
                    # If we already found pricing for this cottage, skip non-matching docs
                    # Otherwise, continue searching (might find it in other docs)
                    if pricing_info and any(f"Cottage {cottage_number}" in info or f"cottage {cottage_number}" in info.lower() for info in pricing_info):
                        continue  # Already found pricing for this cottage, skip others
                    # Otherwise, continue to next doc but don't add to pricing_info yet
                    # We'll add it if we find matching cottage pricing
                    continue
            
            # If found rates, format them
            if weekday_rate or weekend_rate:
                cottage_info = f"Cottage {target_cottage}" if target_cottage else "All Cottages"
                if weekday_rate and weekend_rate:
                    pricing_info.append(f"{cottage_info}: PKR {int(weekday_rate):,} per night on weekdays, PKR {int(weekend_rate):,} per night on weekends")
                elif weekday_rate:
                    pricing_info.append(f"{cottage_info}: PKR {int(weekday_rate):,} per night on weekdays")
                elif weekend_rate:
                    pricing_info.append(f"{cottage_info}: PKR {int(weekend_rate):,} per night on weekends")
        
        # If no specific rates found, look for general pricing mentions (fallback)
        # This is important for cases where pricing format doesn't match our regex
        if not pricing_info:
            for doc in retrieved_contents:
                content = doc.page_content
                content_lower = content.lower()
                
                # If cottage-specific, only look in documents about that cottage
                if cottage_number:
                    if not re.search(rf"cottage\s+{cottage_number}\b", content_lower):
                        continue
                
                # Look for pricing patterns but be more strict
                if re.search(r"pkr\s+[\d,]+", content_lower):
                    # Extract the full sentence containing pricing
                    sentences = re.split(r'[.!?]+', content)
                    for sentence in sentences:
                        if re.search(r"pkr\s+[\d,]+", sentence.lower()):
                            # Check if it's a complete pricing statement
                            if any(word in sentence.lower() for word in ["per night", "weekday", "weekend", "pricing"]):
                                pricing_info.append(sentence.strip())
                                break
                    if pricing_info:
                        break
        
        # Log what we found for debugging
        if pricing_info:
            logger.info(f"Extracted pricing info: {pricing_info}")
        else:
            logger.warning(f"No pricing info extracted from {len(retrieved_contents)} documents")
            # Log document previews for debugging
            for i, doc in enumerate(retrieved_contents[:3]):  # Log first 3 docs
                preview = doc.page_content[:200] if len(doc.page_content) > 200 else doc.page_content
                logger.debug(f"Document {i+1} preview: {preview}...")
                if cottage_number:
                    has_cottage = re.search(rf"cottage\s+{cottage_number}\b", doc.page_content, re.IGNORECASE)
                    logger.debug(f"Document {i+1} has cottage {cottage_number}: {has_cottage is not None}")
            
            # Fallback: Try loading pricing directly from FAQ files
            logger.info("Trying to load pricing from FAQ files as fallback")
            faq_pricing = self._load_pricing_from_faq_files(cottage_number)
            if faq_pricing:
                logger.info(f"Found pricing in FAQ files: {faq_pricing}")
                return faq_pricing
        
        if pricing_info:
            return "\n".join(pricing_info)
        
        return None
    
    def is_pricing_query(self, question: str) -> bool:
        """
        Check if a question is about pricing.
        
        Args:
            question: User's question string
            
        Returns:
            True if question is about pricing
        """
        question_lower = question.lower()
        
        # Exclude non-pricing contexts that contain "rate" or similar words
        exclusion_patterns = [
            "golf rate", "golf rates", "golf course", "golf package",
            "occupancy rate", "occupancy rates", "capacity rate", "capacity rates",
            "exchange rate", "exchange rates", "interest rate", "interest rates",
            "discount rate", "discount rates"
        ]
        
        # If question contains exclusion patterns, it's NOT a pricing query
        if any(pattern in question_lower for pattern in exclusion_patterns):
            return False
        
        # Primary pricing keywords (high confidence)
        primary_keywords = [
            "price", "pricing", "cost", "how much",
            "pkr", "per night", "weekday", "weekend", "total cost",
            "total price", "booking cost", "stay cost", "what will be price",
            "what will be the price", "what is the price", "what is price",
            "tell me the price", "tell me price", "what's the price",
            "tell me the total cost", "tell me total cost", "what is the total cost",
            "what's the total cost", "total cost", "calculate cost", "how much will it cost"
        ]
        
        # Check for primary keywords
        if any(keyword in question_lower for keyword in primary_keywords):
            return True
        
        # Check for date queries that are likely pricing follow-ups
        # If query contains dates (month names + "from/to/stay"), it's likely a pricing query
        # This handles cases like "i will stay from 10 march to 19 march" after asking about pricing
        month_names = ["january", "february", "march", "april", "may", "june", 
                      "july", "august", "september", "october", "november", "december",
                      "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
        has_month = any(month in question_lower for month in month_names)
        has_date_pattern = any(pattern in question_lower for pattern in ["from", "to", "stay", "staying", "will stay"])
        
        # If query has month names and date patterns, it's likely a pricing/booking query
        if has_month and has_date_pattern:
            # Check if it's a date range pattern (e.g., "from 10 march to 19 march")
            date_range_patterns = [
                r"from\s+\d+\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|may|june|july|august|september|october|november|december)\s+to\s+\d+",
                r"\d+\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|may|june|july|august|september|october|november|december)\s+to\s+\d+",
            ]
            import re
            for pattern in date_range_patterns:
                if re.search(pattern, question_lower):
                    logger.info(f"Detected date range query as pricing query: {question_lower[:100]}")
                    return True
        
        # Secondary keywords that require pricing context
        secondary_keywords = ["rate", "rates"]
        pricing_context_keywords = [
            "cottage", "booking", "stay", "night", "nights", "per night",
            "weekday", "weekend", "guest", "guests", "accommodation"
        ]
        
        # If "rate" or "rates" appears, require pricing context
        if any(keyword in question_lower for keyword in secondary_keywords):
            # Must have at least one pricing context keyword
            if any(context in question_lower for context in pricing_context_keywords):
                return True
        
        # Check for patterns like "what will be price" or "what is price"
        pricing_patterns = [
            r"what\s+(will\s+be|is)\s+(the\s+)?(price|cost|rate)",
            r"tell\s+me\s+(the\s+)?(price|cost|rate)",
            r"how\s+much\s+(will\s+it\s+be|is\s+it|does\s+it\s+cost)",
        ]
        import re
        for pattern in pricing_patterns:
            if re.search(pattern, question_lower):
                # Double-check it's not about golf or other non-pricing rates
                if not any(exclusion in question_lower for exclusion in ["golf", "occupancy", "capacity", "exchange", "interest", "discount"]):
                    return True
        
        return False
    
    def process_pricing_query(
        self,
        question: str,
        slots: Dict,
        retrieved_contents: List[Document]
    ) -> Dict:
        """
        Process a pricing query using structured logic.
        
        Args:
            question: User's question string
            slots: Dictionary of extracted slots (guests, dates, cottage_id, season)
            retrieved_contents: List of retrieved documents from RAG
            
        Returns:
            Dictionary with keys:
            - total_price: int or None - Calculated total price
            - breakdown: str - Price breakdown text
            - answer_template: str - Structured answer template to add to context
            - has_all_info: bool - Whether we have all required slots
            - missing_slots: List[str] - List of missing required slots
            - error: str or None - Error message if calculation failed
        """
        # Extract slots
        guests = slots.get("guests")
        dates = slots.get("dates")
        nights = slots.get("nights")  # Extract nights separately
        cottage_id = slots.get("cottage_id")
        season = slots.get("season")
        
        # Extract cottage number from cottage_id or question
        cottage_number = None
        if cottage_id and cottage_id != "any":
            # Extract number from "cottage_7", "cottage_9", "cottage_11"
            cottage_number = cottage_id.replace("cottage_", "")
            logger.info(f"Extracted cottage number from cottage_id slot: {cottage_number}")
        else:
            # Try to extract from question directly
            cottage_num = self.cottage_extractor.extract_cottage_number(question)
            if cottage_num:
                cottage_number = cottage_num
                logger.info(f"Extracted cottage number from question: {cottage_number}")
            else:
                logger.warning(f"Could not extract cottage number from question: {question}")
        
        # Also try to extract guests from question if not in slots
        if guests is None:
            guests = self.group_size_extractor.extract_group_size(question)
            if guests:
                logger.info(f"Extracted guests from question: {guests}")
        
        logger.info(f"Processing pricing query - Guests: {guests}, Dates: {dates}, Nights: {nights}, Cottage: {cottage_number}")
        
        # For pricing, guests can default to 6 (base capacity) if not provided
        # This allows pricing calculation with just dates and cottage
        if guests is None:
            guests = 6  # Default to base capacity
            logger.info(f"Guests not provided, defaulting to 6 (base capacity)")
        
        # CRITICAL FIX: If user explicitly mentioned number of nights, prioritize that over extracted dates
        # This handles cases like "3 nights in next week on weekdays" where dates might be extracted incorrectly
        if nights is not None and nights > 0:
            from datetime import datetime, timedelta
            
            question_lower = question.lower()
            wants_weekdays_only = any(word in question_lower for word in ["weekday", "week day", "on weekdays", "weekdays only"])
            wants_next_week = "next week" in question_lower
            
            # CRITICAL: Only use dates if they were explicitly extracted from conversation
            # DO NOT auto-generate dates from datetime.now() - this creates incorrect dates
            if dates is not None:
                extracted_nights = dates.get("nights", 0)
                if extracted_nights != nights:
                    logger.warning(f"Extracted dates have {extracted_nights} nights but user requested {nights} nights. Adjusting dates to match requested nights.")
                    
                    # Try to get start date from extracted dates
                    start_date = None
                    if dates.get("parsed_start"):
                        start_date = dates["parsed_start"]
                    else:
                        # Try to parse start date from dates dict
                        try:
                            start_date_str = dates.get("start_date", "")
                            if start_date_str:
                                start_date = datetime.strptime(start_date_str, "%d %b %Y")
                        except (ValueError, AttributeError):
                            pass
                    
                    # If we have a start date, adjust end date to match requested nights
                    if start_date:
                        if wants_weekdays_only:
                            start_date = self._ensure_weekday(start_date)
                            end_date = self._create_date_range_for_weekdays(start_date, nights)
                        else:
                            end_date = start_date + timedelta(days=nights)
                        dates = self._create_dates_dict(start_date, end_date, nights)
                        logger.info(f"Adjusted dates to match {nights} nights: {start_date.strftime('%d %b %Y')} to {end_date.strftime('%d %b %Y')}")
                    # If no start date found but user wants next week, use next week logic
                    elif wants_next_week:
                        start_date = self._get_start_date_for_next_week()
                        if wants_weekdays_only:
                            start_date = self._ensure_weekday(start_date)
                            end_date = self._create_date_range_for_weekdays(start_date, nights)
                        else:
                            end_date = start_date + timedelta(days=nights)
                        dates = self._create_dates_dict(start_date, end_date, nights)
                        logger.info(f"Using next Monday as start date: {start_date.strftime('%d %b %Y')} to {end_date.strftime('%d %b %Y')}")
                    # If dates were extracted but no valid start date, keep dates as None
                    else:
                        logger.warning(f"Dates were extracted but no valid start date found. Not auto-generating dates.")
                        dates = None
            else:
                # No dates extracted - DO NOT auto-generate dates
                # Only generate dates if user explicitly mentions "next week"
                if wants_next_week:
                    start_date = self._get_start_date_for_next_week()
                    if wants_weekdays_only:
                        start_date = self._ensure_weekday(start_date)
                        end_date = self._create_date_range_for_weekdays(start_date, nights)
                    else:
                        end_date = start_date + timedelta(days=nights)
                    dates = self._create_dates_dict(start_date, end_date, nights)
                    logger.info(f"Using next Monday as start date (user mentioned 'next week'): {start_date.strftime('%d %b %Y')} to {end_date.strftime('%d %b %Y')}")
                else:
                    # No dates extracted and no time reference - do NOT generate dates
                    logger.info(f"No dates extracted and user didn't mention 'next week'. Not auto-generating dates.")
                    dates = None
        
        # Check if this is a general pricing query vs specific calculation
        question_lower = question.lower()
        
        # General pricing query patterns (asking for rates, not specific calculation)
        general_patterns = [
            "what is the pricing", "tell me the pricing", "tell me pricing", "pricing of",
            "what are the prices", "pricing per night", "rates", "how much", "what are prices",
            "prices for cottage", "pricing for cottage", "what is the price", "price of"
        ]
        
        # Specific calculation patterns (asking for price WITH specific details)
        specific_calculation_patterns = [
            "pricing for", "price for", "cost for", "calculate", "with", "dates", "guests"
        ]
        
        # Check if it matches general patterns
        matches_general = any(phrase in question_lower for phrase in general_patterns)
        
        # Check if it's asking for specific calculation (has calculation keywords AND specific values)
        # But allow "prices for cottage X" as general query (cottage-specific general pricing)
        is_specific_calculation = False
        if any(word in question_lower for word in specific_calculation_patterns):
            # If it has dates or guest numbers, it's a specific calculation
            if any(word in question_lower for word in ["dates", "guests", "people", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december", "january", "february"]):
                is_specific_calculation = True
            # If it's "prices for cottage X" without dates/guests, treat as general
            elif "prices for cottage" in question_lower or "pricing for cottage" in question_lower:
                is_specific_calculation = False
            else:
                is_specific_calculation = True
        
        is_general_query = matches_general and not is_specific_calculation
        
        # Check if we have all required information
        # CRITICAL: For specific pricing calculations, we can use NIGHTS if dates are not provided
        # If user provides nights but no dates, calculate pricing using nights (assume typical weekday/weekend mix)
        missing_slots = []
        if dates is None and nights is None:
            missing_slots.append("dates or nights")
        if cottage_number is None:
            missing_slots.append("cottage_id")
        
        # For specific calculations, we need either dates OR nights, and cottage number
        # If user provides nights without dates, we can still calculate (using typical weekday/weekend mix)
        has_all_info = (dates is not None or nights is not None) and cottage_number is not None
        
        if not has_all_info:
            # Check if this is a general pricing query - if so, extract general rates from context
            if is_general_query:
                logger.info(f"General pricing query detected - extracting general rates from context (cottage_number={cottage_number}, retrieved_docs={len(retrieved_contents)})")
                # If cottage_number is None, try to extract it from the question
                if cottage_number is None:
                    cottage_num = self.cottage_extractor.extract_cottage_number(question)
                    if cottage_num:
                        cottage_number = cottage_num
                        logger.info(f"Extracted cottage number from question: {cottage_number}")
                general_rates = self._extract_general_pricing_from_context(retrieved_contents, cottage_number)
                logger.info(f"Extracted general rates: {general_rates if general_rates else 'None'}")
                
                if general_rates:
                    answer_template = f"""
🚨🚨🚨 GENERAL PRICING INFORMATION - USE THIS DATA 🚨🚨🚨
ALL PRICES ARE IN PKR (PAKISTANI RUPEES) - DO NOT USE DOLLAR PRICES ($)

GENERAL PRICING RATES:
{general_rates}

⚠️⚠️⚠️ CRITICAL INSTRUCTIONS FOR LLM ⚠️⚠️⚠️:
1. YOU MUST provide the pricing rates shown above as your answer
2. DO NOT show cottage listing format ("Swiss Cottages Bhurban offers the following cottages:")
3. DO NOT show "All cottages include:" list
4. DO NOT show "Would you like to know more about:" section
5. DO NOT convert to dollars - use ONLY PKR prices from above
6. Provide ONLY the pricing information - no cottage descriptions or facility lists
7. If user asks for specific pricing, mention that exact pricing depends on dates and number of guests
8. Provide the general per-night rates from the information above
9. Mention that for exact pricing, user needs to provide dates and number of guests
10. DO NOT ask for dates or guests - just provide the general rates shown above
11. DO NOT include any cottage listing or facility information in your response
"""
                    return {
                        "total_price": None,
                        "breakdown": "",
                        "answer_template": answer_template,
                        "has_all_info": False,
                        "missing_slots": missing_slots,
                        "error": None,  # Not an error - general info provided
                        "is_general_query": True,
                    }
                else:
                    # Extraction failed - try to get pricing from all retrieved documents as fallback
                    logger.warning("General pricing extraction returned None - trying fallback extraction")
                    # Try extracting without cottage filter first
                    if cottage_number:
                        general_rates = self._extract_general_pricing_from_context(retrieved_contents, None)
                    
                    # If still None, try loading from FAQ files
                    if not general_rates:
                        logger.info("Trying to load pricing from FAQ files as fallback")
                        general_rates = self._load_pricing_from_faq_files(cottage_number)
                    
                    # If we found pricing (from documents or FAQ files), use it
                    if general_rates:
                        answer_template = f"""
🚨🚨🚨 GENERAL PRICING INFORMATION - USE THIS DATA 🚨🚨🚨
ALL PRICES ARE IN PKR (PAKISTANI RUPEES) - DO NOT USE DOLLAR PRICES ($)

GENERAL PRICING RATES:
{general_rates}

⚠️⚠️⚠️ CRITICAL INSTRUCTIONS FOR LLM ⚠️⚠️⚠️:
1. YOU MUST provide the pricing rates shown above as your answer
2. DO NOT show cottage listing format ("Swiss Cottages Bhurban offers the following cottages:")
3. DO NOT show "All cottages include:" list
4. DO NOT show "Would you like to know more about:" section
5. DO NOT convert to dollars - use ONLY PKR prices from above
6. Provide ONLY the pricing information - no cottage descriptions or facility lists
7. If user asks for specific pricing, mention that exact pricing depends on dates and number of guests
8. Provide the general per-night rates from the information above
9. Mention that for exact pricing, user needs to provide dates and number of guests
10. DO NOT ask for dates or guests - just provide the general rates shown above
11. DO NOT include any cottage listing or facility information in your response
"""
                        return {
                            "total_price": None,
                            "breakdown": "",
                            "answer_template": answer_template,
                            "has_all_info": False,
                            "missing_slots": missing_slots,
                            "error": None,  # Not an error - general info provided
                            "is_general_query": True,
                        }
                    else:
                        # Truly no pricing found - return a message that we need more info but in a helpful way
                        logger.warning("No pricing found in documents or FAQ files")
                        # For general queries, we should still try to provide helpful info
                        # Return a template that tells LLM to use context pricing if available
                        answer_template = f"""
⚠️ GENERAL PRICING QUERY DETECTED ⚠️

The user is asking for general pricing information. Please check the retrieved context documents above for pricing information.

If you find pricing information in the context:
- Provide the per-night rates (weekday and weekend) for the cottages mentioned
- Use ONLY PKR prices from the context
- DO NOT invent or generate prices
- If context has pricing for specific cottages, provide those rates

If you do NOT find pricing in the context:
- Say that pricing information is available on Airbnb or by contacting the property
- DO NOT ask for dates or guests for a general pricing query
- Provide contact information if available in context
"""
                        return {
                            "total_price": None,
                            "breakdown": "",
                            "answer_template": answer_template,
                            "has_all_info": False,
                            "missing_slots": [],
                            "error": None,
                            "is_general_query": True,
                        }
            
            # Specific calculation query but missing slots - ask for information
            missing_info_text = ", ".join(missing_slots)
            
            # Create a helpful message based on what's missing
            # Check if cottage was mentioned in question but not extracted properly
            cottage_mentioned = self.cottage_extractor.extract_cottage_number(question)
            
            if "dates" in missing_slots and "cottage_id" in missing_slots:
                if cottage_mentioned:
                    # Cottage was mentioned but not extracted - clarify
                    message = f"To calculate pricing, I need the dates of your stay (check-in and check-out dates). I see you mentioned Cottage {cottage_mentioned} - is that correct?"
                else:
                    message = "To calculate pricing, I need the dates of your stay (check-in and check-out dates) and which cottage you're interested in (Cottage 7, 9, or 11)."
            elif "dates or nights" in missing_slots:
                # User provided neither dates nor nights - ask for dates or nights
                message = "To calculate pricing, I need either the dates of your stay (check-in and check-out dates) or the number of nights."
            elif "cottage_id" in missing_slots:
                if cottage_mentioned:
                    # Cottage was mentioned but not extracted - this shouldn't happen, but handle gracefully
                    message = f"I see you mentioned Cottage {cottage_mentioned}. To calculate pricing, I need the dates of your stay."
                else:
                    message = "To calculate pricing, I need to know which cottage you're interested in (Cottage 7, 9, or 11)."
            else:
                message = f"To calculate pricing, I need: {missing_info_text}."
            
            answer_template = f"""
🚨 CRITICAL: MISSING REQUIRED INFORMATION FOR PRICING CALCULATION 🚨

STRUCTURED PRICING ANALYSIS:
Status: Missing required information
Missing slots: {missing_info_text}
Note: {message}

⚠️ IMPORTANT INSTRUCTIONS FOR LLM:
1. DO NOT generate or assume dates if dates are missing
2. DO NOT create example dates (e.g., "March 23-26, 2026") 
3. DO NOT assume number of nights if not provided
4. You MUST ask the user for the missing information
5. If dates are missing, say: "To calculate the exact price, I need your check-in and check-out dates."
6. If cottage is missing, say: "Which cottage are you interested in? (Cottage 7, 9, or 11)"
7. DO NOT provide pricing breakdown with assumed dates - only show per-night rates if dates are missing

Please provide the missing information to get an accurate price quote.
"""
            return {
                "total_price": None,
                "breakdown": "",
                "answer_template": answer_template,
                "has_all_info": False,
                "missing_slots": missing_slots,
                "error": f"Missing required slots: {missing_info_text}",
            }
        
        # We have all required information - calculate price
        # If dates are None but nights are provided, create a calculation using nights with typical weekday/weekend mix
        if dates is None and nights is not None and nights > 0:
            # User provided nights but no dates - calculate using typical weekday/weekend mix
            # For N nights, assume typical mix: ~70% weekdays, ~30% weekends (rounded)
            # This gives a reasonable estimate without requiring exact dates
            weekday_nights = int(nights * 0.7)  # ~70% weekdays
            weekend_nights = nights - weekday_nights  # Remaining are weekends
            
            # Get pricing rates from context
            general_rates = self._extract_general_pricing_from_context(retrieved_contents, cottage_number)
            if not general_rates:
                general_rates = self._load_pricing_from_faq_files(cottage_number)
            
            if general_rates:
                # Extract rates from general_rates text
                import re
                weekday_match = re.search(r'PKR\s+([\d,]+)\s+per\s+night\s+on\s+weekdays?', general_rates, re.IGNORECASE)
                weekend_match = re.search(r'PKR\s+([\d,]+)\s+per\s+night\s+on\s+weekends?', general_rates, re.IGNORECASE)
                
                if weekday_match and weekend_match:
                    weekday_rate = int(weekday_match.group(1).replace(",", ""))
                    weekend_rate = int(weekend_match.group(1).replace(",", ""))
                    
                    # Calculate total
                    weekday_total = weekday_nights * weekday_rate
                    weekend_total = weekend_nights * weekend_rate
                    total_price = weekday_total + weekend_total
                    
                    # Also calculate min (all weekdays) and max (all weekends) for price range
                    min_price = nights * weekday_rate  # All weekdays
                    max_price = nights * weekend_rate   # All weekends
                    
                    answer_template = f"""
🚨 CRITICAL PRICING INFORMATION - USE ONLY THIS DATA 🚨
ALL PRICES ARE IN PKR (PAKISTANI RUPEES) - DO NOT USE DOLLAR PRICES ($)
DO NOT CONVERT TO DOLLARS - USE ONLY PKR PRICES BELOW

STRUCTURED PRICING ANALYSIS FOR COTTAGE {cottage_number}:
- Guests: {guests}
- Nights: {nights} nights (estimated: {weekday_nights} weekday nights, {weekend_nights} weekend nights)
- Weekday Rate: PKR {weekday_rate:,} per night
- Weekend Rate: PKR {weekend_rate:,} per night

ESTIMATED TOTAL COST (typical weekday/weekend mix):
- {weekday_nights} weekday nights × PKR {weekday_rate:,} = PKR {weekday_total:,}
- {weekend_nights} weekend nights × PKR {weekend_rate:,} = PKR {weekend_total:,}
🎯 ESTIMATED TOTAL: PKR {total_price:,} 🎯

PRICE RANGE (for reference):
- Minimum (all weekdays): PKR {min_price:,}
- Maximum (all weekends): PKR {max_price:,}
- Estimated (typical mix): PKR {total_price:,}

⚠️⚠️⚠️ CRITICAL INSTRUCTIONS FOR LLM ⚠️⚠️⚠️:
1. YOU MUST provide the ESTIMATED TOTAL: PKR {total_price:,} as the main answer
2. Mention that this is an estimate based on a typical weekday/weekend mix
3. Explain that exact pricing depends on which days are weekdays vs weekends
4. Show the price range: PKR {min_price:,} (all weekdays) to PKR {max_price:,} (all weekends)
5. DO NOT ask for dates - provide the estimated total immediately
6. DO NOT use dollar prices - use ONLY PKR
7. DO NOT say "I need dates" - you have calculated an estimate using nights
8. Your answer MUST include: "For {nights} nights at Cottage {cottage_number}, the estimated total cost is PKR {total_price:,} (based on a typical weekday/weekend mix). The price range is PKR {min_price:,} (all weekdays) to PKR {max_price:,} (all weekends)."
"""
                    return {
                        "total_price": total_price,
                        "breakdown": f"{weekday_nights} weekday nights × PKR {weekday_rate:,} = PKR {weekday_total:,}\n{weekend_nights} weekend nights × PKR {weekend_rate:,} = PKR {weekend_total:,}\nTotal: PKR {total_price:,}",
                        "answer_template": answer_template,
                        "has_all_info": True,
                        "missing_slots": [],
                        "error": None,
                    }
            
            # If we can't extract rates, fall through to ask for dates
            logger.warning(f"Could not extract pricing rates for nights-only calculation")
        
        # If dates are None and nights are also None, we can't calculate
        if dates is None and (nights is None or nights == 0):
            logger.error("CRITICAL: Both dates and nights are None - cannot calculate pricing")
            return {
                "total_price": None,
                "breakdown": "",
                "answer_template": "Error: Dates or nights are required for pricing calculation but were not provided.",
                "has_all_info": False,
                "missing_slots": ["dates or nights"],
                "error": "Both dates and nights are None",
            }
        
        try:
            price_result = self.pricing_calculator.calculate_price(
                guests=guests,
                dates=dates,
                cottage_number=cottage_number,
                season=season
            )
            
            if price_result.get("error"):
                # Calculation failed
                answer_template = f"""
STRUCTURED PRICING ANALYSIS:
Cottage: {cottage_number}
Guests: {guests}
Dates: {dates.get('start_date', 'N/A')} to {dates.get('end_date', 'N/A')}
Error: {price_result['error']}
"""
                return {
                    "total_price": None,
                    "breakdown": price_result.get("breakdown", ""),
                    "answer_template": answer_template,
                    "has_all_info": True,
                    "missing_slots": [],
                    "error": price_result["error"],
                }
            
            # Successful calculation
            total_price = price_result["total_price"]
            breakdown = price_result["breakdown"]
            nights = price_result["nights"]
            weekday_nights = price_result["weekday_nights"]
            weekend_nights = price_result["weekend_nights"]
            weekday_rate = price_result["per_night_weekday"]
            weekend_rate = price_result["per_night_weekend"]
            
            # Get the year from the dates for clarity
            year_info = ""
            if dates.get("parsed_start"):
                year_info = f" (Year: {dates['parsed_start'].year})"
            
            answer_template = f"""
🚨 CRITICAL PRICING INFORMATION - USE ONLY THIS DATA 🚨
ALL PRICES ARE IN PKR (PAKISTANI RUPEES) - DO NOT USE DOLLAR PRICES ($)
DO NOT CONVERT TO DOLLARS - USE ONLY PKR PRICES BELOW

STRUCTURED PRICING ANALYSIS FOR COTTAGE {cottage_number}:
- Guests: {guests}
- Check-in: {dates.get('start_date', 'N/A')}{year_info}
- Check-out: {dates.get('end_date', 'N/A')}
- Total Nights: {nights} ({weekday_nights} weekday nights, {weekend_nights} weekend nights)
- Weekday Rate: PKR {weekday_rate:,} per night
- Weekend Rate: PKR {weekend_rate:,} per night

DETAILED BREAKDOWN (USING ACTUAL CALENDAR FOR THE YEAR):
{breakdown}

🎯 TOTAL COST FOR {nights} NIGHTS: PKR {total_price:,} 🎯

⚠️ MANDATORY INSTRUCTIONS FOR LLM - READ CAREFULLY:
1. You MUST use ONLY these PKR prices from the structured analysis above
2. DO NOT convert to dollars ($220, $250, etc.) - these are WRONG
3. DO NOT use any dollar prices from your training data
4. **🚨🚨🚨 THE TOTAL COST IS PKR {total_price:,} - YOU MUST USE THIS EXACT AMOUNT - DO NOT CALCULATE YOURSELF 🚨🚨🚨**
5. **🚨🚨🚨 CRITICAL: The dates {dates.get('start_date', 'N/A')} to {dates.get('end_date', 'N/A')} have EXACTLY {weekday_nights} weekday nights and {weekend_nights} weekend nights - DO NOT change these numbers 🚨🚨🚨**
6. **🚨🚨🚨 CRITICAL: The total nights is {nights} nights - DO NOT say a different number 🚨🚨🚨**
7. **🚨🚨🚨 CRITICAL: The breakdown above shows {weekday_nights} weekday nights and {weekend_nights} weekend nights - DO NOT say different numbers 🚨🚨🚨**
8. **CRITICAL: The breakdown above is calculated using Python's datetime.weekday() which uses the ACTUAL calendar for the year {dates.get('parsed_start').year if dates.get('parsed_start') else 'current'}**
9. **CRITICAL: The breakdown shows the ACTUAL days of the week - if it says a date is a weekday, it IS a weekday; if it says weekend, it IS a weekend**
10. **CRITICAL: DO NOT recalculate or guess which days are weekdays vs weekends - use the breakdown EXACTLY as provided**
11. **CRITICAL: DO NOT say "1 weekend night" if the breakdown shows {weekend_nights} weekend nights - use the EXACT number from the breakdown**
12. **CRITICAL: DO NOT say "Total cost: PKR 38,000" if the breakdown shows "TOTAL COST FOR {nights} NIGHTS: PKR {total_price:,}" - use the EXACT total from the breakdown**
13. **CRITICAL: If the breakdown lists specific dates with day names (e.g., "April 2, 2026 (Thursday)"), those dates ARE weekdays - DO NOT list them as weekends**
14. **CRITICAL: If the breakdown lists specific dates with day names (e.g., "April 4, 2026 (Saturday)"), those dates ARE weekends - DO NOT list them as weekdays**
15. Show the breakdown exactly as provided above with specific dates and day names - DO NOT change the dates or day types
16. **YOU MUST MENTION THE TOTAL COST: PKR {total_price:,} prominently in your answer - DO NOT use any other amount**
17. DO NOT say dates fall on weekends if the breakdown shows {weekday_nights} weekday nights and {weekend_nights} weekend nights
18. The breakdown above is calculated using the ACTUAL calendar for the current year - trust it completely
19. **Your answer MUST include: "Total cost: PKR {total_price:,}" or "The total cost is PKR {total_price:,}" - DO NOT use any other amount**
20. **🚨🚨🚨 FINAL WARNING: If you output a different total cost than PKR {total_price:,}, your answer is WRONG - use ONLY PKR {total_price:,} 🚨🚨🚨**
"""
            
            logger.info(f"Pricing calculation result: PKR {total_price:,} for {nights} nights at Cottage {cottage_number}")
            
            return {
                "total_price": total_price,
                "breakdown": breakdown,
                "answer_template": answer_template,
                "has_all_info": True,
                "missing_slots": [],
                "error": None,
            }
            
        except Exception as e:
            logger.error(f"Error calculating price: {e}")
            return {
                "total_price": None,
                "breakdown": "",
                "answer_template": f"Error calculating price: {str(e)}",
                "has_all_info": has_all_info,
                "missing_slots": missing_slots,
                "error": str(e),
            }
    
    def enhance_context_with_pricing_info(
        self,
        retrieved_contents: List[Document],
        pricing_result: Dict
    ) -> List[Document]:
        """
        Enhance retrieved documents with structured pricing information.
        
        Args:
            retrieved_contents: List of retrieved documents
            pricing_result: Result from process_pricing_query()
            
        Returns:
            List of documents with pricing info prepended to first document
        """
        if not pricing_result.get("answer_template"):
            return retrieved_contents
        
        # No truncation - use full template
        answer_template = pricing_result["answer_template"]
        
        # Create a new document with pricing analysis
        pricing_doc = Document(
            page_content=answer_template,
            metadata={
                "source": "structured_pricing_analysis",
                "type": "pricing_analysis",
                "total_price": pricing_result.get("total_price"),
                "cottage": pricing_result.get("cottage"),
                "guests": pricing_result.get("guests"),
            }
        )
        
        # Prepend pricing analysis to retrieved contents
        enhanced_contents = [pricing_doc] + retrieved_contents
        
        logger.debug(f"Enhanced context with pricing analysis for {len(enhanced_contents)} documents")
        
        return enhanced_contents


# Global instance for easy access
_pricing_handler: Optional[PricingQueryHandler] = None


def get_pricing_handler(
    pricing_calculator: Optional[PricingCalculator] = None
) -> PricingQueryHandler:
    """
    Get or create the global pricing handler instance.
    
    Args:
        pricing_calculator: Optional PricingCalculator instance
    
    Returns:
        PricingQueryHandler instance
    """
    global _pricing_handler
    if _pricing_handler is None:
        _pricing_handler = PricingQueryHandler(pricing_calculator)
    return _pricing_handler
