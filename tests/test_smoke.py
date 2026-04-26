"""Smoke tests for qyra v0.1.0 — fast, no network, no real services."""
from __future__ import annotations

import asyncio
import os
import time
from unittest.mock import patch

import pytest


def test_imports_and_version():
    """Package imports cleanly and exposes a version string."""
    import qyra

    assert qyra.__version__ == "0.1.0"
    assert callable(qyra.track)
    assert callable(qyra.atrack)
    assert callable(qyra.instrument)
    assert callable(qyra.attach_health_endpoints)
    assert qyra.Client is not None
    assert qyra.AsyncClient is not None
    assert qyra.Config is not None


def test_config_reads_environment():
    from qyra.config import Config, get_config

    with patch.dict(os.environ, {"QYRA_TELEMETRY_URL": "http://example.com/track", "QYRA_API_KEY": "abc123"}):
        cfg = get_config(refresh=True)
        assert cfg.telemetry_url == "http://example.com/track"
        assert cfg.api_key == "abc123"
        assert "X-Qyra-Api-Key" in cfg.headers()


def test_disabled_config_skips_telemetry():
    from qyra.config import get_config

    with patch.dict(os.environ, {"QYRA_DISABLED": "1"}):
        cfg = get_config(refresh=True)
        assert cfg.is_telemetry_enabled() is False


def test_track_is_nonblocking():
    """track() must return immediately even with a slow endpoint."""
    from qyra import track

    # Point at a non-routable IP — telemetry should not block the caller.
    with patch.dict(os.environ, {"QYRA_TELEMETRY_URL": "http://10.255.255.1:8098/track", "QYRA_TIMEOUT": "5"}):
        from qyra.config import get_config

        cfg = get_config(refresh=True)
        t0 = time.perf_counter()
        track("smoke", aim_name="test-aim", config=cfg)
        elapsed = time.perf_counter() - t0
        # Generous bound — even on slow CI we should be < 100ms because
        # the actual POST runs on a background thread.
        assert elapsed < 0.1


def test_atrack_is_nonblocking():
    """atrack() must not await the network."""
    from qyra import atrack

    async def runner():
        with patch.dict(os.environ, {"QYRA_TELEMETRY_URL": "http://10.255.255.1:8098/track"}):
            from qyra.config import get_config

            cfg = get_config(refresh=True)
            t0 = time.perf_counter()
            await atrack("smoke", aim_name="test-aim", config=cfg)
            return time.perf_counter() - t0

    elapsed = asyncio.run(runner())
    assert elapsed < 0.1


def test_instrument_decorator_sync():
    """Sync function decorated with @instrument runs and returns its value."""
    from qyra import instrument

    @instrument(operation="unit_op")
    def add(a, b):
        return a + b

    with patch.dict(os.environ, {"QYRA_DISABLED": "1"}):
        from qyra.config import get_config

        get_config(refresh=True)
        assert add(2, 3) == 5


def test_instrument_decorator_async():
    from qyra import instrument

    @instrument(operation="unit_op_async")
    async def add(a, b):
        return a + b

    async def runner():
        with patch.dict(os.environ, {"QYRA_DISABLED": "1"}):
            from qyra.config import get_config

            get_config(refresh=True)
            return await add(2, 3)

    assert asyncio.run(runner()) == 5


def test_instrument_propagates_exception():
    from qyra import instrument

    @instrument()
    def boom():
        raise ValueError("nope")

    with patch.dict(os.environ, {"QYRA_DISABLED": "1"}):
        from qyra.config import get_config

        get_config(refresh=True)
        with pytest.raises(ValueError):
            boom()


def test_build_event_extracts_anthropic_usage():
    """The internal helper should grok an Anthropic-shaped response."""
    from qyra._internal import build_event

    class FakeUsage:
        input_tokens = 10
        output_tokens = 20

    class FakeResponse:
        model = "claude-haiku-4-5-20251001"
        usage = FakeUsage()

    event = build_event(
        aim_name="test",
        operation="ask",
        success=True,
        response=FakeResponse(),
    )
    assert event["model"] == "claude-haiku-4-5-20251001"
    assert event["input_tokens"] == 10
    assert event["output_tokens"] == 20


def test_health_endpoints_mount():
    """attach_health_endpoints adds the three routes."""
    pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from qyra import attach_health_endpoints

    app = FastAPI()
    attach_health_endpoints(app, aim_name="unit-aim", aim_version="0.0.1")
    client = TestClient(app)

    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["aim_name"] == "unit-aim"
    assert r.json()["status"] == "ok"

    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json()["ready"] is True

    r = client.get("/metrics")
    assert r.status_code == 200
    assert r.json()["aim_name"] == "unit-aim"


def test_readiness_check_returning_false():
    pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from qyra import attach_health_endpoints

    app = FastAPI()
    attach_health_endpoints(app, aim_name="not-ready", readiness=lambda: False)
    client = TestClient(app)

    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json()["ready"] is False


def test_async_readiness_check():
    pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from qyra import attach_health_endpoints

    async def check():
        return True

    app = FastAPI()
    attach_health_endpoints(app, aim_name="async-ready", readiness=check)
    client = TestClient(app)

    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json()["ready"] is True
