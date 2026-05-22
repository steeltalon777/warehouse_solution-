# Agent TZ Workflow

## Purpose

This document defines how the architect agent writes technical assignments and how executor agents track completion.

## Architect Responsibilities

Every architect-authored TZ must be executable by agents and verifiable by humans.

Required TZ properties:

- Start with a checklist table of contents.
- Split work into numbered levels or phases.
- Define exact files/areas in scope.
- Define out-of-scope areas.
- Define acceptance criteria for each level.
- Define required tests for each level, not only unit tests.
- Define who may check each box and when.

## TZ Header Template

Every TZ starts with this block:

```markdown
# TZ: <feature or project name>

## Execution Checklist

- [ ] 0. Context verified
- [ ] 1. Architecture boundaries confirmed
- [ ] 2. Implementation level 1 complete
- [ ] 3. Unit/component tests complete
- [ ] 4. Integration tests with real dependencies complete
- [ ] 5. Stand smoke tests complete
- [ ] 6. UI automation tests complete
- [ ] 7. User scenario tests complete
- [ ] 8. Regression checks complete
- [ ] 9. Documentation updated
- [ ] 10. Final acceptance review complete

## Check Rules

- Architect creates the checklist and acceptance criteria.
- Executor agents may check implementation and test items only after running the required verification.
- QA verifier may check final acceptance only after reviewing evidence.
- If a check is skipped, it must stay unchecked with a reason in the report.
```

## Required Test Ladder

The architect must choose the applicable levels and explicitly mark non-applicable ones.

| Level | Name | Purpose | Examples |
|---|---|---|---|
| 1 | Static checks | Fast local feedback | format, lint, type checks, migration checks |
| 2 | Unit tests | Isolated logic | service functions, mappers, validators |
| 3 | Component tests | Framework-level behavior | Django view tests, Angular component tests, WPF ViewModel tests |
| 4 | Integration tests | Real internal dependencies | Django + test DB, FastAPI + test DB, Rust core + SQLite |
| 5 | Stand smoke tests | Real app against real test stand | SyncServer + PostgreSQL, Django + SyncServer |
| 6 | UI automation | Browser/desktop automation | Playwright for web, FlaUI for WPF |
| 7 | User scenarios | End-to-end business flows | login, catalog CRUD, operation creation, document generation |
| 8 | Regression pack | Critical existing flows | auth, permissions, balances, sync, temporary items |
| 9 | Acceptance review | TZ-level completion proof | evidence table, commands, screenshots/log paths |

## Stand Requirements

When a task touches runtime behavior, the TZ must define a real test stand.

Minimum stand description:

- Database type and lifecycle.
- Required seed data.
- Services to start.
- Environment variables by name only, never secret values.
- Health checks.
- Smoke commands.
- Reset/cleanup procedure.

### Active Test Stand (Linux / Docker)

The test stand runs in Docker from the workspace root `/home/makc/AI_sandbox/warehouse_solution`. Agents must probe health endpoints before any real-stand test step.

| Service | Address | Health Check | Container |
|---|---|---|---|
| SyncServer API | `http://localhost:8000` | `GET /api/v1/health` | `warehouse_syncserver` |
| Django (Warehouse_web) | `http://localhost:8001` | `GET /healthz/` | `warehouse_web` |
| PostgreSQL | `localhost:5432` | `pg_isready -h localhost -p 5432 -t 3` | `warehouse_postgres` (`postgres:15-alpine`) |
| Angular (Warehouse_frontend) | `http://localhost:4200` | `GET /` | `warehouse_angular` |

Use `make up` from the workspace root to start the stand when available. Alternative: `docker compose up -d`. Legacy VM database tunnel is obsolete.

### Stand Availability Protocol

When an agent needs a real test stand:

1. Probe `http://localhost:8000/api/v1/health`, `http://localhost:8001/healthz/`, and `pg_isready -h localhost -p 5432 -t 3`. For Angular/UI tests, also probe `http://localhost:4200/`.
2. If stand is running → proceed.
3. If stand is NOT running → run `make up` from `/home/makc/AI_sandbox/warehouse_solution`.
4. If Makefile is unavailable or fails, run `docker compose up -d` from the same directory.
5. If Docker/compose cannot start the stand, report: **«Стенд не обнаружен. Запусти `make up` или `docker compose up -d` из `/home/makc/AI_sandbox/warehouse_solution/`.»**
6. If stand cannot be brought up, leave the relevant checklist item unchecked: **«стенд недоступен»**.

### Environment Variables (names only, never values)

- `DJANGO_ENV=development`
- `SYNC_SERVER_URL`
- `SYNC_ROOT_USER_TOKEN`
- `SYNC_DEVICE_TOKEN`
- `DATABASE_URL`
- `DJANGO_SETTINGS_MODULE`
- `SECRET_KEY`

### Stand Examples

- `SyncServer` stand: FastAPI app plus PostgreSQL test database, Alembic migrated, known users/sites/devices seeded.
- `Warehouse_web` stand: Django app plus SyncServer test stand, Django test DB, valid non-secret fixture tokens injected through environment.
- Angular web UI stand: Django host plus Angular dev server or built assets, Playwright browser tests through Django route.
- WPF stand: application launched from build output, test profile storage, FlaUI smoke tests.

## Evidence Table

Every executor completion report must include:

```markdown
## Evidence

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|
| Unit tests | `<command>` | pass/fail/skipped | log path or short note |
| DB integration | `<command>` | pass/fail/skipped | DB/fixture note |
| Stand smoke | `<command>` | pass/fail/skipped | URL/log/screenshot |
| UI automation | `Playwright` / `FlaUI` | pass/fail/skipped | report path |
```

## Executor Rules

- Do not mark a checkbox complete before implementation and verification are both done.
- Do not mark another agent's checkbox unless assigned as verifier.
- If tests fail, leave the checkbox unchecked and add the failure summary.
- If a required stand is unavailable, leave the checkbox unchecked and document the blocker.
- Before any real-stand test step, follow the **Stand Availability Protocol** above: probe health endpoints, stop and ask if unavailable.
- Update the TZ checklist in the same file where the TZ lives.

## QA Verifier Rules

- Verify that every checked item has evidence.
- Verify that skipped checks have explicit reasons.
- Verify that real stand and UI automation requirements were not silently replaced by unit tests.
- Only then check final acceptance.
