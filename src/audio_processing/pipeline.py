"""
Audio Processing Pipeline for real-time voice communication.

This module provides a comprehensive audio processing pipeline that integrates
VAD, noise suppression, and echo cancellation for high-quality voice calls.
"""

import logging
import numpy as np
from typing import Optional, Dict, Any, Callable, Tuple
from dataclasses import dataclass
from enum import Enum
import asyncio
from queue import Queue, Empty
import threading
import time

from .vad import VoiceActivityDetector, VADConfig, VADMode
from .noise_suppression import NoiseSuppressor, NoiseSuppressionConfig, NoiseSuppressionMode
from .echo_cancellation import EchoCanceller, EchoCancellationConfig, EchoCancellationMode

logger = logging.getLogger(__name__)


class PipelineMode(Enum):
    """Audio processing pipeline modes."""
    LIGHT = "light"      # Minimal processing for low latency
    BALANCED = "balanced"  # Balanced processing for quality and performance
    HIGH_QUALITY = "high_quality"  # Maximum quality processing
    CUSTOM = "custom"    # User-defined configuration


@dataclass
class AudioProcessingConfig:
    """Configuration for the audio processing pipeline."""
    # Pipeline settings
    mode: PipelineMode = PipelineMode.BALANCED
    sample_rate: int = 16000
    frame_duration_ms: int = 30
    enable_logging: bool = True
    
    # Component enablement
    enable_vad: bool = True
    enable_noise_suppression: bool = True
    enable_echo_cancellation: bool = True
    
    # Processing order (can be customized)
    processing_order: list = None
    
    # Performance settings
    max_queue_size: int = 100
    processing_timeout_ms: int = 50
    
    def __post_init__(self):
        if self.processing_order is None:
            self.processing_order = ['vad', 'noise_suppression', 'echo_cancellation']


class AudioFrame:
    """Represents a single audio frame with metadata."""
    
    def __init__(self, data: bytes, timestamp: float = None, metadata: Dict[str, Any] = None):
        self.data = data
        self.timestamp = timestamp or time.time()
        self.metadata = metadata or {}
        self.frame_id = id(self)
    
    def __len__(self):
        return len(self.data)
    
    def add_metadata(self, key: str, value: Any):
        """Add metadata to the frame."""
        self.metadata[key] = value
    
    def get_metadata(self, key: str, default: Any = None):
        """Get metadata from the frame."""
        return self.metadata.get(key, default)


class AudioProcessingPipeline:
    """
    Comprehensive audio processing pipeline for real-time voice communication.
    
    This pipeline integrates VAD, noise suppression, and echo cancellation
    to provide high-quality audio processing for voice calls.
    """
    
    def __init__(self, config: Optional[AudioProcessingConfig] = None):
        """
        Initialize the audio processing pipeline.
        
        Args:
            config: Pipeline configuration. If None, uses default config.
        """
        self.config = config or AudioProcessingConfig()
        
        # Calculate frame size
        self.frame_size = int(self.config.sample_rate * self.config.frame_duration_ms / 1000)
        self.frame_size_bytes = self.frame_size * 2  # 16-bit PCM
        
        # Initialize components based on configuration
        self._initialize_components()
        
        # Processing queues
        self.input_queue = Queue(maxsize=self.config.max_queue_size)
        self.output_queue = Queue(maxsize=self.config.max_queue_size)
        
        # Processing state
        self.is_processing = False
        self.processing_thread = None
        self.stats = {
            'frames_processed': 0,
            'frames_dropped': 0,
            'processing_time_ms': 0,
            'vad_detections': 0,
            'noise_reduction_applied': 0,
            'echo_cancellation_applied': 0
        }
        
        # Callbacks
        self.on_frame_processed: Optional[Callable[[AudioFrame], None]] = None
        self.on_speech_detected: Optional[Callable[[AudioFrame], None]] = None
        self.on_error: Optional[Callable[[Exception], None]] = None
        
        if self.config.enable_logging:
            logger.info(f"Audio processing pipeline initialized: mode={self.config.mode.value}, "
                       f"sample_rate={self.config.sample_rate}Hz, "
                       f"frame_duration={self.config.frame_duration_ms}ms")
    
    def _initialize_components(self):
        """Initialize audio processing components based on configuration."""
        self.components = {}
        
        # Initialize VAD
        if self.config.enable_vad:
            vad_config = VADConfig(
                sample_rate=self.config.sample_rate,
                frame_duration_ms=self.config.frame_duration_ms,
                enable_logging=self.config.enable_logging
            )
            self.components['vad'] = VoiceActivityDetector(vad_config)
        
        # Initialize Noise Suppression
        if self.config.enable_noise_suppression:
            noise_config = NoiseSuppressionConfig(
                sample_rate=self.config.sample_rate,
                frame_duration_ms=self.config.frame_duration_ms,
                enable_logging=self.config.enable_logging
            )
            self.components['noise_suppression'] = NoiseSuppressor(noise_config)
        
        # Initialize Echo Cancellation
        if self.config.enable_echo_cancellation:
            echo_config = EchoCancellationConfig(
                sample_rate=self.config.sample_rate,
                frame_duration_ms=self.config.frame_duration_ms,
                enable_logging=self.config.enable_logging
            )
            self.components['echo_cancellation'] = EchoCanceller(echo_config)
    
    def _get_mode_configuration(self) -> Dict[str, Any]:
        """Get configuration parameters based on the selected mode."""
        if self.config.mode == PipelineMode.LIGHT:
            return {
                'vad_mode': VADMode.AGGRESSIVE,
                'noise_mode': NoiseSuppressionMode.LIGHT,
                'echo_mode': EchoCancellationMode.LIGHT,
                'enable_spectral_subtraction': False
            }
        elif self.config.mode == PipelineMode.BALANCED:
            return {
                'vad_mode': VADMode.AGGRESSIVE,
                'noise_mode': NoiseSuppressionMode.MODERATE,
                'echo_mode': EchoCancellationMode.MODERATE,
                'enable_spectral_subtraction': True
            }
        elif self.config.mode == PipelineMode.HIGH_QUALITY:
            return {
                'vad_mode': VADMode.VERY_AGGRESSIVE,
                'noise_mode': NoiseSuppressionMode.AGGRESSIVE,
                'echo_mode': EchoCancellationMode.AGGRESSIVE,
                'enable_spectral_subtraction': True
            }
        else:  # CUSTOM mode
            return {
                'vad_mode': VADMode.AGGRESSIVE,
                'noise_mode': NoiseSuppressionMode.MODERATE,
                'echo_mode': EchoCancellationMode.MODERATE,
                'enable_spectral_subtraction': True
            }
    
    def _bytes_to_float32(self, audio_bytes: bytes) -> np.ndarray:
        """Convert 16-bit PCM bytes to float32 numpy array."""
        audio_int16 = np.frombuffer(audio_bytes, dtype=np.int16)
        audio_float32 = audio_int16.astype(np.float32) / 32768.0
        return audio_float32
    
    def _float32_to_bytes(self, audio_float32: np.ndarray) -> bytes:
        """Convert float32 numpy array to 16-bit PCM bytes."""
        audio_int16 = (audio_float32 * 32767.0).astype(np.int16)
        return audio_int16.tobytes()
    
    def _process_frame(self, frame: AudioFrame, reference_frame: Optional[AudioFrame] = None) -> AudioFrame:
        """
        Process a single audio frame through the pipeline.
        
        Args:
            frame: Input audio frame
            reference_frame: Reference frame for echo cancellation (optional)
            
        Returns:
            AudioFrame: Processed audio frame
        """
        start_time = time.time()
        processed_data = frame.data
        metadata = frame.metadata.copy()
        
        try:
            # Process through each component in order
            for component_name in self.config.processing_order:
                if component_name not in self.components:
                    continue
                
                component = self.components[component_name]
                
                if component_name == 'vad':
                    # Voice Activity Detection
                    is_speech = component.process_frame(processed_data)
                    metadata['is_speech'] = is_speech
                    metadata['vad_confidence'] = component.get_stats().get('speech_ratio', 0.0)
                    
                    if is_speech:
                        self.stats['vad_detections'] += 1
                        if self.on_speech_detected:
                            self.on_speech_detected(frame)
                
                elif component_name == 'noise_suppression':
                    # Noise Suppression
                    if metadata.get('is_speech', True):  # Only process speech frames
                        processed_data = component.process_frame(processed_data)
                        metadata['noise_suppression_applied'] = True
                        self.stats['noise_reduction_applied'] += 1
                    else:
                        metadata['noise_suppression_applied'] = False
                
                elif component_name == 'echo_cancellation':
                    # Echo Cancellation (requires reference frame)
                    if reference_frame and metadata.get('is_speech', True):
                        processed_data = component.process_frame(processed_data, reference_frame.data)
                        metadata['echo_cancellation_applied'] = True
                        self.stats['echo_cancellation_applied'] += 1
                    else:
                        metadata['echo_cancellation_applied'] = False
                
                # Add component-specific metadata
                if hasattr(component, 'get_stats'):
                    component_stats = component.get_stats()
                    metadata[f'{component_name}_stats'] = component_stats
            
            # Create processed frame
            processed_frame = AudioFrame(
                data=processed_data,
                timestamp=frame.timestamp,
                metadata=metadata
            )
            
            # Add processing metadata
            processing_time = (time.time() - start_time) * 1000
            processed_frame.add_metadata('processing_time_ms', processing_time)
            processed_frame.add_metadata('pipeline_mode', self.config.mode.value)
            
            self.stats['frames_processed'] += 1
            self.stats['processing_time_ms'] = processing_time
            
            return processed_frame
            
        except Exception as e:
            logger.error(f"Error processing frame: {e}")
            if self.on_error:
                self.on_error(e)
            
            # Return original frame on error
            frame.add_metadata('processing_error', str(e))
            return frame
    
    def add_frame(self, frame: AudioFrame, reference_frame: Optional[AudioFrame] = None):
        """
        Add an audio frame to the processing pipeline.
        
        Args:
            frame: Input audio frame
            reference_frame: Reference frame for echo cancellation (optional)
        """
        try:
            # Add reference frame to metadata if provided
            if reference_frame:
                frame.add_metadata('reference_frame_id', reference_frame.frame_id)
            
            self.input_queue.put((frame, reference_frame), timeout=0.001)
        except:
            self.stats['frames_dropped'] += 1
            logger.warning("Input queue full, dropping frame")
    
    def get_processed_frame(self, timeout: float = 0.1) -> Optional[AudioFrame]:
        """
        Get a processed audio frame from the pipeline.
        
        Args:
            timeout: Maximum time to wait for a frame
            
        Returns:
            AudioFrame: Processed frame or None if timeout
        """
        try:
            return self.output_queue.get(timeout=timeout)
        except Empty:
            return None
    
    def _processing_worker(self):
        """Worker thread for processing audio frames."""
        while self.is_processing:
            try:
                # Get frame from input queue
                frame, reference_frame = self.input_queue.get(timeout=0.1)
                
                # Process frame
                processed_frame = self._process_frame(frame, reference_frame)
                
                # Add to output queue
                self.output_queue.put(processed_frame, timeout=0.001)
                
                # Call callback if set
                if self.on_frame_processed:
                    self.on_frame_processed(processed_frame)
                
            except Empty:
                continue
            except Exception as e:
                logger.error(f"Error in processing worker: {e}")
                if self.on_error:
                    self.on_error(e)
    
    def start(self):
        """Start the audio processing pipeline."""
        if self.is_processing:
            logger.warning("Pipeline is already running")
            return
        
        self.is_processing = True
        self.processing_thread = threading.Thread(target=self._processing_worker, daemon=True)
        self.processing_thread.start()
        
        if self.config.enable_logging:
            logger.info("Audio processing pipeline started")
    
    def stop(self):
        """Stop the audio processing pipeline."""
        if not self.is_processing:
            logger.warning("Pipeline is not running")
            return
        
        self.is_processing = False
        
        if self.processing_thread:
            self.processing_thread.join(timeout=1.0)
        
        # Clear queues
        while not self.input_queue.empty():
            try:
                self.input_queue.get_nowait()
            except Empty:
                break
        
        while not self.output_queue.empty():
            try:
                self.output_queue.get_nowait()
            except Empty:
                break
        
        if self.config.enable_logging:
            logger.info("Audio processing pipeline stopped")
    
    def reset(self):
        """Reset all components in the pipeline."""
        for component in self.components.values():
            if hasattr(component, 'reset'):
                component.reset()
        
        # Reset stats
        self.stats = {
            'frames_processed': 0,
            'frames_dropped': 0,
            'processing_time_ms': 0,
            'vad_detections': 0,
            'noise_reduction_applied': 0,
            'echo_cancellation_applied': 0
        }
        
        logger.debug("Audio processing pipeline reset")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive pipeline statistics."""
        stats = self.stats.copy()
        
        # Add component-specific stats
        for name, component in self.components.items():
            if hasattr(component, 'get_stats'):
                stats[f'{name}_stats'] = component.get_stats()
        
        # Add queue information
        stats['input_queue_size'] = self.input_queue.qsize()
        stats['output_queue_size'] = self.output_queue.qsize()
        stats['is_processing'] = self.is_processing
        
        return stats
    
    def configure_component(self, component_name: str, **kwargs):
        """
        Configure a specific component in the pipeline.
        
        Args:
            component_name: Name of the component to configure
            **kwargs: Configuration parameters
        """
        if component_name not in self.components:
            logger.warning(f"Component '{component_name}' not found")
            return
        
        component = self.components[component_name]
        
        # Update component configuration
        for key, value in kwargs.items():
            if hasattr(component, key):
                setattr(component, key, value)
            else:
                logger.warning(f"Component '{component_name}' does not have attribute '{key}'")
    
    def build_noise_profile(self, noise_sample: bytes, duration_seconds: float = 2.0) -> bool:
        """
        Build noise profile for noise suppression.
        
        Args:
            noise_sample: Sample of background noise
            duration_seconds: Duration of noise sample to use
            
        Returns:
            bool: True if profile was built successfully
        """
        if 'noise_suppression' not in self.components:
            logger.warning("Noise suppression component not available")
            return False
        
        noise_suppressor = self.components['noise_suppression']
        return noise_suppressor.build_noise_profile(noise_sample, duration_seconds)
    
    def enable_echo_cancellation_adaptation(self, enabled: bool = True):
        """Enable or disable echo cancellation adaptation."""
        if 'echo_cancellation' in self.components:
            self.components['echo_cancellation'].enable_adaptation(enabled)
        else:
            logger.warning("Echo cancellation component not available")


class AudioProcessingManager:
    """
    High-level manager for audio processing pipelines.
    
    This class provides a convenient interface for managing multiple
    audio processing pipelines and handling real-time audio streams.
    """
    
    def __init__(self, config: Optional[AudioProcessingConfig] = None):
        """Initialize the audio processing manager."""
        self.config = config or AudioProcessingConfig()
        self.pipelines = {}
        self.active_pipelines = set()
    
    def create_pipeline(self, pipeline_id: str, config: Optional[AudioProcessingConfig] = None) -> AudioProcessingPipeline:
        """
        Create a new audio processing pipeline.
        
        Args:
            pipeline_id: Unique identifier for the pipeline
            config: Pipeline configuration (optional)
            
        Returns:
            AudioProcessingPipeline: Created pipeline
        """
        if pipeline_id in self.pipelines:
            logger.warning(f"Pipeline '{pipeline_id}' already exists")
            return self.pipelines[pipeline_id]
        
        pipeline_config = config or self.config
        pipeline = AudioProcessingPipeline(pipeline_config)
        self.pipelines[pipeline_id] = pipeline
        
        logger.info(f"Created pipeline '{pipeline_id}'")
        return pipeline
    
    def get_pipeline(self, pipeline_id: str) -> Optional[AudioProcessingPipeline]:
        """Get a pipeline by ID."""
        return self.pipelines.get(pipeline_id)
    
    def remove_pipeline(self, pipeline_id: str):
        """Remove a pipeline."""
        if pipeline_id in self.pipelines:
            pipeline = self.pipelines[pipeline_id]
            if pipeline.is_processing:
                pipeline.stop()
            del self.pipelines[pipeline_id]
            self.active_pipelines.discard(pipeline_id)
            logger.info(f"Removed pipeline '{pipeline_id}'")
    
    def start_pipeline(self, pipeline_id: str):
        """Start a pipeline."""
        if pipeline_id in self.pipelines:
            self.pipelines[pipeline_id].start()
            self.active_pipelines.add(pipeline_id)
        else:
            logger.warning(f"Pipeline '{pipeline_id}' not found")
    
    def stop_pipeline(self, pipeline_id: str):
        """Stop a pipeline."""
        if pipeline_id in self.pipelines:
            self.pipelines[pipeline_id].stop()
            self.active_pipelines.discard(pipeline_id)
        else:
            logger.warning(f"Pipeline '{pipeline_id}' not found")
    
    def stop_all_pipelines(self):
        """Stop all active pipelines."""
        for pipeline_id in list(self.active_pipelines):
            self.stop_pipeline(pipeline_id)
    
    def get_all_stats(self) -> Dict[str, Any]:
        """Get statistics for all pipelines."""
        stats = {}
        for pipeline_id, pipeline in self.pipelines.items():
            stats[pipeline_id] = pipeline.get_stats()
        return stats
