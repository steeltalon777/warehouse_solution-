# TZ: Operations Create Modal Cached Search

## Execution Strategy

- [ ] 🟢 Parallel execution recommended
- **Reason:** Django BFF/cache search and Angular modal UX can be implemented in parallel after fixing the shared DTO contract below. They touch different projects and different writable files; integration is needed only after both units are complete.

### Parallel work units

| Unit | Owner area | Writable files/areas | Required input | Output/evidence |
|---|---|---|---|---|
| A. Django BFF cached search | `Warehouse_web` | `apps/bff_api/catalog_views.py`, `apps/catalog_cache/services.py`, optional `apps/sync_client/balances_api.py`, tests in `apps/bff_api/tests.py`, `apps/catalog_cache/tests.py`, optional `apps/operations/tests.py` | DTO contract in this TZ; existing SyncServer `/balances` filters | `/bff/api/v1/catalog/search/items` searches cache by SKU/name/hashtag and returns category plus source-site quantity hint |
| B. Angular modal UX | `Warehouse_frontend` | `src/app/features/operations/components/operation-create-modal/`, `src/app/features/operations/components/item-cache-search/`, `src/app/core/services/catalog-search.service.ts`, `src/app/core/models/operations.models.ts`, related specs/e2e | Same DTO contract; mocked BFF responses allowed until Unit A is merged | User adds operation rows from dynamic search; row format matches requested layout |

### Integration checkpoints

1. Unit A and Unit B confirm field names before coding beyond mocks.
2. Parent/orchestrator verifies Angular calls only Django BFF and never SyncServer directly.
3. After both units land, run Django tests, Angular build/component tests, then real-stand smoke/UI checks if stand is available.

## Execution Checklist

- [ ] 0. Context verified
- [ ] 1. Architecture boundaries confirmed
- [ ] 2. Implementation stage 1 complete — Django BFF/cache search contract
- [ ] 3. Implementation stage 2 complete — Angular modal search-and-lines UX
- [ ] 4. Unit/component tests complete
- [ ] 5. Integration tests with real dependencies complete
- [ ] 6. Stand smoke tests complete
- [ ] 7. UI automation tests complete
- [ ] 8. User scenario tests complete
- [ ] 9. Regression checks complete
- [ ] 10. Documentation updated
- [ ] 11. Final acceptance review complete

## Check Rules

- Architect creates this checklist and acceptance criteria.
- Executor agents may check implementation and test items only after running the required verification.
- QA verifier may check final acceptance only after reviewing evidence.
- If a check is skipped or unavailable, it must stay unchecked with a blocker note.
- If the real stand is unavailable, use blocker note: `стенд недоступен`.

---

## 1. User Request

Improve the operation creation modal. The modal already looks generally acceptable, but item rows must be added from dynamic Django-cache search:

- search is dynamic and uses Django cache;
- search works by SKU, item name, or hashtag;
- search result shows category and quantity on the source warehouse of the operation;
- selecting a found ТМЦ adds a row with operation quantity input;
- operation row format should be approximately:

```text
[название] [категория] [количество для реализации] из (количество на складе источнике) [×]
```

---

## 2. Source Requirements And Alignment

### Canonical functional requirements

`Functional and WorkLogik.md`, section II.5.0:

- common operation fields include a ТМЦ table with search;
- search must show quantity on the selected warehouse and category;
- search must be cached;
- comment is a 2-row textarea.

`Functional and WorkLogik.md`, section II.8:

- storekeeper creates operation;
- adds ТМЦ lines one by one;
- frontend must use cache and search;
- SyncServer validates permissions at confirmation/submission.

`Functional and WorkLogik.md`, section VIII:

- operations are an Angular screen under `/operations/`;
- UI is FHD-oriented;
- modals/tables must scroll when they do not fit.

### Architecture requirements

- `SyncServer` is source of truth for catalog, balances, operations, and permissions.
- `Warehouse_web` may store only technical cache and BFF/UI support state.
- Angular/browser must call same-origin Django BFF only.
- Angular must not receive SyncServer tokens and must not call SyncServer directly.
- Django cache is a UX/search cache only; it is not authoritative for operation validation or balances.

---

## 3. Current State Discovered

### Angular

- Main files:
  - `Warehouse_frontend/src/app/features/operations/pages/operations-page/operations-page.component.ts`
  - `Warehouse_frontend/src/app/features/operations/components/operation-create-modal/operation-create-modal.component.ts`
  - `Warehouse_frontend/src/app/features/operations/components/item-cache-search/item-cache-search.component.ts`
  - `Warehouse_frontend/src/app/core/services/catalog-search.service.ts`
  - `Warehouse_frontend/src/app/core/services/operations.service.ts`
  - `Warehouse_frontend/src/app/core/models/operations.models.ts`
- `OperationCreateModalComponent` currently adds an empty row by `+ Добавить позицию`, then user selects item inside that row.
- Existing row table columns are `Номенклатура`, `Количество`, `Ед. изм.`, `Остаток`, delete button.
- `ItemCacheSearchComponent` calls `CatalogSearchService.searchItemsOnce(query)` but displays `catalogSearch.itemResults()`. Because `searchItemsOnce()` returns data without updating `itemResults()`, dropdown results may remain empty.
- `CatalogSearchItem` lacks hashtags and source-site balance fields.
- `OperationLineDraftVm` lacks `categoryName`, but requested row format needs category.
- `OperationsService.loadBalances(siteId)` exists separately, but search results do not show source-site quantity.

### Django BFF/cache

- Existing cached search endpoint:
  - `GET /bff/api/v1/catalog/search/items?q=...&limit=...`
  - `Warehouse_web/apps/bff_api/catalog_views.py::CatalogCachedItemSearchView`
- Existing cache lookup:
  - `Warehouse_web/apps/catalog_cache/services.py::CatalogLookupService.search_items()`
  - searches `sku`, `name`, and `search_text`;
  - `search_text` includes hashtags when cache was warmed with hashtag data;
  - query normalization strips leading `#` and supports keyboard-layout swap.
- `CatalogLookupService._serialize_item()` currently returns `id`, `name`, `sku`, `unit_symbol`, `category_name`, `hashtags`, `is_active`, but not `category_id`.
- `CatalogCachedItemSearchView._search_remote_items()` and `_warm_catalog_cache()` currently reference `request` outside method scope; executor must pass `request` explicitly.
- Existing BFF balances endpoint:
  - `GET /bff/api/v1/balances?site_id=...&item_id=...`
  - proxies SyncServer `/balances` through `Warehouse_web/apps/sync_client/balances_api.py`.

### SyncServer

- Existing balance API supports exact filters:
  - `GET /api/v1/balances?site_id=<id>&item_id=<id>`
  - access is checked against user identity and visible sites.
- Existing catalog read search `/catalog/read/items` searches name/SKU/description, not hashtags.
- Hashtag-first search for this TZ must therefore be satisfied by Django catalog cache, not browser-side filtering and not direct SyncServer calls.

---

## 4. Target UX

### Modal behavior

1. User selects operation type and relevant warehouse(s).
2. For operations with a source warehouse, item search is disabled until source warehouse is selected.
3. User types at least 2 characters in a search field.
4. Search is debounced and uses Django BFF cached search.
5. Search accepts SKU fragments, item name fragments, hashtag with `#`, and hashtag without `#`.
6. Each search option shows item name, SKU if present, category, and `на складе: <qty>` for the selected source warehouse.
7. Selecting a search result immediately adds a line to the operation; user should not need to add an empty line first.
8. Added line renders compactly as:

```text
[Название ТМЦ] [Категория] [quantity input] из (<source-site qty>) [×]
```

9. `×` removes only that line.
10. If the same item is selected again, preferred behavior is to focus/highlight the existing line instead of creating a duplicate. If duplicates remain allowed, executor must document why and tests must cover payload correctness.
11. Changing source warehouse refreshes source-site quantities for selected lines and invalidates stale search results.
12. If selected operation type does not consume source stock, the UI may show current balance at the relevant warehouse as informational only and must not block creation because of zero stock.

### Quantity hint site rules

| Operation type | Quantity hint site | Stock-blocking hint? |
|---|---|---|
| `MOVE` | `sourceSiteId` | warn/block submit when quantity exceeds source stock |
| `EXPENSE` | `sourceSiteId` | warn/block submit when quantity exceeds source stock |
| `WRITE_OFF` | `sourceSiteId` | warn/block submit when quantity exceeds source stock |
| `ISSUE` | `sourceSiteId` | warn/block submit when quantity exceeds source stock |
| `RECEIVE` | `destinationSiteId` if shown | informational only |
| `ISSUE_RETURN` | `destinationSiteId` if shown | informational only unless issued-assets flow later defines stricter rule |
| correction/adjustment | current existing behavior | do not expand scope; note current `CORRECTION` vs SyncServer `ADJUSTMENT` mismatch if encountered |

Final operation validity remains SyncServer-owned. Frontend stock checks are UX hints and must not replace server validation.

---

## 5. Browser-Facing BFF Contract

Extend the existing endpoint; do not create a direct browser-to-SyncServer path.

```http
GET /bff/api/v1/catalog/search/items?q=<query>&limit=20&source_site_id=<site_id>&include_balance=true
```

`source_site_id` and `include_balance` are optional to preserve existing callers.

Response envelope follows current BFF convention. `data.results` must use this stable shape:

```json
{
  "results": [
    {
      "id": "123",
      "name": "Кабель UTP Cat5e",
      "sku": "UTP-5E",
      "category_id": "7",
      "category_name": "Кабель",
      "unit_id": "2",
      "unit_name": "штука",
      "unit_symbol": "шт",
      "hashtags": ["кабель", "utp", "cat5e"],
      "is_active": true,
      "requires_review": false,
      "source": "cache",
      "source_site_id": "5",
      "source_site_qty": "15",
      "balance_qty": "15"
    }
  ]
}
```

Field rules:

- `id`, `name`, `category_name`, `unit_symbol`, `is_active`, `source` are required for active results.
- `category_id`, `unit_id`, `unit_name`, `sku`, `hashtags` may be empty only when upstream/cache lacks them, but tests must cover normal non-empty category and hashtags.
- `source_site_qty`/`balance_qty` are strings to avoid decimal formatting drift; Angular may parse them for comparisons.
- Missing balance row is represented as `"0"`, not as an omitted field, when `include_balance=true` and `source_site_id` is valid.
- If balance lookup is forbidden for `source_site_id`, return a controlled BFF error or omit balance for all rows with a clear error state; do not leak SyncServer tokens or raw tracebacks.

---

## 6. Implementation Stages

### Stage 0 — Context verification

Executor must re-read before code changes:

- `Functional and WorkLogik.md`, sections II.5, II.8, VIII;
- `Warehouse_frontend/docs/ARCHITECTURE_FRONTEND_SPA.md`, sections BFF-only data and modal/content mount contract;
- `Warehouse_web/AGENTS.md` and `Warehouse_frontend/AGENTS.md`.

Acceptance criteria:

- Completion report states that the work aligns with cached search, source-site quantity, and BFF-only browser access.
- Executor records any discovered mismatch, especially Angular `CORRECTION` vs SyncServer `ADJUSTMENT`, without silently expanding scope.

### Stage 1A — Django BFF/cache search contract

Required backend behavior:

1. Keep using `GET /bff/api/v1/catalog/search/items`.
2. Parse optional `source_site_id` and `include_balance`.
3. Fix `request` scope bug in `CatalogCachedItemSearchView._search_remote_items()` and `_warm_catalog_cache()`.
4. Preserve cache-first behavior:
   - local cache lookup first;
   - remote fallback only if cache has fewer than requested limit;
   - remote results may warm cache;
   - local cache remains UX cache, not domain truth.
5. Ensure local cache results include `category_id`, `category_name`, `hashtags`, `unit_symbol`, and stable string `id`.
6. Ensure hashtag search works from cache with both `#tag` and `tag`.
7. Enrich results with source-site quantity when requested:
   - use `BalancesAPI`/SyncServer through `apps/sync_client`, not local Django domain tables;
   - for current SyncServer API, exact per-item lookup with `site_id` + `item_id` is acceptable for `limit <= 20`;
   - do not persist balances in Django cache;
   - treat balance as display hint only.
8. Keep existing callers working when `source_site_id` is absent.

Suggested backend tests:

- `Warehouse_web/apps/catalog_cache/tests.py`
  - cache serializer returns `category_id` and `hashtags`;
  - search finds item by SKU;
  - search finds item by name;
  - search finds item by `#hashtag` and by `hashtag`.
- `Warehouse_web/apps/bff_api/tests.py`
  - cache-hit response shape includes category and hashtags;
  - `source_site_id` + `include_balance=true` adds `source_site_qty`/`balance_qty`;
  - remote fallback still works and no longer crashes because of missing `request`;
  - unauthenticated request is rejected by existing login/BFF behavior.

Acceptance criteria:

- A cache-hit search for a hashtag returns the item without requiring remote SyncServer catalog search.
- A cache-hit search with `source_site_id` returns source-site quantity from SyncServer balances.
- No browser-visible response includes SyncServer tokens.

### Stage 1B — Angular modal search-and-lines UX

Required frontend behavior:

1. Extend `CatalogSearchItem` with category, hashtags, and source-site quantity fields from the contract.
2. Update `CatalogSearchService` so search supports parameters:
   - `source_site_id`;
   - `include_balance=true`;
   - `limit`.
3. Fix result handling in `ItemCacheSearchComponent`:
   - either use returned `searchItemsOnce()` results in a local signal;
   - or make service search update `itemResults()` consistently.
4. Add input(s) to `ItemCacheSearchComponent` for source-site context and disabled/placeholder state.
5. Search result dropdown must show name, SKU, category, and source-site quantity.
6. Modify `OperationCreateModalComponent` so item selection adds a full line directly from search.
7. Extend `OperationLineDraftVm` or an operation-line view model with:
   - `categoryId`/`categoryName`;
   - `sourceSiteQuantity` or equivalent;
   - existing `availableQuantity` may be reused if naming remains clear.
8. Render operation line in the requested compact format:

```text
[itemName] [categoryName] [quantity input] из (sourceSiteQuantity) [remove button]
```

9. Quantity input must remain editable after row addition.
10. Remove button must be a clear `×`/cross action and remove only the selected row.
11. Changing source site refreshes selected-line quantities and search context.
12. Payload must still send only operation domain fields needed by SyncServer: item id and quantity; display-only category/stock must not be sent as authoritative operation data.

Suggested frontend tests:

- `operation-create-modal.component.spec.ts`
  - selecting search result adds one line with item name/category/source quantity;
  - quantity input updates draft;
  - cross removes only that line;
  - source site change refreshes or clears stale quantity hints;
  - stock-exceeding quantity blocks/warns only for stock-consuming operation types.
- `item-cache-search.component.spec.ts`
  - debounced search starts at 2 characters;
  - search by `#tag` is passed to service unchanged;
  - dropdown renders category and stock;
  - selection emits the full item DTO;
  - no-result and loading states render.
- `catalog-search.service.spec.ts` or extension of existing service tests:
  - request params include `source_site_id` and `include_balance=true` when provided;
  - response maps optional stock fields safely.

Acceptance criteria:

- User can create a draft line without pressing `+ Добавить позицию` first.
- Search-by-SKU, search-by-name, and search-by-hashtag are supported through BFF.
- Added line visually contains item name, category, quantity input, source-site stock, and cross remove action.
- Angular source contains no SyncServer URL or token usage.

### Stage 2 — Integration and regression

Integration tasks:

1. Verify `/operations/` still opens inside Django shell with topbar/sidebar visible.
2. Verify search request path is same-origin `/bff/api/v1/catalog/search/items`.
3. Verify operation create/update payload still matches existing BFF `/operations` contract.
4. Verify existing operations list, submit/cancel, and balances screens are not regressed.
5. If SSR operation form remains in use, do not break `/operations/ssr/` item search; align only if touched.

Acceptance criteria:

- Operation draft can be saved with a searched ТМЦ line.
- Submit path still relies on SyncServer validation.
- Existing operations table reloads after create/save as before.

---

## 7. Out Of Scope

- Redesigning the full operation lifecycle.
- Adding new operation types.
- Solving Angular `CORRECTION` vs SyncServer `ADJUSTMENT` unless it directly blocks this modal; if it blocks, stop and create a separate follow-up or ask for scope decision.
- Changing SyncServer business validation for balances/permissions.
- Persisting balances in Django cache.
- Moving Django sidebar/topbar into Angular.
- Direct browser calls to SyncServer.
- Rebuilding SSR operation form except for non-breaking shared-search regression fixes.

---

## 8. Test Strategy

### Static checks

- `Warehouse_web`: import checks through Django tests; optional formatter/linter only if project has configured command.
- `Warehouse_frontend`: `npm run build`.
- If SyncServer is not changed, no SyncServer static check is required for this TZ.

### Unit tests

- Django cache lookup and BFF response-shape tests listed in Stage 1A.
- Angular service/component unit tests listed in Stage 1B.

### Component tests

- Angular modal/search component specs are required because the user request is UI behavior.
- Django view tests for BFF endpoint are required because browser contract changes.

### Integration tests with real dependencies

- Django tests must exercise BFF search with Django test DB `CatalogCacheItem` rows and mocked SyncServer balances client.
- If executor changes SyncServer API, run relevant SyncServer tests, at minimum:

```bash
python -m pytest tests/test_balances_endpoints.py tests/test_catalog_read_model.py
```

### Real stand smoke tests

Required because this changes runtime browser behavior.

Probe first:

```bash
curl -fsS http://localhost:8000/api/v1/health
curl -fsS http://localhost:8001/healthz/
curl -fsS http://localhost:4200/
pg_isready -h localhost -p 5432 -t 3
```

If unavailable, agents may start the stand with `make up` from the workspace root; if Makefile is unavailable, use `docker compose up -d`.

If the stand still cannot be started, report:

```text
Стенд не обнаружен. Запусти `make up` или `docker compose up -d` из `/home/makc/AI_sandbox/warehouse_solution/`.
```

### UI automation

Required because modal behavior changes.

- Preferred: add/update Playwright scenario under `Warehouse_frontend/e2e/`.
- Use existing config: `Warehouse_frontend/e2e/playwright.config.ts` with base URL `http://localhost:8001`.
- Scenario must cover opening `/operations/`, opening create modal, selecting source warehouse, searching by SKU/name/hashtag, adding a row, entering quantity, removing row.

### User scenario tests

At least one full scenario on real stand or documented QA stand:

1. Login as user with operation rights.
2. Open `/operations/`.
3. Open create operation modal.
4. Select source warehouse with known stock.
5. Search item by SKU; verify category and stock visible.
6. Add item; enter quantity; verify line format.
7. Remove line; add again by hashtag.
8. Save draft.
9. Reopen/inspect operation if existing UI supports it.

### Regression pack

- Existing operations list loads.
- Existing operation submit/cancel controls still work as before.
- Existing balances endpoint/list remains usable.
- Existing nomenclature cached search consumers are not broken by optional fields.

---

## 9. Real Test Stand Definition

### Services

| Service | Address | Health check | Container |
|---|---|---|---|
| SyncServer API | `http://localhost:8000` | `GET /api/v1/health` | `warehouse_syncserver` |
| Django / BFF / shell | `http://localhost:8001` | `GET /healthz/` | `warehouse_web` |
| PostgreSQL | `localhost:5432` | `pg_isready -h localhost -p 5432 -t 3` | `warehouse_postgres` (`postgres:15-alpine`) |
| Angular | `http://localhost:4200` | `GET /` | `warehouse_angular` |

### Database lifecycle

- Use test/development PostgreSQL from the Docker stand at `localhost:5432`.
- Do not run destructive resets without explicit user approval and backup recommendation.
- Django catalog cache may be synced/warmed through existing approved cache sync flow.
- Balances remain SyncServer-owned and must come from SyncServer APIs.

### Seed data

Need at least:

- one user with operation rights for at least one source warehouse;
- one source warehouse with positive stock;
- one active item with:
  - SKU such as `UTP-5E`;
  - name such as `Кабель UTP Cat5e`;
  - category such as `Кабель`;
  - hashtags such as `кабель`, `utp`, `cat5e`;
  - positive balance on the source warehouse;
- one active item with zero/missing balance to test `0` display.

### Environment variable names only

- `DJANGO_ENV`
- `SYNC_SERVER_URL`
- `SYNC_ROOT_USER_TOKEN`
- `SYNC_DEVICE_TOKEN`
- `DATABASE_URL`
- `DJANGO_SETTINGS_MODULE`
- `SECRET_KEY`

### Reset/cleanup

- Remove only test-created operations/items through approved APIs/admin flows.
- Do not run broad `DELETE`, `TRUNCATE`, `docker compose down -v`, or destructive resets without explicit user approval.

---

## 10. Verification Commands

Run smallest useful checks first, then broader checks.

### Django/BFF

From `Warehouse_web/`:

```bash
python manage.py test apps.catalog_cache apps.bff_api apps.operations
python manage.py test
```

### Angular

From `Warehouse_frontend/`:

```bash
npm run build
CI=true npm test -- --watch=false
```

If the configured Angular test runner is unavailable, leave the unit/component checkbox unchecked and document the blocker instead of claiming success.

### Playwright UI

From `Warehouse_frontend/` after the stand is confirmed running:

```bash
npx playwright test --config=e2e/playwright.config.ts
```

If a narrower operations modal spec is added, executor may run only that spec first, then the relevant regression pack.

### Optional SyncServer

Only if executor changes SyncServer:

```bash
python -m pytest
```

For migrations, also run Alembic against a safe DB:

```bash
python -m alembic upgrade head
```

---

## 11. Acceptance Criteria

### Functional acceptance

- Search in the operation creation modal is dynamic and cache-backed through Django BFF.
- Search finds items by SKU, name, `#hashtag`, and hashtag without `#`.
- Search result shows category and source warehouse quantity.
- Selecting a result adds an operation row immediately.
- Row shows item name, category, quantity input, source stock, and cross remove action.
- Quantity remains editable after adding.
- Removing a line does not affect other lines.
- Changing source warehouse updates or clears stale stock hints.
- Saving operation sends item IDs and quantities; category/stock remain display hints only.

### Architecture acceptance

- Angular calls only `/bff/api/v1/*` same-origin endpoints.
- No SyncServer tokens are exposed to browser code, templates, logs, or tests.
- Django cache remains technical UX cache, not warehouse domain truth.
- SyncServer remains final authority for balances, permissions, and operation validation.

### Evidence table required in executor report

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|
| Django unit/component | `python manage.py test apps.catalog_cache apps.bff_api apps.operations` | pass/fail/skipped | log summary |
| Django regression | `python manage.py test` | pass/fail/skipped | log summary |
| Angular build | `npm run build` | pass/fail/skipped | log summary |
| Angular component tests | `CI=true npm test -- --watch=false` | pass/fail/skipped | log summary/blocker |
| Stand health | `curl -fsS .../health` | pass/fail/skipped | URLs/status |
| UI automation | `npx playwright test --config=e2e/playwright.config.ts` | pass/fail/skipped | report/screenshot path |
| User scenario | manual or Playwright | pass/fail/skipped | scenario notes |

---

## 12. Known Risks And Mitigations

| Risk | Mitigation |
|---|---|
| Django cache is stale | Treat search result as UX hint only; SyncServer validates operation on save/submit |
| Hashtag search does not work via remote fallback | Requirement is Django-cache search; tests must seed cache and verify cache-hit hashtag search |
| Balance enrichment creates many SyncServer calls | Limit results to 20, debounce frontend search, use exact `/balances?site_id&item_id`; add bulk endpoint only if performance evidence requires it |
| Existing `searchItemsOnce()` display bug hides results | Fix result state in `ItemCacheSearchComponent` or `CatalogSearchService` and cover with component test |
| Existing consumers of `/catalog/search/items` break | Keep new params optional and preserve old response fields |
| `CORRECTION` vs `ADJUSTMENT` mismatch appears while touching modal | Do not silently change operation semantics; document and ask/create follow-up if it blocks |
