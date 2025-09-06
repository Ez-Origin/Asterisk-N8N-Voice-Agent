#!/usr/bin/env python3
"""
Test script for Voice Activity Detection (VAD) module.

This script tests the VAD functionality with sample audio data.
"""

import sys
import os
import numpy as np
import time
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from audio_processing.vad import VoiceActivityDetector, VADProcessor, VADConfig, VADMode


def generate_test_audio(duration_seconds: float = 5.0, 
                       sample_rate: int = 16000,
                       speech_ratio: float = 0.6) -> bytes:
    """
    Generate test audio data with speech and silence segments.
    
    Args:
        duration_seconds: Total duration in seconds
        sample_rate: Sample rate in Hz
        speech_ratio: Ratio of speech to silence
        
    Returns:
        bytes: 16-bit PCM audio data
    """
    total_samples = int(duration_seconds * sample_rate)
    audio = np.zeros(total_samples, dtype=np.int16)
    
    # Generate speech-like signal (sine wave with noise)
    speech_samples = int(total_samples * speech_ratio)
    silence_samples = total_samples - speech_samples
    
    # Create speech segments
    speech_start = 0
    speech_end = speech_samples
    
    # Generate speech signal (multiple sine waves + noise)
    t = np.linspace(0, speech_samples / sample_rate, speech_samples)
    speech_signal = (
        8000 * np.sin(2 * np.pi * 440 * t) +  # A4 note
        4000 * np.sin(2 * np.pi * 880 * t) +  # A5 note
        2000 * np.random.normal(0, 0.1, speech_samples)  # Noise
    )
    
    # Normalize and convert to 16-bit PCM
    speech_signal = np.clip(speech_signal, -32768, 32767).astype(np.int16)
    audio[speech_start:speech_end] = speech_signal
    
    # Silence segments remain as zeros
    
    return audio.tobytes()


def test_vad_basic():
    """Test basic VAD functionality."""
    print("Testing basic VAD functionality...")
    
    # Create VAD with default config
    config = VADConfig(
        mode=VADMode.AGGRESSIVE,
        sample_rate=16000,
        frame_duration_ms=30,
        enable_logging=True
    )
    
    vad = VoiceActivityDetector(config)
    
    # Generate test audio
    audio_data = generate_test_audio(duration_seconds=3.0, speech_ratio=0.7)
    frame_size = vad.frame_size * 2  # 2 bytes per sample
    
    print(f"Generated {len(audio_data)} bytes of test audio")
    print(f"Frame size: {frame_size} bytes")
    print(f"Number of frames: {len(audio_data) // frame_size}")
    
    # Process audio frame by frame
    speech_frames = 0
    total_frames = 0
    
    for i in range(0, len(audio_data), frame_size):
        frame = audio_data[i:i + frame_size]
        if len(frame) == frame_size:
            is_speech = vad.process_frame(frame)
            if is_speech:
                speech_frames += 1
            total_frames += 1
            
            if total_frames % 50 == 0:  # Print every 50 frames
                print(f"Frame {total_frames}: {'SPEECH' if is_speech else 'SILENCE'}")
    
    print(f"\nVAD Results:")
    print(f"Total frames processed: {total_frames}")
    print(f"Speech frames detected: {speech_frames}")
    print(f"Speech ratio: {speech_frames / total_frames:.2%}")
    print(f"Final speaking state: {vad.is_speaking}")
    
    # Test speech segment detection
    segments = vad.get_speech_segments(audio_data, min_segment_duration_ms=200)
    print(f"Speech segments detected: {len(segments)}")
    for i, (start, end) in enumerate(segments):
        duration_ms = (end - start) * config.frame_duration_ms
        print(f"  Segment {i+1}: frames {start}-{end} ({duration_ms:.1f}ms)")
    
    return True


def test_vad_processor():
    """Test VAD processor for continuous audio streams."""
    print("\nTesting VAD processor for continuous streams...")
    
    config = VADConfig(
        mode=VADMode.AGGRESSIVE,
        sample_rate=16000,
        frame_duration_ms=30,
        enable_logging=False
    )
    
    processor = VADProcessor(config)
    
    # Generate test audio
    audio_data = generate_test_audio(duration_seconds=2.0, speech_ratio=0.5)
    
    # Process in chunks to simulate real-time streaming
    chunk_size = 480  # 30ms at 16kHz (480 samples = 960 bytes)
    results = []
    
    for i in range(0, len(audio_data), chunk_size):
        chunk = audio_data[i:i + chunk_size]
        chunk_results = processor.process_audio(chunk)
        results.extend(chunk_results)
        
        # Check speaking state
        if processor.is_currently_speaking():
            print(f"Chunk {i//chunk_size}: SPEECH detected")
    
    print(f"Processed {len(results)} frames from stream")
    print(f"Speech frames: {sum(results)}")
    print(f"Final speaking state: {processor.is_currently_speaking()}")
    
    return True


def test_vad_modes():
    """Test different VAD sensitivity modes."""
    print("\nTesting different VAD sensitivity modes...")
    
    # Generate test audio with mixed content
    audio_data = generate_test_audio(duration_seconds=2.0, speech_ratio=0.4)
    frame_size = 480 * 2  # 30ms at 16kHz
    
    modes = [VADMode.QUALITY, VADMode.LOW_BITRATE, VADMode.AGGRESSIVE, VADMode.VERY_AGGRESSIVE]
    
    for mode in modes:
        config = VADConfig(mode=mode, enable_logging=False)
        vad = VoiceActivityDetector(config)
        
        speech_frames = 0
        total_frames = 0
        
        for i in range(0, len(audio_data), frame_size):
            frame = audio_data[i:i + frame_size]
            if len(frame) == frame_size:
                is_speech = vad.process_frame(frame)
                if is_speech:
                    speech_frames += 1
                total_frames += 1
        
        speech_ratio = speech_frames / total_frames if total_frames > 0 else 0
        print(f"{mode.name:15}: {speech_frames:3d}/{total_frames:3d} frames ({speech_ratio:.1%})")
    
    return True


def main():
    """Run all VAD tests."""
    print("Voice Activity Detection (VAD) Test Suite")
    print("=" * 50)
    
    try:
        # Test basic functionality
        test_vad_basic()
        
        # Test processor
        test_vad_processor()
        
        # Test different modes
        test_vad_modes()
        
        print("\n" + "=" * 50)
        print("All VAD tests completed successfully! ✅")
        
    except Exception as e:
        print(f"\nVAD test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)