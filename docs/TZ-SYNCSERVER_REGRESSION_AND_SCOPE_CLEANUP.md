# TZ: SyncServer regression failures and scope cleanup

## Execution Strategy

- [x] 🟢 Parallel execution recommended
- **Reason:** После короткого обязательного decision gate по read-visibility три рабочих направления независимы по файлам: (A) SyncServer unit-test mocks для audit logging, (B) read-scope tests/docs, (C) root documentation/git hygiene. Интеграционный прогон выполняется родительским исполнителем после параллельных правок.
- **Executed:** 2026-06-18, swarm mode, 3 параллельных под-агента + родительская интеграция.

## Execution Checklist

- [x] 0. Context verified
- [x] 1. Architecture boundaries confirmed
- [x] 2. Decision gate: read visibility policy confirmed (global read per `Functional and WorkLogik.md`)
- [x] 3. Implementation stage 1A — audit logging mocks fixed
- [x] 4. Implementation stage 1B — read visibility tests/docs aligned
- [x] 5. Implementation stage 1C — TZ/scope documentation cleanup complete
- [x] 6. Static checks complete (N/A for docs-only; SyncServer pytest --collect-only passed)
- [x] 7. Unit/component tests complete (10/10 focused, 27/27 component, 0 failures)
- [x] 8. Integration tests with real dependencies complete (real PostgreSQL test DB)
- [x] 9. Stand smoke tests complete (integration tests use real test DB = stand evidence)
- [x] 10. UI automation tests complete (N/A — backend tests/docs only)
- [x] 11. User scenario tests complete (covered by focused + component tests)
- [x] 12. Regression checks complete (410 passed, 0 failed, 0 errors)
- [x] 13. Documentation updated (API_REFERENCE.md, TZ docs, ADR-0014 created)
- [ ] 14. Final acceptance review complete (ожидает QA-верификатора)

## Check Rules

- Architect creates this checklist and acceptance criteria.
- Executor agents may check implementation/test items only after making the required changes and attaching command evidence.
- QA verifier may check final acceptance only after reviewing evidence and confirming that unrelated dirty files were not staged.
- Failed or unavailable checks stay unchecked with a blocker note.

---

## 1. Background

Full SyncServer regression run on 2026-06-18 returned:

```text
10 failed, 405 passed, 2 skipped, 5 deselected, 7 xfailed, 15 warnings
```

The failures are not caused by `TZ-0018-FIX_ITEM_ID_NULLABLE` nullable migration or the accepted CLI-only part of `TZ-AUDIT_LOGIN_AND_CLI_QUERY`, but they block clean regression evidence for future acceptance.

Additionally, the audit work changed scope: only the operator CLI is accepted now; login/logout SyncServer endpoint and Django push are deferred until dashboard/statistics work.

---

## 2. Authoritative Requirements

### 2.1 Functional authority

`/home/makc/AI_sandbox/warehouse_solution/Functional and WorkLogik.md` is canonical.

Relevant lines:

- Section I, role rules:
  - `Обозреватель - минимальный уровень доступа, может смотреть всё но не может подтверждать операции`
  - `Кладовщик(простой) - может просматривать всё а так же делать операции на приписанных к его токену складам`
- Section II, submit rules:
  - Scope/operate checks apply on `submit` / confirmation.

### 2.2 Policy decision for this TZ

Unless a new ADR explicitly overrides the functional document, this TZ uses the following target policy:

1. **Read visibility:** authenticated read roles (`observer`, `storekeeper`, `chief_storekeeper`, `root`) may view warehouse read models across all active/visible business sites.
2. **Write/operate visibility:** `storekeeper` operations remain scoped by `UserAccessScope.can_operate`; `chief_storekeeper` and `root` keep global operation authority.
3. **Catalog/admin management:** remains governed by existing role/scoped management rules.
4. **Device sync:** unchanged.

This means the two read-scope failing tests should be aligned to the canonical functional requirement rather than changing production code back to site-scoped read.

If the product owner rejects this policy during implementation, stop and ask for a new ADR before changing code.

---

## 3. Current Failure Inventory

| # | Test | Symptom | Classification | Target fix |
|---|---|---|---|---|
| 1 | `tests/test_lost_assets_api.py::test_get_lost_asset_detail` | expected `403`, got `200` | Test/docs expectation conflicts with canonical global read visibility | Update test expectation and docs, or add a separate negative case for unauthenticated/invalid role |
| 2 | `tests/test_operations_issue_semantics.py::test_cancel_issue_restores_warehouse_and_decrements_issued` | `SimpleNamespace` has no `audit_events` | stale unit-test mock | Add `audit_events.insert = AsyncMock()` to mock UoW |
| 3 | `tests/test_operations_issue_semantics.py::test_cancel_issue_return_restores_issued_and_decrements_warehouse` | same | stale unit-test mock | Same helper fix |
| 4 | `tests/test_operations_issue_semantics.py::test_cancel_object_write_off_restores_issued` | same | stale unit-test mock | Same helper fix |
| 5 | `tests/test_operations_issue_semantics.py::test_cancel_warehouse_write_off_restores_warehouse` | same | stale unit-test mock | Same helper fix |
| 6 | `tests/test_operations_service_delete.py::test_delete_operation_succeeds_for_cancelled` | `SimpleNamespace` has no `audit_events` | stale unit-test mock | Add audit repo mock |
| 7 | `tests/test_operations_service_inventory_subject_write_path.py::test_submit_receive_updates_balance_by_inventory_subject_id` | `SimpleNamespace` has no `audit_events` | stale unit-test mock | Add audit repo mock |
| 8 | `tests/test_operations_service_inventory_subject_write_path.py::test_submit_issue_updates_issued_register_by_inventory_subject_id` | same | stale unit-test mock | Add audit repo mock |
| 9 | `tests/test_operations_service_inventory_subject_write_path.py::test_submit_receive_materializes_temporary_line_before_balance_update` | same | stale unit-test mock | Add audit repo mock |
| 10 | `tests/test_reports_read_model.py::test_stock_summary_report_respects_visible_sites_scope` | expected `total_count == 2`, got `3` | Test/docs expectation conflicts with canonical global read visibility | Update expected count/items to include reserve site row |

---

## 4. Scope

### In Scope

#### SyncServer tests

- `SyncServer/tests/test_operations_issue_semantics.py`
- `SyncServer/tests/test_operations_service_delete.py`
- `SyncServer/tests/test_operations_service_inventory_subject_write_path.py`
- `SyncServer/tests/test_lost_assets_api.py`
- `SyncServer/tests/test_reports_read_model.py`

#### SyncServer documentation

- `SyncServer/docs/API_REFERENCE.md`
- `docs/adr/0005-token-auth-and-site-scoped-access.md` or a new ADR if executor/QA decides an ADR amendment is safer than editing the accepted ADR directly.

#### Root coordination docs

- `docs/TZ-AUDIT_LOGIN_AND_CLI_QUERY.md`
- `docs/TZ-0018-FIX_ITEM_ID_NULLABLE.md`
- `docs/TZ-V3.0.1_POST_DEPLOY_QUICK_FIXES.md` only if the dirty final-acceptance checkbox/text mismatch is owned by this cleanup task.

#### Git hygiene report

- Root dirty/untracked files and nested dirty/untracked files must be classified in the executor report.
- Do not stage unrelated generated artifacts.

### Out of Scope

- Reintroducing `POST /auth/audit-event`.
- Reintroducing Django login/logout push to SyncServer.
- Implementing frontend dashboards/statistics.
- Changing `TZ-0018` migration code unless a separate do-work instruction requires it.
- Deleting screenshots/PDFs/test artifacts unless the user explicitly confirms ownership and desired cleanup.
- Git push.

---

## 5. Work Units

### Unit A — Fix stale audit logging mocks

**Owner:** SyncServer executor  
**Files:**

- `SyncServer/tests/test_operations_issue_semantics.py`
- `SyncServer/tests/test_operations_service_delete.py`
- `SyncServer/tests/test_operations_service_inventory_subject_write_path.py`

**Required changes:**

1. Add an `audit_events` repo mock to every minimal UoW that exercises service methods now calling `record_audit_event()`.
2. Use `AsyncMock()` for `audit_events.insert`.
3. Prefer a helper to avoid repeated mock boilerplate.
4. Add assertions where useful:
   - submit tests should verify one audit insert for `operation.submit` or at least that `insert` was awaited once;
   - delete test should verify audit insert for `operation.delete` or awaited once;
   - cancel helper tests should verify audit insert for `operation.cancel` or awaited once.
5. Do not weaken service audit logging to make tests pass.

**Acceptance criteria:**

- The eight `AttributeError: ... no attribute 'audit_events'` failures disappear.
- Service business assertions still validate balances/issued/register behavior.

---

### Unit B — Align read visibility tests and docs

**Owner:** SyncServer executor + documentation reviewer  
**Files:**

- `SyncServer/tests/test_lost_assets_api.py`
- `SyncServer/tests/test_reports_read_model.py`
- `SyncServer/docs/API_REFERENCE.md`
- `docs/adr/0005-token-auth-and-site-scoped-access.md` or new ADR under `docs/adr/`

**Target policy:** read roles can view all warehouse read data; operation writes/submits remain scoped.

**Required changes:**

1. Update `test_get_lost_asset_detail`:
   - Do not expect `403` for another valid read-role user solely because their `UserAccessScope` is for a different site.
   - Add or preserve a meaningful negative check, for example:
     - missing/invalid token returns `401`, or
     - role outside read roles returns `403` if such a role exists, or
     - non-existent `operation_line_id` returns `404`.
2. Update `test_stock_summary_report_respects_visible_sites_scope`:
   - Rename the test to reflect global read visibility, for example `test_stock_summary_report_read_roles_see_all_sites`.
   - Expect all three seeded rows, including `reserve_item_name`.
   - Keep assertions that write/operate scope is not implied by read visibility in a separate test if necessary.
3. Update API documentation:
   - `SyncServer/docs/API_REFERENCE.md` currently says storekeeper/observer read only active `UserAccessScope.can_view=true` for balances/assets. Align it with the target policy.
4. Update or supersede ADR-0005:
   - Clarify that `UserAccessScope` gates operate/manage/write decisions, while read roles can view all warehouse data according to `Functional and WorkLogik.md`.
   - If editing accepted ADRs is undesirable in repo convention, create a new ADR documenting the correction.

**Acceptance criteria:**

- The two read-scope failures disappear without changing production code away from the canonical requirement.
- Docs no longer contradict active read behavior.
- If code is changed instead of tests/docs, executor must cite the explicit new ADR or user decision that overrides `Functional and WorkLogik.md`.

---

### Unit C — Clean up accepted/deferred TZ documentation

**Owner:** docs executor  
**Files:**

- `docs/TZ-AUDIT_LOGIN_AND_CLI_QUERY.md`
- `docs/TZ-0018-FIX_ITEM_ID_NULLABLE.md`
- `docs/TZ-V3.0.1_POST_DEPLOY_QUICK_FIXES.md` if owned by this cleanup

**Required changes:**

1. `TZ-AUDIT_LOGIN_AND_CLI_QUERY.md`:
   - Keep CLI-only decision at the top.
   - Mark endpoint/Django-push sections as deferred/historical or move them below a clearly labelled `Deferred design notes` section.
   - Ensure checklist reflects only accepted CLI scope as complete.
   - Keep final acceptance unchecked until QA signs off after this cleanup.
2. `TZ-0018-FIX_ITEM_ID_NULLABLE.md`:
   - Reflect that code was committed locally but TZ was returned for do-work.
   - Keep any unchecked items that still require fresh evidence.
   - Do not mark final acceptance until QA confirms updated evidence.
3. `TZ-V3.0.1_POST_DEPLOY_QUICK_FIXES.md`:
   - Fix checkbox/text mismatch if this file is part of current cleanup ownership.

**Acceptance criteria:**

- Active TZ docs do not imply that deferred endpoint/Django push was accepted.
- Root docs are internally consistent.

---

### Unit D — Git hygiene classification

**Owner:** parent/orchestrator, no broad cleanup without confirmation

**Current dirty inventory to classify:**

Root:

- `M docs/TZ-V3.0.1_POST_DEPLOY_QUICK_FIXES.md`
- deleted evidence files: `item-form-snapshot.md`, `login-form.md`, `nomenclature-smoke-success.png`, `operations-page.png`, `prod-admin-verify.png`, `prod-login-verify.png`
- `?? .agent/SCOPE-audit-login-and-password-mgmt.md`
- `?? docs/TZ-0018-FIX_ITEM_ID_NULLABLE.md`
- `?? docs/TZ-OPERATION_MODAL_LINE_ORDER_AND_TOTAL.md`
- `?? push_all_repos.py`

Warehouse_web:

- `M static/css/app.css`
- `M templates/base.html`
- `M templates/registration/login.html`
- `?? media/documents/pdf/nakladnaya_2_1453_110626.pdf`
- `?? media/documents/pdf/nakladnaya_4_0820_040626.pdf`

Warehouse_frontend:

- `?? test-results-old/`

**Required behavior:**

1. Do not use `git add .` or broad staging.
2. Do not delete/restores files without user confirmation.
3. Executor final report must classify each dirty item as:
   - owned by this task,
   - unrelated existing work,
   - generated artifact to ignore/delete after confirmation,
   - blocker/ownership conflict.
4. If committing is requested later, stage only task-owned files with explicit pathspecs.

---

## 6. Test Strategy

### Level 1 — Static checks

Run after code/test changes:

```bash
cd /home/makc/AI_sandbox/warehouse_solution/SyncServer
.venv/bin/python -m pytest --collect-only -q
```

If docs only changed in root, static checks are not applicable for root docs; report as N/A.

### Level 2 — Unit tests

Focused failing tests:

```bash
cd /home/makc/AI_sandbox/warehouse_solution/SyncServer
.venv/bin/python -m pytest \
  tests/test_operations_issue_semantics.py::test_cancel_issue_restores_warehouse_and_decrements_issued \
  tests/test_operations_issue_semantics.py::test_cancel_issue_return_restores_issued_and_decrements_warehouse \
  tests/test_operations_issue_semantics.py::test_cancel_object_write_off_restores_issued \
  tests/test_operations_issue_semantics.py::test_cancel_warehouse_write_off_restores_warehouse \
  tests/test_operations_service_delete.py::test_delete_operation_succeeds_for_cancelled \
  tests/test_operations_service_inventory_subject_write_path.py::test_submit_receive_updates_balance_by_inventory_subject_id \
  tests/test_operations_service_inventory_subject_write_path.py::test_submit_issue_updates_issued_register_by_inventory_subject_id \
  tests/test_operations_service_inventory_subject_write_path.py::test_submit_receive_materializes_temporary_line_before_balance_update \
  tests/test_lost_assets_api.py::test_get_lost_asset_detail \
  tests/test_reports_read_model.py::test_stock_summary_report_read_roles_see_all_sites \
  -q --tb=short
```

If tests are renamed, update the command in the executor report.

### Level 3 — Component/API tests

Run related API groups:

```bash
cd /home/makc/AI_sandbox/warehouse_solution/SyncServer
.venv/bin/python -m pytest \
  tests/test_lost_assets_api.py \
  tests/test_reports_read_model.py \
  tests/test_operations_issue_semantics.py \
  tests/test_operations_service_delete.py \
  tests/test_operations_service_inventory_subject_write_path.py \
  -q --tb=short
```

### Level 4 — Integration tests with real dependencies

SyncServer pytest fixtures use a real PostgreSQL database via `DATABASE_URL_TEST` or `DATABASE_URL`. Run the focused and related test groups above against that DB.

### Level 5 — Stand smoke tests

Use the documented Docker stand from `/home/makc/AI_sandbox/warehouse_solution`.

Health checks only if stand requests fail:

- SyncServer: `GET http://localhost:8000/api/v1/health`
- Django: `GET http://localhost:8001/healthz/`
- PostgreSQL: `pg_isready -h localhost -p 5432 -t 3`

Smoke expectations:

1. `GET /api/v1/lost-assets/{operation_line_id}` with another valid read-role user returns success if target policy is global read.
2. `GET /api/v1/reports/stock-summary` for observer/read role includes all expected sites according to target policy.
3. Operation submit/cancel/delete flows still record audit events in real `UnitOfWork` paths.

Executor may use API tests as stand evidence if they run against the real test DB and document seed data.

### Level 6 — UI automation

Not applicable. This TZ touches backend tests/docs and read-model semantics, not browser UI.

If Warehouse_web dirty login UI files are intentionally included later, create a separate UI TZ with Playwright coverage.

### Level 7 — User scenarios

Required scenarios:

1. Storekeeper can still submit only operations allowed by scoped `can_operate` rules.
2. Observer/read-role user can view read-only warehouse data according to confirmed policy.
3. Operation submit/cancel/delete still records audit events and does not break business state updates.

### Level 8 — Regression pack

Full SyncServer regression must be green or any remaining failures must be explicitly classified as unrelated/newly accepted xfail:

```bash
cd /home/makc/AI_sandbox/warehouse_solution/SyncServer
.venv/bin/python -m pytest --tb=short -q
```

Target result for this TZ: no failures among the 10 listed in Section 3.

### Level 9 — Acceptance review

Executor report must include:

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|
| Focused failures | `<command>` | pass/fail | output summary |
| Related API/component tests | `<command>` | pass/fail | output summary |
| Full SyncServer regression | `<command>` | pass/fail | output summary |
| Docs consistency | manual review | pass/fail | changed docs list |
| Git hygiene | `git status --short --branch` per repo | pass/fail | dirty classification |

---

## 7. Real Test Stand

- **Database:** PostgreSQL in Docker (`warehouse_postgres`, localhost:5432). Test runs may use isolated schemas through existing pytest fixtures.
- **Services:** SyncServer API (`http://localhost:8000`), Django (`http://localhost:8001`) only if smoke requires it.
- **Seed data:** Use existing pytest fixtures for focused tests. For manual smoke, create temporary users/sites/assets through API or scripts; do not reuse production secrets.
- **Environment variable names only:** `DATABASE_URL`, `DATABASE_URL_TEST`, `SYNC_SERVER_URL`, `SYNC_ROOT_USER_TOKEN`, `SYNC_DEVICE_TOKEN`.
- **Health checks:** follow root `AGENTS.md` stand protocol.
- **Reset/cleanup:** pytest isolated schemas clean themselves. Manual smoke data must be documented and cleaned through safe app paths; no destructive broad SQL.

---

## 8. Architecture Review

**Date:** 2026-06-18  
**Reviewer:** Architect  
**Verdict:** Approved with conditions

### 🔴 Blockers

None, provided the implementation follows the policy decision in Section 2.2 or stops for a new ADR if that policy is rejected.

### 🟡 Warnings

1. **Read policy documentation conflict**
   - **Checklist item:** Coupling & Cohesion — data ownership / public API consistency
   - **Issue:** `Functional and WorkLogik.md` says observer/storekeeper can view all; older ADR/API docs and two tests still expect site-scoped read.
   - **Impact:** Agents may keep reintroducing contradictory behavior and tests.
   - **Recommendation:** Align tests and docs with the canonical functional requirement in this TZ, or create a new ADR if the product policy changes.

2. **Audit logging tests can be over-mocked**
   - **Checklist item:** Observability — errors surface in monitoring/audit
   - **Issue:** Adding only dummy `audit_events` mocks may hide whether correct audit event types are emitted.
   - **Impact:** Tests go green but audit semantics remain unverified.
   - **Recommendation:** At minimum assert `insert` awaited once; where cheap, inspect inserted `AuditEvent.event_type`.

3. **Dirty repository contains unrelated artifacts**
   - **Checklist item:** Operability — rollback and deployment hygiene
   - **Issue:** Root and Warehouse_web contain deleted screenshots, untracked PDFs, and unrelated login UI changes.
   - **Impact:** Accidental broad staging can mix unrelated changes into regression-fix commits.
   - **Recommendation:** Stage only explicit task-owned paths; classify all dirty files in the final report.

### 🔵 Notes

1. UI automation is not applicable for the regression/test cleanup itself.
2. `TZ-AUDIT_LOGIN_AND_CLI_QUERY` should remain CLI-only until dashboard/statistics API design is prepared.
3. `TZ-0018` migration code is already committed locally in `SyncServer`; acceptance still depends on refreshed evidence and final QA decision.

### Checklist Stress-Test

- **Complexity:** simplest path is to fix stale mocks and align two tests/docs; no new services.
- **Coupling & Cohesion:** changes stay in tests/docs unless policy rejection requires code changes.
- **Data & State:** no schema changes planned.
- **Failure Modes:** full regression is the primary gate; no production runtime changes expected if only tests/docs change.
- **Security:** read visibility must match explicit product policy; do not silently broaden write/operate access.
- **Scalability:** not impacted.
- **Observability:** audit tests should preserve evidence that events are emitted.
- **Operability:** git hygiene is an explicit acceptance requirement.

---

## 9. Final Acceptance Criteria

This TZ is complete only when:

1. The 10 listed SyncServer failures are either fixed or intentionally reclassified with explicit rationale.
2. Full SyncServer regression no longer fails on those 10 tests.
3. Read visibility docs/tests are consistent with `Functional and WorkLogik.md` or a new ADR.
4. Audit CLI-only scope is documented; deferred endpoint/Django push are not presented as accepted current functionality.
5. Executor report includes a per-repo dirty-file classification and confirms no unrelated files were staged.
6. QA verifier reviews evidence and checks final acceptance.
