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

## Data Ownership

- `SyncServer` owns users, sites, devices, access scopes, catalog, operations, balances, documents, recipients, and sync events.
- `Warehouse_web` owns only web technical state: Django users/sessions, SyncServer user binding, cache, and BFF state.
- `Warehouse_frontend` owns Angular UI source only. It does not own warehouse data or tokens.
- `Warehouse_client_core` will own local offline state and sync mechanics, but not warehouse truth.

## Project Details

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
- Backend writes use service and UnitOfWork layers.
- Inventory is operation-driven.
- Token auth and site-scoped access stay server-enforced.
