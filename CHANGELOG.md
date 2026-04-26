# Changelog

All notable changes to qyra will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-04-25

### Added

- Initial release.
- `qyra.telemetry.track()` and `qyra.telemetry.atrack()` — fire-and-forget
  telemetry POST to a Qyra-compatible ingestion endpoint. Captures latency,
  tokens, cost, model, success/error.
- `qyra.client.Client` and `qyra.client.AsyncClient` — HTTP clients for
  inter-AIM calls with configurable retry, timeout, and automatic telemetry.
- `qyra.instrument.instrument` — FastAPI decorator that auto-records
  per-endpoint latency, status code, and error class.
- `qyra.health.attach_health_endpoints()` — mounts `/health`, `/ready`, and
  `/metrics` on a FastAPI app with consistent shape.
- Environment-driven configuration: `QYRA_TELEMETRY_URL`, `QYRA_API_KEY`,
  `QYRA_AIM_NAME`, `QYRA_DISABLED`, `QYRA_TIMEOUT`, `QYRA_MAX_RETRIES`.
- Graceful httpx-or-stdlib fallback inside the telemetry path so qyra
  remains importable in minimal environments.

### Notes

This is an alpha release. Public APIs may change before 1.0.

[Unreleased]: https://github.com/qyratech/qyra/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/qyratech/qyra/releases/tag/v0.1.0
