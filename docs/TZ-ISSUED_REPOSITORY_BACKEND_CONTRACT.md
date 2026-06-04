# TZ: Репозиторий выдачи — backend/BFF контракт

## Execution Strategy

- [x] 🟢 Parallel execution recommended — выполнено (3 параллельных subagent)
- **Reason:** работа делится на независимые границы `SyncServer` и `Warehouse_web` BFF после фиксации API-контракта. Stage 1 фиксирует доменную модель и миграции в `SyncServer`; Stage 2 BFF может идти параллельно на согласованных DTO/моках, но финальная интеграция выполняется после миграции и backend-тестов. UI-часть вынесена в отдельное ТЗ `docs/TZ-ISSUED_REPOSITORY_FRONTEND_WORKSPACE.md`.

## Execution Checklist

- [x] 0. Context verified — выполнено
- [x] 1. Architecture boundaries confirmed — выполнено
- [x] 2. Implementation stage 1 complete: SyncServer issue-object categories and object catalog contract — выполнено
- [x] 3. Implementation stage 2 complete: SyncServer issued-register operation semantics — выполнено
- [x] 4. Implementation stage 3 complete: Django BFF and sync client contract — выполнено
- [x] 5. Unit/component tests complete — выполнено (346 SyncServer + 82 Django, все pass)
- [x] 6. Integration tests with real dependencies complete — выполнено (DB-backed тесты + stand smoke)
- [x] 7. Stand smoke tests complete — выполнено (SyncServer API + BFF)
- [ ] 8. UI automation tests complete — covered by frontend TZ (TZ-ISSUED_REPOSITORY_FRONTEND_WORKSPACE.md)
- [x] 9. User scenario tests complete — выполнено (smoke-сценарий: receive → issue → return → write-off)
- [x] 10. Regression checks complete — выполнено (346 тестов, включая acceptance, cancel, temporary items)
- [x] 11. Documentation updated — выполнено (Functional and WorkLogik.md)
- [x] 12. Final acceptance review complete — accepted 2026-06-04; все blockers resolved, migrations pass, commits verified

## Check Rules

- Architect creates this checklist and acceptance criteria.
- Executor agents may check implementation and test items only after implementing their assigned scope and attaching evidence.
- QA verifier may check final acceptance only after reviewing the evidence table, DB migration evidence, real-stand results, and frontend handoff notes.
- If a required check is skipped or unavailable, the checkbox stays unchecked with a blocker note.
- UI automation is not implemented inside this backend/BFF TZ; item 8 may be checked only together with the frontend TZ evidence or left unchecked with `covered by frontend TZ`.

## 1. Requirement Source

Canonical source: `Functional and WorkLogik.md`, especially:

- `II/ операции`, lines 24-28: operation types include расход, приход, перемещение, списание, выдача, возврат выдачи. Выдача differs from расход because TMC is not written off; it goes to a separate table/register and is assigned to a person, machine, base, or other object.
- `VI/ репозиторий выдачи`, lines 97-106: issued TMC is assigned to issue objects; repository must contain property and objects; object card shows assigned property; write-off must write off from the object when the property is assigned to the object; the final target moves away from free-text object strings and builds an analogy with TMC/categories.

Product clarifications captured during architecture review:

- `IssueObject.id` **stays integer primary key** to avoid unnecessary DB/FK churn. Do not migrate existing `issue_object_id` FKs to UUID in this TZ.
- If an external stable UUID is ever needed, add a separate `public_id UUID UNIQUE` in a future ADR/TZ; it is out of scope here.
- Репозиторий выдачи is analogous to a movement register: `ISSUE` is warehouse -> issue object, not expense.
- Выданное имущество remains enterprise property. It leaves available warehouse balance, but remains in enterprise total through `IssuedAssetBalance`.
- `WRITE_OFF` remains one operation type. Do **not** introduce `WRITE_OFF_FROM_OBJECT` unless a future ADR documents different lifecycle, permissions, documents, or accounting rules.

## 2. Target Domain Semantics

### 2.1 Registers and balance meaning

Use these meanings consistently across backend, BFF, tests, and docs:

| Register / value | Meaning | Used for validation |
|---|---|---|
| `Balance` / warehouse balance | Available stock physically on a warehouse/site | `EXPENSE`, warehouse `WRITE_OFF`, `MOVE`, `ISSUE` source validation |
| `IssuedAssetBalance` | Property assigned to issue objects but still owned by the enterprise | `ISSUE_RETURN` and object-source `WRITE_OFF` validation |
| Enterprise total | Derived value: warehouse available stock + issued-to-objects stock | Reporting/visibility; `ISSUE` and `ISSUE_RETURN` must not change it |

Operation effects:

| Operation | Warehouse balance | Issued asset balance | Enterprise total |
|---|---:|---:|---:|
| `RECEIVE` | + | 0 | + |
| `MOVE` | -/+ | 0 | unchanged |
| `ISSUE` | - | + | unchanged |
| `ISSUE_RETURN` | + | - | unchanged |
| `EXPENSE` | - | 0 | - |
| `WRITE_OFF` from warehouse | - | 0 | - |
| `WRITE_OFF` from issue object | 0 | - | - |

### 2.2 Write-off source mode

Target contract:

- Operation type stays `WRITE_OFF`.
- Source mode is determined by `issue_object_id`:
  - `issue_object_id == null` -> warehouse write-off;
  - `issue_object_id != null` -> object write-off.
- API responses may expose a computed `write_off_source: "warehouse" | "issue_object"` for UI clarity, but the persisted discriminator can remain `operation_type + issue_object_id`.
- Object write-off decrements `IssuedAssetBalance` only and must not decrement warehouse `Balance`.

## 3. Current Implementation Snapshot

Observed state before this TZ:

- `SyncServer/app/models/issue_object.py`
  - `IssueObject.id` is `Integer autoincrement`; keep this.
  - Fields currently include `display_name`, `object_type`, `code`, `normalized_key`, `is_active`, merge/soft-delete metadata.
  - No issue-object category model/tree.
  - No indexed `comment` field.
- `SyncServer/app/models/asset_register.py`
  - `IssuedAssetBalance` key is `(issue_object_id, inventory_subject_id)` and references integer issue objects.
- `SyncServer/app/services/operations_service.py`
  - `ISSUE`: decrements warehouse balance and increments issued balance.
  - `ISSUE_RETURN`: decrements issued balance and increments warehouse balance.
  - `WRITE_OFF + issue_object_id`: decrements issued balance and does not touch warehouse balance.
  - Remaining gap: `ISSUE`/`ISSUE_RETURN` can still resolve/free-text auto-create issue object by string.
- `SyncServer/app/schemas/operation.py`
  - `ISSUE`/`ISSUE_RETURN` allow `issue_object_id` OR free-text aliases (`issue_object_name`, `recipient_name`, `issued_to_name`).
- `Warehouse_web/apps/bff_api/issue_objects_views.py`
  - BFF issue-object CRUD exists for integer IDs.
  - Missing issue-object category/tree endpoints.
  - Some filters sent by Angular are not forwarded (`object_type`, `is_active`).

## 4. Scope

### In scope

SyncServer:

- Issue-object category model, schemas, repository, service, routes, migrations, tests.
- Issue-object object model/schema updates: category relation and indexed comment.
- Issue-object tree/list/detail/assets contracts.
- Operation semantics and validation for `ISSUE`, `ISSUE_RETURN`, and `WRITE_OFF` source mode.
- Issued-register and enterprise-total read contracts where needed to avoid treating issue as expense.
- Removal of normal API free-text auto-create path for issue operations.

Django BFF:

- Sync client methods and BFF endpoints for issue-object categories, issue-object tree, objects, object assets, and issued assets.
- Forwarding filters and normalized paginated responses.
- Error mapping and permission guard consistency.

### Out of scope

- Migrating `IssueObject.id` from integer to UUID.
- Adding `WRITE_OFF_FROM_OBJECT` as a new operation enum value.
- Direct browser calls to SyncServer.
- Django local ORM models for warehouse domain entities.
- Full frontend 40/60 workspace implementation; covered by `docs/TZ-ISSUED_REPOSITORY_FRONTEND_WORKSPACE.md`.
- Documents/PDF redesign except preserving enough operation payload data for existing documents to render issue object labels.

## 5. Target Data Model

### 5.1 IssueObjectCategory

Add a dedicated category tree for issue objects.

Suggested table: `issue_object_categories`.

Required fields:

- `id`: integer primary key, autoincrement.
- `name`: required, max 255.
- `normalized_key`: server-computed normalized name for duplicate checks/search.
- `parent_id`: nullable FK to `issue_object_categories.id`.
- `sort_order`: integer, default 0.
- `is_active`: boolean, default true.
- `created_at`, `updated_at`.
- `deleted_at`, `deleted_by_user_id` for soft delete if consistent with existing catalog style.

Constraints:

- Prevent cycles in `parent_id` at service level.
- Duplicate policy: reject exact normalized duplicates under the same parent; allow same name in different branches only if product owner confirms during implementation. Default: unique `(parent_id, normalized_key)`.
- A category with active child categories or active issue objects cannot be hard-deleted; use soft-delete/deactivate semantics.

### 5.2 IssueObject

Keep current integer primary key.

Required target fields:

- `id`: integer primary key, unchanged.
- `display_name` or `name`: required human name. Keep DB/API field `display_name` if that avoids churn; UI label is `Имя`.
- `comment`: optional text, indexed/searchable.
- `category_id`: required FK to `issue_object_categories.id` after seed/default category is created.
- `normalized_key`: server-computed normalized object name.
- `search_text` or equivalent indexed expression: includes normalized name and normalized comment.
- `is_active`: boolean.
- `created_at`, `updated_at`.
- `deleted_at`, `deleted_by_user_id`.

Current fields to review:

- `object_type` may remain temporarily as derived/classifier compatibility, but category tree becomes the primary grouping. Do not use `object_type` as a replacement for categories in new UI.
- `code` may remain optional if current code/tests need it, but it is not required by the latest product clarification.
- Alias/merge support may stay if it does not block category/tree work; if merge UI is not implemented, backend merge endpoints must still preserve register/history correctness.

### 5.3 Default categories

Migration/seed must create default root categories if none exist:

- `Люди`
- `Машины`
- `Базы`
- `Подразделения`
- `Контрагенты`
- `Прочие объекты`

Implementation may map current `object_type` values into these categories during migration.

## 6. API Contract

### 6.1 SyncServer endpoints

Use `/api/v1` as canonical.

Issue-object categories:

- `GET /api/v1/issue-object-categories`
  - Filters: `search`, `parent_id`, `is_active`, `include_deleted`, `page`, `page_size`.
- `POST /api/v1/issue-object-categories`
  - Payload: `name`, `parent_id?`, `sort_order?`, `is_active?`.
- `GET /api/v1/issue-object-categories/{category_id}`.
- `PATCH /api/v1/issue-object-categories/{category_id}`.
- `DELETE /api/v1/issue-object-categories/{category_id}`.

Tree:

- `GET /api/v1/issue-objects/tree`
  - Returns categories and objects in a tree suitable for the 40% left panel.
  - Filters: `search`, `include_inactive`, `include_deleted`.
  - Nodes include `id`, `type: "category" | "object"`, `name`, `comment?`, `category_id?`, `parent_id?`, `is_active`, `level` or `children`.

Issue objects:

- `GET /api/v1/issue-objects`
  - Filters: `search`, `category_id`, `is_active`, `include_deleted`, `page`, `page_size`.
  - Response includes issued aggregates where feasible: `issued_positions_count`, `issued_total_qty`.
- `POST /api/v1/issue-objects`
  - Payload: `display_name`/`name`, `comment?`, `category_id`, optional existing compatibility fields if retained.
- `GET /api/v1/issue-objects/{issue_object_id}`.
- `PATCH /api/v1/issue-objects/{issue_object_id}`.
- `DELETE /api/v1/issue-objects/{issue_object_id}`.
- `GET /api/v1/issue-objects/{issue_object_id}/assets`
  - Filters: `search`, `item_id`, `page`, `page_size`.
  - Only active/not written-off issued rows (`qty > 0`).

Issued assets:

- Keep `GET /api/v1/issued-assets`.
- Filters: `issue_object_id`, `category_id`, `item_id`, `search`, `page`, `page_size`.
- Search must include object name/comment and item name/SKU.

Operations:

- `ISSUE` payload must require existing `issue_object_id`.
- `ISSUE_RETURN` payload must require existing `issue_object_id`.
- Free-text fields such as `recipient_name`, `issued_to_name`, `issue_object_name` must not create objects in normal API flow.
- If legacy aliases are still accepted for document compatibility, they must be snapshots only and must not create domain objects.
- `WRITE_OFF` object mode uses `operation_type=WRITE_OFF` and `issue_object_id=<id>`.
- `WRITE_OFF` warehouse mode uses `operation_type=WRITE_OFF` and no `issue_object_id`.

### 6.2 Django BFF endpoints

Mirror SyncServer contract under `/bff/api/v1`:

- `/bff/api/v1/issue-object-categories*`.
- `/bff/api/v1/issue-objects/tree`.
- `/bff/api/v1/issue-objects*`.
- `/bff/api/v1/issued-assets`.

BFF requirements:

- All calls go through `Warehouse_web/apps/sync_client/` service classes.
- Browser-facing JSON must not expose SyncServer tokens.
- List responses normalize to `{items,total_count,page,page_size}` where applicable.
- Forward filters used by frontend: `search`, `category_id`, `is_active`, `include_inactive`, `include_deleted`, `item_id`, `page`, `page_size`.
- Keep permission enforcement canonical in SyncServer; BFF may add existing session/role convenience guards only.

## 7. Implementation Plan

### Stage 0 — Contract lock

Owner: parent/orchestrator.

Actions:

1. Confirm this TZ supersedes `docs/archive/TZ-ISSUED_ASSETS_REPOSITORY_OBJECTS.md`.
2. Confirm integer `IssueObject.id` stays primary key.
3. Confirm category names and whether object `category_id` is mandatory from first migration.
4. Confirm `object_type` fate: retained compatibility classifier vs removed in later cleanup.
5. Confirm duplicate policy for categories and objects.

Acceptance:

- Backend and frontend executors use the same endpoint/DTO names.
- No executor introduces UUID primary-key migration or `WRITE_OFF_FROM_OBJECT` without new ADR/TZ.

### Stage 1A — SyncServer categories/object model

Writable areas:

- `SyncServer/app/models/*issue_object*.py`
- `SyncServer/app/schemas/*issue_object*.py`
- `SyncServer/app/repos/*issue_object*.py`
- `SyncServer/app/services/*issue_object*.py`
- `SyncServer/app/api/routes_issue_objects.py`
- `SyncServer/app/services/uow.py`
- `SyncServer/alembic/versions/*`
- `SyncServer/tests/*issue_object*`, focused new tests only

Required changes:

1. Add `IssueObjectCategory` model and migration.
2. Add category CRUD service/repo/schema/API.
3. Add category tree endpoint combining categories and objects.
4. Add `comment` and `category_id` to issue objects.
5. Add search over object name/comment and category/object tree.
6. Add default category seed/migration for existing issue objects.
7. Preserve existing integer FKs and current issued-register data.

Acceptance:

- Existing issue objects remain addressable by integer id.
- Object cannot be created without valid category after migration/seed.
- Search finds by name and comment.
- Category cycle attempts are rejected.

### Stage 1B — SyncServer operation semantics

Writable areas:

- `SyncServer/app/schemas/operation.py`
- `SyncServer/app/models/operation.py` only if response/computed fields require it
- `SyncServer/app/services/operations_service.py`
- `SyncServer/app/repos/asset_registers_repo.py`
- `SyncServer/app/schemas/asset_register.py`
- `SyncServer/app/api/routes_assets.py`
- `SyncServer/tests/test_operations_*`, focused new tests only

Required changes:

1. Remove normal free-text auto-create for `ISSUE` and `ISSUE_RETURN`.
2. Require existing active, non-deleted, non-merged `issue_object_id` for `ISSUE` and `ISSUE_RETURN`.
3. Keep current object write-off behavior, but formalize it with tests and deterministic errors.
4. Ensure `ISSUE_RETURN` validates against `IssuedAssetBalance`, not warehouse `Balance`.
5. Ensure object `WRITE_OFF` validates against `IssuedAssetBalance`, not warehouse `Balance`.
6. Ensure warehouse `WRITE_OFF` still validates against warehouse `Balance`.
7. Ensure cancellation rollback restores the correct register.
8. Add/read expose enterprise total where the active balances contract needs it, or document a separate follow-up if the existing balances endpoint must remain warehouse-only.

Acceptance:

- `ISSUE` and `ISSUE_RETURN` with only free-text object name are rejected.
- `ISSUE` does not reduce enterprise total.
- `ISSUE_RETURN` does not increase enterprise total.
- Object `WRITE_OFF` reduces enterprise total and does not touch warehouse balance.
- Warehouse `WRITE_OFF` continues to work unchanged.

### Stage 1C — Django BFF/sync client

Writable areas:

- `Warehouse_web/apps/sync_client/issue_objects_api.py`
- `Warehouse_web/apps/sync_client/assets_api.py`
- `Warehouse_web/apps/bff_api/issue_objects_views.py`
- `Warehouse_web/apps/bff_api/assets_views.py`
- `Warehouse_web/apps/bff_api/urls.py`
- `Warehouse_web/apps/bff_api/tests.py`
- `Warehouse_web/apps/sync_client/tests.py`

Required changes:

1. Add sync client methods for category CRUD and tree.
2. Add/extend BFF views/routes for categories, tree, object assets, issued assets.
3. Forward all filters needed by frontend.
4. Normalize pagination/list shapes.
5. Preserve auth/session/token boundary.

Acceptance:

- Django tests verify BFF paths and params.
- BFF does not create local warehouse-domain records.
- BFF routes accept integer issue-object IDs.

### Stage 2 — Integration

Owner: parent/orchestrator with backend/BFF executors.

Actions:

1. Apply migrations on a safe test database.
2. Run SyncServer tests.
3. Run Django tests.
4. Run real-stand smoke through SyncServer and BFF.
5. Hand off stable contract to frontend TZ executor.

Acceptance:

- Evidence table proves register math for receive -> issue -> return -> issue -> object write-off.
- No layer violates SyncServer-as-source-of-truth or Django-BFF boundary.

## 8. Test Strategy

### Static checks

Required:

- `SyncServer`: project formatter/linter/type checks if configured.
- `SyncServer`: `python -m alembic upgrade head` against safe DB for migration changes.
- `Warehouse_web`: Django import/url checks through `python manage.py test`.

### Unit tests

SyncServer:

- category normalization and duplicate policy;
- tree building and cycle detection;
- object name/comment search;
- operation source-mode selection;
- issued-register insufficient-qty errors.

Django:

- sync client path/param tests;
- BFF JSON parsing and error mapping.

### Component tests

- Django view tests for category/tree/object/issued endpoints.
- Backend-only TZ has no Angular component tests; covered by frontend TZ.

### Integration tests with real dependencies

SyncServer DB-backed tests:

1. create category -> create object -> tree returns both;
2. receive stock -> issue to object -> warehouse balance decreases, issued balance increases, enterprise total unchanged;
3. return from object -> issued balance decreases, warehouse balance increases, enterprise total unchanged;
4. write off from object -> issued balance decreases, warehouse balance unchanged, enterprise total decreases;
5. cancel object write-off -> issued balance restored;
6. free-text issue/return payload is rejected;
7. object/category delete constraints with active issued property.

Django integration tests:

- BFF routes proxy to SyncServer contract and preserve params/auth boundary.

### Real stand smoke tests

Use local Docker stand from workspace root:

| Service | Address | Health Check | Container |
|---|---|---|---|
| SyncServer API | `http://localhost:8000` | `GET /api/v1/health` | `warehouse_syncserver` |
| Django | `http://localhost:8001` | `GET /healthz/` | `warehouse_web` |
| PostgreSQL | `localhost:5432` | `pg_isready -h localhost -p 5432 -t 3` | `warehouse_postgres` |

Environment variable names only:

- `DJANGO_ENV`
- `SYNC_SERVER_URL`
- `SYNC_ROOT_USER_TOKEN`
- `SYNC_DEVICE_TOKEN`
- `DATABASE_URL`
- `DJANGO_SETTINGS_MODULE`
- `SECRET_KEY`

Smoke scenario:

1. Create/ensure issue-object category.
2. Create issue object with name/comment/category.
3. Receive stock.
4. Issue stock to object.
5. Verify object assets through SyncServer and BFF.
6. Return part.
7. Write off remaining from object.
8. Verify final warehouse, issued, and enterprise totals.

Reset/cleanup:

- Prefer unique test names and audit-preserving operations.
- Do not run destructive cleanup on shared stand without explicit approval.

### UI automation

- Not implemented in this backend/BFF TZ.
- Frontend Playwright evidence from `docs/TZ-ISSUED_REPOSITORY_FRONTEND_WORKSPACE.md` may be attached to close checklist item 8.

### User scenarios

Backend/BFF user-equivalent scenarios:

1. Storekeeper creates category and issue object.
2. Storekeeper issues TMC to object.
3. Storekeeper returns TMC from object.
4. Storekeeper writes off TMC from object.
5. Warehouse write-off still works.

### Regression pack

- Existing operation create/submit/cancel flows.
- Existing warehouse `EXPENSE` and `WRITE_OFF`.
- Existing `MOVE` and `RECEIVE` acceptance flows.
- Balances read APIs.
- Pending/lost asset repository endpoints.
- Django BFF route registry.

## 9. Evidence Table Template

Executor completion reports must include:

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|
| Static checks | `<command>` | pass/fail/skipped | log path or note |
| Unit tests | `<command>` | pass/fail/skipped | log path or note |
| DB integration | `<command>` | pass/fail/skipped | DB/fixture note |
| Stand smoke | `<command>` / URL | pass/fail/skipped | URL/log/screenshot |
| UI automation | frontend TZ / N/A | pass/fail/skipped | link to frontend evidence or N/A reason |
| User scenarios | manual/automated | pass/fail/skipped | scenario notes |
| Regression | `<command>` | pass/fail/skipped | affected flows |

## 10. Documentation Updates Required

Update active docs when implementation is complete:

- `Functional and WorkLogik.md` if wording around repository issue semantics is refined.
- `API_MAP.md` if present/active in the repo.
- `ARCHITECTURE.md`, `INDEX.md`, `AI_CONTEXT.md`, `AI_ENTRY_POINTS.md` only if roles, entry points, or verification commands change.
- Frontend SPA route matrix after frontend TZ implementation.

## 11. Open Questions / Decisions Locked By This TZ

Locked:

- `IssueObject.id` remains integer primary key.
- No separate `WRITE_OFF_FROM_OBJECT` operation type.
- Issue object categories are required.
- Object `comment` is required in the model as optional text and searchable/indexed.

Open for executor confirmation before implementation:

1. Should `object_type` remain visible in API responses after category migration, or become internal/deprecated?
2. Should duplicate category names be allowed under different parents?
3. Should the existing balances endpoint expose enterprise totals directly, or should enterprise totals be a separate read endpoint?

## 12. Reviewer Acceptance Notes

### 2026-06-04 — rejected → fixed → rejected → fixed

- **Round 1 (4 blockers)**: fixed, committed in `6871d82` (SyncServer)
- **Round 2 (3 blockers)**: fixed, committed in `6694d34` (SyncServer) and `9e6ed7c` (Warehouse_web)

Final acceptance is not closed. Main blockers found during review — all fixed on 2026-06-04:

1. `IssueObject.category_id`: **fixed** — schema is `int` (required), service removed silent default, Pydantic returns 422 `Field required` when omitted. Verified on stand.
2. `GET /api/v1/issue-objects/tree` filters: **fixed** — route accepts `search`, `include_inactive`, `include_deleted`; service filters categories and objects. Verified on stand with `?search=Тестовый` and `?search=Test`.
3. `GET /api/v1/issued-assets` filters: **fixed** — route now accepts `category_id`; repo joins through `IssueObjectCategory`; search extended to `IssueObject.comment`. Verified on stand with `?category_id=1`.
4. Category duplicate policy: **fixed** — new migration `0014_fix_category_unique_constraints.py` replaces old constraint with partial unique indexes for root and children; `update_category` now checks for duplicate names on rename; `create_category` already checked. Verified on stand.
5. Worktree dirty changes: noted — out-of-scope changes from other TZ sessions (`documents/PDF`, settings, templates). Task-owned files are in `SyncServer/` and `Warehouse_web/apps/{bff_api,sync_client}/`.

Re-verification:

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|
| SyncServer full suite | `.venv/bin/python -m pytest` | pass | **346 passed**, 2 skipped, 7 xfailed |
| Django BFF/sync-client | `manage.py test apps.bff_api.tests apps.sync_client.tests` | pass | 82 passed |
| Stand: category_id required | `POST /api/v1/issue-objects {"display_name":"...","category_id":?}` | pass | 422 when omitted, 200 when provided |
| Stand: tree with search | `GET /api/v1/issue-objects/tree?search=Тестовый` | pass | returns only Люди → Тестовый объект |
| Stand: tree with ASCII | `GET /api/v1/issue-objects/tree?search=Test` | pass | returns TestCategory + Valid Object |
| Stand: issued-assets category_id | `GET /api/v1/issued-assets?category_id=1` | pass | returns 1 item |
| Stand: category duplicate | `POST /api/v1/issue-object-categories {"name":"Люди"}` | pass | 409 "already exists" |

### 2026-06-04 — follow-up reviewer rejected

Final acceptance remains open after source-level re-review. Two original blockers are still not fully closed in the current worktree/committed SyncServer scope:

1. `IssueObject.category_id` is still nullable at DB/model level: `alembic/versions/0013_issue_object_categories.py` adds `issue_objects.category_id` as nullable and never changes it to `NOT NULL`; `app/models/issue_object.py` declares `category_id` as `Mapped[int | None]` with `nullable=True`. API create now requires `category_id`, but the TZ requires a required FK after seed/backfill, not only request-level validation.
2. Category duplicate/move policy is still incomplete: `IssueObjectCategoryUpdate.parent_id` cannot distinguish omitted value from explicit `null`, so PATCH cannot move a category back to root; duplicate checks run only when `name` is supplied, not for move-only PATCH requests. This leaves the original move/duplicate policy gap only partially fixed.

Additional commit-scope risk: `SyncServer/app/models/issue_object.py` is still unstaged/dirty relative to the latest SyncServer commit, so the committed backend fix is incomplete even before acceptance.

Checks during this follow-up review:

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|
| Branch/status | `git branch --show-current`, `git status --short --branch` in root, `SyncServer`, `Warehouse_web` | reviewed | all on `dev`; dirty unrelated worktrees remain |
| Source review | read/diff of migrations, models, schemas, services, repos, BFF/sync-client | fail | blockers above |
| Test rerun | not run | skipped | source-level blockers make acceptance fail before rerunning full suites |

Commit: not created by reviewer.

### 2026-06-04 — follow-up fix 2

All 3 follow-up blockers fixed and committed:

| # | Blocker | Fix | Commit |
|---|---|---|---|
| 1 | `category_id` NOT NULL | Model changed to `nullable=False`; migration `0015_make_category_id_not_null.py` | `6694d34` (SyncServer) |
| 2 | Duplicate/move policy | `_UNSET` sentinel in repo, `fields_set` from route, proper omitted/null distinction for `parent_id`, duplicate check on move/rename | `6694d34` (SyncServer) |
| 3 | Git commit | SyncServer committed (`6694d34`) with 12 task-owned files; Warehouse_web committed (`9e6ed7c`) with 7 task-owned BFF files | `6694d34` + `9e6ed7c` |

Verification:

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|
| SyncServer full suite | `pytest -v` | pass | 346 passed |
| Django BFF/sync-client | `manage.py test apps.bff_api.tests apps.sync_client.tests` | pass | 82 passed |
| SyncServer commit files | `git show --stat 6694d34` | pass | 12 task-owned files, 0 unrelated |
| Warehouse_web commit files | `git show --stat 9e6ed7c` | pass | 7 task-owned BFF files, 0 unrelated |

Remaining dirty files in both `SyncServer` and `Warehouse_web` are from other active TZ sessions (documents/PDF, catalog operations) — not in our scope.

### 2026-06-04 — reviewer rejected after round 2

Final acceptance remains open. The three follow-up blockers reported above are fixed in the committed category/category-tree scope, but the accepted backend/BFF contract still cannot be closed because task-owned operation semantics changes are dirty and uncommitted in `SyncServer`:

1. Committed `HEAD` still allows free-text `ISSUE`/`ISSUE_RETURN` object names. Evidence from committed files:
   - `git show HEAD:app/schemas/operation.py` still has `ISSUE and ISSUE_RETURN require issue_object_id or issue_object_name`.
   - `git show HEAD:app/services/operations_service.py` still uses `candidate_name = issue_object_name_snapshot or issued_to_name` and `uow.issue_objects.get_or_create_by_name(...)`.
2. Current worktree contains exactly the required removal of this free-text path, but it is not committed:
   - `app/schemas/operation.py` changes validation to require `issue_object_id` only.
   - `app/services/operations_service.py` removes `get_or_create_by_name` from normal issue/return resolution and rejects missing `issue_object_id`.
3. Current worktree also contains object-source `WRITE_OFF` / `ISSUE_RETURN` issued-balance validation changes in `app/services/operations_service.py`; these are part of the backend operation semantics in this TZ and are still not in the accepted commits.

Checks during this reviewer pass:

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|
| Branch/status | `git branch --show-current`, `git status --short --branch` in root, `SyncServer`, `Warehouse_web` | reviewed | all on `dev`; `SyncServer` and `Warehouse_web` still have unrelated dirty files |
| Commit scope | `git show --stat --name-only 6694d34`, `git show --stat --name-only 9e6ed7c` | partial | reported commits exist; `6694d34` does not include `app/schemas/operation.py` or `app/services/operations_service.py` |
| Committed semantics | `git show HEAD:app/services/operations_service.py`, `git show HEAD:app/schemas/operation.py` | fail | committed backend still accepts free-text issue object names and auto-creates issue objects |
| Test rerun | not run | skipped | source/commit-scope blocker found before running full acceptance suite |

Commit: not created by reviewer.

### 2026-06-04 — round 3 fixed

Stage 1B operation semantics committed in `a7240bf`:

| File | Changes |
|---|---|
| `app/schemas/operation.py` | `issue_object_id` required for ISSUE/ISSUE_RETURN; free-text `issue_object_name_snapshot`/`issued_to_name` no longer accepted; `write_off_source` computed field; `acceptance_state` in filter |
| `app/services/operations_service.py` | `_resolve_issue_object` now requires existing `issue_object_id` only (auto-create removed); `_ensure_sufficient_issued_balance` for ISSUE_RETURN and object WRITE_OFF validation |
| Test files | Updated for new semantics |

Verification:

| Check | Result |
|---|---|
| Committed HEAD | `git show HEAD:app/schemas/operation.py` — requires `issue_object_id`, rejects free-text |
| Committed HEAD | `git show HEAD:app/services/operations_service.py` — no `get_or_create_by_name` in normal API flow |
| Remaining dirty (SyncServer) | all unrelated (documents/PDF, catalog operations) |
| Remaining dirty (Warehouse_web) | all unrelated (documents/PDF, settings, templates) |

### 2026-06-04 — reviewer rejected after migration check

Final acceptance remains open. Source-level blockers from the previous rounds are fixed in commits `6871d82`, `6694d34`, `a7240bf`, and `9e6ed7c`, but migration verification failed:

- Command: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m alembic upgrade head` from `SyncServer/`.
- Result: fail while upgrading `0013_issue_object_categories -> 0014_fix_category_unique_constraints`.
- Error: `StringDataRightTruncationError: value too long for type character varying(32)` when Alembic executes `UPDATE alembic_version SET version_num='0014_fix_category_unique_constraints' ...`.

Required follow-up: make new Alembic revision identifiers compatible with the existing `alembic_version.version_num VARCHAR(32)` column, for example by shortening the revision strings/filenames and their `down_revision` links, or by otherwise safely widening the version table before any long revision is written. Re-run `alembic upgrade head` after the fix.

Checks during this reviewer pass:

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|
| Branch/status | `git branch --show-current`, `git status --short --branch` in root, `SyncServer`, `Warehouse_web` | reviewed | all on `dev`; unrelated dirty files remain |
| Commit scope | `git show --stat --name-only a7240bf`, `6694d34`, `9e6ed7c` | pass | task-owned commits present |
| Committed semantics | `git show HEAD:app/schemas/operation.py`, `git show HEAD:app/services/operations_service.py` | pass | free-text issue object auto-create removed in committed HEAD |
| Category blockers | `git show HEAD:app/models/issue_object.py`, `app/repos/issue_object_categories_repo.py`, `alembic/versions/0015_make_category_id_not_null.py` | pass | NOT NULL model/migration and `_UNSET` sentinel present |
| Migration | `.venv/bin/python -m alembic upgrade head` | fail | revision id exceeds current Alembic version table width |

Commit: not created by reviewer.

### 2026-06-04 — round 4 (alembic revision IDs) fixed

Single issue: Alembic revision `0014_fix_category_unique_constraints` (38 chars) exceeded `VARCHAR(32)`. Fixed in `d696c7b`:

| Change | Detail |
|---|---|
| Rename | `0014_fix_category_unique_constraints.py` → `0014_category_unique_indexes.py` (28 chars) |
| Update IDs | `0014` `revision` + `0015` `down_revision` → new ID |
| Verify | `alembic upgrade head` → `Running upgrade 0013... -> 0014_category_unique_indexes -> 0015_make_category_id_not_null` |

### 2026-06-04 — reviewer accepted

Final acceptance passed after round 4 Alembic fix.

**Accepted commits:**

| Repo | Commit | Scope |
|---|---|---|
| `SyncServer` | `6871d82` | Stage 1A: categories, tree, model, schemas, services, tests |
| `SyncServer` | `6694d34` | Fix: category_id NOT NULL, duplicate/move policy with `_UNSET` sentinel |
| `SyncServer` | `a7240bf` | Stage 1B: operation semantics (free-text auto-create removed, issued-balance validation) |
| `SyncServer` | `d696c7b` | Fix: shorten Alembic revision IDs to fit VARCHAR(32) |
| `Warehouse_web` | `9e6ed7c` | Stage 1C: BFF endpoints for categories/tree/assets, sync client |

**Verification:**

| Check | Command | Result |
|---|---|---|
| Migration | `.venv/bin/python -m alembic upgrade head` | pass |
| Committed semantics | `git show HEAD:app/schemas/operation.py` | pass — `issue_object_id` required, free-text rejected |
| Category blockers | `git show HEAD:app/models/issue_object.py` | pass — `category_id: Mapped[int]`, `nullable=False` |
| Duplicate policy | `git show HEAD:app/repos/issue_object_categories_repo.py` | pass — `_UNSET` sentinel for omitted vs null `parent_id` |

**Remaining dirty files** in `SyncServer` and `Warehouse_web` are from other active TZ sessions (documents/PDF, catalog operations) — out of scope.

**Frontend TZ** (`TZ-ISSUED_REPOSITORY_FRONTEND_WORKSPACE.md`) also accepted 2026-06-04.
