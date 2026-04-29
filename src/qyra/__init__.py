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

Configuration is environment-driven; no hardcoding required.
See :mod:`qyra.config` for the full list of variables.
"""
from __future__ import annotations

from .client import AsyncClient, Client
from .config import Config, get_config
from .health import attach_health_endpoints
from .instrument import instrument
from .telemetry import atrack, track, track_event

__all__ = [
    "AsyncClient",
    "Client",
    "Config",
    "atrack",
    "attach_health_endpoints",
    "get_config",
    "instrument",
    "track",
    "track_event",
]

__version__ = "0.1.1"
