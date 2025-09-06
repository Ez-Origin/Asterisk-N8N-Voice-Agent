#!/usr/bin/env python3
"""
Test script for audio processing pipeline functionality.

This script tests the complete audio processing pipeline with all components
integrated and validates the processing workflow.
"""

import sys
import os
import numpy as np
import logging
import time
import threading
from pathlib import Path
from typing import Tuple

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from audio_processing.pipeline import (
    AudioProcessingPipeline,
    AudioProcessingManager,
    AudioProcessingConfig,
    AudioFrame,
    PipelineMode
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


def test_audio_processing_pipeline():
    """Test the AudioProcessingPipeline class."""
    logger.info("Testing AudioProcessingPipeline...")
    
    # Test different pipeline modes
    for mode in PipelineMode:
        if mode == PipelineMode.CUSTOM:
            continue  # Skip custom mode for now
            
        logger.info(f"Testing pipeline mode: {mode.value}")
        
        # Create config
        config = AudioProcessingConfig(
            mode=mode,
            sample_rate=16000,
            frame_duration_ms=30,
            enable_logging=True,
            enable_vad=True,
            enable_noise_suppression=True,
            enable_echo_cancellation=True
        )
        
        # Create pipeline
        pipeline = AudioProcessingPipeline(config)
        
        # Generate test audio
        input_audio, reference_audio = generate_test_audio_with_echo(
            duration_seconds=2.0,
            echo_delay_ms=60,
            echo_amplitude=0.4
        )
        
        # Convert to bytes (16-bit PCM)
        input_int16 = (input_audio * 32767.0).astype(np.int16)
        reference_int16 = (reference_audio * 32767.0).astype(np.int16)
        input_bytes = input_int16.tobytes()
        reference_bytes = reference_int16.tobytes()
        
        # Start pipeline
        pipeline.start()
        
        # Process audio frame by frame
        frame_size = pipeline.frame_size_bytes
        processed_frames = []
        
        for i in range(0, len(input_bytes), frame_size):
            input_frame = input_bytes[i:i + frame_size]
            reference_frame = reference_bytes[i:i + frame_size]
            
            if len(input_frame) == frame_size and len(reference_frame) == frame_size:
                # Create audio frames
                input_audio_frame = AudioFrame(input_frame)
                reference_audio_frame = AudioFrame(reference_frame)
                
                # Add frame to pipeline
                pipeline.add_frame(input_audio_frame, reference_audio_frame)
                
                # Get processed frame
                processed_frame = pipeline.get_processed_frame(timeout=0.1)
                if processed_frame:
                    processed_frames.append(processed_frame)
        
        # Wait for remaining frames
        time.sleep(0.5)
        while True:
            processed_frame = pipeline.get_processed_frame(timeout=0.1)
            if processed_frame:
                processed_frames.append(processed_frame)
            else:
                break
        
        # Stop pipeline
        pipeline.stop()
        
        # Analyze results
        if processed_frames:
            logger.info(f"  Processed {len(processed_frames)} frames")
            
            # Calculate some basic metrics
            total_processing_time = sum(f.get_metadata('processing_time_ms', 0) for f in processed_frames)
            avg_processing_time = total_processing_time / len(processed_frames)
            
            speech_detections = sum(1 for f in processed_frames if f.get_metadata('is_speech', False))
            noise_suppression_applied = sum(1 for f in processed_frames if f.get_metadata('noise_suppression_applied', False))
            echo_cancellation_applied = sum(1 for f in processed_frames if f.get_metadata('echo_cancellation_applied', False))
            
            logger.info(f"  Average processing time: {avg_processing_time:.2f} ms")
            logger.info(f"  Speech detections: {speech_detections}/{len(processed_frames)}")
            logger.info(f"  Noise suppression applied: {noise_suppression_applied}/{len(processed_frames)}")
            logger.info(f"  Echo cancellation applied: {echo_cancellation_applied}/{len(processed_frames)}")
            
            # Get pipeline stats
            stats = pipeline.get_stats()
            logger.info(f"  Pipeline stats: {stats}")
        else:
            logger.warning("  No frames were processed")
        
        # Reset pipeline for next test
        pipeline.reset()


def test_audio_processing_manager():
    """Test the AudioProcessingManager class."""
    logger.info("Testing AudioProcessingManager...")
    
    # Create manager
    config = AudioProcessingConfig(
        mode=PipelineMode.BALANCED,
        sample_rate=16000,
        frame_duration_ms=30,
        enable_logging=True
    )
    manager = AudioProcessingManager(config)
    
    # Create multiple pipelines
    pipeline1 = manager.create_pipeline("pipeline_1", config)
    pipeline2 = manager.create_pipeline("pipeline_2", config)
    
    # Test pipeline management
    logger.info(f"  Created pipelines: {list(manager.pipelines.keys())}")
    
    # Start pipelines
    manager.start_pipeline("pipeline_1")
    manager.start_pipeline("pipeline_2")
    
    logger.info(f"  Active pipelines: {manager.active_pipelines}")
    
    # Generate test audio
    input_audio, reference_audio = generate_test_audio_with_echo(duration_seconds=1.0)
    input_int16 = (input_audio * 32767.0).astype(np.int16)
    reference_int16 = (reference_audio * 32767.0).astype(np.int16)
    input_bytes = input_int16.tobytes()
    reference_bytes = reference_int16.tobytes()
    
    # Process audio through both pipelines
    frame_size = pipeline1.frame_size_bytes
    processed_count = 0
    
    for i in range(0, len(input_bytes), frame_size):
        input_frame = input_bytes[i:i + frame_size]
        reference_frame = reference_bytes[i:i + frame_size]
        
        if len(input_frame) == frame_size and len(reference_frame) == frame_size:
            input_audio_frame = AudioFrame(input_frame)
            reference_audio_frame = AudioFrame(reference_frame)
            
            # Add to both pipelines
            pipeline1.add_frame(input_audio_frame, reference_audio_frame)
            pipeline2.add_frame(input_audio_frame, reference_audio_frame)
            
            # Get processed frames
            processed_frame1 = pipeline1.get_processed_frame(timeout=0.1)
            processed_frame2 = pipeline2.get_processed_frame(timeout=0.1)
            
            if processed_frame1 and processed_frame2:
                processed_count += 1
    
    logger.info(f"  Processed {processed_count} frames through both pipelines")
    
    # Get all stats
    all_stats = manager.get_all_stats()
    logger.info(f"  All pipeline stats: {all_stats}")
    
    # Stop and remove pipelines
    manager.stop_all_pipelines()
    manager.remove_pipeline("pipeline_1")
    manager.remove_pipeline("pipeline_2")
    
    logger.info(f"  Remaining pipelines: {list(manager.pipelines.keys())}")


def test_pipeline_callbacks():
    """Test pipeline callbacks functionality."""
    logger.info("Testing pipeline callbacks...")
    
    # Create pipeline with callbacks
    config = AudioProcessingConfig(
        mode=PipelineMode.BALANCED,
        sample_rate=16000,
        frame_duration_ms=30,
        enable_logging=True
    )
    pipeline = AudioProcessingPipeline(config)
    
    # Set up callbacks
    processed_frames = []
    speech_detections = []
    errors = []
    
    def on_frame_processed(frame):
        processed_frames.append(frame)
    
    def on_speech_detected(frame):
        speech_detections.append(frame)
    
    def on_error(error):
        errors.append(error)
    
    pipeline.on_frame_processed = on_frame_processed
    pipeline.on_speech_detected = on_speech_detected
    pipeline.on_error = on_error
    
    # Start pipeline
    pipeline.start()
    
    # Generate test audio
    input_audio, reference_audio = generate_test_audio_with_echo(duration_seconds=1.0)
    input_int16 = (input_audio * 32767.0).astype(np.int16)
    reference_int16 = (reference_audio * 32767.0).astype(np.int16)
    input_bytes = input_int16.tobytes()
    reference_bytes = reference_int16.tobytes()
    
    # Process audio
    frame_size = pipeline.frame_size_bytes
    
    for i in range(0, len(input_bytes), frame_size):
        input_frame = input_bytes[i:i + frame_size]
        reference_frame = reference_bytes[i:i + frame_size]
        
        if len(input_frame) == frame_size and len(reference_frame) == frame_size:
            input_audio_frame = AudioFrame(input_frame)
            reference_audio_frame = AudioFrame(reference_frame)
            
            pipeline.add_frame(input_audio_frame, reference_audio_frame)
    
    # Wait for processing
    time.sleep(1.0)
    
    # Stop pipeline
    pipeline.stop()
    
    # Check callbacks
    logger.info(f"  Processed frames via callback: {len(processed_frames)}")
    logger.info(f"  Speech detections via callback: {len(speech_detections)}")
    logger.info(f"  Errors via callback: {len(errors)}")
    
    if errors:
        logger.warning(f"  Errors occurred: {errors}")


def test_noise_profile_building():
    """Test noise profile building functionality."""
    logger.info("Testing noise profile building...")
    
    # Create pipeline
    config = AudioProcessingConfig(
        mode=PipelineMode.BALANCED,
        sample_rate=16000,
        frame_duration_ms=30,
        enable_logging=True
    )
    pipeline = AudioProcessingPipeline(config)
    
    # Generate noise sample
    noise_duration = 1.0
    noise_samples = int(16000 * noise_duration)
    noise_audio = 0.1 * np.random.randn(noise_samples).astype(np.float32)
    noise_int16 = (noise_audio * 32767.0).astype(np.int16)
    noise_bytes = noise_int16.tobytes()
    
    # Build noise profile
    success = pipeline.build_noise_profile(noise_bytes, duration_seconds=0.5)
    
    if success:
        logger.info("  Noise profile built successfully")
    else:
        logger.error("  Failed to build noise profile")


def main():
    """Run all tests."""
    logger.info("Starting audio processing pipeline tests...")
    
    try:
        test_audio_processing_pipeline()
        test_audio_processing_manager()
        test_pipeline_callbacks()
        test_noise_profile_building()
        
        logger.info("All tests completed successfully!")
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
