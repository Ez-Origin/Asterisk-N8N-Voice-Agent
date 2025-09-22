"""
SessionStore - Centralized, atomic state management for call sessions.

This replaces the dict soup (active_calls, caller_channels, active_playbacks)
with a single, thread-safe store that enforces invariants.
"""

import asyncio
import time
from typing import Optional, Dict, Set, List
import structlog

from src.core.models import CallSession, PlaybackRef, ProviderSession

logger = structlog.get_logger(__name__)


class SessionStore:
    """
    Thread-safe store for call sessions and playback references.
    
    Enforces key invariants:
    - Canonical call_id == caller_channel_id
    - A call has two channel entries (caller/local), both share call_id
    - Gating is token/refcount-based per call
    - All operations are atomic
    """
    
    def __init__(self):
        # Core session storage
        self._sessions_by_call_id: Dict[str, CallSession] = {}
        self._sessions_by_channel_id: Dict[str, CallSession] = {}
        self._playbacks: Dict[str, PlaybackRef] = {}
        self._provider_sessions: Dict[str, ProviderSession] = {}
        
        # Thread safety
        self._lock = asyncio.Lock()
        
        logger.info("SessionStore initialized")
    
    async def upsert_call(self, session: CallSession) -> None:
        """Add or update a call session atomically."""
        async with self._lock:
            # Store by call_id (canonical)
            self._sessions_by_call_id[session.call_id] = session
            
            # Store by caller_channel_id
            self._sessions_by_channel_id[session.caller_channel_id] = session
            
            # Store by local_channel_id if present
            if session.local_channel_id:
                self._sessions_by_channel_id[session.local_channel_id] = session
            
            # Store by external_media_id if present
            if session.external_media_id:
                self._sessions_by_channel_id[session.external_media_id] = session
            
            logger.debug("Call session upserted",
                        call_id=session.call_id,
                        caller_channel_id=session.caller_channel_id,
                        local_channel_id=session.local_channel_id)
    
    async def get_by_call_id(self, call_id: str) -> Optional[CallSession]:
        """Get session by canonical call_id."""
        async with self._lock:
            return self._sessions_by_call_id.get(call_id)
    
    async def get_by_channel_id(self, channel_id: str) -> Optional[CallSession]:
        """Get session by any channel_id (caller, local, external_media)."""
        async with self._lock:
            return self._sessions_by_channel_id.get(channel_id)
    
    async def remove_call(self, call_id: str) -> Optional[CallSession]:
        """Remove a call session and all its channel mappings."""
        async with self._lock:
            session = self._sessions_by_call_id.pop(call_id, None)
            if not session:
                return None
            
            # Remove all channel mappings
            self._sessions_by_channel_id.pop(session.caller_channel_id, None)
            if session.local_channel_id:
                self._sessions_by_channel_id.pop(session.local_channel_id, None)
            if session.external_media_id:
                self._sessions_by_channel_id.pop(session.external_media_id, None)
            
            logger.debug("Call session removed",
                        call_id=call_id,
                        caller_channel_id=session.caller_channel_id)
            
            return session
    
    async def set_gating_token(self, call_id: str, playback_id: str) -> bool:
        """Add a TTS gating token for a call."""
        async with self._lock:
            session = self._sessions_by_call_id.get(call_id)
            if not session:
                logger.warning("Cannot set gating token - call not found", 
                             call_id=call_id, playback_id=playback_id)
                return False
            
            # Add token and increment refcount
            session.tts_tokens.add(playback_id)
            session.tts_active_count += 1
            session.tts_playing = True
            session.audio_capture_enabled = False
            
            # Update VAD state
            if session.vad_state:
                session.vad_state["tts_playing"] = True
                # Reset VAD buffers to prevent TTS bleed-through
                session.vad_state["webrtc_speech_frames"] = 0
                session.vad_state["webrtc_silence_frames"] = 0
                session.vad_state["webrtc_last_decision"] = False
                # ARCHITECT FIX: Reset both audio_buffer and frame_buffer
                if "audio_buffer" in session.vad_state:
                    session.vad_state["audio_buffer"] = b""
                if "frame_buffer" in session.vad_state:
                    session.vad_state["frame_buffer"] = b""
            
            logger.info("🔇 TTS GATING - Audio capture disabled (token added)",
                       call_id=call_id,
                       playback_id=playback_id,
                       active_count=session.tts_active_count)
            
            return True
    
    async def clear_gating_token(self, call_id: str, playback_id: str) -> bool:
        """Remove a TTS gating token for a call."""
        async with self._lock:
            session = self._sessions_by_call_id.get(call_id)
            if not session:
                logger.warning("Cannot clear gating token - call not found",
                             call_id=call_id, playback_id=playback_id)
                return False
            
            # Remove token and decrement refcount
            session.tts_tokens.discard(playback_id)
            session.tts_active_count = max(0, session.tts_active_count - 1)
            
            # Only re-enable if no more active TTS
            if session.tts_active_count == 0:
                session.tts_playing = False
                session.audio_capture_enabled = True
                
                # Update VAD state
                if session.vad_state:
                    session.vad_state["tts_playing"] = False
                    # ARCHITECT FIX: Reset both audio_buffer and frame_buffer
                    if "audio_buffer" in session.vad_state:
                        session.vad_state["audio_buffer"] = b""
                    if "frame_buffer" in session.vad_state:
                        session.vad_state["frame_buffer"] = b""
            
            logger.info("🔊 TTS GATING - Audio capture enabled (token removed)",
                       call_id=call_id,
                       playback_id=playback_id,
                       active_count=session.tts_active_count,
                       audio_capture_enabled=session.audio_capture_enabled)
            
            return True
    
    async def add_playback(self, playback_ref: PlaybackRef) -> None:
        """Add a playback reference."""
        async with self._lock:
            self._playbacks[playback_ref.playback_id] = playback_ref
            logger.debug("Playback reference added",
                        playback_id=playback_ref.playback_id,
                        call_id=playback_ref.call_id)
    
    async def pop_playback(self, playback_id: str) -> Optional[PlaybackRef]:
        """Remove and return a playback reference."""
        async with self._lock:
            playback_ref = self._playbacks.pop(playback_id, None)
            if playback_ref:
                logger.debug("Playback reference removed",
                           playback_id=playback_id,
                           call_id=playback_ref.call_id)
            return playback_ref
    
    async def get_playback(self, playback_id: str) -> Optional[PlaybackRef]:
        """Get a playback reference without removing it."""
        async with self._lock:
            return self._playbacks.get(playback_id)
    
    async def list_active_calls(self) -> List[str]:
        """Get list of active call IDs."""
        async with self._lock:
            return list(self._sessions_by_call_id.keys())
    
    async def get_all_sessions(self) -> List[CallSession]:
        """Get all active sessions."""
        async with self._lock:
            return list(self._sessions_by_call_id.values())
    
    async def get_session_stats(self) -> Dict[str, int]:
        """Get statistics about active sessions."""
        async with self._lock:
            return {
                "active_calls": len(self._sessions_by_call_id),
                "active_playbacks": len(self._playbacks),
                "provider_sessions": len(self._provider_sessions)
            }
    
    async def cleanup_expired_sessions(self, max_age_seconds: float = 3600) -> int:
        """Clean up sessions older than max_age_seconds."""
        # First pass: identify expired calls while holding lock
        async with self._lock:
            current_time = time.time()
            expired_calls = []
            
            for call_id, session in self._sessions_by_call_id.items():
                if current_time - session.created_at > max_age_seconds:
                    expired_calls.append(call_id)
        
        # Second pass: remove expired calls (each remove_call acquires its own lock)
        for call_id in expired_calls:
            await self.remove_call(call_id)
        
        if expired_calls:
            logger.info("Cleaned up expired sessions",
                       expired_count=len(expired_calls))
        
        return len(expired_calls)
