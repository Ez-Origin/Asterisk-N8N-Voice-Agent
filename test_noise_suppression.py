#!/usr/bin/env python3
"""
Test script for noise suppression functionality.

This script tests the noise suppression module with sample audio data
and validates the processing pipeline.
"""

import sys
import os
import numpy as np
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from audio_processing.noise_suppression import (
    NoiseSuppressor,
    NoiseSuppressionProcessor,
    NoiseSuppressionConfig,
    NoiseSuppressionMode
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def generate_test_audio(duration_seconds: float = 5.0, sample_rate: int = 16000) -> np.ndarray:
    """Generate test audio with speech and noise."""
    # Generate a simple sine wave as "speech"
    t = np.linspace(0, duration_seconds, int(sample_rate * duration_seconds))
    speech = 0.3 * np.sin(2 * np.pi * 440 * t)  # 440Hz tone
    
    # Add some noise
    noise = 0.1 * np.random.randn(len(t))
    
    # Combine speech and noise
    audio = speech + noise
    
    # Normalize
    audio = audio / np.max(np.abs(audio))
    
    return audio.astype(np.float32)


def test_noise_suppressor():
    """Test the NoiseSuppressor class."""
    logger.info("Testing NoiseSuppressor...")
    
    # Test different modes
    for mode in NoiseSuppressionMode:
        if mode == NoiseSuppressionMode.CUSTOM:
            continue  # Skip custom mode for now
            
        logger.info(f"Testing mode: {mode.value}")
        
        # Create config
        config = NoiseSuppressionConfig(
            mode=mode,
            sample_rate=16000,
            frame_duration_ms=30,
            enable_logging=True
        )
        
        # Create suppressor
        suppressor = NoiseSuppressor(config)
        
        # Generate test audio
        test_audio = generate_test_audio(duration_seconds=2.0)
        
        # Convert to bytes (16-bit PCM)
        audio_int16 = (test_audio * 32767.0).astype(np.int16)
        audio_bytes = audio_int16.tobytes()
        
        # Process audio frame by frame
        frame_size = suppressor.frame_size * 2  # 2 bytes per sample
        processed_audio = bytearray()
        
        for i in range(0, len(audio_bytes), frame_size):
            frame = audio_bytes[i:i + frame_size]
            if len(frame) == frame_size:
                processed_frame = suppressor.process_frame(frame)
                processed_audio.extend(processed_frame)
        
        # Convert back to numpy array for analysis
        processed_int16 = np.frombuffer(processed_audio, dtype=np.int16)
        processed_float = processed_int16.astype(np.float32) / 32768.0
        
        # Calculate some basic metrics
        original_rms = np.sqrt(np.mean(test_audio**2))
        processed_rms = np.sqrt(np.mean(processed_float**2))
        
        logger.info(f"  Original RMS: {original_rms:.4f}")
        logger.info(f"  Processed RMS: {processed_rms:.4f}")
        logger.info(f"  Noise reduction: {((original_rms - processed_rms) / original_rms * 100):.1f}%")
        
        # Get stats
        stats = suppressor.get_stats()
        logger.info(f"  Stats: {stats}")
        
        # Reset for next test
        suppressor.reset()


def test_noise_suppression_processor():
    """Test the NoiseSuppressionProcessor class."""
    logger.info("Testing NoiseSuppressionProcessor...")
    
    # Create config
    config = NoiseSuppressionConfig(
        mode=NoiseSuppressionMode.MODERATE,
        sample_rate=16000,
        frame_duration_ms=30,
        enable_logging=True
    )
    
    # Create processor
    processor = NoiseSuppressionProcessor(config)
    
    # Generate test audio
    test_audio = generate_test_audio(duration_seconds=3.0)
    
    # Convert to bytes
    audio_int16 = (test_audio * 32767.0).astype(np.int16)
    audio_bytes = audio_int16.tobytes()
    
    # Process in chunks
    chunk_size = 1024  # Process in 1KB chunks
    processed_audio = bytearray()
    
    for i in range(0, len(audio_bytes), chunk_size):
        chunk = audio_bytes[i:i + chunk_size]
        processed_chunk = processor.process_audio(chunk)
        processed_audio.extend(processed_chunk)
    
    # Convert back to numpy array
    processed_int16 = np.frombuffer(processed_audio, dtype=np.int16)
    processed_float = processed_int16.astype(np.float32) / 32768.0
    
    # Calculate metrics
    original_rms = np.sqrt(np.mean(test_audio**2))
    processed_rms = np.sqrt(np.mean(processed_float**2))
    
    logger.info(f"  Original RMS: {original_rms:.4f}")
    logger.info(f"  Processed RMS: {processed_rms:.4f}")
    logger.info(f"  Noise reduction: {((original_rms - processed_rms) / original_rms * 100):.1f}%")
    
    # Get stats
    stats = processor.get_stats()
    logger.info(f"  Stats: {stats}")


def test_noise_profile():
    """Test noise profile building."""
    logger.info("Testing noise profile building...")
    
    # Create suppressor
    config = NoiseSuppressionConfig(mode=NoiseSuppressionMode.MODERATE)
    suppressor = NoiseSuppressor(config)
    
    # Generate noise sample
    noise_sample = generate_test_audio(duration_seconds=1.0)
    
    # Build noise profile
    success = suppressor.build_noise_profile(noise_sample, duration_seconds=0.5)
    
    if success:
        logger.info("  Noise profile built successfully")
        logger.info(f"  Profile ready: {suppressor.is_noise_profile_ready}")
    else:
        logger.error("  Failed to build noise profile")


def main():
    """Run all tests."""
    logger.info("Starting noise suppression tests...")
    
    try:
        test_noise_suppressor()
        test_noise_suppression_processor()
        test_noise_profile()
        
        logger.info("All tests completed successfully!")
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
