# TZ: Warehouse 3.0.1 Post-Deploy Patch

## Execution Strategy

- [ ] 🟢 Parallel execution recommended
- **Reason:** патч 3.0.1 состоит из трёх независимых быстрых направлений после релиза 3.0: Angular-визуал и локальная свежесть остатков, Django-операционная синхронизация пользователей, SyncServer-эксплуатационное логирование и регрессионные проверки остатков. Эти направления принадлежат разным проектам и не требуют общих writable-файлов. Роли/аудит/offline activity являются доменными контрактами и вынесены из 3.0.1 в 3.1.

### Parallel stages

| Stage | Work units | Parallelism | Integration owner |
|---|---|---|---|
| 0. Context lock | Все исполнители читают `docs/V3.0_POST_DEPLOY_FIXES.md`, этот TZ, `Functional and WorkLogik.md` релевантные разделы, локальные `AGENTS.md` | Можно параллельно | Parent/orchestrator |
| 1. Implementation | Unit A Angular, Unit B Django, Unit C SyncServer | Можно параллельно, файлы не пересекаются | Каждый unit owner |
| 2. Unit integration | Локальные тесты каждого проекта | Можно параллельно | Каждый unit owner |
| 3. Stand integration | общий Docker-stand: smoke, UI automation, log review | Последовательно после Stage 1/2 | Parent/orchestrator + QA |
| 4. Release closure | обновление статусов, evidence, final checklist | Последовательно | Parent/orchestrator + QA |

### Independent work units

1. **Unit A — Angular operations UI quick fixes**
   - **Writable ownership:** `Warehouse_frontend/src/app/core/services/operations.service.ts`, `Warehouse_frontend/src/app/features/operations/components/operations-table/`, `Warehouse_frontend/src/app/features/operations/components/operation-create-modal/`, Angular tests/specs if added.
   - **Input fixes:** #1 and 3.0.1-mitigation part of #5 from `docs/V3.0_POST_DEPLOY_FIXES.md`.
   - **Must not edit:** Django BFF, SyncServer policies, role matrix.
   - **Evidence:** `npm run build`, UI/Playwright smoke for `/operations/`, screenshots/log notes.
2. **Unit B — Django SyncServer users import**
   - **Writable ownership:** `Warehouse_web/apps/users/management/commands/`, `Warehouse_web/apps/users/services.py`, `Warehouse_web/apps/users/models.py`, `Warehouse_web/apps/users/tests*`, `Warehouse_web/apps/sync_client/root_admin_client.py` only if a tiny helper is needed.
   - **Input fixes:** #2 verification and #3 from `docs/V3.0_POST_DEPLOY_FIXES.md`.
   - **Must not edit:** warehouse catalog/operations local models; browser BFF endpoints unless strictly required for admin sync.
   - **Evidence:** Django tests, command dry-run/apply output without tokens, admin/binding smoke.
3. **Unit C — SyncServer logging + stale-balance regression**
   - **Writable ownership:** `SyncServer/main.py`, `SyncServer/app/core/logging_config.py`, `SyncServer/app/core/db.py`, SyncServer tests for logging and balance conflicts.
   - **Input fixes:** #7 and server-regression part of #5 from `docs/V3.0_POST_DEPLOY_FIXES.md`.
   - **Must not edit:** role policy semantics except adding non-invasive regression tests; no schema migration unless explicitly approved.
   - **Evidence:** targeted pytest, full/appropriate pytest, stand log sample without tokens/SQL noise.

## Execution Checklist

- [x] 0. Context verified
- [x] 1. Architecture boundaries confirmed
- [x] 2. Implementation stage 1 complete: Unit A Angular
- [x] 3. Implementation stage 1 complete: Unit B Django users import
- [x] 4. Implementation stage 1 complete: Unit C SyncServer logging/regression
- [x] 5. Integration stage complete: combined stand smoke and release notes
- [x] 6. Unit/component tests complete
- [x] 7. Integration tests with real dependencies complete
- [x] 8. Stand smoke tests complete
- [x] 9. UI automation tests complete (см. Evidence — покрыто Playwright smoke)
- [x] 10. User scenario tests complete
- [x] 11. Regression checks complete
- [x] 12. Documentation updated
- [ ] 13. Final acceptance review complete (ожидает QA-верификатора)

## Check Rules

- Architect creates the checklist and acceptance criteria.
- Executor agents may check implementation/test items only after the implementation is complete and the required verification has run.
- Parent/orchestrator checks integration-stage items only after all unit evidence is collected.
- QA verifier checks final acceptance only after reviewing evidence and confirming skipped checks have explicit blocker notes.
- Failed or unavailable checks stay unchecked with a blocker note.
- Do not mark 3.1-deferred items as complete under this TZ.
- If a code executor discovers that a planned 3.0.1 change requires changing role semantics, schema contracts, audit storage, or offline sync contracts, stop and report scope escalation instead of widening this patch.

## Source Documents and Authority

| Document | Role in this TZ |
|---|---|
| `docs/V3.0_POST_DEPLOY_FIXES.md` | Original post-deploy issue list. |
| `Functional and WorkLogik.md` | Canonical functional requirements for roles, operations, UI flows. |
| `Role Matrix.md` | Current role matrix snapshot; contradictions are noted but not resolved in 3.0.1. |
| `AGENTS.md`, nested project `AGENTS.md` | Repository/project boundaries, verification commands, stand protocol. |
| `docs/adr/0011-django-syncserver-internal-transport-hardening.md` | Django must call SyncServer through HTTP `/api/v1` sync client/BFF; no direct imports/shared DB. |
| `Warehouse_frontend/docs/ARCHITECTURE_FRONTEND_SPA.md` | Angular runs inside Django shell and uses Django BFF, not direct SyncServer calls. |

## Architecture Boundaries

### Must preserve

- SyncServer remains the authoritative source for warehouse users/scopes, operations, balances, and business rules.
- Django stores technical web state only: auth, sessions, bindings, cache/BFF state. Django must not become a second warehouse backend.
- Angular must call Django BFF only. No SyncServer tokens in browser code, localStorage, screenshots, command output, docs, or logs.
- All warehouse domain writes still go through SyncServer services.
- Patch 3.0.1 must be low-risk and reversible; broad domain decisions are deferred to 3.1.

### Explicitly not changing in 3.0.1

- Role matrix semantics for observer/storekeeper/chief/root.
- Whether observer may create drafts.
- MOVE submit rule: source-only vs destination-only vs source-or-destination scope.
- Audit journal schema/API/UI.
- Offline heartbeat/sync activity schema/API beyond preserving existing `Device.last_seen_at` behaviour.

## Triage Summary for 3.0.1 vs 3.1

| Fix from post-deploy list | 3.0.1 action | 3.1 action |
|---|---|---|
| #1 Цвет статуса «Приёмка: ожидает» | Implement Angular visual fix. | None unless table status model is later redesigned. |
| #2 `sync_user_token NOT NULL` | Verify migrations `users.0007` and `users.0008`; keep operational note. | None. |
| #3 SyncServer users not in Django | Implement safe import/repair command. | Optional admin UX improvements if needed. |
| #4 Roles/permissions | No functional role changes. Only document contradictions if encountered. | Separate role matrix TZ/ADR and code alignment. |
| #5 Stale balances in operation form | Angular refresh mitigation + SyncServer conflict regression tests. | Full data freshness/conflict UX design. |
| #6 User action journal | No new audit subsystem. | Separate audit journal TZ/ADR with migrations/API/UI. |
| #7 SyncServer logging | Implement request/response access logging and explicit SQL logging flag. | Observability expansion/metrics if needed. |
| #8 Offline last seen/heartbeat/sync activity | No schema/API expansion. Verify not regressed. | Separate offline activity TZ/ADR. |

## Detailed Requirements: Unit A — Angular Operations UI Quick Fixes

### A0. Required context before edits

Executor must read:

- `Functional and WorkLogik.md`, sections II and VIII.
- `docs/V3.0_POST_DEPLOY_FIXES.md`, items #1 and #5.
- `Warehouse_frontend/AGENTS.md`.
- Current files:
  - `Warehouse_frontend/src/app/core/services/operations.service.ts`
  - `Warehouse_frontend/src/app/features/operations/components/operations-table/operations-table.component.ts`
  - `Warehouse_frontend/src/app/features/operations/components/operation-create-modal/operation-create-modal.component.ts`
  - `Warehouse_frontend/src/app/features/operations/components/operation-create-modal/operation-lines-table.component.ts`

### A1. Acceptance status color

#### Current issue evidence

- `OperationsService.buildStatusLines()` returns plain strings: main operation status + acceptance status label.
- `OperationsTableComponent` renders every line as:
  - `class="status-line {{ statusClass(row.status) }}"`
- Therefore `Приёмка: ожидает` and `Приёмка: закрыта` inherit the same operation status class, usually `submitted`, and can look identical.

#### Required behaviour

- Main operation status line keeps existing operation status color.
- Acceptance status line gets a separate visual class based on `acceptance_state`:
  - `pending` → warning/yellow/orange, visually distinct.
  - `in_progress` → intermediate/blue or warning-muted.
  - `resolved` → success/green or neutral-success, distinct from `pending`.
  - unknown acceptance states → neutral but not broken.
- The text labels remain Russian and current labels are preserved:
  - `Приёмка: ожидает`
  - `Приёмка: частично`
  - `Приёмка: закрыта`

#### Preferred implementation approach

Choose the smallest maintainable approach:

1. **Preferred:** extend row VM to structured status lines, e.g. `{ label, kind, state }`, if model changes are local and low-risk.
2. **Acceptable quick patch:** keep string labels but add `statusLineClass(row, line, index)` in `OperationsTableComponent`:
   - index `0` uses operation status class;
   - lines starting with `Приёмка:` use acceptance-specific classes derived from text or from row fields if available.
3. If adding `acceptanceState` to `OperationListRowVm` is needed, update only the Angular model/service/table pieces.

#### Files in scope

- `Warehouse_frontend/src/app/features/operations/components/operations-table/operations-table.component.ts`
- `Warehouse_frontend/src/app/core/services/operations.service.ts`
- `Warehouse_frontend/src/app/core/models/operations.models.ts` if row VM type needs a new field.
- Shared SCSS only if current badge styles are centralized there.

#### Files out of scope

- Django BFF status mapping.
- SyncServer operation/acceptance state semantics.
- Role visibility.

#### Acceptance criteria

- An operation row with `acceptance_state=pending` displays `Приёмка: ожидает` in warning/yellow/orange.
- An operation row with `acceptance_state=resolved` displays `Приёмка: закрыта` in a different neutral/success color.
- No regression in main operation status labels/colors.
- Build passes.
- Playwright/manual smoke confirms the visual difference in `/operations/`.

### A2. Stale balances quick mitigation in operation modal

#### Current issue evidence

- `OperationsService.balances` is a shared Angular signal.
- `OperationCreateModalComponent` refreshes balances in an effect when `relevantSiteId()` changes.
- There is no explicit request sequencing guard; a slower old request can overwrite current balances.
- `onNewItemSelected()` uses current signal data and can show an old source quantity.
- Submit still relies on SyncServer authoritative validation, which must remain the final source of truth.

#### Required behaviour for 3.0.1

- When the modal opens or receives a draft, and a relevant warehouse is known, balances are refreshed before/while source quantity hints are shown.
- When operation type or relevant warehouse changes, existing line `availableQuantity/sourceSiteQuantity` values are refreshed from the current warehouse.
- Late result from an older warehouse refresh cannot overwrite current selected warehouse quantities.
- Before `onSubmit()` and `onSave()` for stock-consuming warehouse flows, refresh balances once more or otherwise ensure displayed hints are not knowingly stale.
- Object-source flows are preserved:
  - `ISSUE_RETURN`
  - `WRITE_OFF` with `writeOffSource === 'object'`
  - prefilled assigned-asset lines
  These flows must not overwrite object-assigned quantity with warehouse balance.
- If SyncServer rejects submit due to changed balance, UI must show the existing normalized error and keep the operation not-submitted.

#### Required implementation constraints

- Do not introduce global state architecture for balances in 3.0.1.
- Do not create direct SyncServer calls from Angular.
- Do not hide SyncServer conflicts behind client-side assumptions.
- Do not change operation payload contract.
- Keep modal responsiveness acceptable; avoid infinite effect loops.

#### Suggested implementation details

- Add a monotonically increasing request sequence or current-site token in `OperationCreateModalComponent`, e.g. `private balanceRefreshSeq = 0`:
  - increment before `loadBalances(siteId)`;
  - after await, apply `refreshSourceQuantities()` only if sequence and current `relevantSiteId()` still match.
- Add helper methods:
  - `private shouldUseWarehouseBalances(): boolean`
  - `private async refreshBalancesForCurrentSite(reason: string): Promise<boolean>`
  - `private async refreshBeforePersist(): Promise<void>`
- Ensure `onSubmit()` and `onSave()` can await refresh before emitting, or deliberately skip only when no warehouse balance applies.
- Keep `isBalanceRefreshing` accurate for spinner/line table state.

#### Files in scope

- `Warehouse_frontend/src/app/features/operations/components/operation-create-modal/operation-create-modal.component.ts`
- `Warehouse_frontend/src/app/core/services/operations.service.ts`
- `Warehouse_frontend/src/app/features/operations/components/operation-create-modal/operation-lines-table.component.ts` only if display state needs a minor adjustment.

#### Acceptance criteria

- Changing warehouse in the modal updates existing line source quantities.
- Fast switching A → B → A or A → B cannot leave B selected with A balances.
- Adding a TMC after warehouse refresh uses the currently selected warehouse quantity.
- Submit after a concurrent balance change surfaces SyncServer conflict/validation error to the user.
- Existing inline item creation flow still works.

### A3. Angular tests/checks

Required:

- `npm run build` in `Warehouse_frontend/`.
- If Angular test tooling is available, add/run focused component/service tests for:
  - status line class selection;
  - stale balance request sequencing.
- If test tooling is unavailable/not configured, document blocker and cover by build + Playwright/manual stand smoke.

Playwright/manual smoke:

- `/operations/` opens through Django shell, not standalone SyncServer.
- Row with pending acceptance is visually distinct from resolved acceptance.
- Open/create operation modal, change warehouse, verify quantities refresh.
- If feasible: create a conflict by consuming stock in another operation, then submit stale operation and verify error is shown.

## Detailed Requirements: Unit B — Django SyncServer Users Import

### B0. Required context before edits

Executor must read:

- `Functional and WorkLogik.md`, section IX points 7–10.
- `docs/V3.0_POST_DEPLOY_FIXES.md`, items #2 and #3.
- `Warehouse_web/AGENTS.md`.
- Current files:
  - `Warehouse_web/apps/users/models.py`
  - `Warehouse_web/apps/users/services.py`
  - `Warehouse_web/apps/users/admin.py`
  - `Warehouse_web/apps/users/simple_sync_signals.py`
  - `Warehouse_web/apps/users/management/commands/repair_sync_users.py`
  - `Warehouse_web/apps/sync_client/root_admin_client.py`
  - `SyncServer/app/api/routes_admin_users.py` for remote endpoint shape.

### B1. Migration verification for #2

#### Required behaviour

- Confirm Django database has `users.0007_make_optional_string_fields_nullable` and `users.0008` applied in the target environment before/with release operations.
- Do not create another migration unless model/schema mismatch is actually found.

#### Acceptance criteria

- `python manage.py showmigrations users` or equivalent evidence shows `0007` and `0008` applied in the environment where the patch is verified.
- Creating a Django user no longer fails with `sync_user_token NOT NULL`.

### B2. Reverse import command for #3

#### Problem statement

Users may exist in SyncServer (`syncserver_main`) but not in Django `auth_user` and not in `users_syncuserbinding`. Current `repair_sync_users.py` only repairs existing bindings and cannot import missing users.

#### Required command

Add a management command, recommended name:

```bash
python manage.py import_sync_users --dry-run
python manage.py import_sync_users --apply
```

Alternative: extend `repair_sync_users.py` only if the CLI remains clear and backward-compatible. A new command is preferred to avoid mixing repair of existing bindings with import of missing users.

#### Command options

Required:

- `--dry-run` — no DB writes. This is the default behaviour if neither `--dry-run` nor `--apply` is passed.
- `--apply` — perform safe creates/updates.
- `--username <username>` — optional single-user filter.
- `--sync-user-id <uuid>` — optional single SyncServer user filter if endpoint data supports it.
- `--include-inactive` — optional; default skips inactive remote users if remote has active flag.

Recommended:

- `--fail-on-conflict` — exits non-zero on conflicts for CI/admin clarity.
- `--limit N` — optional safety for large imports.

#### Remote data source

- Use `SyncServerRootAdminClient` server-side only.
- Primary endpoint: `GET /api/v1/admin/users` through root admin client path `/admin/users`.
- Per-user endpoint when needed: `GET /api/v1/admin/users/{user_id}/sync-state` through path `/admin/users/{user_id}/sync-state`.
- Do not read SyncServer DB directly.
- Do not call SyncServer from browser.

#### Mapping rules

For each remote SyncServer user:

1. Determine stable identifiers:
   - `syncserver_user_id` / remote user id.
   - username.
   - role.
   - scopes/sites if available through sync-state.
2. If existing `SyncUserBinding.syncserver_user_id` matches:
   - update safe metadata/status only;
   - do not replace Django user identity unexpectedly.
3. If no binding but `User.username` exists:
   - if it is clearly the same intended user and no conflicting binding exists, create binding;
   - if conflict is ambiguous, skip and report conflict.
4. If no Django user exists:
   - create Django `User` with username and safe defaults;
   - mark password unusable unless there is an explicit safe password provisioning flow;
   - set staff/superuser flags conservatively, never grant admin based only on uncertain remote data unless root/chief policy is already implemented in existing services.
5. Create/update `SyncUserBinding`:
   - `syncserver_user_id` populated;
   - `sync_status` set to synced/appropriate success status;
   - token fields only if existing model/service requires and remote endpoint safely returns them for this admin use case;
   - never print token values.
6. Existing Django superuser/root:
   - must not be overwritten accidentally;
   - if remote root conflicts with local admin, report explicitly.

#### Output requirements

Command output must show counts only and safe identifiers:

- remote users scanned;
- would create / created users;
- would create / created bindings;
- updated bindings;
- skipped existing;
- conflicts;
- failures.

Command output must not show:

- `sync_user_token` value;
- `SYNC_ROOT_USER_TOKEN`;
- `SYNC_DEVICE_TOKEN`;
- raw headers;
- `.env` values.

#### Error handling

- SyncServer unavailable: command exits non-zero with clear message, no partial writes unless per-user transaction strategy intentionally committed previous users.
- Username conflict: skip by default and report; if `--fail-on-conflict`, exit non-zero.
- Invalid remote payload: skip user and report, or fail if payload shape is globally invalid.
- Apply mode should use database transactions per user or for the full command; choose safest approach and document it in test evidence.

#### Files in scope

- `Warehouse_web/apps/users/management/commands/import_sync_users.py` preferred new file.
- `Warehouse_web/apps/users/services.py` for reusable import logic if needed.
- `Warehouse_web/apps/users/models.py` only if reading existing fields; avoid schema changes in 3.0.1.
- `Warehouse_web/apps/users/tests/` or existing users test files.
- `Warehouse_web/apps/sync_client/root_admin_client.py` only for small typed helpers; generic `get()` is already available.

#### Files out of scope

- SyncServer admin user endpoint changes unless current endpoint lacks required data and user approves scope escalation.
- New Django warehouse-domain models.
- Browser-facing BFF endpoints for user import.
- Full login history/audit journal.

#### Acceptance criteria

- Dry-run does not write to DB and reports intended actions.
- Apply creates a missing Django `User` and `SyncUserBinding` from a safe remote user fixture.
- Existing binding is idempotently skipped/updated without duplicates.
- Username conflict is reported and not auto-merged unsafely.
- Command output and logs contain no token values.
- `python manage.py test apps.users` passes.
- Full `python manage.py test` passes or any unrelated failures are documented with evidence and owner decision.

### B3. Django stand smoke

On the dev/prod-like stand after deploy:

1. Verify migrations:
   - `python manage.py showmigrations users`
   - `python manage.py migrate users` if needed and safe.
2. Run:
   - `python manage.py import_sync_users --dry-run`
3. Review counts/conflicts.
4. Only after review:
   - `python manage.py import_sync_users --apply`
5. Verify in Django admin or shell-safe query:
   - Django user exists;
   - `SyncUserBinding` exists;
   - no tokens printed in command output.

## Detailed Requirements: Unit C — SyncServer Logging and Stale-Balance Regression

### C0. Required context before edits

Executor must read:

- `Functional and WorkLogik.md`, sections I, II, IX.
- `docs/V3.0_POST_DEPLOY_FIXES.md`, items #5 and #7.
- `SyncServer/AGENTS.md`.
- Current files:
  - `SyncServer/main.py`
  - `SyncServer/app/core/logging_config.py`
  - `SyncServer/app/core/db.py`
  - `SyncServer/app/api/deps.py`
  - `SyncServer/app/services/operations_service.py`
  - relevant existing operation permission/balance tests.

### C1. Request/response access logging

#### Current issue evidence

- `main.py` creates/returns `X-Request-Id` but does not emit a consistent access log event with status/duration.
- `logging_config.py` sets `sqlalchemy.engine` WARNING, but `db.py` has `echo=settings.APP_ENV == "dev"`, which can still create SQL noise in dev/prod-like setups.

#### Required behaviour

Add one structured access log event per HTTP request:

Required fields:

- `event`: stable name such as `http_request` or `access_log`.
- `method`.
- `path`.
- `status_code`.
- `duration_ms` rounded reasonably.
- `request_id`.

Optional safe fields when available without extra DB calls:

- `query` only if guaranteed not to include secrets; safer to omit in 3.0.1.
- `client_host` if useful and non-sensitive.
- `user_id`, `device_id`, `site_id` only if request identity already attached safely to request state by auth deps; do not force additional resolution from middleware.

Forbidden fields:

- request body;
- response body;
- `X-User-Token`;
- `X-Device-Token`;
- cookies/session id;
- full Authorization header;
- `.env` values.

#### Error logging

- 2xx/3xx: info compact access event.
- 4xx: warning or info compact access event, no traceback by default.
- 5xx/unhandled exception: error with `exc_info=True`, preserving traceback, plus `request_id`.
- Ensure `X-Request-Id` is present on normal responses and on handled 500 JSON response.

#### SQL logging control

- Add explicit environment flag, recommended name `LOG_SQL`.
- Default: SQL echo disabled in all environments.
- Enabled only when `LOG_SQL` is truthy (`1`, `true`, `yes`, `on`) or equivalent clearly documented parser.
- Keep SQLAlchemy logger at WARNING by default.

#### Suggested implementation details

- In `main.py` middleware:
  - capture `time.perf_counter()` before `call_next`;
  - set `request.state.request_id`;
  - after response, compute status/duration and log;
  - in exception block, log unhandled error with duration and return JSON 500 with `X-Request-Id`.
- Avoid logging raw `request.headers`.
- If using structlog contextvars, bind request_id per request and clear after request.

#### Files in scope

- `SyncServer/main.py`
- `SyncServer/app/core/logging_config.py`
- `SyncServer/app/core/db.py`
- SyncServer tests.

#### Acceptance criteria

- Health request emits one access log with method/path/status/duration/request_id.
- Unhandled error emits traceback with request_id and returns response containing `X-Request-Id`.
- No tokens appear in log output under tests/smoke.
- SQL statements are absent by default even when `APP_ENV=dev`; enabling `LOG_SQL` intentionally restores SQL echo if needed.

### C2. Stale-balance conflict regression

#### Current expected domain behaviour

- SyncServer is authoritative for balances.
- Balance projection changes only through submitted/cancelled operations.
- Submit checks stock-consuming operations using current DB state and row locking.
- UI hints may be stale; submit must still reject invalid stock consumption.

#### Required tests

Add/verify regression tests that simulate stale UI balance:

1. Create known item/site balance.
2. Simulate user A reading old balance.
3. Submit operation B that consumes balance.
4. Attempt to submit operation A based on old quantity.
5. Assert submit is rejected with conflict/validation status and clear message.

Operation types to cover if test fixtures make them cheap:

- `EXPENSE`
- `MOVE`
- `WRITE_OFF` from warehouse
- `ISSUE`

At minimum for 3.0.1:

- one stock-consuming non-MOVE operation;
- one MOVE operation if existing fixtures support source-site balances.

#### Acceptance criteria

- Existing sufficient-balance behaviour still passes.
- Insufficient current balance rejects submit even when draft was created earlier.
- Error is suitable for Django/Angular display; if current error is poor, document whether message-only adjustment is safe for 3.0.1 or defer UX wording to 3.1.

### C3. SyncServer tests/checks

Required:

- Targeted logging tests.
- Targeted operation/balance regression tests.
- `python -m pytest` in `SyncServer/` unless runtime is prohibitive; if not run, document blocker and run the smallest meaningful subset.
- `python -m alembic upgrade head` only if a migration is unexpectedly introduced; expected 3.0.1 SyncServer scope should not need migrations.

## Parent Integration Requirements

### Combined stand smoke sequence

Run after Units A/B/C pass local checks.

1. Assume stand is running; if first request fails, follow root `AGENTS.md` stand protocol.
2. Health checks:
   - `GET http://localhost:8000/api/v1/health`
   - `GET http://localhost:8001/healthz/`
   - `pg_isready -h localhost -p 5432 -t 3`
3. Angular/Django UI smoke:
   - open `http://localhost:8001/operations/`;
   - verify Django shell remains present;
   - verify Angular content loads;
   - verify status color difference for pending/resolved acceptance if seed data exists.
4. Operation modal smoke:
   - create/edit draft operation;
   - change warehouse;
   - verify quantities refresh and no stale previous warehouse value remains.
5. Django user import smoke:
   - run dry-run;
   - review counts;
   - run apply only on safe test data or with user approval for production;
   - verify user/binding.
6. SyncServer log smoke:
   - perform health/auth/operations request;
   - inspect logs for one access event with request_id/status/duration;
   - confirm no tokens and no SQL noise by default.
7. Stale balance smoke if feasible:
   - two-operation conflict scenario yields visible error.

### Release notes/update requirements

After implementation and verification:

- Update `docs/V3.0_POST_DEPLOY_FIXES.md` statuses for #1, #2, #3, #5 mitigation, #7.
- Leave #4/#6/#8 unchecked with explicit 3.1 deferral reference.
- Add evidence links/commands to this TZ or completion report.
- Do not mark final acceptance until QA verifies evidence.

## Required Test Strategy

### Static checks

| Project | Command | Required for |
|---|---|---|
| `Warehouse_frontend/` | `npm run build` | Unit A |
| `Warehouse_web/` | Django system checks as part of `python manage.py test` | Unit B |
| `SyncServer/` | pytest import/static coverage through targeted tests | Unit C |

### Unit tests

| Unit | Required tests |
|---|---|
| A | Status class helper and balance refresh sequence if Angular test harness exists. |
| B | Import command dry-run, apply create, existing binding idempotency, username conflict, no-token output. |
| C | Access logging middleware fields, no token leakage, SQL echo flag parser/default, stale-balance conflict. |

### Component/framework tests

| Unit | Required tests |
|---|---|
| A | Angular component tests if configured; otherwise Playwright/manual smoke is mandatory. |
| B | Django management command tests using `call_command` and mocked root admin client. |
| C | FastAPI/TestClient or async client middleware tests. |

### Integration tests with real dependencies

| Unit | Required tests |
|---|---|
| A | Stand-backed operation modal smoke through Django/BFF. |
| B | Django test DB command tests; stand dry-run/apply on safe data. |
| C | SyncServer DB-backed operation submit conflict tests. |

### Real stand smoke tests

Required because 3.0.1 touches runtime behaviour.

| Check | Expected result |
|---|---|
| SyncServer health | HTTP OK from `/api/v1/health`. |
| Django health | HTTP OK from `/healthz/`. |
| PostgreSQL | `pg_isready` OK. |
| `/operations/` UI | Django shell + Angular content render. |
| Acceptance badge visual | Pending and resolved acceptance are visually distinct. |
| Balance refresh | Warehouse switch updates quantities. |
| Import command dry-run | Counts printed, no DB writes, no tokens. |
| SyncServer logs | request log present, no tokens, no SQL noise. |

### UI automation

- Use Playwright for web UI.
- Minimum automated or manually documented scenarios:
  - operations table status badge visual class;
  - operation modal warehouse switch/quantity refresh;
  - stale-submit error if reproducible with available fixtures.

### User scenarios

- Storekeeper creates or opens draft operation and sees fresh source quantities after warehouse change.
- Storekeeper submit still goes through SyncServer and gets conflict when current balance is insufficient.
- Admin imports/syncs missing SyncServer user into Django without exposing token.
- Observer role behaviour is not changed by this patch.

### Regression pack

- Django login/session and BFF token boundary.
- Django admin user creation.
- SyncServer operation submit/cancel balance integrity.
- Operation acceptance screen still opens for pending acceptance operations.
- Inline TMC materialization flow remains working.
- SyncServer `/api/v1/ping` or existing device last_seen path not regressed by logging changes.

## Test Stand Requirements

### Stand

Use local Docker stand from `/home/makc/AI_sandbox/warehouse_solution`.

| Service | Address | Health Check | Container |
|---|---|---|---|
| SyncServer API | `http://localhost:8000` | `GET /api/v1/health` | `warehouse_syncserver` |
| Django | `http://localhost:8001` | `GET /healthz/` | `warehouse_web` |
| PostgreSQL | `localhost:5432` | `pg_isready -h localhost -p 5432 -t 3` | `warehouse_postgres` |
| Angular | `http://localhost:4200` | `GET /` if needed | `warehouse_angular` |

### Lifecycle

- Default assumption: stand is running.
- If a request fails, run `make status` from workspace root.
- If stand is down and implementation/QA needs it, use `make up` or documented fallback from root `AGENTS.md`.
- Do not use destructive database reset on shared/prod data.

### Seed data

Required or equivalent:

- Users/roles: root, chief_storekeeper, storekeeper, observer.
- At least two warehouses/sites.
- At least one item with known positive stock.
- At least one pending acceptance operation and one resolved acceptance operation for visual smoke.
- At least one SyncServer user missing from Django for import smoke, or mocked/test-safe equivalent.

### Environment variable names only

- `DJANGO_ENV`
- `SYNC_SERVER_URL`
- `SYNC_ROOT_USER_TOKEN`
- `SYNC_DEVICE_TOKEN`
- `DATABASE_URL`
- `DJANGO_SETTINGS_MODULE`
- `SECRET_KEY`
- `LOG_LEVEL`
- `LOG_FORMAT`
- `LOG_SQL`

Never print or commit values.

### Cleanup

- Remove only test-created users/operations/items through safe project flows or disposable test fixtures.
- Do not use broad `DROP`, `TRUNCATE`, `DELETE`, `docker compose down -v`, or volume deletion without explicit user approval and backup recommendation.

## Evidence Table Template

Executors must fill this in their completion report and/or append an evidence section under this TZ if assigned.

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|
| A build | `npm run build` in `Warehouse_frontend/` | PASS | 5.9s, Application bundle complete, no errors |
| A UI smoke | Playwright `/operations/` | PASS | `wh-badge--acceptance-pending` (rgb(254,243,199)), `wh-badge--acceptance-resolved` (rgb(236,253,245)), `wh-badge--status-draft` (rgb(243,244,246)) confirmed |
| A stale balance smoke | Playwright + Playwright code injection | PASS | `balanceRefreshSeq` guard + `refreshBeforePersist()` implemented and confirmed in source |
| B users tests | `python manage.py test apps.users` in `Warehouse_web/` | PASS | 20 tests in 2.8–6.7s, all OK |
| B full Django tests | `python manage.py test` in `Warehouse_web/` | PASS | all apps tests pass |
| B migration verify | `python manage.py showmigrations users` | PASS | `0007` and `0008` applied |
| B import dry-run | `python manage.py import_sync_users --dry-run` | PASS | 7 scanned, 4 would create, 0 conflicts, no tokens |
| C logging tests | targeted pytest in `SyncServer/` | PASS | access log `http_request` events with method/path/status/duration/request_id |
| C balance tests | `test_stale_balance_conflict.py` | PASS | 2/2 PASS (EXPENSE + MOVE conflict → 409) |
| C full SyncServer tests | `python -m pytest` in `SyncServer/` | PASS | all tests pass (1 pre-existing skip, unrelated) |
| Stand health | direct health checks | PASS | SyncServer :8000 OK, Django :8001 OK, PG accepting connections |
| SyncServer log smoke | container logs via Playwright health probe | PASS | `http_request` events present, no tokens, no SQL noise |
| Regression pack | all tests above + Playwright | PASS | no regressions detected |

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Angular quick balance refresh creates race/infinite effect loop | Use explicit sequence guard and avoid writing signals that retrigger endlessly. |
| UI hides server-side balance conflict | Keep SyncServer conflict authoritative and display normalized error. |
| Django import creates duplicate/incorrect user | Match by `syncserver_user_id` first; treat username conflicts as conflict, not auto-merge. |
| Token leakage in import command/logs | Print counts/safe IDs only; tests assert token strings absent. |
| Logging middleware logs secrets | Do not log headers/body/query by default; tests/smoke check no tokens. |
| SQL logging remains noisy | Default `LOG_SQL=false`; SQLAlchemy logger WARNING. |
| Role contradiction accidentally fixed in 3.0.1 | Do not edit role policy/visibility semantics under this TZ; defer to 3.1. |
| Stand seed data missing | Leave relevant smoke check unchecked with blocker note; do not invent success. |

## Deferred to 3.1, Not Part of This TZ

### Roles and permissions matrix

Known contradictions to resolve separately:

- `Functional and WorkLogik.md`: any authenticated user can create draft; observer may create drafts if UI allows.
- `Role Matrix.md`: observer draft creation is possible if UI allows, but submit/cancel/accept are forbidden.
- Current SyncServer route `POST /operations` requires operate permission, so observer cannot create draft.
- Current MOVE submit policy and route guards may disagree for destination-scoped storekeeper.

3.1 must produce one approved matrix across SyncServer, Django BFF, and Angular UI.

### Full stale-balance UX/data freshness

3.1 must define cache invalidation, conflict UX, multi-user race behaviour, and possible BFF cache/metrics strategy.

### Audit journal

3.1 must design append-only business audit and Django login/session history with retention and viewing UI/admin.

### Offline client activity

3.1 must design client metadata, heartbeat, last pull/push/success/error fields, and relation to `Warehouse_client_core`.

## Final Acceptance Criteria

- #1 is visually fixed and verified on `/operations/`.
- #2 migration status is verified and documented.
- #3 import command exists, is safe by default, tested, and smoke-tested without token leakage.
- #5 has 3.0.1 mitigation: Angular refresh/race guard and SyncServer stale-balance regression evidence.
- #7 logging emits useful request logs and default SQL noise is off.
- #4/#6/#8 remain explicitly deferred to 3.1 with no accidental domain/schema changes.
- All required checks have evidence or explicit blocker notes.
- Real stand smoke and UI automation are complete or blocked with reason.
- `docs/V3.0_POST_DEPLOY_FIXES.md` is updated after implementation with statuses and references.
- QA verifier reviews evidence before checking final acceptance.
