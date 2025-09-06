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
from .pipeline import (
    AudioProcessingPipeline,
    AudioProcessingManager,
    AudioProcessingConfig,
    AudioFrame,
    PipelineMode
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
    'EchoCancellationMode',
    'AudioProcessingPipeline',
    'AudioProcessingManager',
    'AudioProcessingConfig',
    'AudioFrame',
    'PipelineMode'
]
