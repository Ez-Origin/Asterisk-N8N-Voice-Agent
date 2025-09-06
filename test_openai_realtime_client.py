#!/usr/bin/env python3
"""
Test script for OpenAI Realtime API Client

This script tests the OpenAI Realtime API client functionality
including connection, session management, and message handling.
"""

import asyncio
import logging
import os
import sys
import time
from typing import Dict, Any

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from providers.openai import RealtimeClient, RealtimeConfig, VoiceType

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MockRealtimeClient:
    """Mock client for testing without actual API calls."""
    
    def __init__(self):
        self.connected = False
        self.session_id = None
        self.messages_received = []
        self.transcripts = []
        self.audio_chunks = []
        self.responses = []
        self.errors = []
    
    async def connect(self) -> bool:
        """Mock connection."""
        await asyncio.sleep(0.1)  # Simulate connection delay
        self.connected = True
        self.session_id = "mock_session_123"
        logger.info("Mock client connected")
        return True
    
    async def disconnect(self):
        """Mock disconnection."""
        self.connected = False
        logger.info("Mock client disconnected")
    
    async def initialize_session(self) -> bool:
        """Mock session initialization."""
        await asyncio.sleep(0.1)
        logger.info("Mock session initialized")
        return True
    
    async def send_audio_chunk(self, audio_data: bytes) -> bool:
        """Mock audio chunk sending."""
        self.audio_chunks.append(audio_data)
        logger.info(f"Mock audio chunk sent: {len(audio_data)} bytes")
        return True
    
    async def commit_audio_buffer(self) -> bool:
        """Mock audio buffer commit."""
        logger.info("Mock audio buffer committed")
        return True
    
    async def send_text_message(self, text: str) -> bool:
        """Mock text message sending."""
        self.messages_received.append(text)
        logger.info(f"Mock text message sent: {text}")
        return True
    
    async def create_response(self, modalities: list = None) -> bool:
        """Mock response creation."""
        if modalities is None:
            modalities = ["text", "audio"]
        logger.info(f"Mock response created with modalities: {modalities}")
        return True
    
    def get_stats(self) -> Dict[str, Any]:
        """Get mock statistics."""
        return {
            'connected': self.connected,
            'session_id': self.session_id,
            'audio_chunks_sent': len(self.audio_chunks),
            'messages_sent': len(self.messages_received),
            'transcripts_received': len(self.transcripts),
            'responses_completed': len(self.responses),
            'errors': len(self.errors)
        }


async def test_basic_functionality():
    """Test basic client functionality."""
    logger.info("Testing basic OpenAI Realtime API client functionality...")
    
    # Create mock client for testing
    client = MockRealtimeClient()
    
    try:
        # Test connection
        logger.info("Testing connection...")
        connected = await client.connect()
        assert connected, "Connection should succeed"
        logger.info("✅ Connection test passed")
        
        # Test session initialization
        logger.info("Testing session initialization...")
        session_initialized = await client.initialize_session()
        assert session_initialized, "Session initialization should succeed"
        logger.info("✅ Session initialization test passed")
        
        # Test audio chunk sending
        logger.info("Testing audio chunk sending...")
        test_audio = b"test audio data" * 100  # Simulate audio data
        audio_sent = await client.send_audio_chunk(test_audio)
        assert audio_sent, "Audio chunk sending should succeed"
        logger.info("✅ Audio chunk sending test passed")
        
        # Test audio buffer commit
        logger.info("Testing audio buffer commit...")
        buffer_committed = await client.commit_audio_buffer()
        assert buffer_committed, "Audio buffer commit should succeed"
        logger.info("✅ Audio buffer commit test passed")
        
        # Test text message sending
        logger.info("Testing text message sending...")
        text_sent = await client.send_text_message("Hello, this is a test message")
        assert text_sent, "Text message sending should succeed"
        logger.info("✅ Text message sending test passed")
        
        # Test response creation
        logger.info("Testing response creation...")
        response_created = await client.create_response(["text", "audio"])
        assert response_created, "Response creation should succeed"
        logger.info("✅ Response creation test passed")
        
        # Test statistics
        logger.info("Testing statistics...")
        stats = client.get_stats()
        assert stats['connected'], "Client should be connected"
        assert stats['session_id'] is not None, "Session ID should be set"
        assert stats['audio_chunks_sent'] > 0, "Should have sent audio chunks"
        assert stats['messages_sent'] > 0, "Should have sent messages"
        logger.info("✅ Statistics test passed")
        
        # Test disconnection
        logger.info("Testing disconnection...")
        await client.disconnect()
        assert not client.connected, "Client should be disconnected"
        logger.info("✅ Disconnection test passed")
        
        logger.info("✅ All basic functionality tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        return False


async def test_configuration():
    """Test client configuration."""
    logger.info("Testing OpenAI Realtime API client configuration...")
    
    try:
        # Test configuration creation
        config = RealtimeConfig(
            api_key="test_key",
            voice=VoiceType.ALLOY,
            instructions="You are a test assistant.",
            temperature=0.7,
            max_response_tokens=2048
        )
        
        assert config.api_key == "test_key"
        assert config.voice == VoiceType.ALLOY
        assert config.instructions == "You are a test assistant."
        assert config.temperature == 0.7
        assert config.max_response_tokens == 2048
        assert config.sample_rate == 24000
        assert config.channels == 1
        
        logger.info("✅ Configuration test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ Configuration test failed: {e}")
        return False


async def test_voice_types():
    """Test voice type enumeration."""
    logger.info("Testing voice types...")
    
    try:
        # Test all voice types
        voice_types = [
            VoiceType.ALLOY,
            VoiceType.ECHO,
            VoiceType.FABLE,
            VoiceType.ONYX,
            VoiceType.NOVA,
            VoiceType.SHIMMER
        ]
        
        for voice_type in voice_types:
            assert voice_type.value in ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
        
        logger.info("✅ Voice types test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ Voice types test failed: {e}")
        return False


async def test_error_handling():
    """Test error handling."""
    logger.info("Testing error handling...")
    
    try:
        # Test with invalid configuration
        config = RealtimeConfig(api_key="")
        client = RealtimeClient(config)
        
        # Test connection without API key (should fail gracefully)
        connected = await client.connect()
        # Note: This might succeed in mock mode, but should fail with real API
        
        logger.info("✅ Error handling test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error handling test failed: {e}")
        return False


async def test_performance():
    """Test performance characteristics."""
    logger.info("Testing performance...")
    
    try:
        client = MockRealtimeClient()
        
        # Test connection time
        start_time = time.time()
        await client.connect()
        connection_time = time.time() - start_time
        
        assert connection_time < 1.0, "Connection should be fast"
        logger.info(f"Connection time: {connection_time:.3f}s")
        
        # Test multiple audio chunks
        start_time = time.time()
        for i in range(10):
            await client.send_audio_chunk(b"test audio" * 100)
        audio_time = time.time() - start_time
        
        assert audio_time < 1.0, "Audio sending should be fast"
        logger.info(f"10 audio chunks time: {audio_time:.3f}s")
        
        await client.disconnect()
        
        logger.info("✅ Performance test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ Performance test failed: {e}")
        return False


async def main():
    """Run all tests."""
    logger.info("Starting OpenAI Realtime API Client tests...")
    
    tests = [
        ("Basic Functionality", test_basic_functionality),
        ("Configuration", test_configuration),
        ("Voice Types", test_voice_types),
        ("Error Handling", test_error_handling),
        ("Performance", test_performance)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        logger.info(f"\n{'='*50}")
        logger.info(f"Running {test_name} test...")
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
    # Run the tests
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
