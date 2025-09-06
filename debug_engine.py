#!/usr/bin/env python3
import sys
sys.path.insert(0, "src")

import traceback

try:
    from engine import VoiceAgentEngine
    print("Engine imported successfully")
    
    engine = VoiceAgentEngine()
    print("Engine created successfully")
    
    print(f"Config type: {type(engine.config)}")
    print(f"Config attributes: {dir(engine.config)}")
    
except Exception as e:
    print(f"Error: {e}")
    traceback.print_exc()
