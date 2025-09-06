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
from .echo_cancellation import (
    EchoCanceller,
    EchoCancellationProcessor,
    EchoCancellationConfig,
    EchoCancellationMode
)

__all__ = [
    'VoiceActivityDetector', 
    'VADProcessor', 
    'VADConfig', 
    'VADMode',
    'NoiseSuppressor',
    'NoiseSuppressionProcessor', 
    'NoiseSuppressionConfig',
    'NoiseSuppressionMode',
    'EchoCanceller',
    'EchoCancellationProcessor',
    'EchoCancellationConfig',
    'EchoCancellationMode'
]
