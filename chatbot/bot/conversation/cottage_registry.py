"""Cottage registry for managing cottage information and smart filtering."""

from typing import Dict, List, Optional
from dataclasses import dataclass

@dataclass
class CottageInfo:
    number: str
    bedrooms: int
    base_capacity: int
    max_capacity: int
    description: str
    features: List[str]
    is_recommended: bool = False  # Mark recommended cottages (9, 11)
    show_by_default: bool = True  # Show in general listings (9, 11 only)
    
class CottageRegistry:
    """Central registry of all cottages with smart filtering."""
    
    def __init__(self):
        self._cottages = self._load_cottages()
        self._recommended_cottages = {"9", "11"}  # Only 9 and 11 are recommended
        self._total_cottages = 7  # Total number of cottages
    
    def _load_cottages(self) -> Dict[str, CottageInfo]:
        """Load cottage information."""
        return {
            # Cottage 7 - Only show if specifically asked or 2-bedroom query
            "7": CottageInfo(
                number="7",
                bedrooms=2,
                base_capacity=6,
                max_capacity=9,
                description="2-bedroom corner cottage with dual-sided panoramic views, ideal for smaller families",
                features=["2 bedrooms", "Corner positioning", "Panoramic views", "Enhanced privacy"],
                is_recommended=False,  # NOT recommended
                show_by_default=False  # Don't show by default
            ),
            # Cottage 9 - Recommended, show normally
            "9": CottageInfo(
                number="9",
                bedrooms=3,
                base_capacity=6,
                max_capacity=9,
                description="3-bedroom, two-storey cottage with spacious lounge, ideal for larger groups",
                features=["3 bedrooms", "Two-storey", "Master bedroom with en-suite", "Balcony"],
                is_recommended=True,
                show_by_default=True
            ),
            # Cottage 11 - Recommended, show normally
            "11": CottageInfo(
                number="11",
                bedrooms=3,
                base_capacity=6,
                max_capacity=9,
                description="3-bedroom, two-storey cottage with unique attic space, popular with families",
                features=["3 bedrooms", "Two-storey", "Attic sleeping space", "Family-friendly"],
                is_recommended=True,
                show_by_default=True
            ),
        }
    
    def get_cottage(self, number: str) -> Optional[CottageInfo]:
        """Get cottage by number."""
        return self._cottages.get(str(number).strip())
    
    def get_total_cottages(self) -> int:
        """Get total number of cottages."""
        return self._total_cottages
    
    def get_recommended_cottages(self) -> List[CottageInfo]:
        """Get list of recommended cottages (9 and 11 only)."""
        return [cottage for cottage in self._cottages.values() if cottage.is_recommended]
    
    def list_cottages_by_filter(
        self, 
        query: str = "",
        include_all: bool = False
    ) -> List[CottageInfo]:
        """
        List cottages based on query context.
        
        Rules:
        - Cottages 9 and 11: Show normally (recommended)
        - Cottage 7: Only show if specifically asked or 2-bedroom query
        - Total: 7 cottages
        
        Args:
            query: User query to determine which cottages to show
            include_all: If True, include all cottages (for "how many cottages" queries)
        
        Returns:
            Filtered list of cottages
        """
        query_lower = query.lower()
        
        # Check for specific cottage mentions
        mentioned_cottages = set()
        for cottage_num in ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"]:
            if f"cottage {cottage_num}" in query_lower or f"cottage{cottage_num}" in query_lower:
                mentioned_cottages.add(cottage_num)
        
        # If specific cottages mentioned, show those
        if mentioned_cottages:
            result = []
            for num in mentioned_cottages:
                cottage = self.get_cottage(num)
                if cottage:
                    result.append(cottage)
            # If we found mentioned cottages, return them
            if result:
                return result
        
        # Check for bedroom type queries
        if "2 bedroom" in query_lower or "two bedroom" in query_lower:
            # Show 2-bedroom cottages (Cottage 7)
            return [cottage for cottage in self._cottages.values() if cottage.bedrooms == 2]
        
        if "3 bedroom" in query_lower or "three bedroom" in query_lower:
            # Show 3-bedroom cottages (Cottages 9 and 11)
            return [cottage for cottage in self._cottages.values() if cottage.bedrooms == 3]
        
        # For "how many cottages" or "total cottages" queries
        if include_all or any(phrase in query_lower for phrase in [
            "how many cottages", "total cottages", "number of cottages"
        ]):
            # Return recommended cottages (9 and 11) for recommendation
            return self.get_recommended_cottages()
        
        # Default: Show only recommended cottages (9 and 11)
        # Cottage 7 is NOT shown unless specifically asked
        return [cottage for cottage in self._cottages.values() if cottage.show_by_default]
    
    def format_cottage_list(
        self, 
        query: str = "",
        show_total: bool = False
    ) -> str:
        """
        Format cottage list as a readable string.
        
        Args:
            query: User query for context
            show_total: If True, mention total cottages and recommendations
        
        Returns:
            Formatted string with cottage information
        """
        cottages = self.list_cottages_by_filter(query, include_all=show_total)
        
        lines = []
        
        # Add header with total count if requested
        if show_total:
            lines.append(f"🏡 **Swiss Cottages Bhurban has {self._total_cottages} cottages in the neighborhood.**\n")
            lines.append(f"**I recommend these {len(cottages)} cottages as the best options:**\n")
        else:
            lines.append("🏡 **Swiss Cottages Bhurban offers the following cottages:**\n")
        
        # Format each cottage
        for cottage in cottages:
            lines.append(f"**Cottage {cottage.number}** - {cottage.description}")
            lines.append(f"- Base capacity: Up to {cottage.base_capacity} guests (standard capacity)")
            lines.append(f"- Maximum capacity: {cottage.max_capacity} guests (with prior confirmation)")
            lines.append(f"- Bedrooms: {cottage.bedrooms}")
            lines.append("")
        
        return "\n".join(lines)
    
    def format_total_cottages_response(self) -> str:
        """Format response for 'how many cottages' queries."""
        recommended = self.get_recommended_cottages()
        
        return (
            f"🏡 **Swiss Cottages Bhurban has {self._total_cottages} cottages in the neighborhood.**\n\n"
            f"**I recommend these {len(recommended)} cottages as the best options:**\n\n"
            f"{self.format_cottage_list(show_total=False)}\n"
            "All cottages include:\n"
            "- Fully equipped kitchen\n"
            "- Living lounge\n"
            "- Bedrooms and bathrooms\n"
            "- Outdoor terrace/balcony\n"
            "- Wi-Fi, smart TV with Netflix\n"
            "- Heating system\n"
            "- Secure parking\n\n"
            "Would you like to know more about:\n"
            "- Pricing for a specific cottage\n"
            "- Which cottage is best for your group size\n"
            "- Availability and booking information"
        )

# Global instance
_cottage_registry: Optional[CottageRegistry] = None

def get_cottage_registry() -> CottageRegistry:
    """
    Get or create the global cottage registry instance.
    
    Returns:
        CottageRegistry instance
    """
    global _cottage_registry
    if _cottage_registry is None:
        _cottage_registry = CottageRegistry()
    return _cottage_registry
