"""
AI Provider modules for the Asterisk AI Voice Agent.

This module provides interfaces and implementations for various AI providers
including OpenAI, Azure, and custom providers.
"""

from .websocket_manager import (
    WebSocketManager,
    WebSocketPool,
    WebSocketConfig,
    WebSocketState,
    WebSocketMessage,
    MessageType
)

from .openai import (
    RealtimeClient,
    RealtimeConfig,
    RealtimeMessage,
    RealtimeMessageType,
    VoiceType,
    AudioChunk
)

__all__ = [
    'WebSocketManager',
    'WebSocketPool', 
    'WebSocketConfig',
    'WebSocketState',
    'WebSocketMessage',
    'MessageType',
    'RealtimeClient',
    'RealtimeConfig',
    'RealtimeMessage',
    'RealtimeMessageType',
    'VoiceType',
    'AudioChunk'
]
