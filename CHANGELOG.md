# Changelog

All notable changes to qyra will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.1] - 2026-04-29

### Added
- `event_id`: UUID4 generated client-side for each telemetry event. Used by
  the ingest service for idempotency.
- `client_event_at`: ISO8601 UTC timestamp set client-side. Combined with the
  server-side `received_at` this lets the ingest detect clock skew.
- `error_class`: coarse error categorisation (timeout/rate_limit/auth/
  model_error/network/client_error/unknown), auto-derived from the `error`
  string. Heuristic, falls back to "unknown".
- `model_provider`: provider name auto-derived from the model identifier
  (anthropic/openai/google/local/cohere/deepseek/other).
- `cache_read_tokens` and `cache_write_tokens`: Anthropic prompt-cache token
  counts pulled from the response usage object when present.
- `aim_owner` field on `Config`, populated by the new `QYRA_AIM_OWNER`
  environment variable. Empty by default; populated when authors register
  in v0.2.
- `aim_owner` and `hypercycle_metadata` keyword arguments on `track()` and
  `atrack()`. The first is auto-merged from `Config`; the second is a
  free-form JSON blob for HyperCycle-specific event fields.
- `qyra._internal.now_iso8601()`, `new_event_id()`, `classify_error()`,
  `derive_model_provider()` helpers.

### Changed
- `track()` and `atrack()` accept `user_id: Any` (was `Optional[int]`). The
  raw value is hashed client-side with SHA256 and reported as `user_id_hash`.
  The raw `user_id` field is no longer included in the event payload.
- `safe_extract_usage()` now also extracts `cache_read_input_tokens` and
  `cache_creation_input_tokens` from Anthropic-shaped responses.

### Migration

For most users this is a backwards-compatible upgrade — no code changes
required. New event fields are additive. Existing AIMs continue to emit
the same events plus the new fields.

If your code relied on the literal `user_id` key being present in the
event payload, switch to `user_id_hash`. Raw user IDs are no longer
transmitted.

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

[Unreleased]: https://github.com/qyrahub/qyra/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/qyrahub/qyra/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/qyrahub/qyra/releases/tag/v0.1.0
