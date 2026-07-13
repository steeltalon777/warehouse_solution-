# Index

## Current Priority Map

1. `SyncServer/` - source-of-truth backend and API contracts.
2. `Warehouse_web/` - current active Django web client and BFF.
3. `Warehouse_frontend/` - Angular shell hosted by Django; high priority.
4. `Warehouse_client_core/` - Rust offline-first core for future desktop/mobile.
5. `WarehouseDesktop/` and `WarehouseMobile/` - future clients over the core.
6. `WarehouseAIWorkstation/` - paused until explicitly resumed.

## Entry Points

| Area | Start Here |
|---|---|
| Backend app | `SyncServer/main.py` |
| Backend routes | `SyncServer/app/api/` |
| Backend services | `SyncServer/app/services/` |
| Backend tests | `SyncServer/tests/` |
| Django CLI | `Warehouse_web/manage.py` |
| Django URLs | `Warehouse_web/config/urls.py` |
| Django SyncServer client | `Warehouse_web/apps/sync_client/` |
| Django -> SyncServer transport hardening | `docs/TZ-DJANGO_SYNCSERVER_TRANSPORT_HARDENING.md` |
| Django catalog/BFF work | `Warehouse_web/apps/catalog/` |
| Django BFF endpoints | `Warehouse_web/apps/bff_api/` |
| Angular shell | `Warehouse_frontend/` |
| Playwright E2E workflow | `.github/workflows/e2e-tests.yml` |
| Offline core plan | `Warehouse_client_core/docs/Core_plan` |
| Desktop future client | `WarehouseDesktop/` |
| Mobile future client | `WarehouseMobile/` |

## Verification Commands

| Project | Command |
|---|---|
| `SyncServer/` | `python -m pytest` |
| `Warehouse_web/` | `python manage.py test` |
| `Warehouse_frontend/` | `npm run build`; `make test-e2e` for Docker-backed Playwright E2E |
| `Warehouse_client_core/` | `cargo test --workspace` once Rust workspace exists |
| `WarehouseDesktop/` | `dotnet test WarehouseDesktop.sln` when touched |
| `WarehouseMobile/` | `gradlew.bat test` when touched |
| `WarehouseAIWorkstation/` | `dotnet test WarehouseAIWorkstation.sln` only when explicitly resumed |

## Root Docs

- `AGENTS.md` - agent contract and verification matrix.
- `README.md` - project overview.
- `ARCHITECTURE.md` - current architecture.
- `AI_CONTEXT.md` - rules for AI agents.
- `AI_ENTRY_POINTS.md` - file-level starting points.
- `MEMORY.md` - stable facts.
- `API_MAP.md` - SyncServer API inventory.
- `SOLUTION_ROADMAP.md` - implementation priorities.
- `REPOSITORY_MAP.md` - project map.
- `Functional and WorkLogik.md` - canonical functional requirements.

### Key ADRs

- `docs/adr/0011-django-syncserver-internal-transport-hardening.md` - Warehouse 3.0 transport decision.
- `docs/adr/0012-deprecate-temporary-items-review-flow.md` - Temporary items → review flow deprecation.

### Active Technical Assignments

- `docs/TZ-DJANGO_SYNCSERVER_TRANSPORT_HARDENING.md` - internal transport hardening.
- `docs/TZ-NOMENCLATURE_BATCH_CATALOG_CRUD.md` - batch catalog CRUD.
- `docs/TZ-B_OPERATIONS_DELETE_CONTRACT.md` - operations delete contract.
- `docs/TZ-FRONTEND_OPERATIONS_CREATE_MODAL_REWORK.md` - create modal rework.
- `docs/TZ-OPERATIONS_LIST_TABLE_DISPLAY_REWORK.md` - operations table rework.
- `docs/TZ-SPA_OPERATIONS_ACCEPTANCE_AND_LOST_ASSETS.md` - SPA acceptance + lost assets.
- `docs/TZ-CATALOG_CREATED_BY_UPDATED_BY.md` - catalog audit fields (not started).
- `docs/TZ-ISSUED_ASSETS_REPOSITORY_OBJECTS.md` - superseded by the two TZs below.
- `docs/TZ-ISSUED_REPOSITORY_BACKEND_CONTRACT.md` - SyncServer + BFF contract for issue-object categories, tree, and register math.
- `docs/TZ-ISSUED_REPOSITORY_FRONTEND_WORKSPACE.md` - 40/60 repository workspace, sidebar entry, operation modal prefill.
- `docs/TZ-DOCUMENT_PDF_RENDERING_AND_UI.md` - PDF rendering.
- `docs/TZ-DJANGO_ADMIN_PREDEPLOY_HARDENING.md` - ✅ реализовано (2026-07-11): admin security, credential redaction, sync saga, audit, Playwright.
- `docs/TZ-V3.1G_OPERATIONS_UX_HARDENING.md` - operations UX hardening (submit errors, field-level propagation, PDF verification).
- [TZ-V3.1I — Waybill Pagination & Draft Sync Hardening](TZ-V3.1I_WAYBILL_PAGINATION_AND_SYNC_HARDENING.md) (rev. 4, 2026-07-08) — 4 архитектурных дефекта накладной, план из 10 этапов. **rev. 4 активировал plan B (exact-rows) после того, как WeasyPrint flexbox не закрепил подпись внизу первой страницы** (баг 08.07.2026). 3 разных layout (first/middle/last), MOVE = 4 подписи.

### Architecture Reviews

- [Architecture review — V3.1I waybill pagination](reviews/architecture-review-v3.1i-waybill-pagination.md) (2026-07-08) — ревью TZ-V3.1I rev. 1, 1 blocker + 11 warnings + 2 notes.
- [Architecture review — Django Admin pre-deploy hardening](docs/reviews/architecture-review-django-admin-predeploy-hardening.md) (2026-07-11) — approved with conditions; deployment remains NO-GO until security and consistency evidence is complete.

## Rules To Remember

- SyncServer owns warehouse truth.
- Django is the active web client and BFF.
- Django -> SyncServer stays on `/api/v1` HTTP/JSON for Warehouse 3.0; harden `apps/sync_client` before considering alternate transports.
- Angular must run through Django.
- Future offline clients must share `Warehouse_client_core`.
- AI workstation is out of routine scope.
