#!/usr/bin/env python3
"""
Test script for OpenAI STT Handler

This script tests the STT handler functionality including
audio processing, transcript handling, and state management.
"""

import asyncio
import logging
import os
import sys
import time
from typing import Dict, Any

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from providers.openai import (
    STTHandler, 
    STTManager, 
    STTConfig, 
    STTState, 
    TranscriptResult,
    RealtimeClient,
    RealtimeConfig,
    VoiceType
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MockRealtimeClient:
    """Mock Realtime client for testing STT handler."""
    
    def __init__(self):
        self.is_connected = True
        self.session_id = "mock_session_123"
        self.on_transcript = None
        self.on_error = None
        self.audio_chunks_sent = 0
        self.messages_sent = 0
    
    async def initialize_session(self) -> bool:
        """Mock session initialization."""
        await asyncio.sleep(0.1)
        return True
    
    async def send_audio_chunk(self, audio_data: bytes) -> bool:
        """Mock audio chunk sending."""
        self.audio_chunks_sent += 1
        logger.info(f"Mock audio chunk sent: {len(audio_data)} bytes")
        return True
    
    async def commit_audio_buffer(self) -> bool:
        """Mock audio buffer commit."""
        self.messages_sent += 1
        logger.info("Mock audio buffer committed")
        return True


async def test_stt_handler_creation():
    """Test STT handler creation and configuration."""
    logger.info("Testing STT handler creation...")
    
    try:
        # Create mock client
        mock_client = MockRealtimeClient()
        
        # Create STT config
        config = STTConfig(
            sample_rate=24000,
            chunk_duration_ms=20,
            enable_partial_transcripts=True,
            enable_final_transcripts=True
        )
        
        # Create STT handler
        handler = STTHandler(config, mock_client)
        
        # Verify initial state
        assert handler.state == STTState.IDLE
        assert not handler.is_listening()
        assert not handler.is_speaking_detected()
        assert handler.get_current_transcript() == ""
        assert handler.get_partial_transcript() == ""
        
        logger.info("✅ STT handler creation test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ STT handler creation test failed: {e}")
        return False


async def test_stt_listening_cycle():
    """Test the complete STT listening cycle."""
    logger.info("Testing STT listening cycle...")
    
    try:
        # Create mock client
        mock_client = MockRealtimeClient()
        
        # Create STT config with callbacks
        transcripts_received = []
        speech_events = []
        
        def on_transcript(text: str, is_final: bool):
            transcripts_received.append((text, is_final))
            logger.info(f"Transcript received: '{text}' (final: {is_final})")
        
        def on_speech_start():
            speech_events.append("start")
            logger.info("Speech started")
        
        def on_speech_end():
            speech_events.append("end")
            logger.info("Speech ended")
        
        config = STTConfig(
            on_transcript=on_transcript,
            on_speech_start=on_speech_start,
            on_speech_end=on_speech_end
        )
        
        # Create STT handler
        handler = STTHandler(config, mock_client)
        
        # Test start listening
        logger.info("Starting STT listening...")
        success = await handler.start_listening()
        assert success, "Start listening should succeed"
        assert handler.state == STTState.LISTENING
        assert handler.is_listening()
        
        # Test audio processing
        logger.info("Processing audio chunks...")
        test_audio_chunks = [
            b"audio_chunk_1" * 100,
            b"audio_chunk_2" * 100,
            b"audio_chunk_3" * 100
        ]
        
        for i, chunk in enumerate(test_audio_chunks):
            success = await handler.process_audio_chunk(chunk)
            assert success, f"Audio chunk {i+1} processing should succeed"
            await asyncio.sleep(0.01)  # Small delay between chunks
        
        # Simulate transcript callback
        if handler.client.on_transcript:
            await handler.client.on_transcript("Hello, this is a test transcript")
        
        # Test commit audio
        logger.info("Committing audio...")
        success = await handler.commit_audio()
        assert success, "Audio commit should succeed"
        
        # Test stop listening
        logger.info("Stopping STT listening...")
        success = await handler.stop_listening()
        assert success, "Stop listening should succeed"
        assert handler.state == STTState.IDLE
        assert not handler.is_listening()
        
        # Verify callbacks were called
        assert len(transcripts_received) > 0, "Transcript callbacks should be called"
        assert len(speech_events) > 0, "Speech event callbacks should be called"
        
        logger.info("✅ STT listening cycle test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ STT listening cycle test failed: {e}")
        return False


async def test_stt_audio_processing():
    """Test audio processing functionality."""
    logger.info("Testing STT audio processing...")
    
    try:
        # Create mock client
        mock_client = MockRealtimeClient()
        
        # Create STT handler
        config = STTConfig(chunk_duration_ms=20, max_audio_buffer_size=5)
        handler = STTHandler(config, mock_client)
        
        # Start listening
        await handler.start_listening()
        
        # Test audio chunk processing
        test_chunks = [b"test_audio_" + str(i).encode() for i in range(10)]
        
        for i, chunk in enumerate(test_chunks):
            success = await handler.process_audio_chunk(chunk)
            assert success, f"Audio chunk {i} should be processed successfully"
            
            # Check buffer size limit
            stats = handler.get_stats()
            assert stats['audio_buffer_size'] <= config.max_audio_buffer_size
        
        # Test empty audio data
        success = await handler.process_audio_chunk(b"")
        assert not success, "Empty audio data should be rejected"
        
        # Test None audio data
        success = await handler.process_audio_chunk(None)
        assert not success, "None audio data should be rejected"
        
        # Stop listening
        await handler.stop_listening()
        
        logger.info("✅ STT audio processing test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ STT audio processing test failed: {e}")
        return False


async def test_stt_state_management():
    """Test STT state management."""
    logger.info("Testing STT state management...")
    
    try:
        # Create mock client
        mock_client = MockRealtimeClient()
        
        # Create STT handler
        config = STTConfig()
        handler = STTHandler(config, mock_client)
        
        # Test initial state
        assert handler.state == STTState.IDLE
        assert not handler.is_listening()
        
        # Test start listening
        await handler.start_listening()
        assert handler.state == STTState.LISTENING
        assert handler.is_listening()
        
        # Test audio processing changes state
        await handler.process_audio_chunk(b"test_audio")
        assert handler.is_speaking_detected()
        
        # Test stop listening
        await handler.stop_listening()
        assert handler.state == STTState.IDLE
        assert not handler.is_listening()
        
        # Test reset
        await handler.reset()
        assert handler.state == STTState.IDLE
        assert not handler.is_speaking_detected()
        assert handler.get_current_transcript() == ""
        
        logger.info("✅ STT state management test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ STT state management test failed: {e}")
        return False


async def test_stt_statistics():
    """Test STT statistics tracking."""
    logger.info("Testing STT statistics...")
    
    try:
        # Create mock client
        mock_client = MockRealtimeClient()
        
        # Create STT handler
        config = STTConfig()
        handler = STTHandler(config, mock_client)
        
        # Get initial stats
        initial_stats = handler.get_stats()
        assert initial_stats['audio_chunks_processed'] == 0
        assert initial_stats['transcripts_received'] == 0
        assert initial_stats['speech_sessions'] == 0
        assert initial_stats['errors'] == 0
        
        # Process some audio
        await handler.start_listening()
        
        for i in range(5):
            await handler.process_audio_chunk(b"test_audio" * 100)
            await asyncio.sleep(0.01)
        
        await handler.stop_listening()
        
        # Check updated stats
        final_stats = handler.get_stats()
        assert final_stats['audio_chunks_processed'] == 5
        assert final_stats['speech_sessions'] == 1
        assert final_stats['total_audio_duration_ms'] > 0
        
        logger.info("✅ STT statistics test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ STT statistics test failed: {e}")
        return False


async def test_stt_manager():
    """Test STT manager functionality."""
    logger.info("Testing STT manager...")
    
    try:
        # Create STT manager
        manager = STTManager()
        
        # Create mock client
        mock_client = MockRealtimeClient()
        
        # Test creating handlers
        handler1 = manager.create_handler("handler1", realtime_client=mock_client)
        handler2 = manager.create_handler("handler2", realtime_client=mock_client)
        
        assert manager.get_handler("handler1") == handler1
        assert manager.get_handler("handler2") == handler2
        assert manager.get_handler("nonexistent") is None
        
        # Test getting all handlers
        all_handlers = manager.get_all_handlers()
        assert len(all_handlers) == 2
        assert "handler1" in all_handlers
        assert "handler2" in all_handlers
        
        # Test removing handler
        success = manager.remove_handler("handler1")
        assert success, "Handler removal should succeed"
        assert manager.get_handler("handler1") is None
        assert len(manager.get_all_handlers()) == 1
        
        # Test manager stats
        stats = manager.get_stats()
        assert stats['total_handlers'] == 1
        assert stats['active_handlers'] == 0
        
        logger.info("✅ STT manager test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ STT manager test failed: {e}")
        return False


async def test_stt_error_handling():
    """Test STT error handling."""
    logger.info("Testing STT error handling...")
    
    try:
        # Create mock client that fails
        class FailingMockClient:
            def __init__(self):
                self.is_connected = False
                self.session_id = None
            
            async def initialize_session(self) -> bool:
                return False
            
            async def send_audio_chunk(self, audio_data: bytes) -> bool:
                return False
        
        failing_client = FailingMockClient()
        
        # Create STT handler with error callbacks
        errors_received = []
        
        def on_error(message: str, error: Exception):
            errors_received.append((message, error))
            logger.info(f"Error received: {message}")
        
        config = STTConfig(on_error=on_error)
        handler = STTHandler(config, failing_client)
        
        # Test start listening with failing client
        success = await handler.start_listening()
        assert not success, "Start listening should fail with disconnected client"
        assert handler.state == STTState.ERROR
        
        # Test audio processing when not listening
        success = await handler.process_audio_chunk(b"test_audio")
        assert not success, "Audio processing should fail when not listening"
        
        # Test stop listening when not listening
        success = await handler.stop_listening()
        assert not success, "Stop listening should fail when not listening"
        
        logger.info("✅ STT error handling test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ STT error handling test failed: {e}")
        return False


async def main():
    """Run all STT handler tests."""
    logger.info("Starting STT Handler tests...")
    
    tests = [
        ("STT Handler Creation", test_stt_handler_creation),
        ("STT Listening Cycle", test_stt_listening_cycle),
        ("STT Audio Processing", test_stt_audio_processing),
        ("STT State Management", test_stt_state_management),
        ("STT Statistics", test_stt_statistics),
        ("STT Manager", test_stt_manager),
        ("STT Error Handling", test_stt_error_handling)
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
        logger.info("🎉 All STT handler tests passed!")
        return True
    else:
        logger.error(f"❌ {total - passed} tests failed")
        return False


if __name__ == "__main__":
    # Run the tests
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
