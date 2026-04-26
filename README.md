# qyra

[![CI](https://github.com/qyrahub/qyra/actions/workflows/ci.yml/badge.svg)](https://github.com/qyrahub/qyra/actions/workflows/ci.yml)

[![PyPI](https://img.shields.io/pypi/v/qyra.svg)](https://pypi.org/project/qyra/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

Production infrastructure for HyperCycle AIMs.

`qyra` is a small, dependable toolkit for building, instrumenting, and operating
AI Microservices on the HyperCycle network. It gives you four things that every
production AIM needs and that you'd otherwise re-implement: telemetry, retries,
health endpoints, and inter-AIM routing.

## Why qyra

If you're building an AIM today, you're probably writing the same handful of
boilerplate every time:

- A `try/except` around every model call to log latency and tokens.
- An ad-hoc retry loop when the next-hop AIM hiccups.
- `/health` and `/ready` endpoints copy-pasted from your last service.
- A homegrown HTTP client with timeouts you tune by trial and error.

`qyra` standardises this so you can focus on what your AIM actually does.

## Install

```bash
pip install qyra
```

For FastAPI integration (recommended):

```bash
pip install 'qyra[fastapi]'
```

## 30-second quickstart

```python
from fastapi import FastAPI
from qyra import attach_health_endpoints, instrument, track

app = FastAPI()
attach_health_endpoints(app, aim_name="my-aim", aim_version="0.1.0")

@app.post("/ask")
@instrument(operation="ask")
async def ask(payload: dict):
    # your model call here
    response = call_my_model(payload["question"])
    track("ask", response, aim_name="my-aim")
    return {"answer": response.text}
```

That's it. Every call to `/ask` now reports latency, success/failure, model,
and token usage to your telemetry endpoint. `/health`, `/ready`, and `/metrics`
exist automatically.

## Configuration

`qyra` is environment-driven. The most common variables:

| Variable                | Purpose                                                |
| ----------------------- | ------------------------------------------------------ |
| `QYRA_TELEMETRY_URL`    | Where to POST telemetry events.                        |
| `QYRA_API_KEY`          | API key sent in the `X-Qyra-Api-Key` header.           |
| `QYRA_AIM_NAME`         | Default AIM name when not passed to a call.            |
| `QYRA_DISABLED`         | Set to `1` to silence telemetry (useful in tests).     |

Full list: see [`src/qyra/config.py`](src/qyra/config.py).

## Inter-AIM calls

`qyra.AsyncClient` (and `qyra.Client`) wrap `httpx` with retries, timeouts,
and automatic telemetry:

```python
from qyra import AsyncClient

async def fetch_news():
    async with AsyncClient("aim-web-research", base_url="http://127.0.0.1:8087") as c:
        resp = await c.post("/research", json={"query": "HyperCycle"})
        return resp.json()
```

Failed calls are retried with exponential backoff. Every call — successful
or not — emits a telemetry event tagged with the operation name.

## What qyra is not

- **Not a competing AIM marketplace.** It plays well with HMS, HyperCycle's
  own marketplace.
- **Not a node-operator certification.** That's HyperCycle's 88.88
  Certification — we operate at the AIM layer, not the node layer.
- **Not magic.** It's a thin layer over `httpx` and FastAPI. Read the source.

## License

Apache 2.0 — see [LICENSE](LICENSE).

## Status

This is an alpha release (0.1.0). The public API may shift before 1.0.
We use semantic versioning from 1.0 onward.

---

Built by [Qyratech](https://qyratech.com) for the HyperCycle ecosystem.
