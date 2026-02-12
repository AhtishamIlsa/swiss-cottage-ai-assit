"""Cottage capacity data extraction and mapping."""

import re
from pathlib import Path
from typing import Dict, Optional, Tuple
from helpers.log import get_logger

logger = get_logger(__name__)


class CottageCapacityMapper:
    """Maps cottage numbers to their capacity information."""
    
    def __init__(self, docs_path: Optional[Path] = None):
        """
        Initialize the capacity mapper.
        
        Args:
            docs_path: Path to docs/faq directory. If None, uses default location.
        """
        if docs_path is None:
            # Default to docs/faq relative to chatbot directory
            chatbot_dir = Path(__file__).resolve().parent.parent.parent
            docs_path = chatbot_dir / "docs" / "faq"
        
        self.docs_path = docs_path
        self._capacity_map: Dict[str, Dict[str, int]] = {}
        self._load_capacity_data()
    
    def _load_capacity_data(self) -> None:
        """Load capacity data from FAQ files and build mapping."""
        # Base capacity rules from FAQs:
        # - FAQ 020: Each cottage comfortably accommodates up to 6 guests at base price
        # - FAQ 018: No more than 9 guests are allowed in a single cottage (hard limit)
        # - FAQ 042: 3-bedroom cottage can accommodate up to 10 guests, 2-bedroom up to 6 guests
        # - FAQ 017: 3-bedroom up to 10 guests, 2-bedroom up to 6 guests
        # 
        # IMPORTANT: FAQ 018 states max 9 guests in ANY single cottage (safety/community guidelines)
        # So even 3-bedroom cottages have a hard limit of 9 guests, despite FAQ 042 saying 10
        
        # Known cottage configurations from FAQ analysis
        cottage_configs = {
            "7": {"bedrooms": 2, "base_capacity": 6, "max_capacity": 9},  # 2-bedroom, max 9 (hard limit)
            "9": {"bedrooms": 3, "base_capacity": 6, "max_capacity": 9},  # 3-bedroom, but max 9 (hard limit from FAQ 018)
            "11": {"bedrooms": 3, "base_capacity": 6, "max_capacity": 9},  # 3-bedroom, but max 9 (hard limit from FAQ 018)
        }
        
        # Try to extract additional info from FAQ files
        if self.docs_path.exists():
            for md_file in self.docs_path.glob("*.md"):
                try:
                    content = md_file.read_text(encoding='utf-8')
                    self._extract_capacity_from_content(content, cottage_configs)
                except Exception as e:
                    logger.debug(f"Error reading {md_file}: {e}")
        
        # Apply default rules for unknown cottages
        # If cottage not found, assume 2-bedroom (most common)
        self._capacity_map = cottage_configs
        
        logger.info(f"Loaded capacity data for {len(self._capacity_map)} cottages")
    
    def _extract_capacity_from_content(self, content: str, cottage_configs: Dict) -> None:
        """Extract capacity information from FAQ content."""
        content_lower = content.lower()
        
        # Look for cottage numbers mentioned with bedroom info
        cottage_pattern = r"cottage\s*(\d+)"
        bedroom_pattern = r"(\d+)[-\s]*bedroom"
        
        # Find all cottage numbers mentioned
        cottage_matches = re.findall(cottage_pattern, content_lower)
        bedroom_matches = re.findall(bedroom_pattern, content_lower)
        
        # Try to match cottages with bedroom counts
        for cottage_num in cottage_matches:
            if cottage_num not in cottage_configs:
                # Default to 2-bedroom if not specified
                cottage_configs[cottage_num] = {
                    "bedrooms": 2,
                    "base_capacity": 6,
                    "max_capacity": 9
                }
    
    def get_capacity(self, cottage_number: str) -> Optional[Dict[str, int]]:
        """
        Get capacity information for a cottage.
        
        Args:
            cottage_number: Cottage number as string (e.g., "3", "7", "9")
            
        Returns:
            Dictionary with keys: bedrooms, base_capacity, max_capacity
            Returns None if cottage not found
        """
        # Normalize cottage number (remove "cottage" prefix if present)
        cottage_num = str(cottage_number).strip().lower()
        cottage_num = re.sub(r"^cottage\s*", "", cottage_num)
        
        if cottage_num in self._capacity_map:
            return self._capacity_map[cottage_num].copy()
        
        # Default fallback: assume 2-bedroom cottage
        logger.warning(f"Cottage {cottage_number} not found in capacity map, using default (2-bedroom)")
        return {
            "bedrooms": 2,
            "base_capacity": 6,
            "max_capacity": 9
        }
    
    def is_suitable(self, group_size: int, cottage_number: str) -> Tuple[bool, str]:
        """
        Check if a group size is suitable for a cottage.
        
        Args:
            group_size: Number of people in the group
            cottage_number: Cottage number as string
            
        Returns:
            Tuple of (is_suitable: bool, reason: str)
        """
        capacity_info = self.get_capacity(cottage_number)
        if not capacity_info:
            return False, f"Cottage {cottage_number} capacity information not available"
        
        base_capacity = capacity_info["base_capacity"]
        max_capacity = capacity_info["max_capacity"]
        
        if group_size <= base_capacity:
            return True, f"{group_size} guests ≤ {base_capacity} base capacity (comfortable at standard capacity)"
        elif group_size <= max_capacity:
            return True, f"{group_size} guests ≤ {max_capacity} max capacity (possible with prior confirmation and adjusted pricing)"
        else:
            return False, f"{group_size} guests > {max_capacity} max capacity (not suitable - for comfort, safety, and community guidelines, no more than {max_capacity} guests are allowed in a single cottage. Groups exceeding this limit must book multiple cottages)"
    
    def get_all_cottages(self) -> list[str]:
        """
        Get list of all known cottage numbers.
        
        Returns:
            List of cottage numbers as strings
        """
        return list(self._capacity_map.keys())
    
    def get_capacity_summary(self, cottage_number: str) -> str:
        """
        Get a human-readable capacity summary for a cottage.
        
        Args:
            cottage_number: Cottage number as string
            
        Returns:
            Formatted capacity summary string
        """
        capacity_info = self.get_capacity(cottage_number)
        if not capacity_info:
            return f"Cottage {cottage_number}: Capacity information not available"
        
        bedrooms = capacity_info["bedrooms"]
        base = capacity_info["base_capacity"]
        max_cap = capacity_info["max_capacity"]
        
        if base == max_cap:
            return f"Cottage {cottage_number}: {bedrooms}-bedroom cottage, accommodates up to {max_cap} guests"
        else:
            return f"Cottage {cottage_number}: {bedrooms}-bedroom cottage, accommodates up to {base} guests at standard capacity, up to {max_cap} guests with prior confirmation"


# Global instance for easy access
_capacity_mapper: Optional[CottageCapacityMapper] = None


def get_capacity_mapper(docs_path: Optional[Path] = None) -> CottageCapacityMapper:
    """
    Get or create the global capacity mapper instance.
    
    Args:
        docs_path: Optional path to docs/faq directory
        
    Returns:
        CottageCapacityMapper instance
    """
    global _capacity_mapper
    if _capacity_mapper is None:
        _capacity_mapper = CottageCapacityMapper(docs_path)
    return _capacity_mapper
