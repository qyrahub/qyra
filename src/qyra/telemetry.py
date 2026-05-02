"""Telemetry — fire-and-forget reporting of AIM events.

The two main entry points are :func:`track` (sync, safe to call from any context)
and :func:`atrack` (async, suitable for async request handlers).

Both functions are *non-blocking*: they enqueue the event and return immediately.
Reporting failures are silent by default — telemetry must never crash a request.
Set ``QYRA_DEBUG=1`` to log warnings on failures.

For ad-hoc LLM calls without a decorator, use the :func:`track_call` /
:func:`atrack_call` context managers — they auto-measure latency and emit
a single event per call.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import AsyncIterator, Iterator, Mapping
from contextlib import asynccontextmanager, contextmanager
from typing import Any

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


def track_event(event: Mapping[str, Any], *, config: Config | None = None) -> None:
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
    aim_name: str | None = None,
    aim_version: str | None = None,
    aim_owner: str | None = None,
    user_id: Any = None,
    success: bool = True,
    error: str | None = None,
    latency_ms: int | None = None,
    model: str | None = None,
    extra: Mapping[str, Any] | None = None,
    hypercycle_metadata: Mapping[str, Any] | None = None,
    config: Config | None = None,
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
        Optional measured latency in milliseconds. Use :func:`track_call`
        to have this measured automatically.
    model:
        Optional explicit model identifier when no response object is
        available. Used to derive ``model_provider``. ``response.model``
        takes precedence if both are supplied.
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
        model=model,
    )
    track_event(event, config=cfg)


async def atrack(
    operation: str,
    response: Any = None,
    *,
    aim_name: str | None = None,
    aim_version: str | None = None,
    aim_owner: str | None = None,
    user_id: Any = None,
    success: bool = True,
    error: str | None = None,
    latency_ms: int | None = None,
    model: str | None = None,
    extra: Mapping[str, Any] | None = None,
    hypercycle_metadata: Mapping[str, Any] | None = None,
    config: Config | None = None,
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
        model=model,
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


# ─── v0.1.3: track_call / atrack_call context managers ──────────────────────


class _TrackCallContext:
    """Context object yielded by :func:`track_call` / :func:`atrack_call`.

    Use :meth:`set_response` to attach an LLM response after the call so
    that ``model``, ``input_tokens``, ``output_tokens`` etc. are extracted
    automatically. Use :meth:`set_model` if you only know the model name.

    Any other event fields (``user_id``, ``hypercycle_metadata``, ``extra``)
    can be set via the corresponding attributes before the context exits.
    """

    __slots__ = (
        "error",
        "extra",
        "hypercycle_metadata",
        "model",
        "response",
        "user_id",
    )

    def __init__(self) -> None:
        self.response: Any = None
        self.model: str | None = None
        self.user_id: Any = None
        self.extra: Mapping[str, Any] | None = None
        self.hypercycle_metadata: Mapping[str, Any] | None = None
        self.error: str | None = None

    def set_response(self, response: Any) -> None:
        """Attach an Anthropic-shaped response. Tokens, model, cache fields
        will be extracted automatically when the context exits.
        """
        self.response = response

    def set_model(self, model: str) -> None:
        """Set the model name explicitly when no full response object is available."""
        self.model = model


@contextmanager
def track_call(
    operation: str,
    *,
    aim_name: str | None = None,
    aim_version: str | None = None,
    aim_owner: str | None = None,
    config: Config | None = None,
) -> Iterator[_TrackCallContext]:
    """Context manager that auto-measures latency and emits a telemetry event.

    Use this for ad-hoc LLM calls when you don't have a decorator-friendly
    function::

        from qyra import track_call

        with track_call("ask", aim_name="my-aim") as ctx:
            resp = claude.messages.create(...)
            ctx.set_response(resp)

    Behaviour:
    - Latency is measured from ``__enter__`` to ``__exit__`` using
      :func:`time.perf_counter`.
    - On clean exit, an event with ``success=True`` is emitted.
    - On exception, an event with ``success=False`` and a derived
      ``error`` string is emitted, then the exception is re-raised.
    - Telemetry failures are silent (consistent with :func:`track`).
    """
    cfg = config or get_config()
    ctx = _TrackCallContext()
    t0 = time.perf_counter()
    try:
        yield ctx
    except Exception as exc:
        elapsed = int((time.perf_counter() - t0) * 1000)
        # Don't swallow — we record then re-raise.
        track(
            operation,
            response=ctx.response,
            aim_name=aim_name,
            aim_version=aim_version,
            aim_owner=aim_owner,
            user_id=ctx.user_id,
            success=False,
            error=ctx.error or f"{type(exc).__name__}: {exc}",
            latency_ms=elapsed,
            model=ctx.model,
            extra=ctx.extra,
            hypercycle_metadata=ctx.hypercycle_metadata,
            config=cfg,
        )
        raise
    else:
        elapsed = int((time.perf_counter() - t0) * 1000)
        track(
            operation,
            response=ctx.response,
            aim_name=aim_name,
            aim_version=aim_version,
            aim_owner=aim_owner,
            user_id=ctx.user_id,
            success=True,
            error=ctx.error,  # caller may have set a non-fatal warning
            latency_ms=elapsed,
            model=ctx.model,
            extra=ctx.extra,
            hypercycle_metadata=ctx.hypercycle_metadata,
            config=cfg,
        )


@asynccontextmanager
async def atrack_call(
    operation: str,
    *,
    aim_name: str | None = None,
    aim_version: str | None = None,
    aim_owner: str | None = None,
    config: Config | None = None,
) -> AsyncIterator[_TrackCallContext]:
    """Async counterpart of :func:`track_call`.

    Use inside ``async def`` handlers::

        async with atrack_call("ask", aim_name="my-aim") as ctx:
            resp = await claude.messages.create(...)
            ctx.set_response(resp)
    """
    cfg = config or get_config()
    ctx = _TrackCallContext()
    t0 = time.perf_counter()
    try:
        yield ctx
    except Exception as exc:
        elapsed = int((time.perf_counter() - t0) * 1000)
        await atrack(
            operation,
            response=ctx.response,
            aim_name=aim_name,
            aim_version=aim_version,
            aim_owner=aim_owner,
            user_id=ctx.user_id,
            success=False,
            error=ctx.error or f"{type(exc).__name__}: {exc}",
            latency_ms=elapsed,
            model=ctx.model,
            extra=ctx.extra,
            hypercycle_metadata=ctx.hypercycle_metadata,
            config=cfg,
        )
        raise
    else:
        elapsed = int((time.perf_counter() - t0) * 1000)
        await atrack(
            operation,
            response=ctx.response,
            aim_name=aim_name,
            aim_version=aim_version,
            aim_owner=aim_owner,
            user_id=ctx.user_id,
            success=True,
            error=ctx.error,
            latency_ms=elapsed,
            model=ctx.model,
            extra=ctx.extra,
            hypercycle_metadata=ctx.hypercycle_metadata,
            config=cfg,
        )
