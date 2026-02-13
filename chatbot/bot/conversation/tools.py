"""LLM tools for pricing and capacity calculations."""

import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from helpers.log import get_logger
from bot.conversation.pricing_calculator import PricingCalculator, get_pricing_calculator
from bot.conversation.cottage_capacity import CottageCapacityMapper, get_capacity_mapper
from bot.conversation.date_extractor import DateExtractor, get_date_extractor

logger = get_logger(__name__)


def calculate_pricing(
    cottage_id: str,
    guests: int,
    nights: int,
    start_date: Optional[str] = None
) -> str:
    """
    Calculate pricing for a cottage stay.
    
    Args:
        cottage_id: Cottage number (7, 9, or 11) as string
        guests: Number of guests (1-9)
        nights: Number of nights
        start_date: Optional check-in date (format: YYYY-MM-DD or natural language)
        
    Returns:
        JSON string with pricing breakdown
    """
    try:
        # Normalize cottage ID
        cottage_number = str(cottage_id).strip().lower()
        cottage_number = cottage_number.replace("cottage", "").strip()
        
        # Validate inputs
        if cottage_number not in ["7", "9", "11"]:
            return json.dumps({
                "error": f"Invalid cottage ID: {cottage_id}. Must be 7, 9, or 11.",
                "total_price": 0
            })
        
        if not (1 <= guests <= 9):
            return json.dumps({
                "error": f"Invalid guest count: {guests}. Must be between 1 and 9.",
                "total_price": 0
            })
        
        if nights < 1:
            return json.dumps({
                "error": f"Invalid number of nights: {nights}. Must be at least 1.",
                "total_price": 0
            })
        
        # Get pricing calculator
        pricing_calculator = get_pricing_calculator()
        
        # Parse dates if provided
        dates_dict = None
        if start_date:
            date_extractor = get_date_extractor()
            try:
                # Try to extract date range from start_date string
                # If it's just a start date, calculate end date based on nights
                parsed_dates = date_extractor.extract_date_range(start_date)
                if parsed_dates:
                    dates_dict = parsed_dates
                else:
                    # Try parsing as single date and adding nights
                    from datetime import datetime, timedelta
                    # Try common date formats
                    for fmt in ["%Y-%m-%d", "%d %B %Y", "%B %d, %Y", "%d/%m/%Y", "%m/%d/%Y"]:
                        try:
                            start = datetime.strptime(start_date.strip(), fmt)
                            end = start + timedelta(days=nights)
                            # Create dates dict with weekday/weekend breakdown
                            dates_dict = date_extractor._calculate_weekday_weekend_nights(start, end)
                            dates_dict["start_date"] = start.strftime("%Y-%m-%d")
                            dates_dict["end_date"] = end.strftime("%Y-%m-%d")
                            dates_dict["nights"] = nights
                            break
                        except ValueError:
                            continue
            except Exception as e:
                logger.warning(f"Failed to parse date '{start_date}': {e}")
        
        # If no dates provided, create a simple dates dict with just nights
        if not dates_dict:
            dates_dict = {
                "nights": nights,
                "weekday_nights": 0,  # Unknown breakdown
                "weekend_nights": 0
            }
        
        # Calculate price
        result = pricing_calculator.calculate_price(
            guests=guests,
            dates=dates_dict,
            cottage_number=cottage_number,
            season=None
        )
        
        # Format result as JSON
        return json.dumps({
            "total_price": result.get("total_price", 0),
            "breakdown": result.get("breakdown", ""),
            "nights": result.get("nights", nights),
            "weekday_nights": result.get("weekday_nights", 0),
            "weekend_nights": result.get("weekend_nights", 0),
            "per_night_weekday": result.get("per_night_weekday", 0),
            "per_night_weekend": result.get("per_night_weekend", 0),
            "guest_count": guests,
            "cottage": cottage_number,
            "error": result.get("error")
        }, indent=2)
        
    except Exception as e:
        logger.error(f"Error calculating pricing: {e}", exc_info=True)
        return json.dumps({
            "error": f"Failed to calculate pricing: {str(e)}",
            "total_price": 0
        })


def check_capacity(cottage_id: str, guests: int) -> str:
    """
    Check if a cottage can accommodate the number of guests.
    
    Args:
        cottage_id: Cottage number (7, 9, or 11) as string
        guests: Number of guests
        
    Returns:
        JSON string with capacity information
    """
    try:
        # Normalize cottage ID
        cottage_number = str(cottage_id).strip().lower()
        cottage_number = cottage_number.replace("cottage", "").strip()
        
        # Validate inputs
        if cottage_number not in ["7", "9", "11"]:
            return json.dumps({
                "error": f"Invalid cottage ID: {cottage_id}. Must be 7, 9, or 11.",
                "suitable": False
            })
        
        if guests < 1:
            return json.dumps({
                "error": f"Invalid guest count: {guests}. Must be at least 1.",
                "suitable": False
            })
        
        # Get capacity mapper
        capacity_mapper = get_capacity_mapper()
        
        # Get capacity info
        capacity_info = capacity_mapper.get_capacity(cottage_number)
        if not capacity_info:
            return json.dumps({
                "error": f"Capacity information not available for cottage {cottage_id}",
                "suitable": False
            })
        
        # Check suitability
        is_suitable, reason = capacity_mapper.is_suitable(guests, cottage_number)
        
        # Format result as JSON
        return json.dumps({
            "suitable": is_suitable,
            "reason": reason,
            "cottage": cottage_number,
            "guests": guests,
            "base_capacity": capacity_info.get("base_capacity", 6),
            "max_capacity": capacity_info.get("max_capacity", 9),
            "bedrooms": capacity_info.get("bedrooms", 2)
        }, indent=2)
        
    except Exception as e:
        logger.error(f"Error checking capacity: {e}", exc_info=True)
        return json.dumps({
            "error": f"Failed to check capacity: {str(e)}",
            "suitable": False
        })


# Tool configuration for LLM
TOOLS_CONFIG = [
    {
        "type": "function",
        "function": {
            "name": "calculate_pricing",
            "description": "Calculate pricing for a cottage stay. Use this when user asks about prices, costs, or wants to know how much a stay would cost.",
            "parameters": {
                "type": "object",
                "properties": {
                    "cottage_id": {
                        "type": "string",
                        "description": "Cottage number: '7', '9', or '11' (can be 'cottage 7', '7', etc.)"
                    },
                    "guests": {
                        "type": "integer",
                        "description": "Number of guests (1-9)"
                    },
                    "nights": {
                        "type": "integer",
                        "description": "Number of nights for the stay"
                    },
                    "start_date": {
                        "type": "string",
                        "description": "Optional check-in date in format YYYY-MM-DD or natural language like 'March 15, 2025' or 'next Monday'. If not provided, pricing will be estimated."
                    }
                },
                "required": ["cottage_id", "guests", "nights"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_capacity",
            "description": "Check if a cottage can accommodate a specific number of guests. Use this when user asks if a cottage is suitable for their group size, or wants to know capacity information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "cottage_id": {
                        "type": "string",
                        "description": "Cottage number: '7', '9', or '11' (can be 'cottage 7', '7', etc.)"
                    },
                    "guests": {
                        "type": "integer",
                        "description": "Number of guests to check capacity for"
                    }
                },
                "required": ["cottage_id", "guests"]
            }
        }
    }
]

# Tool function map
TOOLS_MAP = {
    "calculate_pricing": calculate_pricing,
    "check_capacity": check_capacity
}


def get_tools_config() -> list:
    """Get tools configuration for LLM."""
    return TOOLS_CONFIG


def get_tools_map() -> dict:
    """Get tools function map."""
    return TOOLS_MAP
