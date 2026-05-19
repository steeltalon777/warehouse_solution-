 # Warehouse Solution Agent Contract

## Scope

This workspace contains one authoritative backend, one active web client, one high-priority Angular shell project, and future offline clients.

- `SyncServer/` is the source of truth for warehouse domain data and business rules.
- `Warehouse_web/` is the active Django web client, Django host, and BFF layer.
- `Warehouse_frontend/` is the high-priority Angular shell that must run through Django.
- `Warehouse_client_core/` is the planned Rust offline-first runtime for future desktop and mobile clients.
- `WarehouseDesktop/` and `WarehouseMobile/` are future offline clients to be rebuilt around `Warehouse_client_core`.
- `WarehouseAIWorkstation/` is paused unless the user explicitly asks to work on it.

 ## Functional Requirements Authority

- `Functional and WorkLogik.md` at the workspace root is the **canonical functional requirements document**.
- All TZ, architecture decisions, and implementation work in every nested project MUST be checked against `Functional and WorkLogik.md` before marking a feature complete.
- Deviations from `Functional and WorkLogik.md` are allowed ONLY when:
  1. the item in `Functional and WorkLogik.md` is explicitly marked as «на стадии продумывания» (design stage) or «частичной реализации» (partial implementation), OR
  2. a written ADR explicitly overrides a specific requirement with a documented rationale.
- Agent behaviour: before starting any implementation that touches warehouse domain logic, operation types, user flows, or screen layouts, re-read the relevant section of `Functional and WorkLogik.md` and confirm alignment.

## Repository Rules

- Treat the root repo as coordination/docs only. Do not add application runtime code at root.
- Check the nested project status before editing nested repos. They may be independent Git repositories.
- Do not touch generated outputs such as `bin/`, `obj/`, `.pytest_cache/`, `.gradle/`, `node_modules/`, or generated repo maps unless the user explicitly asks.
- Do not read, print, commit, or hardcode secrets from `.env`, token files, local config, or `.opencode` secret guard files.
- Prefer the smallest correct change. Do not add compatibility paths unless a persisted-data or production rollout need is explicit.

## Git Rules

- Agents may create git commits for completed work when applicable tests/checks for the touched project pass and the work is in an acceptable state.
- Before committing, agents must verify that the current branch is `dev`.
- Agents commit only to the `dev` branch.
- Switching from `dev` to another branch is forbidden by default.
- If the current branch is not `dev`, the agent must warn the user and must not commit until the user gives an explicit command.
- If tests fail, are unavailable, or were not run, the agent must not commit and must ask the user what to do.
- Git push is completely forbidden for agents. The user performs all pushes manually.

## Architecture Rules

- All warehouse domain writes go through `SyncServer` services.
- Clients must not connect directly to the SyncServer database.
- Django stores technical web state only: auth, sessions, user binding, cache, and BFF state.
- Django catalog screens and APIs must use `Warehouse_web/apps/sync_client/` and services, not local catalog ORM entities.
- Angular must call Django BFF endpoints. It must not receive SyncServer tokens or call SyncServer directly from the browser.
- Frontend SPA architecture is governed by `Warehouse_frontend/docs/ARCHITECTURE_FRONTEND_SPA.md`: Django shell is permanent, Angular renders only the content area, business URLs open migrated Angular screens, replaced SSR routes move under `/ssr/`, and browser data access goes through Django BFF.
- Future offline clients must use `Warehouse_client_core` for local storage, outbox, sync, DTO mapping, and conflict handling.

## Project Priorities

1. Stabilize `SyncServer` API contracts and tests.
2. Remove Django catalog local-domain drift and keep Django as the active web client/BFF.
3. Build `Warehouse_frontend` as the Django-hosted Angular content application, starting with nomenclature and operations.
4. Define and then implement `Warehouse_client_core` for offline-first desktop/mobile.
5. Keep `WarehouseAIWorkstation` out of routine changes until explicitly resumed.

## Verification Matrix

- `SyncServer/`: run `python -m pytest` after backend changes. For migrations, also run `python -m alembic upgrade head` against a safe database.
- `Warehouse_web/`: run `python manage.py test` after Django changes.
- `Warehouse_frontend/`: run `npm run build` after frontend changes once Angular scripts exist.
- `Warehouse_client_core/`: run `cargo fmt --all -- --check`, `cargo clippy --workspace --all-targets -- -D warnings`, and `cargo test --workspace` once Rust workspace exists.
- `WarehouseDesktop/`: run `dotnet test WarehouseDesktop.sln` only when this client is touched.
- `WarehouseMobile/`: run `gradlew.bat test` when Android code is touched.
- `WarehouseAIWorkstation/`: run `dotnet test WarehouseAIWorkstation.sln` only when the user explicitly asks to work on it.

## Documentation Rules

- Update `README.md`, `ARCHITECTURE.md`, `INDEX.md`, `AI_CONTEXT.md`, and `AI_ENTRY_POINTS.md` when project roles, entry points, or verification commands change.
- Keep project-specific `AGENTS.md` files shorter and more concrete than root docs.
- Historical reports may remain historical, but active docs must describe the current target state.

## Test Stand Configuration

The test stand is **usually** running at these addresses. Agents must probe stand availability before any real-stand test step.

| Service | Address | Health Check |
|---|---|---|
| SyncServer API | `http://localhost:8000` | `GET /api/v1/health` |
| Django (Warehouse_web) | `http://localhost:8001` | `GET /healthz/` |
| PostgreSQL (via SSH tunnel) | `localhost:5434` | — |

### SSH Tunnel To Database

The user maintains an SSH tunnel to the VM database. Tunnel command (for reference only — agents never run this):

```
ssh -p 2222 makc@127.0.0.1
```

Port mapping: VM PostgreSQL → `localhost:5434`.

### Stand Availability Protocol

**When an agent needs a real test stand for smoke/integration/UI tests:**

1. Agent probes health endpoints (`/api/v1/health` on `:8000`, `/healthz/` on `:8001`).
2. If **stand is running** → proceed with tests.
3. If **stand is NOT running** → agent STOPS and reports to the user:
   - «Стенд не обнаружен. Подними стенд (Django :8001 + SyncServer :8000 + SSH-туннель :5434).»
   - Agent does NOT attempt to start the stand itself.
   - Agent waits for user confirmation before continuing.
4. User responds with instructions (stand may already be up, or user may start it, or user may say skip).
5. If stand cannot be brought up, agent leaves the relevant checklist item unchecked with the blocker note: «стенд недоступен».

### Stand Environment Variables (names only, never values)

- `DJANGO_ENV=development`
- `SYNC_SERVER_URL`
- `SYNC_ROOT_USER_TOKEN`
- `SYNC_DEVICE_TOKEN`
- `DATABASE_URL`
- `DJANGO_SETTINGS_MODULE`
- `SECRET_KEY`

---

## TZ And Task Tracking Rules

- Architect-authored TZ files must start with a checklist table of contents.
- Executor agents may check boxes only after implementation and verification are complete.
- Runtime features need a test ladder: static checks, unit/component tests, DB-backed integration tests, real stand smoke tests, UI automation when applicable, and user scenario tests.
- Web UI uses Playwright for browser scenarios.
- WPF UI uses FlaUI for desktop scenarios.
- If a required real stand is unavailable, leave the checkbox unchecked and document the blocker.
- See `docs/AGENT_TZ_WORKFLOW.md` for the canonical TZ workflow.
