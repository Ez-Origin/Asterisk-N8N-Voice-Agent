# Scripts Overview

This document summarizes the utilities under `scripts/` and when to use them.

## Health, Monitoring, and Validation

- `scripts/validate_externalmedia_config.py`
  - Validates config required for ExternalMedia + RTP. Run locally before making a test call.
  - Usage: `python3 scripts/validate_externalmedia_config.py`

- `scripts/monitor_externalmedia.py`
  - Monitors ExternalMedia + RTP health continuously.
  - Usage: `python3 scripts/monitor_externalmedia.py` or `--once`

## Test Workflows

- `scripts/test_externalmedia_call.py`
  - End-to-end call flow verification using the `/health` endpoint.
  - Usage: `python3 scripts/test_externalmedia_call.py --url http://127.0.0.1:15000/health`

- `scripts/test_externalmedia_deployment.py`
  - Deployment sanity test to check ARI + RTP wiring.
  - Usage: `python3 scripts/test_externalmedia_deployment.py`

## Log Capture & Analysis

- `scripts/capture_test_logs.py`
  - Captures structured logs for a timed window during a test call.
  - Usage: `python3 scripts/capture_test_logs.py --duration 40`

- `scripts/analyze_logs.py`
  - Analyzes the most recent captured JSON logs and emits a summary.
  - Usage: `python3 scripts/analyze_logs.py logs/<timestamp>.json`

- `scripts/capture_call_window.sh`
  - Shell helper to capture a window for call logs.

- `scripts/summarize_call_capture.sh`
  - Summarizes captured logs quickly on the CLI.

## Provider & Model Management

- `scripts/switch_provider.py`
  - Switches `default_provider` in `config/ai-agent.yaml`.
  - Usage: `make provider=<name> provider-switch` or run the script directly.

- `scripts/model_setup.py`, `scripts/model_manager.py`
  - Detect/Download/Manage local model artifacts for the local provider.
  - Usage: `make model-setup`

- `scripts/download_models.sh`, `scripts/download_tts_models.py`
  - Helpers for bulk model download.

## Miscellaneous

- `scripts/llm_latency_test.py`
  - Rough latency probe for LLM responses (dev utility).

## Tips

- Most scripts assume the engine is running and `/health` is available at `http://127.0.0.1:15000/health`.
- For remote servers, use the Makefile targets (now localhost-aware) under `server-*` and `deploy-*`.
