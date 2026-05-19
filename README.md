# Warehouse Solution

`Warehouse Solution` is a coordination workspace for the warehouse management system. Runtime code lives in project directories; the root keeps cross-project documentation, ADRs, agent guidance, and project maps.

## Current Product Shape

| Project | Role | Status |
|---|---|---|
| `SyncServer/` | Authoritative FastAPI backend and source of truth | Active, highest backend priority |
| `Warehouse_web/` | Active Django web client, session host, admin UI, BFF | Active web client |
| `Warehouse_frontend/` | Angular shell hosted by Django | High priority |
| `Warehouse_client_core/` | Planned Rust offline-first runtime | Architecture/planning |
| `WarehouseDesktop/` | Future offline desktop client over `Warehouse_client_core` | Rebuild later |
| `WarehouseMobile/` | Future offline Android client over `Warehouse_client_core` | Rebuild later |
| `WarehouseAIWorkstation/` | AI workstation | Paused unless explicitly resumed |

## Core Architecture

```text
Browser
  -> Warehouse_web (Django session, SSR/admin/BFF)
    -> SyncServer API (/api/v1)
      -> Services -> UnitOfWork/Repos -> PostgreSQL

Browser
  -> Django-hosted Angular shell from Warehouse_frontend
    -> Django BFF endpoints
      -> Warehouse_web apps/sync_client
        -> SyncServer API (/api/v1)

Future offline desktop/mobile
  -> Warehouse_client_core facade
    -> local SQLite/outbox/cache
    -> SyncServer sync/API contracts
```

`SyncServer` owns warehouse domain data and business rules. Django owns web technical state only: auth, sessions, user binding, cache, and BFF state. Angular never receives SyncServer tokens and never calls SyncServer directly from the browser.

## Project Structure

```text
SyncServer/              FastAPI backend, PostgreSQL, Alembic, API contracts
Warehouse_web/           Django web client, admin UI, BFF, SyncServer HTTP wrappers
Warehouse_frontend/      Angular shell target hosted by Django
Warehouse_client_core/   Planned Rust offline-first runtime
WarehouseDesktop/        Future WPF offline client over warehouse core
WarehouseMobile/         Future Android offline client over warehouse core
WarehouseAIWorkstation/  Paused WPF AI workstation

AGENTS.md               Agent contract and verification matrix
ARCHITECTURE.md         Cross-project architecture
INDEX.md                Navigation index
AI_CONTEXT.md           Agent reasoning rules
AI_ENTRY_POINTS.md      Source entry points
MEMORY.md               Stable project memory
API_MAP.md              SyncServer API map
docs/adr/               Solution-level ADRs
plans/                  Working plans
```

## Verification

| Project | Command |
|---|---|
| `SyncServer/` | `python -m pytest` |
| `Warehouse_web/` | `python manage.py test` |
| `Warehouse_frontend/` | `npm run build` once Angular scripts exist |
| `Warehouse_client_core/` | `cargo fmt --all -- --check`, `cargo clippy --workspace --all-targets -- -D warnings`, `cargo test --workspace` once Rust workspace exists |
| `WarehouseDesktop/` | `dotnet test WarehouseDesktop.sln` when touched |
| `WarehouseMobile/` | `gradlew.bat test` when touched |
| `WarehouseAIWorkstation/` | `dotnet test WarehouseAIWorkstation.sln` only when explicitly resumed |

## Main Rules

- All warehouse domain writes go through `SyncServer` services.
- Clients must not connect directly to the SyncServer database.
- Django catalog and Angular nomenclature features must use Django services/BFF plus `Warehouse_web/apps/sync_client/`.
- Future offline clients must share `Warehouse_client_core` for local storage, outbox, sync, DTO mapping, and conflicts.
- Root repository remains coordination/docs only.

## Useful Docs

- [AGENTS.md](AGENTS.md) - agent contract
- [ARCHITECTURE.md](ARCHITECTURE.md) - architecture and data ownership
- [INDEX.md](INDEX.md) - navigation
- [AI_CONTEXT.md](AI_CONTEXT.md) - agent rules
- [AI_ENTRY_POINTS.md](AI_ENTRY_POINTS.md) - source entry points
- [API_MAP.md](API_MAP.md) - SyncServer endpoint map
- [SOLUTION_ROADMAP.md](SOLUTION_ROADMAP.md) - priority roadmap
