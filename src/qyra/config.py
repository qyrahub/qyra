"""Configuration for qyra.

All configuration is environment-driven. Defaults are sensible for local
development; production deployments should set ``QYRA_TELEMETRY_URL``
and ``QYRA_API_KEY`` explicitly.

Recognised environment variables:

================================  ==============================================
Variable                          Purpose
================================  ==============================================
``QYRA_TELEMETRY_URL``            Telemetry ingestion endpoint.
                                  Default: ``http://127.0.0.1:8098/track``
``QYRA_API_KEY``                  API key sent with telemetry events.
                                  Default: empty (anonymous reporting allowed
                                  for self-hosted endpoints).
``QYRA_AIM_NAME``                 Default AIM name when not supplied to a call.
                                  Default: empty.
``QYRA_AIM_VERSION``              Optional version string reported in events.
                                  Default: empty.
``QYRA_DISABLED``                 ``1``/``true`` to disable all telemetry.
                                  Default: ``0``.
``QYRA_TIMEOUT``                  Telemetry HTTP timeout in seconds.
                                  Default: ``2.0``.
``QYRA_MAX_RETRIES``              Default retries for ``Client``/``AsyncClient``.
                                  Default: ``2``.
``QYRA_CLIENT_TIMEOUT``           Default timeout for inter-AIM client calls.
                                  Default: ``30.0``.
================================  ==============================================
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass
class Config:
    """Runtime configuration for qyra.

    Instances are typically obtained via :func:`get_config`, which reads from
    the process environment. Direct instantiation is also supported for tests
    or custom orchestration.
    """

    telemetry_url: str = field(
        default_factory=lambda: os.getenv("QYRA_TELEMETRY_URL", "http://127.0.0.1:8098/track")
    )
    api_key: str = field(default_factory=lambda: os.getenv("QYRA_API_KEY", ""))
    aim_name: str = field(default_factory=lambda: os.getenv("QYRA_AIM_NAME", ""))
    aim_version: str = field(default_factory=lambda: os.getenv("QYRA_AIM_VERSION", ""))
    disabled: bool = field(default_factory=lambda: _env_bool("QYRA_DISABLED", False))
    telemetry_timeout: float = field(default_factory=lambda: _env_float("QYRA_TIMEOUT", 2.0))
    max_retries: int = field(default_factory=lambda: _env_int("QYRA_MAX_RETRIES", 2))
    client_timeout: float = field(
        default_factory=lambda: _env_float("QYRA_CLIENT_TIMEOUT", 30.0)
    )

    def headers(self) -> dict:
        """HTTP headers attached to telemetry POSTs."""
        h = {"Content-Type": "application/json", "User-Agent": f"qyra-python/{_pkg_version()}"}
        if self.api_key:
            h["X-Qyra-Api-Key"] = self.api_key
        return h

    def is_telemetry_enabled(self) -> bool:
        return not self.disabled and bool(self.telemetry_url)


_cached_config: Optional[Config] = None


def get_config(refresh: bool = False) -> Config:
    """Return the process-wide :class:`Config`.

    The first call snapshots the environment. Pass ``refresh=True`` to
    re-read environment variables (useful in tests).
    """
    global _cached_config
    if refresh or _cached_config is None:
        _cached_config = Config()
    return _cached_config


def _pkg_version() -> str:
    """Return qyra's version, lazy-imported to avoid circulars."""
    try:
        from . import __version__

        return __version__
    except Exception:
        return "0.0.0"
