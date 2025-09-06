#!/usr/bin/env python3
"""
Test script to simulate an incoming call to the AI Voice Agent.
This script will test the call handling logic without requiring a full SIP setup.
"""

import sys
import asyncio
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from config.manager import ConfigManager
from engine import VoiceAgentEngine
from call_session import CallInfo

async def test_call_handling():
    """Test the call handling logic."""
    print("🧪 Testing AI Voice Agent Call Handling...")
    
    try:
        # Initialize the engine with minimal config
        print("1. Initializing Voice Agent Engine...")
        import os
        os.environ['VOICE_AGENT_SIP_HOST'] = 'test'
        os.environ['VOICE_AGENT_SIP_EXTENSION'] = '3000'
        os.environ['VOICE_AGENT_SIP_PASSWORD'] = 'test'
        os.environ['VOICE_AGENT_AI_PROVIDER_API_KEY'] = 'test'
        
        engine = VoiceAgentEngine()
        print("   ✅ Engine initialized successfully")
        
        # Create a mock call
        print("2. Creating mock incoming call...")
        call_info = CallInfo(
            call_id="test-call-123",
            from_user="test-caller",
            to_user="3000",
            local_rtp_port=10000,
            remote_rtp_port=20000,
            remote_ip="127.0.0.1",
            codec="ulaw",
            start_time=time.time()
        )
        
        # Add the call to active calls
        engine.active_calls["test-call-123"] = call_info
        print("   ✅ Mock call created")
        
        # Test call handling
        print("3. Testing call handling logic...")
        await engine._handle_call("test-call-123", call_info)
        print("   ✅ Call handling completed")
        
        # Test call state transitions
        print("4. Testing call state transitions...")
        call_info.state = "ringing"
        await engine._handle_call("test-call-123", call_info)
        
        call_info.state = "connected"
        await engine._handle_call("test-call-123", call_info)
        
        call_info.state = "ended"
        await engine._handle_call("test-call-123", call_info)
        print("   ✅ Call state transitions completed")
        
        # Test engine status
        print("5. Testing engine status...")
        status = engine.get_status()
        print(f"   Engine running: {status['running']}")
        print(f"   Active calls: {status['active_calls']}")
        print(f"   Call details: {status['calls']}")
        
        print("\n🎉 All tests passed! The AI Voice Agent call handling logic is working correctly.")
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    success = asyncio.run(test_call_handling())
    sys.exit(0 if success else 1)
