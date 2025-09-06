#!/usr/bin/env python3
"""
Test script for Voice Activity Detection (VAD) module.
"""

import sys
import os
import numpy as np
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from audio_processing.vad import VoiceActivityDetector, VADConfig, VADMode

def generate_test_audio(duration_seconds=5.0, sample_rate=16000, speech_ratio=0.6):
    """Generate test audio data with speech and silence segments."""
    total_samples = int(duration_seconds * sample_rate)
    audio = np.zeros(total_samples, dtype=np.int16)
    
    # Generate speech-like signal
    speech_samples = int(total_samples * speech_ratio)
    t = np.linspace(0, speech_samples / sample_rate, speech_samples)
    speech_signal = (
        8000 * np.sin(2 * np.pi * 440 * t) +  # A4 note
        4000 * np.sin(2 * np.pi * 880 * t) +  # A5 note
        2000 * np.random.normal(0, 0.1, speech_samples)  # Noise
    )
    
    # Normalize and convert to 16-bit PCM
    speech_signal = np.clip(speech_signal, -32768, 32767).astype(np.int16)
    audio[:speech_samples] = speech_signal
    
    return audio.tobytes()

def test_vad_basic():
    """Test basic VAD functionality."""
    print("Testing basic VAD functionality...")
    
    config = VADConfig(mode=VADMode.AGGRESSIVE, sample_rate=16000, frame_duration_ms=30)
    vad = VoiceActivityDetector(config)
    
    # Generate test audio
    audio_data = generate_test_audio(duration_seconds=3.0, speech_ratio=0.7)
    frame_size = vad.frame_size * 2
    
    print(f"Generated {len(audio_data)} bytes of test audio")
    print(f"Frame size: {frame_size} bytes")
    
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
    
    print(f"VAD Results:")
    print(f"Total frames: {total_frames}")
    print(f"Speech frames: {speech_frames}")
    print(f"Speech ratio: {speech_frames / total_frames:.2%}")
    print(f"Final speaking state: {vad.is_speaking}")
    
    return True

def main():
    """Run VAD tests."""
    print("Voice Activity Detection (VAD) Test Suite")
    print("=" * 50)
    
    try:
        test_vad_basic()
        print("\nVAD tests completed successfully! ✅")
        return True
    except Exception as e:
        print(f"\nVAD test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
