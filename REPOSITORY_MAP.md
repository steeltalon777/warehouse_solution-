# Repository Map

## Root

The root repo is a coordination layer. It contains documentation, ADRs, plans, and agent contracts. Application runtime code belongs in project directories.

## Projects

| Path | Type | Role |
|---|---|---|
| `SyncServer/` | Python/FastAPI | Source-of-truth backend |
| `Warehouse_web/` | Python/Django | Active web client, admin UI, BFF |
| `Warehouse_frontend/` | Angular target | Django-hosted browser shell |
| `Warehouse_client_core/` | Rust target | Offline-first runtime |
| `WarehouseDesktop/` | .NET/WPF | Future desktop UI over core |
| `WarehouseMobile/` | Android/Kotlin | Future mobile UI over core |
| `WarehouseAIWorkstation/` | .NET/WPF | Paused AI workstation |

## Agent Files

- `AGENTS.md` - root contract.
- `*/AGENTS.md` - project-specific contract.

## Main Active Code Paths

- Backend API and business logic: `SyncServer/app/`.
- Django BFF and UI: `Warehouse_web/apps/`, `Warehouse_web/templates/`.
- Angular shell target: `Warehouse_frontend/`.
- Offline core planning: `Warehouse_client_core/docs/Core_plan`.
