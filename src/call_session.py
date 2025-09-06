"""
Call Session Management

This module provides call session management for tracking call state,
context, and metadata throughout the call lifecycle.
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime

logger = logging.getLogger(__name__)


class CallState(Enum):
    """Call state enumeration."""
    RINGING = "ringing"
    CONNECTED = "connected"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    LISTENING = "listening"
    ENDED = "ended"
    ERROR = "error"


class CallDirection(Enum):
    """Call direction enumeration."""
    INBOUND = "inbound"
    OUTBOUND = "outbound"


@dataclass
class CallContext:
    """Call context information."""
    language: str = "en-US"
    timezone: str = "UTC"
    caller_name: Optional[str] = None
    caller_location: Optional[str] = None
    custom_instructions: Optional[str] = None
    conversation_history: List[Dict[str, str]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CallSession:
    """Call session data structure."""
    
    # Core identifiers
    call_id: str
    session_id: str
    
    # Call information
    from_user: str
    to_user: str
    direction: CallDirection
    
    # State management
    state: CallState = CallState.RINGING
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    duration: float = 0.0
    
    # Context and configuration
    context: CallContext = field(default_factory=CallContext)
    
    # Audio processing
    codec: Optional[str] = None
    sample_rate: int = 16000
    channels: int = 1
    
    # AI provider information
    provider: str = "openai"
    voice_type: Optional[str] = None
    
    # Statistics
    stats: Dict[str, Any] = field(default_factory=lambda: {
        'audio_chunks_received': 0,
        'audio_chunks_sent': 0,
        'stt_requests': 0,
        'llm_requests': 0,
        'tts_requests': 0,
        'errors': 0,
        'total_processing_time': 0.0,
        'average_response_time': 0.0
    })
    
    # Callbacks
    on_state_change: Optional[Callable[[CallState], None]] = None
    on_error: Optional[Callable[[str, Exception], None]] = None
    on_cleanup: Optional[Callable[[], None]] = None
    
    def __post_init__(self):
        """Initialize session after creation."""
        if not self.session_id:
            self.session_id = str(uuid.uuid4())
    
    def update_state(self, new_state: CallState) -> bool:
        """Update call state with validation."""
        if self.state == CallState.ENDED:
            logger.warning(f"Cannot change state from ENDED to {new_state.value}")
            return False
        
        old_state = self.state
        self.state = new_state
        
        # Update duration
        if new_state == CallState.ENDED:
            self.end_time = time.time()
            self.duration = self.end_time - self.start_time
        
        # Call state change callback
        if self.on_state_change:
            try:
                self.on_state_change(new_state)
            except Exception as e:
                logger.error(f"Error in state change callback: {e}")
        
        logger.info(f"Call {self.call_id} state changed: {old_state.value} -> {new_state.value}")
        return True
    
    def add_to_conversation(self, role: str, content: str) -> None:
        """Add message to conversation history."""
        self.context.conversation_history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        
        # Trim conversation history if too long (keep last 50 messages)
        if len(self.context.conversation_history) > 50:
            self.context.conversation_history = self.context.conversation_history[-50:]
    
    def get_conversation_history(self) -> List[Dict[str, str]]:
        """Get conversation history."""
        return self.context.conversation_history.copy()
    
    def clear_conversation(self) -> None:
        """Clear conversation history."""
        self.context.conversation_history.clear()
    
    def update_stats(self, key: str, value: Any) -> None:
        """Update session statistics."""
        if key in self.stats:
            if isinstance(self.stats[key], (int, float)):
                self.stats[key] += value
            else:
                self.stats[key] = value
        else:
            self.stats[key] = value
    
    def get_stats(self) -> Dict[str, Any]:
        """Get session statistics."""
        stats = self.stats.copy()
        stats['duration'] = self.duration
        stats['state'] = self.state.value
        stats['conversation_length'] = len(self.context.conversation_history)
        return stats
    
    def is_active(self) -> bool:
        """Check if call is active."""
        return self.state not in [CallState.ENDED, CallState.ERROR]
    
    def is_processing(self) -> bool:
        """Check if call is processing audio."""
        return self.state in [CallState.PROCESSING, CallState.SPEAKING, CallState.LISTENING]
    
    def cleanup(self) -> None:
        """Cleanup call session."""
        if self.on_cleanup:
            try:
                self.on_cleanup()
            except Exception as e:
                logger.error(f"Error in cleanup callback: {e}")
        
        # Final duration calculation
        if not self.end_time:
            self.end_time = time.time()
            self.duration = self.end_time - self.start_time
        
        logger.info(f"Call session {self.call_id} cleaned up after {self.duration:.2f}s")


class CallSessionManager:
    """Manager for call sessions."""
    
    def __init__(self):
        """Initialize call session manager."""
        self.sessions: Dict[str, CallSession] = {}
        self.max_sessions: int = 100
        self.session_timeout: float = 3600.0  # 1 hour
        
        # Start cleanup task
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        logger.info("Call Session Manager initialized")
    
    async def create_session(
        self,
        call_id: str,
        from_user: str,
        to_user: str,
        direction: CallDirection = CallDirection.INBOUND,
        **kwargs
    ) -> CallSession:
        """Create a new call session."""
        if call_id in self.sessions:
            logger.warning(f"Session {call_id} already exists, replacing")
            await self.remove_session(call_id)
        
        # Check session limit
        if len(self.sessions) >= self.max_sessions:
            await self._cleanup_old_sessions()
        
        session = CallSession(
            call_id=call_id,
            session_id=str(uuid.uuid4()),
            from_user=from_user,
            to_user=to_user,
            direction=direction,
            **kwargs
        )
        
        self.sessions[call_id] = session
        logger.info(f"Created call session {call_id} for {from_user} -> {to_user}")
        
        return session
    
    async def get_session(self, call_id: str) -> Optional[CallSession]:
        """Get call session by ID."""
        return self.sessions.get(call_id)
    
    async def remove_session(self, call_id: str) -> bool:
        """Remove call session."""
        if call_id not in self.sessions:
            return False
        
        session = self.sessions[call_id]
        session.cleanup()
        del self.sessions[call_id]
        
        logger.info(f"Removed call session {call_id}")
        return True
    
    async def update_session_state(self, call_id: str, state: CallState) -> bool:
        """Update session state."""
        session = await self.get_session(call_id)
        if not session:
            return False
        
        return session.update_state(state)
    
    async def get_active_sessions(self) -> List[CallSession]:
        """Get all active sessions."""
        return [session for session in self.sessions.values() if session.is_active()]
    
    async def get_session_stats(self) -> Dict[str, Any]:
        """Get session manager statistics."""
        active_sessions = await self.get_active_sessions()
        
        return {
            'total_sessions': len(self.sessions),
            'active_sessions': len(active_sessions),
            'max_sessions': self.max_sessions,
            'sessions': {
                call_id: session.get_stats()
                for call_id, session in self.sessions.items()
            }
        }
    
    async def _cleanup_old_sessions(self) -> None:
        """Cleanup old sessions."""
        current_time = time.time()
        sessions_to_remove = []
        
        for call_id, session in self.sessions.items():
            # Remove ended sessions older than timeout
            if (session.state == CallState.ENDED and 
                current_time - session.end_time > self.session_timeout):
                sessions_to_remove.append(call_id)
            # Remove sessions that have been running too long
            elif current_time - session.start_time > self.session_timeout * 2:
                sessions_to_remove.append(call_id)
        
        for call_id in sessions_to_remove:
            await self.remove_session(call_id)
    
    async def _cleanup_loop(self) -> None:
        """Background cleanup loop."""
        while True:
            try:
                await asyncio.sleep(300)  # Run every 5 minutes
                await self._cleanup_old_sessions()
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
    
    async def shutdown(self) -> None:
        """Shutdown session manager."""
        logger.info("Shutting down Call Session Manager...")
        
        # Cancel cleanup task
        self._cleanup_task.cancel()
        
        # Cleanup all sessions
        for call_id in list(self.sessions.keys()):
            await self.remove_session(call_id)
        
        logger.info("Call Session Manager shutdown complete")


# Global session manager instance
_session_manager: Optional[CallSessionManager] = None


def get_session_manager() -> CallSessionManager:
    """Get global session manager instance."""
    global _session_manager
    if _session_manager is None:
        _session_manager = CallSessionManager()
    return _session_manager


async def shutdown_session_manager() -> None:
    """Shutdown global session manager."""
    global _session_manager
    if _session_manager:
        await _session_manager.shutdown()
        _session_manager = None
