# AI Adapter

A provider-independent, reliability-first AI adapter service built with Python 3.14 and FastAPI.

The finished system will route application requests across multiple AI providers with timeouts, bounded retries, circuit breaking, budget enforcement, deterministic fallback, fault-report summarization, regression testing, cost/latency monitoring, and a Streamlit operations dashboard.

> **Current status: STAGE M complete — all planned stages A–M are implemented.**  
> Stage A provides the application foundation. Stage B adds the provider contract, provider registry, deterministic local fake provider, provider-management API, normalized generation endpoint, and provider error taxonomy. Stage C adds a live OpenAI chat-completions adapter behind the same contract, with validated configuration, normalized error mapping, health checks, and secret-safe handling. Stage D adds per-attempt timeouts, bounded retries with exponential backoff and jitter, per-provider circuit breakers, secondary-provider switching, and a deterministic local fallback, all orchestrated by a provider-independent reliability layer. Stage E adds bearer-key authentication with user/admin roles, admin-protected provider management, fixed-window rate limiting, concurrency-safe per-request/daily/monthly budget reservations with provider-specific pricing, cost reporting, and a risk-focused request summary log. Stage F adds an industrial fault-report summarizer that returns a Pydantic-validated structured summary, uses strict JSON validation for AI output, and falls back to deterministic rule-based extraction when the AI response is unusable, without inventing unknown values. Stage G adds asynchronous SQLAlchemy persistence with Alembic migrations, a metadata-only request-log table for generation and fault requests (including normalized failures), and admin-only request-history endpoints with filters and pagination. Stage H adds a deterministic, test-only fault-injection matrix covering provider timeouts, rate limits, server failures, invalid responses, identity mismatches, terminal client errors, malformed AI output, circuit breaking, fallback, admission failures, persistence metadata, and secret-leak checks. Stage I adds a validated model-version manifest and catalog that fails startup closed when configured models lack safe release metadata, an admin-only model inventory endpoint, readiness integration, and a deterministic golden-contract regression suite with an explicit baseline-update workflow. Stage J adds a GitHub Actions quality gate and an equivalent Windows-local runner: byte-compilation, Ruff static analysis, the full pytest suite, the fault matrix, the regression suite, and a check that committed baselines were not rewritten. Stage K adds bounded cost/latency reporting over persisted request logs (p50, p95, average, success/degraded/error rates, provider failure and fallback rates, cost per request, and cost per accepted result) plus an admin-protected Prometheus text endpoint fed by a process-local collector with bounded labels. Stage L adds a separate, read-only Streamlit operations dashboard that talks to the admin API over HTTP, with live/readiness status, windowed cost and latency reporting, provider inventory and health checks, filtered request history, model-version inventory, and a bounded Prometheus exposition viewer. Stage M adds a multi-stage Dockerfile with hardened API and dashboard targets, a PostgreSQL-backed Compose stack with migrations and health-gated startup, a secret-generating PowerShell demo with deterministic teardown, and an HTTP end-to-end verifier covering readiness, both business paths, authorization, failure handling, monitoring, metrics, history, model inventory, and the dashboard.
>
> Docker container execution was not possible on the implementation host because Docker Desktop, Podman, WSL, and a Docker daemon are not installed. Deployment artifacts are covered by contract tests, `docker compose config` runs automatically when a Docker CLI is available, and the same end-to-end verifier passed against the API and dashboard running natively. The first real image build and container run must be performed on a Docker-capable host.

---

## 1. Implemented capabilities

| Area | Status | Implementation |
|---|---|---|
| Application foundation | Complete (A) | Typed settings, JSON logging, request IDs, health/system endpoints |
| Provider interface | Complete (B) | `AIProvider` async contract shared by every adapter |
| Normalized schemas | Complete (B) | Validated chat messages, generation request/result, token usage, health |
| Provider registry | Complete (B) | Startup registration, lookup, listing, health forwarding, shutdown |
| Local fake provider | Complete (B) | Offline deterministic generation, model switching, token estimates |
| Provider management API | Complete (B) | List, inspect, and health-check registered providers |
| Generation API | Complete (D) | Explicit/default provider selection routed through the reliability chain |
| Provider error taxonomy | Complete (B) | Normalized errors mapped to safe HTTP responses |
| OpenAI provider | Complete (C) | Async HTTPX adapter for `/chat/completions`, configurable models/base URL/timeout |
| OpenAI error translation | Complete (C) | Auth, invalid request, rate limit, server, timeout, transport, and payload failures normalized |
| OpenAI health check | Complete (C) | Bounded `/models` check with healthy/degraded/unavailable reporting |
| Live verification tool | Complete (C) | `scripts/verify-openai.ps1` for one explicit billable request |
| Request timeouts | Complete (D) | Per-attempt deadline enforced above every adapter |
| Bounded retries | Complete (D) | Per-provider attempt ceiling, exponential backoff, configurable jitter |
| Circuit breaker | Complete (D) | Per-provider closed/open/half-open states, single recovery probe |
| Secondary + fallback routing | Complete (D) | Selected/default → optional secondary → deterministic local fallback |
| Authentication | Complete (E) | Bearer API keys, SHA-256 digests, user/admin roles, fail-closed production |
| Authorization | Complete (E) | Provider management is admin-only; generation requires a valid identity |
| Rate limiting | Complete (E) | Atomic fixed-window limit per key or client address with `Retry-After` |
| Budget management | Complete (E) | Per-request/daily/monthly USD limits with pre-call reservation and rollover |
| Cost calculation | Complete (E) | Decimal pricing per million tokens, reported per response and in summary logs |
| Fault-report summarization | Complete (F) | Strict JSON extraction through the provider chain with validated six-field output |
| Deterministic fault fallback | Complete (F) | Rule-based extraction when AI output or the provider chain is unusable |
| Database persistence | Complete (G) | Async SQLAlchemy engine, SQLite local mode, PostgreSQL production mode, Alembic migrations |
| Request logging | Complete (G) | Metadata-only generation/fault records for `200`, `401`, `402`, `404`, `422`, and `429` |
| Request history API | Complete (G) | Admin-only filtered/paginated history and single-record detail |
| Persistence readiness | Complete (G) | `/health/ready` checks connection and `request_logs` schema when enabled |
| Fault-injection matrix | Complete (H) | 31 deterministic end-to-end tests across provider, reliability, output, admission, persistence, and log-safety faults |
| Model version management | Complete (I) | Validated JSON manifest, active/deprecated/retired lifecycle, startup coverage checks, admin inventory, readiness signal |
| Contract regression baselines | Complete (I) | 7 golden HTTP contract snapshots plus 19 manifest/catalog tests with an explicit update workflow |
| CI quality gate | Complete (J) | GitHub Actions on Python 3.14, Ruff, compile checks, full/fault/regression suites, unchanged-baseline check, local Windows mirror |
| Cost and latency reporting | Complete (K) | Admin-only windowed summary with bounded SQL aggregates over `request_logs` |
| Performance evidence | Complete (K) | p50/p95/average latency, accepted/success/degraded/error rates, provider failure and fallback rates, cost per request and per accepted result |
| Prometheus metrics | Complete (K) | Admin-only text exposition fed by a process-local collector with bounded labels |
| Operations dashboard | Complete (L) | Separate read-only Streamlit process with five operational views over the admin API |
| Dashboard resilience | Complete (L) | HTTPS/loopback validation, bounded HTTP timeouts, sanitized errors, no redirects, no ambient proxy inheritance |
| Dashboard data safety | Complete (L) | Boundary-validated API models, bounded metrics parsing, XSS-safe rendering, admin key held in process memory only |
| Monitoring dashboard | Complete (L) | Overview, providers, requests, model versions, and Prometheus metrics views |
| Container images | Complete (M) | Multi-stage Dockerfile with shared non-root runtime and separate API/dashboard targets |
| Container composition | Complete (M) | PostgreSQL, API, and dashboard services with health-gated startup and named persistence |
| Deployment hardening | Complete (M) | Read-only root filesystems, dropped capabilities, no-new-privileges, init, loopback-only ports, internal database network |
| Automated database migration | Complete (M) | API entrypoint runs `alembic upgrade head` with bounded retries before serving |
| Deployment demonstration | Complete (M) | `scripts\demo.ps1` generates random local secrets, starts the stack, verifies it, and tears it down |
| End-to-end verification | Complete (M) | HTTP verifier covers readiness, generation, fault extraction, error paths, auth, monitoring, metrics, history, models, and dashboard |
| Tests | Complete | **340 passed, 1 skipped**, including 31 fault-matrix, 26 Stage I regression/model-version, 7 Stage J CI contract, 15 Stage K monitoring, 29 Stage L dashboard, and 16 Stage M deployment contract tests (15 passed, 1 conditional skip); the skipped test validates `docker compose config` when a Docker CLI is present |

### Deliberately not in Stages C–M

- No vendor-SDK retry logic. Retry orchestration lives in the reliability layer with a hard total-attempt ceiling.
- No streaming or partial results; fallback decisions operate on complete normalized results.
- No per-request reliability overrides; timeout, attempt, circuit, secondary, and fallback behavior are deployment configuration.
- No distributed rate limiting or shared budget ledger. Both are atomic within one process; request history is shared through the database, but rate and budget state remain process-local.
- No per-end-user quotas or billing; budgets are service-wide daily/monthly limits.
- No HTTP provider-registration admin endpoint; registration is code/config driven.
- No runtime fault-injection endpoint or environment switch. Stage H injects faults only through test doubles, so production traffic cannot be placed into a failure mode over HTTP.
- No runtime model-manifest reload. Version metadata is validated at startup; operators restart the service after changing the manifest.
- No automatic provider model discovery or manifest updates. The deployment manifest is reviewed configuration, not a live vendor catalog.
- No model-version column in `request_logs`; persisted rows retain the model identifier, while release metadata is resolved through the manifest and admin inventory.
- No artifact publishing, image registry push, or hosted deployment. Stage M builds and runs the stack locally; registry credentials, provenance, and environment promotion belong to a delivery pipeline.
- No hosted CI result is claimed from the local workspace. The workflow is validated locally, but its first GitHub-hosted run occurs after the project is pushed to a GitHub repository.
- No Kubernetes, Swarm, or other orchestrator; no autoscaling, rolling updates, or multi-host scheduling. Compose is a single-host demonstration topology.
- No TLS termination, reverse proxy, or public ingress. Both published ports bind to loopback by default; a real deployment must place TLS and authentication-aware proxying in front of the services.
- No production secret manager integration. Compose receives secrets through `.env.docker` or the shell; operators should inject them from Docker secrets, a vault, or the platform's secret store in production.
- No image vulnerability scanning, SBOM generation, image signing, or base-image digest pinning policy. Those supply-chain controls belong to the image publishing pipeline.
- No containerized E2E run is claimed on the implementation host. Docker is absent there; the end-to-end verifier was executed against natively started services, and deployment files are covered by contract tests plus a conditional Compose validation.
- No Streamlit dashboard with write actions. Stage L is read-only: it never generates content, changes providers, edits budgets, or triggers fault injection.
- No dashboard-side user accounts, sessions, or authorization service. The dashboard authenticates to the admin API with an operator-supplied admin key; roles, rate limiting, and audit remain server-side.
- No dashboard credential persistence. The admin key is read from `DASHBOARD_ADMIN_API_KEY` by preference; a key entered in the sidebar lives only in the running Streamlit process memory and is never written to disk, URLs, logs, or browser storage.
- No cached or background data collection. Each view fetches on demand through a bounded HTTP client; there is no scheduler, database access from the dashboard, or stored history beyond what the API returns.
- No Grafana, alerting, or metric retention stack (Stage K/L). The dashboard displays the API's Prometheus text and bounded summaries; scraping, storage, and alert rules belong to a deployment's monitoring platform.
- No automated browser E2E suite. UI coverage uses Streamlit's headless `AppTest` against a local Uvicorn fixture; no Selenium/Playwright browser grid is part of the quality gate.
- No time-series history endpoint. `/monitoring/summary` aggregates one UTC window on demand from `request_logs`.
- No full-population percentile scan. p50/p95 use the latest bounded duration sample and set `sample_truncated`; average/min/max/counts come from SQL over the full window.
- No per-attempt failure ledger. Provider failure rate is request-level: requests that ended in a provider-attributed error divided by requests whose final row names a provider.
- No invoice reconciliation or vendor billing import. Costs are the application's configured-price estimates.
- No cross-process aggregation for Prometheus counters. Metrics are process-local and reset on restart; the database-backed summary remains durable.
- No request-log retention job or purge endpoint; operators manage retention with PostgreSQL policy or scheduled SQL.
- No prompt, completion, report text, authorization header, or API key is persisted. Request-log rows contain operational metadata only.
- No file/OCR ingestion for fault reports; the endpoint accepts JSON text only.
- No unit conversion, inference, or repair of incomplete fault data. A missing or unknown field stays `null` and is listed in `missing_fields`.
- No live paid request was made during implementation because no OpenAI key was configured in the development environment. Wire behavior and API integration are covered with `httpx.MockTransport`; separate scripts and local unreachable-endpoint runs support live verification when a key is available.

---

## 2. Architecture

### Request flow

```text
Client
  |
  v
RequestContextMiddleware
  |-- validate or generate request ID
  |-- start timer
  v
POST /api/v1/generate
  |-- Pydantic GenerateRequest validation
  |-- SecurityManager: bearer key -> user/admin identity
  |-- RateLimiter: fixed window per key or client address
  |-- ProviderRouter.generate(...)
  |     |-- bounded chain: selected/default -> optional secondary -> deterministic fallback
  |     |-- per provider: BudgetManager.reserve -> CircuitBreaker -> TimeoutManager -> AIProvider.generate
  |     |-- per provider: RetryManager (attempt ceiling, backoff, jitter)
  |     +-- stop on success or invalid-request; otherwise try the next provider
  v
RouteResult (result + requested_provider, providers_tried, retry_count, fallback metadata)
  |-- provider, model, content, token usage, finish reason, latency
  v
GenerateResponse + request_id + cost_usd
  |-- X-Request-ID, X-RateLimit-Limit, X-RateLimit-Remaining headers
  |-- one safe JSON access-log line and one request.summary line

POST /api/v1/fault-reports/summarize
  |-- Pydantic FaultReportRequest validation
  |-- the same authentication and rate limiting
  |-- FaultReportService.summarize(...)
  |     |-- ProviderRouter.generate(...) with a strict JSON prompt
  |     |-- strict JSON parse -> Pydantic FaultSummary validation
  |     +-- deterministic rule-based extraction if AI output or the chain is unusable
  v
FaultSummaryResponse (summary + extraction mode + missing fields + route/cost metadata)
  |
  +-- RequestLogService.record(...) -> async SQLAlchemy repository -> SQLite/PostgreSQL
      |-- success/degraded status and operational metadata only
      +-- bounded write timeout; persistence failure is logged but never changes the response
```

### Provider boundary

```text
app/api/routes/generation.py
        |
        v
app/reliability/router.py  <-- ProviderRouter, CircuitBreaker,
        |                       TimeoutManager, RetryManager
        v
app/providers/base.py  <-- AIProvider ABC
        ^
        | implements
        +-- app/providers/fake.py    (Stage B)
        +-- app/providers/openai.py  (Stage C)
        ^
        | registered in
app/providers/registry.py
```

Provider-specific request/response shapes and error payloads are translated inside concrete adapters. Route handlers depend only on:

- `GenerationRequest`
- `GenerationResult`
- `ProviderHealth`
- `ProviderInfo`
- normalized `ProviderError` subclasses
- `RouteResult` from the reliability layer

`app/faults/service.py` follows the same rule: it depends on `ProviderRouter`, `BudgetManager`, and the normalized schemas, never on a vendor adapter or vendor response shape.

### Reliability chain (Stage D)

```text
app/reliability/router.py
  |-- chain: primary (selected/default) -> secondary (optional) -> fallback (deterministic local)
  |-- app/reliability/circuit_breaker.py   per-provider closed / open / half-open
  |-- app/reliability/timeout.py           per-attempt asyncio deadline
  +-- app/reliability/retry.py             bounded attempts, exponential backoff, jitter
```

Rules enforced by the router:

- **Bounded work.** Each provider gets at most `RELIABILITY_MAX_ATTEMPTS` attempts and the chain has at most three distinct providers, so a request can never loop. The total ceiling is `3 x RELIABILITY_MAX_ATTEMPTS`.
- **Retry only what can succeed again.** Retryable normalized errors (`provider_server_error`, `provider_unavailable`, `provider_timeout`, `provider_rate_limit`, `provider_invalid_response`) are retried. Authentication failures, invalid requests, and open circuits are not.
- **Client errors stay client errors.** A `provider_invalid_request` aborts the chain immediately; it is never masked by fallback success. It also does not count as a circuit failure.
- **Deterministic fallback.** If the selected provider and optional secondary are exhausted or circuit-open, the configured local fake provider produces a deterministic result. Fallback is reported, never silent.
- **Model remapping.** The primary receives the caller's requested model. A secondary or fallback receives that model only if it declares it; otherwise it uses its own default model.
- **Circuit breaker.** Consecutive qualifying failures open a provider's circuit for `RELIABILITY_CIRCUIT_RECOVERY_SECONDS`. While open, calls are rejected without contacting the provider. After recovery, exactly one half-open probe is allowed; success closes the circuit, failure re-opens it. State transitions contain no awaits and are atomic on the event loop.
- **Attempt deadline.** Each attempt runs under `RELIABILITY_TIMEOUT_SECONDS`; expiry becomes a retryable `provider_timeout`.
- **Idempotency.** Every attempt builds a fresh immutable `GenerationRequest` and validates the complete normalized result. Requests are non-streaming and retries have no partial side effects, so re-issuing an attempt is safe.
- **Result identity.** A provider whose result carries a different provider name is treated as invalid and counted as a circuit failure.
- **Safe observability.** Retry and routing logs contain provider names, attempt numbers, delays, and error codes only — never prompts, headers, or error text.

### Security and cost boundary (Stage E)

```text
app/api/deps.py
  |-- app/security/manager.py      bearer key -> AuthIdentity(role, rate_limit_key)
  |-- app/security/rate_limit.py   fixed-window limiter, atomic per event loop
  +-- app/budget/manager.py        reserve -> settle / release, daily + monthly rollover
```

Rules enforced by the Stage E boundary:

- **Fail closed in production.** `ENVIRONMENT=production` refuses to start unless `SECURITY_REQUIRE_AUTH=true` and at least one user key is configured. Development and test may run without auth for local convenience.
- **Digest-only key storage.** Configured keys are split, trimmed, de-duplicated, and validated (16–512 characters, no whitespace), then reduced to SHA-256 digests in memory. Raw keys are compared with `secrets.compare_digest` and never logged, returned, or placed in settings representations.
- **Admin surface.** Provider listing, inspection, and health are admin-only. Generation accepts any authenticated identity, including admins. Without auth, the identity is anonymous with a per-client-address rate-limit key.
- **Rate limiting.** Each key (or client address) gets a fixed window. The decision, counter update, and rejection are atomic within one event loop. Rejections return `429` with `Retry-After`, `X-RateLimit-Limit`, and `X-RateLimit-Remaining: 0`.
- **Reserve before spending.** Each provider attempt reserves the estimated maximum cost — prompt estimate plus `max_tokens`, or `BUDGET_ASSUMED_COMPLETION_TOKENS` when absent — before the circuit check and provider call. In-flight reservations count toward daily and monthly totals, so concurrent requests cannot overspend.
- **Settle or release.** A successful result settles the reservation using provider-reported usage. A failed attempt releases it. A result with a mismatched provider identity is settled (the call consumed tokens) and counted as a circuit failure.
- **Per-request first.** A request whose estimate exceeds `BUDGET_PER_REQUEST_USD` is rejected before any counter changes. Daily and monthly rejection messages identify the exhausted scope but never expose internal counters.
- **Rollover.** Daily counters reset at the first request of a new UTC day; monthly counters reset on the first request of a new month.
- **Cost reporting.** Money is `Decimal`, quantized to six decimal places. `cost_usd` is calculated from normalized usage and response-reported as a float. Provider pricing is configured as USD per million input/output tokens.
- **Unknown pricing is free.** A registered provider without a pricing entry falls back to zero rates and emits `budget.pricing.missing` at startup.
- **Disableable, not removable.** `BUDGET_ENFORCEMENT_ENABLED=false` stops rejection and reservation tracking while still settling actual spend for observability.
- **Safe summaries.** `request.summary` carries request ID, auth role, requested/final provider, model, token counts, cost, retry count, fallback metadata, and status. Prompt text, headers, keys, and vendor error text are absent.

### Security and budget errors

| Error code | HTTP status | Retryable | Meaning |
|---|---|---|---|
| `authentication_required` | 401 | no | Missing, malformed, or invalid bearer key (`WWW-Authenticate: Bearer`) |
| `permission_denied` | 403 | no | Authenticated user lacks the admin role |
| `rate_limit_exceeded` | 429 | yes | Identity or client address exceeded its fixed window |
| `budget_exceeded` | 402 | no | Estimated cost or accumulated spend exceeds a budget limit |

### Provider errors

| Error code | HTTP status | Retryable | Meaning |
|---|---|---|---|
| `provider_invalid_request` | 400 | no | Unsupported model or invalid provider-owned request |
| `provider_not_found` | 404 | no | Provider name is not registered |
| `provider_rate_limit` | 429 | yes | Upstream rate limit |
| `provider_authentication_failed` | 502 | no | Upstream credential/configuration failure |
| `provider_invalid_response` | 502 | yes | Vendor response could not be normalized |
| `provider_server_error` | 502 | yes | Upstream 5xx or equivalent |
| `provider_unavailable` | 503 | yes | Provider cannot currently serve requests |
| `provider_circuit_open` | 503 | no | Circuit breaker rejected the call without contacting the provider |
| `provider_timeout` | 504 | yes | Upstream operation exceeded its deadline |

Stage D retries only retryable errors, within the configured ceiling. Non-retryable errors switch to the next provider in the chain; an open circuit is skipped immediately. If the entire chain fails, the last normalized error is returned. Stage E budget rejection is not a provider error: it aborts the request with `402` and does not fall back, because a cheaper later provider is never assumed.

### Fault-report summarization (Stage F)

```text
app/api/routes/faults.py
        |
        v
app/faults/service.py        <-- FaultReportService
        |-- app/faults/prompts.py    strict JSON prompt
        |-- app/faults/parsing.py    fence/prose-tolerant decode + Pydantic validation
        |-- app/faults/extraction.py deterministic fallback extractor
        +-- app/faults/models.py     FaultSummary contract + field helpers
        |
        v
app/reliability/router.py    <-- ProviderRouter (timeouts, retries, circuits,
        |                       secondary/fallback, budget hooks)
        v
AIProvider adapters (fake, openai)
```

The output contract contains the six required data fields plus the temperature-unit companion:

| Field | Type | Rule |
|---|---|---|
| `machine` | string or `null` | Explicit machine/equipment/asset identifier only |
| `fault_description` | string or `null` | Explicit fault or symptom description |
| `temperature` | number or `null` | Numeric value only; no conversion |
| `temperature_unit` | `C`, `F`, or `null` | Required when temperature is present; otherwise `null` |
| `downtime` | string or `null` | Explicit duration text, normalized to singular/plural units |
| `action_taken` | string or `null` | Explicit maintenance or corrective action |
| `severity` | `low`, `medium`, `high`, `critical`, or `null` | Labeled value or deterministic signal classification |

Rules enforced by the Stage F boundary:

- **Validated AI output.** Provider content must decode to one JSON object accepted by `FaultSummary` (`extra="forbid"`). Markdown fences and surrounding prose are tolerated; unknown keys, invalid severities, non-finite temperatures, and a unit without a temperature are rejected.
- **Unknown stays unknown.** Neither path fills plausible defaults. Unknown or placeholder values (`N/A`, `unknown`, `none`, `pending`, and similar) become `null`, and the response lists them in `missing_fields`.
- **Deterministic fallback.** If the provider chain is exhausted, or the AI response is invalid JSON, schema-invalid, or empty when the report contains usable data, the service runs rule-based extraction over the same report. The response remains `200` with `extraction: "deterministic"` and an `extraction_reason`.
- **Client/security errors are not masked.** Unknown providers (`404`), unsupported models (`400`), authentication failures, rate limits, and budget rejections still return their normalized errors instead of a fabricated summary.
- **Safe observability.** `fault_report.summary` records request ID, auth role, selected/final provider, model, extraction mode/reason, missing-field count, tokens, cost, retry/fallback metadata, duration, and status. Report text, AI output, keys, and headers are never logged.
- **Normalized route metadata.** Provider failures on the fault path preserve `providers_tried`, `retry_count`, and the route error code for reporting even though the request succeeds with a deterministic summary.

### Database persistence and request history (Stage G)

```text
app/api/routes/generation.py  app/api/routes/faults.py
                  |                      |
                  +------ RequestLogEntry ------+
                                 |
                                 v
                      app/database/service.py      <-- record with bounded timeout
                                 |
                                 v
                    app/database/repository.py     <-- add / list / get / ping
                                 |
                                 v
                    app/database/engine.py         <-- async SQLAlchemy engine
                                 |
                 +---------------+----------------+
                 |                                |
        sqlite+aiosqlite                   postgresql+asyncpg
          (local/tests)                       (production)

app/api/errors.py
  |-- ProviderError, ApplicationError, RequestValidationError
  +-- _record_failure(...) -> same RequestLogService for generation/fault paths
```

The persisted contract records exactly the operational fields required by the project specification, plus normalized error and extraction metadata:

| Column | Meaning |
|---|---|
| `request_id` | Validated client request ID or generated UUID hex |
| `occurred_at` | UTC completion timestamp |
| `kind` | `generation` or `fault_report` |
| `selected_provider` | Provider selected for the attempt |
| `provider` | Provider that served the result, or the final normalized failing provider |
| `model` | Result model when a provider produced one |
| `duration_ms` | End-to-end request duration from middleware start |
| `prompt_tokens`, `completion_tokens`, `total_tokens` | Normalized usage; zero when no result exists |
| `cost_usd` | Settled cost derived from usage and provider pricing (`NUMERIC(14,6)`) |
| `retry_count`, `fallback_used`, `fallback_reason`, `providers_tried` | Reliability outcome |
| `status` | `success`, `degraded` (deterministic fault summary), or `error` |
| `error_code`, `http_status` | Normalized final error and HTTP status |
| `auth_role` | `anonymous`, `user`, or `admin` |
| `extraction`, `extraction_reason`, `missing_field_count` | Fault-report extraction outcome |

Rules enforced by the Stage G boundary:

- **Metadata only.** There is no prompt, completion, report text, request body, authorization header, or credential column. API keys and bearer tokens cannot be persisted by the request logger.
- **Successful and rejected requests are recorded.** Generation and fault outcomes, `401`, `402`, `404`, `422` validation failures, and `429` rate-limit rejections on those paths produce rows. Admin endpoint traffic does not enter AI request history.
- **Persistence never breaks the API.** Writes are awaited under `DATABASE_WRITE_TIMEOUT_SECONDS`, and any repository/driver failure is logged as `request_log.persist_failed` with only the error type. The AI response is still returned.
- **Admin-only history.** `GET /api/v1/requests` supports `kind`, `status`, `provider`, `since`, `until`, `limit`, and `offset`. `GET /api/v1/requests/{id}` returns one record. Both require the admin role.
- **Explicit unavailability.** When persistence is disabled, history returns `503 persistence_unavailable`; a missing record returns `404 request_log_not_found`; reversed time filters return `422 invalid_request_filter`.
- **Readiness includes the schema.** When enabled, `/health/ready` executes a bounded query against `request_logs`; a connection failure or missing table makes the service `not_ready`.
- **Async all the way.** A SQLAlchemy 2.x async engine and `async_sessionmaker` are used for both SQLite (`aiosqlite`) and PostgreSQL (`asyncpg`). Session objects are per operation and never shared across requests.
- **Migrations own production schema.** Local development may use `DATABASE_AUTO_CREATE=true`; production requires PostgreSQL, `DATABASE_AUTO_CREATE=false`, and Alembic. The initial migration creates the table, indexes, and revision marker.
- **Secret-safe configuration.** `DATABASE_URL` is a `SecretStr` and is never logged. Startup logs dialect, enablement, and auto-create mode only.

### Fault-injection test matrix (Stage H)

Stage H is a test-only hardening layer. It replaces only the provider boundary with a deterministic injector and runs the real application stack:

```text
FaultProvider (tests only)
        |
        v
ProviderRouter -> TimeoutManager -> RetryManager -> CircuitBreaker
        |                                   |
        +-------- secondary / fallback -----+
        |
        v
real HTTP routes -> auth -> rate limit -> budget -> fault parser/extractor
        |
        v
RequestLogService -> in-memory SQLite -> admin history assertions
```

| Fault class | Injected modes | Expected behavior |
|---|---|---|
| Retryable transport/provider | timeout, rate limit, server error, unavailable, invalid response, wrong provider identity | `/generate` exhausts the bounded attempts and returns the normalized error when no fallback exists; with fallback it returns `200` and exposes retry/fallback metadata. Fault reports return `200` with `extraction: "deterministic"` and the provider error as `extraction_reason`. |
| Terminal client/provider | invalid request | `400` on both endpoints; the chain stops immediately; fallback and deterministic extraction do not mask the client error. |
| Provider authentication | authentication failure | Non-retryable; generation uses the configured fallback, while fault reports degrade deterministically when no fallback exists. |
| Unknown provider | unregistered provider name | `404 provider_not_found`; no provider is called and no extraction is attempted. |
| Output protocol | malformed JSON, schema-invalid JSON, empty summary, valid JSON control | Fault reports distinguish `ai_invalid_json`, `ai_invalid_schema`, `ai_empty_summary`, and provider success without inventing values. |
| Reliability | slow provider, repeated failure beyond threshold | Actual timeout cancellation bounds latency; the circuit opens after the configured threshold, stops provider calls, and short-circuits to fallback. |
| Admission | missing authentication, rate limit | Rejected before the provider boundary; normalized `401`/`429` rows are persisted. |
| Persistence/privacy | faults with prompt, report, bearer, and secret markers | Operational metadata is persisted; prompts, report text, keys, and raw credentials are absent from responses, logs, and history. |

Rules enforced by the Stage H matrix:

- **No production fault switch.** Fault injection exists only in the test double. There is no environment variable, HTTP endpoint, or admin operation that enables it at runtime.
- **Real components under test.** Tests use the real `create_app` factory, authentication, rate limiter, budget hook, router, timeout/retry/circuit logic, routes, fault parser/extractor, and SQLite persistence. Only the provider adapter is replaced.
- **Every retryable fault crosses every recovery policy.** Each retryable mode is exercised with exhaustion, with configured fallback, and through the fault-report degradation path; a manifest test fails if a mode is omitted.
- **Determinism.** Backoff base, jitter, and sleeps between attempts are zero; the only intentional delay is the injected hanging provider, which must be cancelled by the timeout manager.
- **Outcome and privacy checks are part of the matrix.** A scenario passes only when the HTTP result, fallback/retry metadata, persisted row, and absence of content/secret markers all match.
- **No external calls.** The matrix uses no network, no real provider, and no shared database.

### Model version catalog and regression baselines (Stage I)

Stage I keeps release metadata out of provider adapters and pins the observable contracts that earlier stages depend on:

```text
config/model_versions.json
  |-- bounded UTF-8 JSON read (256 KiB maximum)
  |-- schema v1, strict fields, unique provider/model pairs
  v
ModelCatalog: (provider, model) -> version, status, release date, notes
  |-- every configured provider model must have an entry
  |-- retired configured model -> startup failure
  |-- deprecated configured model -> startup warning
  |-- default model must be active
  v
app.state.model_catalog
  |-- /health/ready -> models: "ok" when enabled
  |-- GET /api/v1/model-versions (admin) -> entries + configured flag
```

- **Opt-in deployment metadata.** `MODEL_VERSION_MANIFEST` enables the catalog; the shipped `.env` points at `config/model_versions.json`. A blank value disables version management and its endpoint.
- **Strict manifest contract.** Entries contain provider, model, version, status, optional release date, and optional notes. Unknown fields, duplicate provider/model pairs, invalid names/versions, malformed JSON, and oversized files fail closed at startup.
- **Lifecycle policy.** `active` is normal. `deprecated` is allowed and logged as `model.version.deprecated` because existing deployments may still use it. `retired` cannot remain in provider configuration. The default model must be active.
- **Configured coverage.** Every model registered by every configured provider must have a manifest entry. Entries for unregistered providers are retained for lifecycle visibility and returned with `configured: false`.
- **Secret-safe operations.** The manifest contains no credentials. Startup logs only enablement, entry count, and status counts; the manifest path and contents are not logged. The admin endpoint exposes release metadata only.
- **Explicit unavailable state.** When the catalog is disabled, `/api/v1/model-versions` returns `503 model_catalog_unavailable`. Existing generation, provider, fault-report, and request-history contracts are unchanged.

The regression harness compares normalized responses from the real application against committed JSON baselines:

```text
real create_app + auth + routes + reliability + fault services
        |
        v
normalized HTTP body (volatile latency removed)
        |
        v
tests/regression/baselines/*.json
```

Seven baselines pin generation, deterministic and provider fault-report extraction, the normalized error envelope, the provider catalog, the model-version inventory, and readiness checks. The suite uses deterministic local providers only. `scripts/regression.ps1` runs the contracts and model-version tests; `-Update` is the only supported way to rewrite baselines, and a mismatch message directs reviewers to inspect the contract diff first.

### CI quality gate (Stage J)

The GitHub Actions workflow is the authoritative pull-request gate. It is deliberately read-only and runs no deployment step:

```text
push / pull_request / manual dispatch
  |
  v
ubuntu-latest + Python 3.14 + pip cache
  |
  +-- pip install -e ".[dev]"
  +-- python -m compileall -q app tests alembic
  +-- python -m ruff check .
  +-- python -m pytest -q --strict-config --strict-markers
  +-- python -m pytest -q -m fault_matrix tests/test_fault_matrix.py
  +-- python -m pytest -q -m regression tests/test_model_versions.py tests/test_regression.py
  +-- git diff --exit-code -- tests/regression/baselines
```

- **Least privilege.** The workflow declares `contents: read`, uses no repository secrets, and is limited to a 15-minute job.
- **Isolated test configuration.** CI exports only `PYTHONHASHSEED`, `PYTHONDONTWRITEBYTECODE`, and `UPDATE_REGRESSION_BASELINES=0`. It does not export application settings globally because the tests intentionally construct `Settings(_env_file=None, ...)`; a checkout contains no `.env`.
- **Named gates.** Byte-compilation, linting, the full suite, the fault matrix, and the regression suite are separate steps so a failure identifies the broken boundary immediately.
- **Baseline integrity.** The final diff check fails if a test run rewrote any file under `tests/regression/baselines`; intentional contract updates must be reviewed and committed explicitly.
- **Local parity.** `scripts/quality.ps1` runs the same compile, lint, full-suite, fault-matrix, and regression commands on Windows. The CI-only baseline diff has no local equivalent when the folder is not a Git working tree.

### Cost and latency monitoring (Stage K)

Stage K adds two views of the same completed-request metadata. It does not add a table or migration:

```text
POST /generate, POST /fault-reports/summarize
  |
  v
RequestLogService.record(entry)
  |-- observer -> MetricsCollector -> private registry
  |                 `-> GET /api/v1/monitoring/metrics (admin, Prometheus text)
  `-- repository -> request_logs
                    `-> GET /api/v1/monitoring/summary (admin, JSON)
                         filters: window, kind, provider
                         SQL: counts, token/cost sums, min/max/average latency
                         bounded latest duration sample: p50, p95
```

- **Durable report versus process metrics.** The summary is recomputed from persisted rows, so it survives restarts and reflects the deployment database. Prometheus counters live in the current process and reset at restart; they still update when `DATABASE_ENABLED=false`, because the observer runs before persistence.
- **Outcome definitions.** `accepted = success + degraded` and represents a validated HTTP `200` result, including deterministic fault extraction. `success_rate` counts only `success`; `degraded_rate` counts deterministic fallback; `error_rate` counts failed requests. `accepted_rate` is the required successful-result percentage.
- **Failure and fallback rates.** `provider_failure_rate = provider-attributed error requests / requests whose final row names a provider`. `fallback_rate = fallback_used requests / all requests`. Both denominators are explicit in the response fields.
- **Cost evidence.** `cost_usd` is the sum of stored estimated costs. `cost_per_request_usd = cost / all requests`; `cost_per_accepted_result_usd = cost / accepted results`. A zero-cost fake deployment legitimately reports zero.
- **Bounded reads.** Counts, sums, min/max, and average latency are full-window SQL aggregates. p50/p95 use at most `MONITORING_LATENCY_SAMPLE_LIMIT` latest durations, and `sample_truncated` states whether older values were excluded. The query timeout is `MONITORING_QUERY_TIMEOUT_SECONDS`.
- **Fixed UTC windows.** Supported windows are `15m`, `1h`, `6h`, `24h`, `7d`, and `30d`; optional `kind` and `provider` filters narrow the report. `window_start`, `window_end`, and `generated_at` are returned with every response.
- **Administrator boundary.** Both monitoring endpoints use the existing admin dependency, so production auth, role checks, and rate limiting apply. When auth is disabled locally, they are available to anonymous callers for development.
- **Bounded metric labels.** Prometheus labels are limited to kind, provider, status, internal error code, fallback reason, and token type. Request IDs, prompts, completions, report text, headers, and keys are never labels. Unknown client-supplied provider names collapse to `unconfigured`.
- **Failure isolation.** The observer runs inside `RequestLogService` and its exceptions are logged as `request_log.metrics_failed` without changing the API response. Persistence failures remain best-effort as in Stage G.
- **Safe unavailability.** With persistence disabled, `/monitoring/summary` returns `503 monitoring_unavailable`; `/monitoring/metrics` remains available. A database error or query timeout maps to the same safe `503` without exposing SQL or credentials.

### Streamlit operations dashboard (Stage L)

Stage L is a separate process. It has no database driver, provider SDK, or application settings; it only calls the admin API:

```text
Browser
  |
  v
Streamlit process (dashboard/app.py, 127.0.0.1:8501)
  |-- dashboard/config.py      DASHBOARD_* env, base-URL/prefix/timeout validation
  |-- dashboard/client.py      httpx.Client, no redirects, no ambient proxy, bounded body
  |-- dashboard/models.py      dashboard-owned Pydantic response models (extra="ignore")
  `-- dashboard/metrics.py     bounded Prometheus text parser
        |
        v  HTTP + Bearer admin key
FastAPI admin API (127.0.0.1:8000)
  |-- /health/live, /health/ready          (unversioned)
  `-- /api/v1/...                          (summary, metrics, providers, requests, models)
```

- **Separate deployment boundary.** Dashboard environment variables are distinct from API settings because the two are different processes. Nothing in `dashboard/` imports `app.*`, so provider, persistence, and monitoring internals cannot leak into presentation code.
- **Read-only by construction.** The client exposes only `GET` operations. There are no generation, fault, provider-switching, budget, or admin-write calls.
- **Five views.** *Overview* shows windowed totals, accepted rate, p50/p95, cost ratios, provider failure/fallback rates, charts, and per-kind/per-provider tables. *Providers* lists the inventory and runs a health check only when the operator clicks. *Requests* shows filtered, paginated metadata with an explicit privacy caption. *Model versions* shows the tracked inventory and configured state. *Prometheus metrics* summarizes process counters and displays the bounded raw exposition.
- **Reachability gate.** On every rerun the dashboard calls `/health/live` and `/health/ready` before rendering a view. An unreachable API stops with a start-the-API hint instead of showing misleading empty data; a reachable but not-ready API renders a warning banner.
- **Strict outbound configuration.** `DASHBOARD_API_BASE_URL` must be an absolute HTTP(S) origin with no credentials, query, fragment, or path. Remote plain HTTP is allowed but warns. The client sets `trust_env=False` (no ambient proxy credentials), `follow_redirects=False` (no key forwarding to another origin), and a bounded timeout.
- **Typed, sanitized failures.** HTTP, timeout, transport, invalid-JSON, and invalid-shape errors become a small `DashboardApiError` vocabulary. Messages are stripped of control characters and capped; response bodies, URLs, keys, and stack traces are not rendered.
- **Bounded parsing.** Prometheus text is capped at 2,000,000 characters, 4,096 characters per line, 32 labels, and 256 characters per label value. Malformed lines are skipped; non-finite values are rejected. Raw text is rendered only through `st.code`, never as Markdown, and API strings only through `st.code`/`st.dataframe`, so upstream content cannot inject HTML.
- **Secret handling.** The admin key is a `SecretStr`. Environment configuration is preferred; when absent, the sidebar accepts a masked key that lives only in process memory for the running session. It is sent only to the configured API origin, never placed in URLs or query strings, and never logged.
- **Session-scoped state.** Each rerun fetches fresh data; Refresh triggers a rerun on demand. The view selector, filters, and any sidebar-entered key are the only session state, and no operational data is written to disk.

### Container deployment (Stage M)

Stage M packages the existing processes without changing their boundaries:

```text
docker compose --env-file .env.docker up -d --build
  |
  |-- db (postgres:17-alpine)
  |     `-- backend network only (internal: true), db_data volume
  |
  |-- api (Dockerfile target "api")
  |     |-- entrypoint: alembic upgrade head, bounded retries, then uvicorn
  |     |-- frontend + backend networks
  |     `-- published only as 127.0.0.1:8000
  |
  `-- dashboard (Dockerfile target "dashboard")
        |-- DASHBOARD_API_BASE_URL=http://api:8000
        |-- frontend network only
        `-- published only as 127.0.0.1:8501
```

- **One Dockerfile, three stages.** A `builder` stage creates `/opt/venv` with the project and its dependencies; a shared `runtime` stage adds an unprivileged `adapter` user (UID/GID 10001), copies only runtime assets, and becomes the base for the `api` and `dashboard` targets. The compiler toolchain never reaches a runtime image.
- **Runtime hardening.** Both service images run as `10001:10001`, use read-only root filesystems with a bounded `/tmp` tmpfs, drop all Linux capabilities, enable `no-new-privileges`, and use `init: true` for signal reaping. Secrets are injected as environment variables, never baked into layers.
- **Database isolation.** PostgreSQL is reachable only on the internal `backend` network. The API joins both networks; the dashboard joins only `frontend`. No database port is published, and the named volume `db_data` persists data across `down` unless `-v` is used.
- **Migrations before serving.** The API entrypoint runs `alembic upgrade head` with up to ten attempts and two-second delays, then `exec`s the server. Compose starts the API only after the database health check passes, and starts the dashboard only after `/health/ready` passes. Production mode forces PostgreSQL, disables auto-create and SQL echo, and requires authentication.
- **Secret requirements fail closed.** Compose uses `${POSTGRES_PASSWORD:?...}`, `${SECURITY_API_KEYS:?...}`, and `${SECURITY_ADMIN_API_KEYS:?...}`, so an unset required secret stops Compose before any container starts. The dashboard reuses the admin key through `DASHBOARD_ADMIN_API_KEY`.
- **Loopback publication is deliberate.** Production mode forces authentication, and the dashboard calls the API server-side. Publishing both ports on `127.0.0.1` avoids exposing an unauthenticated edge while still allowing a local browser demonstration; a real deployment places a TLS reverse proxy in front.
- **Demonstration orchestration.** `scripts\demo.ps1` refuses placeholder secrets, can generate cryptographically random URL-safe values into an ASCII `.env.docker`, builds and starts the stack, runs the verifier, prints diagnostics on failure, and tears the stack down in `finally` unless `-KeepRunning` is supplied. It never prints the generated secrets.
- **Black-box verification.** `scripts\e2e_demo.py` uses `httpx` with ambient proxies and redirects disabled. It polls readiness and dashboard health, exercises two generations, a fault report, an unknown provider, an unauthenticated history call, monitoring, Prometheus metrics, request history, model inventory, and the dashboard, and checks that a per-run marker never appears in metrics or history. It prints only aggregate results and exits nonzero on the first failure.

---

## 3. Project structure

```text
C:\AI ADAPTER PRJCT\
├─ .github\
│  └─ workflows\
│     └─ ci.yml                    # Stage J quality gate
├─ app\
│  ├─ __init__.py
│  ├─ main.py                       # create_app(), lifespan, registry/router/catalog/metrics wiring
│  ├─ api\
│  │  ├─ __init__.py
│  │  ├─ deps.py                    # settings, registry, catalog, monitoring, auth, rate, budget, persistence deps
│  │  ├─ errors.py                  # provider/application error mapping + failure persistence
│  │  ├─ router.py                  # versioned router composition
│  │  ├─ utils.py                   # uptime and request-duration helpers
│  │  ├─ middleware\
│  │  │  ├─ __init__.py
│  │  │  └─ request_context.py      # request ID + access log
│  │  ├─ routes\
│  │  │  ├─ __init__.py
│  │  │  ├─ health.py               # live / ready (database + model catalog checks)
│  │  │  ├─ system.py               # /system/info
│  │  │  ├─ providers.py            # admin list / inspect / health + circuit
│  │  │  ├─ model_versions.py       # admin model version inventory
│  │  │  ├─ generation.py           # /generate + cost + request log
│  │  │  ├─ faults.py               # /fault-reports/summarize + request log
│  │  │  ├─ requests.py             # admin request history + detail
│  │  │  └─ monitoring.py           # admin cost/latency summary + Prometheus metrics
│  │  └─ schemas\
│  │     ├─ __init__.py
│  │     ├─ responses.py            # health/system models
│  │     ├─ errors.py               # public error envelope
│  │     ├─ providers.py            # provider summary, health report, circuit status
│  │     ├─ model_versions.py       # model version inventory models
│  │     ├─ generation.py           # public generate request/response
│  │     ├─ faults.py               # public fault-report request/response
│  │     ├─ requests.py             # request-history item/page models
│  │     └─ monitoring.py           # performance summary, rates, cost ratios, latency models
│  ├─ core\
│  │  ├─ __init__.py
│  │  ├─ config.py                  # Settings / get_settings()
│  │  ├─ errors.py                  # ApplicationError base with status/headers
│  │  ├─ logging.py                 # JSON/console logging
│  │  └─ sanitize.py                # credential redaction
│  ├─ database\
│  │  ├─ __init__.py                # public persistence exports
│  │  ├─ engine.py                  # async engine, session factory, SQLite/PostgreSQL config
│  │  ├─ models.py                  # SQLAlchemy metadata + RequestLogRow
│  │  ├─ records.py                 # framework-neutral request-log records
│  │  ├─ repository.py              # insert / filter / paginate / get / schema ping
│  │  ├─ service.py                 # safe recording facade + bounded timeout
│  │  ├─ paths.py                   # business-path -> request kind mapping
│  │  ├─ errors.py                  # 404/422/503 persistence errors
│  │  └─ factory.py                 # build database + request-log service
│  ├─ security\
│  │  ├─ __init__.py                # public security exports
│  │  ├─ models.py                  # AuthIdentity
│  │  ├─ errors.py                  # 401/403/429 errors with headers
│  │  ├─ manager.py                 # digest-based key authentication + roles
│  │  ├─ rate_limit.py              # fixed-window RateLimiter
│  │  └─ factory.py                 # build from settings
│  ├─ budget\
│  │  ├─ __init__.py                # public budget exports
│  │  ├─ pricing.py                 # PricingRates, Decimal cost
│  │  ├─ estimation.py              # deterministic prompt-token estimate
│  │  ├─ errors.py                  # BudgetExceededError with scopes
│  │  ├─ manager.py                 # reserve / settle / release / rollover
│  │  └─ factory.py                 # build from settings + registry
│  ├─ reliability\
│  │  ├─ __init__.py                # public reliability exports
│  │  ├─ timeout.py                 # TimeoutManager
│  │  ├─ retry.py                   # RetryPolicy, RetryManager, RetryFailure
│  │  ├─ circuit_breaker.py         # CircuitBreaker, config, snapshot
│  │  ├─ router.py                  # ProviderRouter, RouteResult, budget hook
│  │  └─ factory.py                 # build router from settings
│  ├─ faults\
│  │  ├─ __init__.py                # public fault-report exports
│  │  ├─ models.py                  # FaultSummary contract + field helpers
│  │  ├─ prompts.py                 # strict JSON extraction prompt
│  │  ├─ parsing.py                 # decode + validate AI output
│  │  ├─ extraction.py              # deterministic rule-based extractor
│  │  ├─ service.py                 # FaultReportService + fallback policy
│  │  └─ factory.py                 # build from settings + router + budget
│  ├─ model_catalog\
│  │  ├─ __init__.py                # public catalog exports
│  │  ├─ errors.py                  # configuration and unavailable errors
│  │  ├─ versions.py                # ModelVersion + immutable ModelCatalog
│  │  ├─ manifest.py                # bounded JSON manifest parser
│  │  └─ factory.py                 # build + validate against the registry
│  ├─ monitoring\
│  │  ├─ __init__.py                # monitoring package
│  │  ├─ models.py                  # window, latency, performance, report records
│  │  ├─ errors.py                  # safe 503 monitoring error
│  │  ├─ repository.py              # bounded SQL aggregates + latest latency sample
│  │  ├─ service.py                 # window resolution, timeout, report assembly
│  │  ├─ metrics.py                 # process-local Prometheus collector
│  │  └─ factory.py                 # build report service + metrics collector
│  └─ providers\
│     ├─ __init__.py
│     ├─ base.py                    # AIProvider ABC
│     ├─ schemas.py                 # normalized domain schemas
│     ├─ errors.py                  # provider error taxonomy
│     ├─ registry.py                # provider catalog
│     ├─ fake.py                    # deterministic local provider
│     ├─ openai.py                  # HTTPX OpenAI chat-completions adapter
│     └─ factory.py                 # build registry from settings
├─ dashboard\
│  ├─ __init__.py                   # dashboard package + version
│  ├─ config.py                     # DASHBOARD_* settings, URL/prefix/key validation
│  ├─ models.py                     # dashboard-owned response models
│  ├─ formatting.py                 # percent/USD/latency/count/UTC display helpers
│  ├─ metrics.py                    # bounded Prometheus text parser + process summary
│  ├─ client.py                     # read-only HTTP client, typed sanitized errors
│  └─ app.py                        # Streamlit entry point and five views
├─ tests\
│  ├─ conftest.py
│  ├─ test_app_factory.py
│  ├─ test_budget.py                # Stage E pricing, budgets, router hooks, API
│  ├─ test_security.py              # Stage E auth, roles, rate limiting
│  ├─ test_fault_reports.py         # Stage F extraction, parsing, fallback, API
│  ├─ test_persistence.py           # Stage G engine, repository, history, migrations
│  ├─ test_fault_matrix.py          # Stage H deterministic fault-injection matrix
│  ├─ test_model_versions.py        # Stage I manifest, catalog, startup, admin API
│  ├─ test_regression.py            # Stage I golden HTTP contract baselines
│  ├─ test_ci_quality_gate.py       # Stage J workflow, runner, and Ruff contract checks
│  ├─ test_monitoring.py            # Stage K aggregation, percentiles, auth, metrics
│  ├─ test_dashboard.py             # Stage L config, client, parsing, formatting, AppTest UI
│  ├─ test_deployment.py            # Stage M Dockerfile, Compose, demo, and verifier contracts
│  ├─ regression\
│  │  └─ baselines\
│  │     ├─ fault_report_deterministic.json
│  │     ├─ fault_report_provider.json
│  │     ├─ generation.json
│  │     ├─ model_version_catalog.json
│  │     ├─ provider_catalog.json
│  │     ├─ readiness.json
│  │     └─ unsupported_model_error.json
│  ├─ test_config.py
│  ├─ test_health.py
│  ├─ test_logging.py
│  ├─ test_sanitize.py
│  ├─ test_provider_schemas.py
│  ├─ test_fake_provider.py
│  ├─ test_registry.py
│  ├─ test_reliability.py           # Stage D timeout/retry/circuit/router/API
│  ├─ test_openai_provider.py
│  └─ test_provider_api.py
├─ scripts\
│  ├─ setup.ps1
│  ├─ run-dev.ps1
│  ├─ test.ps1
│  ├─ fault-matrix.ps1              # Stage H matrix-only runner
│  ├─ regression.ps1                # Stage I regression suite + explicit baseline update
│  ├─ quality.ps1                   # Stage J local mirror of the CI quality gate
│  ├─ dashboard.ps1                 # Stage L Streamlit launcher with loopback guard
│  ├─ docker-entrypoint.sh          # Stage M migration retry loop, then exec the service
│  ├─ demo.ps1                      # Stage M secret generation, Compose lifecycle, verifier
│  ├─ e2e_demo.py                   # Stage M black-box HTTP deployment verifier
│  ├─ verify-openai.ps1             # live verification wrapper
│  └─ verify_openai.py              # one safe live adapter request
├─ docs\
│  ├─ stage-l-overview.png          # Stage L Overview view (live data)
│  ├─ stage-l-providers.png
│  ├─ stage-l-requests.png
│  ├─ stage-l-models.png
│  └─ stage-l-metrics.png
├─ .streamlit\
│  └─ config.toml                   # loopback bind, XSRF/CORS, minimal toolbar
├─ alembic\
│  ├─ env.py                        # async migration environment
│  ├─ script.py.mako
│  └─ versions\
│     └─ 20261114_0001_create_request_logs.py
├─ config\
│  └─ model_versions.json           # versioned model-release manifest
├─ alembic.ini
├─ compose.yaml                     # Stage M PostgreSQL + API + dashboard topology
├─ Dockerfile                       # Stage M builder/runtime/api/dashboard stages
├─ .dockerignore                    # keeps local data, secrets, tests, and caches out of images
├─ .env.example
├─ .env.docker.example              # Compose-only secret and database placeholders
├─ .gitignore
├─ pyproject.toml
└─ README.md
```

Local-only files created by setup: `.venv\` and `.env\`. Both are git-ignored.

---

## 4. Requirements

- Windows 10/11
- PowerShell 5.1 or PowerShell 7+
- Python 3.14 installed through the `py` launcher
- Network access for the initial dependency installation
- GitHub Actions with `ubuntu-latest` for the hosted Stage J gate
- Docker Desktop with Compose v2 for the Stage M container demonstration (optional for local Python development)

Runtime dependencies:

| Package | Purpose |
|---|---|
| `fastapi` | HTTP application and response validation |
| `uvicorn` | ASGI server |
| `pydantic` | Domain and API schemas |
| `pydantic-settings` | Environment and `.env` configuration |
| `httpx` | Async HTTP client used by the OpenAI adapter and mock-transport tests |
| `SQLAlchemy[asyncio]` | Async ORM/table metadata and engine management |
| `alembic` | Versioned database schema migrations |
| `aiosqlite` | Async SQLite driver for local development and tests |
| `asyncpg` | Async PostgreSQL driver for production |
| `prometheus-client` | Standard Prometheus text exposition and bounded metric collectors |
| `streamlit` | Separate Stage L operations dashboard process |

Development dependencies:

| Package | Purpose |
|---|---|
| `pytest` | Test runner |
| `pytest-asyncio` | Async provider and registry tests |
| `httpx2` | Test-client transport required by Starlette 1.10+ |
| `ruff` | Fast Python linter used by the Stage J CI gate |

`httpx` remains the application’s HTTP client. `httpx2` is test-only because Starlette’s current `TestClient` imports it.

Stage C added no new runtime dependencies; HTTPX was already declared during Stage A. Stage D also adds none: retries, backoff, jitter, timeouts, and circuit breaking are implemented in-house with the standard library (the requirement's "Tenacity or equivalent controlled retry implementation"), keeping the reliability layer explicit and dependency-free. Stage E likewise adds none: authentication uses `hashlib`/`secrets`, rate limiting and budget accounting use `asyncio` plus `Decimal`. Stage F also adds none: structured validation uses Pydantic (already required), JSON decoding uses the standard library, and deterministic extraction uses `re`. Stage G adds SQLAlchemy 2.x asyncio support (which brings `greenlet`), Alembic, `aiosqlite`, and `asyncpg`. Stage H adds no dependencies: the fault-injection provider, matrix, and runner use the existing test stack. Stage I adds no dependencies: manifest parsing uses the standard library, validation uses Pydantic, and regression baselines use the existing pytest stack. Stage J adds only the development dependency `ruff`; the workflow itself uses GitHub-provided actions and standard Python tooling. Stage K adds the runtime dependency `prometheus-client` for the standard text exposition and collector primitives; durable reporting uses SQLAlchemy and Pydantic already present from earlier stages. Stage L adds the runtime dependency `streamlit` (with its transitive web stack) for the separate dashboard process; the dashboard's HTTP access uses the existing `httpx` client and its validation uses the existing Pydantic stack. Stage M adds no Python dependencies: it packages the existing application and dashboard, uses the standard-library `urllib` for container health checks, and uses Docker/Compose as the deployment toolchain. The end-to-end verifier uses the existing `httpx` development/runtime stack.

The Stage M demonstration requires Docker Desktop with Compose v2 and a running Docker daemon. Docker execution was not performed on the implementation host because no Docker CLI, daemon, Podman, or WSL is installed there; see the Stage M walkthrough for the native verification that was executed instead.

---

## 5. PowerShell setup

> Step-by-step runbook covering setup, API, dashboard, real providers, tests, and containers: [execution.md](execution.md).

Open PowerShell in the project directory:

```powershell
cd "C:\AI ADAPTER PRJCT"
```

Allow local scripts for the current PowerShell process only:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Create the environment, install dependencies, and create `.env`:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
Copy-Item .env.example .env
```

Or run the setup script, which performs the same steps idempotently:

```powershell
.\scripts\setup.ps1
```

Verify:

```powershell
python --version
```

Expected:

```text
Python 3.14.10
```

---

## 6. Environment variables

`.env` is loaded automatically. Real environment variables take precedence over `.env`.

| Variable | Default | Validation / meaning |
|---|---|---|
| `APP_NAME` | `AI Adapter` | Display name and OpenAPI title |
| `APP_VERSION` | `0.1.0` | Reported service version |
| `ENVIRONMENT` | `development` | `development`, `test`, `staging`, `production` |
| `DEBUG` | `false` | FastAPI debug mode |
| `API_HOST` | `127.0.0.1` | Host used by scripts/documentation |
| `API_PORT` | `8000` | Integer from 1 to 65535 |
| `API_PREFIX` | `/api/v1` | Must start with `/` and not end with `/` |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `LOG_FORMAT` | `json` | `json` or `console` |
| `REQUEST_ID_HEADER` | `X-Request-ID` | Letters, digits, and hyphens only |
| `CORS_ORIGINS` | `http://localhost:8501,http://127.0.0.1:8501` | Comma-separated allowed origins |
| `DEFAULT_PROVIDER` | `fake` | Must be registered at startup; lowercase provider key |
| `FAKE_PROVIDER_MODELS` | `fake-small,fake-large` | Comma-separated unique model names |
| `FAKE_PROVIDER_DEFAULT_MODEL` | `fake-small` | Must appear in `FAKE_PROVIDER_MODELS` |
| `OPENAI_API_KEY` | empty (disabled) | Secret; read from environment/`.env` only, never logged or returned |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Absolute HTTP(S) URL without query or fragment |
| `OPENAI_MODELS` | `gpt-4o-mini,gpt-4o` | Comma-separated unique model names; request models must be listed |
| `OPENAI_DEFAULT_MODEL` | `gpt-4o-mini` | Must appear in `OPENAI_MODELS` |
| `OPENAI_TIMEOUT_SECONDS` | `30` | Per-request HTTP deadline, greater than 0 and at most 300 |
| `MODEL_VERSION_MANIFEST` | empty (`.env` uses `config/model_versions.json`) | JSON path, at most 500 characters; blank disables the catalog and its admin endpoint |
| `RELIABILITY_MAX_ATTEMPTS` | `3` | Attempts per provider, integer from 1 to 10 |
| `RELIABILITY_BACKOFF_BASE_SECONDS` | `0.25` | First retry delay; must not exceed the backoff maximum |
| `RELIABILITY_BACKOFF_MAX_SECONDS` | `2.0` | Cap for exponential backoff, from 0 to 60 |
| `RELIABILITY_JITTER_SECONDS` | `0.1` | Maximum random addition to each delay, from 0 to 10 |
| `RELIABILITY_TIMEOUT_SECONDS` | `35` | Per-attempt deadline, greater than 0 and at most 300 |
| `RELIABILITY_CIRCUIT_FAILURE_THRESHOLD` | `3` | Consecutive qualifying failures before opening a circuit |
| `RELIABILITY_CIRCUIT_RECOVERY_SECONDS` | `30` | Open duration before a single half-open probe |
| `RELIABILITY_SECONDARY_PROVIDER` | empty (disabled) | Optional registered provider tried after the primary |
| `RELIABILITY_FALLBACK_PROVIDER` | `fake` | Deterministic local fallback; blank disables fallback |
| `SECURITY_REQUIRE_AUTH` | `false` | When true, every API call needs a Bearer key; forced on in production |
| `SECURITY_API_KEYS` | empty | Comma-separated user keys; each 16–512 characters, no whitespace, no duplicates |
| `SECURITY_ADMIN_API_KEYS` | empty | Additional admin keys; must not overlap user keys |
| `SECURITY_RATE_LIMIT_REQUESTS` | `60` | Requests per identity/address per window; `0` disables limiting |
| `SECURITY_RATE_LIMIT_WINDOW_SECONDS` | `60` | Fixed-window length, greater than 0 and at most 3600 |
| `BUDGET_ENFORCEMENT_ENABLED` | `true` | When false, reservations are skipped but actual spend is still tracked |
| `BUDGET_PER_REQUEST_USD` | `0.25` | Maximum estimated cost of one attempt |
| `BUDGET_DAILY_USD` | `50` | Maximum settled plus reserved spend per UTC day |
| `BUDGET_MONTHLY_USD` | `500` | Maximum settled plus reserved spend per calendar month |
| `BUDGET_ASSUMED_COMPLETION_TOKENS` | `512` | Completion tokens reserved when `max_tokens` is absent |
| `BUDGET_PROVIDER_PRICING` | fake free; openai 0.15/0.60 | JSON `{provider: {input_per_million_usd, output_per_million_usd}}` |
| `FAULT_REPORT_MAX_TOKENS` | `512` | Completion-token ceiling for one fault summary, integer from 1 to 8192 |
| `DATABASE_ENABLED` | `false` (`.env` uses `true`) | Enables request persistence and admin history |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/ai_adapter.db` | Secret; `sqlite+aiosqlite` locally, `postgresql+asyncpg` in production |
| `DATABASE_ECHO` | `false` | SQLAlchemy SQL echo; must be false in production |
| `DATABASE_AUTO_CREATE` | `true` | Create tables at startup; must be false in production (use Alembic) |
| `DATABASE_POOL_SIZE` | `5` | PostgreSQL pool size, 1–50 |
| `DATABASE_MAX_OVERFLOW` | `10` | PostgreSQL pool overflow, 0–100 |
| `DATABASE_WRITE_TIMEOUT_SECONDS` | `2` | Maximum request-log write/query/ping wait, 0–30 |
| `MONITORING_QUERY_TIMEOUT_SECONDS` | `5` | Maximum wait for one monitoring aggregate, greater than 0 and at most 60 |
| `MONITORING_LATENCY_SAMPLE_LIMIT` | `10000` | Latest rows sampled for p50/p95, integer from 10 to 100000 |
| `DASHBOARD_API_BASE_URL` | `http://127.0.0.1:8000` | Dashboard process; absolute HTTP(S) origin with no credentials, query, fragment, or path |
| `DASHBOARD_API_PREFIX` | `/api/v1` | Dashboard process; versioned prefix, must start with `/` and not end with `/` |
| `DASHBOARD_ADMIN_API_KEY` | empty | Dashboard process; secret admin key (16–512 characters, no whitespace); blank prompts in the sidebar |
| `DASHBOARD_REQUEST_TIMEOUT_SECONDS` | `10` | Dashboard process; HTTP deadline from 0.1 to 60 seconds |
| `DASHBOARD_TRUST_ENV` | `false` | Dashboard process; when false, ambient proxy variables are ignored |
| `POSTGRES_USER` | `adapter` | Compose only; PostgreSQL user and the user embedded in the API's database URL |
| `POSTGRES_PASSWORD` | required | Compose only; secret, no default, must be URL-safe because it is interpolated into `DATABASE_URL` |
| `POSTGRES_DB` | `ai_adapter` | Compose only; PostgreSQL database name |
| `RUN_MIGRATIONS` | `true` (API image) | Container only; when true, the API entrypoint runs `alembic upgrade head` before starting Uvicorn |
| `E2E_USER_KEY` | none | Verifier process only; must match a key in `SECURITY_API_KEYS` |
| `E2E_ADMIN_KEY` | none | Verifier process only; must match a key in `SECURITY_ADMIN_API_KEYS` |

Reliability provider names are normalized like provider keys and are validated against the registry at startup. An unregistered secondary or fallback fails startup explicitly instead of being ignored.

`MODEL_VERSION_MANIFEST` points to a reviewed, bounded JSON manifest. Relative paths are resolved from the process working directory, so run the service from the repository root or use an absolute path. When enabled, startup fails if the file is missing, malformed, oversized, contains duplicate entries, omits a configured provider/model, configures a `retired` model, or uses a non-`active` default model. A `deprecated` non-default model is allowed with a warning. Leave the value blank to disable model version management; `/api/v1/model-versions` then returns `503 model_catalog_unavailable`.

Stage K adds two monitoring settings. `MONITORING_QUERY_TIMEOUT_SECONDS` bounds one aggregate query; `MONITORING_LATENCY_SAMPLE_LIMIT` bounds the latest duration sample used for p50/p95. Counts, sums, token totals, cost totals, and average/min/max latency remain full-window SQL aggregates. The durable `/monitoring/summary` endpoint requires `DATABASE_ENABLED=true`; the process-local `/monitoring/metrics` endpoint does not. Both are admin-only when authentication is enabled.

Stage L adds five `DASHBOARD_*` settings, read by the Streamlit process rather than the API. They are deliberately separate because the dashboard is a different process and deployment unit. Prefer `DASHBOARD_ADMIN_API_KEY` from the environment or an ignored `.env`; leaving it blank makes the sidebar prompt for a masked key, which is held only in that Streamlit session. The base URL must be a plain origin: health paths are appended at the root and API paths under `DASHBOARD_API_PREFIX`. A remote `http://` origin is allowed with a warning; use HTTPS or a local tunnel for non-loopback deployments. `.streamlit\config.toml` binds the dashboard to `127.0.0.1`, enables CORS/XSRF protection, and minimizes the developer toolbar. `scripts\dashboard.ps1` refuses a non-loopback host unless `-AllowRemote` is supplied explicitly.

Stage M uses `.env.docker`, which is read by Docker Compose and `scripts\demo.ps1`, not by the application. It supplies the PostgreSQL credentials and the user/admin API keys; Compose injects the database URL and maps the admin key into the dashboard. `scripts\demo.ps1` generates URL-safe random values when `.env.docker` is absent, refuses `replace-with*` placeholders, and never prints the values. The Compose topology expects one admin key because the dashboard receives the same string as a single Bearer key; deployments that configure several comma-separated admin keys should add a Compose override that supplies a dedicated `DASHBOARD_ADMIN_API_KEY`. The verifier reads `E2E_USER_KEY` and `E2E_ADMIN_KEY` from its own process environment, so keys are never passed on the command line. `.env.docker` is git-ignored.

Stage J introduced no user-facing runtime setting. The workflow exports only interpreter determinism flags (`PYTHONHASHSEED`, `PYTHONDONTWRITEBYTECODE`) and `UPDATE_REGRESSION_BASELINES=0`. It deliberately does not export application settings globally: the tests create isolated `Settings(_env_file=None, ...)` objects, and a clean CI checkout has no `.env`. It requires no repository secrets and never calls a live provider. `scripts/quality.ps1` applies the same baseline lock and interpreter flags locally.

The OpenAI provider is registered only when `OPENAI_API_KEY` is non-blank. Selecting `DEFAULT_PROVIDER=openai` without a key fails at startup with an explicit error instead of silently falling back.

Enable a real provider for the current PowerShell session. Enter the key through a hidden prompt so it never appears in the window, shell history, or chat:

```powershell
$secure = Read-Host "Provider API key" -AsSecureString
$env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new("", $secure).Password
$env:DEFAULT_PROVIDER = "openai"
.\scripts\run-dev.ps1
```

Revoke any key that is ever exposed in a transcript, screenshot, or log. Never place a real key directly in a command line or a committed file.

`SECURITY_REQUIRE_AUTH=false` keeps local development unauthenticated. With auth enabled, requests need `Authorization: Bearer <key>`; provider-management endpoints additionally require an admin key. Production refuses to start unless auth is enabled and a user key exists. Keys must not be committed; inject them as environment variables:

```powershell
$env:SECURITY_REQUIRE_AUTH = "true"
$env:SECURITY_API_KEYS = "user-key-0123456789abcdef"
$env:SECURITY_ADMIN_API_KEYS = "admin-key-0123456789abcdef"
.\scripts\run-dev.ps1
```

Budget limits are USD decimal strings and must satisfy `per-request <= daily <= monthly`. `BUDGET_PROVIDER_PRICING` is a JSON object; the default prices the fake provider at zero and OpenAI at $0.15 input / $0.60 output per million tokens.

Persistence is enabled in `.env` with a file-backed SQLite database under the git-ignored `data\` directory. Apply the schema with Alembic (the application can also auto-create it locally):

```powershell
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\alembic.exe current
```

Production requires PostgreSQL and versioned migrations:

```powershell
$env:DATABASE_ENABLED = "true"
$env:DATABASE_URL = "postgresql+asyncpg://adapter_user:CHANGE_ME@db-host:5432/ai_adapter"
$env:DATABASE_AUTO_CREATE = "false"
$env:DATABASE_ECHO = "false"
.\.venv\Scripts\alembic.exe upgrade head
.\scripts\run-dev.ps1
```

`postgres://` and `postgresql://` URLs are normalized to the async `postgresql+asyncpg` driver. In production the service refuses to start with SQLite, `DATABASE_AUTO_CREATE=true`, or `DATABASE_ECHO=true`. `DATABASE_URL` is a `SecretStr`; its password is never logged. Disable persistence with `DATABASE_ENABLED=false`; request-history endpoints then return `503 persistence_unavailable`.

Do not commit `.env` or paste keys into source, tests, logs, or issue trackers. `.env` is git-ignored.

Example override:

```powershell
$env:DEFAULT_PROVIDER = "fake"
$env:FAKE_PROVIDER_MODELS = "fake-small,fake-large,fake-test"
$env:FAKE_PROVIDER_DEFAULT_MODEL = "fake-test"
$env:LOG_FORMAT = "console"
.\scripts\run-dev.ps1
```

Invalid provider, security, or budget configuration fails at startup. `ENVIRONMENT=production` disables `/docs`, `/redoc`, and `/openapi.json` and requires authentication.

---

## 7. Run the service

```powershell
.\scripts\run-dev.ps1
```

Equivalent direct command:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-access-log
```

Endpoints:

| Method | Path | Purpose |
|---|---|---|
| GET | `/health/live` | Liveness |
| GET | `/health/ready` | Readiness checks |
| GET | `/api/v1/system/info` | Non-secret service metadata |
| GET | `/api/v1/providers` | List registered providers and models |
| GET | `/api/v1/providers/{provider_name}` | Inspect one provider |
| GET | `/api/v1/providers/{provider_name}/health` | Provider availability plus circuit state |
| GET | `/api/v1/model-versions` | Admin-only tracked model versions and configured state |
| POST | `/api/v1/generate` | Generate through the bounded provider chain |
| POST | `/api/v1/fault-reports/summarize` | Extract a validated structured summary from a maintenance fault report |
| GET | `/api/v1/requests` | Admin-only persisted request history with filters and pagination |
| GET | `/api/v1/requests/{record_id}` | Admin-only single request-log record |
| GET | `/api/v1/monitoring/summary` | Admin-only windowed cost/latency report with kind/provider filters |
| GET | `/api/v1/monitoring/metrics` | Admin-only Prometheus text exposition |

With `SECURITY_REQUIRE_AUTH=true`, generation and fault summarization require a user or admin Bearer key, and `/api/v1/providers*`, `/api/v1/model-versions`, `/api/v1/requests*`, and `/api/v1/monitoring/*` require an admin key. Health and system metadata remain available for probes and clients. Successful responses carry `X-Request-ID`, `X-RateLimit-Limit`, and `X-RateLimit-Remaining`. `/health/ready` additionally reports `database: ok|unavailable` when persistence is enabled and `models: ok` when the model version catalog is enabled.

Interactive docs: <http://127.0.0.1:8000/docs>

A custom port:

```powershell
.\scripts\run-dev.ps1 -Port 8123
```

### Run the Stage L dashboard

Keep the API running, then start the dashboard in a second PowerShell window:

```powershell
$env:DASHBOARD_API_BASE_URL = "http://127.0.0.1:8000"
$env:DASHBOARD_ADMIN_API_KEY = "<admin-key>"
.\scripts\dashboard.ps1
```

Open <http://127.0.0.1:8501>. Equivalent direct command:

```powershell
.\.venv\Scripts\python.exe -m streamlit run dashboard/app.py `
  --server.address 127.0.0.1 --server.port 8501 `
  --server.headless true --browser.gatherUsageStats false
```

If `DASHBOARD_ADMIN_API_KEY` is blank, the sidebar shows a masked key field instead. The key is held only in the Streamlit session and sent only to the configured API origin. `-Port` changes the dashboard port; `-HostAddress` requires `-AllowRemote` for any non-loopback address.

### Run the Stage M container stack

Prerequisites: Docker Desktop with Compose v2 running, PowerShell, and the project's `.venv` (the demo uses the local Python interpreter for the HTTP verifier). Ports `8000` and `8501` must be free.

One-command demonstration:

```powershell
.\scripts\demo.ps1
```

The script creates `.env.docker` with random URL-safe PostgreSQL, user, and admin secrets if it does not exist, builds the images, starts PostgreSQL, the API, and the dashboard, waits for readiness, runs the end-to-end verifier, and tears the stack down. It leaves no containers or volumes behind by default. Options:

```powershell
.\scripts\demo.ps1 -Reset          # remove existing containers and volumes first
.\scripts\demo.ps1 -KeepRunning    # leave the stack running after verification
.\scripts\demo.ps1 -SkipBuild      # reuse existing images
.\scripts\demo.ps1 -TimeoutSeconds 300
```

With `-KeepRunning`, open:

- API health: <http://127.0.0.1:8000/health/ready>
- Dashboard: <http://127.0.0.1:8501>
- API docs are disabled because the container runs `ENVIRONMENT=production`.

Equivalent direct Compose workflow:

```powershell
Copy-Item .env.docker.example .env.docker
# Replace every replace-with* placeholder in .env.docker before continuing.
docker compose --env-file .env.docker --project-name ai-adapter-demo up -d --build
docker compose --env-file .env.docker --project-name ai-adapter-demo ps
docker compose --env-file .env.docker --project-name ai-adapter-demo logs -f api
```

Run the verifier manually after the services are healthy:

```powershell
# Use the same keys you placed in .env.docker.
$env:E2E_USER_KEY = "<user-key>"
$env:E2E_ADMIN_KEY = "<admin-key>"
.\.venv\Scripts\python.exe scripts\e2e_demo.py `
  --api-base-url http://127.0.0.1:8000 `
  --dashboard-url http://127.0.0.1:8501
```

Expected final line:

```text
stage-m e2e: PASS
```

Stop the stack:

```powershell
docker compose --env-file .env.docker --project-name ai-adapter-demo down
```

`down -v` also removes the PostgreSQL volume. The API entrypoint applies Alembic migrations before serving; if the database is not ready, it retries ten times at two-second intervals and then exits nonzero. Compose starts the API only after PostgreSQL is healthy and the dashboard only after the API reports ready.

---

## 8. Provider API walkthrough

### List providers

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/providers
```

Actual output:

```json
[
  {
    "name": "fake",
    "display_name": "Local Fake Provider",
    "kind": "fake",
    "models": ["fake-small", "fake-large"],
    "default_model": "fake-small",
    "is_default": true
  }
]
```

### Check provider availability

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/providers/fake/health
```

Actual output:

```json
{
  "provider": "fake",
  "status": "healthy",
  "latency_ms": 0.001,
  "detail": null,
  "circuit": {
    "state": "closed",
    "failure_count": 0,
    "recovery_remaining_seconds": null
  }
}
```

### Generate through the default provider

```powershell
$body = @'
{"messages":[{"role":"system","content":"Be terse"},{"role":"user","content":"Pump 3 vibration alarm"}]}
'@

Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/generate `
  -ContentType "application/json" `
  -Headers @{ "X-Request-ID" = "stage-b-generate-001" } `
  -Body $body
```

Actual output (shape after Stage D; values are deterministic):

```json
{
  "provider": "fake",
  "model": "fake-small",
  "content": "[fake:fake-small] Pump 3 vibration alarm",
  "usage": {"prompt_tokens": 6, "completion_tokens": 5, "total_tokens": 11},
  "finish_reason": "stop",
  "latency_ms": 0.019,
  "request_id": "stage-b-generate-001",
  "requested_provider": "fake",
  "retry_count": 0,
  "fallback_used": false,
  "fallback_reason": null,
  "providers_tried": ["fake"],
  "cost_usd": 0.0
}
```

### Select a model and cap output

```json
{
  "provider": "fake",
  "model": "fake-large",
  "max_tokens": 2,
  "messages": [{"role": "user", "content": "Pump 3 vibration alarm"}]
}
```

Actual output:

```json
{
  "provider": "fake",
  "model": "fake-large",
  "content": "[fake:fake-large] Pump",
  "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
  "finish_reason": "length",
  "latency_ms": 0.02,
  "request_id": "ff3fdb49d46a4278a29dca35abcbeb71",
  "requested_provider": "fake",
  "retry_count": 0,
  "fallback_used": false,
  "fallback_reason": null,
  "providers_tried": ["fake"],
  "cost_usd": 0.0
}
```

### Provider switching

The `provider` field selects the first provider in the reliability chain. Omitting it uses `DEFAULT_PROVIDER`. The selected provider is followed by `RELIABILITY_SECONDARY_PROVIDER` (optional) and `RELIABILITY_FALLBACK_PROVIDER` (default `fake`); duplicates are removed, so a chain never tries the same provider twice.

Without an OpenAI key, the normal development registry contains only `fake`, and the chain collapses to that single provider. With a non-blank `OPENAI_API_KEY`, it contains `fake` and `openai`. Stage B switching was verified with two fake adapters (`fake` and `fake-alt`); Stage C verified routing to the OpenAI adapter with an injected mock transport; Stage D adds failover between chain members.

### OpenAI provider

The OpenAI adapter calls `POST {OPENAI_BASE_URL}/chat/completions` with the standard chat-completions payload and an `Authorization: Bearer ...` header derived from `OPENAI_API_KEY`.

Configure a key for the current process and start the service:

```powershell
$env:OPENAI_API_KEY = "sk-..."
$env:OPENAI_MODELS = "gpt-4o-mini,gpt-4o"
$env:OPENAI_DEFAULT_MODEL = "gpt-4o-mini"
.\scripts\run-dev.ps1
```

Expected provider listing with a key configured:

```json
[
  {
    "name": "fake",
    "display_name": "Local Fake Provider",
    "kind": "fake",
    "models": ["fake-small", "fake-large"],
    "default_model": "fake-small",
    "is_default": false
  },
  {
    "name": "openai",
    "display_name": "OpenAI",
    "kind": "openai",
    "models": ["gpt-4o-mini", "gpt-4o"],
    "default_model": "gpt-4o-mini",
    "is_default": true
  }
]
```

Request OpenAI explicitly:

```powershell
$body = @'
{"provider":"openai","model":"gpt-4o-mini","messages":[{"role":"user","content":"Reply with exactly: adapter ok"}]}
'@

Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/generate `
  -ContentType "application/json" `
  -Body $body
```

The normalized response shape below was verified through the full API using `httpx.MockTransport`; live text and token counts depend on the model:

```json
{
  "provider": "openai",
  "model": "gpt-4o-mini",
  "content": "Check the coolant.",
  "usage": {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16},
  "finish_reason": "stop",
  "latency_ms": 0.42,
  "request_id": "...",
  "requested_provider": "openai",
  "retry_count": 0,
  "fallback_used": false,
  "fallback_reason": null,
  "providers_tried": ["openai"],
  "cost_usd": 0.000004
}
```

No live paid request was made during implementation because no key was present. To verify with a real key, run exactly one billable request:

```powershell
$env:OPENAI_API_KEY = "sk-..."
.\scripts\verify-openai.ps1 -Model gpt-4o-mini
```

The script prints the `/models` health result followed by the normalized generation result. It reads the same configuration as the service, never prints the key, and closes the HTTP client on exit. A successful run exits with code `0`; a missing key exits with `2`; a normalized provider failure exits with `1`.

Provider health uses a bounded `GET /models` request:

| Condition | Reported status |
|---|---|
| HTTP 200 with a `data` list | `healthy` |
| HTTP 5xx, invalid JSON, unexpected payload | `degraded` |
| HTTP 401/403/other 4xx, timeout, transport failure | `unavailable` |

Health details are static safe strings; upstream response bodies are not echoed.

Local runtime evidence with a dummy key and `OPENAI_BASE_URL=http://127.0.0.1:9/v1` (no external request left the machine):

```json
{"provider":"openai","status":"unavailable","latency_ms":2040.022,"detail":"Endpoint is unreachable."}
```

```text
HTTP 503
{"error":{"code":"provider_unavailable","message":"OpenAI endpoint is unreachable.","provider":"openai","retryable":true},"request_id":"stage-c-live-openai-001"}
```

The corresponding JSON logs contained the request ID and normalized error code but neither the dummy key nor the prompt text.

### Stage D reliability walkthrough

Live verification used a dummy key, an unreachable endpoint (`OPENAI_BASE_URL=http://127.0.0.1:9/v1`, so no external request left the machine), two attempts per provider, a two-failure circuit threshold, and the deterministic local fallback:

```powershell
$env:OPENAI_API_KEY = "sk-dummy-stage-d-12345678"
$env:OPENAI_BASE_URL = "http://127.0.0.1:9/v1"
$env:DEFAULT_PROVIDER = "openai"
$env:RELIABILITY_MAX_ATTEMPTS = "2"
$env:RELIABILITY_BACKOFF_BASE_SECONDS = "0.01"
$env:RELIABILITY_BACKOFF_MAX_SECONDS = "0.02"
$env:RELIABILITY_JITTER_SECONDS = "0"
$env:RELIABILITY_TIMEOUT_SECONDS = "5"
$env:RELIABILITY_CIRCUIT_FAILURE_THRESHOLD = "2"
$env:RELIABILITY_CIRCUIT_RECOVERY_SECONDS = "5"
$env:RELIABILITY_SECONDARY_PROVIDER = ""
$env:RELIABILITY_FALLBACK_PROVIDER = "fake"
.\scripts\run-dev.ps1
```

First request — the OpenAI adapter fails twice, the second failure opens its circuit, and the fallback answers:

```json
{"provider":"fake","model":"fake-small","content":"[fake:fake-small] Pump 3 vibration alarm","usage":{"prompt_tokens":4,"completion_tokens":5,"total_tokens":9},"finish_reason":"stop","latency_ms":0.012,"request_id":"stage-d-live-001","requested_provider":"openai","retry_count":1,"fallback_used":true,"fallback_reason":"provider_unavailable","providers_tried":["openai","fake"],"cost_usd":0.0}
```

Second request — the open circuit rejects the provider without contacting it and falls back immediately:

```json
{"provider":"fake","model":"fake-small","content":"[fake:fake-small] Pump 3 vibration alarm","usage":{"prompt_tokens":4,"completion_tokens":5,"total_tokens":9},"finish_reason":"stop","latency_ms":0.004,"request_id":"stage-d-live-002","requested_provider":"openai","retry_count":0,"fallback_used":true,"fallback_reason":"provider_circuit_open","providers_tried":["openai","fake"],"cost_usd":0.0}
```

Provider health now reports the breaker alongside availability:

```json
{"provider":"openai","status":"unavailable","latency_ms":2049.266,"detail":"Endpoint is unreachable.","circuit":{"state":"open","failure_count":2,"recovery_remaining_seconds":2.875251199991908}}
```

Representative structured log lines (request IDs retained, no prompt or key content):

```json
{"logger":"app.reliability.router","message":"provider.retry","request_id":"stage-d-live-001","provider":"openai","failed_attempt":1,"next_attempt":2,"delay_ms":10.0,"error_code":"provider_unavailable"}
{"logger":"app.reliability.circuit","message":"circuit.opened","provider":"openai","failure_count":2,"recovery_timeout_seconds":5.0}
{"logger":"app.reliability.router","message":"provider.route.completed","request_id":"stage-d-live-002","requested_provider":"openai","provider":"fake","providers_tried":["openai","fake"],"retry_count":0,"fallback_used":true,"fallback_reason":"provider_circuit_open"}
```

A search of the server log for the dummy key and the prompt returned zero matches.

With the fallback disabled and a single attempt, the exhausted chain returns a normalized error instead of looping:

```text
HTTP 503
{"error":{"code":"provider_unavailable","message":"OpenAI endpoint is unreachable.","provider":"openai","retryable":true},"request_id":"stage-d-live-003"}
```

Configuring an unregistered reliability provider fails startup immediately:

```text
ValueError: Reliability provider 'ghost' is not registered; available providers: fake
```

### Stage E security and budget walkthrough

Live verification used a user key, an admin key, a two-request window, and the free fake provider:

```powershell
$env:SECURITY_REQUIRE_AUTH = "true"
$env:SECURITY_API_KEYS = "stage-e-user-key-0123456789"
$env:SECURITY_ADMIN_API_KEYS = "stage-e-admin-key-0123456789"
$env:SECURITY_RATE_LIMIT_REQUESTS = "2"
$env:SECURITY_RATE_LIMIT_WINDOW_SECONDS = "60"
.\scripts\run-dev.ps1 -Port 8140
```

A request without a key is rejected before generation:

```text
HTTP/1.1 401 Unauthorized
www-authenticate: Bearer
{"error":{"code":"authentication_required","message":"A valid API key is required.","provider":null,"retryable":false},"request_id":"12aab55bd4db42babef1bb08f2542af2"}
```

A user key cannot reach provider management:

```text
HTTP/1.1 403 Forbidden
{"error":{"code":"permission_denied","message":"Administrator privileges are required.","provider":null,"retryable":false},"request_id":"4d2a2910757d4cd3bfe66c8b92dcec44"}
```

The admin key receives the provider list. An authenticated generation succeeds and reports rate-limit state:

```text
HTTP/1.1 200 OK
x-ratelimit-limit: 2
x-ratelimit-remaining: 1
x-request-id: stage-e-live-001
{"provider":"fake","model":"fake-small","content":"[fake:fake-small] hello","usage":{"prompt_tokens":1,"completion_tokens":2,"total_tokens":3},"finish_reason":"stop","latency_ms":0.005,"request_id":"stage-e-live-001","requested_provider":"fake","retry_count":0,"fallback_used":false,"fallback_reason":null,"providers_tried":["fake"],"cost_usd":0.0}
```

The third request in the window is limited with an actionable retry delay:

```text
HTTP/1.1 429 Too Many Requests
retry-after: 60
x-ratelimit-limit: 2
x-ratelimit-remaining: 0
{"error":{"code":"rate_limit_exceeded","message":"Rate limit exceeded; retry after 60 seconds.","provider":null,"retryable":true},"request_id":"bb5d1bc1bab64db7a11244c64e0582fd"}
```

With `BUDGET_PER_REQUEST_USD=0.0001`, daily `0.001`, monthly `0.01`, and a fake price of $1 per million tokens, the pre-call estimate exceeds the per-request limit:

```text
HTTP/1.1 402 Payment Required
{"error":{"code":"budget_exceeded","message":"The estimated request cost exceeds the per-request budget limit.","provider":null,"retryable":false},"request_id":"b6a1a69531e94cfcae822487139eda93"}
```

The success summary log contains the operational fields and no prompt content:

```json
{"logger": "app.api.generation", "message": "request.summary", "event": "request.summary", "request_id": "stage-e-live-001", "auth_role": "user", "requested_provider": "fake", "provider": "fake", "model": "fake-small", "prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3, "cost_usd": 0.0, "retry_count": 0, "fallback_used": false, "fallback_reason": null, "duration_ms": 0.42, "status": "success"}
```

A search of both server logs for the configured keys, the `Authorization` header name, and the submitted prompt returned zero matches.

### Stage F fault-report walkthrough

Provider-success path, verified against a temporary OpenAI-compatible stub bound to `127.0.0.1` (no external request, dummy key only):

```powershell
$env:OPENAI_API_KEY = "dummy-stub-key"
$env:OPENAI_BASE_URL = "http://127.0.0.1:8099/v1"
$env:DEFAULT_PROVIDER = "openai"
$env:RELIABILITY_FALLBACK_PROVIDER = ""
$env:RELIABILITY_MAX_ATTEMPTS = "1"
.\scripts\run-dev.ps1 -Port 8012
```

The request used the labeled report from the tests and returned:

```json
{"request_id":"stage-f-ai-001","summary":{"machine":"Conveyor 3","fault_description":"Bearing seized after abnormal vibration","temperature":87.0,"temperature_unit":"C","downtime":"2 hours","action_taken":"Replaced the bearing and realigned the belt","severity":"high"},"extraction":"provider","extraction_reason":null,"missing_fields":[],"selected_provider":"openai","provider":"openai","model":"gpt-4o-mini","prompt_tokens":120,"completion_tokens":40,"total_tokens":160,"cost_usd":0.000042,"retry_count":0,"fallback_used":false,"fallback_reason":null,"providers_tried":["openai"]}
```

`cost_usd` is the configured OpenAI rate: 120 input tokens at $0.15/M plus 40 output tokens at $0.60/M.

The same report through the default fake provider produces a non-JSON echo, so deterministic extraction supplies the validated summary:

```powershell
$report = @"
Machine: Conveyor 3
Fault description: Bearing seized after abnormal vibration
Temperature: 87 C
Downtime: 2 hours
Action taken: Replaced the bearing and realigned the belt
Severity: Major
"@
$body = @{ report = $report } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/api/v1/fault-reports/summarize -Method Post -ContentType "application/json" -Body $body
```

Actual output from port `8010`:

```json
{"request_id":"stage-f-fake-001","summary":{"machine":"Conveyor 3","fault_description":"Bearing seized after abnormal vibration","temperature":87.0,"temperature_unit":"C","downtime":"2 hours","action_taken":"Replaced the bearing and realigned the belt","severity":"high"},"extraction":"deterministic","extraction_reason":"ai_invalid_json","missing_fields":[],"selected_provider":"fake","provider":"fake","model":"fake-small","prompt_tokens":148,"completion_tokens":30,"total_tokens":178,"cost_usd":0.0,"retry_count":0,"fallback_used":false,"fallback_reason":null,"providers_tried":["fake"]}
```

With `DEFAULT_PROVIDER=openai`, an unreachable `OPENAI_BASE_URL`, fallback disabled, and one attempt per provider, the provider failure still returns a valid deterministic summary instead of a fabricated AI result:

```json
{"request_id":"stage-f-openai-down-001","summary":{"machine":"Pump 3","fault_description":"At 09:15 the pump 3 stopped after overheating","temperature":null,"temperature_unit":null,"downtime":"45 minutes","action_taken":"Replaced the bearing and realigned the belt","severity":"critical"},"extraction":"deterministic","extraction_reason":"provider_unavailable","missing_fields":["temperature"],"selected_provider":"openai","provider":null,"model":null,"prompt_tokens":0,"completion_tokens":0,"total_tokens":0,"cost_usd":0.0,"retry_count":0,"fallback_used":false,"fallback_reason":null,"providers_tried":["openai"]}
```

The temperature was not stated in that report and remained `null`, so it appears in `missing_fields`. No value was inferred.

Malformed reports return `422`; selecting an unregistered provider still returns the normalized `404` rather than a summary. The `fault_report.summary` log record contains the request ID, auth role, selected/final provider, model, extraction mode and reason, missing-field count, token counts, cost, retry/fallback metadata, duration, and status. Searches of the server logs for the dummy key and the report text returned zero matches.

### Stage G request-history walkthrough

Apply the schema, enable authentication, and start the service:

```powershell
.\.venv\Scripts\alembic.exe upgrade head
$env:SECURITY_REQUIRE_AUTH = "true"
$env:SECURITY_API_KEYS = "live-user-key-0123456789abcdef"
$env:SECURITY_ADMIN_API_KEYS = "live-admin-key-0123456789abcdef"
.\scripts\run-dev.ps1 -Port 8011
```

Generate one successful request, one deterministic fault summary, one unknown-provider error, and one malformed request:

```powershell
$user = @{ Authorization = "Bearer live-user-key-0123456789abcdef" }
$admin = @{ Authorization = "Bearer live-admin-key-0123456789abcdef" }

Invoke-RestMethod http://127.0.0.1:8011/api/v1/generate `
  -Method Post -Headers ($user + @{"X-Request-ID" = "stage-g-live-001"}) `
  -ContentType "application/json" `
  -Body (@{ messages = @(@{ role = "user"; content = "hello" }) } | ConvertTo-Json -Depth 5)

Invoke-RestMethod http://127.0.0.1:8011/api/v1/fault-reports/summarize `
  -Method Post -Headers ($user + @{"X-Request-ID" = "stage-g-live-002"}) `
  -ContentType "application/json" `
  -Body (@{ report = "Pump 7 overheated to 95 C and the line stopped for 20 minutes." } | ConvertTo-Json)

try {
  Invoke-RestMethod http://127.0.0.1:8011/api/v1/generate `
    -Method Post -Headers ($user + @{"X-Request-ID" = "stage-g-live-003"}) `
    -ContentType "application/json" `
    -Body (@{ provider = "missing"; messages = @(@{ role = "user"; content = "hello" }) } | ConvertTo-Json -Depth 5)
} catch { $_.Exception.Response.StatusCode.value__ }

try {
  Invoke-RestMethod http://127.0.0.1:8011/api/v1/generate `
    -Method Post -Headers ($user + @{"X-Request-ID" = "stage-g-live-004"}) `
    -ContentType "application/json" `
    -Body (@{ messages = @() } | ConvertTo-Json -Depth 5)
} catch { $_.Exception.Response.StatusCode.value__ }

Invoke-RestMethod "http://127.0.0.1:8011/api/v1/requests?limit=10" -Headers $admin
Invoke-RestMethod "http://127.0.0.1:8011/api/v1/requests?status=error&kind=generation" -Headers $admin
```

Actual live SQLite result (four records, newest first):

```text
id  request_id          kind          status    http  error_code                   selected_provider  provider  model       total_tokens  cost_usd
4   stage-g-live-004    generation    error     422   request_validation_failed    null               null      null        0             0
3   stage-g-live-003    generation    error     404   provider_not_found           missing            missing   null        0             0
2   stage-g-live-002    fault_report  degraded  200   null                         fake               fake      fake-small  150           0
1   stage-g-live-001    generation    success   200   null                         fake               fake      fake-small  3             0
```

`/health/ready` returned `{"status":"ready","checks":{"configuration":"ok","logging":"ok","database":"ok"}}`. The database contained no prompt text, bearer key, or `Authorization` value. Server logs also contained zero matches for those values. The Alembic revision was `20261114_0001`.

PostgreSQL availability was not assumed: the migration was additionally rendered offline with `alembic upgrade head --sql` for `postgresql+asyncpg`, producing `TIMESTAMP WITH TIME ZONE`, `NUMERIC(14, 6)`, `JSON`, `BOOLEAN`, and the five indexes. No local PostgreSQL server was available in this environment, so a live PostgreSQL connection is not claimed.

### Stage H fault-matrix walkthrough

Run only the matrix:

```powershell
.\scripts\fault-matrix.ps1
```

Actual result:

```text
...............................                                          [100%]
31 passed in 1.26s
```

Representative assertions executed by the matrix:

| Scenario | Asserted result |
|---|---|
| `timeout` with fallback | `200`, `provider: "fake"`, `fallback_reason: "provider_timeout"`, `retry_count: 2`, three primary attempts |
| `rate_limit`, `server_error`, `unavailable` | Same fallback recovery; exhausted failure without fallback returns `429`, `502`, `503` respectively |
| `wrong_identity` | Provider result is rejected as `provider_invalid_response`; retries and fallback still work |
| invalid request | `400` on `/generate` and `/fault-reports/summarize`; no fallback or deterministic masking; one provider call |
| unknown provider | `404 provider_not_found`; zero provider calls |
| fault report + provider failure | `200`, `extraction: "deterministic"`, provider error as `extraction_reason`, degraded request-log row |
| malformed/schema-invalid/empty output | `ai_invalid_json`, `ai_invalid_schema`, `ai_empty_summary`; valid JSON control reports `extraction: "provider"` |
| hanging provider | Timeout cancellation bounded the test below 1.5 s with two attempts |
| repeated failures | Circuit opens at threshold, second request uses `provider_circuit_open`, primary call count stays fixed |
| admission faults | Missing bearer key and rate-limit rejection never reach the provider; `401` and `429` rows persist |
| leakage markers | Prompt, report, bearer key, and `sk-` secret absent from responses, logs, and request history |

The matrix replaces only the provider adapter. It exercises the real routes, authentication, rate limiter, budget hook, reliability chain, parser/extractor, request logger, and SQLite persistence.

### Stage I model-version and regression walkthrough

The shipped `.env` enables the manifest at `config/model_versions.json`. Startup validates it before the application begins serving:

```text
"model_catalog_enabled": true, "model_catalog_entries": 4, "model_catalog_status_counts": {"active": 4}
```

Inspect the tracked inventory:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/model-versions
```

Actual result with the default local configuration:

```json
{
  "models": [
    {
      "provider": "fake",
      "model": "fake-large",
      "version": "1.0.0",
      "status": "active",
      "released_on": "2026-11-14",
      "notes": "Deterministic local model used for development and fallback.",
      "configured": true
    },
    {
      "provider": "fake",
      "model": "fake-small",
      "version": "1.0.0",
      "status": "active",
      "released_on": "2026-11-14",
      "notes": "Deterministic local model used for development and fallback.",
      "configured": true
    },
    {
      "provider": "openai",
      "model": "gpt-4o",
      "version": "gpt-4o-2024-11-20",
      "status": "active",
      "released_on": "2024-11-20",
      "notes": "Pinned OpenAI snapshot; update the manifest when changing deployments.",
      "configured": false
    },
    {
      "provider": "openai",
      "model": "gpt-4o-mini",
      "version": "gpt-4o-mini-2024-07-18",
      "status": "active",
      "released_on": "2024-07-18",
      "notes": "Pinned OpenAI snapshot; update the manifest when changing deployments.",
      "configured": false
    }
  ]
}
```

`configured: false` is expected for OpenAI while no key is configured; the entries remain visible for lifecycle tracking. Readiness now includes the catalog:

```json
{"status":"ready","checks":{"configuration":"ok","logging":"ok","models":"ok","database":"ok"}}
```

Run the Stage I regression suite:

```powershell
.\scripts\regression.ps1
```

Actual result:

```text
........................                                                 [100%]
26 passed in 0.19s
```

The suite pins seven golden HTTP contracts and validates manifest parsing, lifecycle policy, startup rejection, admin authorization, and readiness integration. After an intentional contract change, update baselines explicitly:

```powershell
.\scripts\regression.ps1 -Update
# Review the changed JSON files under tests\regression\baselines.
.\scripts\regression.ps1
```

Do not set `UPDATE_REGRESSION_BASELINES=1` in CI or a normal test run. A baseline mismatch fails with the baseline filename and an instruction to review the diff before updating.

### Stage J CI quality-gate walkthrough

The workflow is committed at `.github/workflows/ci.yml`. It runs on pushes, pull requests, and manual dispatch, with `contents: read`, a 15-minute timeout, pip caching, and no repository secrets.

Run the same gate locally:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\quality.ps1
```

The script executes byte-compilation, Ruff, the full suite, the fault matrix, and the regression suite with baseline updates forced off. Actual local results after Stage J:

```text
python -m ruff check .
All checks passed!

python -m pytest -q --strict-config --strict-markers
281 passed in 4.59s

python -m pytest -q -m fault_matrix tests/test_fault_matrix.py
31 passed in 1.35s

python -m pytest -q -m regression tests/test_model_versions.py tests/test_regression.py
26 passed in 0.19s
```

The Stage J contract tests also passed:

```text
tests/test_ci_quality_gate.py
7 passed in 0.01s
```

The workflow YAML parsed successfully, and `scripts/quality.ps1` passed the PowerShell parser. A clean-checkout simulation copied the application without `.env` and ran the full suite with CI-safe environment variables: **281 passed in 4.73s**. A GitHub-hosted run is not claimed from this workspace because the project folder is not currently a Git repository with a remote; the first hosted run occurs after the workflow is pushed to GitHub. The workflow also runs `git diff --exit-code -- tests/regression/baselines` after the suites, so an accidental baseline rewrite fails the job instead of being accepted.

### Stage K cost and latency monitoring walkthrough

Start the service with persistence enabled (the shipped `.env` already enables SQLite), then generate a few requests and one fault report:

```powershell
.\scripts\run-dev.ps1

Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/generate" `
  -ContentType "application/json" `
  -Body '{"messages":[{"role":"user","content":"Stage K latency sample"}]}'

Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/fault-reports/summarize" `
  -ContentType "application/json" `
  -Body '{"report":"Pump 7 bearing overheated to 95 C; line stopped for 20 minutes."}'
```

Read the durable report:

```powershell
$summary = Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/v1/monitoring/summary?window=1h"
$summary.totals | ConvertTo-Json -Depth 4
$summary.by_kind | Format-Table kind, requests, accepted, errors, cost_usd
$summary.by_provider | Format-Table provider, requests, errors, cost_usd
```

Read the Prometheus exposition:

```powershell
(Invoke-WebRequest `
  -Uri "http://127.0.0.1:8000/api/v1/monitoring/metrics" `
  -UseBasicParsing).Content | Select-String "ai_adapter_"
```

With authentication enabled, add the same admin bearer header used for `/api/v1/requests`:

```powershell
$headers = @{ Authorization = "Bearer <admin-key>" }
Invoke-RestMethod -Headers $headers `
  -Uri "http://127.0.0.1:8000/api/v1/monitoring/summary?window=24h"
```

Actual live result from an isolated SQLite copy after three generation requests and one deterministic fault report:

```text
summary 200 1h 10000
totals requests=4 accepted=4 success_rate=0.75 degraded_rate=0.25
       error_rate=0.0 provider_failure_rate=0.0 fallback_rate=0.0
       cost_usd=0.0 cost_per_request_usd=0.0 cost_per_accepted_result_usd=0.0
       p50_ms=0.09 p95_ms=2.13 average_ms=0.602
by_kind [('fault_report', 1), ('generation', 3)]
by_provider [('fake', 4)]

metrics 200 text/plain; version=1.0.0; charset=utf-8
ai_adapter_requests_total{kind="generation",provider="fake",status="success"} 3.0
ai_adapter_requests_total{kind="fault_report",provider="fake",status="degraded"} 1.0
ai_adapter_accepted_results_total{kind="generation"} 3.0
ai_adapter_accepted_results_total{kind="fault_report"} 1.0
```

The live check also confirmed that prompt text, report text, and URL paths are absent from the exposition. The fake provider has zero configured cost, so its cost fields are correctly zero; unit tests use nonzero `Decimal` costs to verify cost totals, cost per request, and cost per accepted result. Latency values are machine-specific. The summary reflects persisted rows; metrics reflect observations since the current process started. The live server was started only for this verification and then terminated.

### Stage L dashboard walkthrough

The API from the Stage K walkthrough was started on port `8123` with authentication enabled and a temporary SQLite database. Eight requests were recorded: five successful generations, two deterministic fault reports, and one unknown-provider error. The dashboard was started separately:

```powershell
$env:DASHBOARD_API_BASE_URL = "http://127.0.0.1:8123"
$env:DASHBOARD_ADMIN_API_KEY = "<admin-key>"
.\scripts\dashboard.ps1
```

![Stage L Overview](docs/stage-l-overview.png)

The Overview view read the durable `24h` window and reported:

```text
Requests             8
Accepted rate        87.5%
p50 latency          0.21 ms
p95 latency          2.16 ms
Cost / request       $0.000000
Cost / accepted      $0.000000
Provider failure     12.5%
Fallback rate        0.0%
Window 2026-11-13 08:51:08 UTC to 2026-11-14 08:51:08 UTC.
Latency sample: 8 durations.
```

The charts and per-kind/per-provider tables used the same totals. The Providers view listed the registered `fake` provider and its models; clicking **Check health** returned `healthy`, `0.00 ms`, circuit `closed`. The Requests view showed `Showing 1 to 8 of 8 records. Prompts and completions are never stored, so they cannot appear here.` with kind, status, provider, model, duration, tokens, cost, retry, fallback, and HTTP metadata. The Model versions view reported `4 tracked model releases; 4 active.` The Prometheus metrics view reported:

```text
Process requests     8
Accepted results     7
Errors               1
Provider failures    1
Fallbacks            0
Retries              0
Process cost         $0.000000
Tokens               329
Requests by status: degraded: 2, error: 1, success: 5.
```

Tokens is the sum of the `total` token series (`290` fault-report + `39` generation). The counter table lists only bounded-label counters and excludes histogram internals; the raw exposition is available in an expander and is rendered as plain text. Prompts and report text never appeared in any view. Screenshots of the other views: [providers](docs/stage-l-providers.png), [requests](docs/stage-l-requests.png), [model versions](docs/stage-l-models.png), [Prometheus metrics](docs/stage-l-metrics.png).

The same flow is covered headlessly by `tests/test_dashboard.py`, which starts a local Uvicorn API fixture with seeded SQLite rows and drives all five views through Streamlit `AppTest`. The live dashboard and API were stopped after verification.

### Stage M container deployment walkthrough

The intended demonstration is one command on a Docker-capable host:

```powershell
.\scripts\demo.ps1
```

It builds the `api` and `dashboard` targets, starts PostgreSQL on an internal network, waits for migrations and readiness, runs the verifier, and removes the stack. A successful run ends with `stage-m e2e: PASS` and prints the aggregate checks, never the generated secrets.

**Execution note.** Docker Desktop, Podman, WSL, and a Docker daemon are not installed on the implementation host, so an image build or container run is not claimed there. Two forms of executable evidence were produced instead:

1. **Deployment contract suite** (`tests/test_deployment.py`): 15 tests passed and one conditional `docker compose config` test was skipped because no Docker CLI exists. The contract tests verify the multi-stage targets, non-root runtime, health checks, entrypoint retry behavior, service dependency conditions, required-secret interpolation, loopback-only ports, read-only filesystems, dropped capabilities, internal database network, ignore files, environment placeholders, demo secret handling/teardown, and verifier coverage and secret-safety.
2. **Native equivalent end-to-end run**: the API was started with authentication enabled, a temporary SQLite database, model-version catalog enabled, and persistence auto-created; the dashboard was started against it; the same verifier used by `demo.ps1` was executed. Actual output:

```text
readiness: ready database=ok
summary: requests=4 accepted=3 errors=1 total_tokens=160
metrics: 8784 bytes content-type=text/plain
history: total=4
model_versions: entries=4 active=4
dashboard: 200 health=ok
stage-m e2e: PASS
```

The verifier also proved that an unknown provider returns `provider_not_found`, an unauthenticated history request returns `authentication_required`, and the per-run marker did not appear in Prometheus metrics or request history. The first real container build and Compose run remain an explicit deployment-host step; the exact commands are in section 7.

### Unsupported model

```json
{
  "error": {
    "code": "provider_invalid_request",
    "message": "Model 'unknown-model' is not supported by provider 'fake'.",
    "provider": "fake",
    "retryable": false
  },
  "request_id": "stage-b-bad-model-001"
}
```

HTTP status: `400`.

### Unknown provider

```json
{
  "error": {
    "code": "provider_not_found",
    "message": "Provider 'ghost' is not registered.",
    "provider": "ghost",
    "retryable": false
  },
  "request_id": "bc1cf574ddab44f7aef6f63c8f89126d"
}
```

HTTP status: `404`.

Malformed requests are rejected by Pydantic with HTTP `422` and FastAPI’s standard validation detail format. Provider-owned failures use the normalized error envelope above.

### OpenAPI paths from the running server

```text
[
  '/api/v1/fault-reports/summarize',
  '/api/v1/generate',
  '/api/v1/model-versions',
  '/api/v1/monitoring/metrics',
  '/api/v1/monitoring/summary',
  '/api/v1/providers',
  '/api/v1/providers/{provider_name}',
  '/api/v1/providers/{provider_name}/health',
  '/api/v1/requests',
  '/api/v1/requests/{record_id}',
  '/api/v1/system/info',
  '/health/live',
  '/health/ready'
]
```

---

## 9. Local fake provider semantics

The fake provider is deliberately deterministic and offline:

- Content is `[{provider}:{model}] {last user message}`.
- Temperature is accepted for interface parity but does not change output.
- At least one user message is required.
- The requested model must be declared by the provider.
- `max_tokens` truncates by whitespace-delimited words and sets `finish_reason` to `length`. This is a deterministic simulation, not real tokenization.
- Token counts are word-based estimates; `total_tokens` always equals prompt plus completion.
- Health checks are local and return `healthy`.
- No network access, API key, or external service is used.

This provider exists to exercise the adapter contract, provider switching, registry behavior, and API integration without nondeterministic external dependencies.

---

## 10. Structured logging and security

Each record is a single JSON object on stderr. Example from the Stage B server:

```json
{"timestamp": "2026-11-14T06:40:31.230278+00:00", "level": "WARNING", "logger": "app.providers", "message": "provider.error", "event": "provider.error", "request_id": "stage-b-bad-model-001", "provider": "fake", "error_code": "provider_invalid_request", "retryable": false, "status_code": 400, "error_message": "Model 'unknown-model' is not supported by provider 'fake'."}
```

Properties:

- All timestamps are UTC.
- Every record has a `request_id`; non-request logs use `"-"`.
- Access records contain method, path, status, and duration only.
- Request headers, request bodies, response bodies, and query strings are never logged.
- Prompt and completion content are never written to logs. A regression test uses a sensitive marker to verify this.
- Provider error messages are sanitized before logging and before returning them to clients.
- Sensitive mapping keys such as `authorization`, `api_key`, `token`, `secret`, `password`, `cookie`, and `credential` are redacted recursively.
- Bearer tokens and `sk-...` values embedded in strings are redacted.
- Token-usage fields such as `prompt_tokens` are not mistaken for credentials.
- API keys are reduced to SHA-256 digests in memory and are never placed in log records. Authentication failures log only the request ID and error code.
- Every successful generation emits one `request.summary` record with request ID, auth role, requested/final provider, model, prompt/completion/total tokens, cost, retry count, fallback status, processing duration, and final status.
- Every generation and fault-report request also writes one metadata-only `request_logs` row. Rejected requests on those paths store the normalized error code and HTTP status; `401`, `402`, `404`, `422`, and `429` are covered.
- Persisted rows contain no prompt, completion, report text, request body, authorization header, or credential. Persistence errors log only `request_log.persist_failed` with the request ID, kind, and exception type; they never change the API response.
- `DATABASE_URL` is a `SecretStr`; startup logs database enablement, dialect, and auto-create mode, never the DSN.
- Every fault-report request emits one `fault_report.summary` record with request ID, auth role, selected/final provider, model, extraction mode and reason, missing-field count, token counts, cost, retry/fallback metadata, processing duration, and `success`/`degraded` status. The report text and AI output are absent.
- Fault fallback and provider-failure events (`fault_report.extraction_fallback`, `fault_report.provider_failed`) log only reason codes, provider names, and route metadata.
- Budget events (`budget.reserved`, `budget.settled`, `budget.released`, `budget.rejected`) carry provider, request ID, scope, and estimated/actual cost — never prompt text.
- Model-catalog startup logs contain only enablement, entry count, and active/deprecated/retired counts. The manifest path, release notes, and file contents are not logged; deprecated configured models emit provider/model/version metadata only.
- The admin model-version endpoint returns release metadata from the manifest. It contains no API keys, DSNs, or provider request/response payloads.

Use human-readable logs locally:

```powershell
$env:LOG_FORMAT = "console"
.\scripts\run-dev.ps1
```

No API key was configured during Stage C implementation, so no live external request was made. The design keeps keys in environment settings and adapters:

- `OPENAI_API_KEY` is parsed into a Pydantic `SecretStr`, so its value is hidden from normal representations.
- The key is used only to build the `Authorization` header on outbound OpenAI requests.
- It is never placed in normalized results, health data, error messages, logs, or API responses.
- Upstream OpenAI error bodies are not copied into normalized errors; only fixed safe descriptions and HTTP status codes are used.
- Tests assert that a configured test key never appears in logged records or provider error messages.
- Stage E tests additionally assert that user/admin keys never appear in settings representations or captured API logs.
- Stage F tests assert that fault-report text and AI summary content never appear in captured logs.

---

## 11. Tests

Run:

```powershell
.\scripts\test.ps1
```

Equivalent:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Actual result after Stage M:

```text
........................................................................ [ 21%]
.....................s.................................................. [ 42%]
........................................................................ [ 63%]
........................................................................ [ 84%]
.....................................................                    [100%]
=============================== short test summary info ================================
SKIPPED [1] tests\test_deployment.py:224: Docker CLI is not installed on this host
340 passed, 1 skipped in 7.12s
```

Run only the Stage M deployment contract suite:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_deployment.py
```

```text
...............s                                                         [100%]
SKIPPED [1] tests\test_deployment.py:224: Docker CLI is not installed on this host
15 passed, 1 skipped in 0.05s
```

The skipped test runs `docker compose --env-file .env.docker.example config --quiet` when a Docker CLI with Compose v2 is available. It is skipped, not failed, on hosts without Docker; a Docker-capable host therefore adds one executed Compose validation to the suite.

Run only the Stage L dashboard suite:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_dashboard.py
```

```text
.............................                                            [100%]
29 passed in 2.21s
```

Run only the Stage K monitoring suite:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_monitoring.py
```

```text
...............                                                          [100%]
15 passed in 0.42s
```

Run the complete Stage J quality gate locally:

```powershell
.\scripts\quality.ps1
```

The runner performs the same byte-compilation, Ruff, full-suite, fault-matrix, and regression steps as CI, with `UPDATE_REGRESSION_BASELINES` forced to `0`. On a machine where PowerShell script execution is disabled, use the process-scoped policy command shown in the setup section.

Run only the Stage I model-version and regression suite:

```powershell
.\scripts\regression.ps1
```

```text
........................                                                 [100%]
26 passed in 0.19s
```

Run only the fault-injection matrix:

```powershell
.\scripts\fault-matrix.ps1
```

```text
...............................                                          [100%]
31 passed in 1.35s
```

The Stage M suite was also executed from an isolated copy of the project with no `.env`, matching a clean GitHub checkout: **340 passed, 1 skipped in 7.14s** (the deployment test skipped because Docker is absent).

Test conditions: Windows 10.0.26300, Python 3.14.10, offline, no external provider calls. All OpenAI wire coverage uses `httpx.MockTransport`; reliability sleeps are injected so retry tests add no wall-clock delay. Budget clocks and rate-limit clocks are injected for deterministic rollover and window tests. Stage F extraction, parsing, and fallback tests use deterministic local providers. Persistence tests use in-memory SQLite, temporary on-disk databases, and an Alembic subprocess; no PostgreSQL server is contacted. Stage H uses a test-only fault-injecting provider against the real app, routes, auth, rate limiter, router, persistence, and log capture; no runtime fault switch or external service is used. Stage I uses temporary JSON manifests, the shipped manifest against the default registry, deterministic fake/JSON providers, and committed baseline files; the regression snapshots remove provider latency, and no live provider is contacted. Stage J uses text/TOML contract checks over the workflow, PowerShell runner, and Ruff configuration; it does not execute a GitHub-hosted job from this workspace. Stage K uses seeded in-memory SQLite rows with fixed UTC timestamps, fixed costs, and known durations for exact aggregate and percentile checks; API tests use deterministic fake providers, and one live walkthrough used a temporary SQLite database and local Uvicorn. Stage L uses dashboard-owned settings with `monkeypatch` environment isolation, `httpx.MockTransport` for wire-contract and failure-path tests, a bounded synthetic Prometheus exposition, and Streamlit `AppTest` against a local Uvicorn API fixture with seeded SQLite rows; no external monitoring service or browser automation grid is contacted. Stage M uses text and PowerShell-parse contract checks over the Dockerfile, Compose file, ignore files, entrypoint, demo script, and verifier because Docker is absent; one conditional test invokes Docker Compose only when the CLI exists. The deployment verifier was executed against a natively started API (SQLite, authentication, model catalog) and a natively started Streamlit dashboard using temporary secrets and a temporary database; no image build, container start, PostgreSQL container, or public ingress was contacted.

Coverage by file:

| File | What it proves |
|---|---|
| `tests/test_config.py` | Env overrides, CORS parsing, prefix/header/port/provider/model validation |
| `tests/test_sanitize.py` | Nested redaction, bearer/`sk-` redaction, token-usage false-positive guard |
| `tests/test_logging.py` | JSON parseability, redaction, idempotent handler installation |
| `tests/test_health.py` | Live/ready contracts, request-ID behavior, async ASGI transport |
| `tests/test_app_factory.py` | Factory wiring, production doc locking, prefix and version consistency |
| `tests/test_provider_schemas.py` | Message validation, extra-field rejection, usage arithmetic, normalized results |
| `tests/test_fake_provider.py` | Determinism, model switch, token estimates, truncation, health, invalid requests |
| `tests/test_registry.py` | Registration rules, sorted listing, lookup, health identity, shutdown |
| `tests/test_provider_api.py` | Provider listing/health, generation, switching, 400/404/422 behavior, sanitized errors, no prompt logging |
| `tests/test_reliability.py` | Timeout deadlines, retry ceiling/backoff/jitter, circuit transitions and single probe, chain fallback and model remap, invalid-request fail-fast, metadata fields, circuit-state health, config validation, safe retry logs |
| `tests/test_security.py` | Digest-only key handling, role resolution, 401/403 behavior, admin protection, rate-limit windows/isolation/headers, configuration validation, no key leakage in logs |
| `tests/test_budget.py` | Decimal pricing, token estimation, reservation/settlement/release, per-request/daily/monthly enforcement, concurrent reservation safety, rollover, disabled enforcement, router reserve/release semantics, 402 API behavior, cost reporting, summary logging |
| `tests/test_fault_reports.py` | Labeled/prose extraction, unknown-value preservation, severity/unit/duration normalization, strict JSON parsing and schema rejection, provider-success output, invalid-JSON/schema/empty fallbacks, chain-failure fallback with route metadata, malformed/auth/budget errors, prompt-safe summary logging |
| `tests/test_openai_provider.py` | Wire payload/headers, usage and finish-reason mapping, status/network/payload failures, health states, factory registration, secret-safe API integration |
| `tests/test_persistence.py` | DSN validation and production database guards, `SecretStr` handling, repository write/filter/paginate/order/detail, disabled/broken/slow persistence safety, generation and fault-report rows, degraded status, failure rows for `401`/`403`/`404`/`422`/`429`/`402`, admin-only history with UTC filter normalization, history `503`/`404`/`422`, readiness with missing schema, persistence failure without API breakage, prompt/credential non-persistence, Alembic upgrade/downgrade |
| `tests/test_fault_matrix.py` | Six retryable provider faults across generation exhaustion, fallback recovery, and deterministic fault-report degradation; terminal invalid-request and provider-auth policy; unknown providers; malformed/schema-invalid/empty output; actual timeout cancellation; circuit opening and call suppression; admission and persistence rejection; valid controls; prompt/report/credential non-leakage |
| `tests/test_model_versions.py` | Bounded size/UTF-8 JSON parsing, duplicate/missing/invalid manifests, active/deprecated/retired policy, default-model enforcement, startup fail-closed behavior, shipped-manifest coverage, admin 401/403/200 access, configured-state flags, disabled-catalog `503`, and readiness integration |
| `tests/test_regression.py` | Seven golden snapshots pinning generation, deterministic/provider fault-report extraction, normalized errors, provider inventory, model-version inventory, and readiness contracts; volatile provider latency is excluded |
| `tests/test_ci_quality_gate.py` | Workflow triggers, read-only permissions, job timeout, versioned actions, Python 3.14, all required gate commands, no secrets, baseline-update lock, local runner parity, and declared Ruff configuration |
| `tests/test_monitoring.py` | Window filtering, kind/provider filters, accepted/success/degraded/error math, provider failure and fallback rates, cost per request/accepted result, p50/p95 nearest-rank sampling and truncation, disabled/broken/slow persistence, observer isolation, bounded/no-content Prometheus labels, exposition format, admin-only access, DB-free metrics, and bounded settings |
| `tests/test_dashboard.py` | Dashboard origin/prefix/key/timeout validation, secret redaction, remote-HTTP warning, env loading, display formatting, bounded Prometheus parsing and summaries, Authorization placement, no key on health calls, sanitized `403`/timeout/transport/invalid-JSON/redirect failures, content-type and size caps, request-history filters, admin boundary, and all five Streamlit views through `AppTest` against a live local API fixture |
| `tests/test_deployment.py` | Dockerfile builder/runtime/targets, non-root UID/GID, runtime asset copying, no secrets in images, health checks, entrypoint retry/exec behavior and LF endings, Compose services/dependencies/health, production PostgreSQL and auth guards, required-secret interpolation, loopback-only ports, read-only filesystems, capability dropping, internal database network, named volume, ignore rules, env placeholders, demo secret generation/placeholder rejection/teardown/no secret echo, verifier path coverage, proxy/redirect hardening, marker-leak checks, and conditional `docker compose config` validation when the Docker CLI exists |

The suite uses:

- The application factory with isolated `Settings(_env_file=None, ...)`.
- Injected registries for multi-provider switching tests.
- Starlette `TestClient` for synchronous HTTP tests.
- `httpx.AsyncClient` with `ASGITransport` for async coverage.
- Async tests for provider and registry behavior.
- A test-only `FaultProvider` and pytest `fault_matrix` marker for Stage H.
- Temporary model-version manifests, the shipped manifest, and a `regression` pytest marker for Stage I.
- Committed JSON contract baselines; updates occur only through `scripts/regression.ps1 -Update` / `UPDATE_REGRESSION_BASELINES=1`.
- Workflow, PowerShell-runner, and `pyproject.toml` contract checks for Stage J, without invoking a hosted runner.
- Fixed UTC clocks and in-memory SQLite for Stage K aggregate, percentile, and window tests.
- A process-local Prometheus collector inspected directly and through the admin endpoint for bounded-label and secret-exclusion checks.
- Dashboard-owned `DASHBOARD_*` settings, `httpx.MockTransport` wire doubles, and Streamlit `AppTest` for Stage L, with a local Uvicorn API fixture for the full UI flow.
- Dockerfile/Compose/PowerShell contract checks for Stage M, plus a conditional Compose parse test that executes only where a Docker CLI exists.
- A black-box `httpx` verifier for Stage M, with ambient proxies and redirects disabled and no key or prompt output.

Stage A remains green; no previously working endpoint or contract was removed. Stage B and Stage C tests remain green after Stage D. One Stage C test was narrowed to `RELIABILITY_FALLBACK_PROVIDER=""` because its purpose is error sanitization: with fallback configured, an authentication failure now correctly falls back to the local provider instead of returning `502`. All earlier tests remain green after Stage E; the production-docs test now supplies the explicit auth settings that production requires. All Stage A–E tests remain green after Stage F. All Stage A–F tests remain green after Stage G; database persistence is disabled by default in tests and enabled explicitly only by `tests/test_persistence.py`, so existing request contracts are unchanged. All Stage A–G tests remain green after Stage H; the new matrix is test-only and does not alter production behavior. All Stage A–H tests remain green after Stage I; the catalog is disabled unless a manifest is configured, and the new endpoint and readiness check are additive. All Stage A–I tests remain green after Stage J; the release behavior is unchanged and the new checks cover CI policy rather than application behavior. All Stage A–J tests remain green after Stage K; request recording gained an optional metrics observer but persistence, response bodies, and existing endpoints are unchanged. All Stage A–K tests remain green after Stage L; the dashboard is a separate read-only package, so no API contract, provider, persistence, reliability, or monitoring behavior changed. All Stage A–L tests remain green after Stage M; Stage M adds deployment packaging, a demo script, a verifier, and contract tests without modifying application or dashboard runtime code. The full suite is **340 passed, 1 skipped**.

---

## 12. Design decisions

1. **One async interface.** Every adapter implements `AIProvider`; callers never import vendor-specific code.
2. **Normalized domain models.** Requests, results, usage, provider info, and health are validated before crossing component boundaries.
3. **Explicit selection, bounded chain.** The caller's provider (or the configured default) leads a fixed chain of at most three distinct providers. Secondary and fallback are deployment configuration, not caller-controlled.
4. **Vendor errors stop at the adapter.** Adapters must raise normalized errors; routes and the router never inspect vendor payloads.
5. **Safe error surface.** Error messages are sanitized, provider internals are not returned, and stack traces are not included in responses.
6. **Registry validated at startup.** Duplicate names, invalid names, empty model lists, invalid defaults, and unregistered reliability providers fail fast.
7. **Provider registration stays configuration-driven.** Admin keys protect provider inspection, but there is still no HTTP registration endpoint; allowing runtime provider creation needs more than read-only admin auth and is outside this stage.
8. **Deterministic fake output.** Local behavior is stable enough for regression, fault injection, and fallback.
9. **No hidden vendor retries.** Vendor SDK retry behavior is not used. Retry orchestration lives in `app/reliability` with a hard attempt ceiling and total-work bound.
10. **Shutdown-safe registry.** The application closes every registered provider at shutdown; the OpenAI adapter closes the HTTP client it owns and leaves injected clients to their owner.
11. **Prompt privacy.** Generation content is returned to the caller but never logged.
12. **Testable composition.** `create_app(settings, registry=...)` allows isolated provider sets; reliability sleeps and jitter are injectable.
13. **SecretStr configuration.** The OpenAI key is hidden from normal settings representations and is only materialized to build the outbound authorization header.
14. **Strict response normalization.** Missing choices, non-text content, invalid usage counters, and malformed JSON become `provider_invalid_response`; vendor totals are recomputed from validated parts.
15. **No upstream body echo.** OpenAI response bodies are never copied into public errors or logs.
16. **Direct egress by default.** The adapter-owned HTTPX client does not inherit ambient proxy variables. This avoids accidental credential interception and environment-specific proxy parsing failures; deployments that require a proxy should enforce egress at the network or container layer. (Injected test clients control their own transport.)
17. **Client errors do not fall back.** `provider_invalid_request` aborts the chain. Falling back would turn a legitimate 4xx into a misleading 200 and could hide prompt/content-policy rejections.
18. **Circuit transitions without awaits.** Breaker state changes are synchronous, so they are atomic within the event loop. A half-open circuit admits exactly one probe; concurrent calls are rejected with `provider_circuit_open`.
19. **Idempotent attempts.** Adapters are non-streaming and each attempt uses a fresh immutable request and a complete result. Retries therefore cannot duplicate or partially apply work.
20. **In-house controlled retry.** The retry manager is a small, tested implementation of exponential backoff plus bounded jitter, avoiding a new runtime dependency while retaining the same guarantees as Tenacity-style helpers.
21. **Fallback is observable.** Callers receive `requested_provider`, `providers_tried`, `retry_count`, `fallback_used`, and a normalized `fallback_reason`; fallback is never silent.
22. **Auth is deployment configuration, fail-closed in production.** Local development stays unauthenticated for convenience; production refuses to start without auth and at least one user key.
23. **Digest-only comparison.** Keys are SHA-256 hashed at construction and compared with `secrets.compare_digest`. Raw keys are never stored in manager state or logged; rate-limit keys use a truncated digest, not the token.
24. **Roles are coarse and explicit.** `anonymous`, `user`, and `admin` cover the current surface. Admin keys also generate; user keys never reach provider management.
25. **Fixed-window limiting is intentionally simple.** It is atomic per event loop and adequate for a single process. Stage G adds shared persistence, but a distributed limiter and distributed budget counters remain outside this stage.
26. **Reservation covers the maximum estimate.** The router reserves prompt estimate plus requested `max_tokens` (or the configured assumption) before contacting a provider. Settlement uses reported usage, so reservations are conservative rather than optimistic.
27. **Reservations are per attempt.** A retry or fallback reserves again, which prevents a burst of in-flight attempts from bypassing daily/monthly limits. Failed attempts release their reservation.
28. **Budget rejection aborts the chain.** Attempting a cheaper provider after a reservation failure would make spend behavior unpredictable and hide configuration errors.
29. **Money never uses floats.** Pricing and counters are `Decimal` quantized to six decimals; floats appear only at the JSON boundary.
30. **Request summary is risk-focused.** One record per successful request captures the fields required by the security requirements without prompt text, headers, keys, or upstream error bodies.
31. **One validated summary contract.** `FaultSummary` is the only structured shape returned by the fault path. It forbids extra keys, bounds text lengths, rejects non-finite temperatures, normalizes severity/unit aliases, and requires a unit only when a temperature exists.
32. **Deterministic fallback must not invent data.** The extractor reads explicit labels, explicit equipment identifiers, explicit durations, and explicit severity; otherwise the field stays `null`. Unknown and placeholder values are treated as absent.
33. **AI decoding is strict at the schema, tolerant at the envelope.** Markdown fences and surrounding prose are stripped, but JSON and `FaultSummary` validation remain strict. A schema mismatch is an observable deterministic fallback, not a guessed correction.
34. **Fallback never masks caller or policy errors.** Authentication, rate limits, budgets, unknown providers, and unsupported models keep their normalized errors. Only provider unavailability and unusable AI output trigger deterministic extraction.
35. **Business logic stays provider-independent.** The fault service depends on the router and budget interfaces, never on OpenAI payloads or adapter internals.
36. **Degraded success is explicit.** Fault responses distinguish `extraction: "provider"` from `"deterministic"`, include an `extraction_reason`, list missing fields, and preserve route metadata even when the provider chain itself failed.
37. **Async SQLAlchemy with a scoped factory.** One `AsyncEngine` and one `async_sessionmaker` live on `app.state`; repositories open one short session per operation and never share sessions across requests.
38. **Metadata-only persistence.** `request_logs` stores operational fields and normalized error codes. Prompts, completions, report text, request bodies, headers, and credentials are never written.
39. **Boundary logging.** Routes record successful and degraded work; the shared error handlers record rejected generation and fault-report requests, so `401`, `402`, `404`, `422`, and `429` are covered in one place.
40. **Persistence is best-effort.** Writes run under a bounded timeout and failures are logged as `request_log.persist_failed` without changing the API response, because analytics must not break the business path.
41. **History is admin-only and bounded.** `/api/v1/requests` requires an admin key, caps page size, and rejects reversed ranges with `422` instead of returning misleading empty pages.
42. **Readiness checks the schema.** The database probe queries `request_logs`, not just the connection, so a reachable database with a missing migration is reported as `unavailable`.
43. **Migrations own production schema.** `DATABASE_AUTO_CREATE` is a local convenience; production forbids it and requires `alembic upgrade head`, preventing unreviewed DDL in production.
44. **Secrets stay in `SecretStr`.** `DATABASE_URL` can contain a password, so it is hidden from settings representations and startup logs; only enablement, dialect, and auto-create mode are logged.
45. **Dialect-driven deployment.** SQLite with `aiosqlite` is the local default; production must use `postgresql+asyncpg`. The same metadata and migration produce both schemas.
46. **Filters are normalized to UTC.** Naive client datetimes are interpreted as UTC and all stored timestamps are timezone-aware at the boundary, avoiding SQLite/PostgreSQL comparison drift.
47. **No retention or aggregation yet.** Stage G adds durable request history only; retention jobs, dashboards, and metrics servers belong to later stages.
48. **Fault injection exists only at the test boundary.** A test provider substitutes the adapter; production has no environment flag or HTTP route that can force failures, so the matrix cannot become an attack surface.
49. **Matrix, not a collection of unit stubs.** Each fault travels through the real route, authentication, rate limiter, budget hook, timeout, retry, circuit breaker, fallback, parser/extractor, and request logger.
50. **Timeouts and circuits are exercised, not simulated.** The timeout case uses an actually hanging coroutine that must be cancelled, and the circuit case asserts both the open state and that provider calls stop.
51. **A passing scenario includes evidence.** HTTP status, normalized error, retry/fallback metadata, persisted request-log row, and absence of prompt/report/key markers are all asserted.
52. **Coverage cannot silently shrink.** A manifest test fails if a retryable fault mode is removed from or omitted by the matrix.
53. **Healthy controls are mandatory.** Valid provider output and successful generation/fault requests run beside the fault cases, proving the harness distinguishes failure from success.
54. **Version metadata is deployment configuration.** Provider/model release identifiers live in a reviewed JSON manifest, not inside adapters, so version management cannot introduce provider-specific behavior into business code.
55. **Model metadata is fail-closed at startup.** A missing manifest entry, malformed file, duplicate entry, retired configured model, or inactive default stops the application before it serves traffic; version drift is not discovered lazily per request.
56. **Lifecycle status is explicit.** `active` is normal, `deprecated` is allowed with a startup warning, and `retired` is rejected for configured models. The default model must remain active so fallback behavior cannot silently depend on an end-of-life release.
57. **Coverage follows the registry.** Every configured provider/model must be tracked. Manifest entries for unregistered providers remain visible for lifecycle planning and are marked `configured: false`.
58. **Manifest parsing is bounded and strict.** The loader limits file size, requires UTF-8 JSON, rejects unknown fields and duplicate pairs, validates provider/model/version formats, and never logs manifest contents.
59. **Version management is optional but explicit.** A blank manifest preserves existing deployments and generation contracts; enabling it fails closed. The admin endpoint reports `503 model_catalog_unavailable` rather than an empty list when the feature is off.
60. **Golden baselines target observable contracts.** Snapshots exercise the real app and compare normalized response bodies, not internal implementation details. Provider latency is removed; semantic changes are surfaced as reviewable JSON diffs.
61. **Baselines never update implicitly.** A normal regression run fails on drift; rewriting requires the dedicated `-Update` switch or environment variable. This prevents a contract regression from being accepted merely because tests ran.
62. **Regression coverage includes old and new boundaries.** Snapshots pin generation, fault extraction, errors, provider inventory, model inventory, and readiness, while unit-level model tests cover startup and authorization rules that HTTP snapshots cannot express.
63. **CI is a gate, not a deployment pipeline.** Stage J validates source and contracts with read-only permissions. It does not publish artifacts, push images, or deploy. Stage M adds local image targets and a Compose demonstration, but registry credentials, provenance, and environment promotion still belong to a separate delivery pipeline.
64. **The workflow has no secret dependency.** All gate settings are non-secret test values, OpenAI and persistence are disabled, and the workflow cannot reference repository secrets. This keeps pull-request runs safe and reproducible.
65. **Quality gates are separately named.** Compilation, linting, the full suite, the fault matrix, and the regression suite fail independently, so a red job identifies the affected boundary without reading an undifferentiated log.
66. **Baselines cannot drift silently in CI.** The workflow forces `UPDATE_REGRESSION_BASELINES=0` and then checks `git diff` for baseline files. An intentional contract change requires a reviewed baseline commit rather than an in-place rewrite.
67. **Local and hosted checks share one configuration.** `pyproject.toml` owns pytest and Ruff settings; `scripts/quality.ps1` mirrors the CI commands with the same environment values, reducing “works locally” drift.
68. **CI does not override isolated test settings.** Application settings exported globally would take precedence over some tests’ `Settings(_env_file=None, ...)` fixtures and change their expected behavior. CI therefore sets only interpreter determinism and the baseline-update lock; a clean checkout without `.env` is verified to pass the full suite.
69. **Metrics have two complementary lifetimes.** Durable summaries are computed from `request_logs`, so they survive restarts and cover historical windows. Prometheus series live only for the process lifetime and reset on restart; they are intended for scraping and alerting, not for historical audit.
70. **Percentiles are bounded.** Averages, minima, and maxima come from SQL over the full window, but p50/p95 use the newest `MONITORING_LATENCY_SAMPLE_LIMIT` durations. The response reports `sample_size` and `sample_truncated`, so an approximate percentile is never presented as a full-population result.
71. **Accepted means validated and returned.** `accepted = success + degraded`. A degraded fault report is accepted because its deterministic summary passed the same `FaultSummary` validation; an error row is not accepted. `success` excludes degraded so successful and degraded outcomes remain distinguishable.
72. **Rates have explicit denominators.** Success, degraded, accepted, and error rates divide by all requests in the window. Provider failure rate divides only by rows carrying a provider; fallback rate divides by all requests. Each field name states the outcome it measures.
73. **Cost evidence is normalized, not invoiced.** Costs come from the configured pricing table already used by budget settlement. The fake provider has no price, so its cost is zero by configuration rather than by a hidden default.
74. **Monitoring reads are bounded and fail safe.** Aggregates run under `MONITORING_QUERY_TIMEOUT_SECONDS`, sample reads are limited, windows are fixed UTC ranges, and any storage failure becomes `503 monitoring_unavailable` without affecting generation or fault-report traffic.
75. **Monitoring is an admin boundary.** Both the summary endpoint and the Prometheus exposition require an admin key. Metrics can reveal traffic structure and spend even though they contain no prompts, report text, URLs, or credentials.
76. **Label cardinality is controlled.** Provider labels come from recorded request metadata, and unknown client-supplied provider names collapse to `unconfigured`; fallback reasons are normalized and truncated. A caller cannot create unbounded time series.
77. **Metrics observation is isolated from persistence.** The request-log service notifies an optional observer before attempting a database write, and observer failures are logged and swallowed. Metrics therefore keep working when persistence is disabled, slow, or broken, and a metrics bug cannot fail an API request.
78. **The dashboard is a separate process, not an API module.** It runs under Streamlit, reads its own `DASHBOARD_*` environment, and depends only on the public admin HTTP surface. It imports nothing from `app.*`, so provider, persistence, and monitoring internals cannot leak into presentation code, and the API process does not grow a UI dependency at runtime.
79. **Read-only is enforced by the client, not the UI.** `ApiClient` exposes only `GET` calls. There is no method to generate, mutate providers, change budgets, or invoke fault injection, so a future view cannot accidentally gain a write path without adding one deliberately.
80. **The dashboard validates its own boundary.** API responses are re-validated with dashboard-owned Pydantic models (`extra="ignore"`), not trusted as dictionaries. Unknown fields are ignored so additive API changes remain compatible, while missing or malformed required fields become a visible typed error.
81. **Outbound requests are deliberately constrained.** Base URLs must be plain origins; credentials, paths, queries, and fragments are rejected. The client disables redirects (a redirect could forward the admin key to another host), disables ambient proxy inheritance (environment proxies could intercept credentials), and bounds every request with a timeout.
82. **Admin failure is safe and legible.** `DashboardApiError` carries a normalized code, a sanitized message, an optional status, and retryability. Messages are stripped of control characters and truncated; response bodies, URLs, keys, and tracebacks are never rendered. The UI maps authentication, authorization, rate-limit, persistence, catalog, and monitoring unavailability to specific guidance.
83. **Prometheus text is untrusted input.** The parser caps total size, line length, label count, and label-value length; skips malformed lines; rejects non-finite values; and decodes escaped label content before display. API and exposition text is rendered through `st.code`/`st.dataframe`, never `st.markdown`, so upstream strings cannot become HTML or script.
84. **The admin key is session-scoped.** `DASHBOARD_ADMIN_API_KEY` is preferred and stored as a `SecretStr`. A sidebar-entered key stays in Streamlit session memory, is masked, is never put in URLs or query strings, and is never logged. The dashboard does not persist it to disk or browser storage.
85. **Health checks gate the UI.** `/health/live` and `/health/ready` are called on each rerun. An unreachable API stops with a concrete start command; a reachable but degraded API renders a warning with the failing checks. Empty tables are therefore never mistaken for healthy zero traffic.
86. **Provider health is explicit.** Listing providers is read-only; the provider-side health call runs only when the operator presses **Check health**, so opening the page does not probe providers or add latency to a view load.
87. **Dashboard tests drive the real UI headlessly.** Streamlit `AppTest` executes `dashboard/app.py` against a local Uvicorn API fixture, covering all five views, the refresh path, error states, and the admin boundary. This proves rendering and client integration without a browser grid or any external service.
88. **One Dockerfile, shared runtime, two deployables.** A single builder stage installs the project into `/opt/venv`; the shared runtime stage establishes the non-root user and asset layout; `api` and `dashboard` add only their own entry command. This keeps the two images in lockstep and avoids duplicating dependency installation.
89. **The runtime image contains no compiler.** Build tooling stays in the disposable builder stage. A smaller runtime reduces attack surface and image size; if a dependency later needs native compilation, it is compiled once in the builder rather than added to the deployed image.
90. **The final image runs unprivileged.** UID/GID 10001 owns no application files it needs to modify, the root filesystem is read-only, only `/tmp` is writable via a bounded tmpfs, all capabilities are dropped, and `no-new-privileges` blocks setuid escalation. `init: true` supplies a PID 1 that forwards signals and reaps children.
91. **Migrations are an entrypoint responsibility.** The API container runs `alembic upgrade head` before `exec`ing Uvicorn, with a bounded retry loop for database startup races. Production still forbids `DATABASE_AUTO_CREATE`; schema changes remain reviewed migration files, and a migration failure stops the container instead of serving against an unknown schema.
92. **Startup order is health-gated.** Compose waits for PostgreSQL's `pg_isready`, the API's readiness endpoint, and the dashboard's `_stcore/health` before starting the next service. A dependency that is merely "running" is not treated as usable.
93. **Required secrets fail closed at the Compose boundary.** `${VAR:?message}` prevents startup when a database password or API key is missing. The demo script additionally rejects placeholder values, validates key lengths and non-equality, and generates URL-safe random values so they can be embedded in a database URL without escaping.
94. **Network segmentation is explicit.** PostgreSQL is attached only to an `internal: true` backend network, so it has no outbound path and no published port. The API joins backend and frontend; the dashboard joins only frontend. Both published ports bind to `127.0.0.1`.
95. **Production configuration is asserted, not implied.** Compose sets `ENVIRONMENT=production`, `DATABASE_AUTO_CREATE=false`, `DATABASE_ECHO=false`, `SECURITY_REQUIRE_AUTH=true`, and non-empty user/admin keys. The application's own validators remain the authority; Compose cannot accidentally run a production-labeled container with development defaults.
96. **Dashboard credentials mirror a single admin key.** The Compose topology maps `SECURITY_ADMIN_API_KEYS` into `DASHBOARD_ADMIN_API_KEY` because it assumes one admin key. Multi-admin deployments should supply a dedicated single key through a Compose override; the limitation is documented rather than hidden behind implicit key selection.
97. **Verification is black-box and non-leaking.** The E2E verifier uses only the public HTTP surface, disables ambient proxies and redirects, requires the database readiness check, and injects a per-run marker to prove that request content never reaches metrics or history. It prints aggregate results, never keys or prompts.
98. **The demo stack is ephemeral by default.** `scripts\demo.ps1` generates secrets, starts the stack, verifies it, and tears it down in `finally`, including volumes on `-Reset`. `-KeepRunning` is the explicit opt-in for inspection. Failure diagnostics are bounded log tails, not secret dumps. The generated `.env.docker` remains on disk, git-ignored, so the same keys are reused on the next run; delete it to rotate them.
99. **Deployment contracts are tested where Docker cannot run.** Because the implementation host has no Docker daemon, the suite validates the Dockerfile, Compose topology, entrypoint, ignore rules, demo script, and verifier by contract, and runs `docker compose config` only when a Docker CLI is present. The native E2E run is reported as native, not as a container run; no image-build success is claimed without an executed build.

Stage A safeguards remain: factory-first construction, typed configuration, production documentation lockdown, no header/body access logging, one logging handler, and response models everywhere.

---

## 13. Troubleshooting

### `Activate.ps1 cannot be loaded because running scripts is disabled`

Run for the current PowerShell session only:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### `py -3.14` is not recognized

```powershell
py -0p
```

Install Python 3.14 with the Python launcher if no 3.14 entry appears.

### Startup fails with `DEFAULT_PROVIDER ... is not registered`

Use a registered provider name or register the configured provider before startup:

```powershell
$env:DEFAULT_PROVIDER = "fake"
```

### Startup fails with `DEFAULT_PROVIDER 'openai' requires OPENAI_API_KEY`

Set a non-blank key in the process environment or `.env`, or switch the default back to `fake`:

```powershell
$env:OPENAI_API_KEY = "sk-..."
$env:DEFAULT_PROVIDER = "openai"
```

### OpenAI health reports `unavailable`

Check that the key is valid, `OPENAI_BASE_URL` points to the intended endpoint, and the process can reach that endpoint. The adapter does not inherit proxy environment variables; use network-level egress controls if a proxy is required.

### OpenAI returns `provider_invalid_request`

The requested model must appear in `OPENAI_MODELS`. Stage C does not forward arbitrary model names.

### Startup fails with `fake_provider_default_model must be one of fake_provider_models`

Choose a default that appears in the model list:

```powershell
$env:FAKE_PROVIDER_MODELS = "fake-small,fake-large"
$env:FAKE_PROVIDER_DEFAULT_MODEL = "fake-small"
```

### Startup fails with `Reliability provider ... is not registered`

The configured secondary or fallback provider does not exist in the active registry. Register it, or clear the setting:

```powershell
$env:RELIABILITY_SECONDARY_PROVIDER = ""
$env:RELIABILITY_FALLBACK_PROVIDER = "fake"
```

### Responses unexpectedly come from `fake`

The fallback engaged. Inspect the response metadata (`fallback_used`, `fallback_reason`, `providers_tried`) and the provider health endpoint's `circuit` object. To disable fallback during diagnosis:

```powershell
$env:RELIABILITY_FALLBACK_PROVIDER = ""
```

### Provider health shows `"state": "open"`

The provider exceeded the failure threshold. Calls are rejected until `RELIABILITY_CIRCUIT_RECOVERY_SECONDS` elapses, then exactly one probe is allowed. Investigate the upstream error code in the route logs before lowering the threshold or recovery time.

### Retries make failures slow

Tune the attempt and backoff settings. Delays are capped by `RELIABILITY_BACKOFF_MAX_SECONDS`; `RELIABILITY_MAX_ATTEMPTS=1` disables retries while keeping fallback:

```powershell
$env:RELIABILITY_MAX_ATTEMPTS = "1"
$env:RELIABILITY_BACKOFF_BASE_SECONDS = "0.1"
```

### Startup fails with `security_require_auth must be enabled in production`

Production is fail-closed. Enable auth and provide at least one user key:

```powershell
$env:SECURITY_REQUIRE_AUTH = "true"
$env:SECURITY_API_KEYS = "user-key-0123456789abcdef"
```

### Startup fails with `security_api_keys must contain at least one key`

Auth is enabled but no key is configured. Add one, or disable auth outside production:

```powershell
$env:SECURITY_REQUIRE_AUTH = "false"
```

### Requests return `401 authentication_required`

Send `Authorization: Bearer <key>` using a key from `SECURITY_API_KEYS` or `SECURITY_ADMIN_API_KEYS`. The scheme must be exactly `Bearer`; the key must be 16–512 characters with no whitespace.

### `/api/v1/providers` returns `403 permission_denied`

Provider management requires an admin key. Use a key from `SECURITY_ADMIN_API_KEYS`; user keys are limited to generation and system/health endpoints.

### Requests return `429 rate_limit_exceeded`

The identity or client address exhausted its fixed window. Wait for `Retry-After` seconds, raise `SECURITY_RATE_LIMIT_REQUESTS`, or set it to `0` to disable limiting in development.

### Requests return `402 budget_exceeded`

The estimated per-request cost or the daily/monthly total exceeded its limit. Raise the corresponding `BUDGET_*` limit, lower `max_tokens`, choose a cheaper provider, or adjust `BUDGET_PROVIDER_PRICING`. Setting `BUDGET_ENFORCEMENT_ENABLED=false` stops rejection but keeps spend tracking.

### Startup warns `budget.pricing.missing`

A registered provider has no `BUDGET_PROVIDER_PRICING` entry and is priced at zero. Add an entry if the provider bills per token.

### Fault reports always return `extraction: "deterministic"` with `ai_invalid_json`

The default fake provider echoes text rather than JSON; that is expected. To exercise the AI path, point `DEFAULT_PROVIDER` at a real or compatible model that follows the strict JSON prompt. Deterministic extraction remains active as the safety path.

### Fault reports return `ai_invalid_schema`

The model produced JSON that violates the contract: an unknown field, a severity outside `low|medium|high|critical`, a non-numeric temperature, or a unit without a temperature. Tighten the prompt/model choice; the service will not loosen validation or guess values.

### Fault summary fields are `null`

The extractor only reports explicit values. If the report omits a machine, temperature, downtime, or action, the field stays unknown and is listed in `missing_fields`. This is intentional; no values are inferred.

### Fault report returns `422`

The `report` field must be 10–8000 characters after trimming, and the request forbids unknown fields. Send `{"report": "..."}`.

### `/health/ready` reports `database: "unavailable"`

The connection succeeded but `request_logs` is missing or unreadable. With `DATABASE_AUTO_CREATE=false`, apply the schema:

```powershell
.\.venv\Scripts\alembic.exe upgrade head
```

The readiness probe deliberately checks the table, not just `SELECT 1`, so a missing migration cannot report ready.

### Request history returns `503 persistence_unavailable`

`DATABASE_ENABLED=true` but the database cannot be reached, the query timed out, or the schema is missing. Check the DSN, confirm the database server is running, and apply migrations. The API deliberately does not serve an empty history when the store is unavailable.

### Request history returns `404 request_log_not_found`

The record ID does not exist. IDs are assigned at insert and start at `1`.

### Request history returns `422 invalid_request_filter`

`since` is later than `until`, `limit` is outside `1–200`, or a `kind`/`status` value is not one of the documented literals. `since`/`until` accept ISO-8601; naive values are interpreted as UTC.

### Startup fails with `database_url must use ...`

`DATABASE_URL` must use `sqlite+aiosqlite://` or `postgresql+asyncpg://`. Plain `sqlite://` and `postgresql://` are normalized automatically; other drivers are rejected because the async stack does not support them.

### Startup fails with `database_auto_create must be disabled in production`

Production schema changes must be reviewed migrations. Set `DATABASE_AUTO_CREATE=false` and run `alembic upgrade head`.

### Startup fails with `database_echo must be disabled in production`

SQL echo prints every statement, including parameter values, to logs. Set `DATABASE_ECHO=false` in production.

### SQLite reports `database is locked`

SQLite allows one writer at a time. Keep `DATABASE_WRITE_TIMEOUT_SECONDS` low, avoid reading the file with external tools while the server is running, and move to PostgreSQL for multi-process deployments. Persistence failures are logged but never fail the API request.

### Request history is empty

Confirm `DATABASE_ENABLED=true`, then check the server log for `request_log.persist_failed`. Only `/generate` and `/fault-reports/summarize` requests are persisted, and writes are intentionally best-effort.

### `alembic` is not recognized

Use the virtual environment executable and run from the repository root so `alembic.ini` and the `app` package are found:

```powershell
.\.venv\Scripts\alembic.exe upgrade head
```

### Alembic cannot connect to PostgreSQL

Start from a reachable host and confirm the password is URL-encoded if it contains special characters. Production requires `postgresql+asyncpg://`; `asyncpg` is installed by the project dependencies. Generate SQL without a connection for review:

```powershell
.\.venv\Scripts\alembic.exe upgrade head --sql
```

### Fault matrix collects zero tests

Run the runner from the repository root. It selects the `fault_matrix` marker and the matrix file explicitly:

```powershell
.\scripts\fault-matrix.ps1
```

An `Unknown pytest.mark.fault_matrix` warning means `pyproject.toml` is missing the marker registration; use the repository configuration rather than an external pytest config.

### Fault matrix appears to hang

The timeout scenario injects a provider that sleeps far longer than the configured deadline. A hang means timeout cancellation or retry bounding regressed; do not increase the injected sleep or timeout to hide it. Run the single scenario for a bounded failure:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_fault_matrix.py::test_timeout_fault_is_bounded_and_cancelled
```

### Startup fails with `Model version manifest ...`

The path in `MODEL_VERSION_MANIFEST` must point to a UTF-8 `.json` file at most 256 KiB. Relative paths are resolved from the process working directory, so run from the repository root or configure an absolute path. Malformed JSON, unknown fields, duplicate provider/model pairs, and invalid provider/model/version values all fail startup with a safe message.

### Startup fails with `Configured model ... has no entry in the model version manifest`

Every model declared by every configured provider must appear exactly once in the manifest. This commonly happens after adding a model to `FAKE_PROVIDER_MODELS` or `OPENAI_MODELS`, or after registering the OpenAI provider and enabling its default model list. Add the release entry to `config/model_versions.json`, or remove the model from provider configuration.

### Startup fails with `retired` or `default model ... must be active`

A configured model with `status: "retired"` cannot be used. A `deprecated` non-default model starts with a warning, but the selected default must remain `active`. Change the status only when the model is intentionally supported again, or select/configure an active model.

### `/api/v1/model-versions` returns `503 model_catalog_unavailable`

The catalog is optional. Set `MODEL_VERSION_MANIFEST` to a valid manifest and restart the service. A blank value is intentional and leaves generation unaffected.

### Regression baseline changed or missing

A normal Stage I run fails when an HTTP contract or model inventory differs from `tests\regression\baselines\*.json`. Inspect the failure and the baseline before changing anything. If the contract change is intentional, run the explicit update workflow and review the rewritten files:

```powershell
.\scripts\regression.ps1 -Update
# Review tests\regression\baselines\*.json.
.\scripts\regression.ps1
```

Never set `UPDATE_REGRESSION_BASELINES=1` in CI or an ordinary test run. If the runner reports that no tests were collected, run it from the repository root and keep the `regression` marker registration in `pyproject.toml`.

### CI fails at `Verify regression baselines are unchanged`

The test run modified a file under `tests/regression/baselines`, or the baseline diff was not committed. Review the contract change locally, update baselines only with `.\scripts\regression.ps1 -Update`, inspect the JSON diff, and commit the baseline with the contract change. Do not set `UPDATE_REGRESSION_BASELINES=1` in the workflow.

### `ruff` is not recognized

Install the development extras again:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

### The GitHub workflow does not start

The workflow must be committed at `.github/workflows/ci.yml` in a GitHub repository. This local folder is not currently a Git repository, so a hosted run cannot be claimed from the workspace. Confirm the file path and workflow syntax after pushing; manual runs are available through `workflow_dispatch`.

### `scripts/quality.ps1` cannot be loaded

PowerShell script execution is disabled on the machine. Allow local scripts for the current process only:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\quality.ps1
```

### Monitoring summary returns `503 monitoring_unavailable`

Either persistence is disabled (`DATABASE_ENABLED=false`, so no durable summary exists), the `request_logs` table is missing, the query exceeded `MONITORING_QUERY_TIMEOUT_SECONDS`, or the database is unreachable. Check `/health/ready`, run `alembic upgrade head` for the configured database, or use `/api/v1/monitoring/metrics`, which stays available without persistence. The API response never includes SQL or connection details.

### Monitoring endpoints return `401` or `403`

Both `/api/v1/monitoring/summary` and `/api/v1/monitoring/metrics` are admin-only. Send `Authorization: Bearer <admin key>`; a valid user key still receives `403 permission_denied`.

### Summary reports `"sample_truncated": true`

More requests occurred in the window than `MONITORING_LATENCY_SAMPLE_LIMIT`. Averages, minima, and maxima still cover the full window; p50/p95 describe the newest configured number of requests. Raise the limit deliberately if a wider percentile sample is required.

### Cost is zero for the fake provider

The fake provider has no price in the configured pricing table, so its requests settle at `$0`. This is expected. Configure prices for the providers you bill against; an unknown-priced paid provider logs `budget.pricing.missing` and also settles at zero.

### Prometheus counters reset after restart

`/api/v1/monitoring/metrics` exposes process-local counters and histograms. A restart starts new series at zero, and multiple workers keep separate series unless your scraper aggregates them. Use `/api/v1/monitoring/summary` for durable, cross-restart evidence.

### `ModuleNotFoundError: prometheus_client`

Stage K adds a runtime dependency. Reinstall the project environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

### `ModuleNotFoundError: streamlit`

Stage L adds the Streamlit runtime dependency. Reinstall the project environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

### Dashboard shows `Cannot reach the AI Adapter API`

The API is not listening at `DASHBOARD_API_BASE_URL`, or it rejected the connection. Start the API (`.\scripts\run-dev.ps1`), confirm its host/port, then use Refresh. Health paths are appended to the origin, and API paths use `DASHBOARD_API_PREFIX`; a base URL that already contains `/api/v1` is rejected as a path-bearing origin. The dashboard never falls back to a different host.

### Dashboard returns `permission_denied` or `authentication_required`

The dashboard calls admin-only endpoints. `DASHBOARD_ADMIN_API_KEY` (or the sidebar key) must be an admin key from `SECURITY_ADMIN_API_KEYS`, not a user key. A user key yields `403 permission_denied`; a missing or malformed key yields `401 authentication_required`. Re-enter the key and Refresh.

### Dashboard warns about plain HTTP

The configured API origin is remote and uses `http://`, so the admin key would cross the network unencrypted. Use an HTTPS origin or a local tunnel, or bind both processes to loopback for development. The warning does not block local testing.

### Dashboard port 8501 is already in use

```powershell
.\scripts\dashboard.ps1 -Port 8502
```

Or stop the other Streamlit process. The API and dashboard must use different ports.

### Dashboard Tokens or cost are zero

Process metrics start at zero after an API restart, so a freshly restarted API reports zero until new requests complete. Cost is also zero for the fake provider because its configured price is zero; use the Overview window totals for durable data and a priced provider to see nonzero cost.

### Dashboard says the API is not ready

The API is reachable but `/health/ready` reports a failing dependency, typically `database: unavailable` (missing migration or unreachable database) or `models: unavailable`. The banner lists the failing checks. Fix the API dependency; the dashboard intentionally shows the warning instead of hiding degraded data.

### Dashboard reports `api_timeout`, `api_unreachable`, or `502`

`api_timeout` means the API exceeded `DASHBOARD_REQUEST_TIMEOUT_SECONDS`; `api_unreachable` means a transport failure. A `502` or `504` with a non-JSON body is shown as a bounded `HTTP <status>` message rather than raw HTML. Check the API process and network path, then Refresh; raise the timeout only if the API is legitimately slower.

### Dashboard `Page not found`

Both processes are running, but the API origin or prefix is wrong. `DASHBOARD_API_BASE_URL` must be only the origin (`http://127.0.0.1:8000`), and `DASHBOARD_API_PREFIX` must match the API's `API_PREFIX` (default `/api/v1`). Health checks use the origin root; other calls use the prefix.

### `docker` is not recognized or the demo stops before building

Install Docker Desktop with Compose v2 and start the Docker engine, then reopen PowerShell. The demo checks for both the Docker CLI and `docker compose version`; it refuses to continue instead of starting a partial stack. On Windows, WSL 2 is normally required by Docker Desktop. This project's implementation host had no Docker CLI, so the container build was not executed there.

### Compose reports `POSTGRES_PASSWORD must be set` or another required secret

Create `.env.docker` from `.env.docker.example` and replace every `replace-with*` value, or let `scripts\demo.ps1` generate the file. The `${VAR:?...}` expressions are intentional fail-closed guards. Do not place real secrets in `compose.yaml`, source files, shell history, or test fixtures.

### Compose reports `port is already allocated`

Ports `8000` (API) and `8501` (dashboard) must be free. Stop the conflicting process or change the published port in `compose.yaml`. Both are published on loopback only; changing the container port also requires changing the corresponding `DASHBOARD_API_BASE_URL` only if the dashboard-to-API port changes, not the browser-facing mapping.

### The API container exits while running migrations

Read `docker compose --env-file .env.docker logs api`. The entrypoint retries `alembic upgrade head` ten times at two-second intervals, then exits nonzero. Common causes are an incorrect `DATABASE_URL`, PostgreSQL not yet healthy, a revision error, or a password with URL-reserved characters. Use a URL-safe password (the demo does) or URL-encode it in the database URL.

### `database is locked` or a persistence timeout in a container

The Compose stack uses PostgreSQL, so SQLite locking should not occur there. If you override `DATABASE_URL` with SQLite on a container filesystem, remember that the root filesystem is read-only; mount a writable volume for the database file. PostgreSQL on the internal `backend` network has no published port by design.

### The dashboard container cannot reach the API

Inside Compose the dashboard must use `DASHBOARD_API_BASE_URL=http://api:8000`, not `127.0.0.1`, because loopback inside the dashboard container is the dashboard itself. Check that both services are on the `frontend` network and that the API health check is passing before the dashboard starts. A remote plain-HTTP warning is expected for the in-network `http://api:8000` origin.

### Production validation refuses the container configuration

The API container intentionally runs `ENVIRONMENT=production`, so it requires PostgreSQL, `DATABASE_AUTO_CREATE=false`, `DATABASE_ECHO=false`, authentication enabled, and at least one user key. Missing or overlapping keys, SQLite, auto-create, or SQL echo will stop startup with a typed validation error. Do not weaken these settings to make a demo start; fix the Compose values.

### The image build fails while installing dependencies

The builder needs network access to PyPI and a C toolchain for native wheels; the Dockerfile installs `build-essential` in the builder only. Behind a proxy, configure Docker's daemon proxy settings rather than baking proxy credentials into the image. If the base image tag moves, pin a reviewed `python:3.14-slim` digest in the image pipeline.

### A `.dockerignore` change unexpectedly removed a needed file

The context intentionally excludes `.env*`, tests, local data, documentation, and most scripts. The only script copied by the `api` target is `scripts/docker-entrypoint.sh`. If you add a runtime asset, add it explicitly to both the Dockerfile `COPY` step and any relevant ignore exceptions, then rerun `tests/test_deployment.py`.

### `docker compose config` is skipped in tests

The conditional test skips when the Docker CLI or Compose v2 is not installed. That is expected on the implementation host. On a Docker-capable host it executes and validates interpolation and YAML structure; it does not start containers.

### Port already in use

```powershell
.\scripts\run-dev.ps1 -Port 8123
```

### `ModuleNotFoundError: app`

```powershell
pip install -e ".[dev]"
```

Or run with the explicit interpreter:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app
```

### Tests report an import error for `httpx2`

```powershell
pip install -e ".[dev]"
```

---

## 14. Stage A completion checklist

- [x] Stage A scope documented
- [x] Complete foundation folder structure
- [x] Typed, validated settings with `.env` support
- [x] Structured JSON logging with UTC timestamps
- [x] Recursive credential redaction with tests
- [x] Request-ID validation, generation, and response echo
- [x] Access logging without headers, bodies, or query strings
- [x] Liveness and readiness endpoints
- [x] Non-secret system metadata endpoint
- [x] Versioned API prefix
- [x] Production docs/OpenAPI lockdown
- [x] Application factory with isolated test configuration
- [x] PowerShell setup, run, and test scripts
- [x] `.env.example` and `.gitignore`
- [x] Stage A test gate: **26 passed at that stage**
- [x] Uvicorn server executed and endpoints verified live
- [x] Structured logs inspected at runtime
- [x] README updated

---

## 15. Stage B completion checklist

- [x] Async provider interface defined with normalized request, result, usage, info, and health models
- [x] Provider error taxonomy defined
- [x] Provider-specific errors translated at the adapter boundary
- [x] Provider registry with unique-name and model configuration validation
- [x] Provider listing, inspection, and availability endpoints
- [x] Deterministic local fake provider
- [x] Configurable fake provider models and default model
- [x] Explicit provider selection and configured default provider
- [x] Provider switching verified with two registered fake adapters
- [x] One normalized generation endpoint
- [x] Default model resolution
- [x] Token usage and latency normalized
- [x] Safe provider error responses with request IDs
- [x] Provider error messages sanitized in responses and logs
- [x] Prompt content excluded from logs
- [x] Registry shutdown closes all providers
- [x] Stage A regression suite still passes
- [x] Full suite executed successfully: **60 passed**
- [x] Live provider listing, health, generation, and errors verified
- [x] OpenAPI includes all Stage B endpoints
- [x] README updated

**Stage B is complete.**

---

## 16. Stage C completion checklist

- [x] Typed OpenAI settings for key, base URL, model list, default model, and timeout
- [x] API key read from environment/`.env` only and held as `SecretStr`
- [x] OpenAI provider registered conditionally when a non-blank key exists
- [x] `DEFAULT_PROVIDER=openai` rejects startup when no key is configured
- [x] Async HTTPX adapter for `/chat/completions`
- [x] Bearer authorization built per request and never logged or returned
- [x] Normalized chat payload: model, messages, temperature, optional max tokens
- [x] Normalized result: provider, model, content, usage, finish reason, latency
- [x] OpenAI finish reasons `stop`, `length`, and `content_filter` mapped
- [x] Token usage validated and total recomputed from parts
- [x] HTTP 401/403, 400/404/422, 429, 5xx, timeout, transport, and malformed payload failures normalized
- [x] Upstream error bodies excluded from public messages and logs
- [x] Bounded `/models` health check with healthy/degraded/unavailable states
- [x] Provider HTTP client released at application shutdown
- [x] Mock-transport tests cover payload, headers, mapping, failures, health, factory, and API integration
- [x] Secret and prompt content asserted absent from logs in API tests
- [x] Live verification script provided for key-enabled environments
- [x] Stage A and Stage B suites remain green
- [x] Full suite executed successfully: **110 passed**
- [x] Local runtime checks verified provider registration with and without a key, plus failure handling without any paid request
- [x] README and `.env.example` updated

**Stage C is complete.**

---

## 17. Stage D completion checklist

- [x] Typed `RELIABILITY_*` settings with range, name, and backoff validation
- [x] Per-attempt request timeout enforced above every adapter
- [x] Timeout expiry normalized to retryable `provider_timeout`
- [x] Bounded retry manager with hard attempt ceiling
- [x] Exponential backoff with configurable cap and jitter
- [x] Non-retryable errors stop retry immediately
- [x] Per-provider circuit breaker with closed/open/half-open states
- [x] Failure threshold and recovery window configuration
- [x] Single half-open probe; concurrent probe rejection
- [x] Circuit state exposed in provider health
- [x] Secondary-provider switching
- [x] Deterministic local fallback through the registered fake provider
- [x] Model remapping when a fallback provider lacks the requested model
- [x] Total work bounded by attempts × chain length; no infinite loops
- [x] Invalid client requests abort the chain instead of falling back
- [x] Provider identity mismatch treated as invalid response and circuit failure
- [x] Idempotent attempt construction with complete result validation
- [x] `provider_circuit_open` added to the normalized taxonomy and HTTP mapping
- [x] Generation response reports `requested_provider`, `providers_tried`, `retry_count`, `fallback_used`, `fallback_reason`
- [x] Startup rejects unregistered secondary/fallback providers
- [x] Retry/routing logs carry codes and attempt metadata but no prompts, headers, or error text
- [x] Stage A, B, and C suites remain green
- [x] Full suite executed successfully: **140 passed**
- [x] Live verification: retry → circuit open → deterministic fallback, exhausted-chain 503, startup validation, zero key/prompt log leakage
- [x] README and `.env.example` updated

**Stage D is complete.**

---

## 18. Stage E completion checklist

- [x] Typed `SECURITY_*` settings with key-list, overlap, and rate-limit validation
- [x] Typed `BUDGET_*` settings with decimal limits, provider pricing, and limit ordering
- [x] Production refuses to start without authentication and a user key
- [x] Bearer-key authentication with digest-only storage and constant-time comparison
- [x] User and admin roles; provider management restricted to admins
- [x] Missing, malformed, and invalid credentials return `401` with `WWW-Authenticate: Bearer`
- [x] Non-admin access to provider management returns `403`
- [x] Atomic fixed-window rate limiting per key or client address
- [x] `429` responses include `Retry-After` and `X-RateLimit-*` headers
- [x] Successful responses expose `X-RateLimit-Limit` and `X-RateLimit-Remaining`
- [x] Provider-specific pricing in USD per million tokens
- [x] Deterministic prompt-token estimation and Decimal cost quantization
- [x] Pre-call reservation for every attempt, including in-flight concurrency
- [x] Settlement with reported usage; release on failure; settlement on identity mismatch
- [x] Per-request, daily, and monthly limits with `402 budget_exceeded`
- [x] Daily and monthly counter rollover
- [x] Enforcement can be disabled while spend tracking continues
- [x] Budget rejection aborts the chain without falling back
- [x] `cost_usd` reported in generation responses
- [x] `request.summary` log records the required operational fields without prompt or key content
- [x] Access log and error handling remain body/header safe; application errors map to status/headers
- [x] Existing provider routes and generation contracts preserved
- [x] Stage A–D suites remain green
- [x] Full suite executed successfully: **172 passed**
- [x] Live verification: 401, 403, admin access, 200 with rate headers, 429 with `Retry-After`, 402 per-request rejection, zero key/prompt log leakage
- [x] README, `.env.example`, and `.env` updated

**Stage E is complete.**

---

## 19. Stage F completion checklist

- [x] Fault-report endpoint accepts validated report text plus optional provider/model selection
- [x] Six required data fields plus temperature unit defined in one validated Pydantic contract
- [x] Output rejects unknown keys, invalid severities, non-finite temperatures, and orphan units
- [x] Text fields bounded and whitespace-normalized; aliases normalized
- [x] Strict AI JSON decoding tolerates fences and surrounding prose
- [x] Invalid JSON and schema-invalid AI output are detected explicitly
- [x] Provider success returns `extraction: "provider"`
- [x] Exhausted provider chain and unusable AI output fall back to deterministic extraction
- [x] Empty AI summaries are replaced when the report contains extractable data
- [x] Labeled and prose reports handled deterministically
- [x] Placeholder/unknown values remain `null`; `missing_fields` reports them
- [x] No temperature conversion, inference, or invented field values
- [x] Unknown providers, unsupported models, auth, rate-limit, and budget errors are not masked by fallback
- [x] Provider route metadata preserved on the deterministic recovery path
- [x] Token usage, cost, retry, fallback, and extraction metadata reported
- [x] `FAULT_REPORT_MAX_TOKENS` bounded configuration added to `.env` and `.env.example`
- [x] `fault_report.summary` log includes required operational fields and no report content, keys, or headers
- [x] Existing generation, provider, reliability, security, and budget behavior preserved
- [x] Stage A–E suites remain green
- [x] Full suite executed successfully: **201 passed**
- [x] Live verification: provider-mode success via a local OpenAI-compatible stub, fake-provider deterministic extraction, unreachable-provider deterministic recovery, 422 validation, 404 unknown provider, zero key/report log leakage
- [x] README, `.env.example`, and `.env` updated

**Stage F is complete.**

---

## 20. Stage G completion checklist

- [x] Async SQLAlchemy 2.x engine/session factory with SQLite (`aiosqlite`) and PostgreSQL (`asyncpg`) dialects
- [x] Typed `DATABASE_*` settings, `SecretStr` DSN, driver normalization, and bounded pool/timeout values
- [x] Production refuses SQLite, auto-create, and SQL echo
- [x] `request_logs` schema with naming-convention constraints and query indexes
- [x] Alembic async environment with offline `--sql` support and one initial migration
- [x] Repository, service, and factory layers separated from routes
- [x] Generation success rows persist required fields: request ID, timestamp, provider/model, duration, tokens, cost, retry count, fallback status, final status
- [x] Fault-report rows persist extraction mode, reason, and missing-field count; deterministic output is `degraded`
- [x] Rejected `/generate` and `/fault-reports/summarize` requests persist normalized error code and HTTP status for `401`, `402`, `404`, `422`, and `429`
- [x] No prompt, completion, report, body, header, or credential is persisted or logged
- [x] Bounded write timeout; persistence failure is logged safely and never changes the API response
- [x] Admin-only request history with kind/status/provider/time filters, pagination, and detail lookup
- [x] Invalid filters return `422`; missing records return `404`; unavailable persistence returns `503`
- [x] Readiness includes a schema-aware database probe
- [x] Database initialization failures stop startup with a dialect-only log
- [x] Shutdown disposes the engine after providers close
- [x] Existing Stage A–F contracts preserved; database disabled by default outside persistence tests
- [x] Stage A–F suites remain green
- [x] Full suite executed successfully: **217 passed**
- [x] Live SQLite verification: 4 rows (generation success, deterministic degraded fault, `404`, `422`), admin history filters, readiness `database: "ok"`, zero prompt/key leakage
- [x] Offline PostgreSQL DDL verified (`SERIAL`, `TIMESTAMP WITH TIME ZONE`, `NUMERIC(14,6)`, `JSON`, indexes); no live PostgreSQL server was contacted
- [x] README, `.env.example`, and `.env` updated

**Stage G is complete.**

---

## 21. Stage H completion checklist

- [x] Test-only fault-injecting provider; no production env flag, endpoint, or admin operation enables faults
- [x] Matrix runs through the real app factory, authentication, rate limiter, budget hook, router, timeout, retry, circuit breaker, fallback, parser/extractor, and persistence
- [x] Six retryable faults covered: timeout, rate limit, server error, unavailable, invalid response, wrong provider identity
- [x] Each retryable fault exercised with generation exhaustion, generation fallback recovery, and deterministic fault-report degradation
- [x] Terminal invalid-request fault stops the chain and is not masked by fallback or extraction
- [x] Provider authentication failure follows retry/fallback policy
- [x] Unknown provider returns `404` without a provider call or extraction
- [x] Output faults distinguish invalid JSON, schema-invalid JSON, empty summary, and valid provider output
- [x] Timeout case uses a real hanging coroutine and asserts bounded completion
- [x] Circuit threshold opens, records metadata, and suppresses further provider calls
- [x] Missing authentication and rate-limit admission faults never reach the provider
- [x] Fault outcomes are verified in admin request history
- [x] Prompt, report, bearer key, and `sk-` secret markers absent from responses, logs, and persistence
- [x] Healthy generation and fault-report controls remain green
- [x] Manifest test fails if a retryable fault mode is omitted
- [x] Dedicated `fault_matrix` pytest marker and `scripts/fault-matrix.ps1` runner
- [x] Stage A–G suites remain green
- [x] Fault matrix executed successfully: **31 passed**
- [x] Full suite executed successfully: **248 passed**
- [x] No external provider, network, or PostgreSQL dependency in the matrix
- [x] README updated

**Stage H is complete.**

---

## 22. Stage I completion checklist

- [x] Bounded UTF-8 JSON model-version manifest with schema version, strict fields, and unique provider/model pairs
- [x] Immutable catalog with deterministic ordering and provider/model lookup
- [x] Startup fail-closed validation: missing/malformed/oversized manifest, duplicate entries, missing configured models, retired models, and inactive defaults
- [x] `active` / `deprecated` / `retired` lifecycle policy with warning for deprecated non-default models
- [x] Shipped `config/model_versions.json` covers the default fake configuration and records OpenAI snapshots
- [x] Admin-only `GET /api/v1/model-versions` with `configured` flags and explicit `503 model_catalog_unavailable` when disabled
- [x] `/health/ready` reports `models: ok` when the catalog is enabled
- [x] Manifest path, notes, and contents excluded from logs; no secrets introduced
- [x] Seven committed golden HTTP contract baselines covering generation, fault extraction, errors, providers, model versions, and readiness
- [x] Dedicated `regression` pytest marker and `scripts/regression.ps1` runner with explicit `-Update` workflow
- [x] Stage I suite executed successfully: **26 passed**
- [x] Full suite executed successfully: **274 passed**
- [x] Live `.env` check confirmed `model_catalog_enabled: true`, four active entries, readiness `models: ok`, and successful generation
- [x] Stage A–H suites remain green; no existing endpoint or contract removed
- [x] No new runtime or development dependencies
- [x] `.env.example`, `.env`, README, and project structure updated

**Stage I is complete.**

---

## 23. Stage J completion checklist

- [x] GitHub Actions workflow committed at `.github/workflows/ci.yml`
- [x] Python 3.14 on `ubuntu-latest` with pip caching and versioned checkout/setup actions
- [x] Read-only workflow permissions, concurrency cancellation, and a 15-minute job timeout
- [x] No repository secrets, no live OpenAI calls, and deterministic test-only environment values
- [x] Byte-compilation gate across `app`, `tests`, and `alembic`
- [x] Ruff declared as a development dependency and configured in `pyproject.toml`
- [x] Full suite, deterministic fault matrix, and model-version/regression suite run as named gates
- [x] `UPDATE_REGRESSION_BASELINES=0` forced, plus a post-test baseline diff check
- [x] `scripts/quality.ps1` local Windows mirror of the CI commands
- [x] Stage J contract tests executed successfully: **7 passed**
- [x] Full suite executed successfully: **281 passed**
- [x] Fault matrix executed successfully: **31 passed**
- [x] Regression suite executed successfully: **26 passed**
- [x] Clean-checkout simulation without `.env` executed successfully: **281 passed**
- [x] Workflow YAML parsed successfully and `quality.ps1` passed the PowerShell parser
- [x] Stages A–I remain green; no application behavior, endpoint, or contract was removed
- [x] No runtime dependency was added; only development-time Ruff
- [x] GitHub-hosted execution is not claimed from this workspace because it is not a Git repository with a remote
- [x] README, project structure, and project memory updated

**Stage J is complete.**

---

## 24. Stage K completion checklist

- [x] Durable cost and latency summaries computed from persisted request logs, with fixed UTC windows
- [x] `GET /api/v1/monitoring/summary` with window, kind, and provider filters
- [x] `GET /api/v1/monitoring/metrics` in Prometheus text format
- [x] Admin-only access on both endpoints, with `401`/`403` contract tests
- [x] Average, p50, and p95 latency; request, accepted, successful, degraded, and error counts
- [x] Provider failure, fallback, and retry rates; cost per request and cost per accepted result
- [x] Bounded percentile sample with `sample_size` and `sample_truncated` reporting
- [x] Per-kind and per-provider breakdowns using the same outcome definitions
- [x] Monitoring query timeout, bounded reads, and safe `503 monitoring_unavailable` failures
- [x] Prometheus counters, histograms, and cost/token series with bounded labels
- [x] Metrics remain available with persistence disabled, slow, or broken
- [x] Observer isolation: a metrics failure never fails a request or a log write
- [x] No prompts, report text, URLs, credentials, or request IDs in metric labels
- [x] `MONITORING_QUERY_TIMEOUT_SECONDS` and `MONITORING_LATENCY_SAMPLE_LIMIT` validated at startup
- [x] `prometheus-client` declared as a bounded runtime dependency
- [x] Stage K tests executed successfully: **15 passed**
- [x] Full suite executed successfully: **296 passed**
- [x] Fault matrix executed successfully: **31 passed**
- [x] Regression suite executed successfully: **26 passed**
- [x] Stage J CI contract tests executed successfully: **7 passed**
- [x] Ruff, byte-compilation, and clean-checkout suite executed successfully
- [x] Live walkthrough verified summary math, breakdowns, admin enforcement, and metrics output
- [x] Stages A–J remain green; no existing endpoint or response contract changed
- [x] README, `.env.example`, project structure, and project memory updated

**Stage K is complete.**

---

## 25. Stage L completion checklist

- [x] Separate read-only Streamlit dashboard process under `dashboard/`, with no imports from `app.*`
- [x] Five views: Overview, Providers, Requests, Model versions, Prometheus metrics
- [x] HTTP-only admin API client with no redirects, no ambient proxy inheritance, and bounded timeouts
- [x] Strict `DASHBOARD_API_BASE_URL` / `DASHBOARD_API_PREFIX` validation and separate `DASHBOARD_*` configuration
- [x] Admin key as `SecretStr`; environment-first, masked sidebar fallback held in session memory only
- [x] Live/readiness reachability gate with explicit API start guidance and not-ready warning
- [x] Overview totals: requests, accepted rate, p50/p95, cost per request, cost per accepted result, provider failure and fallback rates
- [x] Charts and per-kind/per-provider tables using the same API totals
- [x] Provider inventory and explicit on-demand health check
- [x] Filtered, paginated request history with a privacy caption and no prompt/report content
- [x] Model-version inventory with tracked/active counts and configured state
- [x] Bounded Prometheus text parsing and a process-metrics summary, with raw text only in `st.code`
- [x] XSS-safe rendering: API/exposition strings never pass through `st.markdown`
- [x] Typed, sanitized dashboard errors for auth, rate limit, timeout, transport, redirects, and invalid payloads
- [x] `.streamlit/config.toml` loopback bind with CORS/XSRF protection and minimal toolbar
- [x] `scripts/dashboard.ps1` loopback guard and explicit `-AllowRemote` opt-in
- [x] `streamlit` declared as a bounded runtime dependency
- [x] Stage L tests executed successfully: **29 passed**
- [x] Full suite executed successfully: **325 passed**
- [x] Fault matrix executed successfully: **31 passed**
- [x] Regression suite executed successfully: **26 passed**
- [x] Stage J CI contract tests executed successfully: **7 passed**
- [x] Ruff and clean-checkout suite (no `.env`) executed successfully: **325 passed**
- [x] Browser walkthrough verified all five views, provider health, Tokens (329), and no prompt/report leakage
- [x] Stages A–K remain green; no existing endpoint or response contract changed
- [x] README, `.env.example`, project structure, screenshots, and project memory updated

**Stage L is complete.**

---

## 26. Stage M completion checklist

- [x] Multi-stage `Dockerfile` with `builder`, shared `runtime`, `api`, and `dashboard` stages
- [x] Non-root runtime (UID/GID 10001), no compiler toolchain, runtime assets copied with ownership
- [x] Separate API and dashboard images built from one runtime; health checks use standard-library HTTP
- [x] API entrypoint runs `alembic upgrade head` with bounded retries, then `exec`s Uvicorn
- [x] `compose.yaml` with PostgreSQL, API, and dashboard services, named volume, and health-gated dependencies
- [x] PostgreSQL isolated on an internal backend network; API on backend + frontend; dashboard on frontend only
- [x] Required secrets enforced with `${VAR:?...}`; no literal database password or API key in Compose
- [x] Production settings asserted by Compose: PostgreSQL, no auto-create/echo, auth required, keys present
- [x] Runtime hardening: read-only root filesystems, tmpfs `/tmp`, `cap_drop: ALL`, `no-new-privileges`, `init`
- [x] Loopback-only published ports (`127.0.0.1:8000`, `127.0.0.1:8501`) and no database port
- [x] `.dockerignore` excludes secrets, local data, tests, documentation, and unnecessary scripts
- [x] `.env.docker.example` placeholders plus git-ignore rules for `.env.docker`
- [x] `scripts\demo.ps1` generates cryptographic URL-safe secrets, rejects placeholders, builds/starts the stack, verifies it, and tears down in `finally`
- [x] Demo never prints generated secrets and returns nonzero on verification failure with bounded diagnostics
- [x] `scripts\e2e_demo.py` verifies readiness/database, liveness, two generations, fault extraction, unknown provider, unauthenticated history, monitoring summary, Prometheus metrics, history, model versions, and dashboard health
- [x] Verifier disables ambient proxies and redirects and proves a per-run marker does not appear in metrics or history
- [x] Stage M deployment contract tests executed successfully: **15 passed, 1 skipped** (Compose CLI unavailable)
- [x] Full suite executed successfully: **340 passed, 1 skipped**
- [x] Fault matrix executed successfully: **31 passed**
- [x] Regression suite executed successfully: **26 passed**
- [x] Stage J CI contract tests executed successfully: **7 passed**
- [x] Stage J local quality gate (`scripts\quality.ps1`) executed successfully
- [x] Ruff and clean-checkout suite (no `.env`) executed successfully: **340 passed, 1 skipped**
- [x] Native equivalent end-to-end run executed successfully: `stage-m e2e: PASS` (requests=4, accepted=3, errors=1, history=4, models=4 active=4, dashboard health=ok)
- [x] Docker absence on the implementation host disclosed; no image build or container start is claimed
- [x] Conditional `docker compose config` validation included for Docker-capable hosts
- [x] Stages A–L remain green; no application or dashboard runtime behavior changed
- [x] README, deployment docs, project structure, test counts, and project memory updated

**Stage M is complete. All planned stages A–M are implemented.**

---

## 27. Roadmap

| Stage | Status | Scope |
|---|---|---|
| A | Complete | Foundation, configuration, logging, health, tests |
| B | Complete | Adapter interface, provider registry, local fake provider |
| C | Complete | OpenAI chat-completions adapter, normalized errors, health, live verification tool |
| D | Complete | Timeouts, bounded retries with jitter, circuit breaker, secondary switching, deterministic fallback |
| E | Complete | Authentication, authorization, rate limiting, budget management, cost reporting |
| F | Complete | Fault-report summarization with validated JSON and deterministic extraction fallback |
| G | Complete | PostgreSQL-ready persistence, Alembic, secure request history |
| H | Complete | Deterministic fault-injection test matrix |
| I | Complete | Model version management and golden-contract regression suite |
| J | Complete | GitHub Actions quality gate and local quality runner |
| K | Complete | Cost and latency monitoring |
| L | Complete | Streamlit monitoring dashboard |
| M | Complete | Docker deployment and end-to-end demonstration |
