import asyncio
import json

import pytest

from src.audio.resampler import convert_pcm16le_to_target_format
from src.config import AppConfig, DeepgramProviderConfig
from src.pipelines.deepgram import DeepgramSTTAdapter, DeepgramTTSAdapter
from src.pipelines.orchestrator import PipelineOrchestrator


def _build_app_config() -> AppConfig:
    providers = {
        "deepgram": {
            "api_key": "test-key",
            "model": "nova-2-general",
            "tts_model": "aura-asteria-en",
            "input_encoding": "linear16",
            "input_sample_rate_hz": 8000,
            "base_url": "https://api.deepgram.com",
            "continuous_input": True,
            "stt_language": "en-US",
        }
    }
    pipelines = {
        "deepgram_only": {
            "stt": "deepgram_stt",
            "llm": "local_llm",
            "tts": "deepgram_tts",
            "options": {
                "stt": {"language": "en-US"},
                "tts": {"format": {"encoding": "mulaw", "sample_rate": 8000}},
            },
        }
    }
    return AppConfig(
        default_provider="deepgram",
        providers=providers,
        asterisk={"host": "127.0.0.1", "username": "ari", "password": "secret"},
        llm={"initial_greeting": "hi", "prompt": "prompt", "model": "gpt-4o"},
        audio_transport="audiosocket",
        downstream_mode="stream",
        pipelines=pipelines,
        active_pipeline="deepgram_only",
    )


class _MockWebSocket:
    def __init__(self):
        self.sent = []
        self._queue: asyncio.Queue = asyncio.Queue()
        self.closed = False

    async def send(self, data):
        self.sent.append(data)

    async def recv(self):
        return await self._queue.get()

    async def close(self):
        self.closed = True

    def push(self, message):
        self._queue.put_nowait(message)


class _FakeResponse:
    def __init__(self, body: bytes, status: int = 200):
        self._body = body
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def read(self):
        return self._body

    async def text(self):
        return self._body.decode("utf-8", errors="ignore")


class _FakeSession:
    def __init__(self, body: bytes, status: int = 200):
        self._body = body
        self._status = status
        self.requests = []
        self.closed = False

    def post(self, url, json=None, params=None, headers=None):
        self.requests.append({"url": url, "json": json, "params": params, "headers": headers})
        return _FakeResponse(self._body, status=self._status)

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_deepgram_stt_adapter_transcribes(monkeypatch):
    app_config = _build_app_config()
    provider_config = DeepgramProviderConfig(**app_config.providers["deepgram"])
    adapter = DeepgramSTTAdapter("deepgram_stt", app_config, provider_config, {"language": "en-US"})

    mock_ws = _MockWebSocket()

    async def fake_connect(*args, **kwargs):
        return mock_ws

    monkeypatch.setattr("src.pipelines.deepgram.websockets.connect", fake_connect)

    await adapter.start()
    await adapter.open_call("call-1", {"model": "nova-2-general"})
    mock_ws.push(
        json.dumps(
            {
                "channel": {"alternatives": [{"transcript": "hello world", "confidence": 0.92}]},
                "is_final": True,
            }
        )
    )

    audio_buffer = b"\x00\x00" * 160
    transcript = await adapter.transcribe("call-1", audio_buffer, 8000, {})
    assert transcript == "hello world"
    assert mock_ws.sent[0] == audio_buffer
    assert json.loads(mock_ws.sent[1])["type"] == "flush"


@pytest.mark.asyncio
async def test_deepgram_tts_adapter_synthesizes_chunks():
    app_config = _build_app_config()
    provider_config = DeepgramProviderConfig(**app_config.providers["deepgram"])
    pcm_audio = b"\x00\x10" * 160  # 160 samples (20 ms @ 8 kHz)
    fake_session = _FakeSession(pcm_audio)
    adapter = DeepgramTTSAdapter(
        "deepgram_tts",
        app_config,
        provider_config,
        {"format": {"encoding": "mulaw", "sample_rate": 8000}},
        session_factory=lambda: fake_session,
    )

    await adapter.start()
    await adapter.open_call("call-1", {})

    chunks = [chunk async for chunk in adapter.synthesize("call-1", "Hello caller", {})]
    synthesized = b"".join(chunks)
    expected = convert_pcm16le_to_target_format(pcm_audio, "mulaw")

    assert synthesized == expected
    request = fake_session.requests[0]
    assert request["json"] == {"text": "Hello caller"}
    assert request["params"]["target_encoding"] == "mulaw"
    assert request["params"]["target_sample_rate"] == 8000


@pytest.mark.asyncio
async def test_pipeline_orchestrator_registers_deepgram_adapters():
    app_config = _build_app_config()
    orchestrator = PipelineOrchestrator(app_config)
    await orchestrator.start()

    resolution = orchestrator.get_pipeline("call-1")
    assert isinstance(resolution.stt_adapter, DeepgramSTTAdapter)
    assert isinstance(resolution.tts_adapter, DeepgramTTSAdapter)
    assert resolution.stt_options["language"] == "en-US"