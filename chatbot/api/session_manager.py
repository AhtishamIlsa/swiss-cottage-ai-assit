"""Session manager for handling chat history per session."""

import sys
import threading
from pathlib import Path
from typing import Dict, Optional, TYPE_CHECKING, Union, Any

# Add chatbot directory to path
chatbot_dir = Path(__file__).parent.parent
if str(chatbot_dir) not in sys.path:
    sys.path.insert(0, str(chatbot_dir))

from bot.conversation.chat_history import ChatHistory
from bot.conversation.slot_manager import SlotManager
from bot.conversation.context_tracker import ContextTracker

if TYPE_CHECKING:
    from bot.client.lama_cpp_client import LamaCppClient
    from bot.client.groq_client import GroqClient


class SessionManager:
    """Manages chat sessions and their associated chat history, slots, and context."""
    
    def __init__(self):
        """Initialize the session manager."""
        self._sessions: Dict[str, ChatHistory] = {}
        self._slot_managers: Dict[str, SlotManager] = {}
        self._context_trackers: Dict[str, ContextTracker] = {}
        self._lock = threading.Lock()
    
    def get_or_create_session(self, session_id: str, total_length: int = 2) -> ChatHistory:
        """
        Get existing session or create a new one.
        
        Args:
            session_id: Unique session identifier
            total_length: Maximum number of messages to keep in history
            
        Returns:
            ChatHistory: The chat history for this session
        """
        with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = ChatHistory(total_length=total_length)
            return self._sessions[session_id]
    
    def get_or_create_slot_manager(
        self, 
        session_id: str, 
        llm: Optional[Union["LamaCppClient", "GroqClient", Any]] = None
    ) -> SlotManager:
        """
        Get existing slot manager or create a new one for a session.
        
        Args:
            session_id: Unique session identifier
            llm: Optional LLM client for slot extraction
            
        Returns:
            SlotManager: The slot manager for this session
        """
        with self._lock:
            if session_id not in self._slot_managers:
                self._slot_managers[session_id] = SlotManager(session_id, llm)
            return self._slot_managers[session_id]
    
    def get_or_create_context_tracker(self, session_id: str) -> ContextTracker:
        """
        Get existing context tracker or create a new one for a session.
        
        Args:
            session_id: Unique session identifier
            
        Returns:
            ContextTracker: The context tracker for this session
        """
        with self._lock:
            if session_id not in self._context_trackers:
                self._context_trackers[session_id] = ContextTracker(session_id)
            return self._context_trackers[session_id]
    
    def clear_session(self, session_id: str) -> bool:
        """
        Clear chat history, slots, and context for a session.
        
        Args:
            session_id: Session ID to clear
            
        Returns:
            bool: True if session was cleared, False if session didn't exist
        """
        with self._lock:
            cleared = False
            if session_id in self._sessions:
                self._sessions[session_id].clear()
                cleared = True
            if session_id in self._slot_managers:
                self._slot_managers[session_id].clear_slots()
                cleared = True
            if session_id in self._context_trackers:
                self._context_trackers[session_id].clear()
                cleared = True
            return cleared
    
    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session entirely (history, slots, and context).
        
        Args:
            session_id: Session ID to delete
            
        Returns:
            bool: True if session was deleted, False if session didn't exist
        """
        with self._lock:
            deleted = False
            if session_id in self._sessions:
                del self._sessions[session_id]
                deleted = True
            if session_id in self._slot_managers:
                del self._slot_managers[session_id]
                deleted = True
            if session_id in self._context_trackers:
                del self._context_trackers[session_id]
                deleted = True
            return deleted


# Global session manager instance
session_manager = SessionManager()
