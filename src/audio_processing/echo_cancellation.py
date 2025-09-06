"""
Echo Cancellation module for real-time audio processing.

This module provides echo cancellation functionality using adaptive filtering
techniques to remove echo and feedback from audio streams.
"""

import logging
import numpy as np
from scipy import signal
from typing import Optional, Tuple, Union
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class EchoCancellationMode(Enum):
    """Echo cancellation processing modes."""
    LIGHT = "light"      # Minimal processing, preserves more audio
    MODERATE = "moderate"  # Balanced processing
    AGGRESSIVE = "aggressive"  # Heavy processing, may affect speech quality
    CUSTOM = "custom"    # User-defined parameters


@dataclass
class EchoCancellationConfig:
    """Configuration for Echo Cancellation."""
    mode: EchoCancellationMode = EchoCancellationMode.MODERATE
    sample_rate: int = 16000
    frame_duration_ms: int = 30
    enable_logging: bool = True
    
    # Adaptive filter parameters
    filter_length: int = 512  # Length of adaptive filter
    step_size: float = 0.01  # LMS step size (0.001-0.1)
    regularization: float = 1e-6  # Regularization factor
    
    # Echo detection parameters
    echo_threshold: float = 0.3  # Threshold for echo detection (0.0-1.0)
    min_echo_delay_ms: int = 10  # Minimum echo delay in milliseconds
    max_echo_delay_ms: int = 200  # Maximum echo delay in milliseconds
    
    # Advanced parameters (for CUSTOM mode)
    enable_nlms: bool = True  # Use Normalized LMS algorithm
    enable_rls: bool = False  # Use Recursive Least Squares (computationally expensive)
    enable_spectral_subtraction: bool = True  # Use spectral subtraction as backup


class EchoCanceller:
    """
    Real-time echo cancellation using adaptive filtering.
    
    This class provides echo cancellation for audio streams using
    adaptive filtering techniques like LMS and NLMS algorithms.
    """
    
    def __init__(self, config: Optional[EchoCancellationConfig] = None):
        """
        Initialize the Echo Canceller.
        
        Args:
            config: Echo cancellation configuration. If None, uses default config.
        """
        self.config = config or EchoCancellationConfig()
        
        # Calculate frame size based on sample rate and duration
        self.frame_size = int(self.config.sample_rate * self.config.frame_duration_ms / 1000)
        
        # Adaptive filter state
        self.filter_length = self.config.filter_length
        self.filter_coeffs = np.zeros(self.filter_length, dtype=np.float32)
        self.input_buffer = np.zeros(self.filter_length, dtype=np.float32)
        self.output_buffer = np.zeros(self.filter_length, dtype=np.float32)
        
        # Echo detection state
        self.echo_delay_samples = int(self.config.min_echo_delay_ms * self.config.sample_rate / 1000)
        self.max_echo_delay_samples = int(self.config.max_echo_delay_ms * self.config.sample_rate / 1000)
        
        # Processing state
        self.frame_count = 0
        self.processed_samples = 0
        self.echo_detected_count = 0
        self.adaptation_enabled = True
        
        # Performance metrics
        self.erle = 0.0  # Echo Return Loss Enhancement
        self.convergence_rate = 0.0
        
        if self.config.enable_logging:
            logger.info(f"Echo canceller initialized: mode={self.config.mode.value}, "
                       f"sample_rate={self.config.sample_rate}Hz, "
                       f"frame_duration={self.config.frame_duration_ms}ms, "
                       f"filter_length={self.filter_length}")
    
    def _get_mode_parameters(self) -> dict:
        """Get processing parameters based on the selected mode."""
        if self.config.mode == EchoCancellationMode.LIGHT:
            return {
                "step_size": 0.005,
                "regularization": 1e-5,
                "echo_threshold": 0.2,
                "enable_nlms": True,
                "enable_rls": False,
                "enable_spectral_subtraction": False
            }
        elif self.config.mode == EchoCancellationMode.MODERATE:
            return {
                "step_size": 0.01,
                "regularization": 1e-6,
                "echo_threshold": 0.3,
                "enable_nlms": True,
                "enable_rls": False,
                "enable_spectral_subtraction": True
            }
        elif self.config.mode == EchoCancellationMode.AGGRESSIVE:
            return {
                "step_size": 0.02,
                "regularization": 1e-7,
                "echo_threshold": 0.4,
                "enable_nlms": True,
                "enable_rls": True,
                "enable_spectral_subtraction": True
            }
        else:  # CUSTOM mode
            return {
                "step_size": self.config.step_size,
                "regularization": self.config.regularization,
                "echo_threshold": self.config.echo_threshold,
                "enable_nlms": self.config.enable_nlms,
                "enable_rls": self.config.enable_rls,
                "enable_spectral_subtraction": self.config.enable_spectral_subtraction
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
    
    def _detect_echo(self, input_signal: np.ndarray, output_signal: np.ndarray) -> bool:
        """
        Detect if echo is present in the signal.
        
        Args:
            input_signal: Input audio signal
            output_signal: Output audio signal (reference)
            
        Returns:
            bool: True if echo is detected
        """
        if len(input_signal) < self.echo_delay_samples:
            return False
        
        # Calculate cross-correlation to detect echo
        correlation = np.correlate(input_signal, output_signal, mode='valid')
        
        if len(correlation) == 0:
            return False
        
        # Find peak correlation
        max_corr = np.max(np.abs(correlation))
        correlation_threshold = self.config.echo_threshold * np.sqrt(len(input_signal))
        
        return max_corr > correlation_threshold
    
    def _lms_adaptation(self, error_signal: np.ndarray, input_signal: np.ndarray) -> None:
        """
        Update filter coefficients using LMS algorithm.
        
        Args:
            error_signal: Error signal (desired - output)
            input_signal: Input signal for adaptation
        """
        if len(input_signal) < self.filter_length:
            return
        
        # Get the last filter_length samples
        x = input_signal[-self.filter_length:]
        
        # LMS update rule: w(n+1) = w(n) + μ * e(n) * x(n)
        step_size = self.config.step_size
        self.filter_coeffs += step_size * error_signal * x
        
        # Apply regularization to prevent filter divergence
        self.filter_coeffs *= (1.0 - self.config.regularization)
    
    def _nlms_adaptation(self, error_signal: np.ndarray, input_signal: np.ndarray) -> None:
        """
        Update filter coefficients using Normalized LMS algorithm.
        
        Args:
            error_signal: Error signal (desired - output)
            input_signal: Input signal for adaptation
        """
        if len(input_signal) < self.filter_length:
            return
        
        # Get the last filter_length samples
        x = input_signal[-self.filter_length:]
        
        # Calculate input power
        input_power = np.dot(x, x) + self.config.regularization
        
        # NLMS update rule: w(n+1) = w(n) + μ * e(n) * x(n) / (x^T * x + δ)
        step_size = self.config.step_size / input_power
        self.filter_coeffs += step_size * error_signal * x
    
    def _apply_adaptive_filter(self, input_signal: np.ndarray) -> np.ndarray:
        """
        Apply adaptive filter to input signal.
        
        Args:
            input_signal: Input audio signal
            
        Returns:
            np.ndarray: Filtered output signal
        """
        if len(input_signal) < self.filter_length:
            # Not enough data, return original signal
            return input_signal
        
        # Apply convolution with current filter coefficients
        filtered_signal = np.convolve(input_signal, self.filter_coeffs, mode='same')
        
        return filtered_signal
    
    def _spectral_subtraction(self, input_signal: np.ndarray, 
                            noise_spectrum: np.ndarray) -> np.ndarray:
        """
        Apply spectral subtraction for echo reduction.
        
        Args:
            input_signal: Input audio signal
            noise_spectrum: Estimated noise spectrum
            
        Returns:
            np.ndarray: Processed signal
        """
        # Compute FFT
        fft_size = min(1024, len(input_signal))
        input_fft = np.fft.fft(input_signal, n=fft_size)
        
        # Estimate noise spectrum if not provided
        if noise_spectrum is None or len(noise_spectrum) != fft_size:
            noise_spectrum = np.abs(input_fft) * 0.1  # Simple noise estimation
        
        # Calculate spectral subtraction gain
        input_magnitude = np.abs(input_fft)
        noise_magnitude = np.abs(noise_spectrum)
        
        # Avoid division by zero
        gain = np.maximum(1.0 - noise_magnitude / (input_magnitude + 1e-10), 0.1)
        
        # Apply gain
        processed_fft = input_fft * gain
        
        # Convert back to time domain
        processed_signal = np.real(np.fft.ifft(processed_fft))
        
        # Ensure same length as input
        if len(processed_signal) != len(input_signal):
            processed_signal = processed_signal[:len(input_signal)]
        
        return processed_signal
    
    def process_frame(self, input_frame: bytes, reference_frame: bytes) -> bytes:
        """
        Process a single audio frame for echo cancellation.
        
        Args:
            input_frame: Input audio frame bytes (16-bit PCM, mono)
            reference_frame: Reference audio frame bytes (speaker output)
            
        Returns:
            bytes: Processed audio frame bytes (16-bit PCM, mono)
            
        Raises:
            ValueError: If audio frame size is incorrect
        """
        if len(input_frame) != self.frame_size * 2:  # 2 bytes per sample (16-bit)
            raise ValueError(f"Invalid input frame size: expected {self.frame_size * 2} bytes, "
                           f"got {len(input_frame)} bytes")
        
        if len(reference_frame) != self.frame_size * 2:
            raise ValueError(f"Invalid reference frame size: expected {self.frame_size * 2} bytes, "
                           f"got {len(reference_frame)} bytes")
        
        try:
            # Convert to float32 for processing
            input_audio = self._bytes_to_float32(input_frame)
            reference_audio = self._bytes_to_float32(reference_frame)
            
            # Update input buffer
            self.input_buffer = np.roll(self.input_buffer, -len(input_audio))
            self.input_buffer[-len(input_audio):] = input_audio
            
            # Update output buffer
            self.output_buffer = np.roll(self.output_buffer, -len(reference_audio))
            self.output_buffer[-len(reference_audio):] = reference_audio
            
            # Detect echo
            echo_detected = self._detect_echo(input_audio, reference_audio)
            if echo_detected:
                self.echo_detected_count += 1
            
            # Apply adaptive filtering
            if self.adaptation_enabled and echo_detected:
                # Apply adaptive filter
                filtered_audio = self._apply_adaptive_filter(input_audio)
                
                # Calculate error signal for adaptation
                error_signal = input_audio - filtered_audio
                
                # Update filter coefficients
                params = self._get_mode_parameters()
                if params["enable_nlms"]:
                    self._nlms_adaptation(error_signal, self.input_buffer)
                else:
                    self._lms_adaptation(error_signal, self.input_buffer)
                
                # Calculate ERLE (Echo Return Loss Enhancement)
                if np.var(input_audio) > 1e-10:
                    self.erle = 10 * np.log10(np.var(input_audio) / np.var(error_signal))
                
                processed_audio = filtered_audio
            else:
                # No echo detected or adaptation disabled, return original
                processed_audio = input_audio
            
            # Apply spectral subtraction if enabled
            params = self._get_mode_parameters()
            if params["enable_spectral_subtraction"] and echo_detected:
                processed_audio = self._spectral_subtraction(processed_audio, None)
            
            # Ensure output is within valid range
            processed_audio = np.clip(processed_audio, -1.0, 1.0)
            
            self.frame_count += 1
            self.processed_samples += len(processed_audio)
            
            # Convert back to bytes
            return self._float32_to_bytes(processed_audio)
            
        except Exception as e:
            logger.error(f"Echo cancellation processing error: {e}")
            return input_frame  # Return original frame on error
    
    def process_audio_chunk(self, input_chunk: bytes, reference_chunk: bytes) -> bytes:
        """
        Process a larger audio chunk by splitting it into frames.
        
        Args:
            input_chunk: Input audio chunk bytes (16-bit PCM, mono)
            reference_chunk: Reference audio chunk bytes (16-bit PCM, mono)
            
        Returns:
            bytes: Processed audio chunk bytes (16-bit PCM, mono)
        """
        processed_chunk = bytearray()
        frame_size_bytes = self.frame_size * 2
        
        for i in range(0, len(input_chunk), frame_size_bytes):
            input_frame = input_chunk[i:i + frame_size_bytes]
            reference_frame = reference_chunk[i:i + frame_size_bytes]
            
            if len(input_frame) == frame_size_bytes and len(reference_frame) == frame_size_bytes:
                processed_frame = self.process_frame(input_frame, reference_frame)
                processed_chunk.extend(processed_frame)
            else:
                # Handle partial frames at the end
                processed_chunk.extend(input_frame)
        
        return bytes(processed_chunk)
    
    def enable_adaptation(self, enabled: bool = True):
        """Enable or disable filter adaptation."""
        self.adaptation_enabled = enabled
        if self.config.enable_logging:
            logger.info(f"Echo cancellation adaptation {'enabled' if enabled else 'disabled'}")
    
    def reset(self):
        """Reset echo canceller state."""
        self.filter_coeffs.fill(0.0)
        self.input_buffer.fill(0.0)
        self.output_buffer.fill(0.0)
        self.frame_count = 0
        self.processed_samples = 0
        self.echo_detected_count = 0
        self.erle = 0.0
        self.convergence_rate = 0.0
        logger.debug("Echo canceller state reset")
    
    def get_stats(self) -> dict:
        """Get current echo canceller statistics."""
        return {
            "frame_count": self.frame_count,
            "processed_samples": self.processed_samples,
            "echo_detected_count": self.echo_detected_count,
            "echo_detection_rate": self.echo_detected_count / max(self.frame_count, 1),
            "erle_db": self.erle,
            "adaptation_enabled": self.adaptation_enabled,
            "filter_length": self.filter_length,
            "mode": self.config.mode.value
        }


class EchoCancellationProcessor:
    """
    High-level echo cancellation processor for real-time audio streams.
    
    This class provides a more convenient interface for processing
    continuous audio streams with echo cancellation.
    """
    
    def __init__(self, config: Optional[EchoCancellationConfig] = None):
        """Initialize the echo cancellation processor."""
        self.config = config or EchoCancellationConfig()
        self.canceller = EchoCanceller(self.config)
        self.input_buffer = bytearray()
        self.reference_buffer = bytearray()
        self.frame_size_bytes = self.canceller.frame_size * 2
        
    def process_audio(self, input_audio: bytes, reference_audio: bytes) -> bytes:
        """
        Process incoming audio data and return echo-cancelled audio.
        
        Args:
            input_audio: Input audio data (16-bit PCM, mono)
            reference_audio: Reference audio data (speaker output, 16-bit PCM, mono)
            
        Returns:
            bytes: Processed audio data (16-bit PCM, mono)
        """
        # Add new audio to buffers
        self.input_buffer.extend(input_audio)
        self.reference_buffer.extend(reference_audio)
        
        processed_audio = bytearray()
        
        # Process complete frames from buffers
        while (len(self.input_buffer) >= self.frame_size_bytes and 
               len(self.reference_buffer) >= self.frame_size_bytes):
            
            input_frame = bytes(self.input_buffer[:self.frame_size_bytes])
            reference_frame = bytes(self.reference_buffer[:self.frame_size_bytes])
            
            processed_frame = self.canceller.process_frame(input_frame, reference_frame)
            processed_audio.extend(processed_frame)
            
            # Remove processed frames from buffers
            self.input_buffer = self.input_buffer[self.frame_size_bytes:]
            self.reference_buffer = self.reference_buffer[self.frame_size_bytes:]
        
        return bytes(processed_audio)
    
    def enable_adaptation(self, enabled: bool = True):
        """Enable or disable filter adaptation."""
        self.canceller.enable_adaptation(enabled)
    
    def get_stats(self) -> dict:
        """Get echo cancellation statistics."""
        return self.canceller.get_stats()
    
    def reset(self):
        """Reset processor state."""
        self.canceller.reset()
        self.input_buffer.clear()
        self.reference_buffer.clear()
