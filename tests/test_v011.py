"""Tests for qyra v0.1.1 additions: schema extensions for the corpus."""
from __future__ import annotations

import os
import re
from unittest.mock import patch

import pytest


def test_event_id_is_uuid_and_unique():
    """Each event gets a fresh UUID4 — used by ingest for idempotency."""
    from qyra._internal import build_event, new_event_id

    e1 = build_event(aim_name="t", operation="o")
    e2 = build_event(aim_name="t", operation="o")
    # UUID4 shape
    uuid_re = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
    assert uuid_re.match(e1["event_id"])
    assert uuid_re.match(e2["event_id"])
    assert e1["event_id"] != e2["event_id"]
    # And the standalone helper works too
    assert uuid_re.match(new_event_id())


def test_client_event_at_is_iso8601_utc():
    """client_event_at must be ISO8601 with Z suffix (UTC)."""
    from qyra._internal import build_event, now_iso8601

    e = build_event(aim_name="t", operation="o")
    ts = e["client_event_at"]
    # Shape: 2026-04-29T13:06:49.809060Z
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z$", ts)
    # Standalone helper produces same shape
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z$", now_iso8601())


def test_classify_error_categories():
    """classify_error returns the documented enum values."""
    from qyra._internal import classify_error

    assert classify_error("Connection timed out") == "timeout"
    assert classify_error("HTTPError 429: rate limit exceeded") == "rate_limit"
    assert classify_error("401 Unauthorized: bad api_key") == "auth"
    assert classify_error("503 Service Unavailable") == "model_error"
    assert classify_error("DNS resolution failed") == "network"
    assert classify_error("400 Bad Request: malformed input") == "client_error"
    assert classify_error("Some completely random nonsense") == "unknown"
    assert classify_error("") is None
    assert classify_error(None) is None


def test_derive_model_provider_categories():
    """derive_model_provider maps model names to provider buckets."""
    from qyra._internal import derive_model_provider

    assert derive_model_provider("claude-sonnet-4-20250514") == "anthropic"
    assert derive_model_provider("claude-haiku-4-5-20251001") == "anthropic"
    assert derive_model_provider("gpt-4o") == "openai"
    assert derive_model_provider("o1-preview") == "openai"
    assert derive_model_provider("gemini-1.5-pro") == "google"
    assert derive_model_provider("llama3.2:3b") == "local"
    assert derive_model_provider("ollama/qwen2.5") == "local"
    assert derive_model_provider("command-r-plus") == "cohere"
    assert derive_model_provider("deepseek-coder") == "deepseek"
    assert derive_model_provider("some-novel-model") == "other"
    assert derive_model_provider("") is None
    assert derive_model_provider(None) is None


def test_cache_tokens_propagate_when_present():
    """Anthropic prompt-cache fields land in the event when present."""
    from qyra._internal import build_event

    class FakeUsage:
        input_tokens = 100
        output_tokens = 50
        cache_read_input_tokens = 200
        cache_creation_input_tokens = 300

    class FakeResponse:
        model = "claude-sonnet-4-20250514"
        usage = FakeUsage()

    e = build_event(aim_name="t", operation="o", response=FakeResponse())
    assert e["cache_read_tokens"] == 200
    assert e["cache_write_tokens"] == 300


def test_cache_tokens_absent_for_non_caching_responses():
    """Older responses without cache fields produce events without cache keys."""
    from qyra._internal import build_event

    class FakeUsage:
        input_tokens = 10
        output_tokens = 20

    class FakeResponse:
        model = "gpt-4o"
        usage = FakeUsage()

    e = build_event(aim_name="t", operation="o", response=FakeResponse())
    assert "cache_read_tokens" not in e
    assert "cache_write_tokens" not in e


def test_user_id_never_appears_raw():
    """The CRITICAL invariant: raw user_id must never escape the SDK."""
    from qyra._internal import build_event

    raw_pii = "alice@example.com"
    e = build_event(aim_name="t", operation="o", user_id=raw_pii)

    # Hash present
    assert "user_id_hash" in e
    assert isinstance(e["user_id_hash"], str)
    assert len(e["user_id_hash"]) == 64  # SHA256 hex

    # Old field name is gone
    assert "user_id" not in e

    # Raw value must not appear ANYWHERE in the event
    import json
    serialized = json.dumps(e)
    assert raw_pii not in serialized


def test_aim_owner_loads_from_environment():
    """QYRA_AIM_OWNER env var populates Config.aim_owner."""
    from qyra.config import get_config

    with patch.dict(os.environ, {"QYRA_AIM_OWNER": "qyrahub"}):
        cfg = get_config(refresh=True)
        assert cfg.aim_owner == "qyrahub"


def test_hypercycle_metadata_round_trips():
    """hypercycle_metadata kwarg lands in the event payload as a nested dict."""
    from qyra._internal import build_event

    meta = {"task_id": "t_abc123", "commitment_id": "c_xyz"}
    e = build_event(
        aim_name="t",
        operation="o",
        hypercycle_metadata=meta,
    )
    assert e["hypercycle_metadata"] == meta
    # And it doesn't leak into top-level keys
    assert "task_id" not in e
    assert "commitment_id" not in e


def test_error_class_auto_derived_when_error_set():
    """If error is set, error_class is automatically classified."""
    from qyra._internal import build_event

    e = build_event(
        aim_name="t",
        operation="o",
        success=False,
        error="HTTPError 429: rate limit exceeded",
    )
    assert e["error"] == "HTTPError 429: rate limit exceeded"
    assert e["error_class"] == "rate_limit"


def test_no_error_class_when_no_error():
    """A successful event has no error_class field."""
    from qyra._internal import build_event

    e = build_event(aim_name="t", operation="o", success=True)
    assert "error_class" not in e
    assert "error" not in e
