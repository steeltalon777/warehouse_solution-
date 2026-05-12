# Memory

Stable architectural knowledge about the Warehouse Solution workspace. Useful for future humans and AI agents working with this codebase. Not a changelog. Not speculative.

## System Architecture

- The root repository is a **shared solution workspace** for documentation and AI-agent orientation. It contains **no application code**.
- **6 nested project repositories** exist under the root:
  1. **SyncServer** — Authoritative FastAPI backend (most mature, most tested)
  2. **Warehouse_web** — Django SSR web client and admin integration layer
  3. **WarehouseAIWorkstation** — WPF desktop AI-powered warehouse analysis workstation
  4. **WarehouseDesktop** — WPF desktop client (less developed)
  5. **WarehouseMobile** — Android mobile client (spec exists, code maturity not verified)
  6. **Warehouse_frontend** — TypeScript placeholder (no application logic)
- **SyncServer is the single source of truth** for warehouse domain data and business rules
- **All other projects are API-consuming clients** that communicate with SyncServer through HTTP
- Each nested project is an independent git repository (confirmed by individual `.git` dirs and root `.gitignore`)
- Network architecture: `Clients → HTTP(/api/v1) → SyncServer → PostgreSQL`

## Core Entities / Core Concepts

### Authoritative Domain Entities (SyncServer)

**Identity & Access:**
- `User` — Domain user with UUID, role (root/chief_storekeeper/storekeeper/observer), user_token
- `UserAccessScope` — Per-site access: can_view, can_operate, can_manage_catalog
- `Site` — Warehouse site with code, name, is_active
- `Device` — Registered sync device with UUID, device_token, associated site

**Catalog:**
- `Category` — Hierarchical item categories (tree structure, parent_id)
- `Unit` — Measurement units (name, symbol, sort_order)
- `Item` — Catalog items (sku, name, category, unit)
- `TemporaryItem` — Items pending resolution (not yet in catalog)
- `InventorySubject` — Stable stock identity for both items and temporary items

**Operations & Inventory:**
- `Operation` — Warehouse operation (ACCEPTANCE, ISSUE, MOVEMENT, INVENTORY) with status lifecycle (DRAFT → SUBMITTED → COMPLETED / CANCELED)
- `OperationLine` — Individual lines within an operation (item, quantity)
- `Balance` — Derived item balances per site
- `PendingAcceptanceBalance` — Items pending acceptance
- `LostAssetBalance` — Lost items register
- `IssuedAssetBalance` — Issued items register
- `OperationAcceptanceAction` — Acceptance action records

**Other:**
- `Recipient`, `RecipientAlias` — External recipients for issue operations
- `Document` — Generated documents (waybill PDFs) from operation snapshots
- `Event` — Idempotent sync events for device push/pull

### Technical Entities (Warehouse_web)
- `UserProfile` — Django user extension
- `SyncUserBinding` — Django user → SyncServer user UUID + token binding
- `Site` — Mirrored from SyncServer (reference only, not authoritative)
- `CatalogCacheItem` — Local catalog cache for UX performance

### Legacy Models (Known Drift)
- `Warehouse_web/apps/catalog/models.py` — Local `Category`, `Unit`, `Item` duplicates. Not authoritative. Should be removed.
- `Warehouse_web/apps/users/models.py` `Site` — Mirror, not source of truth.

### Local Entities (WarehouseAIWorkstation)
- `AppSettings` — Non-secret runtime config
- `SecretSettings` — DPAPI-protected secrets
- `ChatSession`, `ChatMessage`, `ChatAttachment` — AI chat state (in-memory only)
- `ModelProfile` — AI model identity + capabilities
- `DiagnosticsSummary` — Aggregated connectivity check results
- Local SQLite DB with 18 repository implementations for client-side caching

## Data Model Decisions

- **Inventory is operation-driven** — Balances and registers are derived from operations, never edited directly. No manual stock adjustment without an operation.
- **InventorySubject provides stable identity** — Both catalog items and temporary items get an inventory subject for stock tracking.
- **Acceptance/lost/issued states are separate registers** — Dedicated tables (PendingAcceptanceBalance, LostAssetBalance, IssuedAssetBalance) represent these states rather than status flags on a single table.
- **Documents store snapshots** — Document payloads are self-contained operation snapshots (WeasyPrint-generated from HTML templates).
- **Warehouse_web deliberately stores less state than SyncServer** — Local DB is for auth sessions, caching, and technical convenience. Never for authoritative data.

## API Design Notes

- **SyncServer exposes the canonical warehouse API under `/api/v1`**
- **Two auth token types:**
  - `X-User-Token` — User-level auth for app/admin/catalog/operations/balances
  - `X-Device-Token` — Device-level auth for sync (ping/push/pull)
- **Legacy auth:** `Authorization: Bearer <token>` only used by `/business/*` compatibility routes
- **Warehouse_web wraps all SyncServer calls** through `apps/sync_client/` (16 typed client modules) — never ad-hoc HTTP
- **OpenAPI docs** available at `/api/docs` and `/api/openapi.json`
- **Sync protocol** uses server-side sequence numbers for ordering and deduplication (ping/push/pull pattern)
- **Role matrix** (4 roles):
  - `root` — Global authority, all operations
  - `chief_storekeeper` — Site-scoped admin (catalog, devices, site management)
  - `storekeeper` — Operational user (create operations, accept goods within scope)
  - `observer` — Read-only access to all data within scope

## Business Rules

- **Root access is global** — Root users see and can mutate all sites, users, and data
- **Non-root access is site-scoped** — Controlled through `UserAccessScope` (can_view, can_operate, can_manage_catalog flags per site)
- **Operation lifecycle:** DRAFT → SUBMITTED (via submit) → COMPLETED (via acceptance or auto). Cancel available from DRAFT or SUBMITTED states.
- **Catalog master data is global** in SyncServer — All sites share the same catalog
- **Only SyncServer services may change** operations, balances, asset registers, recipients, documents, or sync events
- **Warehouse_web may cache or mirror data** locally for UX and admin convenience, but does not own warehouse truth
- **Catalog admin mutations require** `can_manage_catalog=true` on the target site for `chief_storekeeper`
- **Move operations require both** `source_site_id` and `destination_site_id`

## Known Pitfalls

1. **Root workspace mistaken for application repo** — The root is documentation-first. Actual code is in nested project repos.
2. **Legacy local catalog models in Warehouse_web** — `apps/catalog/models.py` contains `Item`, `Category`, `Unit` models that look like warehouse data but are not authoritative. Changes to these have no effect on SyncServer.
3. **Mirrored Site model** — `users/models.py` `Site` is a local mirror of SyncServer data. Do not treat as source of truth.
4. **Token dependency** — Warehouse_web runtime depends on valid tokens in `.env` (`SYNC_ROOT_USER_TOKEN`, `SYNC_DEVICE_TOKEN`). If tokens expire or are rotated, Django ↔ SyncServer integration breaks silently.
5. **Env files contain secrets** — `Warehouse_web/.env` contains real tokens. Never commit, never hardcode.
6. **Inconsistent client maturity** — Warehouse_frontend is a placeholder. WarehouseDesktop has minimal code. WarehouseMobile code maturity not verified. Don't treat all projects as equally developed.
7. **No cross-project integration tests** — Each project has its own test suite. No automated cross-project end-to-end tests verify the full stack (Browser → Warehouse_web → SyncServer → PostgreSQL).
8. **WarehouseAIWorkstation chat is foundation-only** — In-memory sessions, no actual AI model requests implemented yet (ARCHITECTURE.md confirms this).
9. **Legacy compatibility routes** — `/business/*` routes use different auth patterns and are maintained for backwards compatibility. New code should use the standard `/api/v1/` routes.
10. **SyncServer must start before other projects** — Clients depend on SyncServer API availability. No circuit breaker or retry logic visible in client code.

## Sensitive Areas

- **SyncServer `operations_service.py`** — Core warehouse operations workflow. Incorrect changes here corrupt inventory data.
- **SyncServer `uow.py`** — Transaction boundary. Removing/breaking this corrupts data consistency.
- **SyncServer alembic migrations** — Schema changes must be applied via Alembic only. Direct SQL may break migration history.
- **Warehouse_web `sync_client/` modules** — All Django→SyncServer integration passes through these. Breaking changes cascade to all views.
- **Auth tokens** — Rotating or expiring tokens breaks all client integrations.
- **Environment files** — `.env` files in all projects contain configuration that, if wrong, breaks the entire system.
- **SyncServer .env.example** — Does not contain default values. Missing any required var prevents startup.

## Integration Notes

- **Warehouse_web ↔ SyncServer:** Most comprehensively integrated client. Uses 16 typed HTTP wrappers. Auth via `X-User-Token` (user flows) and `X-Device-Token` (sync flows).
- **WarehouseAIWorkstation ↔ SyncServer:** Partial integration. Known endpoints: `/health`, `/ready`, `/auth/context`, `/catalog/items`, `/catalog/units`, `/catalog/sites`, `/ping`. Rest planned but not implemented.
- **WarehouseAIWorkstation ↔ AI:** OpenAI-compatible diagnostics (`GET /v1/models`). No live chat requests yet.
- **WarehouseDesktop ↔ SyncServer:** Integration level not confirmed.
- **WarehouseMobile ↔ SyncServer:** Planned offline-first sync with Room/SQLite local cache. Integration level not verified.
- **Docker:** SyncServer and Warehouse_web have Dockerfiles and compose files. Both connect to external `backend` network in compose.
- **No CI/CD found:** No GitHub Actions, Jenkins, or other CI pipeline config files in any project.

## Known Unknowns

1. **Production deployment strategy** — Dockerfiles exist but production hosting, orchestration, monitoring, and scaling are not documented.
2. **WarehouseDesktop purpose** — Why both WarehouseDesktop and WarehouseAIWorkstation exist as separate WPF clients is unclear. They may have been separate phases or different use cases.
3. **Warehouse_frontend purpose** — What this TypeScript project is intended to become is unknown. Could be a SPA replacement for Warehouse_web or a separate admin UI.
4. **WarehouseMobile completion state** — Specification is detailed (1751 lines) but actual implementation completeness is not verified. May be in early development.
5. **API versioning strategy** — `/api/v1` prefix implies versioning intent but no deprecation policy, v2 plans, or migration guides exist.
6. **Sync protocol robustness** — Device sync uses sequence-based ordering but edge cases (network partitions, conflict resolution, long offline periods) are not documented at solution level.
7. **Monitoring and observability** — Health checks exist (`/health`, `/ready`) but no monitoring stack (Prometheus, Grafana, etc.) is configured.
8. **Backup and disaster recovery** — No backup strategy, restore procedures, or RPO/RTO documentation found.
9. **WarehouseDesktop SyncServer integration** — The code has layered architecture but whether it actually connects to SyncServer or is a pre-integration skeleton is unknown.
10. **Cross-project release management** — How changes across SyncServer API + Warehouse_web + other clients are coordinated and released together is not documented.

## Future Directions

**Confirmed or clearly indicated:**

- Remove legacy local catalog models from `Warehouse_web` (confirmed by ADR-0002 and code comments)
- Expand integration and smoke tests across projects (inferred from test coverage notes)
- Complete WarehouseAIWorkstation chat orchestration: `IAiConversationService`, tool registry, tool execution (confirmed by WarehouseAIWorkstation ARCHITECTURE.md)
- Implement persistent chat history for WarehouseAIWorkstation (confirmed by WarehouseAIWorkstation ARCHITECTURE.md)
- Continue consolidating all domain writes behind SyncServer services (inferred from architectural principles)

**Not confirmed:**

- Whether WarehouseDesktop will be developed further or merged/retired
- Whether Warehouse_frontend will replace Warehouse_web or serve a different purpose
- Whether WarehouseMobile is planned for production or is an experimental project
- Timeline for any of the future directions above
