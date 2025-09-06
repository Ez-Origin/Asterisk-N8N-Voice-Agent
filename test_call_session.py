#!/usr/bin/env python3
"""
Test script for Call Session Management

This script tests the call session management functionality including
session creation, state management, conversation handling, and cleanup.
"""

import asyncio
import logging
import time
from src.call_session import (
    CallSession, CallSessionManager, CallState, CallDirection, CallContext,
    get_session_manager, shutdown_session_manager
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_session_creation():
    """Test call session creation."""
    logger.info("Testing call session creation...")
    
    try:
        # Create session manager
        manager = CallSessionManager()
        
        # Create a test session
        session = await manager.create_session(
            call_id="test_call_001",
            from_user="+1234567890",
            to_user="+0987654321",
            direction=CallDirection.INBOUND
        )
        
        # Verify session properties
        assert session.call_id == "test_call_001"
        assert session.from_user == "+1234567890"
        assert session.to_user == "+0987654321"
        assert session.direction == CallDirection.INBOUND
        assert session.state == CallState.RINGING
        assert session.is_active()
        assert not session.is_processing()
        
        logger.info("✅ Call session creation test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ Call session creation test failed: {e}")
        return False


async def test_state_management():
    """Test call state management."""
    logger.info("Testing call state management...")
    
    try:
        manager = CallSessionManager()
        session = await manager.create_session(
            call_id="test_call_002",
            from_user="+1234567890",
            to_user="+0987654321"
        )
        
        # Test state transitions
        assert session.update_state(CallState.CONNECTED)
        assert session.state == CallState.CONNECTED
        
        assert session.update_state(CallState.PROCESSING)
        assert session.state == CallState.PROCESSING
        assert session.is_processing()
        
        assert session.update_state(CallState.SPEAKING)
        assert session.state == CallState.SPEAKING
        assert session.is_processing()
        
        assert session.update_state(CallState.LISTENING)
        assert session.state == CallState.LISTENING
        assert session.is_processing()
        
        # Test ending call
        assert session.update_state(CallState.ENDED)
        assert session.state == CallState.ENDED
        assert not session.is_active()
        assert not session.is_processing()
        
        # Test that ended calls can't change state
        assert not session.update_state(CallState.CONNECTED)
        
        logger.info("✅ Call state management test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ Call state management test failed: {e}")
        return False


async def test_conversation_management():
    """Test conversation history management."""
    logger.info("Testing conversation management...")
    
    try:
        manager = CallSessionManager()
        session = await manager.create_session(
            call_id="test_call_003",
            from_user="+1234567890",
            to_user="+0987654321"
        )
        
        # Add conversation messages
        session.add_to_conversation("user", "Hello, how are you?")
        session.add_to_conversation("assistant", "I'm doing well, thank you!")
        session.add_to_conversation("user", "What's the weather like?")
        
        # Verify conversation history
        history = session.get_conversation_history()
        assert len(history) == 3
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "Hello, how are you?"
        assert history[1]["role"] == "assistant"
        assert history[1]["content"] == "I'm doing well, thank you!"
        
        # Test conversation trimming (add many messages)
        for i in range(60):  # More than the 50 message limit
            session.add_to_conversation("user", f"Message {i}")
        
        history = session.get_conversation_history()
        assert len(history) == 50  # Should be trimmed to 50
        assert history[-1]["content"] == "Message 59"  # Last message should be the latest
        
        # Test clearing conversation
        session.clear_conversation()
        history = session.get_conversation_history()
        assert len(history) == 0
        
        logger.info("✅ Conversation management test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ Conversation management test failed: {e}")
        return False


async def test_statistics():
    """Test session statistics."""
    logger.info("Testing session statistics...")
    
    try:
        manager = CallSessionManager()
        session = await manager.create_session(
            call_id="test_call_004",
            from_user="+1234567890",
            to_user="+0987654321"
        )
        
        # Update statistics
        session.update_stats('stt_requests', 5)
        session.update_stats('llm_requests', 3)
        session.update_stats('tts_requests', 2)
        session.update_stats('errors', 1)
        
        # Get statistics
        stats = session.get_stats()
        assert stats['stt_requests'] == 5
        assert stats['llm_requests'] == 3
        assert stats['tts_requests'] == 2
        assert stats['errors'] == 1
        assert stats['state'] == CallState.RINGING.value
        assert stats['conversation_length'] == 0
        
        # Test manager statistics
        manager_stats = await manager.get_session_stats()
        assert manager_stats['total_sessions'] == 1
        assert manager_stats['active_sessions'] == 1
        assert 'test_call_004' in manager_stats['sessions']
        
        logger.info("✅ Session statistics test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ Session statistics test failed: {e}")
        return False


async def test_session_manager():
    """Test session manager functionality."""
    logger.info("Testing session manager...")
    
    try:
        manager = CallSessionManager()
        
        # Create multiple sessions
        session1 = await manager.create_session(
            call_id="test_call_005",
            from_user="+1111111111",
            to_user="+2222222222"
        )
        session2 = await manager.create_session(
            call_id="test_call_006",
            from_user="+3333333333",
            to_user="+4444444444"
        )
        
        # Test getting sessions
        retrieved_session = await manager.get_session("test_call_005")
        assert retrieved_session is not None
        assert retrieved_session.call_id == "test_call_005"
        
        # Test getting non-existent session
        non_existent = await manager.get_session("non_existent")
        assert non_existent is None
        
        # Test active sessions
        active_sessions = await manager.get_active_sessions()
        assert len(active_sessions) == 2
        
        # Test state updates
        await manager.update_session_state("test_call_005", CallState.CONNECTED)
        session1 = await manager.get_session("test_call_005")
        assert session1.state == CallState.CONNECTED
        
        # Test session removal
        removed = await manager.remove_session("test_call_005")
        assert removed
        assert await manager.get_session("test_call_005") is None
        
        # Test removing non-existent session
        removed = await manager.remove_session("non_existent")
        assert not removed
        
        logger.info("✅ Session manager test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ Session manager test failed: {e}")
        return False


async def test_callbacks():
    """Test session callbacks."""
    logger.info("Testing session callbacks...")
    
    try:
        manager = CallSessionManager()
        
        # Track callback calls
        state_changes = []
        errors = []
        cleanups = []
        
        def on_state_change(state):
            state_changes.append(state)
        
        def on_error(message, error):
            errors.append((message, error))
        
        def on_cleanup():
            cleanups.append(True)
        
        # Create session with callbacks
        session = await manager.create_session(
            call_id="test_call_007",
            from_user="+1234567890",
            to_user="+0987654321"
        )
        session.on_state_change = on_state_change
        session.on_error = on_error
        session.on_cleanup = on_cleanup
        
        # Test state change callback
        session.update_state(CallState.CONNECTED)
        assert len(state_changes) == 1
        assert state_changes[0] == CallState.CONNECTED
        
        # Test cleanup callback
        session.cleanup()
        assert len(cleanups) == 1
        
        logger.info("✅ Session callbacks test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ Session callbacks test failed: {e}")
        return False


async def test_global_manager():
    """Test global session manager."""
    logger.info("Testing global session manager...")
    
    try:
        # Get global manager
        manager1 = get_session_manager()
        manager2 = get_session_manager()
        assert manager1 is manager2  # Should be the same instance
        
        # Create session using global manager
        session = await manager1.create_session(
            call_id="test_call_008",
            from_user="+1234567890",
            to_user="+0987654321"
        )
        assert session is not None
        
        # Test shutdown
        await shutdown_session_manager()
        
        logger.info("✅ Global session manager test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ Global session manager test failed: {e}")
        return False


async def main():
    """Run all tests."""
    logger.info("Starting Call Session Management tests...")
    logger.info("=" * 50)
    
    tests = [
        ("Session Creation", test_session_creation),
        ("State Management", test_state_management),
        ("Conversation Management", test_conversation_management),
        ("Statistics", test_statistics),
        ("Session Manager", test_session_manager),
        ("Callbacks", test_callbacks),
        ("Global Manager", test_global_manager),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        logger.info(f"\n{'=' * 50}")
        logger.info(f"Running {test_name} test...")
        logger.info("=" * 50)
        
        try:
            success = await test_func()
            if success:
                passed += 1
                logger.info(f"✅ {test_name} test PASSED")
            else:
                logger.error(f"❌ {test_name} test FAILED")
        except Exception as e:
            logger.error(f"❌ {test_name} test FAILED with exception: {e}")
    
    logger.info(f"\n{'=' * 50}")
    logger.info(f"Test Results: {passed}/{total} tests passed")
    logger.info("=" * 50)
    
    if passed == total:
        logger.info("🎉 All call session management tests passed!")
    else:
        logger.error(f"❌ {total - passed} tests failed")
    
    return passed == total


if __name__ == "__main__":
    asyncio.run(main())
