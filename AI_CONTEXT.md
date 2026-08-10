# AI Context

This file defines how AI agents should reason about this workspace.

## Current Decisions

- `SyncServer` is the authoritative backend and source of truth.
- `Warehouse_web` is the current active web client, Django host, admin UI, and BFF.
- `Warehouse_frontend` is the high-priority Angular shell hosted by Django.
- `Warehouse_client_core` is the planned Rust offline-first runtime for future desktop and mobile clients.
- `WarehouseDesktop` and `WarehouseMobile` should be rebuilt around `Warehouse_client_core`.
- `WarehouseAIWorkstation` is paused unless explicitly requested.
- Warehouse 3.0 keeps Django -> SyncServer on `/api/v1` HTTP/JSON and hardens `Warehouse_web/apps/sync_client/` instead of replacing the boundary.
- ADR-0028 Historical Integrity Stage A is accepted and implemented under `docs/TZ-HISTORICAL_INTEGRITY_STAGE_A.md`; final QA acceptance remains with the verifier. Active status is `docs/audit/HISTORICAL_INTEGRITY_STATUS.md`.
- For audit effects, `created_at` is physical insert time; target `effective_at` is cause-specific business time (submit operation date, acceptance action time, cancellation time, or correction application time).

## Non-Negotiable Rules

- Do not put warehouse domain writes outside SyncServer services.
- Do not let clients connect directly to the SyncServer database.
- Do not expose SyncServer user/device tokens to browser JavaScript.
- Do not add Django local ORM models for catalog/domain entities.
- Do not replace Django -> SyncServer `/api/v1` communication with direct imports, shared database access, stdio IPC, gRPC, or a Rust online backend rewrite unless a new ADR explicitly approves it.
- Do not implement offline sync separately in WPF or Android once the core exists.
- Do not edit generated outputs such as `bin/`, `obj/`, `.gradle/`, `node_modules/`, or generated repo maps.
- Do not read or print secrets from `.env`, token files, or `.opencode` guard files.

## Where To Work

| Task | Project |
|---|---|
| Backend API, business rules, migrations | `SyncServer/` |
| Historical-integrity guards/effects/diagnostics | `SyncServer/`; only transparent report-param passthrough in `Warehouse_web/`; start from ADR-0028 + Stage A TZ |
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
- Frontend browser-flow or CI-parity checks: run `make test-e2e` from the workspace root.
- Rust core changes: run `cargo fmt`, `cargo clippy`, and `cargo test` once the workspace exists.
- Desktop/mobile changes: run the project-specific test command from `AGENTS.md`.

## Working Pattern

1. Read `AGENTS.md` first.
2. Read the target project's local `AGENTS.md`.
3. Inspect code before editing.
4. Make the smallest correct change.
5. Run the narrowest relevant verification.
6. Update active docs when roles, entry points, or verification commands change.

For internal transport work, start from `docs/adr/0011-django-syncserver-internal-transport-hardening.md` and `docs/TZ-DJANGO_SYNCSERVER_TRANSPORT_HARDENING.md`.

For historical-integrity work, start from `docs/audit/HISTORICAL_INTEGRITY_STATUS.md`, then `docs/adr/0028-historical-integrity-stage-a.md` and `docs/TZ-HISTORICAL_INTEGRITY_STAGE_A.md`. Do not mark risks closed before runtime evidence.
