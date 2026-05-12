# AI Context

This file explains how an AI agent should understand and reason about this repository. It describes the actual architecture, layer rules, modification constraints, and safe working patterns — all supported by repository evidence.

## System Architecture

- The root repository is a **documentation/workspace layer**, not an application runtime
- **6 nested project repositories** exist under the root, each treated as an independent git repo
- **SyncServer** is the **authoritative backend** and **single source of truth** for warehouse domain data
- **All other projects are API-consuming clients** that communicate with SyncServer via HTTP only
- No shared database between projects. Each project manages its own persistence.

**Confirmed by code:** `.gitignore` excludes all nested projects. Each has its own `.git` directory.

## Layer Rules

### SyncServer (Backend) — Confirmed by Code

| Where | What to put there | What NOT to put there |
|---|---|---|
| `app/api/` | Thin route handlers: auth wiring, request parsing, response mapping | Business logic, direct DB queries |
| `app/services/` | Business rules, access control, operation workflows, sync processing | HTTP-specific logic, raw SQL |
| `app/repos/` | SQLAlchemy query helpers, persistence logic | Business rules, auth checks |
| `app/services/uow.py` | Transaction boundary | — |
| `app/models/` | Authoritative SQLAlchemy ORM entities | API DTOs, service logic |
| `app/schemas/` | Pydantic request/response DTOs | ORM entities, business logic |
| `app/core/config.py` | Env-based settings via Pydantic Settings | — |
| `app/core/db.py` | Engine + async session factory | — |

### Warehouse_web (Django Client) — Confirmed by Code

| Where | What to put there | What NOT to put there |
|---|---|---|
| `config/urls.py` | URL-to-view routing | — |
| `apps/*/views.py` | Request rendering, context prep, form handling | Business rules, domain data mutations |
| `apps/*/services.py` | UI orchestration, local state management | Direct SyncServer DB queries |
| `apps/sync_client/` | ALL SyncServer HTTP access | Domain business rules |
| `apps/*/models.py` | Django ORM models (technical state only) | Authoritative warehouse entities |
| `templates/` | Django SSR templates | — |

**Critical rule:** New SyncServer HTTP calls MUST go through `apps/sync_client/`, never through ad-hoc `httpx` calls in views.

### WarehouseAIWorkstation (WPF Desktop) — Confirmed by Code

| Where | What to put there | What NOT to put there |
|---|---|---|
| `Presentation/` | WPF Views, ViewModels, converters, navigation | Direct HTTP calls, file I/O |
| `Application/` | Orchestration services, settings/diagnostics/chat logic | Low-level I/O, HTTP details |
| `Infrastructure/` | Local persistence (JSON settings, DPAPI secrets, SQLite) | Presentation logic |
| `Integrations.Sync/` | SyncServer HTTP clients | Business logic |
| `Integrations.AI/` | OpenAI-compatible chat client | Business logic |
| `Domain/` | Chat/settings/AI models | I/O, infrastructure |

### WarehouseDesktop (WPF Desktop) — Inferred from Structure

- Follows same layered pattern: Wpf → Application → Contracts → Domain → Infrastructure
- **Not confirmed** — code maturity not verified

### WarehouseMobile (Android) — Inferred from Spec

- Room/SQLite for local cache, HTTP for SyncServer API
- **Not confirmed** — source code structure not verified

### Warehouse_frontend (TypeScript) — Confirmed by Code

- **Placeholder.** Currently a single `console.log`. No architecture rules applicable.

## Modification Rules

### What Changes Together

- API route + service + repo + schema are a tight vertical slice in SyncServer. Adding a new endpoint typically requires changes in all four layers.
- New SyncServer feature + Warehouse_web client wrapper (`apps/sync_client/`) + Django view/template.
- WarehouseAIWorkstation: new API integration → new typed client in `Integrations.Sync/` + new use in `Application/` + new page in `Presentation/`.

### Sensitive Areas (Extra Caution Required)

- `SyncServer/app/services/operations_service.py` — Core warehouse workflow: creating, submitting, canceling operations triggers balance derivation and document generation.
- `SyncServer/app/services/identity_service.py` — User auth, token management, sync-user flow.
- `SyncServer/app/services/uow.py` — Transaction boundary. Breaking this breaks data consistency.
- `Warehouse_web/apps/sync_client/` — SyncServer API wrappers. Changes here affect all Django views.
- `SyncServer/alembic/versions/` — Schema migrations. Run only through Alembic.
- `.env` files — Contain secrets (tokens). Never commit or hardcode token values.

### What Requires Extra Caution

- **Never bypass UoW** in SyncServer services. All mutations go through it.
- **Never write domain data directly** to Warehouse_web local DB models that duplicate SyncServer entities.
- **Never change operation state directly** in DB. Use service methods that enforce workflow rules.
- **Auth tokens in Warehouse_web `.env`** — if expired, all Django ↔ SyncServer integration breaks.
- **SyncServer migrations** — test against a copy of production schema before applying.

## Database / Persistence Rules

### SyncServer — Confirmed by Code

- **ORM:** SQLAlchemy 2.0 async with asyncpg driver
- **Connection:** Configured via `DATABASE_URL` env var in `app/core/config.py`
- **Migrations:** Alembic (`alembic/versions/`, 9 migration scripts). Run `alembic upgrade head` to migrate.
- **Transactions:** All repo operations go through `UnitOfWork` in `app/services/uow.py`. Transaction begins when UoW is created, commits on explicit `commit()`, rolls back on exception.
- **Migration creation:** `alembic revision --autogenerate -m "description"`

### Warehouse_web — Confirmed by Code

- **ORM:** Django ORM
- **DB:** SQLite in development, PostgreSQL in production (configured via `config/settings/`)
- **Migrations:** `python manage.py makemigrations` / `python manage.py migrate`
- **Local models only** — Django DB stores technical state (auth, sessions, cache), NOT authoritative warehouse data

### WarehouseAIWorkstation — Confirmed by Code

- **Local storage:** SQLite (`Infrastructure/Storage/Migrations/` — 4 custom .NET migration classes)
- **Settings:** JSON files in `%AppData%/WarehouseAIWorkstation`
- **Secrets:** DPAPI-protected `secrets.dat` in `%AppData%/WarehouseAIWorkstation`
- **Chat state:** In-memory only (`InMemoryChatSessionStore`). Not persisted across restarts.

### WarehouseMobile — Inferred from Spec

- **Room/SQLite** for local catalog and operation cache
- **Not confirmed** — actual schema details not verified

## Client / Interface Rules

### HTTP API (SyncServer) — Confirmed by Code

- **Base URL:** `/api/v1`
- **Auth headers:**
  - `X-User-Token: <uuid>` — user flows (auth, admin, catalog, operations, balances)
  - `X-Device-Token: <uuid>` — device sync flows (ping, push, pull)
  - `Authorization: Bearer <token>` — legacy `/business/*` routes only
- **Optional context headers:** `X-Device-Id`, `X-Site-Id`
- **Content-Type:** `application/json`
- **Roles:** `root` (global), `chief_storekeeper` (site admin), `storekeeper` (operational), `observer` (read-only)

### Browser Interface (Warehouse_web) — Confirmed by Code

- **URL routing:** `config/urls.py` → app-level URL includes
- **Templates:** `templates/` (60+ Django templates)
- **Auth:** Django sessions + SyncServer token binding via `SyncUserBinding`

### Desktop Interfaces — Confirmed by Code

- **WarehouseAIWorkstation:** WPF MVVM pattern. `Presentation/` contains Views + ViewModels for 30+ pages. Navigation via `NavigationService`.
- **WarehouseDesktop:** WPF with similar MVVM structure. Less developed.

### Mobile Interface — Inferred from Spec

- **WarehouseMobile:** Android with Kotlin Compose UI (inferred). Barcode/QR scanning support.

## Architecture Constraints

1. **SyncServer is the single source of truth** — All warehouse domain writes go through SyncServer. No other project creates, updates, or deletes catalog items, operations, balances, or documents directly. — Confirmed by code
2. **API-only integration** — Clients communicate with SyncServer through `/api/v1` HTTP only. No shared database access. — Confirmed by code
3. **Root repo is documentation-first** — No application code at root level. Only docs, ADRs, AI navigation files, and helper scripts. — Confirmed by code
4. **Operation-driven inventory** — Balances and asset registers are derived from operations, never directly edited. — Confirmed by code
5. **Site-scoped access** — Non-root users only see data for sites in their `UserAccessScope`. — Confirmed by code
6. **Thin controllers** — HTTP routes handle auth wiring, request parsing, response mapping. All business rules in services. — Confirmed by code
7. **Layered isolation** — Each layer calls only the layer directly below it. Presentation → Application → Infrastructure/Integration. No cross-layer bypassing. — Confirmed by code
8. **Warehouse_web local DB is technical only** — Must not become an alternate domain owner. — Inferred from ADR-0002
9. **SyncServer access posture for AI Workstation** — Prefer `observer` role for AI, use `storekeeper` only for human-operated drafting. Keep `chief_storekeeper` and `root` outside routine workstation usage. — Confirmed by WarehouseAIWorkstation ARCHITECTURE.md

## Safe Working Notes for AI Agents

### What to Inspect First

1. `ARCHITECTURE.md` — Understand the overall system
2. `INDEX.md` — Navigate to the right project
3. `AI_ENTRY_POINTS.md` — Find entry points for the target project
4. Project-specific README.md and ARCHITECTURE.md for detailed rules
5. Test files — Understand expected behavior before making changes

### What Not to Assume

- **Do not assume** all projects are equally mature. SyncServer is the most developed, Warehouse_frontend is a placeholder.
- **Do not assume** warehouse domain data can be stored locally in any client project.
- **Do not assume** Warehouse_web local models (`catalog/models.py`) are authoritative. They are legacy tails.
- **Do not assume** CI/CD or automated deployment exists. No pipeline config files found.
- **Do not assume** WarehouseDesktop and WarehouseMobile are fully functional. Code maturity not verified.
- **Do not assume** the `.env` files contain valid tokens. Always verify connectivity before making integration changes.

### What to Verify After Changes

- **SyncServer:** Run `pytest` from `SyncServer/`. Check both unit and stand tests. Verify no migration divergence.
- **Warehouse_web:** Run `python manage.py test` from `Warehouse_web/`. Verify SyncServer API connectivity.
- **WarehouseAIWorkstation:** Build the solution (`dotnet build` from `src/`). Run test project.
- **Integration:** After changing `Warehouse_web/apps/sync_client/`, verify both: SyncServer API behavior + Django view rendering.
- **Schema changes:** Run `alembic upgrade head` after any migration changes. Test both upgrade and downgrade paths.
- **Auth changes:** Verify with both root and non-root tokens. Test site-scoped access boundaries.
- **Cross-project:** After SyncServer API changes, verify Warehouse_web sync_client wrappers still work. Check WarehouseAIWorkstation integration clients if affected.
