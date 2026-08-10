# Architecture

## System Role Split

`Warehouse Solution` is a multi-project warehouse system with one authoritative backend, one active web client, and future offline clients.

| Area | Owner |
|---|---|
| Warehouse domain truth | `SyncServer` |
| Web sessions, admin UI, BFF | `Warehouse_web` |
| Browser SPA shell | `Warehouse_frontend`, hosted by Django |
| Offline storage/sync runtime | `Warehouse_client_core` |
| Future desktop/mobile UI | `WarehouseDesktop`, `WarehouseMobile` |
| AI workstation | `WarehouseAIWorkstation`, paused |

## Runtime Flow

```text
User browser
  -> Django routes/templates/BFF in Warehouse_web
    -> apps/sync_client typed wrappers
      -> SyncServer /api/v1
        -> API routes
          -> services
            -> UnitOfWork/repos
              -> PostgreSQL
```

For Angular features:

```text
User browser
  -> Django route
    -> Angular assets built from Warehouse_frontend
      -> same-origin Django BFF endpoints
        -> SyncServer through Warehouse_web sync_client
```

Future offline clients:

```text
Desktop or Android UI
  -> Warehouse_client_core facade
    -> local SQLite cache/outbox
    -> SyncServer API/sync protocol
```

## Internal Transport Direction

Warehouse 3.0 keeps Django -> SyncServer communication on the canonical `/api/v1` HTTP/JSON contract.

The approved path is to harden the existing `Warehouse_web/apps/sync_client/` layer:

- reuse HTTP connections through a persistent HTTPX transport;
- keep SyncServer token/header construction per request;
- add request tracing, metrics, explicit timeouts, and safe error mapping;
- aggregate BFF reads where this reduces screen round trips without moving domain rules into Django;
- cache read-heavy lookup data only as technical BFF acceleration;
- consider Unix domain socket transport only as a measured optional experiment.

Do not replace this boundary with direct Python imports, shared database access, stdio IPC, gRPC, or a Rust online backend rewrite without a new ADR.

See `docs/adr/0011-django-syncserver-internal-transport-hardening.md` and `docs/TZ-DJANGO_SYNCSERVER_TRANSPORT_HARDENING.md`.

## Data Ownership

- `SyncServer` owns users, sites, devices, access scopes, catalog, operations, balances, documents, recipients, and sync events.
- `Warehouse_web` owns only web technical state: Django users/sessions, SyncServer user binding, cache, and BFF state.
- `Warehouse_frontend` owns Angular UI source only. It does not own warehouse data or tokens.
- `Warehouse_client_core` will own local offline state and sync mechanics, but not warehouse truth.

## Project Details

### Historical integrity hardening

ADR-0018 defines the append-only audit spine (`audit_events`, `audit_event_resources`, `audit_item_effects`). ADR-0028 accepts Stage A hardening while keeping the operation-driven model and UnitOfWork boundary unchanged:

- submitted/cancelled operation dates become immutable through normal service/API paths;
- restore, catalog soft-delete, acceptance and lost-resolution gain complete causal audit;
- target `audit_item_effects.effective_at` records when each concrete balance mutation became effective, while `created_at` remains physical insert time;
- default item-movement reporting excludes `Operation.origin='system'` without replacing the existing operation/line read model; Django BFF only forwards the optional filter and owns no report rule;
- integrity diagnostics are read-only; automatic repair and scheduled execution are separate decisions.

Status on 2026-08-05: ADR/TZ issued, runtime implementation not started. See `docs/audit/HISTORICAL_INTEGRITY_STATUS.md`, `docs/adr/0028-historical-integrity-stage-a.md`, and `docs/TZ-HISTORICAL_INTEGRITY_STAGE_A.md`.

### SyncServer

- Stack: Python, FastAPI, Pydantic v2, SQLAlchemy async, PostgreSQL, Alembic.
- Layers: `app/api` -> `app/services` -> `app/repos` -> `app/models`.
- Transaction boundary: `app/services/uow.py`.
- Verification: `python -m pytest`; migrations require `python -m alembic upgrade head` against a safe DB.

### Warehouse_web

- Stack: Django 5.2, httpx, WhiteNoise, Gunicorn.
- Role: current active web client and BFF.
- SyncServer integration: `apps/sync_client/`.
- Catalog domain ORM is removed from the Django catalog app; catalog data is SyncServer-backed.
- Verification: `python manage.py test`.

### Document rendering pipeline (rev. V3.1I)

Waybill/act/acceptance_certificate metadata lives in SyncServer (`/api/v1/documents`); final binary is rendered on demand in `Warehouse_web` by `apps/documents/services.py` (Jinja2 → WeasyPrint, in-memory, Django cache TTL 1h, no PDF storage on disk). The V3.1I rev. 2 hardening keeps the layout stable across multi-page waybills: CSS uses a **flexbox `.page` container** so the header sticks to the top and the signature block pins to the bottom of every page (I1), while `paginate_waybill_lines` does a **dynamic, content-height-aware** split with an `extra_signatures_count` budget and active row hard-caps to keep WeasyPrint geometry in sync with the Python estimate (I2). See `docs/TZ-V3.1I_WAYBILL_PAGINATION_AND_SYNC_HARDENING.md`.

### Warehouse_frontend

- Role: Angular shell, currently the high-priority UI direction for nomenclature.
- Must be hosted by Django and call Django BFF endpoints.
- Direct browser calls to SyncServer are not allowed.

### Warehouse_client_core

- Planned Rust workspace for offline-first local runtime.
- Target responsibilities: SQLite schema, outbox, sync, DTO mapping, validation, conflict state, FFI/facade API.

### WarehouseDesktop And WarehouseMobile

- Future clients to be rebuilt around `Warehouse_client_core`.
- UI and platform-specific code stay in each client; offline sync logic belongs in the core.

### WarehouseAIWorkstation

- Paused. Do not change unless explicitly requested.

## Architectural Constraints

1. SyncServer is the source of truth.
2. Clients do not connect directly to the SyncServer database.
3. Django local DB is technical web state only.
4. Angular runs through Django and never receives SyncServer tokens.
5. Offline desktop/mobile behavior belongs in `Warehouse_client_core`.
6. Root repository remains coordination/docs only.

## ADRs

Solution-level ADRs live in `docs/adr/`.

Key current decisions:

- SyncServer is the authoritative backend.
- Warehouse_web goes through SyncServer API.
- Django -> SyncServer transport stays HTTP/JSON `/api/v1` for Warehouse 3.0 and is hardened in `apps/sync_client`.
- Backend writes use service and UnitOfWork layers.
- Inventory is operation-driven.
- Token auth and site-scoped access stay server-enforced.
