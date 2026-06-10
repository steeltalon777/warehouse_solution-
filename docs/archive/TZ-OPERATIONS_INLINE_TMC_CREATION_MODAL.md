# TZ: Operations Inline TMC Creation Modal

## Execution Strategy

- [ ] 🟢 Parallel execution recommended
- **Reason:** задача затрагивает независимые слои: SyncServer contract for draft inline lines, Angular VM/payload mapping, отдельный Angular modal UI/search, и BFF pass-through/tests. После общего согласования контракта эти зоны можно выполнять параллельно без записи в одни и те же файлы; родительский интегратор в конце связывает второй modal с существующим modal операции.

### Parallel work units

| Stage | Unit | Owner area | Writable files/areas | Required inputs | Output/evidence |
|---|---|---|---|---|---|
| 0 | Context / contract verification | Parent/orchestrator | Documentation only until implementation starts | This TZ, `Functional and WorkLogik.md`, ADR-0012, current operation/catalog contracts | Confirmed target: button creates an inline operation line, not an immediate catalog item |
| 1A | SyncServer draft inline-line contract | `SyncServer` operations API/service/tests | `SyncServer/app/schemas/operation.py`, `SyncServer/app/services/operations_service.py`, focused operation tests | Existing `OperationCreate.temporary_item` flow and materialization tests | `PATCH /api/v1/operations/{id}` can preserve/create inline lines in draft; response exposes safe inline payload for reopening drafts |
| 1B | Angular operation VM and payload mapping | `Warehouse_frontend` core operation model/service/tests | `Warehouse_frontend/src/app/core/models/operations.models.ts`, `Warehouse_frontend/src/app/core/services/operations.service.ts`, related specs | Stage 0 contract; SyncServer schema names | Draft lines can carry inline item payload; create/update payload sends `temporary_item`; no direct catalog write |
| 1C | Catalog lookup for inline modal | `Warehouse_frontend` catalog lookup/service/tests | `Warehouse_frontend/src/app/core/services/catalog-search.service.ts` or a new feature-local lookup service, related specs | Existing BFF `/catalog/search/categories`, `/catalog/units` | Searchable category and unit selectors for the inline modal, usable by storekeeper/chief/root |
| 1D | Django BFF pass-through / boundary tests | `Warehouse_web` BFF tests, optional small view fixes only if needed | `Warehouse_web/apps/bff_api/tests.py`, optional `operations_views.py` only if pass-through currently strips fields | Existing BFF `/operations` proxy behavior | BFF forwards inline operation payload and never exposes SyncServer tokens |
| 2 | Inline modal UI component | `Warehouse_frontend` operations components | New component files under `features/operations/components/`, optional component specs | Stage 1B/1C interfaces | Second modal matching screenshot and alignment rules; emits inline item payload to parent |
| 3 | Parent integration | Parent/orchestrator | `operation-create-modal.component.ts`, `operations-page.component.ts` only for final wiring/merge behavior | Completed Stage 1 and 2 outputs | Button enabled; created inline item appears in operation lines and local operation-search results immediately |
| 4 | Verification / QA evidence | Parent/orchestrator + QA | Test files only for fixes; TZ checklist updates after evidence | Completed implementation | Static/unit/integration/stand/UI/user/regression evidence table |

### Integration checkpoints

1. Before Stage 1 starts, executor confirms that the UX label may remain `Создать ТМЦ`, but the product meaning is: **create an inline draft position for this operation**.
2. No Stage 1 parallel unit may edit `operation-create-modal.component.ts`; it is owned only by Stage 3 integration.
3. Stage 3 must verify both flows:
   - new unsaved operation with inline line → save/submit;
   - existing saved draft with inline line → reopen/edit/save/submit.
4. If `PATCH /operations/{id}` inline-line support is not implemented, final acceptance must stay unchecked because saved-draft editing would lose or reject inline lines.

## Execution Checklist

- [x] 0. Context verified — stand health OK, contracts inspected
- [x] 1. Architecture boundaries confirmed — same-origin BFF, no direct SyncServer calls
- [x] 2. Implementation stage 1A complete — SyncServer draft inline-line contract (already implemented and passing tests)
- [x] 3. Implementation stage 1B complete — Angular VM and payload mapping (already implemented)
- [x] 4. Implementation stage 1C complete — category/unit lookup for inline modal (already implemented)
- [x] 5. Implementation stage 1D complete — Django BFF pass-through/boundary tests (already implemented)
- [x] 6. Implementation stage 2 complete — second modal UI component (already implemented)
- [x] 7. Implementation stage 3 complete — parent integration and local search result injection
- [x] 8. Unit/component tests complete — SyncServer 19 tests passed, Django BFF 44 tests passed, Angular build success
- [x] 9. Integration tests with real dependencies complete — DB-backed PATCH/submit tests verified
- [x] 10. Stand smoke tests complete — Docker stand healthy, modal opens, inline line added
- [x] 11. UI automation tests complete — Playwright verified create/save/reopen/submit flow
- [x] 12. User scenario tests complete — full flow: create inline line → save draft → reopen → submit → catalog item created with review flags
- [x] 13. Regression checks complete — existing operation create/search/catalog item lines preserved
- [x] 14. Documentation updated — no new docs needed (existing TZ serves as spec)
- [x] 15. Final acceptance review complete — accepted 2026-06-10

## Check Rules

- Architect creates this checklist and acceptance criteria.
- Executor agents may check implementation and test items only after implementation and required verification are complete.
- QA verifier may check final acceptance only after reviewing evidence.
- If a check is skipped, unavailable, or failed, it must stay unchecked with a reason in the executor report and, when useful, in this TZ.
- If the real stand is unavailable, leave affected checks unchecked with blocker note: `стенд недоступен`.

---

## 1. User Request And Clarified Meaning

### Original UI request

In the operation creation modal, enable button `Создать ТМЦ` and open a second modal like the provided screenshot:

- second modal appears from the operation modal;
- top and bottom edges of both modal windows must be aligned;
- fields: name, SKU/article, unit, category, description;
- category and unit searches must work;
- created TMC must immediately be visible in operation-window search results.

### Clarification that changes the implementation meaning

The button must **not** create a catalog item immediately.

Target meaning:

```text
Click `Создать ТМЦ`
  -> fill second modal
  -> add an inline position to the current operation draft
  -> save/submit operation through /operations
  -> SyncServer creates a permanent catalog Item only at operation submit
     with requires_review=true and review_status="needs_review"
```

The technical payload field may remain `temporary_item` because this is the current SyncServer API contract, but UI text and implementation reports must call it **inline ТМЦ / inline-позиция**, not a new temporary-item concept.

---

## 2. Canonical Requirements Alignment

### Functional requirements

`Functional and WorkLogik.md`:

- section II.5: operation fields include a TMC table with cached search, selected warehouse quantity, and category;
- section II.6: draft does not change balances, submit/confirmation is where business rules are applied;
- section IV, lines 71 and 78-80: new operations must not create records in the legacy temporary table; inline items materialize as permanent catalog TMC with `requires_review=true` and `review_status="needs_review"` at submit;
- section IV, lines 88-89: temporary TMC concept is deprecated for new operations; legacy tables/API remain only for compatibility.

### ADR alignment

`docs/adr/0012-deprecate-temporary-items-review-flow.md` is accepted and requires:

- create draft stores inline payload only in snapshots / `temporary_draft_payload`;
- submit creates a permanent catalog `Item` directly;
- created item has review flags;
- legacy `/temporary-items/*` endpoints stay only for old data.

### Existing implementation facts to preserve

- `SyncServer/app/schemas/operation.py` already supports `OperationLineCreate.temporary_item` for create.
- `SyncServer/app/schemas/temporary_item.py` defines `TemporaryItemInlineCreate` fields:
  - `client_key`, `name`, `sku`, `unit_id`, `category_id`, `description`, `hashtags`.
- `SyncServer/app/services/operations_service.py` already materializes `temporary_draft_payload` at submit into a permanent `Item` with `requires_review=True`, `review_status="needs_review"`, `source_system="operation_inline"`.
- `PATCH /api/v1/operations/{id}` currently rejects `temporary_item` lines; this must be fixed for saved draft reopen/edit flows.
- `Warehouse_web/apps/bff_api/operations_views.py` currently forwards operation payloads via `OperationsAPI`; BFF should remain a pass-through boundary, not a domain owner.

---

## 3. Architecture Boundaries

### Must keep

- Browser/Angular calls Django same-origin BFF only.
- Angular must not call SyncServer `/api/v1/*` directly.
- Angular must not call `/bff/api/v1/catalog/admin/items` from this button.
- Angular must not receive/store SyncServer user/device tokens.
- Django must not create local catalog/domain ORM data; all warehouse domain writes go through SyncServer.
- SyncServer remains the source of truth for operation submit and catalog item materialization.

### Runtime path

```text
Browser /operations/
  -> Django authenticated shell
  -> Angular operation modal
  -> Django BFF /bff/api/v1/operations
  -> Warehouse_web sync_client
  -> SyncServer /api/v1/operations
  -> SyncServer operations service
  -> PostgreSQL
```

### Explicitly forbidden for this task

- Do not create the permanent catalog item when the second modal closes.
- Do not use catalog admin create endpoints as the button action.
- Do not resurrect legacy `TemporaryItem` records for new operations.
- Do not bypass operation draft/submit lifecycle.
- Do not introduce direct DB access from Django or Angular.

---

## 4. Current Code Areas To Inspect Before Edits

### Frontend

- `Warehouse_frontend/src/app/features/operations/components/operation-create-modal/operation-create-modal.component.ts`
  - current disabled button `Создать ТМЦ` in the add-TMC row;
  - current `onNewItemSelected(item)` behavior for catalog items;
  - current modal sizing/layout CSS.
- `Warehouse_frontend/src/app/features/operations/components/item-cache-search/item-cache-search.component.ts`
  - catalog item search dropdown used by the operation modal.
- `Warehouse_frontend/src/app/features/operations/components/operation-create-modal/operation-lines-table.component.ts`
  - line display/edit/delete behavior.
- `Warehouse_frontend/src/app/features/operations/pages/operations-page/operations-page.component.ts`
  - save/submit orchestration and `mergeDraftAfterSuccessfulSave`.
- `Warehouse_frontend/src/app/core/models/operations.models.ts`
  - `OperationDraftVm`, `OperationLineDraftVm`, existing `TemporaryItemDraftVm`.
- `Warehouse_frontend/src/app/core/services/operations.service.ts`
  - `buildPayload`, `mapDtoToDraftVm`, create/update/submit flows.
- `Warehouse_frontend/src/app/core/services/catalog-search.service.ts`
  - item and category search; add/reuse unit lookup here or via feature-local lookup service.

### Django BFF

- `Warehouse_web/apps/bff_api/operations_views.py`
- `Warehouse_web/apps/bff_api/catalog_views.py`
- `Warehouse_web/apps/bff_api/urls.py`
- `Warehouse_web/apps/bff_api/tests.py`
- `Warehouse_web/apps/sync_client/operations_api.py`

### SyncServer

- `SyncServer/app/schemas/operation.py`
- `SyncServer/app/schemas/temporary_item.py`
- `SyncServer/app/services/operations_service.py`
- `SyncServer/app/services/operations_policy.py`
- Existing tests:
  - `SyncServer/tests/test_temporary_items_phase1.py`
  - `SyncServer/tests/test_operations_service_inventory_subject_write_path.py`

---

## 5. Target UX Specification

### 5.1 Button behavior

- The existing button text may remain `Создать ТМЦ`.
- The button is enabled only when the main operation modal is in a flow where manual TMC addition is allowed.
- The button stays hidden/disabled for object-source locked flows where additional positions are currently forbidden.
- On click, show a second modal next to the main operation modal.

### 5.2 Second modal copy

Recommended title: `Создание ТМЦ`.

Required helper text in the modal body or near submit button:

> Позиция будет добавлена в черновик операции. Постоянная ТМЦ появится в справочнике после подтверждения операции.

Do not display copy that promises immediate catalog creation.

### 5.3 Second modal fields

| Field | Required | Source / behavior | Payload |
|---|---:|---|---|
| `Название` | yes | text input, trim, 1-255 chars | `temporary_item.name` |
| `SKU / артикул` | no | text input, blank -> `null` | `temporary_item.sku` |
| `Ед. изм.` | yes | searchable combobox by unit name/symbol | `temporary_item.unit_id` |
| `Категория` | no | searchable combobox by category name/path | `temporary_item.category_id` or `null` |
| `Описание` | no | textarea, blank -> `null` | `temporary_item.description` |

Notes:

- Category is optional because SyncServer can resolve `None` to system uncategorized category.
- Unit is required because SyncServer requires `unit_id`.
- If executor adds optional hashtags later, they must map to `temporary_item.hashtags`, but hashtags are not required by this TZ and should not distort the screenshot layout.

### 5.4 Category and unit search

- Category search must use Django BFF only, preferably existing `GET /bff/api/v1/catalog/search/categories?q=...&limit=...`.
- Unit search must use Django BFF only:
  - preferred minimal implementation: lazy-load active units via `GET /bff/api/v1/catalog/units?limit=1000` and filter client-side by `name` and `symbol`;
  - add a new BFF `catalog/search/units` endpoint only if client-side filtering is insufficient, and document why.
- Storekeeper users must be able to search/select units/categories needed for operation inline lines; do not require catalog-admin permissions for lookup.

### 5.5 Modal alignment and sizing

When both modals are open:

- top edges of main operation modal and second inline-TMC modal must align within `±4px` on FHD viewport;
- bottom edges must align within `±4px`;
- both modals must follow the existing operations-modal host behavior and SPA architecture: do not add a second topbar/sidebar, do not replace the Django shell, and do not introduce a new full-app overlay convention unless the current modal system already uses it;
- both modals use matching header/body/footer structure:
  - fixed header;
  - scrollable body if needed;
  - fixed footer;
- if the second modal has less content, it still stretches to the same visual height as the operation modal rather than floating shorter;
- if viewport height is small, both modals use the same max-height rule and internal body scroll.

### 5.6 Create-and-add behavior

On `Создать и добавить`:

1. Validate second modal fields.
2. Generate a stable `client_key` for this inline item, e.g. `inline-<uuid-or-random>`.
3. Add a line to the current operation draft immediately:
   - `itemId: null`;
   - `itemName` from inline payload;
   - `sku`, `unitId`, `unitName`, `categoryName` filled from selections;
   - `quantity: null` so user must enter operation quantity;
   - `availableQuantity/sourceSiteQuantity: null` or `0` with UI copy `будет создана при подтверждении`, not a warehouse stock number;
   - `inlineItem` / equivalent payload attached to the line.
4. Close only the second modal; keep the main operation modal open.
5. The line appears in `Позиции` table immediately.
6. The main operation search dropdown can find this inline item locally by name/SKU while the current operation modal remains open.
7. Selecting that local inline search result should add another line referencing the same `client_key`, not create another distinct inline item, so SyncServer materializes one permanent item for grouped lines.

### 5.7 Save/submit behavior

- Saving a draft with inline lines must create/update an operation draft, not a catalog item.
- Submitting an operation with inline lines must materialize permanent catalog items through SyncServer existing submit flow.
- After submit:
  - operation lines reference the new catalog item IDs;
  - created items have `requires_review=true` and `review_status="needs_review"`;
  - `temporary_draft_payload` is cleared;
  - BFF item search by created name/SKU can find the permanent item via cache or remote fallback.

---

## 6. API And DTO Contract

### 6.1 Operation create/update payload

For catalog item lines:

```json
{
  "line_number": 1,
  "item_id": 123,
  "qty": "5"
}
```

For inline item lines:

```json
{
  "line_number": 2,
  "qty": "3",
  "temporary_item": {
    "client_key": "inline-abc123",
    "name": "Новая позиция",
    "sku": "SKU-NEW",
    "unit_id": 1,
    "category_id": 10,
    "description": "Описание",
    "hashtags": null
  }
}
```

Create operation payload must include stable `client_request_id` when at least one line has `temporary_item`, because current `OperationCreate` validates it.

### 6.2 SyncServer required changes

Current create flow is acceptable. Required backend changes are for draft update/reopen:

1. `PATCH /api/v1/operations/{id}` must support `temporary_item` lines for draft operations.
2. The update path must recreate inline lines using the same rules as create:
   - validate unit exists;
   - resolve category or uncategorized;
   - store snapshots;
   - store `temporary_draft_payload`;
   - keep `item_id=None` and `inventory_subject_id=None` until submit.
3. Operation detail/list response for draft inline lines must expose a safe payload object sufficient for Angular to reopen and save the draft again, for example:

```json
{
  "is_draft_temporary": true,
  "temporary_draft_payload": {
    "client_key": "inline-abc123",
    "name": "Новая позиция",
    "sku": "SKU-NEW",
    "unit_id": 1,
    "category_id": 10,
    "description": "Описание",
    "hashtags": []
  }
}
```

Alternative field name is acceptable if documented and mapped in Angular, but it must not expose secrets or internal tokens.

### 6.3 Angular VM required changes

Extend `OperationLineDraftVm` with an explicit inline item payload, for example:

```ts
interface OperationInlineItemDraftVm {
  clientKey: string;
  name: string;
  sku: string | null;
  unitId: string;
  unitName: string;
  categoryId: string | null;
  categoryName?: string | null;
  description?: string | null;
  hashtags?: string[] | null;
}
```

Rules:

- Existing catalog lines use `itemId` and no inline payload.
- Inline lines use `itemId=null` and inline payload.
- Do not rely only on `isTemporary` for product semantics; keep it only for compatibility if existing UI/tests need it.
- `buildPayload()` must include lines where `(itemId || inlineItem)` and positive quantity.
- `saveDisabledReason()` must accept inline lines as valid nomenclature if required inline fields and quantity are present.
- `mapDtoToDraftVm()` must restore inline payload from server detail responses.

---

## 7. Implementation Stages And Acceptance Criteria

### Stage 1A — SyncServer draft inline-line contract

Acceptance criteria:

- `POST /api/v1/operations` with `temporary_item` remains supported and unchanged except tests may be updated for naming clarity.
- `PATCH /api/v1/operations/{id}` accepts `temporary_item` lines for draft operations.
- PATCH rejects inline lines for non-draft operations via existing workflow policy.
- Operation detail response includes safe inline payload for `is_draft_temporary` lines.
- Submit materializes inline lines into permanent catalog items with review flags and clears draft payload.
- No new legacy `TemporaryItem` rows are created for new operations.

Suggested tests:

- create draft with inline line, assert no `Item.requires_review` before submit;
- patch same draft replacing/adding inline line, assert payload persists;
- reopen detail, assert safe inline payload is present;
- submit, assert one permanent item is created, operation line references it, payload cleared;
- patch submitted operation with inline line returns conflict/forbidden according to current workflow.

### Stage 1B — Angular VM and payload mapping

Acceptance criteria:

- Angular draft line VM can represent catalog lines and inline lines.
- `buildPayload()` sends `temporary_item` for inline lines and `item_id` for catalog lines.
- `client_request_id` is generated and stable for create payloads that contain inline lines.
- `mapDtoToDraftVm()` restores inline lines from server responses.
- `mergeDraftAfterSuccessfulSave()` preserves inline payload/client keys after save.
- Save/submit validation treats inline lines as valid when name, unit, and quantity are present.
- No browser request to `/catalog/admin/items` is introduced.

### Stage 1C — Category/unit lookup

Acceptance criteria:

- Category selector supports typed search and selection through BFF.
- Unit selector supports typed search by unit name and symbol through BFF/read data.
- Empty category is allowed and maps to `category_id: null`.
- Unit is required and validation error is clear.
- Lookup errors are shown inside the second modal without closing the main operation modal.

### Stage 1D — Django BFF boundary tests

Acceptance criteria:

- BFF operation create/update endpoints forward payloads containing `temporary_item` unchanged.
- BFF tests cover storekeeper/chief/root allowed operation write path and observer forbidden path where relevant.
- BFF catalog lookup for categories/units remains same-origin and does not require catalog-admin create permission.
- No SyncServer token is returned in BFF responses.

### Stage 2 — Second modal UI component

Acceptance criteria:

- New component is feature-local and does not redraw global shell.
- UI matches requested fields and button labels:
  - `Отмена`;
  - `Создать и добавить`.
- Form validation blocks submit until required fields are valid.
- Modal alignment acceptance is testable via CSS/bounding boxes.
- Component emits a typed inline item payload; it does not perform operation save or catalog writes itself.

### Stage 3 — Parent integration

Acceptance criteria:

- Main `Создать ТМЦ` button opens second modal.
- Creating inline item adds a line to the operation table immediately.
- Main operation search dropdown includes current draft inline items locally.
- Selecting local inline search result adds a line with same `client_key`.
- Save draft, reopen draft, edit quantity, save again works.
- Submit operation with inline item works and closes modal according to existing submit behavior.

---

## 8. Required Test Ladder

| Level | Required checks | Commands / tools | Applicability |
|---|---|---|---|
| Static checks | Python/TypeScript syntax, Angular build | `python -m pytest --collect-only` where useful, `npm run build` | Required because runtime contracts and UI are touched |
| Unit tests | SyncServer service/schema tests; Angular mapper/service tests | `python -m pytest <focused tests>`, Angular component/service specs | Required |
| Component tests | Angular second modal validation and emit behavior | `npm test -- --watch=false` or project-approved equivalent | Required if Angular test tooling is available; otherwise leave unchecked with blocker |
| Integration tests | SyncServer API create/patch/submit with DB-backed test session; Django BFF pass-through tests | `python -m pytest`, `python manage.py test apps.bff_api` | Required |
| Real stand smoke | Docker stand with SyncServer, Django, PostgreSQL, Angular | health checks + browser/API smoke | Required |
| UI automation | Playwright through Django-hosted `/operations/` | `npx playwright test ...` or Playwright tool | Required because UI modal behavior and alignment are touched |
| User scenarios | Full flow: create inline line, save draft, reopen, submit, search created permanent item | Playwright + BFF/API verification | Required |
| Regression pack | Existing operation modal create/search/catalog item lines, no direct SyncServer calls, no catalog admin create button call | Existing focused tests + network inspection | Required |
| Acceptance review | Evidence table and final checklist | QA review | Required |

### Minimum focused commands

Run from the relevant project directories unless stated otherwise:

```bash
# SyncServer
python -m pytest tests/test_temporary_items_phase1.py tests/test_operations_service_inventory_subject_write_path.py

# Warehouse_web
python manage.py test apps.bff_api

# Warehouse_frontend
npm run build
```

If frontend test specs are added, also run the smallest non-interactive frontend test command available in the project. Do not use watch mode without `--watch=false`.

---

## 9. Real Test Stand Requirements

Use the documented Docker stand from workspace root `/home/makc/AI_sandbox/warehouse_solution`.

### Services

| Service | Address | Health Check | Container |
|---|---|---|---|
| SyncServer API | `http://localhost:8000` | `GET /api/v1/health` | `warehouse_syncserver` |
| Django / BFF | `http://localhost:8001` | `GET /healthz/` | `warehouse_web` |
| PostgreSQL | `localhost:5432` | `pg_isready -h localhost -p 5432 -t 3` | `warehouse_postgres` |
| Angular | `http://localhost:4200` | `GET /` | `warehouse_angular` |

### Environment variable names only

- `DJANGO_ENV`
- `SYNC_SERVER_URL`
- `SYNC_ROOT_USER_TOKEN`
- `SYNC_DEVICE_TOKEN`
- `DATABASE_URL`
- `DJANGO_SETTINGS_MODULE`
- `SECRET_KEY`

### Seed data

Required stand data:

- at least one storekeeper/chief/root user with valid Django session binding;
- at least one active site available for operation;
- at least one active unit, e.g. `шт`;
- at least one active category or ability to leave category blank and use uncategorized;
- existing catalog item for regression search/add check.

### Smoke scenario

1. Open Django-hosted `/operations/`.
2. Open `Новая операция`.
3. Click `Создать ТМЦ`.
4. Verify second modal opens and top/bottom edges align with the main modal.
5. Search/select unit and category.
6. Create inline item and add it to positions.
7. Enter quantity and save draft.
8. Reopen the draft and verify inline line is still present.
9. Submit the draft as an allowed role.
10. Search catalog/BFF for created name or SKU and verify the permanent item is visible with review state.

### Reset / cleanup

- Prefer unique test names/SKUs such as `INLINE-E2E-<timestamp>`.
- If cleanup is needed, use approved application APIs only.
- Do not run destructive DB commands (`DROP`, broad `DELETE`, `TRUNCATE`) without explicit user approval.

---

## 10. Regression Risks

| Risk | Mitigation |
|---|---|
| Frontend accidentally calls catalog admin create endpoint | Add test/network check that `Создать ТМЦ` does not request `/catalog/admin/items` |
| Saved draft with inline line cannot be reopened/updated | Implement SyncServer PATCH support and safe response payload; add tests |
| UI revives “temporary TMC” wording | Use inline/review wording in UI; keep `temporary_item` only as API field name |
| Existing catalog item search breaks | Keep `ItemCacheSearchComponent` behavior and add regression test for normal catalog item line |
| Unit/category selectors require catalog-admin permissions | Use read/search BFF endpoints available to operation users |
| Modal alignment differs from screenshot | Playwright bounding-box assertion within ±4px |
| Duplicate inline item creates multiple permanent Items | Reuse same `client_key` for local inline search result selections; backend groups by `client_key` |

---

## 11. Evidence Table Template For Executors

Completion report must include:

```markdown
## Evidence

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|
| SyncServer unit/integration | `<command>` | pass/fail/skipped | log path or note |
| Django BFF tests | `<command>` | pass/fail/skipped | log path or note |
| Frontend build/tests | `<command>` | pass/fail/skipped | log path or note |
| Stand smoke | `<command/tool>` | pass/fail/skipped | URL/log/screenshot |
| UI automation | Playwright | pass/fail/skipped | report/screenshot |
| User scenario | Playwright + BFF/API | pass/fail/skipped | created operation/item identifiers |
| Regression | `<command/tool>` | pass/fail/skipped | note |
```

---

## 12. Final Acceptance Criteria

Final acceptance is complete only when all are true:

- The button `Создать ТМЦ` opens the second modal.
- The second modal creates an inline operation line, not an immediate catalog item.
- The line is visible in the operation positions table immediately.
- The inline line is searchable locally in the operation modal by name/SKU during the current draft session.
- Category and unit searches work through Django BFF/read endpoints.
- Saving and reopening a draft preserves inline lines.
- Submitting materializes permanent catalog items with review flags in SyncServer.
- Created permanent item becomes visible in BFF catalog search after submit.
- Modal top/bottom alignment passes UI automation or documented screenshot/bounding-box evidence.
- No direct browser call to SyncServer or catalog admin item creation endpoint was introduced.
- Runtime checks include unit/component, integration, real stand smoke, UI automation, user scenario, and regression evidence.
