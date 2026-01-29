"""Context tracking for user journey and preferences."""

from enum import Enum
from typing import Dict, List, Optional, Any
from datetime import datetime
from helpers.log import get_logger
from bot.conversation.intent_router import IntentType

logger = get_logger(__name__)


class ConversationState(Enum):
    """User journey stages."""
    BROWSING = "browsing"  # Just exploring, no specific intent
    COMPARING = "comparing"  # Comparing options
    INQUIRING = "inquiring"  # Asking specific questions
    READY_TO_BOOK = "ready_to_book"  # Has enough info, ready to book
    BOOKING = "booking"  # In booking process
    COMPLETED = "completed"  # Booking completed or conversation ended


class ContextTracker:
    """Tracks user journey, preferences, and conversation state."""
    
    def __init__(self, session_id: str):
        """
        Initialize the context tracker.
        
        Args:
            session_id: Unique session identifier
        """
        self.session_id = session_id
        self.state = ConversationState.BROWSING
        self.preferences: Dict[str, Any] = {}
        self.intent_history: List[IntentType] = []
        self.conversation_summary: List[str] = []
        self.key_points: Dict[str, Any] = {}  # Important facts discussed
        self.timestamp = datetime.now()
    
    def update_state(self, new_state: ConversationState) -> None:
        """
        Update conversation state.
        
        Args:
            new_state: New conversation state
        """
        if self.state != new_state:
            logger.info(f"State transition: {self.state.value} -> {new_state.value}")
            self.state = new_state
    
    def add_intent(self, intent: IntentType) -> None:
        """
        Track intent in history.
        
        Args:
            intent: Detected intent
        """
        self.intent_history.append(intent)
        # Keep only last 10 intents
        if len(self.intent_history) > 10:
            self.intent_history.pop(0)
        
        # Update state based on intent transitions
        self._update_state_from_intent(intent)
    
    def _update_state_from_intent(self, intent: IntentType) -> None:
        """
        Update conversation state based on intent.
        
        Args:
            intent: Current intent
        """
        # Analyze intent history to determine state
        if intent == IntentType.BOOKING:
            self.update_state(ConversationState.BOOKING)
        elif intent in [IntentType.PRICING, IntentType.AVAILABILITY, IntentType.ROOMS]:
            # User is comparing or inquiring
            if len(self.intent_history) >= 2:
                # Multiple related intents = comparing
                recent_intents = self.intent_history[-3:]
                if len(set(recent_intents)) >= 2:
                    self.update_state(ConversationState.COMPARING)
                else:
                    self.update_state(ConversationState.INQUIRING)
            else:
                self.update_state(ConversationState.INQUIRING)
        elif len(self.intent_history) == 0:
            self.update_state(ConversationState.BROWSING)
    
    def update_preferences(self, preferences: Dict[str, Any]) -> None:
        """
        Update user preferences.
        
        Args:
            preferences: Dictionary of preferences
        """
        self.preferences.update(preferences)
        logger.debug(f"Updated preferences: {preferences}")
    
    def get_preference(self, key: str, default: Any = None) -> Any:
        """
        Get a specific preference.
        
        Args:
            key: Preference key
            default: Default value if not found
            
        Returns:
            Preference value or default
        """
        return self.preferences.get(key, default)
    
    def add_to_summary(self, point: str) -> None:
        """
        Add a point to conversation summary.
        
        Args:
            point: Summary point to add
        """
        self.conversation_summary.append(point)
        # Keep only last 20 points
        if len(self.conversation_summary) > 20:
            self.conversation_summary.pop(0)
    
    def add_key_point(self, key: str, value: Any) -> None:
        """
        Add a key point discussed in conversation.
        
        Args:
            key: Key point identifier
            value: Value of the key point
        """
        self.key_points[key] = value
        logger.debug(f"Added key point: {key} = {value}")
    
    def get_key_point(self, key: str, default: Any = None) -> Any:
        """
        Get a key point.
        
        Args:
            key: Key point identifier
            default: Default value if not found
            
        Returns:
            Key point value or default
        """
        return self.key_points.get(key, default)
    
    def get_summary(self, max_points: int = 5) -> str:
        """
        Get conversation summary.
        
        Args:
            max_points: Maximum number of summary points to return
            
        Returns:
            Summary string
        """
        recent_points = self.conversation_summary[-max_points:]
        return "\n".join(recent_points) if recent_points else ""
    
    def is_ready_to_book(self) -> bool:
        """
        Check if user is ready to book based on context.
        
        Returns:
            True if user appears ready to book
        """
        # Check if user has asked about booking, pricing, and availability
        has_booking_intent = IntentType.BOOKING in self.intent_history
        has_pricing_intent = IntentType.PRICING in self.intent_history
        has_availability_intent = IntentType.AVAILABILITY in self.intent_history
        
        # If user has asked about all three, likely ready to book
        if has_booking_intent and (has_pricing_intent or has_availability_intent):
            return True
        
        # Or if state is already ready_to_book
        if self.state == ConversationState.READY_TO_BOOK:
            return True
        
        return False
    
    def get_recent_intents(self, count: int = 3) -> List[IntentType]:
        """
        Get recent intents.
        
        Args:
            count: Number of recent intents to return
            
        Returns:
            List of recent intents
        """
        return self.intent_history[-count:] if len(self.intent_history) >= count else self.intent_history
    
    def get_last_intent(self) -> Optional[IntentType]:
        """
        Get the last intent from history.
        
        Returns:
            Last intent or None if no history
        """
        return self.intent_history[-1] if self.intent_history else None
    
    def clear(self) -> None:
        """Clear all context (e.g., after booking completion)."""
        self.state = ConversationState.BROWSING
        self.preferences.clear()
        self.intent_history.clear()
        self.conversation_summary.clear()
        self.key_points.clear()
        logger.info(f"Cleared context for session {self.session_id}")
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert context to dictionary for serialization.
        
        Returns:
            Dictionary representation
        """
        return {
            "session_id": self.session_id,
            "state": self.state.value,
            "preferences": self.preferences,
            "intent_history": [intent.value if hasattr(intent, 'value') else str(intent) for intent in self.intent_history],
            "conversation_summary": self.conversation_summary,
            "key_points": self.key_points,
            "timestamp": self.timestamp.isoformat(),
        }


def get_context_tracker(session_id: str) -> ContextTracker:
    """
    Get or create a context tracker for a session.
    
    Args:
        session_id: Session identifier
        
    Returns:
        ContextTracker instance
    """
    # This will be integrated with SessionManager later
    # For now, create a new instance (will be cached in SessionManager)
    return ContextTracker(session_id)
