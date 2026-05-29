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
| Offline core plan | `Warehouse_client_core/docs/Core_plan` |
| Desktop future client | `WarehouseDesktop/` |
| Mobile future client | `WarehouseMobile/` |

## Verification Commands

| Project | Command |
|---|---|
| `SyncServer/` | `python -m pytest` |
| `Warehouse_web/` | `python manage.py test` |
| `Warehouse_frontend/` | `npm run build` once Angular scripts exist |
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
- `docs/adr/0011-django-syncserver-internal-transport-hardening.md` - internal transport architecture decision.
- `docs/TZ-DJANGO_SYNCSERVER_TRANSPORT_HARDENING.md` - internal transport implementation specification.

## Rules To Remember

- SyncServer owns warehouse truth.
- Django is the active web client and BFF.
- Django -> SyncServer stays on `/api/v1` HTTP/JSON for Warehouse 3.0; harden `apps/sync_client` before considering alternate transports.
- Angular must run through Django.
- Future offline clients must share `Warehouse_client_core`.
- AI workstation is out of routine scope.
