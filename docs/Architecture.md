# Asterisk AI Voice Agent - Architecture Documentation

## System Overview

The Asterisk AI Voice Agent v3.0 is a single-container, multi-provider architecture that supports both cloud-based (Deepgram) and local AI models for real-time voice conversations.

## Architecture Diagrams

### 1. DEEPGRAM PROVIDER CALL FLOW 🌐

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   ASTERISK      │    │   AI AGENT      │    │   DEEPGRAM      │    │   OPENAI        │
│   (PJSIP/SIP)   │    │   ENGINE        │    │   CLOUD         │    │   CLOUD         │
└─────────────────┘    └─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │                       │
         │ 1. Incoming Call     │                       │                       │
         ├──────────────────────►│                       │                       │
         │                       │                       │                       │
         │ 2. StasisStart Event │                       │                       │
         ├──────────────────────►│                       │                       │
         │                       │                       │                       │
         │                       │ 3. Create DeepgramProvider                    │
         │                       ├──────────────────────►│                       │
         │                       │                       │                       │
         │                       │ 4. WebSocket Connect  │                       │
         │                       ├──────────────────────►│                       │
         │                       │                       │                       │
         │ 5. Answer Channel     │                       │                       │
         │◄──────────────────────┤                       │                       │
         │                       │                       │                       │
         │ 6. Create External Media Channel              │                       │
         │◄──────────────────────┤                       │                       │
         │                       │                       │                       │
         │ 7. Create Bridge      │                       │                       │
         │◄──────────────────────┤                       │                       │
         │                       │                       │                       │
         │ 8. Add Channels to Bridge                     │                       │
         │◄──────────────────────┤                       │                       │
         │                       │                       │                       │
         │ 9. RTP Audio Stream   │                       │                       │
         ├──────────────────────►│                       │                       │
         │                       │                       │                       │
         │                       │ 10. Forward to Deepgram                       │
         │                       ├──────────────────────►│                       │
         │                       │                       │                       │
         │                       │                       │ 11. STT + LLM + TTS   │
         │                       │                       ├──────────────────────►│
         │                       │                       │                       │
         │                       │ 12. Audio Response    │                       │
         │                       │◄──────────────────────┤                       │
         │                       │                       │                       │
         │ 13. RTP Audio Stream  │                       │                       │
         │◄──────────────────────┤                       │                       │
         │                       │                       │                       │
         │ 14. Call Complete     │                       │                       │
         ├──────────────────────►│                       │                       │
         │                       │                       │                       │
```

### 2. LOCAL PROVIDER CALL FLOW 🏠

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   ASTERISK      │    │   AI AGENT      │    │   LOCAL MODELS  │    │   RTP HANDLER   │
│   (PJSIP/SIP)   │    │   ENGINE        │    │   (Vosk/Llama)  │    │   (Packetizer)  │
└─────────────────┘    └─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │                       │
         │ 1. Incoming Call     │                       │                       │
         ├──────────────────────►│                       │                       │
         │                       │                       │                       │
         │ 2. StasisStart Event │                       │                       │
         ├──────────────────────►│                       │                       │
         │                       │                       │                       │
         │                       │ 3. Create LocalProvider                       │
         │                       ├──────────────────────►│                       │
         │                       │                       │                       │
         │                       │ 4. Load STT/LLM/TTS Models                    │
         │                       ├──────────────────────►│                       │
         │                       │                       │                       │
         │ 5. Answer Channel     │                       │                       │
         │◄──────────────────────┤                       │                       │
         │                       │                       │                       │
         │ 6. Create External Media Channel              │                       │
         │◄──────────────────────┤                       │                       │
         │                       │                       │                       │
         │ 7. Create Bridge      │                       │                       │
         │◄──────────────────────┤                       │                       │
         │                       │                       │                       │
         │ 8. Add Channels to Bridge                     │                       │
         │◄──────────────────────┤                       │                       │
         │                       │                       │                       │
         │ 9. RTP Audio Stream   │                       │                       │
         ├──────────────────────►│                       │                       │
         │                       │                       │                       │
         │                       │ 10. Forward to LocalProvider                  │
         │                       ├──────────────────────►│                       │
         │                       │                       │                       │
         │                       │ 11. STT Processing    │                       │
         │                       │◄──────────────────────┤                       │
         │                       │                       │                       │
         │                       │ 12. LLM Processing    │                       │
         │                       │◄──────────────────────┤                       │
         │                       │                       │                       │
         │                       │ 13. TTS Synthesis     │                       │
         │                       │◄──────────────────────┤                       │
         │                       │                       │                       │
         │                       │ 14. AgentAudio Event  │                       │
         │                       │◄──────────────────────┤                       │
         │                       │                       │                       │
         │                       │ 15. RTP Packetization │                       │
         │                       ├──────────────────────►│                       │
         │                       │                       │                       │
         │ 16. RTP Audio Stream  │                       │                       │
         │◄──────────────────────┤                       │                       │
         │                       │                       │                       │
         │ 17. Call Complete     │                       │                       │
         ├──────────────────────►│                       │                       │
         │                       │                       │                       │
```

### 3. RING MECHANISM FLOW 🔔

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   ASTERISK      │    │   AI AGENT      │    │   LOCAL MODELS  │
│   (PJSIP/SIP)   │    │   ENGINE        │    │   (Loading)     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │ 1. Incoming Call     │                       │
         ├──────────────────────►│                       │
         │                       │                       │
         │ 2. StasisStart Event │                       │
         ├──────────────────────►│                       │
         │                       │                       │
         │ 3. Answer Immediately│                       │
         │◄──────────────────────┤                       │
         │                       │                       │
         │ 4. Start Ring Tone   │                       │
         │◄──────────────────────┤                       │
         │                       │                       │
         │ 5. Load Models (Background)                   │
         │                       ├──────────────────────►│
         │                       │                       │
         │ 6. Ring Continues... │                       │
         │◄──────────────────────┤                       │
         │                       │                       │
         │ 7. Models Ready       │                       │
         │                       │◄──────────────────────┤
         │                       │                       │
         │ 8. Stop Ring          │                       │
         │◄──────────────────────┤                       │
         │                       │                       │
         │ 9. Play Greeting      │                       │
         │◄──────────────────────┤                       │
         │                       │                       │
```

## Key File Architecture

```
src/
├── engine.py                    # 🎯 MAIN ORCHESTRATOR
│   ├── _handle_stasis_start()   # Entry point for all calls
│   ├── _create_provider()       # Factory for Deepgram/Local providers
│   ├── on_provider_event()      # ⚠️ CRITICAL: Handles AgentAudio events
│   ├── _play_ring_tone()        # 🔔 NEW: Ring mechanism
│   └── _play_ai_audio()         # Legacy method (unused)
│
├── providers/
│   ├── base.py                  # AIProviderInterface abstract class
│   ├── deepgram.py              # 🌐 CLOUD PROVIDER
│   │   ├── start_session()      # WebSocket connection to Deepgram
│   │   ├── send_audio()         # Forward RTP → WebSocket
│   │   ├── _receive_loop()      # WebSocket → AgentAudio events
│   │   └── speak()              # Inject text to Deepgram
│   │
│   └── local.py                 # 🏠 LOCAL PROVIDER
│       ├── start_session()      # Load STT/LLM/TTS models
│       ├── send_audio()         # RTP → STT processing
│       ├── speak()              # Text → TTS → AgentAudio events
│       └── _synthesize_tts_audio() # TTS synthesis
│
├── ari_client.py                # Asterisk REST Interface client
├── udp_server.py                # UDP server for RTP handling
├── rtp_handler.py               # RTPPacketizer class
└── rtp_packet.py                # RtpPacket parsing/serialization
```

## Critical Differences

| **Aspect** | **Deepgram Provider** | **Local Provider** |
|------------|----------------------|-------------------|
| **Audio Direction** | Bidirectional WebSocket | Unidirectional RTP |
| **STT Processing** | Cloud-based | Local Vosk model |
| **LLM Processing** | Cloud OpenAI | Local Llama model |
| **TTS Processing** | Cloud Deepgram | Local Coqui TTS |
| **Audio Format** | Pre-packetized from cloud | Raw ulaw requiring packetization |
| **Event Flow** | WebSocket → on_event() | TTS → on_event() → RTP packetization |
| **Dependencies** | Internet + API keys | Local model files |
| **Loading Time** | ~1-2 seconds | ~5-10 seconds |
| **Ring Mechanism** | Not needed | Required for UX |

## Ring Mechanism Implementation

The ring mechanism addresses the delay in local model loading by:

1. **Immediate Answer**: Answer the call immediately to prevent timeout
2. **Ring Tone**: Play a standard ring tone while models load in background
3. **Model Loading**: Load STT/LLM/TTS models asynchronously
4. **Seamless Transition**: Stop ring and play greeting when models are ready
5. **Provider Detection**: Only apply to Local provider, skip for Deepgram

## Unified Provider Interface

Both providers implement the same interface:
```python
class AIProviderInterface:
    async def start_session()     # Initialize provider
    async def send_audio()        # Process incoming audio
    async def speak()             # Generate outgoing audio
    async def stop_session()      # Cleanup resources
    async def is_ready()          # Check if provider is ready
```

The beauty of this architecture: The engine doesn't need to know whether it's talking to Deepgram or Local - it just calls the same methods and handles the same `AgentAudio` events!
