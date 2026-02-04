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
            "tell me the price", "tell me price", "what's the price"
        ]
        
        # Check for primary keywords
        if any(keyword in question_lower for keyword in primary_keywords):
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
            slots: Dictionary of extracted slots (guests, dates, room_type, season)
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
        room_type = slots.get("room_type")
        season = slots.get("season")
        
        # Extract cottage number from room_type or question
        cottage_number = None
        if room_type and room_type != "any":
            # Extract number from "cottage_7", "cottage_9", "cottage_11"
            cottage_number = room_type.replace("cottage_", "")
            logger.info(f"Extracted cottage number from room_type slot: {cottage_number}")
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
            
            # Check if dates were extracted but don't match the requested nights
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
                    
                    # If no start date found or user wants next week, use next week logic
                    if start_date is None or wants_next_week:
                        start_date = self._get_start_date_for_next_week()
                        logger.info(f"Using next Monday as start date: {start_date.strftime('%d %b %Y')}")
            else:
                # No dates extracted, create date range from today (or next week if mentioned)
                if wants_next_week:
                    start_date = self._get_start_date_for_next_week()
                    logger.info(f"Using next Monday as start date: {start_date.strftime('%d %b %Y')}")
                else:
                    start_date = datetime.now()
            
            # Calculate end date based on whether user wants weekdays only
            if wants_weekdays_only:
                # Ensure start date is a weekday
                start_date = self._ensure_weekday(start_date)
                # Calculate end date for N consecutive weekday nights
                end_date = self._create_date_range_for_weekdays(start_date, nights)
                logger.info(f"Calculated dates for {nights} weekday nights: {start_date.strftime('%d %b %Y')} to {end_date.strftime('%d %b %Y')}")
            else:
                # User didn't specify weekdays only, just use the requested number of nights
                end_date = start_date + timedelta(days=nights)
                logger.info(f"Calculated dates for {nights} nights: {start_date.strftime('%d %b %Y')} to {end_date.strftime('%d %b %Y')}")
            
            # Create dates dictionary
            dates = self._create_dates_dict(start_date, end_date, nights)
        
        # Check if we have all required information
        # For pricing, we need either dates OR nights, and cottage number
        missing_slots = []
        if dates is None and nights is None:
            missing_slots.append("dates or nights")
        if cottage_number is None:
            missing_slots.append("room_type")
        
        # If we have nights but no dates, we can still calculate (dates will be created from nights)
        has_all_info = (dates is not None or nights is not None) and cottage_number is not None
        
        if not has_all_info:
            # Missing required slots - generate helpful context
            missing_info_text = ", ".join(missing_slots)
            
            # Create a helpful message based on what's missing
            # Check if cottage was mentioned in question but not extracted properly
            cottage_mentioned = self.cottage_extractor.extract_cottage_number(question)
            
            if "dates or nights" in missing_slots and "room_type" in missing_slots:
                if cottage_mentioned:
                    # Cottage was mentioned but not extracted - clarify
                    message = f"To calculate pricing, I need the dates of your stay (or number of nights). I see you mentioned Cottage {cottage_mentioned} - is that correct?"
                else:
                    message = "To calculate pricing, I need the dates of your stay (or number of nights) and which cottage you're interested in (Cottage 7, 9, or 11)."
            elif "dates or nights" in missing_slots:
                message = "To calculate pricing, I need the dates of your stay (check-in and check-out dates) or the number of nights."
            elif "room_type" in missing_slots:
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
        # CRITICAL: Validate that dates were provided by user, not generated
        if dates is None:
            logger.error("CRITICAL: Dates are None but has_all_info is True - this should not happen!")
            return {
                "total_price": None,
                "breakdown": "",
                "answer_template": "Error: Dates are required for pricing calculation but were not provided.",
                "has_all_info": False,
                "missing_slots": ["dates"],
                "error": "Dates are None",
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
4. THE TOTAL COST IS PKR {total_price:,} - YOU MUST INCLUDE THIS EXACT AMOUNT IN YOUR ANSWER
5. The dates {dates.get('start_date', 'N/A')} to {dates.get('end_date', 'N/A')} have {weekday_nights} weekday nights and {weekend_nights} weekend nights
6. The breakdown above shows the ACTUAL days of the week using the real calendar - DO NOT guess or assume
7. Show the breakdown exactly as provided above with specific dates and day names
8. YOU MUST MENTION THE TOTAL COST: PKR {total_price:,} prominently in your answer
9. DO NOT say dates fall on weekends if the breakdown shows {weekday_nights} weekday nights and {weekend_nights} weekend nights
10. The breakdown above is calculated using the ACTUAL calendar for the current year - trust it completely
11. Your answer MUST include: "Total cost: PKR {total_price:,}" or "The total cost is PKR {total_price:,}"
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
