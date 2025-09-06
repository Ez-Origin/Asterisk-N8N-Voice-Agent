"""
Noise Suppression module for real-time audio processing.

This module provides noise suppression functionality using noisereduce
and librosa for cleaner audio quality in voice calls.
"""

import logging
import numpy as np
import noisereduce as nr
import librosa
from typing import Optional, Tuple, Union
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class NoiseSuppressionMode(Enum):
    """Noise suppression processing modes."""
    LIGHT = "light"      # Minimal processing, preserves more audio
    MODERATE = "moderate"  # Balanced processing
    AGGRESSIVE = "aggressive"  # Heavy processing, may affect speech quality
    CUSTOM = "custom"    # User-defined parameters


@dataclass
class NoiseSuppressionConfig:
    """Configuration for Noise Suppression."""
    mode: NoiseSuppressionMode = NoiseSuppressionMode.MODERATE
    sample_rate: int = 16000
    frame_duration_ms: int = 30
    enable_logging: bool = True
    
    # noisereduce parameters
    stationary: bool = True  # Assume stationary noise
    prop_decrease: float = 0.8  # Proportion of noise to reduce (0.0-1.0)
    use_tqdm: bool = False  # Disable progress bars for real-time processing
    
    # Advanced parameters (for CUSTOM mode)
    noise_reduce_stationary: bool = True
    noise_reduce_nonstationary: bool = True
    noise_reduce_stationary_n_fft: int = 1024
    noise_reduce_stationary_hop_length: int = 256
    noise_reduce_nonstationary_n_fft: int = 1024
    noise_reduce_nonstationary_hop_length: int = 256


class NoiseSuppressor:
    """
    Real-time noise suppression using noisereduce and librosa.
    
    This class provides noise suppression for audio streams with
    configurable processing modes and real-time frame processing.
    """
    
    def __init__(self, config: Optional[NoiseSuppressionConfig] = None):
        """
        Initialize the Noise Suppressor.
        
        Args:
            config: Noise suppression configuration. If None, uses default config.
        """
        self.config = config or NoiseSuppressionConfig()
        
        # Calculate frame size based on sample rate and duration
        self.frame_size = int(self.config.sample_rate * self.config.frame_duration_ms / 1000)
        
        # Audio buffer for processing
        self.audio_buffer = np.array([], dtype=np.float32)
        self.noise_profile = None
        self.is_noise_profile_ready = False
        
        # Frame processing state
        self.frame_count = 0
        self.processed_samples = 0
        
        if self.config.enable_logging:
            logger.info(f"Noise suppressor initialized: mode={self.config.mode.value}, "
                       f"sample_rate={self.config.sample_rate}Hz, "
                       f"frame_duration={self.config.frame_duration_ms}ms")
    
    def _get_mode_parameters(self) -> dict:
        """Get processing parameters based on the selected mode."""
        if self.config.mode == NoiseSuppressionMode.LIGHT:
            return {
                "prop_decrease": 0.3,
                "stationary": True,
                "noise_reduce_stationary": True,
                "noise_reduce_nonstationary": False
            }
        elif self.config.mode == NoiseSuppressionMode.MODERATE:
            return {
                "prop_decrease": 0.6,
                "stationary": True,
                "noise_reduce_stationary": True,
                "noise_reduce_nonstationary": True
            }
        elif self.config.mode == NoiseSuppressionMode.AGGRESSIVE:
            return {
                "prop_decrease": 0.9,
                "stationary": True,
                "noise_reduce_stationary": True,
                "noise_reduce_nonstationary": True
            }
        else:  # CUSTOM mode
            return {
                "prop_decrease": self.config.prop_decrease,
                "stationary": self.config.stationary,
                "noise_reduce_stationary": self.config.noise_reduce_stationary,
                "noise_reduce_nonstationary": self.config.noise_reduce_nonstationary
            }
    
    def _bytes_to_float32(self, audio_bytes: bytes) -> np.ndarray:
        """Convert 16-bit PCM bytes to float32 numpy array."""
        # Convert bytes to int16, then to float32 and normalize
        audio_int16 = np.frombuffer(audio_bytes, dtype=np.int16)
        audio_float32 = audio_int16.astype(np.float32) / 32768.0
        return audio_float32
    
    def _float32_to_bytes(self, audio_float32: np.ndarray) -> bytes:
        """Convert float32 numpy array to 16-bit PCM bytes."""
        # Denormalize and convert to int16
        audio_int16 = (audio_float32 * 32767.0).astype(np.int16)
        return audio_int16.tobytes()
    
    def build_noise_profile(self, noise_sample: Union[bytes, np.ndarray], 
                          duration_seconds: float = 2.0) -> bool:
        """
        Build a noise profile from a sample of background noise.
        
        Args:
            noise_sample: Sample of background noise (bytes or numpy array)
            duration_seconds: Duration of noise sample to use for profile
            
        Returns:
            bool: True if profile was built successfully
        """
        try:
            if isinstance(noise_sample, bytes):
                noise_audio = self._bytes_to_float32(noise_sample)
            else:
                noise_audio = noise_sample.astype(np.float32)
            
            # Limit duration for noise profile
            max_samples = int(self.config.sample_rate * duration_seconds)
            if len(noise_audio) > max_samples:
                noise_audio = noise_audio[:max_samples]
            
            # Store noise profile
            self.noise_profile = noise_audio
            self.is_noise_profile_ready = True
            
            if self.config.enable_logging:
                logger.info(f"Noise profile built from {len(noise_audio)} samples "
                           f"({len(noise_audio) / self.config.sample_rate:.2f}s)")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to build noise profile: {e}")
            return False
    
    def process_frame(self, audio_frame: bytes) -> bytes:
        """
        Process a single audio frame for noise suppression.
        
        Args:
            audio_frame: Raw audio frame bytes (16-bit PCM, mono)
            
        Returns:
            bytes: Processed audio frame bytes (16-bit PCM, mono)
            
        Raises:
            ValueError: If audio frame size is incorrect
        """
        if len(audio_frame) != self.frame_size * 2:  # 2 bytes per sample (16-bit)
            raise ValueError(f"Invalid frame size: expected {self.frame_size * 2} bytes, "
                           f"got {len(audio_frame)} bytes")
        
        try:
            # Convert to float32 for processing
            audio_float32 = self._bytes_to_float32(audio_frame)
            
            # Add to buffer for context
            self.audio_buffer = np.concatenate([self.audio_buffer, audio_float32])
            
            # Keep buffer size reasonable (max 1 second)
            max_buffer_samples = self.config.sample_rate
            if len(self.audio_buffer) > max_buffer_samples:
                self.audio_buffer = self.audio_buffer[-max_buffer_samples:]
            
            # Process audio if we have enough data
            if len(self.audio_buffer) >= self.frame_size:
                processed_audio = self._process_audio_chunk(self.audio_buffer)
                
                # Extract the processed frame
                frame_start = len(self.audio_buffer) - self.frame_size
                processed_frame = processed_audio[frame_start:frame_start + self.frame_size]
                
                # Remove processed frame from buffer
                self.audio_buffer = self.audio_buffer[self.frame_size:]
                
                self.frame_count += 1
                self.processed_samples += len(processed_frame)
                
                # Convert back to bytes
                return self._float32_to_bytes(processed_frame)
            else:
                # Not enough data yet, return original frame
                return audio_frame
                
        except Exception as e:
            logger.error(f"Noise suppression processing error: {e}")
            return audio_frame  # Return original frame on error
    
    def _process_audio_chunk(self, audio_chunk: np.ndarray) -> np.ndarray:
        """
        Process an audio chunk for noise suppression.
        
        Args:
            audio_chunk: Audio data as float32 numpy array
            
        Returns:
            np.ndarray: Processed audio data
        """
        try:
            # Get processing parameters based on mode
            params = self._get_mode_parameters()
            
            # Apply noise reduction
            if self.is_noise_profile_ready and self.noise_profile is not None:
                # Use noise profile for better results
                processed_audio = nr.reduce_noise(
                    y=audio_chunk,
                    sr=self.config.sample_rate,
                    y_noise=self.noise_profile,
                    stationary=params["stationary"],
                    prop_decrease=params["prop_decrease"],
                    use_tqdm=params.get("use_tqdm", False)
                )
            else:
                # Use automatic noise detection
                processed_audio = nr.reduce_noise(
                    y=audio_chunk,
                    sr=self.config.sample_rate,
                    stationary=params["stationary"],
                    prop_decrease=params["prop_decrease"],
                    use_tqdm=params.get("use_tqdm", False)
                )
            
            # Ensure output is float32
            return processed_audio.astype(np.float32)
            
        except Exception as e:
            logger.error(f"Audio chunk processing error: {e}")
            return audio_chunk  # Return original on error
    
    def process_audio_chunk(self, audio_chunk: bytes) -> bytes:
        """
        Process a larger audio chunk by splitting it into frames.
        
        Args:
            audio_chunk: Raw audio chunk bytes (16-bit PCM, mono)
            
        Returns:
            bytes: Processed audio chunk bytes (16-bit PCM, mono)
        """
        processed_chunk = bytearray()
        frame_size_bytes = self.frame_size * 2
        
        for i in range(0, len(audio_chunk), frame_size_bytes):
            frame = audio_chunk[i:i + frame_size_bytes]
            if len(frame) == frame_size_bytes:
                processed_frame = self.process_frame(frame)
                processed_chunk.extend(processed_frame)
            else:
                # Handle partial frame at the end
                processed_chunk.extend(frame)
        
        return bytes(processed_chunk)
    
    def reset(self):
        """Reset noise suppressor state."""
        self.audio_buffer = np.array([], dtype=np.float32)
        self.frame_count = 0
        self.processed_samples = 0
        logger.debug("Noise suppressor state reset")
    
    def get_stats(self) -> dict:
        """Get current noise suppressor statistics."""
        return {
            "frame_count": self.frame_count,
            "processed_samples": self.processed_samples,
            "buffer_size": len(self.audio_buffer),
            "noise_profile_ready": self.is_noise_profile_ready,
            "mode": self.config.mode.value
        }


class NoiseSuppressionProcessor:
    """
    High-level noise suppression processor for real-time audio streams.
    
    This class provides a more convenient interface for processing
    continuous audio streams with noise suppression.
    """
    
    def __init__(self, config: Optional[NoiseSuppressionConfig] = None):
        """Initialize the noise suppression processor."""
        self.config = config or NoiseSuppressionConfig()
        self.suppressor = NoiseSuppressor(self.config)
        self.audio_buffer = bytearray()
        self.frame_size_bytes = self.suppressor.frame_size * 2
        
    def process_audio(self, audio_data: bytes) -> bytes:
        """
        Process incoming audio data and return noise-suppressed audio.
        
        Args:
            audio_data: Raw audio data (16-bit PCM, mono)
            
        Returns:
            bytes: Processed audio data (16-bit PCM, mono)
        """
        # Add new audio to buffer
        self.audio_buffer.extend(audio_data)
        
        processed_audio = bytearray()
        
        # Process complete frames from buffer
        while len(self.audio_buffer) >= self.frame_size_bytes:
            frame = bytes(self.audio_buffer[:self.frame_size_bytes])
            processed_frame = self.suppressor.process_frame(frame)
            processed_audio.extend(processed_frame)
            
            # Remove processed frame from buffer
            self.audio_buffer = self.audio_buffer[self.frame_size_bytes:]
        
        return bytes(processed_audio)
    
    def build_noise_profile(self, noise_sample: Union[bytes, np.ndarray], 
                          duration_seconds: float = 2.0) -> bool:
        """Build noise profile from background noise sample."""
        return self.suppressor.build_noise_profile(noise_sample, duration_seconds)
    
    def get_stats(self) -> dict:
        """Get noise suppression statistics."""
        return self.suppressor.get_stats()
    
    def reset(self):
        """Reset processor state."""
        self.suppressor.reset()
        self.audio_buffer.clear()
