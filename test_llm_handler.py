#!/usr/bin/env python3
"""
Test script for OpenAI LLM Handler

This script tests the LLM handler functionality including
conversation management, response generation, and streaming.
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
    LLMHandler, 
    LLMManager, 
    LLMConfig, 
    LLMState, 
    LLMResponse,
    ResponseType,
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
    """Mock Realtime client for testing LLM handler."""
    
    def __init__(self):
        self.is_connected = True
        self.session_id = "mock_session_123"
        self.on_transcript = None
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


async def test_llm_handler_creation():
    """Test LLM handler creation and configuration."""
    logger.info("Testing LLM handler creation...")
    
    try:
        # Create mock client
        mock_client = MockRealtimeClient()
        
        # Create LLM config
        config = LLMConfig(
            model="gpt-4o-realtime-preview-2024-10-01",
            temperature=0.7,
            max_tokens=2048,
            enable_streaming=True,
            enable_audio_response=True,
            enable_text_response=True
        )
        
        # Create LLM handler
        handler = LLMHandler(config, mock_client)
        
        # Verify initial state
        assert handler.state == LLMState.IDLE
        assert not handler.is_processing()
        assert not handler.is_responding()
        assert len(handler.get_conversation_history()) == 0
        assert handler.get_current_response().text == ""
        
        logger.info("✅ LLM handler creation test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ LLM handler creation test failed: {e}")
        return False


async def test_conversation_management():
    """Test conversation management functionality."""
    logger.info("Testing conversation management...")
    
    try:
        # Create mock client
        mock_client = MockRealtimeClient()
        
        # Create LLM handler
        config = LLMConfig(system_instructions="You are a helpful test assistant.")
        handler = LLMHandler(config, mock_client)
        
        # Test start conversation
        logger.info("Starting conversation...")
        success = await handler.start_conversation("test_conv_1")
        assert success, "Start conversation should succeed"
        assert handler.current_conversation_id == "test_conv_1"
        
        # Check system message was added
        history = handler.get_conversation_history()
        assert len(history) == 1
        assert history[0]["role"] == "system"
        assert history[0]["content"] == "You are a helpful test assistant."
        
        # Test send message
        logger.info("Sending user message...")
        success = await handler.send_message("Hello, how are you?")
        assert success, "Send message should succeed"
        
        # Check message was added to history
        history = handler.get_conversation_history()
        assert len(history) == 2
        assert history[1]["role"] == "user"
        assert history[1]["content"] == "Hello, how are you?"
        
        # Test clear conversation
        logger.info("Clearing conversation...")
        handler.clear_conversation()
        history = handler.get_conversation_history()
        assert len(history) == 1  # Only system message should remain
        assert history[0]["role"] == "system"
        
        logger.info("✅ Conversation management test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ Conversation management test failed: {e}")
        return False


async def test_response_generation():
    """Test response generation functionality."""
    logger.info("Testing response generation...")
    
    try:
        # Create mock client
        mock_client = MockRealtimeClient()
        
        # Create LLM handler with callbacks
        text_chunks = []
        audio_chunks = []
        response_complete = False
        
        def on_text_chunk(text: str):
            text_chunks.append(text)
            logger.info(f"Text chunk received: {text}")
        
        def on_audio_chunk(audio_data: bytes):
            audio_chunks.append(audio_data)
            logger.info(f"Audio chunk received: {len(audio_data)} bytes")
        
        def on_response_complete(response_data: Dict[str, Any]):
            nonlocal response_complete
            response_complete = True
            logger.info("Response completed")
        
        config = LLMConfig(
            on_text_chunk=on_text_chunk,
            on_audio_chunk=on_audio_chunk,
            on_response_complete=on_response_complete
        )
        
        handler = LLMHandler(config, mock_client)
        
        # Start conversation
        await handler.start_conversation()
        
        # Send message
        await handler.send_message("Tell me a short story")
        
        # Create response
        logger.info("Creating response...")
        success = await handler.create_response(["text", "audio"])
        assert success, "Create response should succeed"
        assert handler.state == LLMState.PROCESSING
        assert handler.is_responding()
        
        # Simulate text chunks
        if handler.client.on_transcript:
            await handler.client.on_transcript("Once upon a time, ")
            await handler.client.on_transcript("there was a brave knight. ")
            await handler.client.on_transcript("The end.")
        
        # Simulate audio chunks
        if handler.client.on_audio:
            await handler.client.on_audio(b"audio_chunk_1")
            await handler.client.on_audio(b"audio_chunk_2")
        
        # Simulate response completion
        if handler.client.on_response_done:
            await handler.client.on_response_done({
                "usage": {"total_tokens": 25},
                "modalities": ["text", "audio"]
            })
        
        # Check response was processed
        response = handler.get_current_response()
        assert response.is_complete
        assert response.text == "Once upon a time, there was a brave knight. The end."
        assert len(response.audio_data) > 0
        assert response.tokens_used == 25
        
        # Check callbacks were called
        assert len(text_chunks) > 0
        assert len(audio_chunks) > 0
        assert response_complete
        
        logger.info("✅ Response generation test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ Response generation test failed: {e}")
        return False


async def test_state_management():
    """Test LLM state management."""
    logger.info("Testing LLM state management...")
    
    try:
        # Create mock client
        mock_client = MockRealtimeClient()
        
        # Create LLM handler
        config = LLMConfig()
        handler = LLMHandler(config, mock_client)
        
        # Test initial state
        assert handler.state == LLMState.IDLE
        assert not handler.is_processing()
        assert not handler.is_responding()
        
        # Test start conversation
        await handler.start_conversation()
        assert handler.state == LLMState.IDLE  # Should remain IDLE after conversation start
        
        # Test create response
        await handler.create_response()
        assert handler.state == LLMState.PROCESSING
        assert handler.is_responding()
        
        # Test cancel response
        await handler.cancel_response()
        assert handler.state == LLMState.IDLE
        assert not handler.is_responding()
        
        # Test reset
        await handler.reset()
        assert handler.state == LLMState.IDLE
        assert not handler.is_processing()
        assert not handler.is_responding()
        assert len(handler.get_conversation_history()) == 0
        
        logger.info("✅ LLM state management test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ LLM state management test failed: {e}")
        return False


async def test_conversation_context():
    """Test conversation context management."""
    logger.info("Testing conversation context management...")
    
    try:
        # Create mock client
        mock_client = MockRealtimeClient()
        
        # Create LLM handler with small context limit
        config = LLMConfig(max_context_length=3)
        handler = LLMHandler(config, mock_client)
        
        # Start conversation
        await handler.start_conversation()
        
        # Add multiple messages
        for i in range(5):
            await handler.send_message(f"Message {i}")
        
        # Check context was trimmed
        history = handler.get_conversation_history()
        # Should have system message + 2 recent messages (max_context_length - 1)
        assert len(history) == 3
        assert history[0]["role"] == "system"  # System message preserved
        assert history[1]["content"] == "Message 3"  # Recent messages
        assert history[2]["content"] == "Message 4"
        
        logger.info("✅ Conversation context test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ Conversation context test failed: {e}")
        return False


async def test_statistics():
    """Test LLM statistics tracking."""
    logger.info("Testing LLM statistics...")
    
    try:
        # Create mock client
        mock_client = MockRealtimeClient()
        
        # Create LLM handler
        config = LLMConfig()
        handler = LLMHandler(config, mock_client)
        
        # Get initial stats
        initial_stats = handler.get_stats()
        assert initial_stats['requests_processed'] == 0
        assert initial_stats['responses_completed'] == 0
        assert initial_stats['text_chunks_received'] == 0
        assert initial_stats['audio_chunks_received'] == 0
        assert initial_stats['total_tokens_used'] == 0
        
        # Process some requests
        await handler.start_conversation()
        await handler.send_message("Test message 1")
        await handler.send_message("Test message 2")
        await handler.create_response()
        
        # Simulate response completion
        if handler.client.on_response_done:
            await handler.client.on_response_done({
                "usage": {"total_tokens": 50}
            })
        
        # Check updated stats
        final_stats = handler.get_stats()
        assert final_stats['requests_processed'] == 2
        assert final_stats['responses_completed'] == 1
        assert final_stats['total_tokens_used'] == 50
        assert final_stats['conversations_started'] == 1
        
        logger.info("✅ LLM statistics test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ LLM statistics test failed: {e}")
        return False


async def test_llm_manager():
    """Test LLM manager functionality."""
    logger.info("Testing LLM manager...")
    
    try:
        # Create LLM manager
        manager = LLMManager()
        
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
        assert stats['responding_handlers'] == 0
        
        logger.info("✅ LLM manager test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ LLM manager test failed: {e}")
        return False


async def test_error_handling():
    """Test LLM error handling."""
    logger.info("Testing LLM error handling...")
    
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
        
        # Create LLM handler with error callbacks
        errors_received = []
        
        def on_error(message: str, error: Exception):
            errors_received.append((message, error))
            logger.info(f"Error received: {message}")
        
        config = LLMConfig(on_error=on_error)
        handler = LLMHandler(config, failing_client)
        
        # Test start conversation with failing client
        success = await handler.start_conversation()
        assert not success, "Start conversation should fail with disconnected client"
        
        # Test send message when not connected
        success = await handler.send_message("Test message")
        assert not success, "Send message should fail when not connected"
        
        # Test create response when not connected
        success = await handler.create_response()
        assert not success, "Create response should fail when not connected"
        
        logger.info("✅ LLM error handling test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ LLM error handling test failed: {e}")
        return False


async def main():
    """Run all LLM handler tests."""
    logger.info("Starting LLM Handler tests...")
    
    tests = [
        ("LLM Handler Creation", test_llm_handler_creation),
        ("Conversation Management", test_conversation_management),
        ("Response Generation", test_response_generation),
        ("State Management", test_state_management),
        ("Conversation Context", test_conversation_context),
        ("Statistics", test_statistics),
        ("LLM Manager", test_llm_manager),
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
        logger.info("🎉 All LLM handler tests passed!")
        return True
    else:
        logger.error(f"❌ {total - passed} tests failed")
        return False


if __name__ == "__main__":
    # Run the tests
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
