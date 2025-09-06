"""
Call State Machine Implementation

This module provides a robust call state machine for managing call lifecycle,
state transitions, termination handling, and per-call instructions.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Set
from datetime import datetime, timedelta

from call_session import CallSession, CallState, CallDirection

logger = logging.getLogger(__name__)


class CallEvent(Enum):
    """Call events that trigger state transitions."""
    # Incoming events
    CALL_INITIATED = "call_initiated"
    CALL_ANSWERED = "call_answered"
    CALL_CONNECTED = "call_connected"
    CALL_STARTED = "call_started"
    
    # Audio events
    AUDIO_RECEIVED = "audio_received"
    SPEECH_DETECTED = "speech_detected"
    SPEECH_ENDED = "speech_ended"
    RESPONSE_STARTED = "response_started"
    RESPONSE_COMPLETED = "response_completed"
    
    # Termination events
    CALL_ENDED = "call_ended"
    CALL_TIMEOUT = "call_timeout"
    CALL_ERROR = "call_error"
    USER_HANGUP = "user_hangup"
    AGENT_HANGUP = "agent_hangup"
    NETWORK_ERROR = "network_error"
    
    # Control events
    PAUSE_CALL = "pause_call"
    RESUME_CALL = "resume_call"
    TRANSFER_CALL = "transfer_call"


class TerminationReason(Enum):
    """Call termination reasons."""
    NORMAL = "normal"
    TIMEOUT = "timeout"
    USER_HANGUP = "user_hangup"
    AGENT_HANGUP = "agent_hangup"
    NETWORK_ERROR = "network_error"
    SYSTEM_ERROR = "system_error"
    INVALID_STATE = "invalid_state"
    MAX_DURATION = "max_duration"


@dataclass
class CallInstructions:
    """Per-call instructions and configuration."""
    system_prompt: str = "You are a helpful AI voice assistant for Jugaar LLC."
    custom_instructions: Optional[str] = None
    language: str = "en-US"
    voice_type: str = "alloy"
    max_duration: int = 1800  # 30 minutes in seconds
    silence_timeout: int = 30  # 30 seconds
    response_timeout: int = 30  # 30 seconds
    enable_recording: bool = False
    enable_transcription: bool = True
    transfer_number: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StateTransition:
    """State transition definition."""
    from_state: CallState
    to_state: CallState
    event: CallEvent
    condition: Optional[Callable[['CallStateMachine'], bool]] = None
    action: Optional[Callable[['CallStateMachine'], None]] = None


class CallStateMachine:
    """
    Robust call state machine for managing call lifecycle.
    
    This class handles state transitions, call termination, timeout management,
    and per-call instructions throughout the call lifecycle.
    """
    
    # Valid state transitions
    VALID_TRANSITIONS: Dict[CallState, Set[CallState]] = {
        CallState.RINGING: {CallState.CONNECTED, CallState.ENDED, CallState.ERROR},
        CallState.CONNECTED: {CallState.PROCESSING, CallState.LISTENING, CallState.ENDED, CallState.ERROR},
        CallState.PROCESSING: {CallState.SPEAKING, CallState.LISTENING, CallState.ENDED, CallState.ERROR},
        CallState.SPEAKING: {CallState.LISTENING, CallState.ENDED, CallState.ERROR},
        CallState.LISTENING: {CallState.PROCESSING, CallState.ENDED, CallState.ERROR},
        CallState.ENDED: set(),  # Terminal state
        CallState.ERROR: {CallState.ENDED}  # Can only transition to ENDED
    }
    
    def __init__(self, session: CallSession, instructions: Optional[CallInstructions] = None):
        """Initialize call state machine."""
        self.session = session
        self.instructions = instructions or CallInstructions()
        
        # State machine state
        self.current_state = CallState.RINGING
        self.previous_state: Optional[CallState] = None
        self.state_entry_time = time.time()
        self.last_activity_time = time.time()
        
        # Event handling
        self.event_queue: asyncio.Queue = asyncio.Queue()
        self.event_handlers: Dict[CallEvent, List[Callable]] = {}
        
        # Timeout management
        self.timeout_tasks: Dict[str, asyncio.Task] = {}
        self.max_duration_task: Optional[asyncio.Task] = None
        self.silence_timeout_task: Optional[asyncio.Task] = None
        
        # Termination tracking
        self.termination_reason: Optional[TerminationReason] = None
        self.termination_time: Optional[float] = None
        self.is_terminating = False
        
        # Statistics
        self.stats = {
            'state_transitions': 0,
            'events_processed': 0,
            'timeouts_triggered': 0,
            'errors_handled': 0,
            'total_duration': 0.0
        }
        
        # Callbacks
        self.on_state_change: Optional[Callable[[CallState, CallState], None]] = None
        self.on_termination: Optional[Callable[[TerminationReason], None]] = None
        self.on_error: Optional[Callable[[str, Exception], None]] = None
        
        # Start event processing loop
        self._event_loop_task = asyncio.create_task(self._event_loop())
        
        logger.info(f"Call state machine initialized for call {session.call_id}")
    
    async def start(self) -> bool:
        """Start the call state machine."""
        try:
            logger.info(f"Starting call state machine for call {self.session.call_id}")
            
            # Initialize timeouts
            await self._setup_timeouts()
            
            # Process initial event
            await self.process_event(CallEvent.CALL_INITIATED)
            
            logger.info(f"Call state machine started for call {self.session.call_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start call state machine: {e}")
            await self._handle_error("Failed to start state machine", e)
            return False
    
    async def stop(self) -> None:
        """Stop the call state machine."""
        logger.info(f"Stopping call state machine for call {self.session.call_id}")
        
        # Cancel all timeout tasks
        for task in self.timeout_tasks.values():
            task.cancel()
        
        if self.max_duration_task:
            self.max_duration_task.cancel()
        
        if self.silence_timeout_task:
            self.silence_timeout_task.cancel()
        
        # Cancel event loop
        self._event_loop_task.cancel()
        
        # Final state transition to ENDED if not already
        if self.current_state not in [CallState.ENDED, CallState.ERROR]:
            await self._transition_to_state(CallState.ENDED, TerminationReason.NORMAL)
        
        logger.info(f"Call state machine stopped for call {self.session.call_id}")
    
    async def process_event(self, event: CallEvent, data: Optional[Dict[str, Any]] = None) -> bool:
        """Process a call event."""
        try:
            if self.is_terminating:
                logger.warning(f"Ignoring event {event.value} - call is terminating")
                return False
            
            # Add event to queue
            await self.event_queue.put((event, data or {}))
            self.stats['events_processed'] += 1
            
            # Update activity time
            self.last_activity_time = time.time()
            
            # Reset silence timeout
            await self._reset_silence_timeout()
            
            return True
            
        except Exception as e:
            logger.error(f"Error processing event {event.value}: {e}")
            await self._handle_error(f"Event processing error: {event.value}", e)
            return False
    
    async def _event_loop(self) -> None:
        """Main event processing loop."""
        while not self.is_terminating:
            try:
                # Wait for events with timeout
                event, data = await asyncio.wait_for(
                    self.event_queue.get(), 
                    timeout=1.0
                )
                
                # Process the event
                await self._handle_event(event, data)
                
            except asyncio.TimeoutError:
                # Check for timeouts
                await self._check_timeouts()
                continue
            except Exception as e:
                logger.error(f"Error in event loop: {e}")
                await self._handle_error("Event loop error", e)
    
    async def _handle_event(self, event: CallEvent, data: Dict[str, Any]) -> None:
        """Handle a specific event."""
        try:
            logger.debug(f"Processing event: {event.value} in state {self.current_state.value}")
            
            # Call event handlers
            if event in self.event_handlers:
                for handler in self.event_handlers[event]:
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            await handler(self, data)
                        else:
                            handler(self, data)
                    except Exception as e:
                        logger.error(f"Error in event handler: {e}")
            
            # Process state transitions based on event
            await self._process_state_transition(event, data)
            
        except Exception as e:
            logger.error(f"Error handling event {event.value}: {e}")
            await self._handle_error(f"Event handling error: {event.value}", e)
    
    async def _process_state_transition(self, event: CallEvent, data: Dict[str, Any]) -> None:
        """Process state transition based on event."""
        new_state = None
        
        # Determine new state based on current state and event
        if event == CallEvent.CALL_INITIATED:
            new_state = CallState.RINGING
        elif event == CallEvent.CALL_ANSWERED:
            new_state = CallState.CONNECTED
        elif event == CallEvent.CALL_CONNECTED:
            new_state = CallState.CONNECTED
        elif event == CallEvent.CALL_STARTED:
            new_state = CallState.LISTENING
        elif event == CallEvent.SPEECH_DETECTED:
            if self.current_state == CallState.LISTENING:
                new_state = CallState.PROCESSING
        elif event == CallEvent.RESPONSE_STARTED:
            if self.current_state == CallState.PROCESSING:
                new_state = CallState.SPEAKING
        elif event == CallEvent.RESPONSE_COMPLETED:
            if self.current_state == CallState.SPEAKING:
                new_state = CallState.LISTENING
        elif event == CallEvent.SPEECH_ENDED:
            if self.current_state == CallState.PROCESSING:
                new_state = CallState.PROCESSING  # Stay in processing for response
        elif event in [CallEvent.CALL_ENDED, CallEvent.USER_HANGUP, CallEvent.AGENT_HANGUP]:
            new_state = CallState.ENDED
        elif event in [CallEvent.CALL_TIMEOUT, CallEvent.CALL_ERROR, CallEvent.NETWORK_ERROR]:
            new_state = CallState.ERROR
        
        # Apply state transition if valid
        if new_state and new_state != self.current_state:
            # Determine termination reason based on event
            termination_reason = None
            if event == CallEvent.CALL_TIMEOUT:
                termination_reason = TerminationReason.TIMEOUT
            elif event == CallEvent.USER_HANGUP:
                termination_reason = TerminationReason.USER_HANGUP
            elif event == CallEvent.AGENT_HANGUP:
                termination_reason = TerminationReason.AGENT_HANGUP
            elif event == CallEvent.NETWORK_ERROR:
                termination_reason = TerminationReason.NETWORK_ERROR
            elif event == CallEvent.CALL_ERROR:
                termination_reason = TerminationReason.SYSTEM_ERROR
            
            await self._transition_to_state(new_state, termination_reason)
    
    async def _transition_to_state(self, new_state: CallState, termination_reason: Optional[TerminationReason] = None) -> bool:
        """Transition to a new state."""
        try:
            # Validate transition
            if not self._is_valid_transition(self.current_state, new_state):
                logger.warning(f"Invalid state transition: {self.current_state.value} -> {new_state.value}")
                return False
            
            # Update state
            self.previous_state = self.current_state
            self.current_state = new_state
            self.state_entry_time = time.time()
            
            # Update session state
            self.session.update_state(new_state)
            
            # Update statistics
            self.stats['state_transitions'] += 1
            
            # Handle termination
            if new_state in [CallState.ENDED, CallState.ERROR]:
                await self._handle_termination(termination_reason)
            
            # Call state change callback
            if self.on_state_change:
                try:
                    if asyncio.iscoroutinefunction(self.on_state_change):
                        await self.on_state_change(self.previous_state, new_state)
                    else:
                        self.on_state_change(self.previous_state, new_state)
                except Exception as e:
                    logger.error(f"Error in state change callback: {e}")
            
            logger.info(f"State transition: {self.previous_state.value} -> {new_state.value}")
            return True
            
        except Exception as e:
            logger.error(f"Error transitioning to state {new_state.value}: {e}")
            await self._handle_error(f"State transition error: {new_state.value}", e)
            return False
    
    def _is_valid_transition(self, from_state: CallState, to_state: CallState) -> bool:
        """Check if state transition is valid."""
        return to_state in self.VALID_TRANSITIONS.get(from_state, set())
    
    async def _handle_termination(self, reason: Optional[TerminationReason] = None) -> None:
        """Handle call termination."""
        if self.is_terminating:
            return
        
        self.is_terminating = True
        self.termination_reason = reason or TerminationReason.NORMAL
        self.termination_time = time.time()
        
        # Cancel all timeout tasks
        for task in self.timeout_tasks.values():
            task.cancel()
        
        if self.max_duration_task:
            self.max_duration_task.cancel()
        
        if self.silence_timeout_task:
            self.silence_timeout_task.cancel()
        
        # Call termination callback
        if self.on_termination:
            try:
                if asyncio.iscoroutinefunction(self.on_termination):
                    await self.on_termination(self.termination_reason)
                else:
                    self.on_termination(self.termination_reason)
            except Exception as e:
                logger.error(f"Error in termination callback: {e}")
        
        logger.info(f"Call terminated: {self.termination_reason.value}")
    
    async def _setup_timeouts(self) -> None:
        """Setup timeout management."""
        # Max duration timeout
        if self.instructions.max_duration > 0:
            self.max_duration_task = asyncio.create_task(
                self._max_duration_timeout()
            )
        
        # Silence timeout
        if self.instructions.silence_timeout > 0:
            await self._reset_silence_timeout()
    
    async def _max_duration_timeout(self) -> None:
        """Handle max duration timeout."""
        try:
            await asyncio.sleep(self.instructions.max_duration)
            logger.info(f"Max duration timeout reached for call {self.session.call_id}")
            await self.process_event(CallEvent.CALL_TIMEOUT)
        except asyncio.CancelledError:
            pass
    
    async def _reset_silence_timeout(self) -> None:
        """Reset silence timeout."""
        if self.silence_timeout_task:
            self.silence_timeout_task.cancel()
        
        if self.instructions.silence_timeout > 0:
            self.silence_timeout_task = asyncio.create_task(
                self._silence_timeout()
            )
    
    async def _silence_timeout(self) -> None:
        """Handle silence timeout."""
        try:
            await asyncio.sleep(self.instructions.silence_timeout)
            logger.info(f"Silence timeout reached for call {self.session.call_id}")
            await self.process_event(CallEvent.CALL_TIMEOUT)
        except asyncio.CancelledError:
            pass
    
    async def _check_timeouts(self) -> None:
        """Check for various timeouts."""
        current_time = time.time()
        
        # Check for overall inactivity timeout
        if current_time - self.last_activity_time > 300:  # 5 minutes
            logger.warning(f"Inactivity timeout for call {self.session.call_id}")
            await self.process_event(CallEvent.CALL_TIMEOUT)
    
    async def _handle_error(self, message: str, error: Exception) -> None:
        """Handle errors in the state machine."""
        logger.error(f"{message}: {error}")
        
        self.stats['errors_handled'] += 1
        
        # Call error callback
        if self.on_error:
            try:
                if asyncio.iscoroutinefunction(self.on_error):
                    await self.on_error(message, error)
                else:
                    self.on_error(message, error)
            except Exception as e:
                logger.error(f"Error in error callback: {e}")
        
        # Transition to error state
        await self._transition_to_state(CallState.ERROR, TerminationReason.SYSTEM_ERROR)
    
    def add_event_handler(self, event: CallEvent, handler: Callable) -> None:
        """Add an event handler."""
        if event not in self.event_handlers:
            self.event_handlers[event] = []
        self.event_handlers[event].append(handler)
    
    def remove_event_handler(self, event: CallEvent, handler: Callable) -> None:
        """Remove an event handler."""
        if event in self.event_handlers:
            try:
                self.event_handlers[event].remove(handler)
            except ValueError:
                pass
    
    def get_state_info(self) -> Dict[str, Any]:
        """Get current state information."""
        return {
            'current_state': self.current_state.value,
            'previous_state': self.previous_state.value if self.previous_state else None,
            'state_duration': time.time() - self.state_entry_time,
            'total_duration': time.time() - self.session.start_time,
            'is_terminating': self.is_terminating,
            'termination_reason': self.termination_reason.value if self.termination_reason else None,
            'last_activity': self.last_activity_time,
            'stats': self.stats.copy()
        }
    
    def is_active(self) -> bool:
        """Check if call is active."""
        return self.current_state not in [CallState.ENDED, CallState.ERROR] and not self.is_terminating
    
    def can_process_audio(self) -> bool:
        """Check if call can process audio."""
        return self.current_state in [CallState.LISTENING, CallState.PROCESSING, CallState.SPEAKING]
    
    def can_send_audio(self) -> bool:
        """Check if call can send audio."""
        return self.current_state in [CallState.SPEAKING, CallState.LISTENING]
    
    async def terminate_call(self, reason: TerminationReason = TerminationReason.NORMAL) -> None:
        """Manually terminate the call."""
        logger.info(f"Manually terminating call {self.session.call_id}: {reason.value}")
        
        if reason == TerminationReason.USER_HANGUP:
            await self.process_event(CallEvent.USER_HANGUP)
        elif reason == TerminationReason.AGENT_HANGUP:
            await self.process_event(CallEvent.AGENT_HANGUP)
        else:
            await self.process_event(CallEvent.CALL_ENDED)
    
    async def pause_call(self) -> bool:
        """Pause the call."""
        if self.current_state not in [CallState.LISTENING, CallState.PROCESSING, CallState.SPEAKING]:
            return False
        
        await self.process_event(CallEvent.PAUSE_CALL)
        return True
    
    async def resume_call(self) -> bool:
        """Resume the call."""
        if self.current_state not in [CallState.ENDED, CallState.ERROR]:
            await self.process_event(CallEvent.RESUME_CALL)
            return True
        return False
