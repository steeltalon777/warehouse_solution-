# AI Context

This file defines how AI agents should reason about this workspace.

## Current Decisions

- `SyncServer` is the authoritative backend and source of truth.
- `Warehouse_web` is the current active web client, Django host, admin UI, and BFF.
- `Warehouse_frontend` is the high-priority Angular shell hosted by Django.
- `Warehouse_client_core` is the planned Rust offline-first runtime for future desktop and mobile clients.
- `WarehouseDesktop` and `WarehouseMobile` should be rebuilt around `Warehouse_client_core`.
- `WarehouseAIWorkstation` is paused unless explicitly requested.

## Non-Negotiable Rules

- Do not put warehouse domain writes outside SyncServer services.
- Do not let clients connect directly to the SyncServer database.
- Do not expose SyncServer user/device tokens to browser JavaScript.
- Do not add Django local ORM models for catalog/domain entities.
- Do not implement offline sync separately in WPF or Android once the core exists.
- Do not edit generated outputs such as `bin/`, `obj/`, `.gradle/`, `node_modules/`, or generated repo maps.
- Do not read or print secrets from `.env`, token files, or `.opencode` guard files.

## Where To Work

| Task | Project |
|---|---|
| Backend API, business rules, migrations | `SyncServer/` |
| Django UI, admin, session, BFF endpoints | `Warehouse_web/` |
| Angular nomenclature shell | `Warehouse_frontend/` |
| Offline-first runtime design/implementation | `Warehouse_client_core/` |
| Future WPF offline UI | `WarehouseDesktop/` |
| Future Android offline UI | `WarehouseMobile/` |
| AI workstation | Only when explicitly resumed |

## Verification

- Backend changes: run `python -m pytest` in `SyncServer/`.
- Django changes: run `python manage.py test` in `Warehouse_web/`.
- Angular changes: run `npm run build` in `Warehouse_frontend/` once Angular scripts exist.
- Rust core changes: run `cargo fmt`, `cargo clippy`, and `cargo test` once the workspace exists.
- Desktop/mobile changes: run the project-specific test command from `AGENTS.md`.

## Working Pattern

1. Read `AGENTS.md` first.
2. Read the target project's local `AGENTS.md`.
3. Inspect code before editing.
4. Make the smallest correct change.
5. Run the narrowest relevant verification.
6. Update active docs when roles, entry points, or verification commands change.
