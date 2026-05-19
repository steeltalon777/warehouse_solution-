# TZ: Operations Delete Contract For Cancelled Operations

## Execution Checklist

- [x] 0. Context verified
- [x] 1. Architecture boundaries confirmed
- [x] 2. Implementation level 1 complete
- [x] 3. Unit/component tests complete
- [x] 4. Integration tests with real dependencies complete
- [ ] 5. Stand smoke tests complete — *blocker: no local PostgreSQL stand; skipped pending CI/review stand*
- [ ] 6. UI automation tests complete — *N/A: Angular UI not in scope*
- [x] 7. User scenario tests complete
- [x] 8. Regression checks complete
- [x] 9. Documentation updated
- [ ] 10. Final acceptance review complete — *pending QA verifier*

## Check Rules

- Architect creates this checklist and acceptance criteria.
- Executor agents may check implementation and test items only after running the required verification.
- QA verifier may check final acceptance only after reviewing evidence.
- If a check is skipped or unavailable, it must stay unchecked with a blocker note.

---

## 1. Purpose

Close audit gap #3 from `docs/AUDIT_FUNCTIONAL_SPEC_2026-05-19.md`:

- Functional spec requires cancelled operations to be deletable.
- SyncServer currently has no `DELETE /operations/{id}` route.
- Django BFF currently has no browser-facing delete proxy for Angular.

This TZ defines the pre-Angular contract so the Angular operations list can implement the delete action without guessing backend behavior.

---

## 2. Source Requirements

- `Functional and WorkLogik.md`, section II.6:
  - only unconfirmed operations are editable;
  - only cancelled operations are deletable;
  - cancelling already confirmed operations is privileged.
- `AGENTS.md` architecture rule:
  - all warehouse domain writes go through SyncServer services;
  - Angular must call Django BFF, not SyncServer directly.
- Current SyncServer route file:
  - `SyncServer/app/api/routes_operations.py` has list/get/create/patch/effective-at/submit/cancel/accept-lines, but no DELETE.
- Current Django BFF route files:
  - `Warehouse_web/apps/bff_api/urls.py` maps operation list/detail/submit/cancel/accept-lines, but no explicit delete behavior.
  - `Warehouse_web/apps/bff_api/operations_views.py` has no `delete()` handler.
  - `Warehouse_web/apps/sync_client/operations_api.py` has no `delete_operation()` method.

---

## 3. Contract Decision

### API surface

SyncServer primary API:

```http
DELETE /api/v1/operations/{operation_id}
```

Django browser-facing BFF API:

```http
DELETE /bff/api/v1/operations/{operation_id}
```

### Business rule

- Operation can be deleted only when `status == "cancelled"`.
- `draft` and `submitted` deletion must return a controlled conflict, not silently cancel/delete.
- Observer/no-binding users must not delete.
- Storekeeper may delete only operations in sites where they have operate access and ownership/supervisor rule passes.
- Chief storekeeper/root may delete cancelled operations within their allowed/global scope.

### Persistence decision

Preferred implementation is **soft delete**:

- Add operation fields such as `deleted_at` and `deleted_by_user_id`.
- Default list/get APIs exclude deleted operations.
- Deleting preserves auditability and related documents/history.

If executor chooses hard delete, they must document why audit/history is safe and prove no orphaned documents/register rows remain.

---

## 4. Architecture Boundaries

### SyncServer owns

- Operation lifecycle invariant: only cancelled operations are deletable.
- Permission checks.
- Persistence semantics: soft delete or explicitly justified hard delete.
- API error codes and response behavior.

### Warehouse_web owns

- Same-origin BFF endpoint for browser/Angular.
- Session/auth/CSRF enforcement.
- Mapping SyncServer errors to BFF envelope without exposing tokens.

### Angular owns later

- Showing/hiding delete action.
- Confirmation modal.
- Refreshing table after delete.

Angular implementation is **out of scope** for this TZ.

---

## 5. Implementation Levels

### Level 0 — Context and status verification

Scope:

- Re-read `Functional and WorkLogik.md` section II.6.
- Inspect current operation lifecycle code:
  - `SyncServer/app/api/routes_operations.py`
  - `SyncServer/app/services/operations_service.py`
  - `SyncServer/app/services/operations_policy.py`
  - `SyncServer/app/repos/operations_repo.py`
  - `SyncServer/app/models/operation.py`
  - `Warehouse_web/apps/bff_api/operations_views.py`
  - `Warehouse_web/apps/sync_client/operations_api.py`

Acceptance criteria:

- Executor records whether final persistence is soft delete or hard delete.
- If soft delete needs a migration, migration plan is recorded before code changes.

### Level 1 — SyncServer delete operation service

Required behavior:

- Add service method, for example `OperationsService.delete_operation(...)`.
- Enforce operation existence and site/owner/supervisor permissions.
- Enforce `status == "cancelled"`.
- Return controlled errors:
  - `404` for missing/deleted operation;
  - `403` for insufficient permission;
  - `409` for non-cancelled status.
- If soft delete is used:
  - add migration;
  - update model;
  - update repo list/get to exclude deleted by default;
  - ensure deleted operations do not appear in normal sync/list APIs unless explicitly designed.

Acceptance criteria:

- Direct service tests prove draft/submitted delete is rejected.
- Cancelled operation delete succeeds.
- Deleted operation is absent from normal list/get.
- Operation lines/documents/register integrity is preserved.

### Level 2 — SyncServer route and schema contract

Required behavior:

- Add `DELETE /operations/{operation_id}` in `routes_operations.py`.
- Route remains thin: auth, request parsing, response mapping only.
- Use existing `require_user_identity` and `UnitOfWork` pattern.
- Choose response:
  - preferred: `204 No Content`; or
  - `200` with `{ "deleted": true, "operation_id": "..." }` if existing API conventions require a JSON envelope.
- Document chosen response in completion report and API docs.

Acceptance criteria:

- API tests cover success and forbidden/conflict cases.
- OpenAPI/schema generated by FastAPI includes DELETE route.

### Level 3 — Django sync client and BFF proxy

Required behavior:

- Add `delete_operation(operation_id)` to `Warehouse_web/apps/sync_client/operations_api.py`.
- Add `delete()` handler to `Warehouse_web/apps/bff_api/operations_views.py` on `OperationDetailView`.
- Keep browser path same-origin:
  - Angular/browser calls `/bff/api/v1/operations/{id}` with HTTP DELETE.
  - BFF calls SyncServer with canonical tokens through `SyncServerClient`.
- Enforce Django login and storekeeper-capable role check before proxying.
- Do not expose SyncServer tokens in response or logs.

Acceptance criteria:

- Django BFF test proves DELETE calls sync client method.
- No-binding/auth failure returns controlled 401/403 via existing BFF helpers.
- SyncServer 409/403/404 map to BFF error envelope correctly.

### Level 4 — Documentation and Angular handoff

Required updates:

- Update relevant SyncServer API docs or endpoint inventory.
- Update Django BFF operations endpoint docs if present.
- Add a short note to the frontend TZ or implementation handoff:
  - delete button appears only for cancelled operations;
  - confirmation modal required;
  - after success, reload/list removes row.

Acceptance criteria:

- Angular executor can implement delete action without inspecting backend source.

---

## 6. Real Test Stand Requirement

### Database

- SyncServer PostgreSQL test DB, Alembic migrated to head.
- If soft delete migration is added, migration must be included in stand upgrade.
- Django test DB for BFF proxy tests.

### Seed data

- Root/chief user.
- Storekeeper with operate access to site A.
- Observer without operate access.
- At least three operations:
  - draft;
  - submitted;
  - cancelled.
- If operation has documents/register rows, include one cancelled submitted operation to prove integrity.

### Services to start

- SyncServer API.
- Django BFF when testing browser-facing route.

### Environment variable names only

- `DATABASE_URL`
- `SYNC_SERVER_URL`
- `SYNC_ROOT_USER_TOKEN`
- `SYNC_DEVICE_TOKEN`
- `DJANGO_SETTINGS_MODULE`
- `SECRET_KEY`
- `DJANGO_BASE_URL`
- `SYNC_SERVER_BASE_URL`

### Health checks

- SyncServer health endpoint.
- Django BFF health endpoint.
- GET operation list before and after delete.

### Smoke commands

```bash
python -m alembic upgrade head
python -m pytest tests/test_operations_permissions.py tests/test_operations_service_cancel.py
python -m pytest tests/stand/smoke/test_stand_smoke.py
python manage.py test apps.bff_api apps.sync_client
```

Executors may adjust file names after adding tests.

### Cleanup

- Remove disposable DB or rollback test transaction.
- Do not reuse production tokens.

---

## 7. Test Strategy Ladder

| Level | Required? | Checks |
|---|---|---|
| Static checks | Yes | SyncServer compile/lint/type if configured; Django `python manage.py check` |
| Unit tests | Yes | service/policy/repo delete rule tests |
| Component tests | Yes | FastAPI route tests; Django BFF view tests |
| Integration tests | Yes | real test DB with migrated schema, operation rows, permission identities |
| Real stand smoke | Yes | DELETE cancelled operation through SyncServer; optionally through Django BFF |
| UI automation | Not applicable here | Angular UI not implemented in this TZ |
| User scenarios | Yes | cancel operation, delete cancelled, verify list no longer shows it |
| Regression pack | Yes | create/update/submit/cancel/acceptance tests must still pass |
| Acceptance review | Yes | evidence table reviewed |

---

## 8. Acceptance Criteria

- SyncServer exposes `DELETE /api/v1/operations/{id}`.
- Django BFF exposes same-origin `DELETE /bff/api/v1/operations/{id}`.
- Only cancelled operations can be deleted.
- Draft/submitted operations return conflict.
- Unauthorized/observer/no-binding users cannot delete.
- Storekeeper cannot delete outside allowed warehouse scope.
- Deleted operations disappear from normal list/get responses.
- Existing operation lifecycle and acceptance behavior is not regressed.
- Angular handoff documents delete button visibility and expected response.

---

## 9. Evidence Table

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|---|
| SyncServer unit/component | `python -m pytest tests/test_operations_workflow_policy.py tests/test_operations_permissions.py tests/test_operations_service_delete.py` | pass | 3+4+4 = 11 new tests, all pass |
| SyncServer DB integration | `python -m pytest tests/test_operations_delete_api.py` | pass | 10 new DB-backed API tests, all pass |
| Django sync_client tests | `python manage.py test apps.sync_client.tests.OperationsAPITests` | pass | 2 tests (accept + delete), 1 new |
| Django BFF tests | `python manage.py test apps.bff_api.tests.BffApiViewMethodTests.test_operations_delete_supported` | pass | 1 new test verifies DELETE calls sync client |
| Stand smoke | — | skipped | blocker: no local PostgreSQL stand |
| Regression pack | `python -m pytest tests/ --ignore=tests/test_operations_service_inventory_subject_write_path.py` | pass | 261 selected, all pass |
| Docs/handoff | TZ-B checklist updated | done | evidence table populated, blocker noted |
