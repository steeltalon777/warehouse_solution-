# Index

## Project Overview

- Multi-repository workspace for warehouse management
- 1 authoritative backend + 5 client applications
- Root repo is documentation-first, no application code
- SyncServer is the single source of truth for warehouse domain data

## Tech Stack

| Project | Stack |
|---|---|
| **SyncServer** | Python, FastAPI, SQLAlchemy async, PostgreSQL, Alembic |
| **Warehouse_web** | Python, Django 5, httpx, WhiteNoise, Gunicorn |
| **WarehouseAIWorkstation** | .NET, C#, WPF, SQLite (local) |
| **WarehouseDesktop** | .NET 8, C#, WPF |
| **WarehouseMobile** | Kotlin, Android, Gradle, Room/SQLite |
| **Warehouse_frontend** | TypeScript (placeholder) |
| **Operations** | Docker, docker-compose |

## Repository Structure

```
├── SyncServer/                         Authoritative FastAPI backend
│   ├── main.py                         App entry point
│   ├── app/api/                        Route handlers (21 modules)
│   ├── app/services/                   Business logic (22 modules)
│   ├── app/repos/                      Data access (16 modules)
│   ├── app/models/                     SQLAlchemy ORM (18 models)
│   ├── app/schemas/                    Pydantic DTOs (16 modules)
│   ├── alembic/                        DB migrations (9 versions)
│   └── tests/                          Test suite (38+ files)
│
├── Warehouse_web/                      Django SSR web client
│   ├── manage.py                       Django CLI
│   ├── config/urls.py                  URL routing
│   ├── config/settings/                Base, dev, prod settings
│   ├── apps/sync_client/               SyncServer HTTP wrappers (16 modules)
│   ├── apps/users/                     Django auth + SyncUserBinding
│   ├── apps/catalog/                   Catalog browser
│   ├── apps/operations/                Operations UI
│   ├── apps/balances/                  Balances UI
│   ├── apps/admin_panel/               Root-only admin
│   └── templates/                      Django templates (60+ files)
│
├── WarehouseAIWorkstation/             WPF AI-powered desktop
│   ├── src/WarehouseAIWorkstation.App/           App host, bootstrap
│   ├── src/WarehouseAIWorkstation.Presentation/  Views, ViewModels (MVVM)
│   ├── src/WarehouseAIWorkstation.Application/   Service layer (40+ interfaces)
│   ├── src/WarehouseAIWorkstation.Infrastructure/ Local storage (SQLite, JSON, DPAPI)
│   ├── src/WarehouseAIWorkstation.Integrations.Sync/    SyncServer HTTP client
│   ├── src/WarehouseAIWorkstation.Integrations.AI/      OpenAI-compatible client
│   ├── src/WarehouseAIWorkstation.Domain/         Domain models
│   └── src/WarehouseAIWorkstation.Shared/         Shared utilities
│
├── WarehouseDesktop/                   WPF desktop client
│   ├── WarehouseDesktop.Application/   App services
│   ├── WarehouseDesktop.Contracts/     Interfaces
│   ├── WarehouseDesktop.Domain/        Domain models
│   ├── WarehouseDesktop.Infrastructure/ Infrastructure
│   └── WarehouseDesktop.Wpf/           WPF UI (Views, ViewModels)
│
├── WarehouseMobile/                    Android mobile client
│   ├── app/                            Android app module
│   ├── WarehouseMobile_SPEC.md         Spec (1751 lines, RU)
│   └── WHMobile_TZ.md                  Tech requirements
│
├── Warehouse_frontend/                 TypeScript frontend (placeholder)
│   └── src/index.ts                    Single console.log
│
├── docs/adr/                           Solution-level ADRs
├── plans/                              Roadmap plans
└── Root docs: README, ARCHITECTURE, INDEX, AI_CONTEXT, AI_ENTRY_POINTS, MEMORY, API_MAP, Domain_model, Role Matrix
```

## Main Modules

### SyncServer
- `app/api/` — Auth, admin, catalog, operations, balances, sync, documents, recipients, reports, health, temporary-items, assets
- `app/services/` — Identity, access, operations, catalog admin, sync, documents, event processing, machine service
- `app/repos/` — One repo per entity group, grouped under `UnitOfWork`
- `app/models/` — User, Site, Device, Category, Unit, Item, InventorySubject, Operation, Balance, etc.

### Warehouse_web
- `apps/sync_client/` — Base HTTP client, auth, admin, catalog, operations, balances, recipients, assets, temporary-items, access wrappers
- `apps/users/` — Django auth, SyncUserBinding, role mirror
- `apps/catalog/` — Catalog browse/management UI (some legacy local models)
- `apps/operations/` — Operation creation, submission, cancellation UI
- `apps/balances/` — Balance browse UI
- `apps/admin_panel/` — Root admin panel
- `apps/catalog_cache/` — Local catalog cache

### WarehouseAIWorkstation
- `Presentation/` — 30+ pages: settings, diagnostics, catalog, operations, balances, chat workspace, AI session, recommendations
- `Application/` — Settings, diagnostics, navigation, chat foundation, token estimation, prompt building
- `Infrastructure/Storage/` — SQLite repos (18) + migrations (4)
- `Integrations.Sync/` — Health, auth context, catalog read, device ping
- `Integrations.AI/` — OpenAI-compatible diagnostics, model listing

### Other Clients
- `WarehouseDesktop/` — 5-project layered WPF client (less developed)
- `WarehouseMobile/` — Android with offline sync, barcode/QR scanning (spec exists)
- `Warehouse_frontend/` — Placeholder TypeScript project

## Entry Points

| Entry | File |
|---|---|
| SyncServer | `SyncServer/main.py` |
| Warehouse_web CLI | `Warehouse_web/manage.py` |
| Warehouse_web WSGI | `Warehouse_web/config/wsgi.py` |
| WarehouseAIWorkstation | `src/WarehouseAIWorkstation.App/App.xaml.cs` |
| WarehouseDesktop | `WarehouseDesktop.Wpf/App.xaml` |
| WarehouseMobile | Android Activity (not confirmed) |
| Warehouse_frontend | `src/index.ts` |

## Important Models / Schemas

**Authoritative (SyncServer):** `User`, `UserAccessScope`, `Site`, `Device`, `Category`, `Unit`, `Item`, `TemporaryItem`, `InventorySubject`, `Operation`, `OperationLine`, `Balance`, `PendingAcceptanceBalance`, `LostAssetBalance`, `IssuedAssetBalance`, `Recipient`, `Document`, `Event`

**Technical (Warehouse_web):** `UserProfile`, `SyncUserBinding`, `Site` (mirrored), `CatalogCacheItem`

**Local (WarehouseAIWorkstation):** `AppSettings`, `ChatSession`, `ChatMessage`, `ModelProfile`, `DiagnosticsSummary`

## Important Services / Use Cases

| Project | Key Services |
|---|---|
| SyncServer | `identity_service.py`, `access_service.py`, `operations_service.py`, `sync_service.py`, `document_service.py`, `event_ingest.py`, `uow.py` |
| Warehouse_web | `apps/sync_client/*.py` (16 wrappers), `apps/users/services.py`, `apps/operations/services.py` |
| WarehouseAIWorkstation | `SettingsService`, `DiagnosticsService`, `NavigationService`, `InMemoryChatSessionStore`, `ModelProfileService`, `PromptContextBuilder` |

## Important Configuration Files

| File | Purpose |
|---|---|
| `SyncServer/app/core/config.py` | Pydantic Settings (env vars) |
| `SyncServer/.env.example` | Env template |
| `SyncServer/alembic.ini` | Alembic config |
| `SyncServer/pytest.ini` | Test config, markers |
| `SyncServer/docker-compose.yml` | API + migration services |
| `Warehouse_web/config/settings/base.py` | Django base settings |
| `Warehouse_web/config/settings/development.py` | Dev overrides |
| `Warehouse_web/config/settings/production.py` | Prod overrides |
| `Warehouse_web/.env` | Django env vars |
| `Warehouse_web/docker-compose.yml` | Gunicorn deployment |
| `WarehouseDesktop/WarehouseDesktop.Wpf/appsettings.json` | WPF settings |

## Infrastructure / Deployment Files

- `SyncServer/Dockerfile` — Python 3.13-slim, uvicorn
- `SyncServer/docker-compose.yml` — API + migration services
- `Warehouse_web/Dockerfile` — Python 3.12-slim, Gunicorn
- `Warehouse_web/docker-compose.yml` — Gunicorn web service
- `Warehouse_web/entrypoint.sh` — Migrate + collectstatic
- `Warehouse_web/DEPLOYMENT.md` — Deployment guide
- No CI/CD pipeline files found (GitHub Actions, etc.)

## Tests

| Project | Test Directory | Framework | Files |
|---|---|---|---|
| SyncServer | `SyncServer/tests/` | pytest, pytest-asyncio | 38+ test files + `stand/` |
| Warehouse_web | `Warehouse_web/apps/*/tests.py` | Django test | Minimal |
| WarehouseAIWorkstation | `WarehouseAIWorkstation/tests/` | .NET test | Present |
| WarehouseDesktop | `WarehouseDesktop.Tests/` | .NET test | Present |

**SyncServer test markers:** `unit`, `stand`, `integration`, `e2e`, `smoke`, `serial`, `destructive`, `requires_reset`, `stand_db`

## Architecture Decisions

### Solution-Level ADRs (`docs/adr/`)
- [ADR-0001](docs/adr/0001-syncserver-source-of-truth.md) — SyncServer As Source Of Truth
- [ADR-0002](docs/adr/0002-warehouse-web-through-syncserver-api.md) — Warehouse_web Through SyncServer API
- [ADR-0003](docs/adr/0003-layered-backend-with-unit-of-work.md) — Layered Backend With Unit Of Work
- [ADR-0004](docs/adr/0004-operation-driven-inventory-and-derived-balances.md) — Operation-Driven Inventory And Derived Balances
- [ADR-0005](docs/adr/0005-token-auth-and-site-scoped-access.md) — Token Auth And Site-Scoped Access

### Project-Level ADRs
- `SyncServer/docs/adr/` (6 records)
- `WarehouseAIWorkstation/docs/adr/` (6 records)
- `Warehouse_web/docs/adr/`

## Open Uncertainties

- **WarehouseMobile code maturity** — Spec exists but source code not fully verified
- **WarehouseDesktop completeness** — Structure present but development level unclear. Minimal App.xaml.
- **Warehouse_frontend intent** — Placeholder with single console.log. Future purpose unknown.
- **Production deployment strategy** — Dockerfiles exist for SyncServer and Warehouse_web, but production hosting, CI/CD, and scaling strategy not documented
- **Cross-project integration testing** — Individual test suites exist but no end-to-end cross-project test harness found
- **API versioning strategy** — `/api/v1` implies versioning but no v2 or deprecation policy visible
- **AI workstation production readiness** — Multiple planned features not implemented yet (`IAiConversationService`, tool registry)
