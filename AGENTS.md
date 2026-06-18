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

- Parallel sessions are normal. `git status` may show unrelated modified/untracked files from other agents or the user; this is not a blocker by itself.
- Agents MUST commit their own completed task changes when applicable tests/checks for the touched project pass and the work is in an acceptable state.
- Before committing, agents must verify that the current branch is `dev`.
- Agents commit only to the `dev` branch.
- Switching from `dev` to another branch is forbidden by default.
- If the current branch is not `dev`, the agent must warn the user and must not commit until the user gives an explicit command.
- Agents must stage only files intentionally changed for their assigned task, using explicit pathspecs such as `git add -- path/to/file`. Do not use broad `git add .` or `git add -A` for task commits.
- Git does not auto-track new files by itself; untracked files become tracked only after staging. Keep local/service artifacts ignored and unstaged unless the user explicitly assigns them.
- Before committing, inspect the staged diff and confirm it contains only task-owned files. Leave unrelated dirty files unstaged.
- If intended edits overlap with unrelated changes in the same file, stop and report the ownership conflict instead of committing.
- If tests fail, are unavailable, or were not run, the agent must not commit unless the user explicitly instructs to commit with that limitation documented.
- Git push is completely forbidden for agents. The user performs all pushes manually.

## Architecture Rules

- All warehouse domain writes go through `SyncServer` services.
- Clients must not connect directly to the SyncServer database.
- Django stores technical web state only: auth, sessions, user binding, cache, and BFF state.
- Django catalog screens and APIs must use `Warehouse_web/apps/sync_client/` and services, not local catalog ORM entities.
- Angular must call Django BFF endpoints. It must not receive SyncServer tokens or call SyncServer directly from the browser.
- Frontend SPA architecture is governed by `Warehouse_frontend/docs/ARCHITECTURE_FRONTEND_SPA.md`: Django shell is permanent, Angular renders only the content area, business URLs open migrated Angular screens, replaced SSR routes move under `/ssr/`, and browser data access goes through Django BFF.
- Django -> SyncServer internal transport for Warehouse 3.0 is governed by `docs/adr/0011-django-syncserver-internal-transport-hardening.md` and `docs/TZ-DJANGO_SYNCSERVER_TRANSPORT_HARDENING.md`: keep `/api/v1` HTTP/JSON as the canonical contract, harden `Warehouse_web/apps/sync_client/`, add BFF aggregation/cache/metrics where useful, and do not replace it with direct imports, shared DB access, stdio, gRPC, or a Rust online backend without a new ADR.
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

## Test Stand Configuration (Linux / Docker)

**Default state: dev-стенд запущен.** Агенты исходят из того, что стенд работает, и обращаются к нему без лишних проверок. Пробуют health-check только если запросы к стенду падают.

Стенд работает в Docker из корня `/home/makc/AI_sandbox/warehouse_solution`.

| Service | Address | Health Check | Container |
|---|---|---|---|
| SyncServer API | `http://localhost:8000` | `GET /api/v1/health` | `warehouse_syncserver` |
| Django (Warehouse_web) | `http://localhost:8001` | `GET /healthz/` | `warehouse_web` |
| PostgreSQL | `localhost:5432` | `pg_isready -h localhost -p 5432 -t 3` | `warehouse_postgres` (`postgres:15-alpine`) |
| Angular (Warehouse_frontend) | `http://localhost:4200` | `GET /` | `warehouse_angular` |

### Make-команды для управления стендом

Агенты имеют полное право использовать эти команды из `/home/makc/AI_sandbox/warehouse_solution`:

| Команда | Назначение |
|---|---|
| `make up` | Запустить все сервисы в фоне (сборка + старт) |
| `make down` | Остановить все сервисы |
| `make restart` | Перезапустить стенд (`down` → `up`) |
| `make build` | Пересобрать все образы с нуля (без кэша) |
| `make build-sync` | Пересобрать только SyncServer |
| `make build-web` | Пересобрать только Warehouse_web |
| `make build-angular` | Пересобрать только Angular-фронтенд |
| `make status` | Статус контейнеров + проверка эндпоинтов |
| `make logs` | Логи всех сервисов (Ctrl+C для выхода) |
| `make logs-sync` | Логи только SyncServer |
| `make logs-web` | Логи только Warehouse_web |
| `make migrate` | Применить все миграции |
| `make dev` | Запустить + миграции + показать логи (интерактивный) |
| `make init` | Первоначальная инициализация (первый запуск) |
| `make clean` | Очистить всё (контейнеры + volumes + образы) |
| `make ps` | Статус контейнеров (кратко) |
| `make reset-django-admin` | Сбросить Django superuser до admin/admin123 |

### Stand Availability Protocol

**Когда агенту нужен рабочий стенд для smoke/интеграционных/UI-тестов:**

1. **По умолчанию стенд запущен.** Агент не проверяет health-check перед каждым обращением — только если запрос возвращает ошибку подключения.
2. Если запрос к стенду упал → агент проверяет `http://localhost:8000/api/v1/health`, `http://localhost:8001/healthz/` и `pg_isready -h localhost -p 5432 -t 3`.
3. Если **стенд работает** → продолжить тесты.
4. Если **стенд НЕ работает** → агент запускает `make up` из `/home/makc/AI_sandbox/warehouse_solution`.
5. Если `make up` недоступен или падает → агент пробует `docker compose up -d` из той же директории.
6. Если стенд запустился, но тест падает по таймауту/ошибке → агент может попробовать `make restart` (полный перезапуск) или `make build-sync` / `make build-web` / `make build` (ребилд с нуля), особенно если были изменения в Dockerfile, зависимостях или конфигурации.
7. Если Docker/compose не может поднять стенд → агент сообщает: «Стенд не обнаружен. Запусти `make up` или `docker compose up -d` из `/home/makc/AI_sandbox/warehouse_solution/`.»
8. Если стенд не удаётся поднять ни одним способом → агент оставляет чек-лист незакрытым с пометкой: «стенд недоступен».

### Default credentials (dev-стенд)

**Django superuser (Warehouse_web `http://localhost:8001/admin/`):**

| Поле | Значение |
|---|---|
| Логин | `admin` |
| Пароль | `admin123` |

При проблемах со входом — сбросить до значений по умолчанию:

```
make reset-django-admin
```

### Stand Environment Variables (names only, never values)

- `DJANGO_ENV=development`
- `SYNC_SERVER_URL`
- `SYNC_ROOT_USER_TOKEN`
- `SYNC_DEVICE_TOKEN`
- `DATABASE_URL`
- `DJANGO_SETTINGS_MODULE`
- `SECRET_KEY`

---

## Deployment Rules

Полные правила деплоя, роли веток, pre-deploy review, workflow, Angular-стратегия и rollback — в `docs/DEPLOYMENT.md`.

Кратко:
- Решение о деплое принимает пользователь.
- Агент выполняет pre-deploy review по запросу.
- Ветки: `dev` (разработка), `main` (релиз/прод), `prod` (фолбек).
- Деплой — строго по команде пользователя.
- SSH-доступ к VPS агент запрашивает у пользователя, не хранит.


## TZ And Task Tracking Rules

- Architect-authored TZ files must start with a checklist table of contents.
- Executor agents may check boxes only after implementation and verification are complete.
- Runtime features need a test ladder: static checks, unit/component tests, DB-backed integration tests, real stand smoke tests, UI automation when applicable, and user scenario tests.
- Web UI uses Playwright for browser scenarios.
- WPF UI uses FlaUI for desktop scenarios.
- If a required real stand is unavailable, leave the checkbox unchecked and document the blocker.
- See `docs/AGENT_TZ_WORKFLOW.md` for the canonical TZ workflow.
