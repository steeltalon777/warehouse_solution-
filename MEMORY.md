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
- Historical-integrity audit is complete; ADR-0028 and `TZ-HISTORICAL_INTEGRITY_STAGE_A.md` are issued and Stage A-wide runtime is implemented as of 2026-08-06 (final QA acceptance pending).
- Operation modal balance refresh is manual and explicit as of 2026-08-07 (`docs/TZ-OPERATION_MODAL_BALANCES_MANUAL_REFRESH.md`): warehouse switch and item add trigger a single targeted auto-request, Save/Submit do not, and a «Обновить всё» button refreshes all line balances on demand; search dropdown no longer shows «на складе: X» and does not request `include_balance`.

## Domain Ownership

- SyncServer owns users, sites, devices, access scopes, catalog, operations, balances, documents, recipients, and sync events.
- Django owns web technical state only: sessions, auth integration, SyncServer binding, cache, and BFF support.
- Future offline core may own local cache/outbox/conflict state, but final business validation and truth remain on SyncServer.

## Critical Rules

- All warehouse mutations go through SyncServer services and UnitOfWork.
- Historical-integrity risks are closed only after implementation evidence/QA; ADR/TZ publication alone does not close R-01…R-40.
- Clients never connect directly to the SyncServer database.
- Django catalog app has no local warehouse-domain ORM models.
- `Warehouse_web/apps/sync_client/` is the canonical Django integration layer.
- Offline storage/sync belongs in `Warehouse_client_core`, not duplicated in desktop/mobile UI projects.
- Generated outputs and local tool caches are not source files.
- `.env` and local tool config may contain secrets; do not read, print, or hardcode them.

## Test Stand

The test stand is usually running locally:

| Service | Address | Health Check | Container |
|---|---|---|---|
| SyncServer API | `http://localhost:8000` | `GET /api/v1/health` | `warehouse_syncserver` |
| Django (Warehouse_web) | `http://localhost:8001` | `GET /healthz/` | `warehouse_web` |
| PostgreSQL | `localhost:5432` | `pg_isready -h localhost -p 5432 -t 3` | `warehouse_postgres` (`postgres:15-alpine`) |
| Angular (Warehouse_frontend) | `http://localhost:4200` | `GET /` | `warehouse_angular` |

Run from workspace root: `make up` or `docker compose up -d`. Legacy VM database tunnel is obsolete.

**Protocol:** agents probe health endpoints before real-stand tests, including Angular at `http://localhost:4200/` for UI checks. If the stand is not running, agents try `make up`, then `docker compose up -d`. If Docker/compose cannot start the stand, agents report the blocker and leave the relevant checklist item unchecked.

## Verification Memory

- `SyncServer`: `python -m pytest`.
- `Warehouse_web`: `python manage.py test`.
- `Warehouse_frontend`: `npm run build` once Angular scripts exist.
- `Warehouse_client_core`: `cargo fmt`, `cargo clippy`, `cargo test` once Rust workspace exists.
- `WarehouseDesktop`: `dotnet test WarehouseDesktop.sln` when touched.
- `WarehouseMobile`: `gradlew.bat test` when touched.
- `WarehouseAIWorkstation`: test only when explicitly resumed.
