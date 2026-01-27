"""Session manager for handling chat history per session."""

import sys
import threading
from pathlib import Path
from typing import Dict

# Add chatbot directory to path
chatbot_dir = Path(__file__).parent.parent
if str(chatbot_dir) not in sys.path:
    sys.path.insert(0, str(chatbot_dir))

from bot.conversation.chat_history import ChatHistory


class SessionManager:
    """Manages chat sessions and their associated chat history."""
    
    def __init__(self):
        """Initialize the session manager."""
        self._sessions: Dict[str, ChatHistory] = {}
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
    
    def clear_session(self, session_id: str) -> bool:
        """
        Clear chat history for a session.
        
        Args:
            session_id: Session ID to clear
            
        Returns:
            bool: True if session was cleared, False if session didn't exist
        """
        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id].clear()
                return True
            return False
    
    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session entirely.
        
        Args:
            session_id: Session ID to delete
            
        Returns:
            bool: True if session was deleted, False if session didn't exist
        """
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                return True
            return False


# Global session manager instance
session_manager = SessionManager()
