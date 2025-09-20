#!/usr/bin/env python3
"""
Test combined audio files with STT to analyze speech detection and transcription accuracy.
This script combines multiple 20ms frames into longer audio segments for better STT testing.
"""

import asyncio
import websockets
import base64
import json
import logging
import os
import glob
import struct
import time
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

LOCAL_AI_SERVER_URL = "ws://localhost:8765/ws"

def combine_audio_frames(file_groups: dict, frames_per_segment: int = 50):
    """Combine multiple 20ms frames into longer audio segments for STT testing"""
    logging.info(f"Combining audio frames into segments of {frames_per_segment} frames each")
    
    combined_segments = []
    
    for file_type, files in file_groups.items():
        logging.info(f"Processing {file_type} files...")
        
        # Sort files by timestamp (filename contains timestamp)
        sorted_files = sorted(files)
        
        # Group files into segments
        for i in range(0, len(sorted_files), frames_per_segment):
            segment_files = sorted_files[i:i+frames_per_segment]
            if len(segment_files) < 10:  # Skip segments with too few files
                continue
                
            # Combine audio data
            combined_audio = b""
            for filepath in segment_files:
                try:
                    with open(filepath, "rb") as f:
                        audio_data = f.read()
                        combined_audio += audio_data
                except Exception as e:
                    logging.warning(f"Error reading {filepath}: {e}")
                    continue
            
            if len(combined_audio) > 0:
                segment_info = {
                    "type": file_type,
                    "segment_id": len(combined_segments),
                    "file_count": len(segment_files),
                    "total_bytes": len(combined_audio),
                    "duration_ms": len(combined_audio) // 32,  # 16kHz = 32 bytes per ms
                    "files": [os.path.basename(f) for f in segment_files]
                }
                combined_segments.append((combined_audio, segment_info))
    
    logging.info(f"Created {len(combined_segments)} combined audio segments")
    return combined_segments

async def test_combined_audio(combined_audio: bytes, segment_info: dict):
    """Test a combined audio segment with STT"""
    logging.info(f"Testing segment {segment_info['segment_id']}: {segment_info['file_count']} files, {segment_info['total_bytes']} bytes, {segment_info['duration_ms']}ms")
    
    try:
        # Test with STT
        async with websockets.connect(LOCAL_AI_SERVER_URL) as websocket:
            # Send audio data
            msg = json.dumps({
                "type": "audio",
                "data": base64.b64encode(combined_audio).decode('utf-8'),
                "rate": 16000,
                "format": "pcm16le"
            })
            await websocket.send(msg)
            
            # Wait for response
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=10)
                # Response is binary TTS audio, not JSON transcript
                return {
                    "status": "processed",
                    "response_size": len(response),
                    "segment_info": segment_info
                }
            except asyncio.TimeoutError:
                return {
                    "status": "timeout",
                    "segment_info": segment_info
                }
            except Exception as e:
                return {
                    "status": "error",
                    "error": str(e),
                    "segment_info": segment_info
                }
                
    except Exception as e:
        return {
            "status": "connection_error",
            "error": str(e),
            "segment_info": segment_info
        }

def analyze_audio_files(capture_dir: str):
    """Analyze the captured audio files to understand the data"""
    logging.info(f"Analyzing audio files in: {capture_dir}")
    
    raw_files = glob.glob(os.path.join(capture_dir, "*.raw"))
    logging.info(f"Found {len(raw_files)} .raw files")
    
    # Group files by type
    file_groups = defaultdict(list)
    file_sizes = defaultdict(int)
    
    for filepath in sorted(raw_files):
        filename = os.path.basename(filepath)
        
        # Parse filename: 0001_rtp_ssrc_230021204_raw_rtp_all_220756_417.raw
        parts = filename.split('_')
        if len(parts) >= 4:
            file_type = f"{parts[2]}_{parts[3]}"  # e.g., "ssrc_raw" or "1758319668.236_raw"
        else:
            file_type = "unknown"
        
        file_groups[file_type].append(filepath)
        
        # Get file size
        try:
            size = os.path.getsize(filepath)
            file_sizes[file_type] += size
        except:
            pass
    
    # Print analysis
    logging.info("\n📊 AUDIO FILE ANALYSIS")
    logging.info("=" * 50)
    for file_type, files in file_groups.items():
        logging.info(f"{file_type}: {len(files)} files, {file_sizes[file_type]} bytes total")
        if files:
            avg_size = file_sizes[file_type] // len(files)
            logging.info(f"  Average size: {avg_size} bytes per file")
    
    return file_groups

async def test_audio_segments(combined_segments: list, max_segments: int = 10):
    """Test combined audio segments with STT"""
    logging.info(f"\n🧪 TESTING COMBINED AUDIO SEGMENTS (max {max_segments})")
    logging.info("=" * 50)
    
    results = []
    
    # Test up to max_segments
    test_segments = combined_segments[:max_segments]
    
    for i, (combined_audio, segment_info) in enumerate(test_segments):
        logging.info(f"\nTesting segment {i+1}/{len(test_segments)}...")
        
        result = await test_combined_audio(combined_audio, segment_info)
        results.append(result)
        
        # Small delay between tests
        await asyncio.sleep(0.5)
    
    return results

def print_results(results: list):
    """Print test results summary"""
    logging.info("\n📋 COMBINED AUDIO TEST RESULTS")
    logging.info("=" * 50)
    
    total_tests = len(results)
    processed = sum(1 for r in results if r["status"] == "processed")
    timeouts = sum(1 for r in results if r["status"] == "timeout")
    errors = sum(1 for r in results if r["status"] in ["error", "connection_error"])
    
    logging.info(f"Total segments tested: {total_tests}")
    logging.info(f"Processed: {processed} ({processed/total_tests*100:.1f}%)")
    logging.info(f"Timeouts: {timeouts} ({timeouts/total_tests*100:.1f}%)")
    logging.info(f"Errors: {errors} ({errors/total_tests*100:.1f}%)")
    
    # Show details for processed segments
    if processed > 0:
        logging.info("\n✅ Successfully processed segments:")
        for result in results:
            if result["status"] == "processed":
                seg = result["segment_info"]
                logging.info(f"  Segment {seg['segment_id']}: {seg['file_count']} files, {seg['duration_ms']}ms, response {result['response_size']} bytes")

async def main():
    logging.info("🎤 COMBINED AUDIO STT TEST")
    logging.info("=" * 50)
    
    # Find the latest capture directory
    capture_dirs = sorted(glob.glob("/app/audio_capture_*/"), reverse=True)
    if not capture_dirs:
        logging.error("No audio capture directories found!")
        return
    
    latest_capture_dir = capture_dirs[0]
    logging.info(f"Using latest capture directory: {latest_capture_dir}")
    
    # Analyze the captured files
    file_groups = analyze_audio_files(latest_capture_dir)
    
    if not file_groups:
        logging.error("No audio files found in capture directory!")
        return
    
    # Combine audio frames into longer segments
    combined_segments = combine_audio_frames(file_groups, frames_per_segment=50)  # 50 frames = 1 second
    
    if not combined_segments:
        logging.error("No combined audio segments created!")
        return
    
    # Test combined segments
    results = await test_audio_segments(combined_segments, max_segments=5)
    
    # Print results
    print_results(results)
    
    logging.info("\n✅ Testing complete!")
    logging.info("Check local_ai_server logs for actual STT transcripts.")

if __name__ == "__main__":
    asyncio.run(main())
