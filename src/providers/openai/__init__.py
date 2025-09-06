"""
OpenAI Provider Package

This package contains implementations for OpenAI's various APIs,
including the Realtime API for streaming STT, LLM, and TTS operations.
"""

from .realtime_client import (
    RealtimeClient,
    RealtimeConfig,
    RealtimeMessage,
    RealtimeMessageType,
    VoiceType,
    AudioChunk
)

from .stt_handler import (
    STTHandler,
    STTManager,
    STTConfig,
    STTState,
    TranscriptResult
)

__all__ = [
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
    'TranscriptResult'
]
