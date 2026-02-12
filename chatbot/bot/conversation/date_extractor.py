"""Date extraction and parsing utilities for booking queries."""

import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from calendar import month_name, month_abbr
from helpers.log import get_logger

logger = get_logger(__name__)


class DateExtractor:
    """Extract and parse dates from user queries."""
    
    # Month name mappings (full and abbreviated)
    MONTH_NAMES = {
        **{name.lower(): i for i, name in enumerate(month_name) if name},
        **{abbr.lower(): i for i, abbr in enumerate(month_abbr) if abbr},
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }
    
    def __init__(self):
        """Initialize the date extractor."""
        pass
    
    def extract_date_range(self, query: str) -> Optional[Dict]:
        """
        Extract date range from user query.
        
        Args:
            query: User's question string
            
        Returns:
            Dictionary with keys:
            - start_date: str - Start date string
            - end_date: str - End date string
            - parsed_start: datetime or None - Parsed start date
            - parsed_end: datetime or None - Parsed end date
            - nights: int or None - Number of nights
            - weekday_nights: int or None - Number of weekday nights
            - weekend_nights: int or None - Number of weekend nights
            - date_list: List[datetime] or None - List of all dates in range
            Or None if no date range found
        """
        query_lower = query.lower()
        
        # Handle common typos for month names
        typo_fixes = {
            "match": "march",
            "martch": "march",  # Common typo: martch -> march
            "marchh": "march",  # Double letter typo
            "feburary": "february",
            "febuary": "february",
            "februrary": "february",
            "janurary": "january",
            "januray": "january",
            "april": "april",  # Already correct, but include for completeness
            "may": "may",
            "june": "june",
            "july": "july",
            "august": "august",
            "september": "september",
            "septmeber": "september",
            "october": "october",
            "november": "november",
            "december": "december",
            "decembr": "december",
        }
        for typo, correct in typo_fixes.items():
            query_lower = query_lower.replace(typo, correct)
        
        # Pattern 1: "from X to Y [month]" or "X to Y [month]"
        patterns = [
            # "from march 10 to march 14" or "march 10 to march 14" (month day to month day)
            # Also handles "from feb 13 to feb 19" format
            r"(?:from|arrival|check-in|starting|planning)?\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})\s+to\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})",
            # "February 11, 2026, to February 15, 2026" (full format with year and commas - from bot responses)
            r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2}),\s*(\d{2,4}),?\s+to\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2}),?\s*(\d{2,4})?",
            # "from 4 feb to 9 feb" or "from 4 february to 9 february" (day to day month)
            # Also handles "if we stay from 5 feb to 15 feb"
            r"(?:from|arrival|check-in|starting|stay|staying)?\s*(\d{1,2})\s+to\s+(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|may|june|july|august|september|october|november|december)",
            # "4 feb to 9 feb" (without "from")
            r"(\d{1,2})\s+to\s+(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|may|june|july|august|september|october|november|december)",
            # "february 4-9" or "feb 4-9"
            r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})[-\s]+(\d{1,2})",
            # "from 4/2/2024 to 9/2/2024" or "4/2/2024 to 9/2/2024"
            r"(?:from|arrival|check-in|starting)?\s*(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\s+to\s+(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})",
            # "next week from X to Y [month]"
            r"next\s+week\s+(?:from|arrival|check-in|starting)?\s*(\d{1,2})\s+to\s+(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|may|june|july|august|september|october|november|december)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, query_lower)
            if match:
                try:
                    groups = match.groups()
                    
                    # Handle different pattern formats
                    if len(groups) == 4:
                        # Pattern: "from march 10 to march 14" (month day to month day)
                        start_month_str = groups[0].lower()
                        start_day = int(groups[1])
                        end_month_str = groups[2].lower()
                        end_day = int(groups[3])
                        
                        if start_month_str in self.MONTH_NAMES and end_month_str in self.MONTH_NAMES:
                            start_month = self.MONTH_NAMES[start_month_str]
                            end_month = self.MONTH_NAMES[end_month_str]
                            year = datetime.now().year
                            
                            try:
                                start_date = datetime(year, start_month, start_day)
                                end_date = datetime(year, end_month, end_day)
                                
                                # If end date is before start date, assume next year
                                if end_date < start_date:
                                    end_date = datetime(year + 1, end_month, end_day)
                                
                                return self._calculate_date_details(start_date, end_date, query)
                            except ValueError as e:
                                logger.warning(f"Invalid date: {e}")
                                continue
                    
                    elif len(groups) == 3:
                        # Pattern: "from 4 feb to 9 feb" or "4 feb to 9 feb" (day to day month)
                        start_day = int(groups[0])
                        end_day = int(groups[1])
                        month_str = groups[2].lower()
                        
                        if month_str in self.MONTH_NAMES:
                            month = self.MONTH_NAMES[month_str]
                            year = datetime.now().year
                            
                            # Try to parse dates
                            try:
                                start_date = datetime(year, month, start_day)
                                end_date = datetime(year, month, end_day)
                                
                                # If end date is before start date, assume next month
                                if end_date < start_date:
                                    if month == 12:
                                        end_date = datetime(year + 1, 1, end_day)
                                    else:
                                        end_date = datetime(year, month + 1, end_day)
                                
                                # Log for debugging
                                logger.info(f"Extracted date range: {start_date.strftime('%d %b %Y')} to {end_date.strftime('%d %b %Y')}")
                                
                                return self._calculate_date_details(start_date, end_date, query)
                            except ValueError as e:
                                logger.warning(f"Invalid date: {e}")
                                continue
                    
                    elif len(groups) == 6:
                        # Check if this is the "February 11, 2026, to February 15, 2026" format (month names)
                        # or "from 4/2/2024 to 9/2/2024" format (numeric)
                        start_month_str = groups[0].lower()
                        start_day_str = groups[1]
                        start_year_str = groups[2] if len(groups) > 2 else None
                        end_month_str = groups[3].lower() if len(groups) > 3 else None
                        end_day_str = groups[4] if len(groups) > 4 else None
                        end_year_str = groups[5] if len(groups) > 5 else None
                        
                        # Check if first group is a month name (not a number)
                        if start_month_str in self.MONTH_NAMES:
                            # Pattern: "February 11, 2026, to February 15, 2026"
                            start_month = self.MONTH_NAMES[start_month_str]
                            start_day = int(start_day_str)
                            start_year = int(start_year_str) if start_year_str else datetime.now().year
                            
                            if end_month_str and end_month_str in self.MONTH_NAMES:
                                end_month = self.MONTH_NAMES[end_month_str]
                                end_day = int(end_day_str) if end_day_str else start_day
                                end_year = int(end_year_str) if end_year_str and end_year_str.strip() else start_year
                                
                                # Handle 2-digit years
                                if start_year < 100:
                                    start_year += 2000
                                if end_year < 100:
                                    end_year += 2000
                                
                                try:
                                    start_date = datetime(start_year, start_month, start_day)
                                    end_date = datetime(end_year, end_month, end_day)
                                    logger.info(f"Extracted date range with year: {start_date.strftime('%d %b %Y')} to {end_date.strftime('%d %b %Y')}")
                                    return self._calculate_date_details(start_date, end_date, query)
                                except ValueError as e:
                                    logger.warning(f"Invalid date: {e}")
                                    continue
                        else:
                            # Pattern: "from 4/2/2024 to 9/2/2024" (numeric format)
                            start_day = int(groups[0])
                            start_month = int(groups[1])
                            start_year = int(groups[2])
                            end_day = int(groups[3])
                            end_month = int(groups[4])
                            end_year = int(groups[5])
                            
                            # Handle 2-digit years
                            if start_year < 100:
                                start_year += 2000
                            if end_year < 100:
                                end_year += 2000
                            
                            try:
                                start_date = datetime(start_year, start_month, start_day)
                                end_date = datetime(end_year, end_month, end_day)
                                return self._calculate_date_details(start_date, end_date, query)
                            except ValueError as e:
                                logger.warning(f"Invalid date: {e}")
                                continue
                    
                except (ValueError, IndexError) as e:
                    logger.debug(f"Error parsing date pattern: {e}")
                    continue
        
        # Pattern 2: Single date mentions (less common for booking queries)
        # "on 4 feb" or "4 february"
        single_date_patterns = [
            r"(?:on|for)\s+(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|may|june|july|august|september|october|november|december)",
            r"(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|may|june|july|august|september|october|november|december)",
        ]
        
        for pattern in single_date_patterns:
            match = re.search(pattern, query_lower)
            if match:
                try:
                    day = int(match.group(1))
                    month_str = match.group(2).lower()
                    
                    if month_str in self.MONTH_NAMES:
                        month = self.MONTH_NAMES[month_str]
                        year = datetime.now().year
                        
                        try:
                            start_date = datetime(year, month, day)
                            # Assume 1 night stay if only start date given
                            end_date = start_date + timedelta(days=1)
                            return self._calculate_date_details(start_date, end_date, query)
                        except ValueError as e:
                            logger.warning(f"Invalid date: {e}")
                            continue
                except (ValueError, IndexError) as e:
                    logger.debug(f"Error parsing single date: {e}")
                    continue
        
        logger.debug(f"Could not extract date range from: {query}")
        return None
    
    def _calculate_date_details(
        self, 
        start_date: datetime, 
        end_date: datetime,
        original_query: str
    ) -> Dict:
        """
        Calculate detailed date information from start and end dates.
        
        Args:
            start_date: Start datetime
            end_date: End datetime
            original_query: Original user query for context
            
        Returns:
            Dictionary with date details
        """
        # Calculate number of nights
        # In accommodation context, "from 5 feb to 15 feb" means:
        # Check-in: Feb 5, Check-out: Feb 15
        # Nights stayed: Feb 5, 6, 7, 8, 9, 10, 11, 12, 13, 14 (10 nights)
        # The difference in days IS the number of nights
        nights = (end_date - start_date).days
        
        # Log for debugging
        logger.info(f"Date calculation: {start_date.strftime('%d %b %Y')} to {end_date.strftime('%d %b %Y')} = {nights} nights")
        
        if nights <= 0:
            # If end date is same as start date, assume 1 night
            nights = 1
            end_date = start_date + timedelta(days=1)
        
        # Generate list of all dates in range
        # Uses Python's datetime.weekday() which correctly identifies weekdays/weekends
        # based on the actual calendar for the year (handles leap years, etc.)
        date_list = []
        current_date = start_date
        weekday_nights = 0
        weekend_nights = 0
        
        while current_date < end_date:
            date_list.append(current_date)
            # Monday = 0, Sunday = 6
            # Weekday: Monday-Friday (0-4), Weekend: Saturday-Sunday (5-6)
            # This uses the actual calendar for the year, so it correctly identifies
            # which days are weekdays vs weekends based on the real calendar
            if current_date.weekday() < 5:  # Monday to Friday
                weekday_nights += 1
            else:  # Saturday or Sunday
                weekend_nights += 1
            current_date += timedelta(days=1)
        
        # Format dates as strings
        start_date_str = start_date.strftime("%d %b %Y")
        end_date_str = end_date.strftime("%d %b %Y")
        
        return {
            "start_date": start_date_str,
            "end_date": end_date_str,
            "parsed_start": start_date,
            "parsed_end": end_date,
            "nights": nights,
            "weekday_nights": weekday_nights,
            "weekend_nights": weekend_nights,
            "date_list": date_list,
        }
    
    def parse_date_string(self, date_str: str) -> Optional[datetime]:
        """
        Parse a date string into datetime object.
        
        Args:
            date_str: Date string in various formats
            
        Returns:
            datetime object or None if parsing fails
        """
        date_str_lower = date_str.lower().strip()
        
        # Try common formats
        formats = [
            "%d %b %Y",  # "4 Feb 2024"
            "%d %B %Y",  # "4 February 2024"
            "%d/%m/%Y",  # "4/2/2024"
            "%d-%m-%Y",  # "4-2-2024"
            "%d %b",     # "4 Feb" (assume current year)
            "%d %B",     # "4 February" (assume current year)
        ]
        
        for fmt in formats:
            try:
                parsed = datetime.strptime(date_str, fmt)
                # If no year in format, assume current year
                if "%Y" not in fmt:
                    parsed = parsed.replace(year=datetime.now().year)
                return parsed
            except ValueError:
                continue
        
        # Try to extract day and month from natural language
        match = re.search(r"(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|may|june|july|august|september|october|november|december)", date_str_lower)
        if match:
            try:
                day = int(match.group(1))
                month_str = match.group(2).lower()
                if month_str in self.MONTH_NAMES:
                    month = self.MONTH_NAMES[month_str]
                    year = datetime.now().year
                    return datetime(year, month, day)
            except (ValueError, IndexError):
                pass
        
        logger.debug(f"Could not parse date string: {date_str}")
        return None
    
    def validate_date_range(self, start_date: datetime, end_date: datetime) -> Tuple[bool, Optional[str]]:
        """
        Validate that a date range is reasonable.
        
        Args:
            start_date: Start datetime
            end_date: End datetime
            
        Returns:
            Tuple of (is_valid: bool, error_message: str or None)
        """
        if end_date <= start_date:
            return False, "End date must be after start date"
        
        # Check if dates are too far in the past
        if start_date < datetime.now() - timedelta(days=365):
            return False, "Start date is too far in the past"
        
        # Check if dates are too far in the future (e.g., more than 2 years)
        if start_date > datetime.now() + timedelta(days=730):
            return False, "Start date is too far in the future"
        
        # Check if stay is too long (e.g., more than 30 nights)
        nights = (end_date - start_date).days
        if nights > 30:
            return False, f"Stay duration ({nights} nights) exceeds maximum allowed (30 nights)"
        
        return True, None


# Global instance for easy access
_date_extractor: Optional[DateExtractor] = None


def get_date_extractor() -> DateExtractor:
    """
    Get or create the global date extractor instance.
    
    Returns:
        DateExtractor instance
    """
    global _date_extractor
    if _date_extractor is None:
        _date_extractor = DateExtractor()
    return _date_extractor
