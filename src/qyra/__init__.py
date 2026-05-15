"""qyra — production infrastructure for HyperCycle AIMs.

A small, dependable toolkit for instrumenting, calling, and operating
AI Microservices (AIMs) on the HyperCycle network.

Quickstart:

    from fastapi import FastAPI
    from qyra import attach_health_endpoints, instrument, track

    app = FastAPI()
    attach_health_endpoints(app, aim_name="my-aim")

    @app.post("/work")
    @instrument(operation="work")
    async def do_work(payload: dict):
        # ... your logic ...
        return {"ok": True}

For ad-hoc LLM call instrumentation without a decorator, use the
:func:`track_call` / :func:`atrack_call` context managers — they
auto-measure latency and emit a single event covering the call::

    from qyra import track_call

    with track_call("ask", aim_name="my-aim") as ctx:
        resp = claude.messages.create(...)
        ctx.set_response(resp)

Configuration is environment-driven; no hardcoding required.
See :mod:`qyra.config` for the full list of variables.
"""

from __future__ import annotations

from .client import AsyncClient, Client
from .config import Config, get_config
from .health import attach_health_endpoints
from .instrument import instrument
from .telemetry import atrack, atrack_call, track, track_call, track_event

__all__ = [
    "AsyncClient",
    "Client",
    "Config",
    "atrack",
    "atrack_call",
    "attach_health_endpoints",
    "get_config",
    "instrument",
    "track",
    "track_call",
    "track_event",
]

__version__ = "0.1.5"
