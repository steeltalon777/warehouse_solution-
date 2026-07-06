# Quartermaster

**Система складского и имущественного учёта.** Складской фреймворк/WMS: онлайн-клиент, офлайн-терминалы, синхронизация, AI-воркстейшн.

Технические имена репозиториев, пакетов, сервисов и БД сохраняются без изменений. Quartermaster — пользовательское продуктовое имя.

Runtime code lives in project directories; the root keeps cross-project documentation, ADRs, agent guidance, and project maps.

## Current Product Shape

| Project | Role | Status |
|---|---|---|
| `SyncServer/` | Authoritative FastAPI backend, source of truth, sync hub | Active |
| `Warehouse_web/` | Django web client, session host, admin UI, BFF | Active |
| `Warehouse_frontend/` | Angular shell hosted by Django | Active |
| `Warehouse_client_core/` | Rust offline-first runtime (SQLite, sync engine, outbox, FFI) | Active (v3.1) |
| `WarehouseWorkstation/` | WPF desktop AI workstation, target for Rust core migration | Active (v3.1 Layer 0, full migration → 3.2) |
| `WarehouseMobile/` | Future Android client over `Warehouse_client_core` (Kotlin/UniFFI) | Planned (v3.3) |

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

## Warehouse 3.0 Transport Direction

The Django -> SyncServer boundary stays on the canonical `/api/v1` HTTP/JSON API. For Warehouse 3.0 the approved path is transport hardening, not a domain rewrite: improve `Warehouse_web/apps/sync_client/` connection reuse, timeouts, metrics, BFF aggregation, and safe read caching. Unix domain sockets may be tested later as an optional measured optimization.

Do not move SyncServer domain logic into Django, give Django direct warehouse DB access, replace the boundary with stdio/gRPC/direct imports, or rewrite the online backend in Rust without a new ADR.

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
| `Warehouse_frontend/` | `npm run build`; `make test-e2e` for Docker-backed Playwright E2E |
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
- [.github/workflows/e2e-tests.yml](.github/workflows/e2e-tests.yml) - GitHub Actions Playwright E2E pipeline
- [API_MAP.md](API_MAP.md) - SyncServer endpoint map
- [SOLUTION_ROADMAP.md](SOLUTION_ROADMAP.md) - priority roadmap
- [docs/adr/0011-django-syncserver-internal-transport-hardening.md](docs/adr/0011-django-syncserver-internal-transport-hardening.md) - Warehouse 3.0 internal transport decision
- [docs/TZ-DJANGO_SYNCSERVER_TRANSPORT_HARDENING.md](docs/TZ-DJANGO_SYNCSERVER_TRANSPORT_HARDENING.md) - executable transport hardening specification
