"""Decorator for instrumenting FastAPI (or other) endpoints.

Usage::

    from qyra import instrument

    @app.post("/work")
    @instrument(operation="work")
    async def do_work(payload: dict):
        return {"ok": True}

The decorator records latency, success/failure, and exception class for every
call, then fires telemetry asynchronously. Both sync and async functions are
supported; the right reporting path is chosen automatically.
"""

from __future__ import annotations

import asyncio
import functools
import time
from collections.abc import Callable
from typing import Any

from .config import Config
from .telemetry import atrack, track


def instrument(
    operation: str | None = None,
    *,
    aim_name: str | None = None,
    aim_version: str | None = None,
    config: Config | None = None,
) -> Callable:
    """Wrap a function so each call emits a telemetry event.

    The operation name defaults to the wrapped function's ``__name__``.

    Parameters
    ----------
    operation:
        Override the operation name reported in telemetry.
    aim_name, aim_version, config:
        Forwarded to :func:`qyra.track` / :func:`qyra.atrack`.
    """

    def decorator(func: Callable) -> Callable:
        op_name = operation or getattr(func, "__name__", "unknown")
        is_async = asyncio.iscoroutinefunction(func)

        if is_async:

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                t0 = time.perf_counter()
                try:
                    result = await func(*args, **kwargs)
                    elapsed = int((time.perf_counter() - t0) * 1000)
                    await atrack(
                        op_name,
                        aim_name=aim_name,
                        aim_version=aim_version,
                        latency_ms=elapsed,
                        success=True,
                        config=config,
                    )
                    return result
                except Exception as exc:
                    elapsed = int((time.perf_counter() - t0) * 1000)
                    await atrack(
                        op_name,
                        aim_name=aim_name,
                        aim_version=aim_version,
                        latency_ms=elapsed,
                        success=False,
                        error=f"{type(exc).__name__}: {exc}",
                        config=config,
                    )
                    raise

            return async_wrapper

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            t0 = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                elapsed = int((time.perf_counter() - t0) * 1000)
                track(
                    op_name,
                    aim_name=aim_name,
                    aim_version=aim_version,
                    latency_ms=elapsed,
                    success=True,
                    config=config,
                )
                return result
            except Exception as exc:
                elapsed = int((time.perf_counter() - t0) * 1000)
                track(
                    op_name,
                    aim_name=aim_name,
                    aim_version=aim_version,
                    latency_ms=elapsed,
                    success=False,
                    error=f"{type(exc).__name__}: {exc}",
                    config=config,
                )
                raise

        return sync_wrapper

    return decorator
