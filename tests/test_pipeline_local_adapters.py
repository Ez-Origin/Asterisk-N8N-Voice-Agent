import asyncio
import base64
import json

import pytest

from src.config import AppConfig, LocalProviderConfig
from src.pipelines.local import LocalLLMAdapter, LocalSTTAdapter, LocalTTSAdapter
from src.pipelines.orchestrator import PipelineOrchestrator


def _build_app_config() -> AppConfig:
    providers = {
        "local": {
            "enabled": True,
            "ws_url": "ws://127.0.0.1:8765",
            "connect_timeout_sec": 0.5,
            "response_timeout_sec": 0.5,
            "chunk_ms": 200,
        }
    }
    pipelines = {
        "local_only": {
            "stt": "local_stt",
            "llm": "local_llm",
            "tts": "local_tts",
            "options": {
                "stt": {"mode": "stt"},
                "llm": {"mode": "llm"},
                "tts": {"mode": "tts"},
            },
        }
    }
    return AppConfig(
        default_provider="local",
        providers=providers,
        asterisk={"host": "127.0.0.1", "username": "ari", "password": "secret"},
        llm={"initial_greeting": "hi", "prompt": "prompt", "model": "local-llm"},
        audio_transport="audiosocket",
        downstream_mode="file",
        pipelines=pipelines,
        active_pipeline="local_only",
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


@pytest.mark.asyncio
async def test_local_stt_adapter_transcribes(monkeypatch):
    app_config = _build_app_config()
    provider_config = LocalProviderConfig(**app_config.providers["local"])
    adapter = LocalSTTAdapter("local_stt", app_config, provider_config, {"mode": "stt"})

    mock_ws = _MockWebSocket()

    async def fake_connect(*_args, **_kwargs):
        return mock_ws

    monkeypatch.setattr("src.pipelines.local.websockets.connect", fake_connect)

    await adapter.start()
    await adapter.open_call("call-1", {"mode": "stt"})

    set_mode_message = json.loads(mock_ws.sent[0])
    assert set_mode_message == {"type": "set_mode", "mode": "stt", "call_id": "call-1"}

    audio_buffer = b"\x01\x02" * 80  # 160 bytes == 20 ms of 8 kHz PCM16
    task = asyncio.create_task(adapter.transcribe("call-1", audio_buffer, 8000, {}))
    await asyncio.sleep(0)

    partial_payload = {
        "type": "stt_result",
        "text": "hello",
        "is_partial": True,
        "is_final": False,
    }
    final_payload = {
        "type": "stt_result",
        "text": "hello world",
        "is_partial": False,
        "is_final": True,
    }

    mock_ws.push(json.dumps(partial_payload))
    await asyncio.sleep(0)
    mock_ws.push(json.dumps(final_payload))

    transcript = await task
    assert transcript == "hello world"

    audio_message = json.loads(mock_ws.sent[1])
    assert audio_message["type"] == "audio"
    assert audio_message["mode"] == "stt"
    decoded = base64.b64decode(audio_message["data"])
    assert decoded == audio_buffer


@pytest.mark.asyncio
async def test_local_llm_adapter_generate(monkeypatch):
    app_config = _build_app_config()
    provider_config = LocalProviderConfig(**app_config.providers["local"])
    adapter = LocalLLMAdapter("local_llm", app_config, provider_config, {"mode": "llm"})

    mock_ws = _MockWebSocket()

    async def fake_connect(*_args, **_kwargs):
        return mock_ws

    monkeypatch.setattr("src.pipelines.local.websockets.connect", fake_connect)

    await adapter.start()
    await adapter.open_call("call-2", {"mode": "llm"})

    request_task = asyncio.create_task(
        adapter.generate(
            "call-2",
            "user text",
            {"messages": [{"role": "user", "content": "user text"}]},
            {},
        )
    )
    await asyncio.sleep(0)

    mock_ws.push(json.dumps({"type": "llm_response", "text": "assistant reply"}))

    response = await request_task
    assert response == "assistant reply"

    llm_message = json.loads(mock_ws.sent[1])
    assert llm_message["type"] == "llm_request"
    assert llm_message["call_id"] == "call-2"
    assert llm_message["text"] == "user text"
    assert llm_message["context"] == [{"role": "user", "content": "user text"}]


@pytest.mark.asyncio
async def test_local_tts_adapter_synthesizes(monkeypatch):
    app_config = _build_app_config()
    provider_config = LocalProviderConfig(**app_config.providers["local"])
    adapter = LocalTTSAdapter("local_tts", app_config, provider_config, {"mode": "tts"})

    mock_ws = _MockWebSocket()

    async def fake_connect(*_args, **_kwargs):
        return mock_ws

    monkeypatch.setattr("src.pipelines.local.websockets.connect", fake_connect)

    await adapter.start()
    await adapter.open_call("call-3", {"mode": "tts"})

    audio_bytes = b"\xAA\xBB" * 40  # 80 bytes
    encoded = base64.b64encode(audio_bytes).decode("ascii")

    collected = []

    async def collect_audio():
        async for chunk in adapter.synthesize("call-3", "Hello world", {}):
            collected.append(chunk)

    task = asyncio.create_task(collect_audio())
    await asyncio.sleep(0)

    mock_ws.push(json.dumps({"type": "tts_response", "audio_data": encoded}))

    await task

    assert collected == [audio_bytes]

    tts_message = json.loads(mock_ws.sent[1])
    assert tts_message["type"] == "tts_request"
    assert tts_message["call_id"] == "call-3"
    assert tts_message["text"] == "Hello world"


@pytest.mark.asyncio
async def test_pipeline_orchestrator_resolves_local_adapters():
    app_config = _build_app_config()
    orchestrator = PipelineOrchestrator(app_config)
    await orchestrator.start()

    resolution = orchestrator.get_pipeline("call-99")
    assert resolution is not None
    assert isinstance(resolution.stt_adapter, LocalSTTAdapter)
    assert isinstance(resolution.llm_adapter, LocalLLMAdapter)
    assert isinstance(resolution.tts_adapter, LocalTTSAdapter)
    assert resolution.pipeline_name == "local_only"

    await orchestrator.stop()
