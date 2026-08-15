# AI Entry Points

## Root

- `AGENTS.md` - workspace agent contract.
- `ARCHITECTURE.md` - current architecture and ownership.
- `INDEX.md` - navigation and verification commands.
- `.github/workflows/e2e-tests.yml` - GitHub Actions Playwright E2E pipeline.
- `SOLUTION_ROADMAP.md` - priority roadmap.
- `Functional and WorkLogik.md` - canonical functional requirements.
- `docs/audit/HISTORICAL_INTEGRITY_STATUS.md` - active status of historical-integrity work.

### Key ADRs

- `docs/adr/0011-django-syncserver-internal-transport-hardening.md` - Warehouse 3.0 Django -> SyncServer transport decision.
- `docs/adr/0012-deprecate-temporary-items-review-flow.md` - Temporary items deprecation.
- `docs/adr/0018-audit-architecture.md` - audit spine/resources/item effects.
- `docs/adr/0028-historical-integrity-stage-a.md` - accepted Stage A decision; implementation pending.
- `docs/adr/0029-quartermaster-document-engine.md` - QDE architecture (envelope, contracts, render-host).
- `docs/adr/0030-qde-primary-rendering-backend-typst.md` - QDE primary rendering backend = Typst.
- `docs/adr/0031-qde-ownership-and-versioning.md` - QDE ownership: monorepo component.
- `docs/adr/0032-qde-warehouse-integration-contract.md` - Warehouse → QDE integration contract.

### Active Technical Assignments

- `docs/TZ-HISTORICAL_INTEGRITY_STAGE_A.md` - executable Stage A guard/audit/effect-time/integrity-check scope.
- `docs/TZ-QDE_INTEGRATION_READINESS.md` - QDE integration readiness + Phase 6A–6F decomposition (baseline prepared, Phase 6A pending).
- `docs/TZ-DJANGO_SYNCSERVER_TRANSPORT_HARDENING.md` - transport hardening.
- `docs/TZ-PLAYWRIGHT_PIPELINE_INTEGRATION.md` - Playwright pipeline integration.
- `docs/TZ-NOMENCLATURE_BATCH_CATALOG_CRUD.md` - batch catalog CRUD.
- `docs/TZ-SPA_OPERATIONS_ACCEPTANCE_AND_LOST_ASSETS.md` - SPA acceptance + lost assets.
- `docs/TZ-ISSUED_REPOSITORY_BACKEND_CONTRACT.md` - SyncServer + BFF contract for the issue repository (categories, tree, register math).
- `docs/TZ-ISSUED_REPOSITORY_FRONTEND_WORKSPACE.md` - 40/60 repository workspace, sidebar entry, operation modal prefill.
- `docs/TZ-DOCUMENT_PDF_RENDERING_AND_UI.md` - PDF rendering.
- `docs/TZ-CATALOG_CREATED_BY_UPDATED_BY.md` - catalog audit fields.
- `docs/TZ-OPERATIONS_FORM_REWORK_AND_VALIDATION.md` - operation form rework, restore endpoint, readonly mode, SKU removal, batch error.
- `docs/TZ-OPERATIONS_FORM_REWORK_FOLLOWUP.md` - backend tests (restore + operation_type) + e2e SKU adaptation.

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

## QuartermasterDocumentEngine

- `QuartermasterDocumentEngine/README.md` - QDE overview and status.
- `QuartermasterDocumentEngine/pyproject.toml` - own package/deps (`qm_engine`, `qm_backends`, `qm_cli`).
- `QuartermasterDocumentEngine/engine/qm_engine/` - envelope, registry, fonts, render pipeline.
- `QuartermasterDocumentEngine/backends/qm_backends/` - Typst + WeasyPrint backends.
- `QuartermasterDocumentEngine/cli/qm_cli/main.py` - `qm-render` CLI (primary integration contract).
- `QuartermasterDocumentEngine/contracts/` - envelope + document contract schemas.
- `QuartermasterDocumentEngine/templates/` + `fonts/` - bundled template packages and DejaVu fonts.
- `QuartermasterDocumentEngine/tests/` - unit/integration/component/golden suites; `tests/unit/test_architecture_boundaries.py` enforces ADR-0031 D2.
- `QuartermasterDocumentEngine/doc/` - engine-internal ADR-0001, ROADMAP, SPEC, TZ-PHASE2-BACKEND-SPIKE.

## Warehouse_frontend

- `Warehouse_frontend/AGENTS.md` - Angular shell rules.
- `Warehouse_frontend/docs/nomenculature_plan.md` - nomenclature Angular plan.
- `Warehouse_frontend/package.json` - frontend scripts.
- `Warehouse_frontend/e2e/` - Playwright specs and helpers.
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
