"""HTTP clients for inter-AIM calls.

Two classes are provided:

- :class:`Client` for synchronous code.
- :class:`AsyncClient` for ``async def`` request handlers.

Both share the same retry / timeout / telemetry behaviour. Use the async
variant inside FastAPI endpoints to avoid blocking the event loop.

Example::

    from qyra import AsyncClient

    async def fetch_news():
        async with AsyncClient("aim-web-research", base_url="http://127.0.0.1:8087") as c:
            return await c.post("/research", json={"query": "HyperCycle"})
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Mapping, Optional

import httpx

from .config import Config, get_config
from .telemetry import atrack, track


class _RetryPolicy:
    """Exponential-backoff retry policy. Public-but-internal helper."""

    def __init__(self, max_retries: int = 2, base_delay: float = 0.25, max_delay: float = 4.0):
        self.max_retries = max(0, int(max_retries))
        self.base_delay = max(0.0, float(base_delay))
        self.max_delay = max(self.base_delay, float(max_delay))

    def delay_for(self, attempt: int) -> float:
        # attempt is 1-indexed (first retry = attempt 1).
        if attempt <= 0:
            return 0.0
        return min(self.max_delay, self.base_delay * (2 ** (attempt - 1)))


def _is_retryable_status(status: int) -> bool:
    # 408 Request Timeout, 425 Too Early, 429 Rate Limited, 5xx
    return status in (408, 425, 429) or 500 <= status < 600


class _ClientBase:
    """Shared configuration for sync/async clients."""

    def __init__(
        self,
        aim_name: str,
        *,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
        headers: Optional[Mapping[str, str]] = None,
        config: Optional[Config] = None,
    ):
        cfg = config or get_config()
        self.aim_name = aim_name
        self.base_url = base_url
        self.timeout = timeout if timeout is not None else cfg.client_timeout
        self.retry = _RetryPolicy(
            max_retries=max_retries if max_retries is not None else cfg.max_retries
        )
        self.headers = dict(headers or {})
        self._cfg = cfg


class Client(_ClientBase):
    """Synchronous HTTP client with retries and telemetry."""

    def __enter__(self) -> "Client":
        self._http = httpx.Client(
            base_url=self.base_url or "",
            timeout=self.timeout,
            headers=self.headers,
        )
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._http.close()

    def request(self, method: str, url: str, *, operation: Optional[str] = None, **kwargs: Any) -> httpx.Response:
        op = operation or f"{method.lower()}:{url.rsplit('/', 1)[-1] or 'root'}"
        # Ensure we have an httpx.Client even if the user didn't use the context manager.
        owns_http = not hasattr(self, "_http")
        if owns_http:
            self._http = httpx.Client(
                base_url=self.base_url or "",
                timeout=self.timeout,
                headers=self.headers,
            )

        try:
            attempt = 0
            t0 = time.perf_counter()
            while True:
                try:
                    resp = self._http.request(method, url, **kwargs)
                    if resp.status_code < 400 or not _is_retryable_status(resp.status_code):
                        elapsed_ms = int((time.perf_counter() - t0) * 1000)
                        track(
                            op,
                            aim_name=self.aim_name,
                            success=resp.status_code < 400,
                            error=None if resp.status_code < 400 else f"HTTP {resp.status_code}",
                            latency_ms=elapsed_ms,
                            config=self._cfg,
                        )
                        return resp
                    last_error = f"HTTP {resp.status_code}"
                except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as e:
                    last_error = f"{type(e).__name__}: {e}"

                attempt += 1
                if attempt > self.retry.max_retries:
                    elapsed_ms = int((time.perf_counter() - t0) * 1000)
                    track(
                        op,
                        aim_name=self.aim_name,
                        success=False,
                        error=last_error,
                        latency_ms=elapsed_ms,
                        config=self._cfg,
                    )
                    raise httpx.HTTPError(last_error)
                time.sleep(self.retry.delay_for(attempt))
        finally:
            if owns_http:
                self._http.close()
                del self._http

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, **kwargs)


class AsyncClient(_ClientBase):
    """Async HTTP client with retries and telemetry."""

    async def __aenter__(self) -> "AsyncClient":
        self._http = httpx.AsyncClient(
            base_url=self.base_url or "",
            timeout=self.timeout,
            headers=self.headers,
        )
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self._http.aclose()

    async def request(
        self, method: str, url: str, *, operation: Optional[str] = None, **kwargs: Any
    ) -> httpx.Response:
        op = operation or f"{method.lower()}:{url.rsplit('/', 1)[-1] or 'root'}"
        owns_http = not hasattr(self, "_http")
        if owns_http:
            self._http = httpx.AsyncClient(
                base_url=self.base_url or "",
                timeout=self.timeout,
                headers=self.headers,
            )

        try:
            attempt = 0
            t0 = time.perf_counter()
            while True:
                try:
                    resp = await self._http.request(method, url, **kwargs)
                    if resp.status_code < 400 or not _is_retryable_status(resp.status_code):
                        elapsed_ms = int((time.perf_counter() - t0) * 1000)
                        await atrack(
                            op,
                            aim_name=self.aim_name,
                            success=resp.status_code < 400,
                            error=None if resp.status_code < 400 else f"HTTP {resp.status_code}",
                            latency_ms=elapsed_ms,
                            config=self._cfg,
                        )
                        return resp
                    last_error = f"HTTP {resp.status_code}"
                except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as e:
                    last_error = f"{type(e).__name__}: {e}"

                attempt += 1
                if attempt > self.retry.max_retries:
                    elapsed_ms = int((time.perf_counter() - t0) * 1000)
                    await atrack(
                        op,
                        aim_name=self.aim_name,
                        success=False,
                        error=last_error,
                        latency_ms=elapsed_ms,
                        config=self._cfg,
                    )
                    raise httpx.HTTPError(last_error)
                await asyncio.sleep(self.retry.delay_for(attempt))
        finally:
            if owns_http:
                await self._http.aclose()
                del self._http

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", url, **kwargs)
