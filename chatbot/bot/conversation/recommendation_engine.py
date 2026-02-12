"""Recommendation engine for gentle suggestions and booking nudges."""

import re
from typing import Dict, Any, Optional, List, TYPE_CHECKING
from helpers.log import get_logger
from bot.conversation.intent_router import IntentType
from bot.conversation.slot_manager import SlotManager
from bot.conversation.context_tracker import ContextTracker, ConversationState
from bot.conversation.number_extractor import ExtractCottageNumber

if TYPE_CHECKING:
    from bot.client.lama_cpp_client import LamaCppClient
    from bot.client.groq_client import GroqClient

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
        Generate gentle recommendation for pricing, cottages, or safety intents.
        
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
                recommendations.append("💡 **Tip:** For groups of 6 or fewer, you can book at standard capacity. All cottages accommodate up to 6 guests comfortably.")
            elif guests <= 9:
                recommendations.append("💡 **Tip:** For groups of 7-9 guests, prior confirmation and adjusted pricing apply. All cottages can accommodate up to 9 guests.")
        
        # General pricing tip
        if not recommendations:
            recommendations.append("💡 **Tip:** Weekday rates are typically lower than weekend rates. Advance payment is required to confirm your booking.")
        
        return "\n".join(recommendations)
    
    def _generate_rooms_recommendation(self, slots: Dict[str, Any]) -> str:
        """Generate cottage recommendation (ROOMS intent - users ask about cottages, not rooms)."""
        recommendations = []
        seen_recommendations = set()  # Track to avoid duplicates
        
        guests = slots.get("guests")
        cottage_id = slots.get("cottage_id")
        family = slots.get("family")
        
        # Priority: specific recommendations first, then general
        if cottage_id:
            if cottage_id == "cottage_9" or cottage_id == "cottage_11":
                rec = "💡 **Tip:** Cottage 9 and Cottage 11 are 3-bedroom cottages, perfect for families or larger groups."
                if rec not in seen_recommendations:
                    recommendations.append(rec)
                    seen_recommendations.add(rec)
            elif cottage_id == "cottage_7":
                rec = "💡 **Tip:** Cottage 7 is a 2-bedroom cottage, ideal for smaller groups or couples."
                if rec not in seen_recommendations:
                    recommendations.append(rec)
                    seen_recommendations.add(rec)
        
        if guests:
            if guests <= 6:
                if not cottage_id or cottage_id == "any":
                    rec = "💡 **Tip:** For groups of 6 or fewer, any cottage (Cottage 7, 9, or 11) is suitable at standard capacity."
                    if rec not in seen_recommendations:
                        recommendations.append(rec)
                        seen_recommendations.add(rec)
                if family and (not cottage_id or cottage_id in ["cottage_9", "cottage_11", "any"]):
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
        # Check if enough info for booking
        has_guests = slots.get("guests") is not None
        has_dates = slots.get("dates") is not None
        has_cottage_id = slots.get("cottage_id") is not None
        
        # Need at least 2 out of 3 key slots
        filled_count = sum([has_guests, has_dates, has_cottage_id])
        
        # Relaxed intent requirement: If user has provided guests + cottage, they're likely ready
        # Don't require explicit booking/availability intent if they have key information
        should_show_nudge = False
        
        if context_tracker:
            recent_intents = context_tracker.get_recent_intents(5)
            has_booking_intent = IntentType.BOOKING in recent_intents
            has_availability_intent = IntentType.AVAILABILITY in recent_intents
            has_pricing_intent = IntentType.PRICING in recent_intents
            
            # Show nudge if:
            # 1. User has explicit booking/availability intent, OR
            # 2. User has guests + cottage (cottage_id) - they're exploring options, OR
            # 3. User has asked about pricing (shows purchase intent)
            if intent:
                should_show_nudge = (
                    intent in [IntentType.BOOKING, IntentType.AVAILABILITY, IntentType.PRICING] or 
                    has_booking_intent or 
                    has_availability_intent or
                    has_pricing_intent or
                    (filled_count >= 2 and has_guests and has_cottage_id)  # Guests + cottage = ready
                )
            else:
                should_show_nudge = (
                    has_booking_intent or 
                    has_availability_intent or
                    has_pricing_intent or
                    (filled_count >= 2 and has_guests and has_cottage_id)  # Guests + cottage = ready
                )
        else:
            # No context tracker - show if enough slots filled
            should_show_nudge = filled_count >= 2
        
        if not should_show_nudge:
            return None  # Don't show booking nudge
        
        if filled_count >= 2:
            nudge = "💡 **Ready to book?** "
            
            if has_guests and has_dates and has_cottage_id:
                nudge += "You have all the key information! Would you like to proceed with booking? "
            elif has_guests and has_dates:
                nudge += "You've shared your group size and dates. Would you like to explore booking options? "
            elif has_guests and has_cottage_id:
                nudge += "You've shared your group size and preferred cottage. Would you like to check availability? "
            elif has_dates and has_cottage_id:
                nudge += "You've shared your dates and preferred cottage. Would you like to proceed with booking? "
            
            nudge += "I can help you with the booking process or answer any other questions you have.\n\n"
            nudge += "**To proceed with booking, you can:**\n"
            nudge += "- Contact us: https://swisscottagesbhurban.com/contact-us/\n"
            nudge += "- Cottage Manager (Abdullah): +92 300 1218563\n"
            
            # Add Airbnb links based on cottage_id if available
            cottage_id = slots.get("cottage_id")
            if cottage_id == "cottage_7":
                nudge += "- View on Airbnb - Cottage 7: https://www.airbnb.com/rooms/886682083069412842\n"
            elif cottage_id == "cottage_9":
                nudge += "- View on Airbnb - Cottage 9: https://www.airbnb.com/rooms/651168099240245080\n"
            elif cottage_id == "cottage_11":
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
            cottage_id = slots.get("cottage_id")
            if cottage_id and cottage_id != "any":
                # Suggest other cottages
                if cottage_id == "cottage_7":
                    return "💡 **Alternative:** Cottage 9 and Cottage 11 are also available and offer 3-bedroom options with more space."
                elif cottage_id in ["cottage_9", "cottage_11"]:
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
        cottage_id = slots.get("cottage_id")
        has_cottage_in_query = any(
            cottage in query_lower 
            for cottage in ["cottage 7", "cottage 9", "cottage 11", "cottage7", "cottage9", "cottage11"]
        )
        
        # Only suggest images if:
        # 1. A specific cottage is mentioned (cottage_id slot or in query)
        # 2. Intent is ROOMS, PRICING, or general inquiry about cottages
        # 3. User hasn't already asked for images
        
        if cottage_id or has_cottage_in_query:
            # Determine which cottage(s) to mention
            cottage_mention = ""
            if cottage_id:
                if cottage_id == "cottage_7":
                    cottage_mention = "Cottage 7"
                elif cottage_id == "cottage_9":
                    cottage_mention = "Cottage 9"
                elif cottage_id == "cottage_11":
                    cottage_mention = "Cottage 11"
                elif cottage_id == "any":
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
    
    def _analyze_user_interest(self, query: str, chat_history: List[str]) -> Optional[str]:
        """
        Analyze user query and chat history to determine interest (family, couple, groups, etc.).
        
        Args:
            query: Current user query
            chat_history: Chat history
            
        Returns:
            Interest keyword or None
        """
        text = (query + " " + " ".join(chat_history)).lower()
        
        # Family/larger group indicators
        family_keywords = ["family", "families", "children", "kids", "larger group", "big group", "many people", "socializing", "relaxation", "spacious", "more space"]
        if any(keyword in text for keyword in family_keywords):
            return "family"
        
        # Couple/smaller group indicators
        couple_keywords = ["couple", "couples", "two people", "smaller group", "intimate", "romantic"]
        if any(keyword in text for keyword in couple_keywords):
            return "couple"
        
        return None
    
    def generate_contextual_suggestions(
        self,
        query: str,
        intent: IntentType,
        slots: Dict[str, Any],
        context_tracker: ContextTracker,
        chat_history: Optional[List[str]] = None
    ) -> List[str]:
        """
        Generate contextual suggestions using 3-tier system.
        
        Tier 1 (Engaging/Informational): Kitchen, facilities, nearby attractions, safety
        Tier 2 (Exploration): Pictures, group size, cottage features
        Tier 3 (Transactional): Pricing, booking, contact
        
        Args:
            query: User's query
            intent: Detected intent
            slots: Current slot values
            context_tracker: Context tracker with user journey info
            chat_history: Optional chat history for topic analysis
            
        Returns:
            List of suggestions in priority order (Tier 1 first, Tier 3 last)
        """
        suggestions = []
        query_lower = query.lower()
        
        # Extract cottage number from query
        cottage_extractor = ExtractCottageNumber()
        cottage_number = cottage_extractor.extract_cottage_number(query)
        cottage_id = slots.get("cottage_id")
        
        # Determine if specific cottage or general query
        is_specific_cottage = cottage_number is not None or (cottage_id and cottage_id != "any")
        if cottage_id and cottage_id.startswith("cottage_") and cottage_number is None:
            cottage_number = cottage_id.replace("cottage_", "")
        
        # Analyze chat history to avoid repeating topics
        covered_topics = self._analyze_covered_topics(chat_history or [])
        
        # Get tier priorities based on user journey state
        tier_priorities = self._get_recommendation_priority(context_tracker)
        
        # Generate Tier 1 (Engaging/Informational) suggestions
        tier1_suggestions = []
        
        if intent == IntentType.LOCATION:
            if "attraction" not in covered_topics:
                tier1_suggestions.append("Tell me more about nearby attractions")
            if "safety" not in covered_topics:
                tier1_suggestions.append("What's the safety like?")
            if "facility" not in covered_topics:
                tier1_suggestions.append("What facilities are nearby?")
        elif intent == IntentType.SAFETY:
            if "attraction" not in covered_topics:
                tier1_suggestions.append("Tell me about nearby attractions")
            if "facility" not in covered_topics:
                tier1_suggestions.append("What facilities are available?")
            if "location" not in covered_topics:
                tier1_suggestions.append("Where is it located?")
        elif intent == IntentType.FACILITIES:
            if "attraction" not in covered_topics:
                tier1_suggestions.append("Tell me about nearby attractions")
            if "safety" not in covered_topics:
                tier1_suggestions.append("Is it safe?")
            if "kitchen" not in covered_topics:
                tier1_suggestions.append("Tell me about the kitchen")
        elif intent == IntentType.ROOMS:
            if is_specific_cottage and cottage_number:
                # Specific cottage - focus on facilities and features
                if "facility" not in covered_topics:
                    tier1_suggestions.append(f"Tell me about Cottage {cottage_number} facilities")
                if "kitchen" not in covered_topics:
                    tier1_suggestions.append(f"What's the kitchen like in Cottage {cottage_number}?")
            else:
                # General cottage query
                if "facility" not in covered_topics:
                    tier1_suggestions.append("Tell me about facilities")
                if "kitchen" not in covered_topics:
                    tier1_suggestions.append("What's the kitchen like?")
        else:
            # General/FAQ_QUESTION intent
            if "attraction" not in covered_topics:
                tier1_suggestions.append("Tell me about nearby attractions")
            if "safety" not in covered_topics:
                tier1_suggestions.append("Is it safe to stay here?")
            if "facility" not in covered_topics:
                tier1_suggestions.append("What facilities are available?")
            if "kitchen" not in covered_topics:
                tier1_suggestions.append("Tell me about the kitchen")
        
        # Generate Tier 2 (Exploration) suggestions
        tier2_suggestions = []
        
        if is_specific_cottage and cottage_number:
            if "picture" not in covered_topics and "image" not in covered_topics:
                tier2_suggestions.append(f"Show me pictures of Cottage {cottage_number}")
            if "group" not in covered_topics and "capacity" not in covered_topics:
                tier2_suggestions.append(f"What's the group size for Cottage {cottage_number}?")
            if "feature" not in covered_topics:
                tier2_suggestions.append(f"Tell me more about Cottage {cottage_number} features")
        else:
            # Analyze user interest to suggest specific cottages
            user_interest = self._analyze_user_interest(query, chat_history or [])
            
            if user_interest == "family":
                # User interested in families/groups - suggest Cottage 9 or 11
                if "picture" not in covered_topics and "image" not in covered_topics:
                    tier2_suggestions.append("Show me pictures of Cottage 9")
                if "group" not in covered_topics and "capacity" not in covered_topics:
                    tier2_suggestions.append("What's the group size for Cottage 11?")
                if "feature" not in covered_topics:
                    tier2_suggestions.append("Tell me about Cottage 9's features")
            elif user_interest == "couple":
                # User interested in couples - suggest Cottage 7
                if "picture" not in covered_topics and "image" not in covered_topics:
                    tier2_suggestions.append("Show me pictures of Cottage 7")
                if "group" not in covered_topics and "capacity" not in covered_topics:
                    tier2_suggestions.append("What's the group size for Cottage 7?")
                if "feature" not in covered_topics:
                    tier2_suggestions.append("Tell me about Cottage 7's features")
            else:
                # General - suggest popular cottages (9 and 11)
                if "picture" not in covered_topics and "image" not in covered_topics:
                    tier2_suggestions.append("Show me pictures of Cottage 9")
                if "group" not in covered_topics and "capacity" not in covered_topics:
                    tier2_suggestions.append("What's the group size capacity?")
                if "feature" not in covered_topics:
                    tier2_suggestions.append("Tell me about Cottage 11's features")
        
        # Generate Tier 3 (Transactional) suggestions - only if user is ready
        tier3_suggestions = []
        user_state = context_tracker.state
        
        # Only show transactional suggestions if user is inquiring or ready to book
        if user_state in [ConversationState.INQUIRING, ConversationState.READY_TO_BOOK, ConversationState.COMPARING]:
            if is_specific_cottage and cottage_number:
                if "pricing" not in covered_topics and "price" not in covered_topics:
                    tier3_suggestions.append(f"What's the pricing for Cottage {cottage_number}?")
                if "booking" not in covered_topics and "book" not in covered_topics:
                    tier3_suggestions.append(f"I want to book Cottage {cottage_number}")
            else:
                if "pricing" not in covered_topics and "price" not in covered_topics:
                    tier3_suggestions.append("What's the pricing per night?")
                if "availability" not in covered_topics:
                    tier3_suggestions.append("I want to check availability")
        
        # Combine suggestions based on tier priorities
        # Lower priority number = higher priority (shown first)
        all_suggestions = []
        
        if tier_priorities["tier1"] <= tier_priorities["tier2"] and tier_priorities["tier1"] <= tier_priorities["tier3"]:
            all_suggestions.extend(tier1_suggestions)
            if tier_priorities["tier2"] <= tier_priorities["tier3"]:
                all_suggestions.extend(tier2_suggestions)
                all_suggestions.extend(tier3_suggestions)
            else:
                all_suggestions.extend(tier3_suggestions)
                all_suggestions.extend(tier2_suggestions)
        elif tier_priorities["tier2"] <= tier_priorities["tier1"] and tier_priorities["tier2"] <= tier_priorities["tier3"]:
            all_suggestions.extend(tier2_suggestions)
            if tier_priorities["tier1"] <= tier_priorities["tier3"]:
                all_suggestions.extend(tier1_suggestions)
                all_suggestions.extend(tier3_suggestions)
            else:
                all_suggestions.extend(tier3_suggestions)
                all_suggestions.extend(tier1_suggestions)
        else:
            all_suggestions.extend(tier3_suggestions)
            if tier_priorities["tier1"] <= tier_priorities["tier2"]:
                all_suggestions.extend(tier1_suggestions)
                all_suggestions.extend(tier2_suggestions)
            else:
                all_suggestions.extend(tier2_suggestions)
                all_suggestions.extend(tier1_suggestions)
        
        # Limit to 4-5 suggestions max
        return all_suggestions[:5]
    
    def _analyze_covered_topics(self, chat_history: List[str]) -> set:
        """
        Analyze chat history to determine what topics have been covered.
        
        Args:
            chat_history: List of chat messages
            
        Returns:
            Set of covered topic keywords
        """
        covered = set()
        history_text = " ".join(chat_history).lower()
        
        # Topic keywords mapping
        topic_keywords = {
            "attraction": ["attraction", "nearby", "near", "location", "place", "visit"],
            "safety": ["safe", "safety", "secure", "security", "guard"],
            "facility": ["facility", "amenity", "amenities", "feature", "features"],
            "kitchen": ["kitchen", "cook", "cooking", "chef"],
            "picture": ["picture", "pictures", "image", "images", "photo", "photos"],
            "image": ["picture", "pictures", "image", "images", "photo", "photos"],
            "group": ["group", "guests", "people", "capacity", "accommodate"],
            "capacity": ["group", "guests", "people", "capacity", "accommodate"],
            "pricing": ["price", "pricing", "cost", "pkr", "rate", "rates"],
            "price": ["price", "pricing", "cost", "pkr", "rate", "rates"],
            "booking": ["book", "booking", "reserve", "reservation"],
            "book": ["book", "booking", "reserve", "reservation"],
            "availability": ["available", "availability", "vacancy"],
            "feature": ["feature", "features", "amenity", "amenities"]
        }
        
        for topic, keywords in topic_keywords.items():
            if any(keyword in history_text for keyword in keywords):
                covered.add(topic)
        
        return covered
    
    def _get_recommendation_priority(self, context_tracker: ContextTracker) -> Dict[str, int]:
        """
        Determine recommendation tier priority based on user journey state.
        
        Returns dict with tier priorities (lower number = higher priority).
        """
        state = context_tracker.state
        
        if state == ConversationState.BROWSING:
            return {"tier1": 1, "tier2": 2, "tier3": 3}  # Focus on engaging
        elif state == ConversationState.COMPARING:
            return {"tier1": 1, "tier2": 1, "tier3": 2}  # Mix engaging and exploration
        elif state == ConversationState.INQUIRING:
            return {"tier1": 2, "tier2": 1, "tier3": 1}  # Mix exploration and transactional
        elif state == ConversationState.READY_TO_BOOK:
            return {"tier1": 3, "tier2": 2, "tier3": 1}  # Focus on transactional
        else:
            return {"tier1": 1, "tier2": 2, "tier3": 3}  # Default
    
    def generate_llm_recommendations(
        self,
        query: str,
        intent: IntentType,
        chat_history: List[str],
        context_tracker: ContextTracker,
        llm_client
    ) -> List[str]:
        """
        Use LLM to generate 1-2 contextual recommendations based on chat history.
        
        Args:
            query: Current user query
            intent: Detected intent
            chat_history: List of previous messages in session
            context_tracker: Context tracker with user journey info
            llm_client: LLM client for generation
            
        Returns:
            List of 1-2 LLM-generated recommendations
        """
        try:
            # Prepare chat history summary
            history_summary = ""
            if chat_history:
                # Take last 5 messages for context
                recent_history = chat_history[-5:] if len(chat_history) > 5 else chat_history
                history_summary = "\n".join([f"- {msg}" for msg in recent_history])
            else:
                history_summary = "No previous conversation"
            
            # Get user journey state
            state = context_tracker.state.value if context_tracker else "browsing"
            
            # Build prompt with available facilities/amenities
            available_facilities = """Available Facilities & Amenities at Swiss Cottages Bhurban:
- Fully equipped kitchens (microwave, oven, kettle, refrigerator, cookware, utensils)
- Wi-Fi internet
- Smart TV with Netflix
- BBQ facilities
- Outdoor sitting areas (terrace/balcony)
- Secure parking
- Chef services (available at additional cost)
- Heating system
- Living lounge areas
- Bedrooms and bathrooms

DO NOT suggest facilities that are NOT listed above, such as:
- Spa facilities (NOT available)
- Gym/fitness center (NOT available)
- Swimming pool (NOT available)
- Room service (NOT available)
- Restaurant on-site (NOT available - but nearby restaurants exist)
- Laundry service (NOT available - check FAQ for details)

Only suggest facilities/amenities from the list above."""
            
            # Analyze user interest to suggest specific cottages
            user_interest = self._analyze_user_interest(query, chat_history)
            cottage_suggestion = ""
            if user_interest == "family":
                cottage_suggestion = "\n- User shows interest in families/larger groups - suggest Cottage 9 or Cottage 11 (3-bedroom cottages ideal for families)"
            elif user_interest == "couple":
                cottage_suggestion = "\n- User shows interest in couples/smaller groups - suggest Cottage 7 (2-bedroom cottage ideal for couples)"
            
            # Build prompt
            prompt = f"""Based on the conversation history below, generate 1-2 engaging, contextual recommendations for the user.

Conversation History:
{history_summary}

Current Query: {query}
Intent: {intent.value if hasattr(intent, 'value') else str(intent)}
User Journey State: {state}
{cottage_suggestion}

{available_facilities}

Rules:
- Generate recommendations that are relevant to what the user has been asking about
- Start with engaging/informational topics (facilities, attractions, safety, kitchen) - NOT pricing or booking
- Only suggest pricing/booking if user has shown clear interest (asked about pricing, availability, or is ready to book)
- Use "cottage" terminology, never "room"
- Make recommendations natural and conversational
- Avoid topics already covered in conversation
- Generate exactly 1-2 recommendations, one per line
- Each recommendation should be a SHORT, DIRECT question (e.g., "Tell me about nearby attractions" or "Show me pictures of Cottage 9")
- DO NOT use phrases like "Would you like to know more about..." - make it a direct question instead
- For facilities, use: "What facilities are available?" or "Tell me about the kitchen" (NOT "spa facilities" or "dining options" unless specifically mentioned in available facilities)
- **CRITICAL: Output ONLY the recommendation questions themselves, one per line. DO NOT include any meta-text like "Here are recommendations:" or "Based on your interest:" or "I'd like to suggest:"**
- **DO NOT write introductory phrases. Start directly with the question.**
- **Example of CORRECT output:**
  Tell me about nearby attractions
  Show me pictures of Cottage 9
- **Example of WRONG output (DO NOT DO THIS):**
  Here are 2 contextual recommendations for the user:
  Tell me about nearby attractions
  Based on your interest in relaxation, I'd like to suggest:
  Show me pictures of Cottage 9
- **If user shows interest in specific features (relaxation, socializing, families, groups), suggest specific cottages (Cottage 9 or Cottage 11) that match their interest**
- **Cottage 9 and 11 are 3-bedroom cottages ideal for families and larger groups**
- **Cottage 7 is 2-bedroom, ideal for couples or smaller groups**

Generate 1-2 recommendations (ONLY the questions, no meta-text, no introductions):"""
            
            # Generate with LLM
            response = llm_client.generate_answer(prompt, max_new_tokens=64)
            
            # Parse response - split by newlines and clean
            recommendations = []
            
            # Meta-text patterns to remove (these should not be shown to users)
            meta_text_patterns = [
                r"^here are \d+ (?:contextual )?recommendations?",
                r"^based on your interest",
                r"^i'?d like to suggest",
                r"^suggest exploring",
                r"^recommendations?:",
                r"^here are some",
                r"^you might be interested in",
                r"^consider",
            ]
            
            # Facilities/amenities that are NOT available (should be filtered out)
            unavailable_facilities = [
                "spa", "spa facilities", "spa services",
                "gym", "fitness", "fitness center", "gymnasium",
                "swimming pool", "pool",
                "room service",
                "restaurant on-site", "on-site restaurant",
                "laundry service", "laundry facilities"
            ]
            
            for line in response.strip().split('\n'):
                line = line.strip()
                
                # Skip empty lines
                if not line:
                    continue
                
                # Remove meta-text lines
                is_meta_text = any(re.search(pattern, line, re.IGNORECASE) for pattern in meta_text_patterns)
                if is_meta_text:
                    logger.debug(f"Filtered out meta-text: {line}")
                    continue
                
                # Remove numbering if present (1., 2., etc.)
                line = line.lstrip('1234567890.-) ')
                
                # Remove common prefixes that are meta-text
                line = re.sub(r'^(?:here are|based on|i\'?d like|suggest|recommendations?:)\s*', '', line, flags=re.IGNORECASE)
                line = line.strip()
                
                if line and len(line) > 10:  # Valid recommendation
                    # Check if recommendation mentions unavailable facilities
                    line_lower = line.lower()
                    has_unavailable = any(facility in line_lower for facility in unavailable_facilities)
                    
                    if not has_unavailable:
                        recommendations.append(line)
                    else:
                        logger.warning(f"Filtered out recommendation mentioning unavailable facility: {line}")
            
            # Limit to 2 recommendations
            return recommendations[:2]
            
        except Exception as e:
            logger.warning(f"Failed to generate LLM recommendations: {e}")
            return []  # Fallback to empty list


def get_recommendation_engine() -> RecommendationEngine:
    """
    Get or create a recommendation engine.
    
    Returns:
        RecommendationEngine instance
    """
    return RecommendationEngine()
