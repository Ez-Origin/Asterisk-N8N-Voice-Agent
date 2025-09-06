#!/usr/bin/env python3
"""
Test script for OpenAI TTS Handler

This script tests the TTS handler functionality including
text synthesis, audio streaming, and voice management.
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
    TTSHandler, 
    TTSManager, 
    TTSConfig, 
    TTSState, 
    TTSResponse,
    AudioFormat,
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
    """Mock Realtime client for testing TTS handler."""
    
    def __init__(self):
        self.is_connected = True
        self.session_id = "mock_session_123"
        self.on_audio = None
        self.on_response_done = None
        self.on_error = None
        self.messages_sent = 0
        self.responses_created = 0
    
    async def initialize_session(self) -> bool:
        """Mock session initialization."""
        await asyncio.sleep(0.1)
        return True
    
    async def send_text_message(self, text: str) -> bool:
        """Mock text message sending."""
        self.messages_sent += 1
        logger.info(f"Mock text message sent: {text[:50]}...")
        return True
    
    async def create_response(self, modalities: list) -> bool:
        """Mock response creation."""
        self.responses_created += 1
        logger.info(f"Mock response created with modalities: {modalities}")
        return True
    
    async def cancel_response(self) -> bool:
        """Mock response cancellation."""
        logger.info("Mock response cancelled")
        return True


async def test_tts_handler_creation():
    """Test TTS handler creation and configuration."""
    logger.info("Testing TTS handler creation...")
    
    try:
        # Create mock client
        mock_client = MockRealtimeClient()
        
        # Create TTS config
        config = TTSConfig(
            voice=VoiceType.ALLOY,
            speed=1.0,
            pitch=1.0,
            volume=1.0,
            audio_format=AudioFormat.PCM_24KHZ,
            sample_rate=24000,
            enable_streaming=True
        )
        
        # Create TTS handler
        handler = TTSHandler(config, mock_client)
        
        # Verify initial state
        assert handler.state == TTSState.IDLE
        assert not handler.is_synthesizing()
        assert not handler.is_speaking()
        assert len(handler.get_audio_data()) == 0
        
        logger.info("✅ TTS handler creation test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ TTS handler creation test failed: {e}")
        return False


async def test_text_synthesis():
    """Test text synthesis functionality."""
    logger.info("Testing text synthesis...")
    
    try:
        # Create mock client
        mock_client = MockRealtimeClient()
        
        # Create TTS handler with callbacks
        audio_chunks = []
        speech_started = False
        speech_ended = False
        synthesis_complete = False
        
        def on_audio_chunk(audio_data: bytes):
            audio_chunks.append(audio_data)
            logger.info(f"Audio chunk received: {len(audio_data)} bytes")
        
        def on_speech_start():
            nonlocal speech_started
            speech_started = True
            logger.info("Speech started")
        
        def on_speech_end():
            nonlocal speech_ended
            speech_ended = True
            logger.info("Speech ended")
        
        def on_synthesis_complete(response_data: Dict[str, Any]):
            nonlocal synthesis_complete
            synthesis_complete = True
            logger.info("Synthesis completed")
        
        config = TTSConfig(
            on_audio_chunk=on_audio_chunk,
            on_speech_start=on_speech_start,
            on_speech_end=on_speech_end,
            on_synthesis_complete=on_synthesis_complete
        )
        
        handler = TTSHandler(config, mock_client)
        
        # Test text synthesis
        logger.info("Synthesizing text...")
        success = await handler.synthesize_text("Hello, this is a test of the TTS system.")
        assert success, "Text synthesis should succeed"
        assert handler.state == TTSState.PROCESSING
        assert handler.is_synthesizing()
        
        # Simulate audio chunks
        if handler.client.on_audio:
            await handler.client.on_audio(b"audio_chunk_1")
            await handler.client.on_audio(b"audio_chunk_2")
            await handler.client.on_audio(b"audio_chunk_3")
        
        # Simulate synthesis completion
        if handler.client.on_response_done:
            await handler.client.on_response_done({
                "modalities": ["audio"],
                "usage": {"total_tokens": 10}
            })
        
        # Check response was processed
        response = handler.get_current_response()
        assert response.is_complete
        assert response.text == "Hello, this is a test of the TTS system."
        assert len(response.audio_data) > 0
        assert response.duration_ms > 0
        
        # Check callbacks were called
        assert len(audio_chunks) > 0
        assert speech_started
        assert speech_ended
        assert synthesis_complete
        
        logger.info("✅ Text synthesis test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ Text synthesis test failed: {e}")
        return False


async def test_ssml_synthesis():
    """Test SSML synthesis functionality."""
    logger.info("Testing SSML synthesis...")
    
    try:
        # Create mock client
        mock_client = MockRealtimeClient()
        
        # Create TTS handler with SSML enabled
        config = TTSConfig(enable_ssml=True)
        handler = TTSHandler(config, mock_client)
        
        # Test SSML synthesis
        ssml_text = "<speak>Hello <emphasis>world</emphasis>, this is SSML.</speak>"
        success = await handler.synthesize_ssml(ssml_text)
        assert success, "SSML synthesis should succeed"
        
        # Test SSML synthesis with SSML disabled
        config_no_ssml = TTSConfig(enable_ssml=False)
        handler_no_ssml = TTSHandler(config_no_ssml, mock_client)
        success = await handler_no_ssml.synthesize_ssml(ssml_text)
        assert not success, "SSML synthesis should fail when disabled"
        
        logger.info("✅ SSML synthesis test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ SSML synthesis test failed: {e}")
        return False


async def test_state_management():
    """Test TTS state management."""
    logger.info("Testing TTS state management...")
    
    try:
        # Create mock client
        mock_client = MockRealtimeClient()
        
        # Create TTS handler
        config = TTSConfig()
        handler = TTSHandler(config, mock_client)
        
        # Test initial state
        assert handler.state == TTSState.IDLE
        assert not handler.is_synthesizing()
        assert not handler.is_speaking()
        
        # Test synthesis start
        await handler.synthesize_text("Test message")
        assert handler.state == TTSState.PROCESSING
        assert handler.is_synthesizing()
        
        # Test stop synthesis
        await handler.stop_synthesis()
        assert handler.state == TTSState.IDLE
        assert not handler.is_synthesizing()
        
        # Test reset
        await handler.reset()
        assert handler.state == TTSState.IDLE
        assert not handler.is_synthesizing()
        assert not handler.is_speaking()
        
        logger.info("✅ TTS state management test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ TTS state management test failed: {e}")
        return False


async def test_voice_management():
    """Test voice management functionality."""
    logger.info("Testing voice management...")
    
    try:
        # Create mock client
        mock_client = MockRealtimeClient()
        
        # Test different voice types
        voices = [VoiceType.ALLOY, VoiceType.ECHO, VoiceType.FABLE, VoiceType.ONYX, VoiceType.NOVA, VoiceType.SHIMER]
        
        for voice in voices:
            config = TTSConfig(voice=voice)
            handler = TTSHandler(config, mock_client)
            
            # Test synthesis with different voice
            success = await handler.synthesize_text(f"Testing voice {voice.value}")
            assert success, f"Synthesis should succeed with voice {voice.value}"
            
            # Check voice was set correctly
            assert handler.config.voice == voice
        
        logger.info("✅ Voice management test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ Voice management test failed: {e}")
        return False


async def test_audio_formats():
    """Test different audio formats."""
    logger.info("Testing audio formats...")
    
    try:
        # Create mock client
        mock_client = MockRealtimeClient()
        
        # Test different audio formats
        formats = [
            AudioFormat.PCM_16KHZ,
            AudioFormat.PCM_24KHZ,
            AudioFormat.MP3_64K,
            AudioFormat.MP3_128K,
            AudioFormat.OPUS_64K,
            AudioFormat.OPUS_128K
        ]
        
        for audio_format in formats:
            config = TTSConfig(audio_format=audio_format)
            handler = TTSHandler(config, mock_client)
            
            # Test synthesis with different format
            success = await handler.synthesize_text(f"Testing format {audio_format.value}")
            assert success, f"Synthesis should succeed with format {audio_format.value}"
            
            # Check format was set correctly
            assert handler.config.audio_format == audio_format
        
        logger.info("✅ Audio formats test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ Audio formats test failed: {e}")
        return False


async def test_statistics():
    """Test TTS statistics tracking."""
    logger.info("Testing TTS statistics...")
    
    try:
        # Create mock client
        mock_client = MockRealtimeClient()
        
        # Create TTS handler
        config = TTSConfig()
        handler = TTSHandler(config, mock_client)
        
        # Get initial stats
        initial_stats = handler.get_stats()
        assert initial_stats['texts_processed'] == 0
        assert initial_stats['syntheses_completed'] == 0
        assert initial_stats['audio_chunks_received'] == 0
        assert initial_stats['total_audio_bytes'] == 0
        
        # Process some synthesis
        await handler.synthesize_text("Test message 1")
        await handler.synthesize_text("Test message 2")
        
        # Simulate audio chunks
        if handler.client.on_audio:
            await handler.client.on_audio(b"chunk1")
            await handler.client.on_audio(b"chunk2")
        
        # Simulate synthesis completion
        if handler.client.on_response_done:
            await handler.client.on_response_done({"modalities": ["audio"]})
        
        # Check updated stats
        final_stats = handler.get_stats()
        assert final_stats['texts_processed'] == 2
        assert final_stats['audio_chunks_received'] == 2
        assert final_stats['total_audio_bytes'] == 12  # len("chunk1") + len("chunk2")
        
        logger.info("✅ TTS statistics test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ TTS statistics test failed: {e}")
        return False


async def test_tts_manager():
    """Test TTS manager functionality."""
    logger.info("Testing TTS manager...")
    
    try:
        # Create TTS manager
        manager = TTSManager()
        
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
        assert stats['speaking_handlers'] == 0
        
        logger.info("✅ TTS manager test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ TTS manager test failed: {e}")
        return False


async def test_error_handling():
    """Test TTS error handling."""
    logger.info("Testing TTS error handling...")
    
    try:
        # Create mock client that fails
        class FailingMockClient:
            def __init__(self):
                self.is_connected = False
                self.session_id = None
            
            async def initialize_session(self) -> bool:
                return False
            
            async def send_text_message(self, text: str) -> bool:
                return False
            
            async def create_response(self, modalities: list) -> bool:
                return False
        
        failing_client = FailingMockClient()
        
        # Create TTS handler with error callbacks
        errors_received = []
        
        def on_error(message: str, error: Exception):
            errors_received.append((message, error))
            logger.info(f"Error received: {message}")
        
        config = TTSConfig(on_error=on_error)
        handler = TTSHandler(config, failing_client)
        
        # Test synthesis with failing client
        success = await handler.synthesize_text("Test message")
        assert not success, "Synthesis should fail with disconnected client"
        
        # Test stop synthesis when not processing
        success = await handler.stop_synthesis()
        assert not success, "Stop synthesis should fail when not processing"
        
        logger.info("✅ TTS error handling test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ TTS error handling test failed: {e}")
        return False


async def main():
    """Run all TTS handler tests."""
    logger.info("Starting TTS Handler tests...")
    
    tests = [
        ("TTS Handler Creation", test_tts_handler_creation),
        ("Text Synthesis", test_text_synthesis),
        ("SSML Synthesis", test_ssml_synthesis),
        ("State Management", test_state_management),
        ("Voice Management", test_voice_management),
        ("Audio Formats", test_audio_formats),
        ("Statistics", test_statistics),
        ("TTS Manager", test_tts_manager),
        ("Error Handling", test_error_handling)
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
        logger.info("🎉 All TTS handler tests passed!")
        return True
    else:
        logger.error(f"❌ {total - passed} tests failed")
        return False


if __name__ == "__main__":
    # Run the tests
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
