# ADR-0011: Django -> SyncServer Internal Transport Hardening

## Status
Accepted

## Date
2026-05-29

## Context

Warehouse 3.0 will increase the share of Angular SPA screens hosted by Django. The current macroarchitecture is accepted and works:

```text
Browser -> Django shell/BFF -> Warehouse_web apps/sync_client -> SyncServer /api/v1 -> services -> PostgreSQL
```

The concern is the internal transport between Django and SyncServer. Alternatives considered include stdio IPC, direct module imports, moving the API into Django, gRPC, Unix domain sockets, and a full Rust online backend rewrite.

The existing documents establish that:

- `SyncServer` owns warehouse domain data and business rules.
- Django owns web technical state and BFF behavior.
- Angular must call Django BFF endpoints and must not receive SyncServer tokens.
- Future desktop/mobile offline behavior belongs in `Warehouse_client_core`.

## Decision

Keep HTTP/JSON `/api/v1` as the canonical Django -> SyncServer contract for Warehouse 3.0, and harden the existing transport instead of replacing the architecture.

Implementation direction:

1. Optimize `Warehouse_web/apps/sync_client/` first:
   - persistent HTTPX transport / connection reuse;
   - per-request token/header construction;
   - explicit timeouts;
   - stable exception mapping.
2. Reduce unnecessary round trips with Django BFF aggregation where the aggregation is UI-oriented.
3. Add safe caching for read-heavy lookup data without making Django authoritative for warehouse state.
4. Add request tracing and transport metrics.
5. Treat Unix domain socket transport as an optional measured experiment after baseline and HTTP hardening.

## Rejected For Warehouse 3.0

### Move SyncServer domain into Django

Rejected because it would make Django a second warehouse backend and would duplicate or bypass SyncServer business rules.

### Direct Django access to SyncServer database

Rejected because it would bypass service-layer validation, authorization, UnitOfWork transaction boundaries, and operation-driven inventory invariants.

### Direct Python imports / in-process calls from Django to SyncServer services

Rejected for now because it tightly couples Django runtime, FastAPI dependencies, async SQLAlchemy session management, auth dependencies, and service lifecycle. It also makes future client contracts less clear.

### stdio IPC

Rejected because it complicates concurrency, backpressure, restarts, monitoring, and error handling for a web workload while still requiring serialization.

### gRPC

Deferred. gRPC could be useful later for a large polyglot service mesh, but today it would add a second contract next to existing Pydantic/OpenAPI schemas and Django sync_client wrappers.

### Rust online backend rewrite

Rejected for Warehouse 3.0. Rust remains strategic for `Warehouse_client_core` offline-first desktop/mobile runtime. It should not replace the working Django/FastAPI online architecture without a separate product-level migration ADR.

## Consequences

### Pros

- Preserves current working product architecture.
- Improves latency and reliability where the actual problem lives.
- Keeps SyncServer API contracts usable by Django, Rust core, and future clients.
- Avoids blocking Angular migration with a large backend rewrite.
- Allows optional Unix socket optimization without changing API semantics.

### Cons

- HTTP/JSON serialization remains in the path.
- Django and SyncServer remain independently deployed services.
- BFF aggregation must be designed carefully to avoid moving domain rules into Django.

## Implementation Spec

The executable specification is:

- `docs/TZ-DJANGO_SYNCSERVER_TRANSPORT_HARDENING.md`

## Confidence

High for persistent HTTP transport, BFF aggregation, caching, and observability.

Medium for Unix domain socket adoption, pending measurements on the real Docker stand.
