# Asterisk AI Voice Agent

An open-source AI Voice Agent that integrates with Asterisk/FreePBX using SIP/RTP technology (Asterisk 16+) and answers calls using configurable AI providers.

## Features

- **SIP/RTP Integration**: Primary integration mode with Asterisk 16+
- **Advanced Audio Processing**: Voice Activity Detection (VAD), noise suppression, echo cancellation
- **Multi-provider AI Support**: OpenAI Realtime API (MVP), Azure Speech, Deepgram
- **Real-time Communication**: WebSocket-based AI provider integration for sub-second response times
- **Security & Compliance**: Built-in encryption, access controls, and privacy controls
- **Docker-based Deployment**: Simple containerized deployment with host networking

## Quick Start

### Prerequisites

- **Asterisk 16+** with FreePBX UI
- **Docker** installed
- **Python 3.11+** for development

### Development Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/haiderjarral/Asterisk-AI-Voice-Agent.git
   cd Asterisk-AI-Voice-Agent
   ```

2. **Set up environment variables**:
   ```bash
   cp config/engine.json.example config/engine.json
   # Edit config/engine.json with your settings
   ```

3. **Build and run locally**:
   ```bash
   docker-compose up --build
   ```

4. **Test with Asterisk**:
   - Create a PJSIP extension in FreePBX
   - Configure the extension details in `config/engine.json`
   - Route a test call to the extension

## Configuration

### Required Environment Variables

- `INTEGRATION_MODE`: `sip` (default)
- `ASTERISK_HOST`: Asterisk server hostname/IP
- `ASTERISK_VERSION`: `16` (minimum)
- `SIP_EXTENSION`: PJSIP extension number
- `SIP_PASSWORD`: Extension password
- `OPENAI_API_KEY`: OpenAI API key

### Optional Environment Variables

- `VAD_ENABLED`: Enable voice activity detection (default: `true`)
- `NOISE_SUPPRESSION`: Enable noise suppression (default: `true`)
- `ECHO_CANCELLATION`: Enable echo cancellation (default: `true`)
- `LOG_LEVEL`: Logging level (`debug`, `info`, `warn`, `error`)

## Development Workflow

1. **Local Development**: Make changes locally
2. **Git Push**: Commit and push changes to repository
3. **Server Testing**: SSH to test server, pull changes, test with Asterisk

### Test Server

- **Server**: `root@voiprnd.nemtclouddispatch.com`
- **Asterisk**: 16+ with FreePBX UI
- **Docker**: Available for testing

## Project Structure

```
Asterisk-AI-Voice-Agent/
├── src/
│   ├── providers/          # AI provider integrations
│   ├── security/           # Security and compliance
│   ├── monitoring/         # Health checks and metrics
│   ├── sip_client.py       # SIP/RTP integration
│   ├── audio_processor.py  # Audio processing engine
│   ├── config_manager.py   # Configuration management
│   └── engine.py           # Core conversation loop
├── config/
│   └── engine.json         # Default configuration
├── tests/                  # Unit and integration tests
├── docs/                   # Documentation
├── scripts/                # Deployment and utility scripts
├── docker-compose.yml      # Local development
├── Dockerfile              # Container configuration
└── requirements.txt        # Python dependencies
```

## Development Guidelines

1. **Start with SIP Integration**: Focus on getting SIP registration working first
2. **Test Early and Often**: Use the test server for integration testing
3. **Audio Quality First**: Ensure clear audio before adding AI features
4. **Security by Design**: Implement security features from the start

## Performance Targets

- **Response Time**: <2 seconds for AI responses
- **Audio Latency**: <500ms for real-time processing
- **Uptime**: 99.9% availability
- **CPU Usage**: <80% under normal load

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For questions and support, please open an issue on GitHub or contact the development team.
