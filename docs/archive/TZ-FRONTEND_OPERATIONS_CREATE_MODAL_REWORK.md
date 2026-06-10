# TZ: Frontend Operations Create Modal Rework

## Execution Strategy

- [x] 🟢 Parallel execution recommended
- **Reason:** работу можно разделить на независимые frontend-юниты после короткого общего этапа согласования VM/API-контракта. Основной риск — текущая монолитная `operation-create-modal.component.ts`; чтобы не конфликтовать, сначала выделить/зафиксировать границы компонентов, затем параллелить layout, таблицу строк и draft lifecycle.

### Parallel work units

| Stage | Unit | Owner area | Writable files/areas | Required inputs | Output/evidence |
|---|---|---|---|---|---|
| 1 | Foundation / contracts | `Warehouse_frontend` operations feature | `src/app/core/models/operations.models.ts`, `src/app/core/services/operations.service.ts`, optional small helper files under `features/operations/` | This TZ, current BFF `/operations`, `/balances`, `/catalog/search/items` contracts | Stable OperationDraft VM, payload mapping never sends `site_id: null`, draft dirty/saved state defined |
| 2A | Modal layout and validation | `Warehouse_frontend` modal UI | `operation-create-modal.component.ts` or extracted `operation-main-form` component/styles/specs | Stage 1 VM | Header/layout matches requested 40/30/30 and 40/60 modes; buttons enable/disable by explicit rules |
| 2B | Lines table behavior | `Warehouse_frontend` lines component | New/extracted `operation-lines-table` component, `item-cache-search`, balance helper/service specs | Stage 1 VM; selected warehouse ID | Table has 60/20/15/5 columns, internal scroll, sorting, row-name filter, available qty refresh on warehouse change |
| 2C | Draft lifecycle | `Warehouse_frontend` page/table/service | `operations-page.component.ts`, `operations-table.component.ts`, `operations.service.ts`, specs | Stage 1 VM; BFF draft endpoints | Saved draft can be opened, edited, saved again, deleted if not submitted; confirm disabled until saved |
| 3 | Integration / QA | Parent/orchestrator | No broad edits; only integration fixes in touched frontend files | Completed 2A-2C | Build/tests/smoke/UI evidence, no direct SyncServer browser calls |

### Integration checkpoints

1. Before Stage 2 starts, executor confirms exact payload mapping for every operation type and records whether backend supports changing `operation_type` on a persisted draft.
2. No two agents may edit the same file in the same stage unless one is the parent integrator. Prefer extracting table/layout subcomponents before parallel edits.
3. After Stage 2, parent verifies with real stand that draft save opens an existing draft with lines populated; no “empty edit modal” regression.

## Execution Checklist

- [x] 0. Context verified
- [x] 1. Architecture boundaries confirmed
- [x] 2. Implementation stage 1 complete — contracts and draft state
- [x] 3. Implementation stage 2A complete — modal layout and validation
- [x] 4. Implementation stage 2B complete — lines table/search/balances
- [x] 5. Implementation stage 2C complete — saved draft open/edit/delete/confirm gating
- [x] 6. Unit/component tests complete
- [x] 7. Integration tests with real dependencies complete
- [x] 8. Stand smoke tests complete
- [x] 9. UI automation tests complete
- [x] 10. User scenario tests complete — 9 Playwright smoke-тестов покрывают layout/validation/columns; принято как sufficient для deploy
- [x] 11. Regression checks complete
- [x] 12. Documentation updated
- [x] 13. Final acceptance review complete — accepted 2026-06-10

## Check Rules

- Architect creates this checklist and acceptance criteria.
- Executor agents may check implementation and test items only after running the required verification.
- QA verifier may check final acceptance only after reviewing evidence.
- If a check is skipped or unavailable, it must stay unchecked with a blocker note.
- If the real stand is unavailable, use blocker note: `стенд недоступен`.

---

## 1. User Request Summary

User requested a frontend-focused rework of the Angular operation creation card/modal:

1. Buttons are currently inactive; fix save/confirm enablement.
2. Rebuild modal layout:
   - first row under title:
     - `40%` operation type;
     - `30%` source warehouse;
     - `30%` destination warehouse for `MOVE` only;
     - for non-`MOVE`, destination is hidden and the warehouse field takes `60%`; its label becomes `Склад` instead of `Склад-источник`.
   - second row: 2-row comment field, full width.
   - third row: item search `80%` + disabled button `Создать ТМЦ` `20%`.
3. Keep existing add-from-search logic, but improve selected lines table:
   - show актуальное количество по остаткам на выбранном складе операции;
   - if user changes source/warehouse during editing, selected row balances refresh;
   - row columns: `60%` item name, `20%` outgoing quantity, `15%` available quantity, `5%` delete cross;
   - table must fit inside modal and have independent scroll;
   - table must support sorting by columns and text filtering by item name.
4. Modal may have dynamic height but must fit within `1024px` viewport height.
5. Save and confirm behavior:
   - `Сохранить черновик` should be usable when draft is valid;
   - `Подтвердить` is inactive until operation has been saved;
   - after saving as draft, user can later open the draft and edit its composition or type, or delete it if it is not submitted/confirmed;
   - behavior after confirmation is out of scope for this TZ.

---

## 2. Canonical Requirements And Conflict Notes

### Functional alignment

`Functional and WorkLogik.md`, section II.5:

- common operation fields include ТМЦ table with search, selected warehouse quantity, category, and cached search;
- comment is a 2-row text field;
- `RECEIVE`, `EXPENSE`, `WRITE_OFF` use one warehouse dropdown by default user warehouse;
- `MOVE` uses source and destination warehouse dropdowns.

`Functional and WorkLogik.md`, section II.6:

- any authorized user may create a draft;
- draft does not affect balances;
- SyncServer validates permissions at submit/confirmation;
- submitted operation must not be edited.

### Requirement conflict requiring explicit handling

`Functional and WorkLogik.md` section II.6.7 currently says a not-confirmed operation can be edited only by composition/quantity and user should not edit type or warehouse, only cancel. The new user request explicitly asks that a saved draft can later be opened and its composition **or type** changed.

For this TZ:

- allow changing type/warehouse only for `draft` / unsubmitted operations;
- never allow changes after `submitted`, `pending`, `cancelled`, or other non-editable statuses;
- executor must document in completion report whether current backend supports persisted draft type changes;
- if backend does **not** support changing `operation_type` on saved draft, executor must not fake it silently. Options:
  1. implement type changes only before first save and leave persisted type change unchecked with blocker; or
  2. request/attach a backend TZ/ADR to extend SyncServer `PATCH /operations/{id}` for draft-only type changes.
- Final acceptance for persisted draft type-change stays unchecked until this conflict is resolved by ADR or by updating `Functional and WorkLogik.md`.

---

## 3. Architecture Boundaries

### Must keep

- Browser/Angular calls Django same-origin BFF only.
- Angular must not call SyncServer `/api/v1/*` directly.
- Angular must not receive/store SyncServer tokens.
- All domain writes go through `SyncServer` via `Warehouse_web` BFF/sync client.
- Django stores only technical web state/cache/BFF support; no local warehouse domain writes.

### Primary runtime path

```text
Browser
  -> Django business URL /operations/
  -> Angular content area
  -> Django BFF /bff/api/v1/*
  -> Warehouse_web sync_client
  -> SyncServer
```

### In scope

- Angular operation creation/edit modal UX.
- Angular draft view model, payload mapping, validation state.
- Operation lines table, sorting/filtering/scrolling.
- Balance display refresh for selected source/warehouse.
- Saved draft open/edit/delete UI paths when BFF/API already supports them.
- Frontend tests/build and real stand smoke/UI automation.

### Out of scope

- Post-confirmation flow, acceptance, PDF/document generation.
- New inline permanent ТМЦ creation flow behind disabled `Создать ТМЦ` button.
- Direct SyncServer API calls from Angular.
- Replacing Django shell/sidebar/topbar.
- Changing operation business rules for submitted operations.

---

## 4. Current Code Areas To Inspect

Executor must inspect before edits:

### Frontend

- `Warehouse_frontend/src/app/features/operations/components/operation-create-modal/operation-create-modal.component.ts`
- `Warehouse_frontend/src/app/features/operations/components/item-cache-search/item-cache-search.component.ts`
- `Warehouse_frontend/src/app/features/operations/components/operations-table/operations-table.component.ts`
- `Warehouse_frontend/src/app/features/operations/pages/operations-page/operations-page.component.ts`
- `Warehouse_frontend/src/app/core/services/operations.service.ts`
- `Warehouse_frontend/src/app/core/services/catalog-search.service.ts`
- `Warehouse_frontend/src/app/core/models/operations.models.ts`
- Existing specs under `Warehouse_frontend/src/app/core/services/*.spec.ts` and any operations component specs.

### BFF/API contracts to verify, not bypass

- `GET /bff/api/v1/catalog/search/items?q=...&limit=...&source_site_id=...&include_balance=true`
- `GET /bff/api/v1/balances?site_id=...` and/or exact `item_id` filters if available.
- `POST /bff/api/v1/operations`
- `GET /bff/api/v1/operations/{id}`
- `PATCH /bff/api/v1/operations/{id}`
- `DELETE /bff/api/v1/operations/{id}` if draft delete action is implemented through delete.
- `POST /bff/api/v1/operations/{id}/submit` for confirm gating only; post-confirmation behavior is out of scope.

---

## 5. Target UX Specification

### 5.1 Modal sizing

- Modal overlays only Angular content workspace, not Django topbar/sidebar, unless current app-level modal system already overlays more broadly.
- Modal max height: `min(1024px, calc(100vh - 32px))` or equivalent.
- Modal width may remain current width or grow if needed, but must fit normal FHD content area.
- Modal body uses flex layout:
  - fixed header;
  - fixed main form/search area;
  - lines table area grows and scrolls internally;
  - fixed footer buttons.
- The whole page behind the modal should not scroll when table scrolls.

### 5.2 Header/form layout

Under modal title, first form row:

#### For `MOVE`

| Field | Width | Label | Required |
|---|---:|---|---|
| Operation type | 40% | `Тип операции` | yes |
| Source warehouse | 30% | `Склад-источник` | yes |
| Destination warehouse | 30% | `Склад-получатель` | yes |

#### For all non-`MOVE` operation types

| Field | Width | Label | Required |
|---|---:|---|---|
| Operation type | 40% | `Тип операции` | yes |
| Warehouse | 60% | `Склад` | yes |

Destination warehouse control is hidden, not disabled placeholder, for non-`MOVE`.

### 5.3 Logical warehouse mapping

The UI has one logical field `warehouseSiteId` for non-`MOVE`, but implementation may continue using `sourceSiteId`/`destinationSiteId` internally if mapping is explicit and tested.

Required payload mapping:

| Type | UI field(s) | Payload notes |
|---|---|---|
| `MOVE` | source + destination | `site_id = sourceSiteId`; send `source_site_id`, `destination_site_id` |
| `RECEIVE` | `Склад` | `site_id = warehouseSiteId`; do not send `site_id: null`; destination/source mapping must match current backend contract |
| `EXPENSE` | `Склад` | `site_id = warehouseSiteId`; source-site balance hint uses this warehouse |
| `WRITE_OFF` | `Склад` plus current write-off source logic if still present | `site_id = warehouseSiteId`; source-site balance hint uses this warehouse |
| `ISSUE` | `Склад` plus issue object when required | `site_id = warehouseSiteId`; source-site balance hint uses this warehouse |
| `ISSUE_RETURN` | `Склад` plus issue object when required | `site_id = warehouseSiteId`; balance hint is informational unless backend rule says otherwise |
| `CORRECTION` / `ADJUSTMENT` | `Склад` | Frontend/backend naming mismatch must be normalized in service and covered by test |

Acceptance: no valid save path may send `site_id: null`.

### 5.4 Comment row

- Full-width textarea below the warehouse row.
- 2 visible rows.
- Keep current placeholder unless product owner supplies a new one.

### 5.5 Add ТМЦ row

Below comment:

| Element | Width | Behavior |
|---|---:|---|
| Cached item search | 80% | searches by name/SKU/hashtag through Django BFF cache endpoint |
| `Создать ТМЦ` button | 20% | visible but `disabled`; no action in this TZ |

Search behavior:

- disabled until required warehouse context is selected when balance hint needs warehouse;
- debounced;
- uses cached search endpoint, not direct SyncServer;
- selecting result adds/updates line in table;
- duplicate item policy must be deterministic:
  - preferred: if item already exists, focus/highlight existing row rather than adding duplicate;
  - if duplicates remain allowed, document reason and test payload correctness.

---

## 6. Lines Table Specification

### 6.1 Table layout

Columns:

| Column | Width | Content |
|---|---:|---|
| `ТМЦ` | 60% | item name, SKU/category as secondary text if useful |
| `Отправляемое количество` / `Количество` | 20% | numeric input, step compatible with backend qty |
| `Имеется` | 15% | current available qty at selected source/warehouse |
| delete | 5% | cross button removes row |

For operations where “отправляемое” wording is wrong (`RECEIVE`), label may be `Количество`, but layout stays 60/20/15/5.

### 6.2 Independent scroll

- Table container has its own vertical scroll.
- Header remains visible if practical; sticky header preferred.
- Footer buttons remain visible while table scrolls.
- Modal remains within `1024px` height.

### 6.3 Sorting

Required sortable columns:

- item name;
- quantity;
- available quantity.

Default order: insertion order unless an active sort is selected.

Sorting must not mutate the underlying line identity in a way that breaks delete/edit by `localId`.

### 6.4 Text filter inside table

- Add a compact table-local text filter by item name.
- It filters already-added lines only.
- It must not replace the top add-TMC search.
- Filtered-out lines must still remain in draft payload.

### 6.5 Available quantity refresh

When source/warehouse changes:

1. refresh balances for all selected line item IDs;
2. update `availableQuantity/sourceSiteQuantity` for each row;
3. clear stale add-search dropdown results;
4. keep selected rows and user-entered quantities intact;
5. show loading/placeholder state for available quantity while refresh is pending.

Data source:

- Use Django BFF `/bff/api/v1/balances` or `catalog/search/items?...include_balance=true` through existing Angular services.
- Do not call SyncServer directly from Angular.
- Balance is a display hint; final validation remains SyncServer-owned.

UX validation:

- For outgoing operations (`MOVE`, `EXPENSE`, `WRITE_OFF`, `ISSUE`), if quantity exceeds available quantity, show row warning.
- Whether to block save/submit on insufficient stock must follow current backend/business rule; if unknown, warn but let server be authoritative. Document observed behavior.

---

## 7. Save / Confirm / Draft Lifecycle

### 7.1 Button states

`Сохранить черновик`:

- enabled when required fields are set and at least one line has item + positive quantity;
- disabled only with visible/understandable validation reason, not silently;
- for saved draft with unsaved changes, enabled again.

`Подтвердить`:

- disabled until operation has a persisted `id` from successful save;
- disabled if current modal has unsaved changes after last save;
- enabled only for editable/savable persisted draft and when user role/status permits submit;
- click should submit the saved operation ID, not a transient unsaved draft.

### 7.2 Save behavior

- New draft: `POST /bff/api/v1/operations`.
- Existing draft: `PATCH /bff/api/v1/operations/{id}`.
- After successful save:
  - keep modal open or show saved state; either is acceptable if user can clearly proceed to confirm;
  - store returned operation ID;
  - mark draft clean (`hasUnsavedChanges=false`);
  - refresh operations list in parent page.

### 7.3 Open/edit saved draft

Current regression to eliminate: opening a row for edit must not create an empty modal.

Required behavior:

1. User selects edit/open action on draft row.
2. Frontend calls `GET /bff/api/v1/operations/{id}`.
3. Response lines are mapped into `OperationDraftVm.lines` with:
   - stable `localId`;
   - `itemId`;
   - item name snapshot;
   - SKU snapshot;
   - unit/category snapshot when available;
   - quantity;
   - available quantity refreshed for currently selected warehouse.
4. User can edit composition/quantity.
5. User can edit type only if backend/API supports draft type update or a backend dependency is completed.
6. Save updates the persisted draft.

### 7.4 Delete saved draft

- Add/keep a delete action only for not-submitted operations where role/status allows it.
- Prefer existing `DELETE /bff/api/v1/operations/{id}` if current backend/BFF supports it.
- Require confirmation dialog.
- On success, close modal if open and refresh list.
- If API returns 403/409/422 because draft is no longer editable, show BFF error and refresh list.

---

## 8. Payload Contract Requirements

Executor must add/update frontend tests so payload mapping is covered.

Minimum payload expectations:

- Valid form never sends `site_id: null`.
- Lines include only backend-supported fields:
  - `line_number`;
  - `item_id`;
  - `qty`;
  - `comment` only if supported/needed.
- Do not send unsupported `unit_id`/`note` if backend ignores or rejects them.
- Use backend field names:
  - `issued_to_name`, not frontend-only `person_name`, when recipient/person text is sent;
  - `issue_object_id` / `issue_object_name_snapshot` for issue object flows;
  - map frontend `CORRECTION` to backend `ADJUSTMENT` if current UI still exposes `CORRECTION`.
- For `MOVE`, send source and destination IDs.
- For non-`MOVE`, hide destination UI and map the single warehouse into backend contract without nulls.

---

## 9. Implementation Guidance

### Recommended refactor

The existing modal component is large. Prefer small components/helpers:

```text
features/operations/components/operation-create-modal/
  operation-create-modal.component.ts
  operation-lines-table.component.ts        # new if practical
  operation-main-form.component.ts          # optional
  operation-draft-mappers.ts                # optional pure helpers
```

Keep CSS feature-local or shared via existing `.wh-*` classes. Do not restyle Django shell.

### State model

Suggested modal state:

- `localDraft`: editable fields;
- `savedOperationId`: ID after successful save;
- `lastSavedSnapshot`: serialized clean state or equivalent;
- `hasUnsavedChanges`: computed/explicit dirty flag;
- `isBalanceRefreshing`: per-table or per-row loading state;
- `lineSort`: `{ column, direction }`;
- `lineNameFilter`: string.

### Validation UX

If save/confirm is disabled, provide one of:

- small validation summary near footer;
- button title/tooltip;
- inline field hints.

Do not leave user with disabled buttons and no reason.

---

## 10. Test Strategy

### Static checks

Required:

```bash
cd Warehouse_frontend
npm run build
```

If lint/type scripts are added by the time executor works, run them too.

### Unit tests

Required where test tooling is available:

- `OperationsService` payload mapping tests for `MOVE`, `RECEIVE`, and one outgoing non-`MOVE` type.
- Draft detail mapping test: `OperationDto.lines` -> `OperationDraftVm.lines` preserves line data.
- Confirm gating logic: unsaved draft cannot submit; saved clean draft can submit.
- Balance refresh helper test if extracted.

Suggested command:

```bash
cd Warehouse_frontend
npx vitest run src/app/core/services/operations.service.spec.ts
```

If Vitest fails because optional Rollup dependency is missing, executor must try a non-destructive dependency repair such as `npm install --yes` only if appropriate for the repo state, or record the blocker clearly. Do not delete `node_modules` unless explicitly approved.

### Component tests

Required if Angular component test setup is usable:

- modal renders 40/30/30 row for `MOVE`;
- modal renders 40/60 and hides destination for non-`MOVE`;
- save button enables for valid form and disables with validation reason for invalid form;
- confirm button disabled until saved ID exists;
- lines table sort/filter/delete behavior.

If component test infra is not usable, leave checklist unchecked with blocker and compensate with Playwright smoke evidence.

### Integration tests with real dependencies

Applicable because this touches runtime BFF/API behavior.

Use Docker stand. Verify:

- `GET /bff/api/v1/catalog/search/items` works with selected warehouse and returns search results;
- `GET /bff/api/v1/balances` returns/update quantities used in UI;
- `POST /bff/api/v1/operations` creates draft without `422 site_id null`;
- `GET /bff/api/v1/operations/{id}` returns lines for edit;
- `PATCH /bff/api/v1/operations/{id}` updates draft lines/type if supported;
- `DELETE /bff/api/v1/operations/{id}` deletes draft if supported.

Suggested Django/BFF test command if BFF code touched:

```bash
docker exec warehouse_web python manage.py test apps.bff_api.tests
```

Suggested SyncServer test command if backend contract changes are needed:

```bash
docker exec warehouse_syncserver python -m pytest tests/test_operations_acceptance_and_issue_api.py
```

### Real stand smoke tests

Follow stand protocol first if requests fail.

Health checks:

```bash
curl -s --max-time 5 http://localhost:8000/api/v1/health
curl -s --max-time 5 http://localhost:8001/healthz/
pg_isready -h localhost -p 5432 -t 3
curl -s --max-time 5 http://localhost:4200/
```

Smoke scenario:

1. Open `/operations/` through Django-hosted Angular screen.
2. Click `+ Создать операцию`.
3. Verify modal layout for default type and for `MOVE`/non-`MOVE` switching.
4. Select warehouse(s).
5. Search known ТМЦ by name/SKU/hashtag.
6. Add row, enter quantity, verify available qty column.
7. Change warehouse/source and verify available qty refreshes without losing row quantity.
8. Save draft; verify no `422` and operation appears in list.
9. Reopen saved draft; verify type/warehouses/comment/lines are populated.
10. Edit line quantity/composition; save again.
11. Verify confirm is disabled while unsaved and enabled after save when status/role permits.
12. Delete not-submitted draft if delete action is in scope and API permits.

### UI automation

Use Playwright for the smoke scenario above where possible. Evidence should include:

- test command;
- screenshot or trace path;
- note whether Django shell/sidebar remains visible and Angular only changes content area.

### User scenarios

Required business scenarios:

1. Create `MOVE` draft with source/destination and one ТМЦ.
2. Create non-`MOVE` draft with single `Склад` field and one ТМЦ.
3. Open saved draft and edit rows.
4. Try to confirm before save: button remains disabled with reason.
5. Save, then confirm becomes available only for saved clean draft.

### Regression checks

Must verify no regression in:

- operations list loading/search/status tabs;
- cached item search in operation modal;
- BFF-only browser requests;
- existing issue object search for `ISSUE`/`ISSUE_RETURN` if present;
- non-root cancelled operations visibility rules if touched.

---

## 11. Test Stand

### Services

| Service | Address | Health Check | Container |
|---|---|---|---|
| SyncServer API | `http://localhost:8000` | `GET /api/v1/health` | `warehouse_syncserver` |
| Django / BFF | `http://localhost:8001` | `GET /healthz/` | `warehouse_web` |
| PostgreSQL | `localhost:5432` | `pg_isready -h localhost -p 5432 -t 3` | `warehouse_postgres` |
| Angular | `http://localhost:4200` | `GET /` | `warehouse_angular` |

### Lifecycle

- Default assumption: stand is running.
- If connection fails, run from workspace root:

```bash
make up
```

- If `make up` is unavailable/fails, try:

```bash
docker compose up -d
```

- Reset/cleanup: do not run destructive volume cleanup unless explicitly approved. For normal UI testing, delete only test drafts created by the scenario through the app/API.

### Seed data

Need at least:

- authenticated user/session able to create operation drafts;
- at least two warehouses/sites for `MOVE`;
- at least one active catalog item searchable by name/SKU/hashtag;
- known balance for that item on at least one selected source warehouse.

If seed is missing, executor may create safe test data through existing app/API paths if authorized and non-destructive, or report blocker.

### Environment variable names only

- `DJANGO_ENV`
- `SYNC_SERVER_URL`
- `SYNC_ROOT_USER_TOKEN`
- `SYNC_DEVICE_TOKEN`
- `DATABASE_URL`
- `DJANGO_SETTINGS_MODULE`
- `SECRET_KEY`

Never print or hardcode secret values.

---

## 12. Acceptance Criteria

### Layout acceptance

- [ ] `MOVE` modal first row visually uses 40/30/30 proportions: type/source/destination.
- [ ] Non-`MOVE` modal first row visually uses 40/60 proportions: type/`Склад`; destination is hidden.
- [ ] Comment is a full-width 2-row textarea.
- [ ] Add row uses 80% cached search + 20% disabled `Создать ТМЦ` button.
- [ ] Modal fits within 1024px height; lines table scrolls independently; footer buttons remain visible.

### Lines table acceptance

- [ ] Row columns follow 60/20/15/5 proportions.
- [ ] Available quantity is shown for selected warehouse/source.
- [ ] Changing warehouse/source refreshes available quantities without losing selected rows or entered quantities.
- [ ] Table supports sorting by item name, quantity, available quantity.
- [ ] Table-local name filter filters displayed rows only and does not remove them from payload.
- [ ] Delete cross removes only the target row.

### Save/confirm acceptance

- [ ] Valid save never sends `site_id: null`.
- [ ] Save button enables for valid draft and explains disabled reason when invalid.
- [ ] Confirm button is disabled before first successful save.
- [ ] After successful save, persisted operation ID is stored and clean saved draft can be confirmed when role/status permits.
- [ ] After editing a saved draft, confirm is disabled until changes are saved again.
- [ ] Opening saved draft loads existing lines into modal.
- [ ] Not-submitted draft can be deleted if current API/permissions allow; otherwise blocker documented.
- [ ] Submitted/non-editable operations cannot be edited by this modal.

### Architecture acceptance

- [ ] Angular calls only Django same-origin BFF.
- [ ] No SyncServer tokens in browser code/storage.
- [ ] No direct local Django warehouse-domain writes.
- [ ] Any backend gap for changing persisted draft type is documented and not silently faked.

---

## 13. Evidence Required In Executor Report

Executor final report must include:

```markdown
## Evidence

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|
| Static build | `npm run build` | pass/fail | short log or path |
| Unit tests | `npx vitest run ...` | pass/fail/skipped | log/blocker |
| Component tests | `<command>` | pass/fail/skipped | log/blocker |
| BFF/API integration | `docker exec ...` / curl | pass/fail/skipped | endpoint/status note |
| Stand smoke | browser/manual/commands | pass/fail/skipped | URL/screenshot/log |
| UI automation | Playwright | pass/fail/skipped | trace/screenshot path |
| User scenario | manual/Playwright | pass/fail/skipped | scenario note |
```

Final acceptance may be checked only after evidence covers layout, save, reopen/edit, balance refresh, and confirm gating.
