# ADR-0001: SyncServer As Source Of Truth

## Status
Accepted

## Context
The repository contains a FastAPI backend (`SyncServer`) and multiple client applications (Django web client, WPF desktop clients, Android mobile client, TypeScript frontend). All clients need access to users, sites, catalog data, operations, balances, documents, and synchronization state. Without clear ownership, the same warehouse state could be edited in multiple places and business rules would diverge.

## Evidence
- `SyncServer/app/services/` — All warehouse business logic (22 modules): identity, access, operations, catalog admin, sync, documents
- `SyncServer/app/repos/` — All persistence logic (16 modules) bound to syncserver PostgreSQL
- `SyncServer/app/models/` — Authoritative warehouse entities (18 SQLAlchemy ORM models)
- `Warehouse_web/apps/sync_client/` — Django calls SyncServer via 16 HTTP client wrappers, never accesses SyncServer DB directly
- `Warehouse_web/apps/catalog/models.py` — local catalog ORM was removed from active domain ownership; SyncServer is authoritative
- `WarehouseAIWorkstation/src/Integrations.Sync/` — WPF client routes all warehouse access through SyncServer HTTP API
- `ARCHITECTURE.md` — Explicitly states "SyncServer is the single source of truth"
- All `.gitignore` entries — Each project is a separate repository with independent code

## Decision
`SyncServer` owns warehouse domain data and warehouse business rules. Authoritative persistence lives in `SyncServer` and its PostgreSQL database. All other projects (`Warehouse_web`, `WarehouseAIWorkstation`, `WarehouseDesktop`, `WarehouseMobile`, `Warehouse_frontend`) must consume `SyncServer` APIs instead of owning warehouse state independently.

## Consequences

### Pros
- One authoritative warehouse state, one place for validation, permissions, and workflow rules
- Easier onboarding for new clients — all integrate through the same `/api/v1` contract
- Clear separation: SyncServer as domain backend, all others as UI/display clients

### Cons
- All clients depend on `SyncServer` availability and API contracts
- Client features often require coordinated API integration work across projects
- Warehouse_frontend (placeholder) and WarehouseDesktop (less developed) haven't yet implemented full integration

## Alternatives Considered

### Option 1
Split warehouse domain ownership between `SyncServer` and `Warehouse_web`.
Why not chosen: The code and project docs consistently treat Django as a client, not a second warehouse backend.

### Option 2
Use a shared database with direct client reads and writes.
Why not chosen: Would bypass service-layer validation, access control, and operation-driven invariants already implemented in `SyncServer`.

## Confidence
- **Confirmed by code** — Multiple source files demonstrate this decision in practice
