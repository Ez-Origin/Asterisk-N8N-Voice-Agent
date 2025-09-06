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
    AudioChunk,
    STTHandler,
    STTManager,
    STTConfig,
    STTState,
    TranscriptResult,
    LLMHandler,
    LLMManager,
    LLMConfig,
    LLMState,
    LLMResponse,
    ResponseType,
    TTSHandler,
    TTSManager,
    TTSConfig,
    TTSState,
    TTSResponse,
    AudioFormat
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
    'AudioChunk',
    'STTHandler',
    'STTManager',
    'STTConfig',
    'STTState',
    'TranscriptResult',
    'LLMHandler',
    'LLMManager',
    'LLMConfig',
    'LLMState',
    'LLMResponse',
    'ResponseType',
    'TTSHandler',
    'TTSManager',
    'TTSConfig',
    'TTSState',
    'TTSResponse',
    'AudioFormat'
]
