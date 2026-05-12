# Architecture

## System Overview

`Warehouse Solution` is a **multi-repository client-server workspace** with 6 project repositories nested under one root. The root repo is documentation-first and contains no application code.

**System type:** Multi-project client-server system
- 1 authoritative backend (SyncServer)
- 5 client applications consuming the backend API

## Current State

**Confirmed by code:**

- **SyncServer** — Active and highly developed. FastAPI backend with layered architecture (API → Services → Repos → ORM → PostgreSQL). The most mature project. **38+ test files, 9 Alembic migrations.**
- **Warehouse_web** — Active Django SSR client. 13 Django apps, ~60 templates, 16 SyncServer HTTP client wrappers. Well integrated with SyncServer.
- **WarehouseAIWorkstation** — Active WPF desktop app. 7 .NET projects with layered architecture (App → Presentation → Application → Infrastructure + Integrations). Local JSON+DPAPI storage. OpenAI-compatible AI diagnostics. SyncServer HTTP integration.
- **WarehouseDesktop** — Present but less developed WPF desktop client. 5 .NET projects (Application, Contracts, Domain, Infrastructure, Wpf).
- **WarehouseMobile** — Android/Kotlin client. Has detailed specification (`WarehouseMobile_SPEC.md`, 1751 lines) and technical requirements (`WHMobile_TZ.md`). Room/SQLite for local cache. **Not confirmed** — code maturity not assessed.
- **Warehouse_frontend** — Placeholder. TypeScript project with single `console.log` line.

**Inferred from structure:**
- All nested projects are treated as independent git repositories (each has its own `.git`)
- Every project except Warehouse_frontend uses some form of SyncServer HTTP integration
- The `.gitignore` at root level excludes all nested project directories

## High-Level Architecture

```text
┌──────────────────────────────────────────────┐
│ CLIENTS (API consumers only)                  │
│                                               │
│  Browser ──> Warehouse_web (Django SSR)       │
│               │                               │
│  Desktop ──>  WarehouseAIWorkstation (WPF)    │
│  Desktop ──>  WarehouseDesktop (WPF)          │
│  Mobile ──>   WarehouseMobile (Android)       │
│                                               │
│  All clients ──> HTTP ──> /api/v1             │
└──────────────────────────────┬───────────────┘
                               │
┌──────────────────────────────▼───────────────┐
│ SyncServer (SOURCE OF TRUTH)                  │
│                                               │
│  /api/v1/*     ──> API Routes (thin)          │
│  Services      ──> Business logic + access    │
│  Repos / UoW   ──> Data access                │
│  Models        ──> SQLAlchemy ORM             │
│                                               │
│  Storage: PostgreSQL                          │
└──────────────────────────────────────────────┘
```

**Confirmed by code:** All client-projects found in the workspace consume SyncServer API. Warehouse_web has the most complete integration (16 HTTP client wrappers). WarehouseAIWorkstation has a partial integration layer (`Integrations.Sync`).

## Application Layers

### SyncServer (Backend) — Confirmed by Code

| Layer | Location | Responsibility |
|---|---|---|
| **API / Controllers** | `SyncServer/app/api/` (21 modules) | Route handlers, auth wiring, request validation |
| **Services / Use Cases** | `SyncServer/app/services/` (22 modules) | Business rules, identity, access control, operation workflows, sync, documents |
| **Repositories** | `SyncServer/app/repos/` (16 modules) | SQLAlchemy query helpers, persistence |
| **Unit of Work** | `SyncServer/app/services/uow.py` | Transaction boundary grouping all repos |
| **Models / Entities** | `SyncServer/app/models/` (18 files) | Authoritative warehouse domain entities |
| **DTOs / Schemas** | `SyncServer/app/schemas/` (16 modules) | Pydantic request/response models |
| **Config** | `SyncServer/app/core/config.py` | Pydantic Settings (env-based) |
| **DB Engine** | `SyncServer/app/core/db.py` | Async SQLAlchemy engine + session factory |
| **Migrations** | `SyncServer/alembic/versions/` (9 files) | Alembic schema migrations |

### Warehouse_web (Django Client) — Confirmed by Code

| Layer | Location | Responsibility |
|---|---|---|
| **URL routing** | `Warehouse_web/config/urls.py` | Browser request routing |
| **Views** | `Warehouse_web/apps/*/views.py` | HTTP response rendering, context preparation |
| **Services (orchestration)** | `Warehouse_web/apps/*/services.py` | UI orchestration, local state management |
| **HTTP integration** | `Warehouse_web/apps/sync_client/` | Canonical SyncServer API wrappers (16 modules) |
| **Local models** | `Warehouse_web/apps/*/models.py` | Django ORM models (technical state only) |
| **Templates** | `Warehouse_web/templates/` (60+ HTML files) | Django SSR templates |
| **Static** | `Warehouse_web/static/` | CSS, JS assets |
| **Config** | `Warehouse_web/config/settings/` | Django settings (base, dev, production) |

### WarehouseAIWorkstation (WPF Desktop) — Confirmed by Code

| Layer | Location | Responsibility |
|---|---|---|
| **App host / bootstrap** | `src/WarehouseAIWorkstation.App/` | WPF startup, DI, host creation |
| **Presentation (MVVM)** | `src/WarehouseAIWorkstation.Presentation/` | Views, ViewModels, navigation, converters |
| **Application services** | `src/WarehouseAIWorkstation.Application/` | Orchestration, settings, diagnostics, chat foundation (40+ interfaces) |
| **Infrastructure** | `src/WarehouseAIWorkstation.Infrastructure/` | Local JSON settings, DPAPI secrets, SQLite storage (18 repos, 4 migrations) |
| **Sync integration** | `src/WarehouseAIWorkstation.Integrations.Sync/` | SyncServer HTTP client (`/health`, `/auth/context`, `/catalog/*`, `/ping`) |
| **AI integration** | `src/WarehouseAIWorkstation.Integrations.AI/` | OpenAI-compatible chat/diagnostics client |
| **Domain models** | `src/WarehouseAIWorkstation.Domain/` | Chat, settings, AI model profile entities |
| **Shared** | `src/WarehouseAIWorkstation.Shared/` | Generic utilities, `Result<T>` wrappers |

### WarehouseDesktop (WPF Desktop) — Inferred from Structure

| Layer | Location | Responsibility |
|---|---|---|
| **Application** | `WarehouseDesktop.Application/` | Application services |
| **Contracts** | `WarehouseDesktop.Contracts/` | Service interfaces |
| **Domain** | `WarehouseDesktop.Domain/` | Domain models |
| **Infrastructure** | `WarehouseDesktop.Infrastructure/` | Infrastructure services |
| **WPF UI** | `WarehouseDesktop.Wpf/` | Views, ViewModels, navigation |

**Not confirmed** — Code maturity and actual SyncServer integration level not assessed. App.xaml is minimal (6 lines, no resources defined).

### WarehouseMobile (Android) — Inferred from Structure

| Aspect | Details |
|---|---|
| **Platform** | Android with Kotlin (Gradle Kotlin DSL) |
| **Local storage** | Room/SQLite (inferred from spec) |
| **Specification** | `WarehouseMobile_SPEC.md` (1751 lines, Russian) |
| **API integration** | SyncServer HTTP (inferred from spec) |
| **Features** | Barcode/QR scanning, offline operations, sync (inferred from spec) |

**Not confirmed** — Actual source code structure and integration details not verified.

### Warehouse_frontend (TypeScript) — Confirmed by Code

Status: **Placeholder**. Single `src/index.ts` with `console.log('Happy developing ✨')`. No application logic.

## Data Model

### Authoritative Entities (SyncServer) — Confirmed by Code

Sources: `SyncServer/app/models/` (18 files), `SyncServer/alembic/versions/`

**Identity & access:**
- `User`, `UserAccessScope`, `Site`, `Device`

**Catalog:**
- `Category`, `Unit`, `Item`, `TemporaryItem`

**Operations & inventory:**
- `InventorySubject`
- `Operation`, `OperationLine`
- `Balance`
- `PendingAcceptanceBalance`, `LostAssetBalance`, `IssuedAssetBalance`, `OperationAcceptanceAction`

**Other:**
- `Recipient`, `RecipientAlias`
- `Document`, `DocumentOperation`, `DocumentSource`
- `Event`

### Technical Entities (Warehouse_web) — Confirmed by Code

Sources: `Warehouse_web/apps/users/models.py`, `Warehouse_web/apps/catalog_cache/models.py`

- `UserProfile` — Django user extension
- `SyncUserBinding` — Maps Django user to SyncServer user token
- `Site` — Mirrored from SyncServer (not authoritative)
- `CatalogCacheItem` — Local catalog cache
- Legacy local `Category`, `Unit`, `Item` models — **Known drift:** these duplicate SyncServer entities

### Local Entities (WarehouseAIWorkstation) — Confirmed by Code

Sources: `WarehouseAIWorkstation/src/WarehouseAIWorkstation.Domain/`

- `AppSettings`, `SecretSettings`
- `ChatSession`, `ChatMessage`, `ChatAttachment`
- `ModelProfile`, `TimeContext`, `TokenEstimate`
- `DiagnosticsSummary`

### Local Entities (WarehouseMobile) — Inferred from Structure

- Local Room entities for catalog, operations (inferred from spec)

## Data Flow

### Browser request through Django (Confirmed by Code)

```
Browser → Django URL → View → sync_client (httpx) → SyncServer /api/v1
                                                          → Route → Service → UoW/Repo → PostgreSQL
                                                                    ← Response
                                     ← sync_client ← Response
       ← Django renders template with response data
```

### Direct API request from desktop/mobile/device (Confirmed by Code)

```
Client → HTTP (X-User-Token / X-Device-Token) → SyncServer /api/v1
                                                      → Route → Service → UoW/Repo → PostgreSQL
                                                                ← Response
       ← JSON response
```

### Operation-driven inventory (Confirmed by Code)

```
POST /operations → Service validates → Repo persists Operation + OperationLines
                                       → Balances, acceptance/issue/lost registers derived from operations
                                       → Documents generated from operation snapshots (WeasyPrint)
```

## External Integrations

| Integration | Type | Evidence |
|---|---|---|
| PostgreSQL | Authortiative storage for SyncServer | `SyncServer/app/core/db.py`, `DATABASE_URL` env |
| Warehouse_web → SyncServer | Internal HTTP | `Warehouse_web/apps/sync_client/` (16 wrappers) |
| WarehouseAIWorkstation → SyncServer | Internal HTTP | `Integrations.Sync/` (5 typed clients) |
| WarehouseAIWorkstation → OpenAI-compatible API | External HTTP | `Integrations.AI/` (`GET /v1/models`) |
| Windows DPAPI | Local secret storage | `WarehouseAIWorkstation.Infrastructure/` |
| Room/SQLite (WarehouseMobile) | Local cache | Inferred from spec |
| Docker / docker-compose | Deployment | `SyncServer/docker-compose.yml`, `Warehouse_web/docker-compose.yml` |
| Alembic | Schema migrations for SyncServer | `SyncServer/alembic/` |
| Django migrations | Schema for web local DB | `Warehouse_web/apps/*/migrations/` |

## Architectural Constraints

1. **SyncServer is the single source of truth for warehouse domain data** — All writes to catalog, operations, balances must go through SyncServer. Other projects store only technical/caching state. — Confirmed by code
2. **No direct database access from clients** — Clients access SyncServer through `/api/v1` HTTP only. — Confirmed by code
3. **Operation-driven inventory** — Balances and registers are derived from operations, never directly edited. — Confirmed by code
4. **Site-scoped access** — Non-root users see only data for sites in their `UserAccessScope`. — Confirmed by code
5. **Token-based auth** — `X-User-Token` for user flows, `X-Device-Token` for device sync. — Confirmed by code
6. **Root workspace is documentation-first** — No shared business logic at root level. — Confirmed by code

## Known Drift / Inconsistencies

| Issue | Location | Details |
|---|---|---|
| **Legacy local catalog models** | `Warehouse_web/apps/catalog/models.py` | Local `Category`, `Unit`, `Item` models duplicate SyncServer entities. Should be removed in favor of API-only access. — Confirmed by code |
| **Legacy mirrored Site model** | `Warehouse_web/apps/users/models.py` | Local `Site` mirrors SyncServer but is not authoritative. — Confirmed by code |
| **Legacy `/business/*` compatibility routes** | `SyncServer/app/api/` | Uses `Authorization: Bearer` service tokens, different from current `X-User-Token` pattern. — Confirmed by code |
| **Legacy device-auth catalog reads** | `SyncServer/app/api/` | `POST /catalog/items|categories|units` with `X-Device-Token` alongside newer `GET` equivalents. — Confirmed by code |
| **WarehouseFrontend is placeholder** | `Warehouse_frontend/src/index.ts` | Single console.log, no real application logic. Project intent unclear. |
| **WarehouseDesktop maturity** | `WarehouseDesktop/` | Code structure present but development level not confirmed. App.xaml is minimal. |
| **WarehouseMobile code maturity** | `WarehouseMobile/` | Spec exists (1751 lines) but code maturity not verified. |
| **WarehouseMobile in .gitignore** | `.gitignore` | Excluded via `/WarehouseMobile/` unlike other projects listed without `/` prefix. — Confirmed by code |

## Architecture Decisions

See `docs/adr/` for 5 solution-level ADRs:
- ADR-0001: SyncServer as source of truth
- ADR-0002: Warehouse_web through SyncServer API (not direct DB)
- ADR-0003: Layered backend with Unit of Work
- ADR-0004: Operation-driven inventory and derived balances
- ADR-0005: Token auth and site-scoped access

Additional project-specific ADRs in:
- `SyncServer/docs/adr/` (6 records)
- `WarehouseAIWorkstation/docs/adr/` (6 records)
- `Warehouse_web/docs/adr/`

## Future Architecture

**Inferred from TODOs and plans:**

- Remove legacy local catalog models from `Warehouse_web` — Confirmed by code comments and ADR-0002
- Expand integration and smoke tests across projects — Inferred from test coverage notes
- Complete WarehouseAIWorkstation chat orchestration (`IAiConversationService`, tool registry) — Confirmed by code (ARCHITECTURE.md Future Architecture section)
- WarehouseMobile: implementation of offline-first sync with local Room cache — Inferred from specification

**Not confirmed:**
- Production deployment strategy for most clients
- CI/CD pipeline configuration (no GitHub Actions or other CI files found)
- Timeline for consolidating all clients to remove legacy tails
