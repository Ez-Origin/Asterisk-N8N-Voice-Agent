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

from .llm_handler import (
    LLMHandler,
    LLMManager,
    LLMConfig,
    LLMState,
    LLMResponse,
    ResponseType
)

from .tts_handler import (
    TTSHandler,
    TTSManager,
    TTSConfig,
    TTSState,
    TTSResponse,
    AudioFormat
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
