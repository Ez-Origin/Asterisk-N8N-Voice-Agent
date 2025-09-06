"""
Voice Activity Detection (VAD) module for real-time audio processing.
"""

import logging
import webrtcvad
import numpy as np
from typing import Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class VADMode(Enum):
    """VAD sensitivity modes."""
    QUALITY = 0
    LOW_BITRATE = 1
    AGGRESSIVE = 2
    VERY_AGGRESSIVE = 3

@dataclass
class VADConfig:
    """Configuration for Voice Activity Detection."""
    mode: VADMode = VADMode.AGGRESSIVE
    sample_rate: int = 16000
    frame_duration_ms: int = 30
    min_speech_frames: int = 3
    min_silence_frames: int = 3
    enable_logging: bool = True

class VoiceActivityDetector:
    """Voice Activity Detector using WebRTC VAD."""
    
    def __init__(self, config: Optional[VADConfig] = None):
        self.config = config or VADConfig()
        self.vad = webrtcvad.Vad(self.config.mode.value)
        self.frame_size = int(self.config.sample_rate * self.config.frame_duration_ms / 1000)
        self.speech_frames = 0
        self.silence_frames = 0
        self.is_speaking = False
        self.frame_count = 0
        
    def process_frame(self, audio_frame: bytes) -> bool:
        """Process a single audio frame for voice activity detection."""
        if len(audio_frame) != self.frame_size * 2:
            raise ValueError(f"Invalid frame size: expected {self.frame_size * 2} bytes, got {len(audio_frame)} bytes")
        
        try:
            is_speech = self.vad.is_speech(audio_frame, self.config.sample_rate)
            self.frame_count += 1
            
            if is_speech:
                self.speech_frames += 1
                self.silence_frames = 0
            else:
                self.silence_frames += 1
                self.speech_frames = 0
            
            if is_speech and self.speech_frames >= self.config.min_speech_frames:
                self.is_speaking = True
            elif not is_speech and self.silence_frames >= self.config.min_silence_frames:
                self.is_speaking = False
            
            return is_speech
        except Exception as e:
            logger.error(f"VAD processing error: {e}")
            return False
    
    def reset(self):
        """Reset VAD state."""
        self.speech_frames = 0
        self.silence_frames = 0
        self.is_speaking = False
        self.frame_count = 0

class VADProcessor:
    """High-level VAD processor for real-time audio streams."""
    
    def __init__(self, config: Optional[VADConfig] = None):
        self.config = config or VADConfig()
        self.vad = VoiceActivityDetector(self.config)
        self.audio_buffer = bytearray()
        self.frame_size_bytes = self.vad.frame_size * 2
        
    def process_audio(self, audio_data: bytes) -> List[bool]:
        """Process incoming audio data and return VAD results."""
        self.audio_buffer.extend(audio_data)
        results = []
        
        while len(self.audio_buffer) >= self.frame_size_bytes:
            frame = bytes(self.audio_buffer[:self.frame_size_bytes])
            result = self.vad.process_frame(frame)
            results.append(result)
            self.audio_buffer = self.audio_buffer[self.frame_size_bytes:]
        
        return results
    
    def is_currently_speaking(self) -> bool:
        """Check if currently detecting speech."""
        return self.vad.is_speaking
