#!/usr/bin/env python3
"""
Test script for codec handler functionality.

This script tests the codec handler module with various codec types
and validates transcoding operations.
"""

import sys
import os
import numpy as np
import logging
import asyncio
from pathlib import Path
from typing import List

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from audio_processing.codec_handler import (
    CodecHandler,
    CodecManager,
    CodecConfig,
    CodecType,
    CodecInfo,
    CodecCapability
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def generate_test_audio(duration_seconds: float = 1.0, 
                       sample_rate: int = 16000) -> np.ndarray:
    """Generate test audio signal."""
    t = np.linspace(0, duration_seconds, int(sample_rate * duration_seconds))
    
    # Generate a complex signal with multiple frequencies
    signal = 0.3 * np.sin(2 * np.pi * 440 * t)  # 440Hz
    signal += 0.2 * np.sin(2 * np.pi * 880 * t)  # 880Hz
    signal += 0.1 * np.sin(2 * np.pi * 1320 * t)  # 1320Hz
    signal += 0.05 * np.random.randn(len(t))  # Add some noise
    
    # Normalize
    signal = signal / np.max(np.abs(signal))
    
    return signal.astype(np.float32)


def test_codec_handler_basic():
    """Test basic codec handler functionality."""
    logger.info("Testing basic codec handler functionality...")
    
    # Create codec handler
    config = CodecConfig(enable_logging=True)
    handler = CodecHandler(config)
    
    # Test supported codecs
    supported_codecs = handler.get_supported_codecs()
    logger.info(f"  Supported codecs: {[c.codec_type.value for c in supported_codecs]}")
    
    # Test codec info retrieval
    for codec_type in CodecType:
        info = handler.get_codec_info(codec_type)
        if info:
            logger.info(f"  {codec_type.value}: {info.description}")
        else:
            logger.warning(f"  {codec_type.value}: Not supported")
    
    # Test codec negotiation
    remote_codecs = ["G722", "PCMU", "PCMA"]
    negotiated = handler.negotiate_codec(remote_codecs)
    logger.info(f"  Negotiated codec: {negotiated.value if negotiated else 'None'}")
    
    # Test with different preferences
    custom_preferences = [CodecType.G711_ULAW, CodecType.G711_ALAW]
    negotiated2 = handler.negotiate_codec(remote_codecs, custom_preferences)
    logger.info(f"  Negotiated with custom preferences: {negotiated2.value if negotiated2 else 'None'}")
    
    # Test with unsupported codecs
    unsupported_codecs = ["G729", "G723"]
    negotiated3 = handler.negotiate_codec(unsupported_codecs)
    logger.info(f"  Negotiated with unsupported codecs: {negotiated3.value if negotiated3 else 'None'}")
    
    handler.close()


def test_codec_transcoding():
    """Test codec transcoding functionality."""
    logger.info("Testing codec transcoding...")
    
    # Create codec handler
    config = CodecConfig(enable_logging=True)
    handler = CodecHandler(config)
    
    # Generate test audio
    test_audio = generate_test_audio(duration_seconds=0.5, sample_rate=16000)
    pcm_data = test_audio.astype(np.float32).tobytes()
    
    # Test transcoding between different codecs
    test_cases = [
        (CodecType.PCM, CodecType.G711_ULAW),
        (CodecType.PCM, CodecType.G711_ALAW),
        (CodecType.PCM, CodecType.G722),
        (CodecType.G711_ULAW, CodecType.PCM),
        (CodecType.G711_ALAW, CodecType.PCM),
        (CodecType.G722, CodecType.PCM),
        (CodecType.G711_ULAW, CodecType.G711_ALAW),
        (CodecType.G711_ALAW, CodecType.G711_ULAW),
    ]
    
    for from_codec, to_codec in test_cases:
        try:
            logger.info(f"  Testing {from_codec.value} -> {to_codec.value}")
            
            # Prepare input data
            if from_codec == CodecType.PCM:
                input_data = pcm_data
            else:
                # First convert PCM to source codec
                input_data = handler.transcode(pcm_data, CodecType.PCM, from_codec)
            
            # Transcode
            output_data = handler.transcode(input_data, from_codec, to_codec)
            
            # Validate output
            is_valid = handler.validate_audio_data(output_data, to_codec)
            
            logger.info(f"    Input size: {len(input_data)} bytes")
            logger.info(f"    Output size: {len(output_data)} bytes")
            logger.info(f"    Valid: {is_valid}")
            
        except Exception as e:
            logger.error(f"    Error: {e}")
    
    # Test statistics
    stats = handler.get_codec_stats()
    logger.info(f"  Transcoding stats: {stats}")
    
    handler.close()


def test_codec_validation():
    """Test codec validation functionality."""
    logger.info("Testing codec validation...")
    
    # Create codec handler
    config = CodecConfig(enable_logging=True)
    handler = CodecHandler(config)
    
    # Generate test data
    test_audio = generate_test_audio(duration_seconds=0.1, sample_rate=16000)
    pcm_data = test_audio.astype(np.float32).tobytes()
    
    # Test validation for different codecs
    codec_tests = [
        (CodecType.PCM, pcm_data, True),
        (CodecType.G711_ULAW, b'\x00\x01\x02\x03', True),
        (CodecType.G711_ALAW, b'\x00\x01\x02\x03', True),
        (CodecType.G722, b'\x00\x01\x02\x03', True),
        (CodecType.PCM, b'invalid', False),
        (CodecType.PCM, b'', False),
    ]
    
    for codec_type, data, expected in codec_tests:
        is_valid = handler.validate_audio_data(data, codec_type)
        status = "✓" if is_valid == expected else "✗"
        logger.info(f"  {status} {codec_type.value}: {is_valid} (expected: {expected})")
    
    handler.close()


def test_codec_manager():
    """Test codec manager functionality."""
    logger.info("Testing codec manager...")
    
    # Create codec manager
    config = CodecConfig(enable_logging=True)
    manager = CodecManager(config)
    
    # Create multiple handlers
    handler1 = manager.create_handler("handler_1", config)
    handler2 = manager.create_handler("handler_2", config)
    
    # Test handler management
    logger.info(f"  Created handlers: {list(manager.handlers.keys())}")
    
    # Test codec negotiation for handlers
    remote_codecs = ["G722", "PCMU"]
    
    negotiated1 = manager.negotiate_codec_for_handler("handler_1", remote_codecs)
    negotiated2 = manager.negotiate_codec_for_handler("handler_2", ["PCMA", "PCMU"])
    
    logger.info(f"  Handler 1 negotiated: {negotiated1.value if negotiated1 else 'None'}")
    logger.info(f"  Handler 2 negotiated: {negotiated2.value if negotiated2 else 'None'}")
    
    # Test transcoding for handlers
    test_audio = generate_test_audio(duration_seconds=0.1, sample_rate=16000)
    pcm_data = test_audio.astype(np.float32).tobytes()
    
    try:
        # Test transcoding through handler 1
        if negotiated1:
            ulaw_data = manager.transcode_for_handler("handler_1", pcm_data, CodecType.PCM, negotiated1)
            logger.info(f"  Handler 1 transcoded {len(pcm_data)} bytes -> {len(ulaw_data)} bytes")
        
        # Test transcoding through handler 2
        if negotiated2:
            alaw_data = manager.transcode_for_handler("handler_2", pcm_data, CodecType.PCM, negotiated2)
            logger.info(f"  Handler 2 transcoded {len(pcm_data)} bytes -> {len(alaw_data)} bytes")
    
    except Exception as e:
        logger.error(f"  Transcoding error: {e}")
    
    # Test statistics
    all_stats = manager.get_all_stats()
    logger.info(f"  All handler stats: {all_stats}")
    
    # Cleanup
    manager.close_all()
    logger.info("  All handlers closed")


async def test_async_transcoding():
    """Test asynchronous transcoding functionality."""
    logger.info("Testing async transcoding...")
    
    # Create codec handler
    config = CodecConfig(enable_logging=True)
    handler = CodecHandler(config)
    
    # Generate test audio
    test_audio = generate_test_audio(duration_seconds=0.1, sample_rate=16000)
    pcm_data = test_audio.astype(np.float32).tobytes()
    
    # Test async transcoding
    try:
        start_time = asyncio.get_event_loop().time()
        
        # Perform multiple async transcodes
        tasks = []
        for i in range(5):
            task = handler.transcode_async(pcm_data, CodecType.PCM, CodecType.G711_ULAW)
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        
        end_time = asyncio.get_event_loop().time()
        duration = end_time - start_time
        
        logger.info(f"  Completed {len(results)} async transcodes in {duration:.3f}s")
        logger.info(f"  Average time per transcode: {duration/len(results):.3f}s")
        
        # Verify results
        for i, result in enumerate(results):
            is_valid = handler.validate_audio_data(result, CodecType.G711_ULAW)
            logger.info(f"  Result {i+1}: {len(result)} bytes, valid: {is_valid}")
    
    except Exception as e:
        logger.error(f"  Async transcoding error: {e}")
    
    handler.close()


def test_codec_roundtrip():
    """Test codec roundtrip conversion."""
    logger.info("Testing codec roundtrip conversion...")
    
    # Create codec handler
    config = CodecConfig(enable_logging=True)
    handler = CodecHandler(config)
    
    # Generate test audio
    original_audio = generate_test_audio(duration_seconds=0.2, sample_rate=16000)
    original_pcm = original_audio.astype(np.float32).tobytes()
    
    # Test roundtrip for different codecs
    codecs_to_test = [CodecType.G711_ULAW, CodecType.G711_ALAW, CodecType.G722]
    
    for codec in codecs_to_test:
        try:
            logger.info(f"  Testing roundtrip for {codec.value}")
            
            # Convert to codec
            encoded_data = handler.transcode(original_pcm, CodecType.PCM, codec)
            
            # Convert back to PCM
            decoded_pcm = handler.transcode(encoded_data, codec, CodecType.PCM)
            
            # Compare original and decoded
            original_array = np.frombuffer(original_pcm, dtype=np.float32)
            decoded_array = np.frombuffer(decoded_pcm, dtype=np.float32)
            
            # Calculate similarity (correlation)
            if len(original_array) == len(decoded_array):
                correlation = np.corrcoef(original_array, decoded_array)[0, 1]
                logger.info(f"    Correlation: {correlation:.4f}")
            else:
                logger.warning(f"    Length mismatch: {len(original_array)} vs {len(decoded_array)}")
            
            logger.info(f"    Original: {len(original_pcm)} bytes")
            logger.info(f"    Encoded: {len(encoded_data)} bytes")
            logger.info(f"    Decoded: {len(decoded_pcm)} bytes")
        
        except Exception as e:
            logger.error(f"    Roundtrip error: {e}")
    
    handler.close()


def main():
    """Run all tests."""
    logger.info("Starting codec handler tests...")
    
    try:
        test_codec_handler_basic()
        test_codec_transcoding()
        test_codec_validation()
        test_codec_manager()
        
        # Run async test
        asyncio.run(test_async_transcoding())
        
        test_codec_roundtrip()
        
        logger.info("All tests completed successfully!")
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
