import threading
from typing import Dict, Optional
from .types import BookingState

class MemorySessionStore:
    """Thread-safe in-memory store for managing conversation states."""
    
    def __init__(self):
        self._store: Dict[str, BookingState] = {}
        self._lock = threading.Lock()
        
    def get(self, session_id: str) -> BookingState:
        """Retrieve booking state for a session. Returns a new empty state if session_id is not found."""
        with self._lock:
            if session_id not in self._store:
                self._store[session_id] = BookingState()
            return self._store[session_id]
            
    def set(self, session_id: str, state: BookingState) -> None:
        """Save booking state for a session."""
        with self._lock:
            self._store[session_id] = state
            
    def clear(self, session_id: str) -> None:
        """Clear booking state (e.g. after booking completes or resets)."""
        with self._lock:
            if session_id in self._store:
                # Keep messages history but reset booking details
                old_messages = self._store[session_id].messages
                self._store[session_id] = BookingState(messages=old_messages)

    def delete(self, session_id: str) -> None:
        """Completely delete the session including conversation history."""
        with self._lock:
            if session_id in self._store:
                del self._store[session_id]

# Initialize singleton store
session_store = MemorySessionStore()
