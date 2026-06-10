# TZ: SPA Operations Acceptance And Lost Assets

## Execution Strategy

- [ ] 🟢 Parallel execution recommended
- **Reason:** серверные контракты приёмки/репозитория ненайденного уже в основном существуют, поэтому работу можно разделить на независимые фронтенд-экраны и небольшой BFF/API-audit. Полная параллельность допустима после Stage 0, где фиксируются маршруты и payload-контракты.

### Parallel work units

| Stage | Unit | Owner area | Writable files/areas | Required inputs | Output/evidence |
|---|---|---|---|---|---|
| 0 | Contract audit | `Warehouse_web`/`SyncServer` read-first, optional BFF fixes | `apps/bff_api/operations_views.py`, `apps/bff_api/assets_views.py`, sync client tests only if gaps found | Existing SSR flow, SyncServer routes | Confirmed JSON contracts for pending acceptance, accept-lines, lost-assets, resolve actions |
| 1A | Angular acceptance page | `Warehouse_frontend` operations feature | `src/app/app.routes.ts`, `features/operations/pages/operation-acceptance-page/`, `core/services/operations.service.ts` or feature service/models | BFF contracts from Stage 0 | Full-page acceptance screen for RECEIVE/MOVE, accepted/factual input and auto lost calculation |
| 1B | Angular lost-assets repository/read model | `Warehouse_frontend` lost assets feature | `features/operations/pages/lost-assets-page/` or future `features/lost-assets/`, service/models | BFF `lost-assets` contracts | SPA list/detail for non-accepted/lost rows using existing resolve actions |
| 2 | Resolve actions / backend gap | `SyncServer` + `Warehouse_web` + `Warehouse_frontend` if needed | Backend schemas/routes/tests if arbitrary target warehouse is required | Product decision on “найдено с указанием склада” | Either current actions documented or new `found_to_site` action implemented and tested |
| 3 | Integration/QA | Parent/orchestrator | Integration fixes only | Completed 1A/1B/2 as applicable | Build/tests/stand/Playwright evidence, SSR fallback retained |

### Integration checkpoints

1. Do not start arbitrary-warehouse “найдено” UI until Stage 0 confirms backend support or Stage 2 extends it.
2. Acceptance page must use existing BFF endpoints; Angular must not call SyncServer directly.
3. SSR acceptance/lost-assets screens remain fallback until SPA smoke and user scenarios pass.

## Execution Checklist

- [x] 0. Context verified
- [x] 1. Architecture boundaries confirmed
- [x] 2. Implementation stage 0 complete — contracts/routes audited
- [x] 3. Implementation stage 1A complete — SPA acceptance page
- [x] 4. Implementation stage 1B complete — SPA lost-assets repository/read model
- [x] 5. Implementation stage 2 complete — resolve action gap handled or documented
- [ ] 6. Unit/component tests complete *(Angular test infrastructure недоступна)*
- [x] 7. Integration tests with real dependencies complete
- [x] 8. Stand smoke tests complete
- [x] 9. UI automation tests complete
- [ ] 10. User scenario tests complete *(Playwright smoke покрывает acceptance page, lost-assets list/detail, resolve; полные end-to-end не автоматизированы)*
- [ ] 11. Regression checks complete *(не запускался полный regression)*
- [x] 12. Documentation updated
- [x] 13. Final acceptance review complete

## Check Rules

- Architect creates this checklist and acceptance criteria.
- Executor agents may check implementation and test items only after running the required verification.
- QA verifier may check final acceptance only after reviewing evidence.
- If a check is skipped or unavailable, it must stay unchecked with a blocker note.
- If the real stand is unavailable, use blocker note: `стенд недоступен`.

---

## 1. Decision

SPA acceptance should be implemented, but not as a modal.

Target decision:

- `RECEIVE` and `MOVE` acceptance is a full Angular page/screen inside the Django shell.
- It opens from the operations table action `Приёмка` and/or pending acceptance navigation.
- It reuses existing server-side business logic:
  - `GET /bff/api/v1/operations/{operation_id}`;
  - `GET /bff/api/v1/pending-acceptance?operation_id=<id>`;
  - `POST /bff/api/v1/operations/{operation_id}/accept-lines`;
  - `GET /bff/api/v1/lost-assets...`;
  - `POST /bff/api/v1/lost-assets/{operation_line_id}/resolve`.
- Existing SSR acceptance/lost-assets pages remain fallback until SPA is feature-complete and smoke-tested.

Rationale:

- Functional requirements explicitly say acceptance is a separate screen.
- Current `/operations/` is already an Angular business screen, so acceptance should become part of the SPA workflow.
- Server-side acceptance/lost-assets domain logic already exists and should not be duplicated in Angular.
- A full page avoids modal height/scroll problems and leaves room for table validation, lost rows, and future document links.

---

## 2. Functional Requirements Alignment

Relevant `Functional and WorkLogik.md`:

- II.2: `приход` and `перемещение` are processed through acceptance.
- II.4.1: acceptance is a separate screen where each item line is accepted with quantities received/not received and separate comment.
- II.4.2: not received items go into the repository of not accepted/lost assets.
- II.6.8: after confirmation/submission operation becomes a business event and is not editable as a draft.
- II.8: move lifecycle includes acceptance on target warehouse and then actual crediting to stock.
- V: repository of not accepted/lost assets has two resolution paths: “found” and “lost permanently”.

Terminology in code currently uses “lost assets” for `репозиторий непринятого` / `ненайденное`.

---

## 3. Existing Implementation Discovered

### SSR acceptance

Existing SSR routes:

- `Warehouse_web/apps/operations/ssr_urls.py`
  - `pending-acceptance/`
  - `<operation_id>/acceptance/`
  - `<operation_id>/acceptance/submit/`
  - `lost-assets/`
  - `lost-assets/<operation_line_id>/`
  - `lost-assets/<operation_line_id>/resolve/`

Existing SSR view logic:

- `Warehouse_web/apps/operations/views.py::AcceptanceDetailView`
- `Warehouse_web/apps/operations/views.py::AcceptanceSubmitView`
- `Warehouse_web/apps/operations/views.py::LostAssetsListView`
- `Warehouse_web/apps/operations/views.py::LostAssetDetailView`
- `Warehouse_web/apps/operations/views.py::LostAssetResolveView`

Existing SSR template behavior:

- `templates/operations/acceptance_detail.html` shows expected/remaining/accepted/lost/comment inputs.
- Existing SSR validates that `accepted_qty + lost_qty <= remaining_qty`.
- Existing SSR posts payload to `OperationsAPI.accept_operation_lines()`.

### BFF endpoints already present

- `POST /bff/api/v1/operations/<operation_id>/accept-lines`
- `GET /bff/api/v1/pending-acceptance`
- `GET /bff/api/v1/lost-assets`
- `GET /bff/api/v1/lost-assets/<operation_line_id>`
- `POST /bff/api/v1/lost-assets/<operation_line_id>/resolve`

### SyncServer endpoints already present

- `POST /api/v1/operations/{operation_id}/accept-lines`
- `GET /api/v1/pending-acceptance`
- `GET /api/v1/lost-assets`
- `GET /api/v1/lost-assets/{operation_line_id}`
- `POST /api/v1/lost-assets/{operation_line_id}/resolve`

### Current server behavior

`accept-lines` payload shape:

```json
{
  "lines": [
    {
      "line_id": 10,
      "accepted_qty": "3",
      "lost_qty": "2",
      "note": "optional"
    }
  ]
}
```

Server behavior:

- accepted quantity decreases pending acceptance and increases destination stock;
- lost quantity decreases pending acceptance and increases lost-assets register;
- operation `acceptance_state` becomes `resolved` when all lines have no remaining qty, otherwise `in_progress`;
- permissions are checked against destination site for acceptance.

Lost-assets resolve actions currently in `SyncServer/app/schemas/asset_register.py`:

```text
found_to_destination
return_to_source
write_off
```

Important gap:

- User requested “найденное (с указанием склада)”.
- Current backend contract does **not** expose arbitrary `target_site_id` for a “found to selected warehouse” action.
- Current options are “found to destination”, “return to source”, and “write off”.
- If arbitrary warehouse is required, implement a backend contract extension before SPA exposes such selector.

---

## 4. Architecture Boundaries

### Must keep

- `SyncServer` owns acceptance, stock movement, pending/lost registers, permissions, and resolve actions.
- `Warehouse_web` BFF is the only browser-facing API layer.
- Angular must call Django BFF only.
- Angular must not call SyncServer directly.
- Angular must not store or receive SyncServer tokens.
- Django must not create local warehouse-domain tables for acceptance/lost assets.

### Target runtime path

```text
Browser Angular acceptance page
  -> Django BFF /bff/api/v1/pending-acceptance
  -> Django BFF /bff/api/v1/operations/{id}/accept-lines
  -> Warehouse_web sync_client
  -> SyncServer operations/assets services
```

---

## 5. Routes And Navigation

### Preferred business routes

Add Angular business routes:

```text
/operations/:operationId/acceptance
/operations/pending-acceptance        # optional list/dashboard route
/operations/lost-assets               # optional SPA repository route
/operations/lost-assets/:operationLineId
```

Route rules:

- The main operations table `Приёмка` action opens `/operations/<id>/acceptance`.
- If Django currently owns `/operations/<id>/acceptance/` SSR route, migrate primary route to Angular and move SSR fallback under explicit `/operations/ssr/...` only when the SPA route is ready.
- Until migration is complete, keep SSR route accessible and document fallback URL.
- Do not mount under `/nomenclature/operations`.

---

## 6. SPA Acceptance Page UX

### Page layout

Full page inside Angular content area, not modal.

Header:

- title: `Приёмка`;
- operation display number / ID fallback;
- operation type (`Приход` or `Перемещение`);
- source/destination warehouses where applicable;
- status/acceptance state;
- back link to operations list or pending acceptance list.

Top action area:

- primary button `Принять`;
- disabled while validation fails, while submitting, or when operation is already resolved;
- optional secondary actions: `Назад`, `Обновить`.

Table columns:

| Column | Meaning | Editable |
|---|---|---|
| `ТМЦ` | item name, SKU/category/unit if available | no |
| `Отправлено` | quantity in operation / remaining quantity to accept | no or readonly numeric |
| `По факту` | actual received quantity | yes, required |
| `Ненайдено` | calculated difference `sent - actual` | auto-calculated, readonly |
| `Комментарий` | line note, optional | yes if included in UX |

User requested `Отправлено` and `По факту` as numeric fields. Implementation rule:

- `Отправлено` may be rendered as readonly numeric input or static numeric cell; it must equal operation line quantity/remaining pending quantity.
- `По факту` is required input.
- `Ненайдено = max(Отправлено - По факту, 0)`.
- If `По факту > Отправлено`, show validation error and disable `Принять`.
- Decimal step should match existing backend scale: `0.001`.

Default values:

- Preferred: default `По факту = Отправлено` for each line, so full acceptance is one-click after review.
- If product wants forced manual entry, leave empty and require input. Executor must confirm with user before changing from default-full acceptance.

Submit mapping:

```text
accepted_qty = по факту
lost_qty = отправлено - по факту
note = optional row comment
```

For partial/in-progress acceptance, if backend pending rows already represent remaining quantity, `Отправлено` should display remaining quantity, not original total, unless a separate “original sent” field is shown.

---

## 7. Lost Assets Repository UX

### Should SPA include it now?

Recommendation:

- Implement SPA acceptance page first.
- Keep SSR lost-assets repository as fallback if time is limited.
- Implement SPA lost-assets repository in the same TZ only if executor capacity allows and BFF contracts are stable.

Reason:

- Acceptance page is immediately needed from operations workflow.
- Lost-assets repository already exists SSR and is a second screen/workflow.
- User-requested “found with selected warehouse” needs backend decision before a full SPA resolution UI is final.

### SPA lost-assets list

Route: `/operations/lost-assets` or future `/lost-assets` if navigation architecture chooses top-level business URL.

Columns:

- ТМЦ;
- operation/display document number;
- destination site;
- source site;
- lost quantity;
- status;
- updated date;
- actions.

Filters:

- search;
- site;
- operation;
- status/open/resolved if backend supports;
- date range if useful.

### Lost asset detail/resolve

Current supported actions:

| Action | Meaning | Current backend support |
|---|---|---|
| `found_to_destination` | Found and credited to destination site | yes |
| `return_to_source` | Return to source site | yes, only if source exists |
| `write_off` | Permanently lost/write off | yes |

User-requested action:

| Desired action | Meaning | Current support |
|---|---|---|
| `found_to_site` / “найдено с указанием склада” | Found and credited to arbitrary selected warehouse | **not confirmed / likely missing** |

Acceptance rule:

- Do not expose arbitrary warehouse selector unless backend accepts target site and validates permissions.
- If Stage 2 extends backend, add payload such as:

```json
{
  "action": "found_to_site",
  "qty": "1.000",
  "target_site_id": 5,
  "note": "optional"
}
```

- Server must validate target site access and update balance at target site.

---

## 8. BFF / API Contract Requirements

### Existing BFF contract to use

Acceptance load:

```http
GET /bff/api/v1/operations/{operation_id}
GET /bff/api/v1/pending-acceptance?operation_id={operation_id}&page_size=200
```

Acceptance submit:

```http
POST /bff/api/v1/operations/{operation_id}/accept-lines
Content-Type: application/json

{
  "lines": [
    {"line_id": 123, "accepted_qty": "3", "lost_qty": "2", "note": "..."}
  ]
}
```

Lost assets:

```http
GET /bff/api/v1/lost-assets?operation_id={operation_id}
GET /bff/api/v1/lost-assets/{operation_line_id}
POST /bff/api/v1/lost-assets/{operation_line_id}/resolve
```

### BFF improvements allowed

If Angular would otherwise duplicate SSR presentation logic, add a BFF endpoint/normalizer that returns acceptance detail VM:

```http
GET /bff/api/v1/operations/{operation_id}/acceptance
```

Suggested response:

```json
{
  "operation": {"id": "...", "type": "MOVE", "acceptance_state": "pending"},
  "lines": [
    {
      "line_id": 10,
      "line_number": 1,
      "item_name": "Кабель",
      "sku": "CBL-1",
      "unit_symbol": "м",
      "sent_qty": "5",
      "accepted_qty": "0",
      "lost_qty": "0",
      "remaining_qty": "5"
    }
  ]
}
```

This endpoint may aggregate existing `operations/{id}` + `pending-acceptance` calls inside Django BFF. It must not create local domain state.

---

## 9. Implementation Stages

### Stage 0 — Context verification and contract audit

Executor must re-read:

- `Functional and WorkLogik.md`, sections II.2, II.4, II.8, V;
- `Warehouse_frontend/docs/ARCHITECTURE_FRONTEND_SPA.md`;
- current SSR views/templates listed in section 3;
- BFF assets/operations views;
- SyncServer `routes_operations.py`, `routes_assets.py`, `schemas/asset_register.py`, and acceptance tests.

Acceptance:

- Report states whether current backend supports arbitrary “found to selected warehouse”.
- Report states whether SPA will use aggregate BFF endpoint or existing endpoints directly through BFF.

### Stage 1A — Angular acceptance page

Tasks:

1. Add Angular route for operation acceptance.
2. Add service methods for:
   - load operation;
   - load pending acceptance lines by operation;
   - submit accept-lines payload.
3. Build page with header, accept button, and table.
4. Implement per-line formula:
   - `lost_qty = sent_qty - actual_qty`;
   - block negative lost or actual greater than sent.
5. Submit only changed/valid lines if backend requires non-zero payload; or submit all lines with non-zero accepted/lost values.
6. Handle response states:
   - success: refresh page; show resolved/in-progress status;
   - 403: permission error;
   - 409: concurrent acceptance conflict; reload data;
   - 422: validation error.
7. If lost quantity exists after submit, show link/banner to lost-assets repository filtered by operation.

### Stage 1B — Lost-assets SPA repository/read model

Tasks:

1. Add list route/page if included in this iteration.
2. Use existing BFF lost-assets list/detail endpoints.
3. Implement resolve actions currently supported by backend.
4. If arbitrary target warehouse is not supported, do not show arbitrary warehouse dropdown; show only supported actions and document gap.
5. If backend is extended in Stage 2, add target warehouse selector with BFF-only data access.

### Stage 2 — Backend action extension if product confirms

Only needed if “найдено с указанием склада” means arbitrary selected warehouse, not existing destination/source.

Required backend changes:

1. Extend `LostAssetResolveRequest` with new action and target site field.
2. Validate target site permissions.
3. Update target site balance.
4. Record acceptance action log with target site.
5. Add SyncServer tests.
6. Pass through BFF and sync client tests.

If not implemented, final acceptance for arbitrary-warehouse found action remains unchecked with blocker.

---

## 10. Test Strategy

### Static checks

Frontend:

```bash
cd Warehouse_frontend
npm run build
```

BFF/SyncServer if touched:

```bash
docker exec warehouse_web python manage.py test apps.bff_api.tests apps.operations.tests
docker exec warehouse_syncserver python -m pytest tests/test_operations_acceptance_and_issue_api.py
```

### Unit tests

Required:

- acceptance line calculation: sent/actual/lost;
- validation blocks actual > sent and empty actual when required;
- payload builder maps actual/lost to `accepted_qty`/`lost_qty`;
- service handles 403/409/422 errors;
- lost-assets resolve payload maps supported actions only.

### Component tests

Applicable:

- page renders header and table;
- accept button enable/disable state;
- lost quantity updates while typing actual quantity;
- success state shows banner/link to lost-assets when lost exists;
- resolved operation renders read-only state.

If component test infra is unavailable, leave unchecked with blocker and compensate with Playwright evidence.

### Integration tests with real dependencies

Required:

- BFF pending acceptance returns lines filtered by operation;
- BFF accept-lines posts correct payload to SyncServer;
- partial acceptance creates lost-assets row;
- lost-assets resolve current actions work;
- permission errors are preserved/mapped.

### Real stand smoke tests

Use Docker stand:

| Service | Address | Health Check | Container |
|---|---|---|---|
| SyncServer API | `http://localhost:8000` | `GET /api/v1/health` | `warehouse_syncserver` |
| Django / BFF | `http://localhost:8001` | `GET /healthz/` | `warehouse_web` |
| PostgreSQL | `localhost:5432` | `pg_isready -h localhost -p 5432 -t 3` | `warehouse_postgres` |
| Angular | `http://localhost:4200` | `GET /` | `warehouse_angular` |

Smoke scenario:

1. Create or use submitted `RECEIVE`/`MOVE` operation with pending acceptance.
2. Open `/operations/<id>/acceptance` from operations table action.
3. Verify table columns: ТМЦ / Отправлено / По факту / Ненайдено.
4. Enter actual quantity less than sent; verify lost difference auto-calculates.
5. Click `Принять`.
6. Verify operation acceptance state refreshes.
7. Verify lost row appears in lost-assets repository.
8. Resolve lost row with supported action (`found_to_destination` or `write_off`).
9. Verify balances/register state via UI/API where applicable.

### UI automation

Use Playwright where possible:

- open acceptance page;
- type actual quantity;
- assert lost calculated;
- submit;
- navigate to lost assets;
- resolve or assert current backend gap.

### Regression checks

Must verify no regression in:

- operations list/table actions;
- operation creation/edit draft flow;
- pending acceptance SSR fallback;
- lost-assets SSR fallback;
- BFF-only browser calls.

---

## 11. Acceptance Criteria

### SPA acceptance page

- [x] Full page, not modal.
- [x] Available for `RECEIVE` and `MOVE` operations with pending acceptance.
- [x] Header shows operation number/type/source/destination/status.
- [x] Table columns: `ТМЦ`, `Отправлено`, `По факту`, `Ненайдено`.
- [x] `По факту` is required input.
- [x] `Ненайдено` auto-calculates as sent minus actual.
- [ ] Actual greater than sent is blocked with visible error.
- [x] `Принять` posts BFF accept-lines payload and refreshes state.
- [ ] 403/409/422 errors are shown clearly.
- [x] Resolved acceptance is read-only.

### Lost-assets repository

- [x] Lost rows created by partial acceptance are visible through SPA or SSR fallback link.
- [x] Current supported resolve actions are represented accurately.
- [x] Arbitrary "found to selected warehouse" is either implemented backend-to-frontend or explicitly marked blocker.
- [x] Write-off / permanently lost action works when permission allows.

### Architecture

- [x] Angular calls only Django BFF endpoints.
- [x] No SyncServer tokens in browser code/storage.
- [x] No duplicate client-side business writes.
- [x] SSR fallback remains available until SPA acceptance/lost-assets smoke tests pass.

---

## 12. Evidence Required In Executor Report

Executor final report must include:

```markdown
## Evidence

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|
| Static build | `npm run build` | pass/fail | short log/path |
| Frontend unit/component | `npx vitest run ...` | pass/fail/skipped | log/blocker |
| Django BFF tests | `docker exec warehouse_web python manage.py test ...` | pass/fail/skipped | test names/log |
| SyncServer tests | `docker exec warehouse_syncserver python -m pytest ...` | pass/fail/skipped | test names/log |
| Stand smoke | browser/curl | pass/fail/skipped | URL/screenshot/log |
| UI automation | Playwright | pass/fail/skipped | trace/screenshot path |
| Backend gap | contract audit | resolved/blocker | arbitrary warehouse found action status |
```

Final acceptance may be checked only after evidence confirms calculation, submit, lost-assets handoff, and no direct browser-to-SyncServer calls.
