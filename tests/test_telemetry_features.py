"""Tests for qyra telemetry feature surface:
- track_call / atrack_call context managers (auto-latency)
- Explicit `model` kwarg on track / atrack
- Expanded provider auto-detection patterns
"""

from __future__ import annotations

import asyncio
import os
import time
from unittest.mock import patch

import pytest

def test_track_call_is_exported():
    import qyra

    assert callable(qyra.track_call)
    assert callable(qyra.atrack_call)


# ─── track_call sync context manager ───────────────────────────────────────


def test_track_call_measures_latency_and_emits_on_clean_exit(monkeypatch):
    """Successful track_call block produces an event with measured latency_ms."""
    from qyra import track_call
    from qyra.config import get_config

    captured: list[dict] = []

    def fake_track_event(event, *, config=None):
        captured.append(dict(event))

    monkeypatch.setattr("qyra.telemetry.track_event", fake_track_event)

    with patch.dict(os.environ, {"QYRA_TELEMETRY_URL": "http://example.invalid/track"}):
        get_config(refresh=True)
        with track_call("ask", aim_name="my-aim"):
            time.sleep(0.02)  # 20ms

    assert len(captured) == 1
    e = captured[0]
    assert e["aim_name"] == "my-aim"
    assert e["operation"] == "ask"
    assert e["success"] is True
    assert "latency_ms" in e
    assert e["latency_ms"] >= 20  # we slept 20ms
    assert e["latency_ms"] < 5000  # sanity upper bound


def test_track_call_records_failure_and_reraises(monkeypatch):
    """Exception inside track_call → event with success=False + raise propagates."""
    from qyra import track_call
    from qyra.config import get_config

    captured: list[dict] = []

    def fake_track_event(event, *, config=None):
        captured.append(dict(event))

    monkeypatch.setattr("qyra.telemetry.track_event", fake_track_event)

    with patch.dict(os.environ, {"QYRA_TELEMETRY_URL": "http://example.invalid/track"}):
        get_config(refresh=True)
        with pytest.raises(ValueError, match="boom"), track_call("ask", aim_name="my-aim"):
            raise ValueError("boom")

    assert len(captured) == 1
    e = captured[0]
    assert e["success"] is False
    assert "ValueError" in e["error"]
    assert "boom" in e["error"]
    assert "error_class" in e
    assert "latency_ms" in e


def test_track_call_extracts_response_when_set(monkeypatch):
    """Calling ctx.set_response(resp) attaches model + tokens to the event."""
    from qyra import track_call
    from qyra.config import get_config

    captured: list[dict] = []
    monkeypatch.setattr(
        "qyra.telemetry.track_event",
        lambda event, *, config=None: captured.append(dict(event)),
    )

    class FakeUsage:
        input_tokens = 100
        output_tokens = 50

    class FakeResponse:
        model = "claude-haiku-4-5-20251001"
        usage = FakeUsage()

    with patch.dict(os.environ, {"QYRA_TELEMETRY_URL": "http://example.invalid/track"}):
        get_config(refresh=True)
        with track_call("ask", aim_name="t") as ctx:
            ctx.set_response(FakeResponse())

    e = captured[0]
    assert e["model"] == "claude-haiku-4-5-20251001"
    assert e["model_provider"] == "anthropic"
    assert e["input_tokens"] == 100
    assert e["output_tokens"] == 50


def test_track_call_set_model_only(monkeypatch):
    """set_model() works when no full response is available."""
    from qyra import track_call
    from qyra.config import get_config

    captured: list[dict] = []
    monkeypatch.setattr(
        "qyra.telemetry.track_event",
        lambda event, *, config=None: captured.append(dict(event)),
    )

    with patch.dict(os.environ, {"QYRA_TELEMETRY_URL": "http://example.invalid/track"}):
        get_config(refresh=True)
        with track_call("ask", aim_name="t") as ctx:
            ctx.set_model("gpt-4o")

    e = captured[0]
    assert e["model"] == "gpt-4o"
    assert e["model_provider"] == "openai"
    # No tokens since no usage object
    assert "input_tokens" not in e


def test_track_call_disabled_emits_nothing(monkeypatch):
    """If telemetry is disabled, track_call still yields and runs the body but emits no event."""
    from qyra import track_call
    from qyra.config import get_config

    captured: list[dict] = []
    monkeypatch.setattr(
        "qyra.telemetry.track_event",
        lambda event, *, config=None: captured.append(dict(event)),
    )

    body_ran = False
    with patch.dict(os.environ, {"QYRA_DISABLED": "1"}):
        get_config(refresh=True)
        with track_call("ask", aim_name="t"):
            body_ran = True

    assert body_ran is True
    assert captured == []


# ─── atrack_call async context manager ─────────────────────────────────────


def test_atrack_call_measures_latency_and_emits_on_clean_exit(monkeypatch):
    """Async counterpart: success path."""
    from qyra import atrack_call
    from qyra.config import get_config

    captured: list[dict] = []

    # atrack uses asyncio.create_task to fire the POST. We bypass the network
    # by patching _post_async to capture the event directly.
    async def fake_post_async(cfg, event):
        captured.append(dict(event))

    monkeypatch.setattr("qyra.telemetry._post_async", fake_post_async)

    async def runner():
        with patch.dict(os.environ, {"QYRA_TELEMETRY_URL": "http://example.invalid/track"}):
            get_config(refresh=True)
            async with atrack_call("ask", aim_name="my-aim"):
                await asyncio.sleep(0.02)
        # Yield control so the create_task'd POST runs.
        await asyncio.sleep(0.01)

    asyncio.run(runner())
    assert len(captured) == 1
    e = captured[0]
    assert e["operation"] == "ask"
    assert e["success"] is True
    assert e["latency_ms"] >= 20


def test_atrack_call_records_failure_and_reraises(monkeypatch):
    from qyra import atrack_call
    from qyra.config import get_config

    captured: list[dict] = []

    async def fake_post_async(cfg, event):
        captured.append(dict(event))

    monkeypatch.setattr("qyra.telemetry._post_async", fake_post_async)

    async def runner():
        with patch.dict(os.environ, {"QYRA_TELEMETRY_URL": "http://example.invalid/track"}):
            get_config(refresh=True)
            with pytest.raises(RuntimeError, match="kaboom"):
                async with atrack_call("ask", aim_name="t"):
                    raise RuntimeError("kaboom")
        await asyncio.sleep(0.01)

    asyncio.run(runner())
    assert len(captured) == 1
    assert captured[0]["success"] is False
    assert "kaboom" in captured[0]["error"]


# ─── Explicit `model` kwarg on track ──────────────────────────────────────


def test_track_with_model_kwarg_derives_provider(monkeypatch):
    """Passing model='gpt-4o' to track sets model + model_provider on the event."""
    from qyra import track
    from qyra.config import get_config

    captured: list[dict] = []
    monkeypatch.setattr(
        "qyra.telemetry.track_event",
        lambda event, *, config=None: captured.append(dict(event)),
    )

    with patch.dict(os.environ, {"QYRA_TELEMETRY_URL": "http://example.invalid/track"}):
        get_config(refresh=True)
        track("op", model="gpt-4o", aim_name="t")

    e = captured[0]
    assert e["model"] == "gpt-4o"
    assert e["model_provider"] == "openai"


def test_response_model_takes_precedence_over_model_kwarg(monkeypatch):
    """If both response.model and model= are given, the response wins."""
    from qyra import track
    from qyra.config import get_config

    captured: list[dict] = []
    monkeypatch.setattr(
        "qyra.telemetry.track_event",
        lambda event, *, config=None: captured.append(dict(event)),
    )

    class FakeResponse:
        model = "claude-haiku-4-5-20251001"
        usage = None

    with patch.dict(os.environ, {"QYRA_TELEMETRY_URL": "http://example.invalid/track"}):
        get_config(refresh=True)
        track("op", response=FakeResponse(), model="gpt-4o", aim_name="t")

    e = captured[0]
    assert e["model"] == "claude-haiku-4-5-20251001"
    assert e["model_provider"] == "anthropic"


# ─── Provider pattern expansions ──────────────────────────────────────────


def test_derive_model_provider_extended_openai():
    """v0.1.3: text-embedding-*, dall-e-*, whisper-*, tts-* are openai."""
    from qyra._internal import derive_model_provider

    assert derive_model_provider("text-embedding-3-large") == "openai"
    assert derive_model_provider("text-embedding-ada-002") == "openai"
    assert derive_model_provider("dall-e-3") == "openai"
    assert derive_model_provider("whisper-1") == "openai"
    assert derive_model_provider("tts-1-hd") == "openai"


def test_derive_model_provider_extended_local():
    """v0.1.3: mixtral, codellama match local."""
    from qyra._internal import derive_model_provider

    assert derive_model_provider("mixtral-8x7b") == "local"
    assert derive_model_provider("codellama-13b") == "local"


def test_derive_model_provider_ollama_tagged_fallback():
    """v0.1.3: 'name:tag' (Ollama-style) without explicit prefix → local."""
    from qyra._internal import derive_model_provider

    # qwen and gemma already match the named-family pattern → local
    assert derive_model_provider("qwen2.5:3b") == "local"
    assert derive_model_provider("gemma2:2b") == "local"
    # An unknown family with a colon tag still falls through to local
    # via the new generic ":tag" fallback rule.
    assert derive_model_provider("randombrand-foundation:7b") == "local"


def test_derive_model_provider_anthropic_unchanged():
    """Sanity: existing patterns still work."""
    from qyra._internal import derive_model_provider

    assert derive_model_provider("claude-opus-4-7") == "anthropic"
    assert derive_model_provider("claude-haiku-4-5-20251001") == "anthropic"


def test_derive_model_provider_other_for_truly_novel():
    """A genuinely unrecognized model name with no colon falls to 'other'."""
    from qyra._internal import derive_model_provider

    assert derive_model_provider("some-novel-model") == "other"
    # Empty stays None
    assert derive_model_provider("") is None
    assert derive_model_provider(None) is None


# ─── Build event derives provider from extra['model'] ─────────────────────


def test_build_event_derives_provider_from_extra_model():
    """If only extra={'model': 'gpt-4o'} is provided, provider is still derived."""
    from qyra._internal import build_event

    e = build_event(
        aim_name="t",
        operation="o",
        extra={"model": "gpt-4o"},
    )
    assert e["model"] == "gpt-4o"
    assert e["model_provider"] == "openai"
