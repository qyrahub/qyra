"""Health, readiness, and metrics endpoints for FastAPI apps.

Call :func:`attach_health_endpoints` once during app startup and qyra will
add three endpoints to your application:

- ``GET /health`` — liveness; always returns 200 once the app is running.
- ``GET /ready`` — readiness; configurable via a callback to gate dependencies.
- ``GET /metrics`` — process / runtime metrics in a simple JSON shape.

FastAPI is an optional dependency. Importing this module will not import FastAPI
unless :func:`attach_health_endpoints` is actually called.
"""
from __future__ import annotations

import os
import platform
import time
from typing import Any, Awaitable, Callable, Optional, Union

ReadinessCheck = Callable[[], Union[bool, Awaitable[bool]]]


def _now_iso() -> str:
    import datetime as _dt

    return _dt.datetime.now(tz=_dt.timezone.utc).isoformat()


def attach_health_endpoints(
    app: Any,
    *,
    aim_name: str,
    aim_version: str = "",
    readiness: Optional[ReadinessCheck] = None,
) -> None:
    """Mount ``/health``, ``/ready``, and ``/metrics`` on a FastAPI app.

    Parameters
    ----------
    app:
        A ``FastAPI`` instance.
    aim_name:
        Reported in every endpoint payload — useful for multi-AIM dashboards.
    aim_version:
        Optional version string.
    readiness:
        Optional sync or async callable returning ``True`` when the AIM is
        ready to accept traffic (e.g. database connection up, model loaded).
        Defaults to always-ready.
    """
    try:
        from fastapi import status  # noqa: F401  (validates fastapi presence)
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            "qyra.attach_health_endpoints requires fastapi. "
            "Install with: pip install 'qyra[fastapi]'"
        ) from e

    started_at = time.time()

    @app.get("/health", tags=["qyra"])
    async def _qyra_health() -> dict:
        return {
            "status": "ok",
            "aim_name": aim_name,
            "aim_version": aim_version,
            "uptime_seconds": int(time.time() - started_at),
            "now": _now_iso(),
        }

    @app.get("/ready", tags=["qyra"])
    async def _qyra_ready() -> dict:
        ready = True
        detail: Optional[str] = None
        if readiness is not None:
            try:
                result = readiness()
                if hasattr(result, "__await__"):
                    result = await result  # type: ignore[assignment]
                ready = bool(result)
            except Exception as exc:
                ready = False
                detail = f"{type(exc).__name__}: {exc}"
        body: dict = {
            "ready": ready,
            "aim_name": aim_name,
            "aim_version": aim_version,
            "now": _now_iso(),
        }
        if detail is not None:
            body["detail"] = detail
        return body

    @app.get("/metrics", tags=["qyra"])
    async def _qyra_metrics() -> dict:
        return {
            "aim_name": aim_name,
            "aim_version": aim_version,
            "uptime_seconds": int(time.time() - started_at),
            "process_id": os.getpid(),
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "now": _now_iso(),
        }
