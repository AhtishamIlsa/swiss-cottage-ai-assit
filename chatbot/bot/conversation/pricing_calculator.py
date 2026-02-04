"""Pricing calculator for structured price calculations."""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from helpers.log import get_logger
from bot.conversation.date_extractor import DateExtractor, get_date_extractor

logger = get_logger(__name__)


class PricingCalculator:
    """Maps cottage numbers to pricing information and calculates prices."""
    
    def __init__(self, docs_path: Optional[Path] = None):
        """
        Initialize the pricing calculator.
        
        Args:
            docs_path: Path to docs/faq directory. If None, uses default location.
        """
        if docs_path is None:
            # Default to docs/faq relative to chatbot directory
            chatbot_dir = Path(__file__).resolve().parent.parent.parent
            docs_path = chatbot_dir / "docs" / "faq"
        
        self.docs_path = docs_path
        self.date_extractor = get_date_extractor()
        self._pricing_rules: Dict[str, Dict[str, int]] = {}
        self._load_pricing_data()
    
    def _load_pricing_data(self) -> None:
        """Load pricing data from FAQ files and build pricing rules."""
        # Base pricing rules extracted from FAQs
        # FAQ 084: Cottage 11 - PKR 32,000 weekend, PKR 26,000 weekday (up to 6 guests)
        # FAQ 085: Cottage 9 - PKR 38,000 weekend, PKR 33,000 weekday (up to 6 guests)
        # Cottage 7 pricing not explicitly found in FAQs - will try to extract
        
        base_pricing = {
            "cottage_7": {"weekday": 0, "weekend": 0},  # To be extracted from FAQs
            "cottage_9": {"weekday": 33000, "weekend": 38000},
            "cottage_11": {"weekday": 26000, "weekend": 32000},
        }
        
        # Try to extract additional pricing from FAQ files
        if self.docs_path.exists():
            for md_file in self.docs_path.glob("Pricing_Payments_faq_*.md"):
                try:
                    content = md_file.read_text(encoding='utf-8')
                    self._extract_pricing_from_content(content, base_pricing)
                except Exception as e:
                    logger.debug(f"Error reading {md_file}: {e}")
        
        self._pricing_rules = base_pricing
        
        # Log loaded pricing
        for cottage, rates in self._pricing_rules.items():
            if rates["weekday"] > 0 or rates["weekend"] > 0:
                logger.info(f"Loaded pricing for {cottage}: Weekday PKR {rates['weekday']:,}, Weekend PKR {rates['weekend']:,}")
            else:
                logger.warning(f"Pricing for {cottage} not found in FAQs - using placeholder")
    
    def _extract_pricing_from_content(self, content: str, pricing_dict: Dict) -> None:
        """Extract pricing information from FAQ content."""
        content_lower = content.lower()
        
        # Look for PKR pricing patterns
        # Pattern: "PKR 32,000 per night on weekends and PKR 26,000 per night on weekdays"
        # Pattern: "PKR 38,000 per night on weekends and PKR 33,000 per night on weekdays"
        
        # Extract cottage number
        cottage_match = re.search(r"cottage\s*(\d+)", content_lower)
        if not cottage_match:
            return
        
        cottage_num = cottage_match.group(1)
        cottage_key = f"cottage_{cottage_num}"
        
        # Extract weekend price
        weekend_patterns = [
            r"pkr\s*([\d,]+)\s*per\s*night\s*on\s*weekends?",
            r"weekends?.*?pkr\s*([\d,]+)",
            r"pkr\s*([\d,]+).*?weekends?",
        ]
        
        weekend_price = None
        for pattern in weekend_patterns:
            match = re.search(pattern, content_lower)
            if match:
                try:
                    price_str = match.group(1).replace(",", "")
                    weekend_price = int(price_str)
                    break
                except (ValueError, IndexError):
                    continue
        
        # Extract weekday price
        weekday_patterns = [
            r"pkr\s*([\d,]+)\s*per\s*night\s*on\s*weekdays?",
            r"weekdays?.*?pkr\s*([\d,]+)",
            r"pkr\s*([\d,]+).*?weekdays?",
        ]
        
        weekday_price = None
        for pattern in weekday_patterns:
            match = re.search(pattern, content_lower)
            if match:
                try:
                    price_str = match.group(1).replace(",", "")
                    weekday_price = int(price_str)
                    break
                except (ValueError, IndexError):
                    continue
        
        # Update pricing if found
        if weekend_price and weekday_price:
            if cottage_key not in pricing_dict:
                pricing_dict[cottage_key] = {"weekday": 0, "weekend": 0}
            pricing_dict[cottage_key]["weekday"] = weekday_price
            pricing_dict[cottage_key]["weekend"] = weekend_price
            logger.debug(f"Extracted pricing for {cottage_key}: Weekday PKR {weekday_price:,}, Weekend PKR {weekend_price:,}")
    
    def get_pricing(self, cottage_number: str) -> Optional[Dict[str, int]]:
        """
        Get pricing information for a cottage.
        
        Args:
            cottage_number: Cottage number as string (e.g., "7", "9", "11")
            
        Returns:
            Dictionary with keys: weekday, weekend
            Returns None if cottage not found or pricing not available
        """
        # Normalize cottage number
        cottage_num = str(cottage_number).strip().lower()
        cottage_num = re.sub(r"^cottage\s*", "", cottage_num)
        cottage_key = f"cottage_{cottage_num}"
        
        if cottage_key in self._pricing_rules:
            pricing = self._pricing_rules[cottage_key]
            # Only return if pricing is available (not placeholder)
            if pricing["weekday"] > 0 or pricing["weekend"] > 0:
                return pricing.copy()
        
        logger.warning(f"Pricing for cottage {cottage_number} not available")
        return None
    
    def calculate_price(
        self,
        guests: int,
        dates: Optional[Dict],
        cottage_number: str,
        season: Optional[str] = None
    ) -> Dict:
        """
        Calculate total price for a booking.
        
        Args:
            guests: Number of guests (1-9)
            dates: Date range dictionary from DateExtractor (with nights, weekday_nights, weekend_nights)
            cottage_number: Cottage number as string
            season: Optional season override ("weekday", "weekend", "peak", "off-peak")
            
        Returns:
            Dictionary with keys:
            - total_price: int - Total price in PKR
            - breakdown: str - Human-readable breakdown
            - nights: int - Number of nights
            - weekday_nights: int - Number of weekday nights
            - weekend_nights: int - Number of weekend nights
            - per_night_weekday: int - Weekday rate per night
            - per_night_weekend: int - Weekend rate per night
            - guest_count: int - Number of guests
            - cottage: str - Cottage number
            - error: str or None - Error message if calculation failed
        """
        # Get pricing for cottage
        pricing = self.get_pricing(cottage_number)
        if not pricing:
            return {
                "total_price": 0,
                "breakdown": f"Pricing for Cottage {cottage_number} is not available in the system.",
                "nights": 0,
                "weekday_nights": 0,
                "weekend_nights": 0,
                "per_night_weekday": 0,
                "per_night_weekend": 0,
                "guest_count": guests,
                "cottage": cottage_number,
                "error": f"Pricing for Cottage {cottage_number} not available",
            }
        
        weekday_rate = pricing["weekday"]
        weekend_rate = pricing["weekend"]
        
        # Handle date-based calculation
        if dates:
            nights = dates.get("nights", 0)
            weekday_nights = dates.get("weekday_nights", 0)
            weekend_nights = dates.get("weekend_nights", 0)
            
            # If dates don't have weekday/weekend breakdown, assume all weekdays
            if weekday_nights == 0 and weekend_nights == 0 and nights > 0:
                weekday_nights = nights
                weekend_nights = 0
        else:
            # No dates provided - cannot calculate total
            return {
                "total_price": 0,
                "breakdown": "Date range is required to calculate total price. Please provide check-in and check-out dates.",
                "nights": 0,
                "weekday_nights": 0,
                "weekend_nights": 0,
                "per_night_weekday": weekday_rate,
                "per_night_weekend": weekend_rate,
                "guest_count": guests,
                "cottage": cottage_number,
                "error": "Date range not provided",
            }
        
        # Calculate total price
        weekday_total = weekday_nights * weekday_rate
        weekend_total = weekend_nights * weekend_rate
        total_price = weekday_total + weekend_total
        
        # Handle guest count pricing adjustments
        # Base price is for up to 6 guests
        # For 7-9 guests, pricing may be adjusted (but base rates are for up to 6)
        # Note: FAQ mentions "up to 6 guests" for base pricing
        # For 7-9 guests, "prior confirmation and adjusted pricing" applies
        # For now, we use base rates (actual adjusted pricing would need to be provided)
        
        # Build detailed breakdown with specific dates
        breakdown_parts = []
        
        # Get date list from dates dict if available
        date_list = dates.get("date_list", [])
        
        if date_list:
            # Group dates by weekday/weekend
            weekday_dates = []
            weekend_dates = []
            
            for date_obj in date_list:
                date_str = date_obj.strftime("%B %d, %Y")  # "March 11, 2024"
                day_name = date_obj.strftime("%A")  # "Monday", "Tuesday", etc.
                
                if date_obj.weekday() < 5:  # Monday to Friday
                    weekday_dates.append(f"{date_str} ({day_name})")
                else:  # Saturday or Sunday
                    weekend_dates.append(f"{date_str} ({day_name})")
            
            # Build detailed breakdown
            if weekday_dates:
                breakdown_parts.append(f"**Weekday Nights ({weekday_nights} nights) at PKR {weekday_rate:,} per night:**")
                for date_str in weekday_dates:
                    breakdown_parts.append(f"  - {date_str}: PKR {weekday_rate:,}")
                breakdown_parts.append(f"  Subtotal: PKR {weekday_total:,}")
            
            if weekend_dates:
                breakdown_parts.append(f"\n**Weekend Nights ({weekend_nights} nights) at PKR {weekend_rate:,} per night:**")
                for date_str in weekend_dates:
                    breakdown_parts.append(f"  - {date_str}: PKR {weekend_rate:,}")
                breakdown_parts.append(f"  Subtotal: PKR {weekend_total:,}")
        else:
            # Fallback to simple breakdown if date list not available
            if weekday_nights > 0:
                breakdown_parts.append(f"{weekday_nights} weekday night(s) at PKR {weekday_rate:,} per night = PKR {weekday_total:,}")
            if weekend_nights > 0:
                breakdown_parts.append(f"{weekend_nights} weekend night(s) at PKR {weekend_rate:,} per night = PKR {weekend_total:,}")
        
        breakdown = "\n".join(breakdown_parts)
        if not breakdown:
            breakdown = f"Per night rate: PKR {weekday_rate:,} (weekday), PKR {weekend_rate:,} (weekend)"
        
        # Add guest count note if > 6
        if guests > 6:
            breakdown += f"\n\nNote: Base pricing is for up to 6 guests. For {guests} guests, prior confirmation and adjusted pricing may apply."
        
        return {
            "total_price": total_price,
            "breakdown": breakdown,
            "nights": nights,
            "weekday_nights": weekday_nights,
            "weekend_nights": weekend_nights,
            "per_night_weekday": weekday_rate,
            "per_night_weekend": weekend_rate,
            "guest_count": guests,
            "cottage": cottage_number,
            "error": None,
        }
    
    def get_all_cottages(self) -> List[str]:
        """
        Get list of all cottages with pricing available.
        
        Returns:
            List of cottage numbers as strings
        """
        cottages = []
        for cottage_key in self._pricing_rules.keys():
            cottage_num = cottage_key.replace("cottage_", "")
            if self._pricing_rules[cottage_key]["weekday"] > 0 or self._pricing_rules[cottage_key]["weekend"] > 0:
                cottages.append(cottage_num)
        return cottages


# Global instance for easy access
_pricing_calculator: Optional[PricingCalculator] = None


def get_pricing_calculator(docs_path: Optional[Path] = None) -> PricingCalculator:
    """
    Get or create the global pricing calculator instance.
    
    Args:
        docs_path: Optional path to docs/faq directory
    
    Returns:
        PricingCalculator instance
    """
    global _pricing_calculator
    if _pricing_calculator is None:
        _pricing_calculator = PricingCalculator(docs_path)
    return _pricing_calculator
