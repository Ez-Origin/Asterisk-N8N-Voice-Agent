#!/usr/bin/env python3
"""
Test Call State Machine

This script tests the call state machine implementation for robust
call lifecycle management, state transitions, and termination handling.
"""

import asyncio
import logging
import sys
import time
from unittest.mock import Mock, AsyncMock

# Add src to path
sys.path.insert(0, 'src')

from call_session import CallSession, CallState, CallDirection
from call_state_machine import (
    CallStateMachine, CallEvent, TerminationReason, CallInstructions
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_state_machine_initialization():
    """Test call state machine initialization."""
    logger.info("Testing State Machine Initialization")
    
    try:
        # Create mock session
        session = CallSession(
            call_id="test-call-init",
            session_id="test-session-init",
            from_user="user123",
            to_user="agent",
            direction=CallDirection.INBOUND
        )
        
        # Create instructions
        instructions = CallInstructions(
            system_prompt="You are a test assistant.",
            max_duration=60,
            silence_timeout=10
        )
        
        # Create state machine
        state_machine = CallStateMachine(session, instructions)
        
        # Test initialization
        assert state_machine.current_state == CallState.RINGING, "Should start in RINGING state"
        assert state_machine.session == session, "Session should be set"
        assert state_machine.instructions == instructions, "Instructions should be set"
        assert not state_machine.is_terminating, "Should not be terminating initially"
        
        # Test start
        success = await state_machine.start()
        assert success, "State machine should start successfully"
        
        # Test stop
        await state_machine.stop()
        assert state_machine.is_terminating, "Should be terminating after stop"
        
        logger.info("✅ State machine initialization test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ State machine initialization test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_state_transitions():
    """Test valid state transitions."""
    logger.info("Testing State Transitions")
    
    try:
        # Create mock session
        session = CallSession(
            call_id="test-call-transitions",
            session_id="test-session-transitions",
            from_user="user123",
            to_user="agent",
            direction=CallDirection.INBOUND
        )
        
        # Create state machine
        state_machine = CallStateMachine(session)
        await state_machine.start()
        
        # Test valid transitions
        transitions = [
            (CallEvent.CALL_ANSWERED, CallState.CONNECTED),
            (CallEvent.CALL_STARTED, CallState.LISTENING),
            (CallEvent.SPEECH_DETECTED, CallState.PROCESSING),
            (CallEvent.RESPONSE_STARTED, CallState.SPEAKING),
            (CallEvent.RESPONSE_COMPLETED, CallState.LISTENING),
            (CallEvent.CALL_ENDED, CallState.ENDED)
        ]
        
        for event, expected_state in transitions:
            success = await state_machine.process_event(event)
            assert success, f"Event {event.value} should be processed successfully"
            
            # Wait a bit for state transition
            await asyncio.sleep(0.1)
            
            if expected_state != CallState.ENDED:  # Don't check ENDED as it's terminal
                assert state_machine.current_state == expected_state, \
                    f"Should be in {expected_state.value} after {event.value}"
        
        logger.info("✅ State transitions test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ State transitions test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if 'state_machine' in locals():
            await state_machine.stop()


async def test_termination_handling():
    """Test call termination handling."""
    logger.info("Testing Termination Handling")
    
    try:
        # Create mock session
        session = CallSession(
            call_id="test-call-termination",
            session_id="test-session-termination",
            from_user="user123",
            to_user="agent",
            direction=CallDirection.INBOUND
        )
        
        # Create state machine
        state_machine = CallStateMachine(session)
        await state_machine.start()
        
        # Test different termination scenarios
        termination_tests = [
            (CallEvent.USER_HANGUP, TerminationReason.USER_HANGUP),
            (CallEvent.AGENT_HANGUP, TerminationReason.AGENT_HANGUP),
            (CallEvent.CALL_TIMEOUT, TerminationReason.TIMEOUT),
            (CallEvent.NETWORK_ERROR, TerminationReason.NETWORK_ERROR),
            (CallEvent.CALL_ERROR, TerminationReason.SYSTEM_ERROR)
        ]
        
        for event, expected_reason in termination_tests:
            # Reset state machine
            state_machine = CallStateMachine(session)
            await state_machine.start()
            
            # Process termination event
            success = await state_machine.process_event(event)
            assert success, f"Termination event {event.value} should be processed"
            
            # Wait for state transition
            await asyncio.sleep(0.1)
            
            # Check termination
            assert state_machine.is_terminating, f"Should be terminating after {event.value}"
            assert state_machine.current_state in [CallState.ENDED, CallState.ERROR], \
                f"Should be in terminal state after {event.value}"
        
        logger.info("✅ Termination handling test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ Termination handling test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if 'state_machine' in locals():
            await state_machine.stop()


async def test_timeout_management():
    """Test timeout management."""
    logger.info("Testing Timeout Management")
    
    try:
        # Create mock session
        session = CallSession(
            call_id="test-call-timeout",
            session_id="test-session-timeout",
            from_user="user123",
            to_user="agent",
            direction=CallDirection.INBOUND
        )
        
        # Create instructions with short timeouts for testing
        instructions = CallInstructions(
            max_duration=2,  # 2 seconds
            silence_timeout=1  # 1 second
        )
        
        # Create state machine
        state_machine = CallStateMachine(session, instructions)
        await state_machine.start()
        
        # Test max duration timeout
        logger.info("Testing max duration timeout...")
        await asyncio.sleep(2.5)  # Wait longer than max duration
        
        assert state_machine.is_terminating, "Should be terminating after max duration"
        assert state_machine.termination_reason == TerminationReason.TIMEOUT, \
            "Should have timeout termination reason"
        
        logger.info("✅ Timeout management test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ Timeout management test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if 'state_machine' in locals():
            await state_machine.stop()


async def test_event_handlers():
    """Test event handler registration and execution."""
    logger.info("Testing Event Handlers")
    
    try:
        # Create mock session
        session = CallSession(
            call_id="test-call-handlers",
            session_id="test-session-handlers",
            from_user="user123",
            to_user="agent",
            direction=CallDirection.INBOUND
        )
        
        # Create state machine
        state_machine = CallStateMachine(session)
        
        # Track handler calls
        handler_calls = []
        
        def test_handler(sm, data):
            handler_calls.append(("test_handler", data))
        
        async def async_test_handler(sm, data):
            handler_calls.append(("async_test_handler", data))
        
        # Add event handlers
        state_machine.add_event_handler(CallEvent.CALL_ANSWERED, test_handler)
        state_machine.add_event_handler(CallEvent.SPEECH_DETECTED, async_test_handler)
        
        await state_machine.start()
        
        # Process events
        await state_machine.process_event(CallEvent.CALL_ANSWERED, {"test": "data"})
        await state_machine.process_event(CallEvent.SPEECH_DETECTED, {"speech": "data"})
        
        # Wait for handlers to execute
        await asyncio.sleep(0.1)
        
        # Check handler calls
        assert len(handler_calls) >= 2, "Event handlers should have been called"
        
        # Test handler removal
        state_machine.remove_event_handler(CallEvent.CALL_ANSWERED, test_handler)
        await state_machine.process_event(CallEvent.CALL_ANSWERED)
        await asyncio.sleep(0.1)
        
        # Should not have additional calls for removed handler
        call_count = len([call for call in handler_calls if call[0] == "test_handler"])
        assert call_count == 1, "Removed handler should not be called again"
        
        logger.info("✅ Event handlers test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ Event handlers test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if 'state_machine' in locals():
            await state_machine.stop()


async def test_call_instructions():
    """Test per-call instructions and configuration."""
    logger.info("Testing Call Instructions")
    
    try:
        # Create mock session
        session = CallSession(
            call_id="test-call-instructions",
            session_id="test-session-instructions",
            from_user="user123",
            to_user="agent",
            direction=CallDirection.INBOUND
        )
        
        # Create custom instructions
        instructions = CallInstructions(
            system_prompt="You are a specialized test assistant.",
            custom_instructions="Always respond with 'Test response'",
            language="en-GB",
            voice_type="echo",
            max_duration=300,
            silence_timeout=15,
            response_timeout=20,
            enable_recording=True,
            enable_transcription=False,
            transfer_number="+1234567890",
            metadata={"test": "value", "priority": "high"}
        )
        
        # Create state machine
        state_machine = CallStateMachine(session, instructions)
        
        # Test instruction properties
        assert state_machine.instructions.system_prompt == "You are a specialized test assistant."
        assert state_machine.instructions.custom_instructions == "Always respond with 'Test response'"
        assert state_machine.instructions.language == "en-GB"
        assert state_machine.instructions.voice_type == "echo"
        assert state_machine.instructions.max_duration == 300
        assert state_machine.instructions.silence_timeout == 15
        assert state_machine.instructions.response_timeout == 20
        assert state_machine.instructions.enable_recording == True
        assert state_machine.instructions.enable_transcription == False
        assert state_machine.instructions.transfer_number == "+1234567890"
        assert state_machine.instructions.metadata["test"] == "value"
        assert state_machine.instructions.metadata["priority"] == "high"
        
        logger.info("✅ Call instructions test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ Call instructions test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_state_validation():
    """Test state validation and invalid transitions."""
    logger.info("Testing State Validation")
    
    try:
        # Create mock session
        session = CallSession(
            call_id="test-call-validation",
            session_id="test-session-validation",
            from_user="user123",
            to_user="agent",
            direction=CallDirection.INBOUND
        )
        
        # Create state machine
        state_machine = CallStateMachine(session)
        await state_machine.start()
        
        # Test state validation methods
        assert state_machine.is_active(), "Should be active initially"
        assert not state_machine.can_process_audio(), "Should not process audio in RINGING state"
        assert not state_machine.can_send_audio(), "Should not send audio in RINGING state"
        
        # Transition to CONNECTED
        await state_machine.process_event(CallEvent.CALL_ANSWERED)
        await asyncio.sleep(0.1)
        
        assert state_machine.is_active(), "Should be active in CONNECTED state"
        assert not state_machine.can_process_audio(), "Should not process audio in CONNECTED state"
        assert not state_machine.can_send_audio(), "Should not send audio in CONNECTED state"
        
        # Transition to LISTENING
        await state_machine.process_event(CallEvent.CALL_STARTED)
        await asyncio.sleep(0.1)
        
        assert state_machine.is_active(), "Should be active in LISTENING state"
        assert state_machine.can_process_audio(), "Should process audio in LISTENING state"
        assert state_machine.can_send_audio(), "Should send audio in LISTENING state"
        
        # Test manual termination
        await state_machine.terminate_call(TerminationReason.USER_HANGUP)
        await asyncio.sleep(0.1)
        
        assert not state_machine.is_active(), "Should not be active after termination"
        assert state_machine.is_terminating, "Should be terminating after manual termination"
        
        logger.info("✅ State validation test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ State validation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if 'state_machine' in locals():
            await state_machine.stop()


async def test_statistics():
    """Test state machine statistics tracking."""
    logger.info("Testing Statistics")
    
    try:
        # Create mock session
        session = CallSession(
            call_id="test-call-stats",
            session_id="test-session-stats",
            from_user="user123",
            to_user="agent",
            direction=CallDirection.INBOUND
        )
        
        # Create state machine
        state_machine = CallStateMachine(session)
        await state_machine.start()
        
        # Process some events
        await state_machine.process_event(CallEvent.CALL_ANSWERED)
        await state_machine.process_event(CallEvent.CALL_STARTED)
        await state_machine.process_event(CallEvent.SPEECH_DETECTED)
        await state_machine.process_event(CallEvent.RESPONSE_STARTED)
        await state_machine.process_event(CallEvent.RESPONSE_COMPLETED)
        
        # Wait for processing
        await asyncio.sleep(0.2)
        
        # Get state info
        state_info = state_machine.get_state_info()
        
        # Check statistics
        assert 'current_state' in state_info, "State info should include current state"
        assert 'previous_state' in state_info, "State info should include previous state"
        assert 'state_duration' in state_info, "State info should include state duration"
        assert 'total_duration' in state_info, "State info should include total duration"
        assert 'is_terminating' in state_info, "State info should include termination status"
        assert 'stats' in state_info, "State info should include statistics"
        
        stats = state_info['stats']
        assert 'state_transitions' in stats, "Stats should include state transitions"
        assert 'events_processed' in stats, "Stats should include events processed"
        assert stats['events_processed'] >= 5, "Should have processed at least 5 events"
        assert stats['state_transitions'] >= 3, "Should have at least 3 state transitions"
        
        logger.info("✅ Statistics test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ Statistics test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if 'state_machine' in locals():
            await state_machine.stop()


async def main():
    """Run all tests."""
    logger.info("Starting Call State Machine Tests")
    
    tests = [
        ("State Machine Initialization", test_state_machine_initialization),
        ("State Transitions", test_state_transitions),
        ("Termination Handling", test_termination_handling),
        ("Timeout Management", test_timeout_management),
        ("Event Handlers", test_event_handlers),
        ("Call Instructions", test_call_instructions),
        ("State Validation", test_state_validation),
        ("Statistics", test_statistics)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        logger.info(f"\n{'='*50}")
        logger.info(f"Running {test_name} Test")
        logger.info(f"{'='*50}")
        
        try:
            result = await test_func()
            if result:
                passed += 1
                logger.info(f"✅ {test_name} test PASSED")
            else:
                logger.error(f"❌ {test_name} test FAILED")
        except Exception as e:
            logger.error(f"❌ {test_name} test FAILED with exception: {e}")
    
    logger.info(f"\n{'='*50}")
    logger.info(f"Test Results: {passed}/{total} tests passed")
    logger.info(f"{'='*50}")
    
    if passed == total:
        logger.info("🎉 All tests passed!")
        return True
    else:
        logger.error(f"❌ {total - passed} tests failed")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
