# Changelog

All notable changes to qyra will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.3] - 2026-05-02

### Added
- `track_call()` context manager: auto-measures latency of a code block
  and emits a single telemetry event covering the call. Closes the
  ergonomic gap where bare `track()` calls shipped without `latency_ms`.
  ```python
  from qyra import track_call

  with track_call("ask", aim_name="my-aim") as ctx:
      resp = claude.messages.create(...)
      ctx.set_response(resp)
  ```
- `atrack_call()`: async counterpart of `track_call`, for use inside
  `async def` request handlers.
- `model` keyword argument on `track()` and `atrack()`. Lets callers
  specify the model identifier explicitly when no full response object
  is available, so `model_provider` is still auto-derived. The response
  object's `model` field still takes precedence when both are supplied.

### Changed
- Provider auto-detection patterns expanded:
  - OpenAI now matches `text-embedding-*`, `dall-e-*`, `whisper-*`, `tts-*`
    in addition to the existing `gpt-*` / `o\d` patterns.
  - Google now matches `embedding-gecko` and `text-bison`.
  - Local models now match `mixtral`, `codellama`.
  - New fallback: any model identifier containing `:` (Ollama-style
    `name:tag`) is treated as `local` when no other pattern matches.
  This fixes silent `null` `model_provider` fields for events emitted
  from local Ollama installs and OpenAI's non-chat models.
- `build_event()` now derives `model_provider` from any source of model
  information in priority order: `response.model` → `model` kwarg →
  `extra['model']`. Previously only `response.model` triggered derivation.

### Notes
- All changes are additive — v0.1.2 callers continue to work unchanged.
- No new dependencies.

## [0.1.2] - 2026-05-01

### Changed
- Default `QYRA_TELEMETRY_URL` changed from `http://127.0.0.1:8098/track`
  to `https://api.qyratech.com/hypercycle/track`. Installs without an
  explicit `QYRA_TELEMETRY_URL` set will now post telemetry events to the
  public Qyra ingest endpoint by default. Set `QYRA_DISABLED=1` to silence
  telemetry, or set `QYRA_TELEMETRY_URL` to point at your own ingest.

### Fixed
- The previous default URL was broken: port 8098 belonged to a different
  service and the path was missing the `/hypercycle/` prefix. Anyone running
  with default config was emitting POSTs that 404'd silently. The new
  default points at a working public endpoint.


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

[Unreleased]: https://github.com/qyrahub/qyra/compare/v0.1.2...HEAD
[0.1.2]: https://github.com/qyrahub/qyra/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/qyrahub/qyra/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/qyrahub/qyra/releases/tag/v0.1.0
