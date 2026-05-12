# AI Entry Points

Where an AI agent should start reading each project in this repository.

## SyncServer (Backend) — Confirmed by Code

### Server / App Entry Points
- `SyncServer/main.py` — FastAPI app composition, router mounting, CORS setup

### API / Controller Layer
- `SyncServer/app/api/deps.py` — FastAPI dependency injection (user/device identity resolution)
- `SyncServer/app/api/exceptions.py` — Custom exception classes
- `SyncServer/app/api/routes_auth.py` — `/auth/*` endpoints
- `SyncServer/app/api/routes_admin.py` — `/admin/*` CRUD base
- `SyncServer/app/api/routes_admin_users.py` — `/admin/users/*`
- `SyncServer/app/api/routes_admin_sites.py` — `/admin/sites/*`
- `SyncServer/app/api/routes_admin_devices.py` — `/admin/devices/*`
- `SyncServer/app/api/routes_admin_access.py` — `/admin/access/*`
- `SyncServer/app/api/routes_catalog.py` — `/catalog/*` read API
- `SyncServer/app/api/routes_catalog_admin.py` — `/catalog/admin/*` mutations
- `SyncServer/app/api/routes_operations.py` — `/operations/*`
- `SyncServer/app/api/routes_balances.py` — `/balances/*`
- `SyncServer/app/api/routes_documents.py` — `/documents/*`
- `SyncServer/app/api/routes_sync.py` — `/sync/*` (ping/push/pull)
- `SyncServer/app/api/routes_recipients.py` — `/recipients/*`
- `SyncServer/app/api/routes_reports.py` — `/reports/*`
- `SyncServer/app/api/routes_temporary_items.py` — `/temporary-items/*`
- `SyncServer/app/api/routes_health.py` — `/health`, `/ready`
- `SyncServer/app/api/routes_assets.py` — `/assets/*`

### Service / Use Case Layer
- `SyncServer/app/services/identity_service.py` — User identity, auth, token management
- `SyncServer/app/services/access_service.py` — Access control, scope management
- `SyncServer/app/services/operations_service.py` — Operation lifecycle (create/submit/cancel)
- `SyncServer/app/services/catalog_admin_service.py` — Catalog mutations (items, categories, units)
- `SyncServer/app/services/sync_service.py` — Device sync processing (ping/push/pull)
- `SyncServer/app/services/document_service.py` — Document generation (WeasyPrint HTML→PDF)
- `SyncServer/app/services/event_ingest.py` — Idempotent event processing from device sync
- `SyncServer/app/services/temporary_items_resolution_service.py` — Temporary item lifecycle
- `SyncServer/app/services/uow.py` — Unit of Work (transaction boundary)
- `SyncServer/app/services/*.py` — 22 service modules total

### Repository / Data Layer
- `SyncServer/app/repos/users_repo.py`
- `SyncServer/app/repos/sites_repo.py`
- `SyncServer/app/repos/devices_repo.py`
- `SyncServer/app/repos/catalog_repo.py`
- `SyncServer/app/repos/operations_repo.py`
- `SyncServer/app/repos/balances_repo.py`
- `SyncServer/app/repos/documents_repo.py`
- `SyncServer/app/repos/events_repo.py`
- `SyncServer/app/repos/recipients_repo.py`
- `SyncServer/app/repos/temporary_items_repo.py`
- `SyncServer/app/repos/asset_registers_repo.py`
- `SyncServer/app/repos/inventory_subjects_repo.py`
- `SyncServer/app/repos/machine_repo.py`
- `SyncServer/app/repos/reports_repo.py`
- `SyncServer/app/repos/user_access_scopes_repo.py`
- `SyncServer/app/repos/__init__.py` — 16 repo modules total

### Models / Entities / Schemas
- `SyncServer/app/models/` — 18 SQLAlchemy ORM model files + `base.py`
- `SyncServer/app/schemas/` — 16 Pydantic DTO modules

### Config / Settings
- `SyncServer/app/core/config.py` — Pydantic Settings (DATABASE_URL, SYNC_ROOT_USER_TOKEN, etc.)
- `SyncServer/app/core/db.py` — Async SQLAlchemy engine + session factory
- `SyncServer/app/core/identity.py` — Identity helpers
- `SyncServer/.env.example` — Env template
- `SyncServer/alembic.ini` — Alembic migration config
- `SyncServer/pytest.ini` — Pytest config with markers

### Infra / Deployment
- `SyncServer/Dockerfile` — Python 3.13-slim, uvicorn
- `SyncServer/docker-compose.yml` — syncserver + migrate services

### Test Entry Points
- `SyncServer/tests/conftest.py` — Global test fixtures
- `SyncServer/tests/stand/` — Integration/e2e/smoke test directory
- `SyncServer/tests/test_auth_routes.py` — Auth API tests
- `SyncServer/tests/test_operations_*.py` — Operation tests (5 files)
- `SyncServer/tests/test_catalog_*.py` — Catalog tests (3 files)
- `SyncServer/tests/test_balances_*.py` — Balance tests (2 files)
- `SyncServer/tests/test_http_sync.py` — Sync protocol tests
- `SyncServer/tests/test_temporary_items_*.py` — Temporary items tests (4 files)
- `SyncServer/tests/test_health_*.py` — Health check tests
- `SyncServer/tests/test_document*.py` — Document tests (4 files)
- `SyncServer/tests/test_events_repo.py`, `test_reports_read_model.py`, `test_access_service_business_access.py`, etc.
- 38+ test files total

---

## Warehouse_web (Django Client) — Confirmed by Code

### Server / App Entry Points
- `Warehouse_web/manage.py` — Django CLI
- `Warehouse_web/config/wsgi.py` — WSGI (production via Gunicorn)
- `Warehouse_web/config/asgi.py` — ASGI
- `Warehouse_web/entrypoint.sh` — Container startup (migrate + collectstatic)

### API / Controller Layer
- `Warehouse_web/config/urls.py` — Root URL routing
- `Warehouse_web/apps/catalog/views.py`
- `Warehouse_web/apps/operations/views.py`
- `Warehouse_web/apps/balances/views.py`
- `Warehouse_web/apps/client/views.py`
- `Warehouse_web/apps/admin_panel/views.py`
- `Warehouse_web/apps/documents/views.py`
- `Warehouse_web/apps/temporary_items/views.py`
- `Warehouse_web/apps/users/sync_views.py` — Auth views
- `Warehouse_web/apps/users/admin.py` — Django admin

### SyncServer Client Layer (HTTP Integration)
- `Warehouse_web/apps/sync_client/client.py` — Base HTTP client
- `Warehouse_web/apps/sync_client/auth_api.py`
- `Warehouse_web/apps/sync_client/admin_api.py`
- `Warehouse_web/apps/sync_client/catalog_api.py`
- `Warehouse_web/apps/sync_client/operations_api.py`
- `Warehouse_web/apps/sync_client/balances_api.py`
- `Warehouse_web/apps/sync_client/recipients_api.py`
- `Warehouse_web/apps/sync_client/assets_api.py`
- `Warehouse_web/apps/sync_client/temporary_items_api.py`
- `Warehouse_web/apps/sync_client/access_api.py`
- `Warehouse_web/apps/sync_client/auth_integration.py`
- `Warehouse_web/apps/sync_client/session_auth.py`
- `Warehouse_web/apps/sync_client/root_admin_client.py`
- `Warehouse_web/apps/sync_client/simple_client.py`
- 16 client modules total

### Service Layer
- `Warehouse_web/apps/users/services.py` — User sync/orchestration
- `Warehouse_web/apps/catalog/services.py` — Catalog orchestration
- `Warehouse_web/apps/catalog_cache/services.py` — Cache sync
- `Warehouse_web/apps/operations/services.py`
- `Warehouse_web/apps/client/services.py`

### Models / Entities
- `Warehouse_web/apps/users/models.py` — UserProfile, SyncUserBinding, Site (mirrored)
- `Warehouse_web/apps/catalog/models.py` — **LEGACY** local catalog models (not authoritative)
- `Warehouse_web/apps/catalog_cache/models.py` — CatalogCacheItem

### Config / Settings
- `Warehouse_web/config/settings/base.py`
- `Warehouse_web/config/settings/development.py`
- `Warehouse_web/config/settings/production.py`
- `Warehouse_web/.env` — Environment variables

### Infra / Deployment
- `Warehouse_web/Dockerfile` — Python 3.12-slim, Gunicorn
- `Warehouse_web/docker-compose.yml`
- `Warehouse_web/entrypoint.sh`
- `Warehouse_web/DEPLOYMENT.md`

### Templates
- `Warehouse_web/templates/base.html` — Base layout
- `Warehouse_web/templates/catalog/` — Catalog templates (partials, browse, manage)
- `Warehouse_web/templates/operations/` — Operation templates
- `Warehouse_web/templates/balances/` — Balance templates
- `Warehouse_web/templates/client/` — Client dashboard
- `Warehouse_web/templates/admin_panel/` — Admin panel
- `Warehouse_web/templates/temporary_items/` — Temporary items
- `Warehouse_web/templates/includes/` — Navbar, sidebar, brand
- 60+ template files

### Static Assets
- `Warehouse_web/static/css/app.css`
- `Warehouse_web/static/js/operations_create.js`
- `Warehouse_web/static/js/ui_components.js`

---

## WarehouseAIWorkstation (WPF AI Desktop) — Confirmed by Code

### App Entry Point
- `WarehouseAIWorkstation/src/WarehouseAIWorkstation.App/App.xaml.cs` — WPF startup
- `WarehouseAIWorkstation/src/WarehouseAIWorkstation.App/Bootstrap/HostingExtensions.cs`
- `WarehouseAIWorkstation/src/WarehouseAIWorkstation.App/Bootstrap/ServiceCollectionExtensions.cs`
- `WarehouseAIWorkstation/src/WarehouseAIWorkstation.App/Bootstrap/NavigationExtensions.cs`
- `WarehouseAIWorkstation/src/WarehouseAIWorkstation.App/ShellWindow.xaml`

### Solution File
- `WarehouseAIWorkstation/WarehouseAIWorkstation.sln`

### Presentation Layer (MVVM)
- `WarehouseAIWorkstation/src/WarehouseAIWorkstation.Presentation/` — Views, ViewModels for 30+ pages

### Application Layer
- `WarehouseAIWorkstation/src/WarehouseAIWorkstation.Application/Contracts/` — 40+ service interfaces
- `WarehouseAIWorkstation/src/WarehouseAIWorkstation.Application/Models/` — Conversation models
- `WarehouseAIWorkstation/src/WarehouseAIWorkstation.Application/Services/` — 30+ implementations

### Infrastructure Layer
- `WarehouseAIWorkstation/src/WarehouseAIWorkstation.Infrastructure/Storage/Migrations/` — 4 SQLite migrations
- `WarehouseAIWorkstation/src/WarehouseAIWorkstation.Infrastructure/Storage/Repositories/` — 18 repo implementations

### Integration Layer
- `WarehouseAIWorkstation/src/WarehouseAIWorkstation.Integrations.Sync/` — SyncServer HTTP clients
- `WarehouseAIWorkstation/src/WarehouseAIWorkstation.Integrations.AI/` — OpenAI-compatible client

### Domain Models
- `WarehouseAIWorkstation/src/WarehouseAIWorkstation.Domain/` — AI, Directory, Sync, Users models

### Shared
- `WarehouseAIWorkstation/src/WarehouseAIWorkstation.Shared/` — Common utilities

### Config / Docs
- `WarehouseAIWorkstation/AI_CONTEXT.md`
- `WarehouseAIWorkstation/ARCHITECTURE.md`
- `WarehouseAIWorkstation/README.md`
- `WarehouseAIWorkstation/INDEX.md`
- `WarehouseAIWorkstation/MEMORY.md`
- `WarehouseAIWorkstation/docs/` — ADRs, stage reports, specs

### Test Entry Point
- `WarehouseAIWorkstation/tests/` — .NET test project

---

## WarehouseDesktop (WPF Desktop) — Confirmed by Code

### App Entry Point
- `WarehouseDesktop/WarehouseDesktop.Wpf/App.xaml` — WPF app entry
- `WarehouseDesktop/WarehouseDesktop.Wpf/App.xaml.cs` — Code-behind
- `WarehouseDesktop/WarehouseDesktop.Wpf/Views/MainWindow.xaml` — Main window
- `WarehouseDesktop/WarehouseDesktop.Wpf/ViewModels/MainViewModel.cs`

### Solution File
- `WarehouseDesktop/WarehouseDesktop.sln`

### Project Layers
- `WarehouseDesktop/WarehouseDesktop.Application/`
- `WarehouseDesktop/WarehouseDesktop.Contracts/`
- `WarehouseDesktop/WarehouseDesktop.Domain/`
- `WarehouseDesktop/WarehouseDesktop.Infrastructure/`
- `WarehouseDesktop/WarehouseDesktop.Wpf/` — UI, settings, navigation, converters, resources

### Config
- `WarehouseDesktop/WarehouseDesktop.Wpf/appsettings.json`

### Test Entry Point
- `WarehouseDesktop/WarehouseDesktop.Tests/`

---

## WarehouseMobile (Android) — Inferred from Structure

**Not confirmed** — Source directories not fully verified.

### Entry Points (inferred)
- `WarehouseMobile/app/src/main/` — Android app source
- `WarehouseMobile/build.gradle.kts` — Gradle build
- `WarehouseMobile/settings.gradle.kts` — Gradle settings
- `WarehouseMobile/gradle/libs.versions.toml` — Version catalog (likely)

### Spec & Requirements
- `WarehouseMobile/WarehouseMobile_SPEC.md` — Detailed spec (1751 lines, RU)
- `WarehouseMobile/WHMobile_TZ.md` — Technical requirements

---

## Warehouse_frontend (TypeScript) — Confirmed by Code

### App Entry Point
- `Warehouse_frontend/src/index.ts` — Single `console.log('Happy developing ✨')`

### Config
- `Warehouse_frontend/package.json` — TypeScript 5.5, `tsc` build script
- `Warehouse_frontend/tsconfig.json`

**Placeholder project** — No application logic implemented.

---

## Root Workspace — Confirmed by Code

### Documentation
- `README.md` — Project overview
- `ARCHITECTURE.md` — System architecture
- `INDEX.md` — Quick navigation
- `AI_CONTEXT.md` — Rules for AI agents
- `AI_ENTRY_POINTS.md` — This file
- `MEMORY.md` — Stable knowledge base
- `API_MAP.md` — Practical API reference
- `Domain_model.md` — Domain model (RU, 665 lines)
- `Role Matrix.md` — Permission matrix

### ADRs
- `docs/adr/0001-syncserver-source-of-truth.md`
- `docs/adr/0002-warehouse-web-through-syncserver-api.md`
- `docs/adr/0003-layered-backend-with-unit-of-work.md`
- `docs/adr/0004-operation-driven-inventory-and-derived-balances.md`
- `docs/adr/0005-token-auth-and-site-scoped-access.md`

### Tools
- `build_repo_map.py` — AI-friendly repo snapshot generator
- `repo_map.txt` — Auto-generated snapshot output
- `plans/` — Roadmap plans
