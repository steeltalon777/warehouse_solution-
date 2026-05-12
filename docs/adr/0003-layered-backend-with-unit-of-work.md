# ADR-0003: Layered Backend With Unit Of Work

## Status
Accepted

## Context
`SyncServer` contains multiple warehouse domains and workflows: authentication, access scopes, catalog management, operations, documents, reports, and synchronization. These flows need transaction boundaries and a predictable place for business rules versus persistence logic.

## Evidence
- `SyncServer/app/api/` — 21 thin route modules (parse requests, wire auth, delegate to services)
- `SyncServer/app/services/` — 22 business logic modules (identity, access, operations, catalog admin, sync, documents, event processing, etc.)
- `SyncServer/app/repos/` — 16 data access modules (one per entity group, SQLAlchemy query helpers)
- `SyncServer/app/services/uow.py` — UnitOfWork class grouping all repositories into one transaction boundary
- `SyncServer/app/schemas/` — 16 Pydantic DTO modules (separate from ORM models)
- `SyncServer/app/models/` — 18 SQLAlchemy ORM modules (separate from API DTOs)
- `SyncServer/app/core/db.py` — Async engine + session factory
- Layer stack visible in import chains: routes → services → UoW/repos → models

## Decision
`SyncServer` uses a layered backend structure:
- FastAPI routes in `app/api/` — thin, handle HTTP concerns
- Business logic in `app/services/` — domain rules and workflows
- Persistence logic in `app/repos/` — SQLAlchemy queries
- One request-scoped `UnitOfWork` groups repositories into a transaction boundary

## Consequences

### Pros
- Cleaner separation of concerns between HTTP, business rules, and persistence
- Explicit transaction handling across related repository calls
- Easier testing of services and repositories independently
- API DTOs decoupled from ORM models (schemas vs models directories)

### Cons
- More structural boilerplate than a flatter codebase
- Contributors must understand the route → service → repo → model boundary
- New features require changes in 3-4 layers simultaneously

## Alternatives Considered

### Option 1
Put most workflow logic directly in FastAPI routes.
Why not chosen: The current codebase already centralizes domain workflows in services and uses thin routes.

### Option 2
Put persistence and business logic together in ORM model methods (Active Record).
Why not chosen: The implemented architecture favors explicit services and repositories over model-embedded logic.

## Confidence
- **Confirmed by code** — All 4 layers (api/services/repos/models) clearly separated across the file structure
