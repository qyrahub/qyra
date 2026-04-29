"""Telemetry — fire-and-forget reporting of AIM events.

The two main entry points are :func:`track` (sync, safe to call from any context)
and :func:`atrack` (async, suitable for async request handlers).

Both functions are *non-blocking*: they enqueue the event and return immediately.
Reporting failures are silent by default — telemetry must never crash a request.
Set ``QYRA_DEBUG=1`` to log warnings on failures.
"""
from __future__ import annotations

import asyncio
import threading
from typing import Any, Mapping, Optional

from ._internal import build_event, logger, post_urllib
from .config import Config, get_config

try:
    import httpx as _httpx  # type: ignore

    _HAVE_HTTPX = True
except ImportError:  # pragma: no cover — fallback path
    _HAVE_HTTPX = False
    _httpx = None  # type: ignore


def _post_sync(cfg: Config, event: dict) -> None:
    """Synchronous POST — used by the daemon thread in :func:`track`."""
    if _HAVE_HTTPX:
        try:
            with _httpx.Client(timeout=cfg.telemetry_timeout) as client:
                client.post(cfg.telemetry_url, json=event, headers=cfg.headers())
            return
        except Exception:
            # Fall through to urllib.
            pass
    post_urllib(cfg.telemetry_url, cfg.headers(), event, cfg.telemetry_timeout)


async def _post_async(cfg: Config, event: dict) -> None:
    """Async POST using httpx.AsyncClient when available."""
    if _HAVE_HTTPX:
        try:
            async with _httpx.AsyncClient(timeout=cfg.telemetry_timeout) as client:
                await client.post(cfg.telemetry_url, json=event, headers=cfg.headers())
            return
        except Exception:
            pass
    # urllib has no async story; offload to a thread.
    await asyncio.get_running_loop().run_in_executor(
        None, post_urllib, cfg.telemetry_url, cfg.headers(), event, cfg.telemetry_timeout
    )


def track_event(event: Mapping[str, Any], *, config: Optional[Config] = None) -> None:
    """Report a pre-built event dict synchronously (fire-and-forget).

    Lower-level than :func:`track`; useful when you've already constructed
    an event payload yourself and just want it shipped.
    """
    cfg = config or get_config()
    if not cfg.is_telemetry_enabled():
        return

    payload = dict(event)

    def _runner() -> None:
        try:
            _post_sync(cfg, payload)
        except Exception:
            logger.debug("qyra: telemetry post failed", exc_info=True)

    t = threading.Thread(target=_runner, daemon=True, name="qyra-telemetry")
    t.start()


def track(
    operation: str,
    response: Any = None,
    *,
    aim_name: Optional[str] = None,
    aim_version: Optional[str] = None,
    aim_owner: Optional[str] = None,
    user_id: Any = None,
    success: bool = True,
    error: Optional[str] = None,
    latency_ms: Optional[int] = None,
    extra: Optional[Mapping[str, Any]] = None,
    hypercycle_metadata: Optional[Mapping[str, Any]] = None,
    config: Optional[Config] = None,
) -> None:
    """Report a single event from synchronous code.

    Designed to be drop-in after a model call:

        response = claude.messages.create(...)
        track("ask", response, aim_name="my-aim")

    The function returns immediately — the actual POST runs on a daemon
    thread and any failure is silent unless ``QYRA_DEBUG=1`` is set.

    Parameters
    ----------
    operation:
        Free-form operation name. Convention: ``snake_case`` verb or
        ``verb_object`` (``ask``, ``generate_aim``, ``synthesise_results``).
    response:
        Optional Anthropic-shaped response. Used to extract ``model`` and
        ``input_tokens``/``output_tokens`` automatically.
    aim_name:
        AIM identifier. Falls back to ``QYRA_AIM_NAME`` if not provided.
    aim_version:
        Optional version of the AIM, useful for staged rollouts.
    user_id:
        Optional integer user id.
    success:
        Whether the call succeeded.
    error:
        Optional error description for failed calls (truncated to 500 chars).
    latency_ms:
        Optional measured latency in milliseconds.
    extra:
        Optional additional fields to merge into the event payload.
        Reserved keys (``aim_name``, ``operation``, ``success``, ``error``)
        are overridable by ``extra`` to allow corrections.
    """
    cfg = config or get_config()
    if not cfg.is_telemetry_enabled():
        return

    event = build_event(
        aim_name=aim_name or cfg.aim_name or "unknown",
        operation=operation,
        success=success,
        error=error,
        extra=extra,
        response=response,
        user_id=user_id,
        aim_version=aim_version or cfg.aim_version,
        aim_owner=aim_owner or cfg.aim_owner,
        latency_ms=latency_ms,
        hypercycle_metadata=hypercycle_metadata,
    )
    track_event(event, config=cfg)


async def atrack(
    operation: str,
    response: Any = None,
    *,
    aim_name: Optional[str] = None,
    aim_version: Optional[str] = None,
    aim_owner: Optional[str] = None,
    user_id: Any = None,
    success: bool = True,
    error: Optional[str] = None,
    latency_ms: Optional[int] = None,
    extra: Optional[Mapping[str, Any]] = None,
    hypercycle_metadata: Optional[Mapping[str, Any]] = None,
    config: Optional[Config] = None,
) -> None:
    """Async counterpart of :func:`track`.

    Schedules the POST as an :func:`asyncio.create_task` and returns immediately.
    Suitable for use inside async request handlers without blocking the event loop.
    """
    cfg = config or get_config()
    if not cfg.is_telemetry_enabled():
        return

    event = build_event(
        aim_name=aim_name or cfg.aim_name or "unknown",
        operation=operation,
        success=success,
        error=error,
        extra=extra,
        response=response,
        user_id=user_id,
        aim_version=aim_version or cfg.aim_version,
        aim_owner=aim_owner or cfg.aim_owner,
        latency_ms=latency_ms,
        hypercycle_metadata=hypercycle_metadata,
    )

    async def _runner() -> None:
        try:
            await _post_async(cfg, event)
        except Exception:
            logger.debug("qyra: async telemetry post failed", exc_info=True)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_runner(), name="qyra-telemetry")
    except RuntimeError:
        # No running loop — degrade to sync threaded path.
        track_event(event, config=cfg)
