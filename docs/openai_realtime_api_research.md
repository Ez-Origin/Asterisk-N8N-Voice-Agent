# OpenAI Realtime API Research

## Overview
The OpenAI Realtime API is a WebSocket-based API that enables real-time, bidirectional communication with OpenAI's models for speech-to-text (STT), text-to-speech (TTS), and large language model (LLM) interactions in a single conversation.

## Key Features
- **WebSocket-based**: Real-time, low-latency communication
- **Unified Interface**: Single API for STT, LLM, and TTS
- **Streaming**: All operations support streaming for real-time responses
- **Conversation Context**: Maintains conversation state throughout the session
- **Voice Selection**: Multiple voice options for TTS
- **Interrupt Handling**: Supports conversation interruption and turn-taking

## WebSocket Endpoint
- **URL**: `wss://api.openai.com/v1/realtime`
- **Authentication**: Bearer token in Authorization header
- **Protocol**: WebSocket with JSON message format

## Message Types

### 1. Session Management
```json
{
  "type": "session.update",
  "session": {
    "modalities": ["text", "audio"],
    "instructions": "You are a helpful AI assistant for Jugaar LLC.",
    "voice": "alloy",
    "input_audio_format": "pcm16",
    "output_audio_format": "pcm16",
    "input_audio_transcription": {
      "model": "whisper-1"
    },
    "turn_detection": {
      "type": "server_vad",
      "threshold": 0.5,
      "prefix_padding_ms": 300,
      "silence_duration_ms": 200
    },
    "tools": [],
    "tool_choice": "auto",
    "temperature": 0.8,
    "max_response_output_tokens": 4096
  }
}
```

### 2. Audio Input
```json
{
  "type": "input_audio_buffer.append",
  "audio": "<base64_encoded_audio_data>"
}
```

### 3. Audio Input Commit
```json
{
  "type": "input_audio_buffer.commit"
}
```

### 4. Text Input
```json
{
  "type": "conversation.item.create",
  "item": {
    "type": "message",
    "role": "user",
    "content": [{"type": "input_text", "text": "Hello, how can I help you?"}]
  }
}
```

### 5. Response Generation
```json
{
  "type": "response.create",
  "response": {
    "modalities": ["text", "audio"],
    "instructions": "Respond naturally and helpfully."
  }
}
```

## Audio Format Specifications

### Input Audio
- **Format**: PCM 16-bit signed integer
- **Sample Rate**: 24kHz
- **Channels**: Mono (1 channel)
- **Encoding**: Base64 encoded
- **Chunk Size**: Variable, typically 20ms chunks

### Output Audio
- **Format**: PCM 16-bit signed integer
- **Sample Rate**: 24kHz
- **Channels**: Mono (1 channel)
- **Encoding**: Base64 encoded in response messages

## Voice Options
- `alloy` - Neutral, balanced voice
- `echo` - Warm, friendly voice
- `fable` - Expressive, storytelling voice
- `onyx` - Deep, authoritative voice
- `nova` - Bright, energetic voice
- `shimmer` - Soft, gentle voice

## Response Message Types

### 1. Response Start
```json
{
  "type": "response.audio_transcript.delta",
  "delta": {
    "type": "audio_transcript.delta",
    "index": 0,
    "text": "Hello, I'm an AI assistant for Jugaar LLC. How can I help you today?"
  }
}
```

### 2. Audio Data
```json
{
  "type": "response.audio.delta",
  "delta": {
    "type": "audio.delta",
    "audio": "<base64_encoded_audio_data>"
  }
}
```

### 3. Response Complete
```json
{
  "type": "response.done",
  "response": {
    "id": "response_123",
    "modalities": ["text", "audio"],
    "usage": {
      "input_audio_duration_ms": 1500,
      "output_audio_duration_ms": 2000,
      "total_tokens": 150
    }
  }
}
```

## Error Handling

### Error Response Format
```json
{
  "type": "error",
  "error": {
    "type": "invalid_request_error",
    "code": "invalid_audio_format",
    "message": "The audio format is not supported. Expected PCM 16-bit, 24kHz, mono."
  }
}
```

### Common Error Types
- `invalid_request_error`: Malformed request
- `authentication_error`: Invalid API key
- `rate_limit_error`: Too many requests
- `server_error`: Internal server error

## Rate Limits
- **Requests per minute**: 60
- **Audio duration per minute**: 5 minutes
- **Concurrent connections**: 3 per API key

## Implementation Considerations

### 1. Connection Management
- Maintain persistent WebSocket connection
- Implement reconnection logic with exponential backoff
- Handle connection drops gracefully

### 2. Audio Processing
- Convert incoming audio to PCM 16-bit, 24kHz, mono
- Chunk audio into appropriate sizes (typically 20ms)
- Handle audio format conversion from SIP codecs

### 3. Message Handling
- Implement proper message queuing
- Handle out-of-order messages
- Manage conversation state

### 4. Error Recovery
- Implement retry logic for transient errors
- Handle rate limiting with backoff
- Graceful degradation on errors

## Integration with Asterisk
- Convert SIP audio (G.711/G.722) to PCM 16-bit, 24kHz
- Handle real-time audio streaming
- Manage conversation turn-taking
- Implement proper audio buffering

## Security Considerations
- Use secure WebSocket (wss://)
- Implement proper API key management
- Handle sensitive voice data appropriately
- Comply with data privacy regulations

## Testing Strategy
- Unit tests for message formatting
- Integration tests with mock OpenAI responses
- End-to-end tests with real audio data
- Performance tests for latency and throughput
- Error handling tests for various failure scenarios
