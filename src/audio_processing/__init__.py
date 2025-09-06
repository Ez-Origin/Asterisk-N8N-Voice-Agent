"""
Audio processing module for the Asterisk AI Voice Agent.
"""

from .vad import VoiceActivityDetector, VADProcessor, VADConfig, VADMode
from .noise_suppression import (
    NoiseSuppressor, 
    NoiseSuppressionProcessor, 
    NoiseSuppressionConfig, 
    NoiseSuppressionMode
)

__all__ = [
    'VoiceActivityDetector', 
    'VADProcessor', 
    'VADConfig', 
    'VADMode',
    'NoiseSuppressor',
    'NoiseSuppressionProcessor', 
    'NoiseSuppressionConfig',
    'NoiseSuppressionMode'
]
