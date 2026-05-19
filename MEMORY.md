# Memory

Stable facts about the Warehouse Solution workspace.

## Current Product Decisions

- `SyncServer` is the single source of truth for warehouse domain data and business rules.
- `Warehouse_web` is the only active web client today. It also hosts Django sessions, admin screens, and BFF endpoints.
- `Warehouse_frontend` is the target Angular shell for high-priority browser UI work, starting with nomenclature.
- Angular must run through Django and same-origin BFF endpoints; browser code must not call SyncServer directly or receive SyncServer tokens.
- `Warehouse_client_core` is planned as a Rust offline-first runtime for future desktop and mobile clients.
- `WarehouseDesktop` and `WarehouseMobile` should be rebuilt around `Warehouse_client_core` instead of growing separate offline runtimes.
- `WarehouseAIWorkstation` is paused until the user explicitly asks to resume it.

## Domain Ownership

- SyncServer owns users, sites, devices, access scopes, catalog, operations, balances, documents, recipients, and sync events.
- Django owns web technical state only: sessions, auth integration, SyncServer binding, cache, and BFF support.
- Future offline core may own local cache/outbox/conflict state, but final business validation and truth remain on SyncServer.

## Critical Rules

- All warehouse mutations go through SyncServer services and UnitOfWork.
- Clients never connect directly to the SyncServer database.
- Django catalog app has no local warehouse-domain ORM models.
- `Warehouse_web/apps/sync_client/` is the canonical Django integration layer.
- Offline storage/sync belongs in `Warehouse_client_core`, not duplicated in desktop/mobile UI projects.
- Generated outputs and local tool caches are not source files.
- `.env` and local tool config may contain secrets; do not read, print, or hardcode them.

## Test Stand

The test stand is usually running locally:

| Service | Address | Health Check |
|---|---|---|
| SyncServer API | `http://localhost:8000` | `GET /api/v1/health` |
| Django (Warehouse_web) | `http://localhost:8001` | `GET /healthz/` |
| PostgreSQL (VM, via SSH) | `localhost:5434` | — |

SSH tunnel to VM database: `ssh -p 2222 makc@127.0.0.1` (agents never run this; user maintains the tunnel).

**Protocol:** agents probe health endpoints before real-stand tests. If the stand is not running, agents stop and ask the user to start it. Agents never attempt to start the stand themselves.

## Verification Memory

- `SyncServer`: `python -m pytest`.
- `Warehouse_web`: `python manage.py test`.
- `Warehouse_frontend`: `npm run build` once Angular scripts exist.
- `Warehouse_client_core`: `cargo fmt`, `cargo clippy`, `cargo test` once Rust workspace exists.
- `WarehouseDesktop`: `dotnet test WarehouseDesktop.sln` when touched.
- `WarehouseMobile`: `gradlew.bat test` when touched.
- `WarehouseAIWorkstation`: test only when explicitly resumed.
