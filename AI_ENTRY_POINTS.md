# AI Entry Points

## Root

- `AGENTS.md` - workspace agent contract.
- `ARCHITECTURE.md` - current architecture and ownership.
- `INDEX.md` - navigation and verification commands.
- `SOLUTION_ROADMAP.md` - priority roadmap.
- `Functional and WorkLogik.md` - canonical functional requirements.

### Key ADRs

- `docs/adr/0011-django-syncserver-internal-transport-hardening.md` - Warehouse 3.0 Django -> SyncServer transport decision.
- `docs/adr/0012-deprecate-temporary-items-review-flow.md` - Temporary items deprecation.

### Active Technical Assignments

- `docs/TZ-DJANGO_SYNCSERVER_TRANSPORT_HARDENING.md` - transport hardening.
- `docs/TZ-NOMENCLATURE_BATCH_CATALOG_CRUD.md` - batch catalog CRUD.
- `docs/TZ-SPA_OPERATIONS_ACCEPTANCE_AND_LOST_ASSETS.md` - SPA acceptance + lost assets.
- `docs/TZ-ISSUED_REPOSITORY_BACKEND_CONTRACT.md` - SyncServer + BFF contract for the issue repository (categories, tree, register math).
- `docs/TZ-ISSUED_REPOSITORY_FRONTEND_WORKSPACE.md` - 40/60 repository workspace, sidebar entry, operation modal prefill.
- `docs/TZ-DOCUMENT_PDF_RENDERING_AND_UI.md` - PDF rendering.
- `docs/TZ-CATALOG_CREATED_BY_UPDATED_BY.md` - catalog audit fields.

## SyncServer

- `SyncServer/AGENTS.md` - backend agent rules.
- `SyncServer/main.py` - FastAPI app composition.
- `SyncServer/app/api/` - route handlers.
- `SyncServer/app/services/` - business rules.
- `SyncServer/app/repos/` - persistence.
- `SyncServer/app/services/uow.py` - transaction boundary.
- `SyncServer/app/models/` - SQLAlchemy models.
- `SyncServer/app/schemas/` - Pydantic DTOs.
- `SyncServer/alembic/versions/` - schema migrations.
- `SyncServer/tests/` - pytest suite.

## Warehouse_web

- `Warehouse_web/AGENTS.md` - Django agent rules.
- `Warehouse_web/manage.py` - Django CLI.
- `Warehouse_web/config/urls.py` - URL routing.
- `Warehouse_web/apps/sync_client/` - SyncServer HTTP wrappers.
- `Warehouse_web/apps/sync_client/client.py` - canonical low-level Django -> SyncServer transport entry point.
- `Warehouse_web/apps/catalog/` - catalog UI and BFF work.
- `Warehouse_web/apps/bff_api/` - browser-facing BFF endpoints for Angular and Django-hosted screens.
- `Warehouse_web/apps/users/` - Django auth and SyncServer user binding.
- `Warehouse_web/apps/operations/` - operations UI.
- `Warehouse_web/templates/` - server-rendered templates.
- `Warehouse_web/apps/*/tests.py` - Django tests.

## Warehouse_frontend

- `Warehouse_frontend/AGENTS.md` - Angular shell rules.
- `Warehouse_frontend/docs/nomenculature_plan.md` - nomenclature Angular plan.
- `Warehouse_frontend/package.json` - frontend scripts.
- `Warehouse_frontend/src/` - frontend source.

## Warehouse_client_core

- `Warehouse_client_core/AGENTS.md` - Rust core rules.
- `Warehouse_client_core/docs/Core_plan` - phased offline-first plan.

## Future Clients

- `WarehouseDesktop/AGENTS.md` - future WPF offline client rules.
- `WarehouseMobile/AGENTS.md` - future Android offline client rules.

## Paused AI Workstation

- `WarehouseAIWorkstation/AGENTS.md` - paused project rules.
- Read this project only when the user explicitly resumes it.
