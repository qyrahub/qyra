"""Internal helpers — not part of the public API.

Anything in this module can change without notice between minor versions.
"""
from __future__ import annotations

import json as _json
import logging
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
    except Exception:
        # We never let telemetry errors bubble.
        if _debug_enabled():
            logger.exception("qyra: failed to extract usage from response")
    return out


def build_event(
    *,
    aim_name: str,
    operation: str,
    success: bool = True,
    error: Optional[str] = None,
    extra: Optional[Mapping[str, Any]] = None,
    response: Any = None,
    user_id: Optional[int] = None,
    aim_version: str = "",
    latency_ms: Optional[int] = None,
) -> dict:
    """Build a telemetry event dict ready to be JSON-encoded."""
    payload: dict = {
        "aim_name": aim_name or "unknown",
        "operation": operation or "unknown",
        "success": bool(success),
    }
    if aim_version:
        payload["aim_version"] = aim_version
    if error is not None:
        payload["error"] = str(error)[:500]
    if user_id is not None:
        try:
            payload["user_id"] = int(user_id)
        except (TypeError, ValueError):
            pass
    if latency_ms is not None:
        try:
            payload["latency_ms"] = int(latency_ms)
        except (TypeError, ValueError):
            pass

    payload.update(safe_extract_usage(response))

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
