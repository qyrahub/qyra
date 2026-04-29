"""Internal helpers — not part of the public API.

Anything in this module can change without notice between minor versions.
"""
from __future__ import annotations

import json as _json
import logging
import re as _re
import uuid as _uuid
from datetime import datetime as _dt, timezone as _tz
from typing import Any, Mapping, Optional
from urllib import error as _urlerr
from urllib import request as _urlreq

logger = logging.getLogger("qyra")

_QYRA_DEBUG_ENV = "QYRA_DEBUG"


def _truthy(value: Optional[str]) -> bool:
    return bool(value) and value.strip().lower() in ("1", "true", "yes", "on")


def _debug_enabled() -> bool:
    import os

    return _truthy(os.getenv(_QYRA_DEBUG_ENV))


# ─── v0.1.1 additions ───────────────────────────────────────────────────────


def now_iso8601() -> str:
    """Current UTC time as ISO8601 with microsecond precision and Z suffix."""
    return _dt.now(_tz.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def new_event_id() -> str:
    """Generate a UUID4 string for event idempotency."""
    return str(_uuid.uuid4())


# Pattern-based error classifier. Falls back to "unknown" when nothing matches.
_ERROR_PATTERNS = (
    (_re.compile(r"\b(timeout|timed out|deadline exceeded)\b", _re.I), "timeout"),
    (_re.compile(r"\b(rate.?limit|429|too many requests|quota)\b", _re.I), "rate_limit"),
    (_re.compile(r"\b(401|403|unauthor|forbid|api.?key|authentication)\b", _re.I), "auth"),
    (_re.compile(r"\b(5\d\d|server error|service unavailable|bad gateway)\b", _re.I), "model_error"),
    (_re.compile(r"\b(connection|network|dns|unreachable|reset by peer)\b", _re.I), "network"),
    (_re.compile(r"\b(4\d\d|invalid|malformed|bad request)\b", _re.I), "client_error"),
)


def classify_error(error: Optional[str]) -> Optional[str]:
    """Classify a free-form error string into a coarse category.

    Returns one of: "timeout", "rate_limit", "auth", "model_error",
    "network", "client_error", "unknown". Returns None for empty input.
    """
    if not error:
        return None
    text = str(error)
    for pattern, label in _ERROR_PATTERNS:
        if pattern.search(text):
            return label
    return "unknown"


# Provider detection from model name.
_PROVIDER_PATTERNS = (
    (_re.compile(r"^claude", _re.I), "anthropic"),
    (_re.compile(r"^(gpt|o\d|chatgpt|text-davinci)", _re.I), "openai"),
    (_re.compile(r"^(gemini|palm|bison)", _re.I), "google"),
    (_re.compile(r"^(llama|mistral|qwen|phi|gemma)", _re.I), "local"),
    (_re.compile(r"^ollama", _re.I), "local"),
    (_re.compile(r"^command", _re.I), "cohere"),
    (_re.compile(r"^deepseek", _re.I), "deepseek"),
)


def derive_model_provider(model: Optional[str]) -> Optional[str]:
    """Infer provider name from model identifier string.

    Returns provider name (lower-case) or "other" for unrecognized models,
    or None for empty input.
    """
    if not model:
        return None
    text = str(model)
    for pattern, label in _PROVIDER_PATTERNS:
        if pattern.search(text):
            return label
    return "other"


def safe_extract_usage(response: Any) -> dict:
    """Extract token usage from an Anthropic-shaped or compatible response.

    Returns a dict with ``model``, ``input_tokens``, ``output_tokens`` keys
    where present. Missing fields are simply omitted; never raises.
    """
    out: dict = {}
    if response is None:
        return out
    try:
        model = getattr(response, "model", None)
        if model:
            out["model"] = str(model)
        usage = getattr(response, "usage", None)
        if usage is not None:
            it = getattr(usage, "input_tokens", None)
            ot = getattr(usage, "output_tokens", None)
            if it is not None:
                try:
                    out["input_tokens"] = int(it)
                except (TypeError, ValueError):
                    pass
            if ot is not None:
                try:
                    out["output_tokens"] = int(ot)
                except (TypeError, ValueError):
                    pass
            # v0.1.1: cache tokens (Anthropic prompt caching)
            crt = getattr(usage, "cache_read_input_tokens", None)
            cwt = getattr(usage, "cache_creation_input_tokens", None)
            if crt is not None:
                try:
                    out["cache_read_tokens"] = int(crt)
                except (TypeError, ValueError):
                    pass
            if cwt is not None:
                try:
                    out["cache_write_tokens"] = int(cwt)
                except (TypeError, ValueError):
                    pass
    except Exception:
        # We never let telemetry errors bubble.
        if _debug_enabled():
            logger.exception("qyra: failed to extract usage from response")
    return out


def _hash_user_id(user_id: Any) -> Optional[str]:
    """Hash a user identifier with SHA256. Never sends raw IDs over the wire."""
    if user_id is None:
        return None
    try:
        import hashlib
        return hashlib.sha256(str(user_id).encode("utf-8")).hexdigest()
    except Exception:
        return None


def build_event(
    *,
    aim_name: str,
    operation: str,
    success: bool = True,
    error: Optional[str] = None,
    extra: Optional[Mapping[str, Any]] = None,
    response: Any = None,
    user_id: Any = None,
    aim_version: str = "",
    aim_owner: str = "",
    latency_ms: Optional[int] = None,
    hypercycle_metadata: Optional[Mapping[str, Any]] = None,
) -> dict:
    """Build a telemetry event dict ready to be JSON-encoded.

    v0.1.1 schema additions:
        event_id           — UUID4, client-generated for idempotency
        client_event_at    — ISO8601 UTC timestamp from client
        aim_owner          — author identifier (empty until Week 4 auth lands)
        error_class        — coarse error category (auto-derived from error)
        model_provider     — provider name (auto-derived from model)
        cache_read_tokens  — Anthropic prompt-cache reads
        cache_write_tokens — Anthropic prompt-cache writes
        user_id_hash       — SHA256 of user_id (raw never leaves the client)
        hypercycle_metadata — free-form JSON for HyperCycle-specific fields
    """
    payload: dict = {
        "event_id": new_event_id(),
        "client_event_at": now_iso8601(),
        "aim_name": aim_name or "unknown",
        "operation": operation or "unknown",
        "success": bool(success),
    }
    if aim_version:
        payload["aim_version"] = aim_version
    if aim_owner:
        payload["aim_owner"] = aim_owner
    if error is not None:
        payload["error"] = str(error)[:500]
        payload["error_class"] = classify_error(error)
    if user_id is not None:
        h = _hash_user_id(user_id)
        if h:
            payload["user_id_hash"] = h
    if latency_ms is not None:
        try:
            payload["latency_ms"] = int(latency_ms)
        except (TypeError, ValueError):
            pass

    usage = safe_extract_usage(response)
    payload.update(usage)
    if "model" in usage:
        provider = derive_model_provider(usage["model"])
        if provider:
            payload["model_provider"] = provider

    if hypercycle_metadata:
        payload["hypercycle_metadata"] = dict(hypercycle_metadata)

    if extra:
        # User-supplied keys may not collide with reserved names — overwrite is allowed,
        # but reserved keys win when both supplied. We choose to let extra override
        # so users can correct a misdetected field.
        for k, v in extra.items():
            payload[k] = v
    return payload


def post_urllib(url: str, headers: Mapping[str, str], payload: Mapping[str, Any], timeout: float) -> bool:
    """POST a JSON payload using the standard library only.

    Returns True on 2xx, False otherwise. Never raises.
    """
    try:
        data = _json.dumps(payload).encode("utf-8")
        req = _urlreq.Request(url, data=data, headers=dict(headers), method="POST")
        with _urlreq.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", 200)
            if 200 <= status < 300:
                return True
            if _debug_enabled():
                logger.warning("qyra urllib post non-2xx: status=%s", status)
            return False
    except _urlerr.HTTPError as e:
        if _debug_enabled():
            logger.warning("qyra urllib HTTPError: %s", e)
        return False
    except Exception as e:
        if _debug_enabled():
            logger.warning("qyra urllib exception: %s", e)
        return False
