# TZ: Репозиторий выдачи — frontend workspace и операции с объекта

## Execution Strategy

- [x] 🟢 Parallel execution recommended
- **Reason:** frontend work can be staged by ownership boundaries: Django shell/sidebar route, Angular repository workspace, and operations-modal integration. These areas share the backend/BFF contract from `docs/TZ-ISSUED_REPOSITORY_BACKEND_CONTRACT.md`; final integration must happen after backend category/tree/object-assets endpoints are available. Avoid parallel edits to the same Angular component in the same stage.

## Execution Checklist

- [x] 0. Context verified
- [x] 1. Architecture boundaries confirmed
- [x] 2. Implementation stage 1 complete: Django shell/sidebar route
- [x] 3. Implementation stage 2 complete: Angular 40/60 repository workspace
- [x] 4. Implementation stage 3 complete: operation modal return/write-off from object assets
- [x] 5. Unit/component tests complete
- [x] 6. Integration tests with real dependencies complete (BFF tests + SPA route tests)
- [x] 7. Stand smoke tests complete
- [x] 8. UI automation tests complete (Playwright on /issued-assets/ and /operations/lost-assets, plus object-asset row return/write-off modal path)
- [x] 9. User scenario tests complete (sidebar label, workspace render, category create, object form open, ISSUE → save → submit return flow on real stand)
- [x] 10. Regression checks complete (operations, lost-assets, temporary-items, nomenclature, BFF tests)
- [x] 11. Documentation updated
- [x] 12. Final acceptance review complete (orchestrator)

## Check Rules

- Architect creates this checklist and acceptance criteria.
- Executor agents may check implementation and test items only after implementing their assigned scope and attaching evidence.
- QA verifier may check final acceptance only after reviewing evidence, screenshots/Playwright output, and backend/BFF contract compatibility.
- If a required check is skipped or unavailable, the checkbox stays unchecked with a blocker note.

## Reviewer Notes

### 2026-06-04 first review — rejected (5 findings, 3 blocker + 2 major)

- Object assigned-assets actions open `OperationCreateModalComponent`, but `ObjectPanelComponent` handles `save`/`submit` by only refreshing object assets and closing the modal; it does not call `OperationsService.createOperation`, `updateOperation`, or `submitOperation`.
- `/bff/api/v1/issue-objects/{id}/assets` is normalized by Django BFF/sync client as a paginated object with `items`, while `IssueObjectsService.loadObjectAssets()` expects a raw array and stores the response directly in `objectAssets`.
- Object-source `ISSUE_RETURN` / `WRITE_OFF` still expose the generic catalog/warehouse item search; manually added lines are not constrained to assets issued to the selected object.
- `RepositoryTreeComponent` both flattens expanded nodes and renders nested children in the template, so expanded nodes can be duplicated and nested category nodes can be rendered as object rows.
- Reported Playwright/user scenarios covered shell/category/object-form smoke only; they did not verify assigned-property row actions, operation creation/submission, or updated object assets.

### 2026-06-04 first round of fixes (5 findings closed)

- `ObjectPanelComponent.onModalSave/onModalSubmit` now call `OperationsService.createOperation` / `updateOperation` / `submitOperation` (parity with `OperationsPageComponent.onDraftSave/onDraftSubmit`). On `submit`, after `submitOperation(result.id)` the modal closes and `loadObjectAssets` is awaited to refresh the assigned-assets table.
- `IssueObjectsService.loadObjectAssets` now reads `result.items ?? []` from the BFF paginated response and tolerates both raw-array and wrapper shapes.
- `OperationCreateModalComponent` now hides `app-item-cache-search` for object-source flows and shows a blue hint card "Позиция зафиксирована за объектом выдачи…". `lineAvailableQtyError` rejects object-source rows that have no `availableQuantity` and the `Сохранить/Подтвердить` buttons stay disabled in that case. `buildPayload` falls back to the user's default site for `ISSUE_RETURN` and object-source `WRITE_OFF` so the required `site_id` is always sent.
- `RepositoryTreeComponent` removed the duplicate nested `<ul>`; rendering is now a single flat `walk()` over the tree.
- First full scenario verified: receive → issue 3 → assigned-asset qty=3 → row Возврат (modal prefill, hidden item-search, qty=1) → Подтвердить → `ISSUE_RETURN submitted`, qty=2 → row Списание (writeOffSource='object') → qty=2 → Подтвердить → `WRITE_OFF submitted`, qty=0, warehouse balance unchanged at 7.

### 2026-06-04 second review — rejected (2 blocker)

- `Сохранить черновик` → последующий `Подтвердить` ломает object-source context: after `onModalSave()` the DTO is remapped via `mapDtoToDraftVm()` and the server response drops `writeOffSource: 'object'` and `availableQuantity` (these are UI-only fields). For `ISSUE_RETURN` submit then gets blocked by the validator; for object `WRITE_OFF` the source selector can flip back to `warehouse`.
- Modal from assigned-property row does not lock the object/type/source: the user can clear or pick a different issue object and switch the operation type while the line/qty cap stays from the original assigned asset.

### 2026-06-04 second round of fixes (2 blockers closed)

- `OperationDraftVm` extended with two new UI-only fields that survive a save → remap: `prefilledAssetLine`, `lockedFromAssetRow`, and `assignedAssetAvailableQty`. The `lockedFromAssetRow` flag is set on row-action drafts in `ObjectPanelComponent.onReturn/onWriteOff` and explicitly re-attached in `ObjectPanelComponent.onModalSave` after `mapDtoToDraftVm`. Per-line `availableQuantity` is also re-attached by matching on `itemId` (server-generated `localId` differs from the client-side one). Re-attach covers `type`, `writeOffSource`, `sourceSiteId`, `destinationSiteId`, `personName`, `comment`, `effectiveAt`, and `lines[].availableQuantity`.
- `OperationCreateModalComponent` now computes `isLockedFromAssetRow = !!localDraft().lockedFromAssetRow`. When true:
  - The operation type select is `[disabled]="isEdit() || isLockedFromAssetRow()"`.
  - The "✎" edit button next to the issue object is hidden.
  - The `writeOffSource` radio is hidden (`@if (showWriteOffSource() && !isLockedFromAssetRow())`).
  - `onTypeModelChange` and `clearIssueObject` early-return when locked, so even programmatic flips cannot change the context.
- Verified on the real stand: assigned-asset qty=2 → click Возврат → modal opens locked (type select disabled, no "✎" button, hint card shown, "Имеется на объекте: 2") → qty=1, склад=Base → click Сохранить черновик → modal stays open, **type select still [disabled] "Возврат выдачи" [selected], object still read-only, "Имеется на объекте: 2" still 2, save/submit still enabled** → click Подтвердить → `ISSUE_RETURN | submitted` issued, assigned-asset qty=1. Evidence: `before-save-locked.png`, `after-save-locked-state-preserved.png`, `after-save-submit-final.png`.

### 2026-06-04 re-review — rejected

- Direct `Подтвердить` from assigned-asset row is now wired to create/submit operations, `IssueObjectsService.loadObjectAssets` handles the BFF paginated `items` shape, the generic TMC search is hidden for object-source rows, and the duplicate nested tree renderer was removed.
- Remaining blocker: save-then-submit from an assigned-asset modal still loses object-source runtime context. `ObjectPanelComponent.onModalSave()` remaps the server response through `OperationsService.mapDtoToDraftVm()`, but the mapped draft does not restore `writeOffSource: 'object'` for object `WRITE_OFF` and does not preserve or re-fetch line `availableQuantity`. As a result, saved `ISSUE_RETURN` drafts become blocked by the object-quantity validator, and saved object `WRITE_OFF` drafts can fall back to source selection instead of staying in object-source mode.
- Remaining blocker: a modal launched from an assigned-property row does not lock the assigned object/type/source context. The user can clear/change the prefilled issue object and can change the operation type before save; this can make the line quantity validation refer to the original assigned asset while the payload points to another object/type.
- Required fix: mark row-action drafts with an explicit locked assigned-asset context (for example `prefilledAssetLine: true` plus immutable object/item/source metadata), preserve that context across save/remap or re-fetch the object asset before enabling submit, and disable object/type/source changes that would detach the draft from the selected assigned-asset row.
- Required evidence: add UI/regression coverage for `Возврат` and object `Списание` using `Сохранить черновик` → `Подтвердить`, and for attempts to change object/type/source from a row-action modal.

### 2026-06-05 user bug: «кнопка сохранения объекта деактивирована» — fixed

- **Симптом:** after filling the object-creation form (paste / autofill), the Submit button stays disabled even when all required fields (Наименование, Категория) appear to be filled visually. This is a known Angular `[(ngModel)]` + signals limitation: programmatically-set values (paste, password manager autofill, drag & drop, JS fill) do not fire the `(ngModelChange)` event that would update the connected signal. The signals `displayName` and `categoryId` remain empty, so `isValid()` stays `false` and the Save button stays disabled.
- **Fix:** migrated `ObjectFormComponent`, `ObjectPanelComponent` (inline create/edit forms), `CategoryPanelComponent`, and `NewCategoryFormComponent` from `[(ngModel)]` + signals to **Reactive Forms** (`[formGroup]` + `formControlName` + `FormControl` with `Validators.required`). Reactive Forms dispatch `input`/`change` events internally and track value changes through `valueChanges` streams, which are then exposed as signals via `toSignal(form.valueChanges)`. The `canSave` / `canCreate` / `canEdit` computed signals re-evaluate on every `valueChanges` event regardless of how the value was set (keyboard, paste, autofill, programmatic JS).
- **Verified via Playwright:** programmatically set name value via `el.value = '…'; el.dispatchEvent(new Event('input', {bubbles:true}))` and selected a category via `s.value = '1'; s.dispatchEvent(new Event('change', {bubbles:true}))` — **`saveBtnDisabled=null → ENABLED ✓`** (Reactive Forms catch all input events).
- **Files changed:**
  - `Warehouse_frontend/src/app/features/issued-assets/components/object-form/object-form.component.ts` — Full rewrite: `FormsModule` → `ReactiveFormsModule`, `[ngModel]` → `formControlName`, `isValid` computed → `canSave` via `toSignal(form.statusChanges) + toSignal(form.valueChanges)`.
  - `Warehouse_frontend/src/app/features/issued-assets/components/object-panel/object-panel.component.ts` — Inline create/edit forms migrated to `[formGroup]="createForm"` / `[formGroup]="editForm"` with `formControlName`. Removed signal fields `displayName/comment/categoryId/objectType/code/isActive` and computeds `isCreateValid/isEditValid`. Added `createForm` and `editForm` `FormGroup` instances + `canCreate` / `canEdit` computeds driven by `toSignal(form.statusChanges)`.
  - `Warehouse_frontend/src/app/features/issued-assets/components/category-panel/new-category-form.component.ts` — Migrated to `[formGroup]="form"` with `formControlName`.
  - `Warehouse_frontend/src/app/features/issued-assets/components/category-panel/category-panel.component.ts` — Migrated to `[formGroup]="form"` with `formControlName`.
- **Evidence:** `reactive-forms-save-enabled-after-paste.png` (Screenshot showing Save button enabled after programmatic fill).

### 2026-06-04 final acceptance — accepted

- Round-2 fixes close the remaining blockers: row-action drafts now carry `lockedFromAssetRow`, `prefilledAssetLine`, and `assignedAssetAvailableQty`; `ObjectPanelComponent.onModalSave()` re-attaches `type`, `writeOffSource`, locked flags, site/person/comment/effectiveAt, and per-line `availableQuantity` after server DTO remap.
- The row-action modal now keeps the assigned-object context locked in user UI: type select is disabled/guarded, issue-object edit button is hidden/guarded, and write-off source radio is hidden for locked drafts.
- Verification accepted: `git diff --check` passed in root, `Warehouse_web`, and `Warehouse_frontend`; `CI=true NG_CLI_ANALYTICS=false npm run build` passed with only known SCSS budget warnings; Django route/BFF regression tests ran 49 tests OK.
- Real-stand evidence from the executor is accepted for save → submit: assigned-asset qty=2 → `Возврат` modal locked → save draft preserves type/object/available qty → submit creates `ISSUE_RETURN submitted` and object qty becomes 1.
- Remaining non-blocking UX risk: locked object-source modal still allows removing the prefilled line, which leaves the modal without positions and blocks save/submit. This does not detach the payload from another object/type/source, but should be considered for a follow-up polish/regression test.

## 1. Requirement Source

Canonical source: `Functional and WorkLogik.md`, section `VI/ репозиторий выдачи`, plus product clarifications from architecture review:

- `Репозиторий выдачи` appears in the sidebar near the repository of unaccepted/lost assets.
- Current UI label `Непринятое` must be renamed to `Репозиторий непринятого`.
- Репозиторий выдачи uses a 40/60 workspace:
  - left 40%: searchable tree of issue-object categories and issue objects;
  - right 60%: work area for selected category/object/property.
- Left panel has search and buttons to create issue object and issue-object category.
- Category and object CRUD must be complete, analogous to the SPA nomenclature catalog pattern.
- Issue object creation fields: name, indexed comment, category.
- On object click, right panel shows a table of currently assigned/not-written-off property.
- From an assigned-property row, user can start:
  - `Возврат выдачи` for that property;
  - `Списание с объекта` for that property.
- `ISSUE_RETURN` and object-source `WRITE_OFF` must search and validate against property assigned to the object, not warehouse balances.

Backend/BFF contract source: `docs/TZ-ISSUED_REPOSITORY_BACKEND_CONTRACT.md`.

## 2. Product Semantics For UI

Use these labels and mental model in UI copy:

- `Выдача`: movement from warehouse to issue object. Enterprise still owns the property.
- `Возврат выдачи`: movement from issue object back to warehouse.
- `Списание со склада`: warehouse property removed from enterprise.
- `Списание с объекта`: issued property removed from enterprise while warehouse balance is not touched.

Do not present issued property as vanished from the enterprise. If the balances screen is touched or if backend exposes enterprise totals, UI should distinguish:

- warehouse available quantity;
- issued-to-objects quantity;
- enterprise total quantity.

## 3. Current Implementation Snapshot

Observed state before this TZ:

- `Warehouse_frontend/src/app/app.routes.ts`
  - Angular route `/issued-assets` exists with child tabs `property` and `objects`.
- `Warehouse_web/config/urls.py`
  - No Django host/catchall route for `/issued-assets/`.
- `Warehouse_web/templates/includes/sidebar.html`
  - Has `Непринятое` link to `/operations/lost-assets`.
  - No `Репозиторий выдачи` link.
- `Warehouse_frontend/src/app/features/issued-assets/pages/issued-assets-page/issued-assets-page.component.ts`
  - Current UI is tabs `Имущество` / `Объекты`, not 40/60 tree/workspace.
- `Warehouse_frontend/src/app/features/issued-assets/components/objects-table/objects-table.component.ts`
  - Flat object table with search/type/active filters.
- `Warehouse_frontend/src/app/features/issued-assets/components/object-form/object-form.component.ts`
  - Form fields are `display_name`, `object_type`, `code`; no category/comment.
- `Warehouse_frontend/src/app/features/issued-assets/components/object-detail/object-detail.component.ts`
  - Shows assigned assets read-only; no row actions.
- `Warehouse_frontend/src/app/features/operations/components/operation-create-modal/operation-create-modal.component.ts`
  - Has issue-object search and write-off source selector.
  - Item search and quantity hints still use warehouse-oriented balance/search for return/object write-off flows.

## 4. Scope

### In scope

Django shell:

- Add `/issued-assets/` Django-hosted SPA route and catchall.
- Add sidebar item `Репозиторий выдачи` near `Репозиторий непринятого`.
- Rename UI/sidebar label `Непринятое` to `Репозиторий непринятого` where this label represents the lost/unaccepted repository.

Angular repository workspace:

- Replace the current tab/table repository UI with a 40/60 workspace.
- Implement issue-object category/object tree.
- Implement category CRUD.
- Implement object CRUD with fields name, comment, category.
- Implement selected-object assigned-property table with row actions.

Operations UI:

- Start return/write-off operation from assigned-property row.
- For `ISSUE_RETURN` and object-source `WRITE_OFF`, search/select property from the selected object's issued assets, not warehouse catalog balances.
- Prefill operation modal with object, item, qty constraints, and source mode.

### Out of scope

- SyncServer DB migrations and operation register math; covered by backend TZ.
- Changing `IssueObject.id` to UUID.
- Adding a new `WRITE_OFF_FROM_OBJECT` operation type.
- Direct browser calls to SyncServer.
- Storing SyncServer tokens in browser storage.
- Redrawing Django topbar/sidebar in Angular.
- Full redesign of the balances screen unless backend exposes enterprise totals and this is explicitly assigned in the implementation stage.

## 5. Target UX / Routes

### 5.1 Django route and sidebar

Target sidebar under `Остатки и операции`:

1. `Остатки`
2. `Операции`
3. `Операции к приёмке`
4. `Репозиторий непринятого`
5. `Репозиторий выдачи`

Target routes:

- `/operations/lost-assets` keeps route path unless a separate route-migration TZ is approved; only label changes to `Репозиторий непринятого`.
- `/issued-assets/` opens the Django-hosted Angular SPA screen.
- `/issued-assets/<path>` refresh/deep-link must render the Angular shell through Django.

### 5.2 Angular route shape

Keep a single feature prefix:

- `/issued-assets/` — repository workspace default.
- Optional query/path state:
  - selected category id;
  - selected object id;
  - search query.

Avoid final UX based on separate tab pages `/issued-assets/property` and `/issued-assets/objects`. Existing routes may redirect during migration, but target screen is the single 40/60 workspace.

### 5.3 40/60 workspace layout

Left panel, 40%:

- Search input at top.
- Buttons:
  - `+ Объект выдачи`;
  - `+ Категория выдачи`;
  - expand/collapse all if useful.
- Scrollable tree of categories and issue objects.
- Category nodes can expand/collapse.
- Object nodes are children of categories.
- Search filters by category name, object name, and object comment.
- Inactive/deleted items must be visually distinct if shown.

Right panel, 60%:

- Empty state when nothing selected.
- Category selected:
  - category details/edit form;
  - child categories/objects summary;
  - actions: edit, deactivate/delete when allowed.
- Object selected:
  - object details/edit form or profile header;
  - assigned active property table;
  - actions: edit object, deactivate/delete when allowed;
  - per-property actions: `Возврат`, `Списание`.

Layout requirements:

- Must fit the Django content area without redrawing topbar/sidebar.
- Internal scroll should scroll panels/tables, not the entire shell.
- Sticky table headers where tables exceed panel height.
- FHD-friendly; responsive fallback may stack panels below narrow viewport.

## 6. Frontend Data Contract

Use Django BFF only.

Expected BFF endpoints from backend TZ:

- `GET /bff/api/v1/issue-objects/tree`
- `GET /bff/api/v1/issue-object-categories`
- `POST /bff/api/v1/issue-object-categories`
- `GET /bff/api/v1/issue-object-categories/{id}`
- `PATCH /bff/api/v1/issue-object-categories/{id}`
- `DELETE /bff/api/v1/issue-object-categories/{id}`
- `GET /bff/api/v1/issue-objects`
- `POST /bff/api/v1/issue-objects`
- `GET /bff/api/v1/issue-objects/{id}`
- `PATCH /bff/api/v1/issue-objects/{id}`
- `DELETE /bff/api/v1/issue-objects/{id}`
- `GET /bff/api/v1/issue-objects/{id}/assets`
- `GET /bff/api/v1/issued-assets`

Frontend models should include:

```ts
interface IssueObjectCategory {
  id: string;
  name: string;
  parent_id: string | null;
  sort_order: number;
  is_active: boolean;
}

interface IssueObject {
  id: string; // backend integer id serialized as string/number by BFF; do not assume UUID
  display_name: string;
  comment?: string | null;
  category_id: string;
  is_active: boolean;
  issued_positions_count?: number;
  issued_total_qty?: string;
}

type IssueRepositoryTreeNode =
  | { type: 'category'; id: string; name: string; parent_id: string | null; children?: IssueRepositoryTreeNode[]; is_active: boolean }
  | { type: 'object'; id: string; name: string; comment?: string | null; category_id: string; is_active: boolean };
```

Do not keep `object_type` as the primary UI grouping. If backend still returns it, treat it as compatibility metadata only.

## 7. Implementation Plan

### Stage 0 — Contract and UX lock

Owner: parent/orchestrator.

Actions:

1. Confirm backend/BFF endpoints from backend TZ are available or mocked.
2. Confirm target sidebar labels.
3. Confirm whether old `/issued-assets/property` and `/issued-assets/objects` routes redirect to the new workspace or remain temporary aliases.
4. Confirm create/edit presentation: right-panel forms vs modal forms.

Acceptance:

- Frontend executor has stable DTO names and route expectations.
- No executor implements a final tab/table-only repository UI.

### Stage 1A — Django shell/sidebar route

Writable areas:

- `Warehouse_web/config/urls.py`
- `Warehouse_web/apps/catalog/views.py`
- `Warehouse_web/templates/includes/sidebar.html`
- Django SPA template file if a separate `issued_assets_spa.html` is needed
- `Warehouse_web` tests for routes/templates if existing patterns support it

Required changes:

1. Add `IssuedAssetsSPAView` or equivalent using the existing Angular SPA serve pattern.
2. Add exact and catchall routes for `/issued-assets/`.
3. Add sidebar link `Репозиторий выдачи`.
4. Rename sidebar label `Непринятое` to `Репозиторий непринятого`.
5. Ensure active link state works for `/issued-assets` and `/operations/lost-assets`.

Acceptance:

- Refreshing `/issued-assets/` and nested selected-state routes does not return HTML error/404 outside the shell.
- Sidebar contains both repositories in the expected order.

### Stage 1B — Angular repository models/services

Writable areas:

- `Warehouse_frontend/src/app/core/models/issue-objects.models.ts`
- `Warehouse_frontend/src/app/core/services/issue-objects.service.ts`
- `Warehouse_frontend/src/app/core/services/issued-assets.service.ts`
- `Warehouse_frontend/src/app/core/api/*` only if BFF helper changes are needed

Required changes:

1. Add category and tree models.
2. Add service methods for tree, category CRUD, object CRUD, object assets.
3. Preserve same-origin BFF usage only.
4. Normalize backend integer IDs safely as strings in UI state if current frontend conventions do this.

Acceptance:

- No browser code calls SyncServer directly.
- Service tests or lightweight component tests verify BFF URL construction if test tooling exists.

### Stage 1C — Angular 40/60 repository workspace

Writable areas:

- `Warehouse_frontend/src/app/app.routes.ts`
- `Warehouse_frontend/src/app/features/issued-assets/**`
- Shared UI components only if already used by this feature and ownership is clear

Required changes:

1. Replace tab shell with 40/60 workspace shell.
2. Add left tree component with search, create category/object buttons, expand/collapse, scroll.
3. Add category form/panel with create/edit/deactivate/delete.
4. Add object form/panel with create/edit/deactivate/delete, fields name/comment/category.
5. Add selected-object assigned-assets table.
6. Add row action buttons `Возврат` and `Списание`.
7. Add loading/error/empty states.
8. Redirect or gracefully handle old routes `/issued-assets/property`, `/issued-assets/objects`, `/issued-assets/objects/:id` if they already exist in user bookmarks/test links.

Acceptance:

- UI matches 40/60 target, not the old tabs-only layout.
- Category and object CRUD are both available.
- Object selected in tree shows only its active assigned/not-written-off property.

### Stage 1D — Operation modal integration for object property

Writable areas:

- `Warehouse_frontend/src/app/features/operations/components/operation-create-modal/**`
- `Warehouse_frontend/src/app/features/operations/pages/operations-page/**` only if modal launch contract lives there
- `Warehouse_frontend/src/app/core/models/operations.models.ts`
- `Warehouse_frontend/src/app/core/services/operations.service.ts`
- `Warehouse_frontend/src/app/features/issued-assets/**` for launching operations from rows

Required changes:

1. Define a modal prefill contract for object-property actions:
   - operation type;
   - issue object id/name;
   - item/inventory subject id;
   - available object quantity;
   - write-off source for `WRITE_OFF`.
2. `Возврат` row action opens operation modal as `ISSUE_RETURN`.
3. `Списание` row action opens operation modal as `WRITE_OFF` with object source.
4. For `ISSUE_RETURN` and object-source `WRITE_OFF`, item search/list uses issued assets for selected object, not warehouse catalog balance search.
5. Quantity validation uses object issued quantity.
6. Warehouse `WRITE_OFF` still uses warehouse balance search/validation.
7. `ISSUE` still selects issue object from repository, but item search remains warehouse/source-site based.

Acceptance:

- User cannot return/write off more than assigned to the object.
- Object source mode does not show misleading warehouse stock as the available quantity.
- Payload for object write-off remains `operation_type=WRITE_OFF` + `issue_object_id`.
- No new `WRITE_OFF_FROM_OBJECT` operation type appears in frontend enums.

### Stage 2 — Integration

Owner: parent/orchestrator with frontend executor.

Actions:

1. Run frontend build.
2. Run Django tests for route/sidebar if changed.
3. Run real stand with backend endpoints.
4. Run Playwright smoke/user scenario.
5. Update active docs if route labels or SPA route matrix changed.

Acceptance:

- Browser scenario works through Django-hosted route, not Angular dev-server-only route.
- Evidence includes screenshots or Playwright trace/report for repository tree and object row actions.

## 8. Test Strategy

### Static checks

Required:

- `Warehouse_frontend`: `npm run build`.
- `Warehouse_web`: `python manage.py test` for changed route/BFF/template tests.
- TypeScript compile through build.

### Unit tests

If Angular test tooling exists:

- issue-object service builds correct BFF URLs;
- tree filtering preserves category/object hierarchy;
- operation prefill mapper builds correct draft for return/write-off;
- quantity validator uses object-issued qty for object flows.

Django:

- route/view test for `/issued-assets/` exact and catchall;
- sidebar template smoke test if pattern exists.

### Component tests

If Angular component tests are configured:

- left tree renders categories/objects and search states;
- category form validates name/parent;
- object form validates name/comment/category;
- assigned-assets table renders actions;
- operation modal shows object-issued availability for return/object write-off.

### Integration tests with real dependencies

Required through running stand or API-backed test:

1. Load tree from BFF.
2. Create category through UI/service.
3. Create object through UI/service.
4. Load object assets.
5. Start operation modal from assigned asset row.
6. Submit return/write-off and verify updated object assets.

### Real stand smoke tests

Use local Docker stand from workspace root:

| Service | Address | Health Check | Container |
|---|---|---|---|
| SyncServer API | `http://localhost:8000` | `GET /api/v1/health` | `warehouse_syncserver` |
| Django | `http://localhost:8001` | `GET /healthz/` | `warehouse_web` |
| PostgreSQL | `localhost:5432` | `pg_isready -h localhost -p 5432 -t 3` | `warehouse_postgres` |
| Angular | `http://localhost:4200` or built assets via Django | `GET /` where applicable | `warehouse_angular` |

Environment variable names only:

- `DJANGO_ENV`
- `SYNC_SERVER_URL`
- `SYNC_ROOT_USER_TOKEN`
- `SYNC_DEVICE_TOKEN`
- `DATABASE_URL`
- `DJANGO_SETTINGS_MODULE`
- `SECRET_KEY`

Smoke scenario:

1. Log in to Django stand as a user with storekeeper/chief permissions.
2. Open sidebar and verify labels `Репозиторий непринятого` and `Репозиторий выдачи`.
3. Open `/issued-assets/`.
4. Create category and object.
5. Issue a test TMC to that object using operations flow or backend fixture.
6. Open object in tree and verify assigned property table.
7. Click `Возврат`, verify operation modal is prefilled and validates against object qty.
8. Click `Списание`, verify source is object and payload remains `WRITE_OFF + issue_object_id`.

Reset/cleanup:

- Prefer unique names/codes/comments and audit-preserving cleanup.
- Do not run destructive cleanup on shared stand without explicit approval.

### UI automation

Use Playwright through Django-hosted routes:

- Navigate to `/issued-assets/`.
- Assert 40/60 layout and tree controls.
- Create category and object if backend stand is writable.
- Search object by name/comment.
- Open object and assert assigned property table.
- Trigger return/write-off modal from an assigned row.
- Verify modal source/quantity fields.

### User scenarios

Minimum scenarios:

1. Storekeeper creates issue-object category and object.
2. Storekeeper finds object by name/comment in tree.
3. Storekeeper sees property assigned to object.
4. Storekeeper returns part of property from object.
5. Storekeeper writes off remaining property from object.
6. Storekeeper performs warehouse write-off and sees it remains separate from object write-off.

### Regression pack

- Existing operations create/submit/cancel flows.
- Existing `ISSUE` object selection.
- Existing warehouse `WRITE_OFF`.
- Pending acceptance page.
- Repository of unaccepted/lost assets after label rename.
- Django shell topbar/sidebar layout.
- Nomenclature SPA still renders; do not break shared Angular shell assets.

## 9. Evidence Table Template

Executor completion reports must include:

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|
| Static checks | `<command>` | pass/fail/skipped | log path or note |
| Unit tests | `<command>` | pass/fail/skipped | log path or note |
| Component tests | `<command>` | pass/fail/skipped | test output or reason |
| DB/BFF integration | `<command>` / API | pass/fail/skipped | URL/log note |
| Stand smoke | browser/API | pass/fail/skipped | URL/log/screenshot |
| UI automation | Playwright | pass/fail/skipped | report/trace/screenshot |
| User scenarios | manual/automated | pass/fail/skipped | scenario notes |
| Regression | `<command>` | pass/fail/skipped | affected flows |

## 10. Documentation Updates Required

Update active docs when implementation is complete:

- `Functional and WorkLogik.md` if labels/wording are refined.
- `Warehouse_frontend/docs/ARCHITECTURE_FRONTEND_SPA.md` for `/issued-assets/` route state.
- `AI_ENTRY_POINTS.md` / `INDEX.md` only if entry points changed and no unrelated edit conflict exists.
- Any user-facing README/API route map if maintained.

## 11. Open Questions / Decisions Locked By This TZ

Locked:

- Final repository UI is 40/60 tree/workspace, not tabs-only.
- Sidebar label `Непринятое` becomes `Репозиторий непринятого`.
- Add sidebar item `Репозиторий выдачи`.
- `WRITE_OFF` stays one operation type; object source is UI mode + `issue_object_id` payload.
- Frontend must treat issue-object IDs as opaque values and must not assume UUID.

Open for executor confirmation before implementation:

1. Should create/edit be right-panel inline forms or modal windows?
2. Should old `/issued-assets/property` and `/issued-assets/objects` URLs redirect, or can they be removed immediately?
3. Should object/category changes use immediate-save CRUD or a batch buffer like nomenclature? Default for this TZ: immediate CRUD unless product owner asks for batch.
