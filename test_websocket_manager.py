#!/usr/bin/env python3
"""
Test script for WebSocket manager functionality.

This script tests the WebSocket manager module with various scenarios
and validates the connection and message handling.
"""

import sys
import os
import asyncio
import json
import logging
import time
from pathlib import Path
from typing import List, Dict, Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from providers.websocket_manager import (
    WebSocketManager,
    WebSocketPool,
    WebSocketConfig,
    WebSocketState,
    WebSocketMessage,
    MessageType
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MockWebSocketServer:
    """Mock WebSocket server for testing."""
    
    def __init__(self, port: int = 8765):
        self.port = port
        self.clients = []
        self.server = None
    
    async def start(self):
        """Start the mock server."""
        import websockets
        
        async def handle_client(websocket):
            self.clients.append(websocket)
            logger.info(f"Client connected: {websocket.remote_address}")
            
            try:
                async for message in websocket:
                    # Echo back the message
                    await websocket.send(message)
            except websockets.exceptions.ConnectionClosed:
                logger.info(f"Client disconnected: {websocket.remote_address}")
            finally:
                self.clients.remove(websocket)
        
        self.server = await websockets.serve(handle_client, "localhost", self.port)
        logger.info(f"Mock WebSocket server started on port {self.port}")
    
    async def stop(self):
        """Stop the mock server."""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            logger.info("Mock WebSocket server stopped")


async def test_websocket_manager_basic():
    """Test basic WebSocket manager functionality."""
    logger.info("Testing basic WebSocket manager functionality...")
    
    # Start mock server
    mock_server = MockWebSocketServer()
    await mock_server.start()
    
    try:
        # Create WebSocket manager
        config = WebSocketConfig(
            url="ws://localhost:8765",
            api_key="test-key",
            enable_logging=True,
            timeout=5.0
        )
        
        manager = WebSocketManager(config)
        
        # Test connection
        connected = await manager.connect()
        assert connected, "Failed to connect to WebSocket"
        assert manager.state == WebSocketState.CONNECTED, "Manager not in connected state"
        
        # Test sending messages
        message_id = await manager.send_text("Hello, WebSocket!")
        assert message_id is not None, "Failed to send text message"
        
        # Test sending control message
        control_data = {"command": "start", "params": {"mode": "test"}}
        control_id = await manager.send_control(control_data)
        assert control_id is not None, "Failed to send control message"
        
        # Test statistics
        stats = manager.get_stats()
        assert stats['messages_sent'] >= 2, "Message count not updated"
        assert stats['connection_attempts'] == 1, "Connection attempts not tracked"
        
        logger.info(f"  Sent {stats['messages_sent']} messages")
        logger.info(f"  Connection attempts: {stats['connection_attempts']}")
        
        # Test disconnection
        await manager.disconnect()
        assert manager.state == WebSocketState.DISCONNECTED, "Manager not disconnected"
        
        logger.info("✅ Basic WebSocket manager test completed successfully!")
        
    finally:
        await manager.close()
        await mock_server.stop()


async def test_websocket_manager_callbacks():
    """Test WebSocket manager callbacks."""
    logger.info("Testing WebSocket manager callbacks...")
    
    # Start mock server
    mock_server = MockWebSocketServer(8766)
    await mock_server.start()
    
    try:
        # Create WebSocket manager with callbacks
        config = WebSocketConfig(
            url="ws://localhost:8766",
            api_key="test-key",
            enable_logging=True,
            timeout=5.0
        )
        
        manager = WebSocketManager(config)
        
        # Set up callbacks
        connect_called = False
        disconnect_called = False
        message_received = False
        error_received = False
        
        def on_connect():
            nonlocal connect_called
            connect_called = True
            logger.info("  Connect callback triggered")
        
        def on_disconnect():
            nonlocal disconnect_called
            disconnect_called = True
            logger.info("  Disconnect callback triggered")
        
        def on_message(message: WebSocketMessage):
            nonlocal message_received
            message_received = True
            logger.info(f"  Message callback triggered: {message.message_type.value}")
        
        def on_error(message: str, error: Exception):
            nonlocal error_received
            error_received = True
            logger.info(f"  Error callback triggered: {message}")
        
        manager.on_connect = on_connect
        manager.on_disconnect = on_disconnect
        manager.on_message = on_message
        manager.on_error = on_error
        
        # Connect and test
        connected = await manager.connect()
        assert connected, "Failed to connect"
        
        # Wait a bit for callbacks
        await asyncio.sleep(0.1)
        assert connect_called, "Connect callback not called"
        
        # Send a message (will be echoed back)
        await manager.send_text("Test message")
        
        # Wait for message callback
        await asyncio.sleep(0.1)
        assert message_received, "Message callback not called"
        
        # Disconnect
        await manager.disconnect()
        await asyncio.sleep(0.1)
        assert disconnect_called, "Disconnect callback not called"
        
        logger.info("✅ WebSocket manager callbacks test completed successfully!")
        
    finally:
        await manager.close()
        await mock_server.stop()


async def test_websocket_manager_reconnection():
    """Test WebSocket manager reconnection functionality."""
    logger.info("Testing WebSocket manager reconnection...")
    
    # Start mock server
    mock_server = MockWebSocketServer(8767)
    await mock_server.start()
    
    try:
        # Create WebSocket manager with reconnection settings
        config = WebSocketConfig(
            url="ws://localhost:8767",
            api_key="test-key",
            enable_logging=True,
            timeout=5.0,
            max_reconnect_attempts=3,
            reconnect_delay=0.5
        )
        
        manager = WebSocketManager(config)
        
        # Connect initially
        connected = await manager.connect()
        assert connected, "Failed to connect initially"
        
        # Send a message
        await manager.send_text("Initial message")
        
        # Simulate connection loss by stopping server
        await mock_server.stop()
        await asyncio.sleep(0.1)
        
        # Try to send message (should trigger reconnection attempt)
        try:
            await manager.send_text("Message after disconnect")
        except Exception as e:
            logger.info(f"  Expected error after disconnect: {e}")
        
        # Restart server
        await mock_server.start()
        await asyncio.sleep(1.0)  # Wait for reconnection attempt
        
        # Check if reconnection was attempted
        stats = manager.get_stats()
        assert stats['reconnection_attempts'] > 0, "No reconnection attempts made"
        
        logger.info(f"  Reconnection attempts: {stats['reconnection_attempts']}")
        logger.info("✅ WebSocket manager reconnection test completed successfully!")
        
    finally:
        await manager.close()
        await mock_server.stop()


async def test_websocket_pool():
    """Test WebSocket pool functionality."""
    logger.info("Testing WebSocket pool...")
    
    # Start mock servers
    mock_server1 = MockWebSocketServer(8768)
    mock_server2 = MockWebSocketServer(8769)
    await mock_server1.start()
    await mock_server2.start()
    
    try:
        # Create WebSocket pool with multiple configurations
        configs = [
            WebSocketConfig(
                url="ws://localhost:8768",
                api_key="test-key-1",
                enable_logging=True,
                timeout=5.0
            ),
            WebSocketConfig(
                url="ws://localhost:8769",
                api_key="test-key-2",
                enable_logging=True,
                timeout=5.0
            )
        ]
        
        pool = WebSocketPool(configs, max_connections=5)
        
        # Create connections
        conn1_id = await pool.create_connection(configs[0], "connection-1")
        conn2_id = await pool.create_connection(configs[1], "connection-2")
        
        assert conn1_id == "connection-1", "Connection 1 ID mismatch"
        assert conn2_id == "connection-2", "Connection 2 ID mismatch"
        
        # Test getting connections
        conn1 = await pool.get_connection("connection-1")
        conn2 = await pool.get_connection("connection-2")
        any_conn = await pool.get_connection()
        
        assert conn1 is not None, "Connection 1 not found"
        assert conn2 is not None, "Connection 2 not found"
        assert any_conn is not None, "No connection available"
        
        # Test sending messages through pool
        message_id1 = await pool.send_message(MessageType.TEXT, "Message 1", "connection-1")
        message_id2 = await pool.send_message(MessageType.TEXT, "Message 2", "connection-2")
        message_id3 = await pool.send_message(MessageType.TEXT, "Message 3")  # Any connection
        
        assert message_id1 is not None, "Failed to send message to connection 1"
        assert message_id2 is not None, "Failed to send message to connection 2"
        assert message_id3 is not None, "Failed to send message to any connection"
        
        # Test pool statistics
        pool_stats = pool.get_stats()
        assert pool_stats['total_connections'] == 2, "Total connections mismatch"
        assert pool_stats['active_connections'] == 2, "Active connections mismatch"
        assert pool_stats['messages_routed'] >= 3, "Messages routed mismatch"
        
        logger.info(f"  Total connections: {pool_stats['total_connections']}")
        logger.info(f"  Active connections: {pool_stats['active_connections']}")
        logger.info(f"  Messages routed: {pool_stats['messages_routed']}")
        
        # Test closing all connections
        await pool.close_all()
        
        # Verify connections are closed
        conn1_after = await pool.get_connection("connection-1")
        conn2_after = await pool.get_connection("connection-2")
        
        assert conn1_after is None, "Connection 1 not closed"
        assert conn2_after is None, "Connection 2 not closed"
        
        logger.info("✅ WebSocket pool test completed successfully!")
        
    finally:
        await mock_server1.stop()
        await mock_server2.stop()


async def test_websocket_manager_audio():
    """Test WebSocket manager with audio data."""
    logger.info("Testing WebSocket manager with audio data...")
    
    # Start mock server
    mock_server = MockWebSocketServer(8770)
    await mock_server.start()
    
    try:
        # Create WebSocket manager
        config = WebSocketConfig(
            url="ws://localhost:8770",
            api_key="test-key",
            enable_logging=True,
            timeout=5.0,
            audio_format="pcm16",
            sample_rate=16000,
            channels=1
        )
        
        manager = WebSocketManager(config)
        
        # Set up audio callback
        audio_received = False
        
        def on_audio_data(data: bytes):
            nonlocal audio_received
            audio_received = True
            logger.info(f"  Audio data received: {len(data)} bytes")
        
        manager.on_audio_data = on_audio_data
        
        # Connect
        connected = await manager.connect()
        assert connected, "Failed to connect"
        
        # Generate test audio data (PCM16, 1 second)
        import numpy as np
        sample_rate = 16000
        duration = 1.0
        t = np.linspace(0, duration, int(sample_rate * duration))
        audio_signal = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        audio_data = (audio_signal * 32767).astype(np.int16).tobytes()
        
        # Send audio data
        message_id = await manager.send_audio(audio_data)
        assert message_id is not None, "Failed to send audio data"
        
        # Wait for audio callback
        await asyncio.sleep(0.1)
        assert audio_received, "Audio callback not triggered"
        
        # Test statistics
        stats = manager.get_stats()
        assert stats['messages_sent'] >= 1, "Audio message not counted"
        assert stats['bytes_sent'] > 0, "Audio bytes not counted"
        
        logger.info(f"  Audio data sent: {len(audio_data)} bytes")
        logger.info(f"  Messages sent: {stats['messages_sent']}")
        logger.info(f"  Bytes sent: {stats['bytes_sent']}")
        
        logger.info("✅ WebSocket manager audio test completed successfully!")
        
    finally:
        await manager.close()
        await mock_server.stop()


async def test_websocket_manager_error_handling():
    """Test WebSocket manager error handling."""
    logger.info("Testing WebSocket manager error handling...")
    
    # Create WebSocket manager with invalid URL
    config = WebSocketConfig(
        url="ws://localhost:9999",  # Non-existent server
        api_key="test-key",
        enable_logging=True,
        timeout=1.0,
        max_reconnect_attempts=1
    )
    
    manager = WebSocketManager(config)
    
    # Set up error callback
    error_received = False
    
    def on_error(message: str, error: Exception):
        nonlocal error_received
        error_received = True
        logger.info(f"  Error callback triggered: {message}")
    
    manager.on_error = on_error
    
    # Try to connect (should fail)
    connected = await manager.connect()
    assert not connected, "Connection should have failed"
    
    # Wait for error callback
    await asyncio.sleep(0.1)
    assert error_received, "Error callback not triggered"
    
    # Test statistics
    stats = manager.get_stats()
    assert stats['errors'] > 0, "Errors not counted"
    assert stats['connection_attempts'] > 0, "Connection attempts not counted"
    
    logger.info(f"  Connection attempts: {stats['connection_attempts']}")
    logger.info(f"  Errors: {stats['errors']}")
    
    await manager.close()
    
    logger.info("✅ WebSocket manager error handling test completed successfully!")


async def main():
    """Run all WebSocket manager tests."""
    logger.info("Starting WebSocket manager tests...")
    
    try:
        await test_websocket_manager_basic()
        await test_websocket_manager_callbacks()
        await test_websocket_manager_reconnection()
        await test_websocket_pool()
        await test_websocket_manager_audio()
        await test_websocket_manager_error_handling()
        
        logger.info("All WebSocket manager tests completed successfully!")
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
