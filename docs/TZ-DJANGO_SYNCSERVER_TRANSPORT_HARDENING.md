# TZ: Django -> SyncServer Internal Transport Hardening

## Checklist Table Of Contents

- [ ] 0. Context and architecture invariants confirmed
- [ ] 1. Baseline measurements collected
- [ ] 2. Persistent HTTP transport implemented in `Warehouse_web/apps/sync_client/`
- [ ] 3. BFF screen-level aggregation reviewed and implemented where useful
- [ ] 4. Safe cache policy implemented for read-heavy data
- [ ] 5. Timeout, retry, and error mapping policy hardened
- [ ] 6. Request tracing and transport metrics added
- [ ] 7. Optional Unix domain socket experiment measured
- [ ] 8. Verification ladder completed
- [ ] 9. Rollout notes and agent docs updated
- [ ] 10. Final acceptance review completed

## 0. Purpose

This document defines the Warehouse 3.0 direction for improving the internal transport between `Warehouse_web` Django/BFF and `SyncServer` FastAPI.

The goal is to reduce latency, request overhead, and operational fragility without changing the accepted macroarchitecture:

```text
Browser
  -> Django shell / BFF
    -> Warehouse_web apps/sync_client
      -> SyncServer /api/v1
        -> SyncServer services and UnitOfWork
```

This work is a transport hardening task, not a domain rewrite.

## 1. Source Documents

Agents must read these before implementation:

- `Functional and WorkLogik.md`, especially auth, operation lifecycle, and launch/operation rules.
- `ARCHITECTURE.md`.
- `Warehouse_web/AGENTS.md`.
- `SyncServer/AGENTS.md`.
- `Warehouse_frontend/docs/ARCHITECTURE_FRONTEND_SPA.md`.
- `docs/adr/0011-django-syncserver-internal-transport-hardening.md`.

## 2. Invariants

These rules are not changed by this TZ:

- `SyncServer` remains the authoritative warehouse backend.
- All warehouse domain writes go through `SyncServer` services.
- Django remains the active browser client, session host, admin UI, and BFF.
- Angular calls only same-origin Django BFF endpoints.
- Browser JavaScript never receives `X-User-Token` or `X-Device-Token`.
- Clients do not connect directly to the SyncServer database.
- `Warehouse_client_core` remains the Rust offline-first runtime for future desktop/mobile clients, not a replacement for the online Django/FastAPI backend in 3.0.

## 3. Non-Goals

Do not implement these as part of this TZ:

- Moving SyncServer domain models, business services, or SQLAlchemy repositories into Django.
- Giving Django direct access to SyncServer warehouse tables.
- Replacing `/api/v1` REST contracts with gRPC, stdio, JSON-RPC, or direct Python imports.
- Rewriting the online backend in Rust.
- Exposing SyncServer tokens to Angular.
- Adding a second browser-facing API surface that bypasses Django BFF.
- Introducing LibreOffice/docx document generation. PDF generation belongs to document workflow work, not this transport task.

## 4. Current Problem

The accepted architecture is sound, but the current Django -> SyncServer HTTP implementation should be hardened before Warehouse 3.0 grows more Angular screens.

Observed issues to verify during implementation:

- `Warehouse_web/apps/sync_client/client.py` creates a new `httpx.Client` inside each low-level request path. This likely prevents stable connection pooling and increases per-request overhead.
- BFF views often forward one browser action into one SyncServer call. Some Angular screens will naturally need several related datasets, so a screen can become chatty unless the BFF owns screen-level aggregation.
- Transport observability is thin. It is hard to answer: how many SyncServer calls does one screen make, what is p95 latency, and which endpoints dominate.
- Caching policy exists in places but is not documented as a cross-project transport rule.

## 5. Target Transport

Primary target:

```text
Django BFF
  -> typed apps/sync_client wrappers
    -> persistent HTTPX transport over Docker network TCP
      -> SyncServer /api/v1
```

Optional measured target after baseline:

```text
Django BFF
  -> typed apps/sync_client wrappers
    -> persistent HTTPX transport over Unix domain socket
      -> SyncServer /api/v1
```

The API contract remains HTTP + JSON + `/api/v1`. Unix socket, if adopted, is only a process/container transport optimization. It must not create a second semantic API.

## 6. Work Packages

### 6.1 Baseline Measurements

Before changing runtime transport, collect baseline numbers on the Docker stand:

- request count from browser action to Django BFF;
- request count from Django BFF to SyncServer;
- p50 and p95 latency for BFF endpoints;
- p50 and p95 latency for SyncServer calls;
- slowest SyncServer endpoint paths;
- error rates and timeout counts;
- representative scenarios:
  - Angular nomenclature screen open;
  - operations journal open;
  - operation detail open;
  - create operation draft;
  - edit unsubmitted operation;
  - submit operation;
  - temporary item list/open;
  - pending acceptance/lost assets list.

Minimum artifact:

- a short markdown report under `Warehouse_web/docs/reports/` or `docs/archive/` with date, stand state, commands, and measured numbers.

### 6.2 Persistent HTTPX Transport

Replace per-request HTTP client construction with a stable transport provider in `Warehouse_web/apps/sync_client/`.

Required behavior:

- Keep all raw SyncServer calls centralized in `SyncServerClient`.
- Reuse connections across requests within a Django worker process or thread-safe client provider.
- Keep token resolution per request. Do not cache user tokens inside a shared client object.
- Preserve existing public wrapper methods: `get`, `post`, `put`, `patch`, `delete`, `get_bytes`.
- Preserve current exception classes and status-code mapping.
- Add explicit connect/read/write/pool timeout configuration if supported by the chosen HTTPX setup.
- Provide deterministic cleanup where Django process lifecycle allows it.
- Unit-test that headers are built per request and that root fallback is not introduced for non-root users.

Implementation notes:

- Prefer a small provider module, for example `apps/sync_client/transport.py`, over spreading `httpx.Client` creation through wrappers.
- Avoid process-global mutable auth state.
- Keep `SYNC_SERVER_URL` requiring `/api/v1`.
- Do not change Angular/BFF contracts as part of this step.

### 6.3 BFF Screen-Level Aggregation

Review Angular screens and BFF endpoints for request fan-out.

Allowed:

- Add BFF endpoints that aggregate data needed by a single screen or modal.
- Compose multiple SyncServer reads inside Django when the composition is UI-oriented.
- Keep response DTOs browser-friendly and token-free.
- Cache read-only lookup data where safe.

Forbidden:

- Moving SyncServer validation or write decisions into Django.
- Performing warehouse writes in Django DB.
- Inventing Django-only operation states.
- Adding BFF mutation semantics that differ from SyncServer service rules.

Good candidates:

- operations create/edit modal bootstrap data;
- operation detail with related documents and acceptance status;
- temporary item detail with related operation links;
- dashboard counters for temporary items and pending acceptance;
- catalog search lookup bundles.

### 6.4 Safe Cache Policy

Use Django cache only for technical/BFF acceleration.

Allowed cache data:

- catalog read/search responses;
- units/categories/sites lookups;
- navigation/sidebar permission summaries;
- dashboard counters with short TTL;
- screen bootstrap bundles.

Forbidden cache data:

- raw user/device tokens;
- SyncServer root token;
- uncommitted operation write decisions;
- final authority for balances, access rights, or operation submission.

Invalidation options:

- short TTL for volatile views;
- cache key includes user role/site scope where permissions affect results;
- explicit bust after BFF mutation;
- SyncServer cursor fields such as `updated_after` when available.

### 6.5 Timeout, Retry, And Error Policy

Hardening rules:

- Configure separate connect/read/write/pool timeouts where practical.
- Use retries only for safe idempotent reads and health checks unless an idempotency key is present.
- Do not blindly retry operation create/submit/cancel without idempotency protection.
- Map `401`, `403`, `404`, `409`, `422`, timeout, and unavailable errors into stable Django BFF error shapes.
- Preserve existing user-facing Russian messages where they exist.

### 6.6 Request Tracing And Metrics

Add observability without leaking secrets.

Required:

- Generate or forward `X-Request-Id` from Django to SyncServer.
- Log SyncServer method, path, status, duration, and request id.
- Never log `X-User-Token`, `X-Device-Token`, root token, or `.env` values.
- Add a way to count SyncServer calls per BFF request during tests or debug mode.

Optional:

- Prometheus-style counters/histograms if the project already introduces metrics plumbing.
- A debug-only response header showing upstream call count, disabled by default in production.

### 6.7 Optional Unix Domain Socket Experiment

Run this only after baseline and persistent HTTP transport are complete.

Experiment design:

- Keep `/api/v1` HTTP semantics unchanged.
- Run Uvicorn with a Unix domain socket in an environment-specific compose override.
- Mount the socket into the Django container.
- Configure HTTPX transport with the socket path through an environment flag.
- Measure the same scenarios as baseline.
- Keep TCP as the default unless UDS gives a clear benefit and does not complicate deployment.

Acceptance threshold suggestion:

- Adopt UDS only if p95 Django -> SyncServer latency or CPU overhead improves enough to matter in real scenarios, and operational complexity remains low.

Rollback:

- Switching `SYNC_SERVER_TRANSPORT=tcp` or removing the UDS override must restore the current Docker network TCP path.

### 6.8 Deferred Alternatives

These are explicitly deferred for Warehouse 3.0:

- gRPC between Django and SyncServer;
- stdio IPC;
- direct in-memory Python imports of SyncServer services from Django;
- shared database access;
- online backend rewrite in Rust.

They require a separate ADR with measured evidence and migration plan.

## 7. Verification Ladder

Static checks:

- Django import check.
- No direct SyncServer tokens in Angular source.
- No raw `httpx` calls outside approved `apps/sync_client/` or documented public health helpers.

Unit/component tests:

- `SyncServerClient` header and error mapping tests.
- Transport provider tests with mocked HTTPX transport.
- BFF aggregation tests with mocked `apps/sync_client` wrappers.

Integration tests:

- Django BFF tests for changed endpoints.
- SyncServer tests only if backend API behavior changes.

Real stand smoke:

- Probe SyncServer, Django, and PostgreSQL per root `AGENTS.md`.
- Exercise key BFF endpoints through Django.
- Confirm no direct browser request to SyncServer for Angular screens.

Performance evidence:

- Before/after request count.
- Before/after p50/p95 latency for representative screen actions.
- Error/timeout behavior under stopped SyncServer.

## 8. Rollout Strategy

Recommended rollout:

1. Add baseline metrics and debug logging.
2. Introduce persistent HTTP transport behind existing `SyncServerClient` API.
3. Run Django tests and real stand smoke.
4. Add BFF aggregation only for screens currently being migrated or actively edited.
5. Add cache policy incrementally for read-heavy lookups.
6. Consider UDS only after product-critical Warehouse 3.0 flows are stable.

This keeps the path useful immediately without blocking Angular migration and operation workflow work.

## 9. Acceptance Criteria

The task is accepted when:

- Django still communicates with SyncServer only through `apps/sync_client/`.
- `/api/v1` remains the canonical SyncServer contract.
- Angular still calls only Django same-origin endpoints.
- Connection reuse is implemented or explicitly rejected with measured rationale.
- Representative screen actions have before/after metrics.
- BFF aggregation does not move domain writes or warehouse authority into Django.
- Documentation references this TZ and ADR.
- All relevant tests pass, or unavailable real-stand checks are left unchecked with a blocker note.
