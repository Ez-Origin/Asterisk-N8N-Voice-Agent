"""
WebSocket Manager for AI Provider Communication.

This module provides a WebSocket manager for low-latency, real-time communication
with AI providers, starting with OpenAI Realtime API as MVP.
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Optional, Dict, Any, List, Callable, Union, Awaitable
from dataclasses import dataclass, field
from enum import Enum
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException
import aiohttp
from aiohttp import ClientSession, ClientWebSocketResponse
import ssl
from urllib.parse import urljoin, urlparse
import threading
from concurrent.futures import ThreadPoolExecutor
import base64

logger = logging.getLogger(__name__)


class WebSocketState(Enum):
    """WebSocket connection states."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"


class MessageType(Enum):
    """WebSocket message types."""
    AUDIO = "audio"
    TEXT = "text"
    CONTROL = "control"
    HEARTBEAT = "heartbeat"
    ERROR = "error"
    RESPONSE = "response"


@dataclass
class WebSocketConfig:
    """Configuration for WebSocket manager."""
    # Connection settings
    url: str
    api_key: str
    timeout: float = 30.0
    ping_interval: float = 20.0
    ping_timeout: float = 10.0
    
    # Reconnection settings
    max_reconnect_attempts: int = 5
    reconnect_delay: float = 1.0
    max_reconnect_delay: float = 60.0
    reconnect_backoff_factor: float = 2.0
    
    # Message settings
    max_message_size: int = 1024 * 1024  # 1MB
    message_queue_size: int = 1000
    
    # Security settings
    verify_ssl: bool = True
    custom_headers: Dict[str, str] = field(default_factory=dict)
    
    # Provider-specific settings
    provider: str = "openai"  # openai, azure, custom
    model: str = "gpt-4o-realtime-preview-2024-10-01"
    
    # Audio settings
    audio_format: str = "pcm16"  # pcm16, pcm24, flac, mp3
    sample_rate: int = 16000
    channels: int = 1
    
    # Debug settings
    enable_logging: bool = True
    log_level: str = "INFO"


@dataclass
class WebSocketMessage:
    """WebSocket message structure."""
    message_id: str
    message_type: MessageType
    data: Union[str, bytes, Dict[str, Any]]
    timestamp: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class WebSocketManager:
    """
    WebSocket manager for AI provider communication.
    
    This class provides:
    - Automatic connection management with reconnection
    - Message queuing and delivery
    - Audio and text data handling
    - Provider-specific protocol support
    - Connection pooling and health monitoring
    """
    
    def __init__(self, config: WebSocketConfig):
        """
        Initialize the WebSocket manager.
        
        Args:
            config: WebSocket configuration
        """
        self.config = config
        self.state = WebSocketState.DISCONNECTED
        self.websocket: Optional[ClientWebSocketResponse] = None
        self.session: Optional[ClientSession] = None
        
        # Message handling
        self.message_queue = asyncio.Queue(maxsize=config.message_queue_size)
        self.response_handlers: Dict[str, Callable[[WebSocketMessage], None]] = {}
        
        # Connection management
        self.reconnect_attempts = 0
        self.last_ping_time = 0.0
        self.last_pong_time = 0.0
        
        # Statistics
        self.stats = {
            'messages_sent': 0,
            'messages_received': 0,
            'bytes_sent': 0,
            'bytes_received': 0,
            'connection_attempts': 0,
            'reconnection_attempts': 0,
            'errors': 0,
            'last_connection_time': 0.0,
            'uptime': 0.0
        }
        
        # Event callbacks
        self.on_connect: Optional[Callable[[], None]] = None
        self.on_disconnect: Optional[Callable[[], None]] = None
        self.on_message: Optional[Callable[[WebSocketMessage], None]] = None
        self.on_error: Optional[Callable[[str, Exception], None]] = None
        self.on_audio_data: Optional[Callable[[bytes], None]] = None
        self.on_text_data: Optional[Callable[[str], None]] = None
        
        # Thread pool for blocking operations
        self.executor = ThreadPoolExecutor(max_workers=4)
        
        # Start time for uptime calculation
        self.start_time = time.time()
        
        if self.config.enable_logging:
            logger.info(f"WebSocket manager initialized for {self.config.provider} "
                       f"at {self.config.url}")
    
    async def connect(self) -> bool:
        """
        Establish WebSocket connection.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        if self.state == WebSocketState.CONNECTED:
            logger.warning("Already connected")
            return True
        
        self.state = WebSocketState.CONNECTING
        self.stats['connection_attempts'] += 1
        
        try:
            # Create SSL context if needed
            ssl_context = None
            if self.config.verify_ssl and self.config.url.startswith('wss://'):
                ssl_context = ssl.create_default_context()
            
            # Prepare headers
            headers = {
                'Authorization': f'Bearer {self.config.api_key}',
                'User-Agent': 'Asterisk-AI-Voice-Agent/1.0',
                'Content-Type': 'application/json',
                **self.config.custom_headers
            }
            
            # Create aiohttp session
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.config.timeout),
                connector=aiohttp.TCPConnector(ssl=ssl_context)
            )
            
            # Connect to WebSocket
            self.websocket = await self.session.ws_connect(
                self.config.url,
                headers=headers,
                heartbeat=self.config.ping_interval,
                max_msg_size=self.config.max_message_size
            )
            
            self.state = WebSocketState.CONNECTED
            self.reconnect_attempts = 0
            self.stats['last_connection_time'] = time.time()
            self.stats['uptime'] = time.time() - self.start_time
            
            if self.config.enable_logging:
                logger.info(f"WebSocket connected to {self.config.url}")
            
            # Start message handling loop
            asyncio.create_task(self._message_loop())
            asyncio.create_task(self._heartbeat_loop())
            
            # Call connect callback
            if self.on_connect:
                if asyncio.iscoroutinefunction(self.on_connect):
                    await self.on_connect()
                else:
                    self.on_connect()
            
            return True
            
        except Exception as e:
            self.state = WebSocketState.FAILED
            self.stats['errors'] += 1
            
            if self.config.enable_logging:
                logger.error(f"WebSocket connection failed: {e}")
            
            if self.on_error:
                if asyncio.iscoroutinefunction(self.on_error):
                    await self.on_error(f"Connection failed: {e}", e)
                else:
                    self.on_error(f"Connection failed: {e}", e)
            
            return False
    
    async def disconnect(self):
        """Disconnect from WebSocket."""
        if self.state == WebSocketState.DISCONNECTED:
            return
        
        self.state = WebSocketState.DISCONNECTED
        
        try:
            if self.websocket:
                await self.websocket.close()
                self.websocket = None
            
            if self.session:
                await self.session.close()
                self.session = None
            
            if self.config.enable_logging:
                logger.info("WebSocket disconnected")
            
            # Call disconnect callback
            if self.on_disconnect:
                if asyncio.iscoroutinefunction(self.on_disconnect):
                    await self.on_disconnect()
                else:
                    self.on_disconnect()
                    
        except Exception as e:
            if self.config.enable_logging:
                logger.error(f"Error during disconnect: {e}")
    
    async def send_message(self, message_type: MessageType, data: Union[str, bytes, Dict[str, Any]], 
                          message_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Send a message through the WebSocket.
        
        Args:
            message_type: Type of message to send
            data: Message data
            message_id: Optional message ID (generated if not provided)
            metadata: Optional message metadata
            
        Returns:
            str: Message ID
        """
        if self.state != WebSocketState.CONNECTED:
            raise ConnectionError("WebSocket not connected")
        
        if not self.websocket:
            raise ConnectionError("WebSocket connection not available")
        
        message_id = message_id or str(uuid.uuid4())
        timestamp = time.time()
        
        # Create message
        message = WebSocketMessage(
            message_id=message_id,
            message_type=message_type,
            data=data,
            timestamp=timestamp,
            metadata=metadata or {}
        )
        
        try:
            # Prepare message based on provider
            if self.config.provider == "openai":
                payload = self._prepare_openai_message(message)
            else:
                payload = self._prepare_generic_message(message)
            
            # Send message
            await self.websocket.send_str(json.dumps(payload))
            
            # Update statistics
            self.stats['messages_sent'] += 1
            self.stats['bytes_sent'] += len(json.dumps(payload).encode())
            
            if self.config.enable_logging:
                logger.debug(f"Sent message {message_id} of type {message_type.value}")
            
            return message_id
            
        except Exception as e:
            self.stats['errors'] += 1
            if self.config.enable_logging:
                logger.error(f"Failed to send message {message_id}: {e}")
            raise
    
    async def send_audio(self, audio_data: bytes, format: str = None) -> str:
        """
        Send audio data through the WebSocket.
        
        Args:
            audio_data: Audio data bytes
            format: Audio format (uses config default if not provided)
            
        Returns:
            str: Message ID
        """
        audio_format = format or self.config.audio_format
        
        # Encode audio data based on format
        if audio_format == "pcm16":
            # PCM16 is already in the correct format
            encoded_data = audio_data
        elif audio_format == "base64":
            # Encode as base64
            encoded_data = base64.b64encode(audio_data).decode()
        else:
            # For other formats, encode as base64
            encoded_data = base64.b64encode(audio_data).decode()
        
        metadata = {
            'format': audio_format,
            'sample_rate': self.config.sample_rate,
            'channels': self.config.channels,
            'size': len(audio_data)
        }
        
        return await self.send_message(MessageType.AUDIO, encoded_data, metadata=metadata)
    
    async def send_text(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Send text data through the WebSocket.
        
        Args:
            text: Text to send
            metadata: Optional metadata
            
        Returns:
            str: Message ID
        """
        return await self.send_message(MessageType.TEXT, text, metadata=metadata)
    
    async def send_control(self, control_data: Dict[str, Any]) -> str:
        """
        Send control message through the WebSocket.
        
        Args:
            control_data: Control data dictionary
            
        Returns:
            str: Message ID
        """
        return await self.send_message(MessageType.CONTROL, control_data)
    
    def _prepare_openai_message(self, message: WebSocketMessage) -> Dict[str, Any]:
        """Prepare message for OpenAI Realtime API format."""
        if message.message_type == MessageType.AUDIO:
            return {
                "type": "input_audio_buffer.append",
                "audio": message.data,
                "timestamp": message.timestamp
            }
        elif message.message_type == MessageType.TEXT:
            return {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": message.data}]
                },
                "timestamp": message.timestamp
            }
        elif message.message_type == MessageType.CONTROL:
            return {
                "type": "conversation.item.create",
                "item": message.data,
                "timestamp": message.timestamp
            }
        else:
            return {
                "type": "custom",
                "data": message.data,
                "timestamp": message.timestamp
            }
    
    def _prepare_generic_message(self, message: WebSocketMessage) -> Dict[str, Any]:
        """Prepare message for generic WebSocket format."""
        return {
            "id": message.message_id,
            "type": message.message_type.value,
            "data": message.data,
            "timestamp": message.timestamp,
            "metadata": message.metadata
        }
    
    async def _message_loop(self):
        """Main message handling loop."""
        while self.state == WebSocketState.CONNECTED and self.websocket:
            try:
                # Wait for message
                message = await self.websocket.receive()
                
                if message.type == aiohttp.WSMsgType.TEXT:
                    await self._handle_text_message(message.data)
                elif message.type == aiohttp.WSMsgType.BINARY:
                    await self._handle_binary_message(message.data)
                elif message.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {message.data}")
                    self.stats['errors'] += 1
                elif message.type == aiohttp.WSMsgType.CLOSE:
                    logger.info("WebSocket closed by server")
                    break
                    
            except ConnectionClosed:
                logger.info("WebSocket connection closed")
                break
            except Exception as e:
                logger.error(f"Error in message loop: {e}")
                self.stats['errors'] += 1
                await asyncio.sleep(1)
        
        # Attempt reconnection if not manually disconnected
        if self.state != WebSocketState.DISCONNECTED:
            await self._attempt_reconnection()
    
    async def _handle_text_message(self, data: str):
        """Handle incoming text message."""
        try:
            message_data = json.loads(data)
            
            # Update statistics
            self.stats['messages_received'] += 1
            self.stats['bytes_received'] += len(data.encode())
            
            # Parse message based on provider
            if self.config.provider == "openai":
                parsed_message = self._parse_openai_message(message_data)
            else:
                parsed_message = self._parse_generic_message(message_data)
            
            if parsed_message:
                # Call message callback
                if self.on_message:
                    if asyncio.iscoroutinefunction(self.on_message):
                        await self.on_message(parsed_message)
                    else:
                        self.on_message(parsed_message)
                
                # Call specific callbacks
                if parsed_message.message_type == MessageType.AUDIO and self.on_audio_data:
                    if isinstance(parsed_message.data, bytes):
                        if asyncio.iscoroutinefunction(self.on_audio_data):
                            await self.on_audio_data(parsed_message.data)
                        else:
                            self.on_audio_data(parsed_message.data)
                
                elif parsed_message.message_type == MessageType.TEXT and self.on_text_data:
                    if isinstance(parsed_message.data, str):
                        if asyncio.iscoroutinefunction(self.on_text_data):
                            await self.on_text_data(parsed_message.data)
                        else:
                            self.on_text_data(parsed_message.data)
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON message: {e}")
            self.stats['errors'] += 1
        except Exception as e:
            logger.error(f"Error handling text message: {e}")
            self.stats['errors'] += 1
    
    async def _handle_binary_message(self, data: bytes):
        """Handle incoming binary message."""
        try:
            # Create message for binary data
            message = WebSocketMessage(
                message_id=str(uuid.uuid4()),
                message_type=MessageType.AUDIO,
                data=data,
                timestamp=time.time()
            )
            
            # Update statistics
            self.stats['messages_received'] += 1
            self.stats['bytes_received'] += len(data)
            
            # Call audio callback
            if self.on_audio_data:
                if asyncio.iscoroutinefunction(self.on_audio_data):
                    await self.on_audio_data(data)
                else:
                    self.on_audio_data(data)
            
        except Exception as e:
            logger.error(f"Error handling binary message: {e}")
            self.stats['errors'] += 1
    
    def _parse_openai_message(self, data: Dict[str, Any]) -> Optional[WebSocketMessage]:
        """Parse OpenAI Realtime API message format."""
        try:
            message_type = MessageType.TEXT  # Default
            message_data = data
            
            if "type" in data:
                if data["type"] == "conversation.item.input_audio_buffer.committed":
                    message_type = MessageType.AUDIO
                    message_data = data.get("audio", "")
                elif data["type"] == "conversation.item.create":
                    message_type = MessageType.TEXT
                    message_data = data.get("item", {}).get("content", "")
                elif data["type"] == "response.audio.delta":
                    message_type = MessageType.AUDIO
                    message_data = data.get("delta", "")
                elif data["type"] == "response.text.delta":
                    message_type = MessageType.TEXT
                    message_data = data.get("delta", "")
                elif data["type"] == "error":
                    message_type = MessageType.ERROR
                    message_data = data.get("error", {})
            
            return WebSocketMessage(
                message_id=data.get("id", str(uuid.uuid4())),
                message_type=message_type,
                data=message_data,
                timestamp=data.get("timestamp", time.time()),
                metadata={"provider": "openai", "raw": data}
            )
            
        except Exception as e:
            logger.error(f"Failed to parse OpenAI message: {e}")
            return None
    
    def _parse_generic_message(self, data: Dict[str, Any]) -> Optional[WebSocketMessage]:
        """Parse generic WebSocket message format."""
        try:
            return WebSocketMessage(
                message_id=data.get("id", str(uuid.uuid4())),
                message_type=MessageType(data.get("type", "text")),
                data=data.get("data", ""),
                timestamp=data.get("timestamp", time.time()),
                metadata=data.get("metadata", {})
            )
        except Exception as e:
            logger.error(f"Failed to parse generic message: {e}")
            return None
    
    async def _heartbeat_loop(self):
        """Heartbeat loop to maintain connection."""
        while self.state == WebSocketState.CONNECTED:
            try:
                await asyncio.sleep(self.config.ping_interval)
                
                if self.websocket and not self.websocket.closed:
                    await self.websocket.ping()
                    self.last_ping_time = time.time()
                else:
                    logger.warning("WebSocket connection lost during heartbeat")
                    break
                    
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
                break
    
    async def _attempt_reconnection(self):
        """Attempt to reconnect to WebSocket."""
        if self.reconnect_attempts >= self.config.max_reconnect_attempts:
            logger.error("Max reconnection attempts reached")
            self.state = WebSocketState.FAILED
            return
        
        self.state = WebSocketState.RECONNECTING
        self.reconnect_attempts += 1
        self.stats['reconnection_attempts'] += 1
        
        # Calculate delay with exponential backoff
        delay = min(
            self.config.reconnect_delay * (self.config.reconnect_backoff_factor ** (self.reconnect_attempts - 1)),
            self.config.max_reconnect_delay
        )
        
        if self.config.enable_logging:
            logger.info(f"Attempting reconnection {self.reconnect_attempts}/{self.config.max_reconnect_attempts} in {delay:.1f}s")
        
        await asyncio.sleep(delay)
        
        # Attempt to reconnect
        success = await self.connect()
        if not success:
            # Schedule another reconnection attempt
            asyncio.create_task(self._attempt_reconnection())
    
    def get_stats(self) -> Dict[str, Any]:
        """Get WebSocket manager statistics."""
        self.stats['uptime'] = time.time() - self.start_time
        return self.stats.copy()
    
    def reset_stats(self):
        """Reset statistics."""
        self.stats = {
            'messages_sent': 0,
            'messages_received': 0,
            'bytes_sent': 0,
            'bytes_received': 0,
            'connection_attempts': 0,
            'reconnection_attempts': 0,
            'errors': 0,
            'last_connection_time': 0.0,
            'uptime': 0.0
        }
    
    async def close(self):
        """Close the WebSocket manager and cleanup resources."""
        await self.disconnect()
        self.executor.shutdown(wait=True)
        
        if self.config.enable_logging:
            logger.info("WebSocket manager closed")


class WebSocketPool:
    """
    Connection pool for managing multiple WebSocket connections.
    
    This class provides:
    - Multiple WebSocket connection management
    - Load balancing across connections
    - Health monitoring and failover
    - Resource cleanup and lifecycle management
    """
    
    def __init__(self, configs: List[WebSocketConfig], max_connections: int = 10):
        """
        Initialize WebSocket pool.
        
        Args:
            configs: List of WebSocket configurations
            max_connections: Maximum number of connections
        """
        self.configs = configs
        self.max_connections = max_connections
        self.connections: Dict[str, WebSocketManager] = {}
        self.connection_health: Dict[str, bool] = {}
        
        # Statistics
        self.stats = {
            'total_connections': 0,
            'active_connections': 0,
            'failed_connections': 0,
            'messages_routed': 0,
            'load_balance_hits': 0
        }
        
        logger.info(f"WebSocket pool initialized with {len(configs)} configurations")
    
    async def create_connection(self, config: WebSocketConfig, connection_id: str = None) -> str:
        """
        Create a new WebSocket connection.
        
        Args:
            config: WebSocket configuration
            connection_id: Optional connection ID
            
        Returns:
            str: Connection ID
        """
        if len(self.connections) >= self.max_connections:
            raise RuntimeError("Maximum connections reached")
        
        connection_id = connection_id or str(uuid.uuid4())
        manager = WebSocketManager(config)
        
        # Set up connection health monitoring
        manager.on_disconnect = lambda: self._on_connection_disconnected(connection_id)
        manager.on_error = lambda msg, err: self._on_connection_error(connection_id, msg, err)
        
        # Connect
        success = await manager.connect()
        if success:
            self.connections[connection_id] = manager
            self.connection_health[connection_id] = True
            self.stats['total_connections'] += 1
            self.stats['active_connections'] += 1
            
            logger.info(f"Created connection {connection_id}")
            return connection_id
        else:
            self.stats['failed_connections'] += 1
            raise ConnectionError(f"Failed to create connection {connection_id}")
    
    async def get_connection(self, connection_id: str = None) -> Optional[WebSocketManager]:
        """
        Get a WebSocket connection.
        
        Args:
            connection_id: Specific connection ID (optional)
            
        Returns:
            WebSocketManager: Connection manager or None
        """
        if connection_id:
            return self.connections.get(connection_id)
        
        # Return first healthy connection
        for conn_id, manager in self.connections.items():
            if self.connection_health.get(conn_id, False) and manager.state == WebSocketState.CONNECTED:
                return manager
        
        return None
    
    async def send_message(self, message_type: MessageType, data: Union[str, bytes, Dict[str, Any]], 
                          connection_id: str = None) -> Optional[str]:
        """
        Send a message through a connection.
        
        Args:
            message_type: Message type
            data: Message data
            connection_id: Specific connection ID (optional)
            
        Returns:
            str: Message ID or None if failed
        """
        manager = await self.get_connection(connection_id)
        if not manager:
            logger.error("No available connections")
            return None
        
        try:
            message_id = await manager.send_message(message_type, data)
            self.stats['messages_routed'] += 1
            return message_id
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            return None
    
    def _on_connection_disconnected(self, connection_id: str):
        """Handle connection disconnection."""
        self.connection_health[connection_id] = False
        self.stats['active_connections'] = max(0, self.stats['active_connections'] - 1)
        logger.warning(f"Connection {connection_id} disconnected")
    
    def _on_connection_error(self, connection_id: str, message: str, error: Exception):
        """Handle connection error."""
        self.connection_health[connection_id] = False
        logger.error(f"Connection {connection_id} error: {message}")
    
    async def close_all(self):
        """Close all connections in the pool."""
        for connection_id, manager in self.connections.items():
            try:
                await manager.close()
                logger.info(f"Closed connection {connection_id}")
            except Exception as e:
                logger.error(f"Error closing connection {connection_id}: {e}")
        
        self.connections.clear()
        self.connection_health.clear()
        self.stats['active_connections'] = 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get pool statistics."""
        return self.stats.copy()
