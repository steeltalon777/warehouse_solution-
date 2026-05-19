# Plan: Pre-Angular Functional Gap Remediation

**Date:** 2026-05-19  
**Source audit:** `docs/AUDIT_FUNCTIONAL_SPEC_2026-05-19.md`  
**Canonical requirements:** `Functional and WorkLogik.md`  
**Purpose:** close the functional and infrastructure gaps that should not be deferred until the Angular operations/catalog work starts.

---

## 1. Decision

Do **not** block Angular on every audit finding.

Do close the backend/domain/security gaps now, in parallel with Angular preparation, because they define stable API contracts and data invariants that Angular must rely on.

Pre-Angular scope:

1. SyncServer bootstrap and emergency token recovery.
2. Operation deletion contract for cancelled operations.
3. Catalog freeze when permanent items are present in the lost/unaccepted register.
4. Small Django shell prerequisites that Angular will be rendered inside: configurable brand, SyncServer role in navbar, temporary item counter on dashboard.

Deferred until after Angular MVP or separate product decision:

- Mass SSR table standardization for screens that may move to Angular.
- Issued assets SSR screens because Functional spec marks the section as design stage.
- Angular-specific table behavior, operation list UX, and operation modal UX; these stay in `Warehouse_frontend/docs/TZ_FRONTEND_SCREENS_IMPLEMENTATION.md`.

---

## 2. Parallel Workstreams

| Stream | TZ | Project | Priority | Main gaps | Can run with |
|---|---|---|---|---|---|
| A | `SyncServer/docs/TZ-A_BOOTSTRAP_ROOT_TOKEN_RECOVERY.md` | `SyncServer` | Critical | Audit #1, #2 | B, C, D |
| B | `docs/TZ-B_OPERATIONS_DELETE_CONTRACT.md` | `SyncServer` + `Warehouse_web` BFF | High | Audit #3 | A, C, D |
| C | `SyncServer/docs/TZ-C_LOST_ASSETS_CATALOG_FREEZE.md` | `SyncServer` | High | Audit #4 | A, B, D if not editing catalog admin simultaneously |
| D | `Warehouse_web/docs/TZ-D_DJANGO_SHELL_PRE_ANGULAR_UX.md` | `Warehouse_web` | Medium | Audit #5, #11, #12 | A, B, C |

### File conflict matrix

| TZ | Primary files likely touched | Conflict risk |
|---|---|---|
| A | `SyncServer/scripts/bootstrap_root.py`, new token recovery script, admin user/device services/tests/docs | Low with B/C |
| B | `SyncServer/app/api/routes_operations.py`, operation service/repo/model/migration/tests; `Warehouse_web/apps/sync_client/operations_api.py`; `Warehouse_web/apps/bff_api/operations_views.py`; `Warehouse_web/apps/bff_api/urls.py` | Medium with any operation-service or BFF operations work only |
| C | `SyncServer/app/services/catalog_admin_service.py`, catalog/asset repos/tests | Medium with catalog-admin work only |
| D | `Warehouse_web/templates/includes/*`, `apps/client/views.py`, context processor/settings/tests | Low with backend SyncServer streams |

---

## 3. Gate Definitions

### Gate 1 — Backend pre-Angular contract ready

Complete when TZ-A, TZ-B, and TZ-C are implemented and verified:

- SyncServer can be bootstrapped from an empty safe database through documented commands.
- Root and Django device tokens can be recovered/rotated through explicit local ops tooling.
- `DELETE /api/v1/operations/{id}` exists and deletes only already-cancelled operations.
- Catalog item mutation is blocked while its inventory subject has positive `lost_asset_balances`.

### Gate 2 — Django shell ready for Angular container screenshots

Complete when TZ-D is implemented and verified:

- Brand is configurable from Django settings/static variables, not hardcoded in template.
- Navbar shows SyncServer role/context without exposing tokens.
- Dashboard shows temporary item count/reminder.

### Gate 3 — Angular may proceed without waiting for SSR polish

Angular may proceed after Gate 1 starts, but Angular acceptance must use the final Gate 1 contracts.

Gate 2 is recommended before Playwright screenshot baselines for Angular because Angular is rendered inside the Django shell.

---

## 4. Dependency Notes

### TZ-A is infrastructure/security critical

The restored `SyncServer/scripts/bootstrap_root.py` exists, but the audit still stands until it is made current and tested.

Observed current state:

- It uses `Base.metadata.create_all` directly.
- It creates or updates root user and Django device.
- It creates or repairs the uncategorized category.
- It prints root and Django device tokens.
- It does not provide explicit token rotation/recovery mode.
- It does not document safe database lifecycle or Alembic migration behavior.

### TZ-B defines Angular operation delete semantics

Angular operations UI must know whether cancelled operations can be deleted and what response/status to expect.

Decision for implementation agents:

- Prefer soft delete (`deleted_at`, `deleted_by_user_id`) over hard delete to preserve audit trail.
- Normal operation lists must exclude deleted operations by default.
- If implementation chooses hard delete, an ADR or explicit TZ note must justify why audit trail is safe.

### TZ-C protects data integrity independently of UI

Freeze logic belongs in SyncServer, not in Angular or Django templates.

Angular may show disabled controls later, but SyncServer must be the authority.

### TZ-D is not a replacement for Angular UX work

TZ-D only prepares the Django shell that Angular is rendered inside. It does not standardize every SSR table and does not implement Angular screens.

---

## 5. Deferred Audit Gaps

| Audit gap | Decision | Reason |
|---|---|---|
| #6 sorting in all tables | Defer or split after Angular MVP | Some tables may be replaced by Angular; avoid duplicate work |
| #7 sticky headers in all tables | Defer or apply only where screen remains SSR | Angular TZ already mandates sticky headers for Angular tables |
| #8 pagination 10/20/50 in all tables | Defer except new Angular screens | Avoid SSR churn before route ownership decision |
| #9 stock quantity in operation item search | Handle in Angular operations API/UX work unless SSR operation form remains primary | Angular modal must implement stock hints through BFF/balances contract |
| #10 operation date display | Handle in Angular operations screen and optionally later SSR polish | Not a backend blocker |
| #13 FHD breakpoint | Handle in shared Angular/Django visual baseline | Already in frontend TZ visual work |
| #14-16 issued assets SSR | Defer | Functional spec marks section as design stage |

---

## 6. Execution Rules For Agents

- Re-read `Functional and WorkLogik.md` before implementation.
- Follow the project-local `AGENTS.md` file.
- Do not expose tokens in logs, tests, screenshots, or docs.
- Commit only if project checks pass and current branch is `dev`.
- Git push is forbidden.
- Executor agents may check TZ boxes only after implementation and verification evidence is recorded.
- QA verifier checks final acceptance only after reviewing evidence.

---

## 7. Evidence Tracking

Each TZ has its own evidence table. The master plan is considered complete when the following rows are filled by executors/QA:

| Stream | Required evidence | Status |
|---|---|---|
| A | Script command logs, token rotation tests, clean DB bootstrap smoke | Pending |
| B | API route tests, migration proof if soft delete, stand DELETE smoke | Pending |
| C | Catalog-admin conflict tests, lost-assets integration smoke | Pending |
| D | Django tests, screenshot or HTML proof for navbar/dashboard, no token exposure check | Pending |

---

## 8. Recommended Launch Order

1. Start TZ-A immediately.
2. Start TZ-B and TZ-C in parallel with separate SyncServer agents.
3. Start TZ-D with a Django agent once frontend shell screenshots or Angular container work are near.
4. Start Angular implementation only against documented contracts from TZ-B/TZ-C; if TZ-B/TZ-C are not merged yet, mock only the final contract and mark the blocker.
