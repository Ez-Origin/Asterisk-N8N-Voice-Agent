#!/usr/bin/env python3
"""
Test AI Provider Integration

This script tests the integration of AI providers (STT, LLM, TTS) 
within the conversation loop.
"""

import asyncio
import logging
import sys
import time
from unittest.mock import Mock, AsyncMock, MagicMock

# Add src to path
sys.path.insert(0, 'src')

from call_session import CallSession, CallSessionConfig, CallState
from conversation_loop import ConversationLoop, ConversationConfig, ConversationState
from providers.openai import RealtimeClient, STTHandler, LLMHandler, TTSHandler
from providers.openai import RealtimeConfig, STTConfig, LLMConfig, TTSConfig
from audio_processing.pipeline import AudioFrame

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MockRealtimeClient:
    """Mock RealtimeClient for testing."""
    
    def __init__(self, config):
        self.config = config
        self.is_connected = False
        self.message_handlers = {}
    
    async def connect(self):
        """Mock connection."""
        await asyncio.sleep(0.1)  # Simulate connection delay
        self.is_connected = True
        return True
    
    async def disconnect(self):
        """Mock disconnection."""
        await asyncio.sleep(0.1)  # Simulate disconnection delay
        self.is_connected = False
    
    async def send_message(self, message):
        """Mock message sending."""
        pass
    
    def set_message_handler(self, message_type, handler):
        """Mock message handler setup."""
        self.message_handlers[message_type] = handler


class MockSTTHandler:
    """Mock STTHandler for testing."""
    
    def __init__(self, config, client):
        self.config = config
        self.client = client
        self.is_listening = False
        self.current_transcript = None
    
    async def start_listening(self):
        """Mock start listening."""
        await asyncio.sleep(0.1)
        self.is_listening = True
        return True
    
    async def stop_listening(self):
        """Mock stop listening."""
        await asyncio.sleep(0.1)
        self.is_listening = False
    
    async def process_audio(self, audio_data):
        """Mock audio processing."""
        await asyncio.sleep(0.2)  # Simulate processing time
        # Simulate transcript generation
        self.current_transcript = Mock()
        self.current_transcript.text = "Hello, this is a test transcript"
        return True
    
    def get_current_transcript(self):
        """Mock get current transcript."""
        return self.current_transcript


class MockLLMHandler:
    """Mock LLMHandler for testing."""
    
    def __init__(self, config, client):
        self.config = config
        self.client = client
        self.is_responding = False
        self.current_response = None
    
    async def send_message(self, message):
        """Mock send message."""
        await asyncio.sleep(0.1)
    
    async def create_response(self, response_types):
        """Mock create response."""
        await asyncio.sleep(0.1)
        self.is_responding = True
        return True
    
    async def cancel_response(self):
        """Mock cancel response."""
        await asyncio.sleep(0.1)
        self.is_responding = False
    
    def get_current_response(self):
        """Mock get current response."""
        if not self.current_response:
            self.current_response = Mock()
            self.current_response.text = "This is a test AI response"
        return self.current_response


class MockTTSHandler:
    """Mock TTSHandler for testing."""
    
    def __init__(self, config, client):
        self.config = config
        self.client = client
        self.is_synthesizing = False
    
    async def synthesize_text(self, text):
        """Mock text synthesis."""
        await asyncio.sleep(0.3)  # Simulate synthesis time
        self.is_synthesizing = True
        return True
    
    async def stop_synthesis(self):
        """Mock stop synthesis."""
        await asyncio.sleep(0.1)
        self.is_synthesizing = False


async def test_ai_provider_integration():
    """Test AI provider integration in conversation loop."""
    logger.info("Testing AI Provider Integration")
    
    try:
        # Create mock session
        session_config = CallSessionConfig()
        session = CallSession("test-call-123", "user123", "agent", session_config)
        
        # Create conversation config
        conv_config = ConversationConfig(
            openai_api_key="test-key",
            system_prompt="You are a helpful test assistant.",
            enable_vad=True,
            enable_noise_suppression=True,
            enable_echo_cancellation=True
        )
        
        # Create conversation loop
        conv_loop = ConversationLoop(session, conv_config)
        
        # Mock the AI providers
        conv_loop.realtime_client = MockRealtimeClient(RealtimeConfig(api_key="test"))
        conv_loop.stt_handler = MockSTTHandler(STTConfig(), conv_loop.realtime_client)
        conv_loop.llm_handler = MockLLMHandler(LLMConfig(), conv_loop.realtime_client)
        conv_loop.tts_handler = MockTTSHandler(TTSConfig(), conv_loop.realtime_client)
        
        # Setup callbacks
        conv_loop._setup_callbacks()
        
        # Test initialization
        logger.info("Testing conversation loop initialization...")
        success = await conv_loop.initialize()
        assert success, "Conversation loop initialization should succeed"
        logger.info("✅ Conversation loop initialization test passed")
        
        # Test conversation flow
        logger.info("Testing conversation flow...")
        
        # Start conversation loop
        conv_loop.is_running = True
        conv_loop._update_state(ConversationState.LISTENING)
        
        # Test audio processing
        logger.info("Testing audio processing...")
        test_audio = b"test audio data" * 100  # Simulate audio data
        
        # Create mock audio frame
        audio_frame = AudioFrame(
            data=test_audio,
            timestamp=time.time(),
            metadata={'is_speech': True, 'source': 'test'}
        )
        
        # Process audio chunk
        success = await conv_loop.process_audio_chunk(test_audio)
        assert success, "Audio processing should succeed"
        logger.info("✅ Audio processing test passed")
        
        # Test speech processing
        logger.info("Testing speech processing...")
        conv_loop.current_audio_buffer = test_audio
        await conv_loop._process_speech()
        logger.info("✅ Speech processing test passed")
        
        # Test response generation
        logger.info("Testing response generation...")
        await conv_loop._generate_response("Hello, how are you?")
        logger.info("✅ Response generation test passed")
        
        # Test TTS synthesis
        logger.info("Testing TTS synthesis...")
        await conv_loop._synthesize_response("This is a test response")
        logger.info("✅ TTS synthesis test passed")
        
        # Test state management
        logger.info("Testing state management...")
        assert conv_loop.state == ConversationState.LISTENING, "Should be in listening state"
        logger.info("✅ State management test passed")
        
        # Test statistics
        logger.info("Testing statistics...")
        stats = conv_loop.get_stats()
        assert 'conversation_turns' in stats, "Stats should include conversation turns"
        assert 'stt_requests' in stats, "Stats should include STT requests"
        assert 'llm_requests' in stats, "Stats should include LLM requests"
        assert 'tts_requests' in stats, "Stats should include TTS requests"
        logger.info("✅ Statistics test passed")
        
        # Test stop
        logger.info("Testing conversation loop stop...")
        await conv_loop.stop()
        assert not conv_loop.is_running, "Conversation loop should not be running"
        logger.info("✅ Conversation loop stop test passed")
        
        logger.info("🎉 All AI Provider Integration tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ AI Provider Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_error_handling():
    """Test error handling in AI provider integration."""
    logger.info("Testing Error Handling")
    
    try:
        # Create mock session
        session_config = CallSessionConfig()
        session = CallSession("test-call-error", "user123", "agent", session_config)
        
        # Create conversation config
        conv_config = ConversationConfig(
            openai_api_key="test-key",
            system_prompt="You are a helpful test assistant."
        )
        
        # Create conversation loop
        conv_loop = ConversationLoop(session, conv_config)
        
        # Test with missing AI providers
        logger.info("Testing missing AI providers...")
        conv_loop.stt_handler = None
        conv_loop.llm_handler = None
        conv_loop.tts_handler = None
        
        # Test speech processing with missing handlers
        await conv_loop._process_speech()
        logger.info("✅ Missing handlers error handling test passed")
        
        # Test response generation with missing handlers
        await conv_loop._generate_response("test")
        logger.info("✅ Missing LLM handler error handling test passed")
        
        # Test TTS synthesis with missing handler
        await conv_loop._synthesize_response("test")
        logger.info("✅ Missing TTS handler error handling test passed")
        
        logger.info("🎉 All Error Handling tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error Handling test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_callback_integration():
    """Test callback integration with AI providers."""
    logger.info("Testing Callback Integration")
    
    try:
        # Create mock session
        session_config = CallSessionConfig()
        session = CallSession("test-call-callbacks", "user123", "agent", session_config)
        
        # Create conversation config with callbacks
        callback_calls = []
        
        def on_user_speech(text):
            callback_calls.append(f"user_speech: {text}")
        
        def on_ai_response(text):
            callback_calls.append(f"ai_response: {text}")
        
        def on_state_change(state):
            callback_calls.append(f"state_change: {state.value}")
        
        conv_config = ConversationConfig(
            openai_api_key="test-key",
            system_prompt="You are a helpful test assistant.",
            on_user_speech=on_user_speech,
            on_ai_response=on_ai_response,
            on_state_change=on_state_change
        )
        
        # Create conversation loop
        conv_loop = ConversationLoop(session, conv_config)
        
        # Mock the AI providers
        conv_loop.realtime_client = MockRealtimeClient(RealtimeConfig(api_key="test"))
        conv_loop.stt_handler = MockSTTHandler(STTConfig(), conv_loop.realtime_client)
        conv_loop.llm_handler = MockLLMHandler(LLMConfig(), conv_loop.realtime_client)
        conv_loop.tts_handler = MockTTSHandler(TTSConfig(), conv_loop.realtime_client)
        
        # Setup callbacks
        conv_loop._setup_callbacks()
        
        # Test callback execution
        logger.info("Testing callback execution...")
        
        # Test STT callbacks
        conv_loop._on_transcript("test transcript", True)
        conv_loop._on_speech_start()
        conv_loop._on_speech_end()
        
        # Test LLM callbacks
        conv_loop._on_response_start()
        conv_loop._on_response_chunk("test chunk")
        conv_loop._on_response_complete("test response")
        
        # Test TTS callbacks
        conv_loop._on_tts_speech_start()
        conv_loop._on_audio_chunk(b"test audio")
        conv_loop._on_tts_speech_end()
        
        # Test state change callbacks
        conv_loop._update_state(ConversationState.PROCESSING)
        conv_loop._update_state(ConversationState.SPEAKING)
        
        # Verify callbacks were called
        assert len(callback_calls) > 0, "Callbacks should have been called"
        logger.info(f"Callbacks called: {callback_calls}")
        logger.info("✅ Callback integration test passed")
        
        logger.info("🎉 All Callback Integration tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Callback Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests."""
    logger.info("Starting AI Provider Integration Tests")
    
    tests = [
        ("AI Provider Integration", test_ai_provider_integration),
        ("Error Handling", test_error_handling),
        ("Callback Integration", test_callback_integration)
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
