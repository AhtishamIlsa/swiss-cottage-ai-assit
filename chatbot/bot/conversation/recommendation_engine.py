"""Recommendation engine for gentle suggestions and booking nudges."""

from typing import Dict, Any, Optional
from helpers.log import get_logger
from bot.conversation.intent_router import IntentType
from bot.conversation.slot_manager import SlotManager
from bot.conversation.context_tracker import ContextTracker

logger = get_logger(__name__)


class RecommendationEngine:
    """Generates gentle recommendations and booking nudges."""
    
    def __init__(self):
        """Initialize the recommendation engine."""
        pass
    
    def generate_gentle_recommendation(
        self,
        intent: IntentType,
        slots: Dict[str, Any],
        context_tracker: Optional[ContextTracker] = None
    ) -> Optional[str]:
        """
        Generate gentle recommendation for pricing, rooms, or safety intents.
        
        Args:
            intent: Detected intent
            slots: Current slot values
            context_tracker: Optional context tracker
            
        Returns:
            Recommendation string or None
        """
        if intent == IntentType.PRICING:
            return self._generate_pricing_recommendation(slots)
        elif intent == IntentType.ROOMS:
            return self._generate_rooms_recommendation(slots)
        elif intent == IntentType.SAFETY:
            return self._generate_safety_recommendation(slots)
        
        return None
    
    def _generate_pricing_recommendation(self, slots: Dict[str, Any]) -> str:
        """Generate pricing recommendation."""
        recommendations = []
        
        # Check if season is specified
        season = slots.get("season")
        if season:
            if season == "weekday":
                recommendations.append("💡 **Tip:** Weekday rates are typically lower than weekend rates, making them a great value option.")
            elif season == "weekend":
                recommendations.append("💡 **Tip:** Weekend rates are slightly higher, but you'll enjoy the full weekend experience.")
            elif season == "peak":
                recommendations.append("💡 **Tip:** Peak season rates apply, so booking in advance is recommended.")
        
        # Check guest count
        guests = slots.get("guests")
        if guests:
            if guests <= 6:
                recommendations.append("💡 **Tip:** For groups of 6 or fewer, you can book at base price. All cottages accommodate up to 6 guests comfortably.")
            elif guests <= 9:
                recommendations.append("💡 **Tip:** For groups of 7-9 guests, prior confirmation and adjusted pricing apply. All cottages can accommodate up to 9 guests.")
        
        # General pricing tip
        if not recommendations:
            recommendations.append("💡 **Tip:** Weekday rates are typically lower than weekend rates. Advance payment is required to confirm your booking.")
        
        return "\n".join(recommendations)
    
    def _generate_rooms_recommendation(self, slots: Dict[str, Any]) -> str:
        """Generate rooms recommendation."""
        recommendations = []
        seen_recommendations = set()  # Track to avoid duplicates
        
        guests = slots.get("guests")
        room_type = slots.get("room_type")
        family = slots.get("family")
        
        # Priority: specific recommendations first, then general
        if room_type:
            if room_type == "cottage_9" or room_type == "cottage_11":
                rec = "💡 **Tip:** Cottage 9 and Cottage 11 are 3-bedroom cottages, perfect for families or larger groups."
                if rec not in seen_recommendations:
                    recommendations.append(rec)
                    seen_recommendations.add(rec)
            elif room_type == "cottage_7":
                rec = "💡 **Tip:** Cottage 7 is a 2-bedroom cottage, ideal for smaller groups or couples."
                if rec not in seen_recommendations:
                    recommendations.append(rec)
                    seen_recommendations.add(rec)
        
        if guests:
            if guests <= 6:
                if not room_type or room_type == "any":
                    rec = "💡 **Tip:** For groups of 6 or fewer, any cottage (Cottage 7, 9, or 11) is suitable at base price."
                    if rec not in seen_recommendations:
                        recommendations.append(rec)
                        seen_recommendations.add(rec)
                if family and (not room_type or room_type in ["cottage_9", "cottage_11", "any"]):
                    rec = "💡 **Tip:** Cottage 9 and Cottage 11 are 3-bedroom cottages with more space, ideal for families."
                    if rec not in seen_recommendations:
                        recommendations.append(rec)
                        seen_recommendations.add(rec)
            elif guests <= 9:
                rec = "💡 **Tip:** All cottages can accommodate up to 9 guests with prior confirmation. Cottage 9 and 11 offer more space for larger groups."
                if rec not in seen_recommendations:
                    recommendations.append(rec)
                    seen_recommendations.add(rec)
        
        # Only add general recommendation if no specific ones were added
        if not recommendations:
            rec = "💡 **Tip:** All cottages offer comfortable accommodation. Cottage 9 and 11 are 3-bedroom options with more space."
            recommendations.append(rec)
        
        return "\n".join(recommendations)
    
    def _generate_safety_recommendation(self, slots: Dict[str, Any]) -> str:
        """Generate safety recommendation."""
        return (
            "💡 **Tip:** Swiss Cottages prioritize guest safety and security. "
            "All cottages have safety measures in place, and emergency contacts are available. "
            "If you have specific safety concerns, feel free to ask, or contact our team directly."
        )
    
    def generate_booking_nudge(
        self, 
        slots: Dict[str, Any],
        context_tracker: Optional[ContextTracker] = None,
        intent: Optional[IntentType] = None
    ) -> Optional[str]:
        """
        Generate soft booking nudge if enough information is available AND user seems ready.
        
        Args:
            slots: Current slot values
            context_tracker: Optional context tracker to check user journey
            intent: Current intent to determine if booking nudge is appropriate
            
        Returns:
            Booking nudge string or None
        """
        # Only show booking nudge if user has asked about booking or availability
        if context_tracker:
            recent_intents = context_tracker.get_recent_intents(5)
            has_booking_intent = IntentType.BOOKING in recent_intents
            has_availability_intent = IntentType.AVAILABILITY in recent_intents
            
            # Only show if user has asked about booking/availability OR current intent is booking/availability
            if intent:
                should_show = (intent in [IntentType.BOOKING, IntentType.AVAILABILITY] or 
                              has_booking_intent or has_availability_intent)
            else:
                should_show = has_booking_intent or has_availability_intent
            
            if not should_show:
                return None  # Don't show booking nudge if user hasn't shown interest in booking
        
        # Check if enough info for booking
        has_guests = slots.get("guests") is not None
        has_dates = slots.get("dates") is not None
        has_room_type = slots.get("room_type") is not None
        
        # Need at least 2 out of 3 key slots
        filled_count = sum([has_guests, has_dates, has_room_type])
        
        if filled_count >= 2:
            nudge = "💡 **Ready to book?** "
            
            if has_guests and has_dates and has_room_type:
                nudge += "You have all the key information! Would you like to proceed with booking? "
            elif has_guests and has_dates:
                nudge += "You've shared your group size and dates. Would you like to explore booking options? "
            elif has_guests and has_room_type:
                nudge += "You've shared your group size and preferred cottage. Would you like to check availability? "
            elif has_dates and has_room_type:
                nudge += "You've shared your dates and preferred cottage. Would you like to proceed with booking? "
            
            nudge += "I can help you with the booking process or answer any other questions you have.\n\n"
            nudge += "**To proceed with booking, you can:**\n"
            nudge += "- Contact us: https://swisscottagesbhurban.com/contact-us/\n"
            nudge += "- Cottage Manager (Abdullah): +92 300 1218563\n"
            
            # Add Airbnb links based on room type if available
            room_type = slots.get("room_type")
            if room_type == "cottage_7":
                nudge += "- View on Airbnb - Cottage 7: https://www.airbnb.com/rooms/886682083069412842\n"
            elif room_type == "cottage_9":
                nudge += "- View on Airbnb - Cottage 9: https://www.airbnb.com/rooms/651168099240245080\n"
            elif room_type == "cottage_11":
                nudge += "- View on Airbnb - Cottage 11: https://www.airbnb.com/rooms/886682083069412842\n"
            else:
                nudge += "- Book through Airbnb or contact us directly for assistance\n"
            
            return nudge
        
        return None
    
    def generate_alternative_suggestion(
        self,
        intent: IntentType,
        slots: Dict[str, Any],
        unavailable_item: str
    ) -> Optional[str]:
        """
        Suggest alternatives when primary option is unavailable.
        
        Args:
            intent: Detected intent
            slots: Current slot values
            unavailable_item: What's unavailable
            
        Returns:
            Alternative suggestion string or None
        """
        if intent == IntentType.AVAILABILITY:
            room_type = slots.get("room_type")
            if room_type and room_type != "any":
                # Suggest other cottages
                if room_type == "cottage_7":
                    return "💡 **Alternative:** Cottage 9 and Cottage 11 are also available and offer 3-bedroom options with more space."
                elif room_type in ["cottage_9", "cottage_11"]:
                    return "💡 **Alternative:** Cottage 7 is a 2-bedroom option that might be available for your dates."
                else:
                    return "💡 **Alternative:** Other cottages might be available. Would you like me to check availability for different dates?"
        
        return None
    
    def generate_image_recommendation(
        self,
        query: str,
        slots: Dict[str, Any],
        intent: Optional[IntentType] = None
    ) -> Optional[str]:
        """
        Generate a gentle recommendation to show images when a cottage is mentioned.
        
        Args:
            query: User's query string
            slots: Current slot values
            intent: Current intent
            
        Returns:
            Image recommendation string or None
        """
        query_lower = query.lower()
        
        # Don't suggest images if user already asked for them
        image_keywords = [
            "image", "images", "photo", "photos", "picture", "pictures",
            "show me", "see", "view", "gallery", "visual"
        ]
        if any(keyword in query_lower for keyword in image_keywords):
            return None  # User already asked for images
        
        # Check if a cottage is mentioned
        room_type = slots.get("room_type")
        has_cottage_in_query = any(
            cottage in query_lower 
            for cottage in ["cottage 7", "cottage 9", "cottage 11", "cottage7", "cottage9", "cottage11"]
        )
        
        # Only suggest images if:
        # 1. A specific cottage is mentioned (room_type slot or in query)
        # 2. Intent is ROOMS, PRICING, or general inquiry about cottages
        # 3. User hasn't already asked for images
        
        if room_type or has_cottage_in_query:
            # Determine which cottage(s) to mention
            cottage_mention = ""
            if room_type:
                if room_type == "cottage_7":
                    cottage_mention = "Cottage 7"
                elif room_type == "cottage_9":
                    cottage_mention = "Cottage 9"
                elif room_type == "cottage_11":
                    cottage_mention = "Cottage 11"
                elif room_type == "any":
                    cottage_mention = "the cottages"
            elif has_cottage_in_query:
                # Extract cottage number from query
                for num in ["7", "9", "11"]:
                    if f"cottage {num}" in query_lower or f"cottage{num}" in query_lower:
                        cottage_mention = f"Cottage {num}"
                        break
                if not cottage_mention:
                    cottage_mention = "the cottages"
            
            if cottage_mention:
                # Only suggest for relevant intents or general cottage questions
                relevant_intents = [IntentType.ROOMS, IntentType.PRICING]
                is_general_cottage_question = (
                    "cottage" in query_lower and 
                    intent not in [IntentType.BOOKING, IntentType.AVAILABILITY]
                )
                
                if intent in relevant_intents or is_general_cottage_question:
                    return f"📷 **Would you like to see images of {cottage_mention.lower()}?** Just ask and I can show you photos!"
        
        return None
    
    def generate_cross_recommendation(
        self,
        query: str,
        intent: IntentType
    ) -> Optional[str]:
        """
        Generate cross-recommendations for related facilities/services.
        
        For example:
        - If user asks about kitchen/cooking → recommend chef services
        - If user asks about chef services → recommend kitchen facilities
        - If user asks about Wi-Fi → recommend other tech amenities
        - If user asks about parking → recommend location/accessibility
        
        Args:
            query: User's query
            intent: Detected intent
            
        Returns:
            Cross-recommendation string or None
        """
        query_lower = query.lower()
        
        # Kitchen/Cooking related → Recommend chef services
        kitchen_keywords = ["kitchen", "cook", "cooking", "prepare food", "make food", "cook meals"]
        if any(keyword in query_lower for keyword in kitchen_keywords):
            return (
                "💡 **Related Service:** Did you know we also offer chef services? "
                "You can avail professional chef services at an additional cost for freshly prepared meals. "
                "This is perfect if you'd like to enjoy delicious meals without cooking yourself!"
            )
        
        # Chef services related → Recommend kitchen facilities
        chef_keywords = ["chef", "chief", "chef service", "cooking service", "meal service"]
        if any(keyword in query_lower for keyword in chef_keywords):
            return (
                "💡 **Related Facility:** All cottages come with fully equipped kitchens, "
                "so you can also cook your own meals if you prefer. Each kitchen includes modern appliances "
                "and everything you need for preparing meals."
            )
        
        # Wi-Fi/Internet related → Recommend other tech amenities
        wifi_keywords = ["wifi", "wi-fi", "internet", "network", "connection", "online"]
        if any(keyword in query_lower for keyword in wifi_keywords):
            return (
                "💡 **Related Amenities:** In addition to Wi-Fi, all cottages also include Smart TV with Netflix, "
                "so you can enjoy streaming entertainment during your stay."
            )
        
        # Parking related → Recommend location/accessibility
        parking_keywords = ["parking", "park", "car", "vehicle", "drive"]
        if any(keyword in query_lower for keyword in parking_keywords):
            return (
                "💡 **Location Info:** Swiss Cottages is located in a secure gated community in Bhurban, "
                "adjacent to Pearl Continental (PC) Bhurban, with easy access to nearby attractions."
            )
        
        # Food/Dining related → Recommend chef services and BBQ
        food_keywords = ["food", "dining", "meal", "eat", "restaurant", "dinner", "lunch", "breakfast"]
        if any(keyword in query_lower for keyword in food_keywords) and "chef" not in query_lower:
            return (
                "💡 **Food Options:** You can cook your own meals in the fully equipped kitchen, "
                "order food delivery from nearby restaurants, enjoy BBQ facilities, or avail chef services "
                "for freshly prepared meals at an additional cost."
            )
        
        # BBQ related → Recommend chef services
        bbq_keywords = ["bbq", "barbecue", "grill", "outdoor cooking"]
        if any(keyword in query_lower for keyword in bbq_keywords):
            return (
                "💡 **Related Service:** If you'd prefer not to cook, we also offer chef services "
                "for freshly prepared meals at an additional cost."
            )
        
        # Facilities/Amenities general → Recommend specific popular amenities
        if intent == IntentType.FACILITIES and ("facility" in query_lower or "amenity" in query_lower or "what" in query_lower):
            return (
                "💡 **Popular Amenities:** All cottages include fully equipped kitchens, Wi-Fi, Smart TV with Netflix, "
                "BBQ facilities, outdoor sitting areas, and secure parking. Chef services are also available at an additional cost."
            )
        
        return None
    
    def generate_proactive_suggestion(
        self,
        context_tracker: ContextTracker,
        slots: Dict[str, Any]
    ) -> Optional[str]:
        """
        Generate proactive suggestions based on context.
        
        Args:
            context_tracker: Context tracker
            slots: Current slot values
            
        Returns:
            Proactive suggestion string or None
        """
        # Check if user has asked about pricing but not booking
        recent_intents = context_tracker.get_recent_intents(3)
        has_pricing = IntentType.PRICING in recent_intents
        has_booking = IntentType.BOOKING in recent_intents
        
        if has_pricing and not has_booking:
            # User asked about pricing but not booking - suggest booking
            if slots.get("guests") and slots.get("dates"):
                return "💡 **Next step:** Would you like to know more about the booking process or check availability?"
        
        # Check if user has asked about availability
        if IntentType.AVAILABILITY in recent_intents and not has_booking:
            if slots.get("dates"):
                return "💡 **Next step:** Would you like to know about pricing for these dates or proceed with booking?"
        
        return None


def get_recommendation_engine() -> RecommendationEngine:
    """
    Get or create a recommendation engine.
    
    Returns:
        RecommendationEngine instance
    """
    return RecommendationEngine()
