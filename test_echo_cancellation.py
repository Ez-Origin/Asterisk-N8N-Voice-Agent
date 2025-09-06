#!/usr/bin/env python3
"""
Test script for echo cancellation functionality.

This script tests the echo cancellation module with sample audio data
and validates the processing pipeline.
"""

import sys
import os
import numpy as np
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from audio_processing.echo_cancellation import (
    EchoCanceller,
    EchoCancellationProcessor,
    EchoCancellationConfig,
    EchoCancellationMode
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def generate_test_audio_with_echo(duration_seconds: float = 3.0, 
                                sample_rate: int = 16000,
                                echo_delay_ms: int = 50,
                                echo_amplitude: float = 0.3) -> Tuple[np.ndarray, np.ndarray]:
    """Generate test audio with simulated echo."""
    # Generate original signal (speech-like)
    t = np.linspace(0, duration_seconds, int(sample_rate * duration_seconds))
    original_signal = 0.5 * np.sin(2 * np.pi * 440 * t)  # 440Hz tone
    
    # Add some variation to make it more speech-like
    original_signal += 0.2 * np.sin(2 * np.pi * 880 * t)  # 880Hz harmonic
    original_signal += 0.1 * np.random.randn(len(t))  # Add some noise
    
    # Normalize
    original_signal = original_signal / np.max(np.abs(original_signal))
    
    # Create echo by delaying and attenuating the original signal
    echo_delay_samples = int(echo_delay_ms * sample_rate / 1000)
    echo_signal = np.zeros_like(original_signal)
    echo_signal[echo_delay_samples:] = echo_amplitude * original_signal[:-echo_delay_samples]
    
    # Create input signal (original + echo)
    input_signal = original_signal + echo_signal
    
    # Add some noise
    input_signal += 0.05 * np.random.randn(len(input_signal))
    
    # Normalize both signals
    input_signal = input_signal / np.max(np.abs(input_signal))
    original_signal = original_signal / np.max(np.abs(original_signal))
    
    return input_signal.astype(np.float32), original_signal.astype(np.float32)


def test_echo_canceller():
    """Test the EchoCanceller class."""
    logger.info("Testing EchoCanceller...")
    
    # Test different modes
    for mode in EchoCancellationMode:
        if mode == EchoCancellationMode.CUSTOM:
            continue  # Skip custom mode for now
            
        logger.info(f"Testing mode: {mode.value}")
        
        # Create config
        config = EchoCancellationConfig(
            mode=mode,
            sample_rate=16000,
            frame_duration_ms=30,
            enable_logging=True
        )
        
        # Create canceller
        canceller = EchoCanceller(config)
        
        # Generate test audio with echo
        input_audio, reference_audio = generate_test_audio_with_echo(
            duration_seconds=2.0,
            echo_delay_ms=50,
            echo_amplitude=0.3
        )
        
        # Convert to bytes (16-bit PCM)
        input_int16 = (input_audio * 32767.0).astype(np.int16)
        reference_int16 = (reference_audio * 32767.0).astype(np.int16)
        input_bytes = input_int16.tobytes()
        reference_bytes = reference_int16.tobytes()
        
        # Process audio frame by frame
        frame_size = canceller.frame_size * 2  # 2 bytes per sample
        processed_audio = bytearray()
        
        for i in range(0, len(input_bytes), frame_size):
            input_frame = input_bytes[i:i + frame_size]
            reference_frame = reference_bytes[i:i + frame_size]
            
            if len(input_frame) == frame_size and len(reference_frame) == frame_size:
                processed_frame = canceller.process_frame(input_frame, reference_frame)
                processed_audio.extend(processed_frame)
        
        # Convert back to numpy array for analysis
        processed_int16 = np.frombuffer(processed_audio, dtype=np.int16)
        processed_float = processed_int16.astype(np.float32) / 32768.0
        
        # Calculate some basic metrics
        input_rms = np.sqrt(np.mean(input_audio**2))
        processed_rms = np.sqrt(np.mean(processed_float**2))
        reference_rms = np.sqrt(np.mean(reference_audio**2))
        
        # Calculate echo reduction
        echo_reduction = 20 * np.log10(input_rms / (processed_rms + 1e-10))
        
        logger.info(f"  Input RMS: {input_rms:.4f}")
        logger.info(f"  Processed RMS: {processed_rms:.4f}")
        logger.info(f"  Reference RMS: {reference_rms:.4f}")
        logger.info(f"  Echo reduction: {echo_reduction:.1f} dB")
        
        # Get stats
        stats = canceller.get_stats()
        logger.info(f"  Stats: {stats}")
        
        # Reset for next test
        canceller.reset()


def test_echo_cancellation_processor():
    """Test the EchoCancellationProcessor class."""
    logger.info("Testing EchoCancellationProcessor...")
    
    # Create config
    config = EchoCancellationConfig(
        mode=EchoCancellationMode.MODERATE,
        sample_rate=16000,
        frame_duration_ms=30,
        enable_logging=True
    )
    
    # Create processor
    processor = EchoCancellationProcessor(config)
    
    # Generate test audio with echo
    input_audio, reference_audio = generate_test_audio_with_echo(
        duration_seconds=3.0,
        echo_delay_ms=80,
        echo_amplitude=0.4
    )
    
    # Convert to bytes
    input_int16 = (input_audio * 32767.0).astype(np.int16)
    reference_int16 = (reference_audio * 32767.0).astype(np.int16)
    input_bytes = input_int16.tobytes()
    reference_bytes = reference_int16.tobytes()
    
    # Process in chunks
    chunk_size = 1024  # Process in 1KB chunks
    processed_audio = bytearray()
    
    for i in range(0, len(input_bytes), chunk_size):
        input_chunk = input_bytes[i:i + chunk_size]
        reference_chunk = reference_bytes[i:i + chunk_size]
        
        # Pad chunks if necessary
        if len(input_chunk) < chunk_size:
            input_chunk = input_chunk + b'\x00' * (chunk_size - len(input_chunk))
        if len(reference_chunk) < chunk_size:
            reference_chunk = reference_chunk + b'\x00' * (chunk_size - len(reference_chunk))
        
        processed_chunk = processor.process_audio(input_chunk, reference_chunk)
        processed_audio.extend(processed_chunk)
    
    # Convert back to numpy array
    processed_int16 = np.frombuffer(processed_audio, dtype=np.int16)
    processed_float = processed_int16.astype(np.float32) / 32768.0
    
    # Calculate metrics
    input_rms = np.sqrt(np.mean(input_audio**2))
    processed_rms = np.sqrt(np.mean(processed_float**2))
    reference_rms = np.sqrt(np.mean(reference_audio**2))
    
    echo_reduction = 20 * np.log10(input_rms / (processed_rms + 1e-10))
    
    logger.info(f"  Input RMS: {input_rms:.4f}")
    logger.info(f"  Processed RMS: {processed_rms:.4f}")
    logger.info(f"  Reference RMS: {reference_rms:.4f}")
    logger.info(f"  Echo reduction: {echo_reduction:.1f} dB")
    
    # Get stats
    stats = processor.get_stats()
    logger.info(f"  Stats: {stats}")


def test_echo_detection():
    """Test echo detection functionality."""
    logger.info("Testing echo detection...")
    
    # Create canceller
    config = EchoCancellationConfig(mode=EchoCancellationMode.MODERATE)
    canceller = EchoCanceller(config)
    
    # Generate test signals
    input_audio, reference_audio = generate_test_audio_with_echo(
        duration_seconds=1.0,
        echo_delay_ms=60,
        echo_amplitude=0.5
    )
    
    # Convert to bytes
    input_int16 = (input_audio * 32767.0).astype(np.int16)
    reference_int16 = (reference_audio * 32767.0).astype(np.int16)
    input_bytes = input_int16.tobytes()
    reference_bytes = reference_int16.tobytes()
    
    # Process frames and count echo detections
    frame_size = canceller.frame_size * 2
    echo_detections = 0
    total_frames = 0
    
    for i in range(0, len(input_bytes), frame_size):
        input_frame = input_bytes[i:i + frame_size]
        reference_frame = reference_bytes[i:i + frame_size]
        
        if len(input_frame) == frame_size and len(reference_frame) == frame_size:
            # Test echo detection
            input_float = canceller._bytes_to_float32(input_frame)
            reference_float = canceller._bytes_to_float32(reference_frame)
            
            echo_detected = canceller._detect_echo(input_float, reference_float)
            if echo_detected:
                echo_detections += 1
            total_frames += 1
    
    detection_rate = echo_detections / max(total_frames, 1)
    logger.info(f"  Echo detections: {echo_detections}/{total_frames}")
    logger.info(f"  Detection rate: {detection_rate:.2%}")


def main():
    """Run all tests."""
    logger.info("Starting echo cancellation tests...")
    
    try:
        test_echo_canceller()
        test_echo_cancellation_processor()
        test_echo_detection()
        
        logger.info("All tests completed successfully!")
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
