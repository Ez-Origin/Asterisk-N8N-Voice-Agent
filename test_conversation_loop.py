#!/usr/bin/env python3
"""
Test script for Conversation Loop

This script tests the conversation loop functionality including
initialization, audio processing, and AI provider integration.
"""

import asyncio
import logging
import time
from unittest.mock import Mock, AsyncMock
from src.conversation_loop import ConversationLoop, ConversationConfig, ConversationState
from src.call_session import CallSession, CallDirection, CallState

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MockRealtimeClient:
    """Mock Realtime client for testing."""
    
    def __init__(self):
        self.is_connected = True
        self.session_id = "test_session"
    
    async def connect(self):
        return True
    
    async def disconnect(self):
        pass
    
    async def initialize_session(self):
        return True


class MockSTTHandler:
    """Mock STT handler for testing."""
    
    def __init__(self, config, client):
        self.config = config
        self.client = client
        self.is_listening = False
        self.current_transcript = None
    
    async def start_listening(self):
        self.is_listening = True
        return True
    
    async def stop_listening(self):
        self.is_listening = False
    
    async def process_audio(self, audio_data):
        # Simulate transcript generation
        self.current_transcript = Mock()
        self.current_transcript.text = "Hello, this is a test"
        return True
    
    def get_current_transcript(self):
        return self.current_transcript


class MockLLMHandler:
    """Mock LLM handler for testing."""
    
    def __init__(self, config, client):
        self.config = config
        self.client = client
        self.is_responding = False
        self.current_response = None
    
    async def send_message(self, message):
        return True
    
    async def create_response(self, modalities):
        self.is_responding = True
        # Simulate response generation
        self.current_response = Mock()
        self.current_response.text = "Hello! How can I help you today?"
        return True
    
    async def cancel_response(self):
        self.is_responding = False
    
    def is_responding(self):
        return self.is_responding
    
    def get_current_response(self):
        return self.current_response


class MockTTSHandler:
    """Mock TTS handler for testing."""
    
    def __init__(self, config, client):
        self.config = config
        self.client = client
        self.is_synthesizing = False
    
    async def synthesize_text(self, text):
        self.is_synthesizing = True
        return True
    
    async def stop_synthesis(self):
        self.is_synthesizing = False
    
    def is_synthesizing(self):
        return self.is_synthesizing


class MockAudioPipeline:
    """Mock audio processing pipeline for testing."""
    
    def __init__(self, config):
        self.config = config
        self.voice_detected = False
        self.silence_detected = False
    
    async def initialize(self):
        return True
    
    async def process_audio(self, audio_data):
        # Simulate voice detection
        self.voice_detected = True
        return audio_data
    
    def is_voice_detected(self):
        return self.voice_detected
    
    def is_silence_detected(self):
        return self.silence_detected


async def test_conversation_loop_creation():
    """Test conversation loop creation."""
    logger.info("Testing conversation loop creation...")
    
    try:
        # Create mock session
        session = CallSession(
            call_id="test_call_001",
            session_id="test_session_001",
            from_user="+1234567890",
            to_user="+0987654321",
            direction=CallDirection.INBOUND
        )
        
        # Create config
        config = ConversationConfig(
            openai_api_key="test_key",
            system_prompt="You are a test assistant."
        )
        
        # Create conversation loop
        loop = ConversationLoop(session, config)
        
        # Verify properties
        assert loop.session == session
        assert loop.config == config
        assert loop.state == ConversationState.IDLE
        assert not loop.is_running
        
        logger.info("✅ Conversation loop creation test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ Conversation loop creation test failed: {e}")
        return False


async def test_conversation_loop_initialization():
    """Test conversation loop initialization."""
    logger.info("Testing conversation loop initialization...")
    
    try:
        # Create mock session
        session = CallSession(
            call_id="test_call_002",
            session_id="test_session_002",
            from_user="+1234567890",
            to_user="+0987654321",
            direction=CallDirection.INBOUND
        )
        
        # Create config
        config = ConversationConfig(
            openai_api_key="test_key",
            system_prompt="You are a test assistant."
        )
        
        # Create conversation loop
        loop = ConversationLoop(session, config)
        
        # Mock the components
        loop.realtime_client = MockRealtimeClient()
        loop.stt_handler = MockSTTHandler(config, loop.realtime_client)
        loop.llm_handler = MockLLMHandler(config, loop.realtime_client)
        loop.tts_handler = MockTTSHandler(config, loop.realtime_client)
        loop.audio_pipeline = MockAudioPipeline({})
        
        # Test initialization
        success = await loop.initialize()
        assert success
        
        # Verify components are set
        assert loop.realtime_client is not None
        assert loop.stt_handler is not None
        assert loop.llm_handler is not None
        assert loop.tts_handler is not None
        assert loop.audio_pipeline is not None
        
        logger.info("✅ Conversation loop initialization test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ Conversation loop initialization test failed: {e}")
        return False


async def test_conversation_loop_start_stop():
    """Test conversation loop start and stop."""
    logger.info("Testing conversation loop start/stop...")
    
    try:
        # Create mock session
        session = CallSession(
            call_id="test_call_003",
            session_id="test_session_003",
            from_user="+1234567890",
            to_user="+0987654321",
            direction=CallDirection.INBOUND
        )
        
        # Create config
        config = ConversationConfig(
            openai_api_key="test_key",
            system_prompt="You are a test assistant."
        )
        
        # Create conversation loop
        loop = ConversationLoop(session, config)
        
        # Mock the components
        loop.realtime_client = MockRealtimeClient()
        loop.stt_handler = MockSTTHandler(config, loop.realtime_client)
        loop.llm_handler = MockLLMHandler(config, loop.realtime_client)
        loop.tts_handler = MockTTSHandler(config, loop.realtime_client)
        loop.audio_pipeline = MockAudioPipeline({})
        
        # Initialize
        await loop.initialize()
        
        # Test start
        success = await loop.start()
        assert success
        assert loop.is_running
        assert session.state == CallState.CONNECTED
        
        # Test stop
        await loop.stop()
        assert not loop.is_running
        assert session.state == CallState.ENDED
        
        logger.info("✅ Conversation loop start/stop test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ Conversation loop start/stop test failed: {e}")
        return False


async def test_audio_processing():
    """Test audio processing functionality."""
    logger.info("Testing audio processing...")
    
    try:
        # Create mock session
        session = CallSession(
            call_id="test_call_004",
            session_id="test_session_004",
            from_user="+1234567890",
            to_user="+0987654321",
            direction=CallDirection.INBOUND
        )
        
        # Create config
        config = ConversationConfig(
            openai_api_key="test_key",
            system_prompt="You are a test assistant."
        )
        
        # Create conversation loop
        loop = ConversationLoop(session, config)
        
        # Mock the components
        loop.realtime_client = MockRealtimeClient()
        loop.stt_handler = MockSTTHandler(config, loop.realtime_client)
        loop.llm_handler = MockLLMHandler(config, loop.realtime_client)
        loop.tts_handler = MockTTSHandler(config, loop.realtime_client)
        loop.audio_pipeline = MockAudioPipeline({})
        
        # Initialize
        await loop.initialize()
        
        # Test audio processing
        test_audio = b"test_audio_data"
        success = await loop.process_audio_chunk(test_audio)
        assert success
        
        # Verify audio was processed
        assert len(loop.current_audio_buffer) > 0
        
        logger.info("✅ Audio processing test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ Audio processing test failed: {e}")
        return False


async def test_state_management():
    """Test conversation state management."""
    logger.info("Testing state management...")
    
    try:
        # Create mock session
        session = CallSession(
            call_id="test_call_005",
            session_id="test_session_005",
            from_user="+1234567890",
            to_user="+0987654321",
            direction=CallDirection.INBOUND
        )
        
        # Create config
        config = ConversationConfig(
            openai_api_key="test_key",
            system_prompt="You are a test assistant."
        )
        
        # Create conversation loop
        loop = ConversationLoop(session, config)
        
        # Test initial state
        assert loop.state == ConversationState.IDLE
        
        # Test state changes
        loop._update_state(ConversationState.LISTENING)
        assert loop.state == ConversationState.LISTENING
        
        loop._update_state(ConversationState.PROCESSING)
        assert loop.state == ConversationState.PROCESSING
        
        loop._update_state(ConversationState.SPEAKING)
        assert loop.state == ConversationState.SPEAKING
        
        logger.info("✅ State management test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ State management test failed: {e}")
        return False


async def test_statistics():
    """Test conversation loop statistics."""
    logger.info("Testing statistics...")
    
    try:
        # Create mock session
        session = CallSession(
            call_id="test_call_006",
            session_id="test_session_006",
            from_user="+1234567890",
            to_user="+0987654321",
            direction=CallDirection.INBOUND
        )
        
        # Create config
        config = ConversationConfig(
            openai_api_key="test_key",
            system_prompt="You are a test assistant."
        )
        
        # Create conversation loop
        loop = ConversationLoop(session, config)
        
        # Test initial statistics
        stats = loop.get_stats()
        assert 'conversation_turns' in stats
        assert 'total_processing_time' in stats
        assert 'errors' in stats
        assert 'state' in stats
        assert 'is_running' in stats
        assert 'session_stats' in stats
        
        # Test statistics updates
        loop.stats['conversation_turns'] = 5
        loop.stats['errors'] = 2
        
        stats = loop.get_stats()
        assert stats['conversation_turns'] == 5
        assert stats['errors'] == 2
        
        logger.info("✅ Statistics test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ Statistics test failed: {e}")
        return False


async def test_callbacks():
    """Test conversation loop callbacks."""
    logger.info("Testing callbacks...")
    
    try:
        # Create mock session
        session = CallSession(
            call_id="test_call_007",
            session_id="test_session_007",
            from_user="+1234567890",
            to_user="+0987654321",
            direction=CallDirection.INBOUND
        )
        
        # Track callback calls
        user_speech_calls = []
        ai_response_calls = []
        state_change_calls = []
        error_calls = []
        
        def on_user_speech(text):
            user_speech_calls.append(text)
        
        def on_ai_response(text):
            ai_response_calls.append(text)
        
        def on_state_change(state):
            state_change_calls.append(state)
        
        def on_error(message, error):
            error_calls.append((message, error))
        
        # Create config with callbacks
        config = ConversationConfig(
            openai_api_key="test_key",
            system_prompt="You are a test assistant.",
            on_user_speech=on_user_speech,
            on_ai_response=on_ai_response,
            on_state_change=on_state_change,
            on_error=on_error
        )
        
        # Create conversation loop
        loop = ConversationLoop(session, config)
        
        # Test state change callback
        loop._update_state(ConversationState.LISTENING)
        assert len(state_change_calls) == 1
        assert state_change_calls[0] == ConversationState.LISTENING
        
        # Test error callback
        await loop._handle_error("Test error", Exception("Test exception"))
        assert len(error_calls) == 1
        assert error_calls[0][0] == "Test error"
        
        logger.info("✅ Callbacks test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ Callbacks test failed: {e}")
        return False


async def main():
    """Run all tests."""
    logger.info("Starting Conversation Loop tests...")
    logger.info("=" * 50)
    
    tests = [
        ("Conversation Loop Creation", test_conversation_loop_creation),
        ("Initialization", test_conversation_loop_initialization),
        ("Start/Stop", test_conversation_loop_start_stop),
        ("Audio Processing", test_audio_processing),
        ("State Management", test_state_management),
        ("Statistics", test_statistics),
        ("Callbacks", test_callbacks),
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
        logger.info("🎉 All conversation loop tests passed!")
    else:
        logger.error(f"❌ {total - passed} tests failed")
    
    return passed == total


if __name__ == "__main__":
    asyncio.run(main())
