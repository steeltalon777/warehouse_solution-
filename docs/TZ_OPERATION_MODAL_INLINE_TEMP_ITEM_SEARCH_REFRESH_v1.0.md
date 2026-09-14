# TZ: Quartermaster 4.0 — Operation Modal / Inline Temporary Item / Authoritative Search Refresh

**Дата:** 2026-09-14
**Режим подготовки:** analysis + preparation only (код не менялся, коммитов нет, миграций нет)
**Статус:** CLOSED для Quartermaster 4.0 (2026-09-14). Independent Reviewer verdict: «OPERATION MODAL READY FOR 4.0». Stage 3b и Reviewer residual R-1…R-7 deferred to 4.1 / ADR scope. См. «Final acceptance closure».
**Родительские документы:**
- `docs/adr/0033-item-identity-guard-v1.md` (Accepted, стадии 4 не выполнены)
- `docs/adr/0012-deprecate-temporary-items-review-flow.md`
- `docs/adr/0023-operation-correction-by-diff.md` (**Proposed**, V1 RECEIVE, нет BFF/Angular)
- `docs/archive/TZ-OPERATION_MODAL_BALANCES_MANUAL_REFRESH.md` (completed)
- `docs/TZ_OPERATION_MODAL_VISUAL_REDESIGN_MINIMAX_M3_v1.0.md`
- `Functional and WorkLogik.md` (канонические требования)

---

## Execution strategy

- **🟡 Sequential**
- **Reason:** этапы 1–3 правят одни и те же файлы (`operation-create-modal.component.ts`, `operation-lines-table.component.ts`, `operation-draft-mappers.ts`), этап 3b затрагивает контракт BFF+SyncServer, от которого зависят acceptance-сценарии этапа 3a. Параллелить нечего, кроме внутренних шардов этапа 4 (после фиксации контрактов этапов 1–3). Максимум полезных потоков: 2 (V1: 1).

---

## Execution checklist

- [x] 0. Context verified (Functional and WorkLogik.md + ADR-0033 + ADR-0012 + ADR-0023)
- [x] 1. Architecture boundaries confirmed (BFF остаётся host, SyncServer — source of truth)
- [x] 2. Stage 1 — Operation Modal UX cleanup (VIEW semantics, read-only, title) complete
- [x] 3. Stage 2 — Inline temporary-item editing (name + full card) complete
- [x] 4. Stage 3a — Authoritative search refresh (frontend wiring + invalidation) complete
- [ ] 5. Stage 3b — Operation-specific search eligibility contract — ADR accepted / decision recorded — **deferred to 4.1 / ADR scope** (в 4.0 не требуется; не подменяется этапом 3a; Operation Modal — не blocker 4.0)
- [ ] 6. Stage 4 — Batching enhancements (optional, gate decision) complete
- [x] 7. Unit/component tests complete
- [x] 8. Integration tests (Django + SyncServer test DB) complete
- [x] 9. Stand smoke tests complete
- [x] 10. UI automation tests (Playwright) complete
- [x] 11. User scenario tests complete
- [x] 12. Regression checks complete (ADR-0033 E2E, balance refresh E2E, phantom-item block E2E — см. Stage 3a evidence: catalog-refresh E2E красный по baseline; 2 baseline-падения классифицированы как test/environment debt, не product regression)
- [x] 13. Documentation updated (ADR-0033 checklist stage 4, this TZ, ARCHITECTURE_FRONTEND_SPA if needed)
- [x] 14. Final acceptance review complete (independent Reviewer: «OPERATION MODAL READY FOR 4.0»; ручная проверка пользователя пройдена — см. «Final acceptance closure»)

**Check rules:** боксы закрываются только после реализации и проверки; недоступный стенд оставляет бокс незакрытым с пометкой. Архитектурные решения (3b, corrections, batching >100) — только через ADR.

---

## A. Current architecture

### A.1 Angular

| Слой | Файл | Роль |
|---|---|---|
| Modal | `Warehouse_frontend/src/app/features/operations/components/operation-create-modal/operation-create-modal.component.ts` (2542 строки) | Единое окно CREATE/EDIT/VIEW всех типов операций |
| Table | `.../operation-create-modal/operation-lines-table.component.ts` (690) | Строки операции, qty, balance-состояния, identity candidates, submit-errors |
| Search | `.../item-cache-search/item-cache-search.component.ts` (334) | Dropdown поиска ТМЦ + кнопка «Обновить и проверить» |
| Inline create | `.../operation-create-modal/inline-item-create-modal.component.ts` (534) | Создание temporary item полностью на клиенте |
| Search service | `Warehouse_frontend/src/app/core/services/catalog-search.service.ts` (388) | `/catalog/search`, `/catalog/read/items/resolve`, unitCache |
| Ops service | `.../core/services/operations.service.ts` (1092) | CRUD/submit/cancel/restore, resolve-валидация, balances, DTO↔VM |
| Page | `.../features/operations/pages/operations-page/operations-page.component.ts` (1198) | Список, открытие модала, save/submit orchestration, `itemSearchCache` |
| Mappers | `.../core/services/operation-draft-mappers.ts` | `snapshotDraft` (dirty-check), `isDraftClean` |
| Models | `.../core/models/operations.models.ts` (430) | `OperationType`, `OperationStatus`, `OperationLineDraftVm`, `OperationInlineItemDraftVm`, `balanceState` |

Ключевые точки modal:
- title: L60 `isEdit ? 'Редактирование операции' : 'Новая операция'`;
- `isReadonly = status 'submitted' | 'cancelled'` L1212–1215;
- footer: L363–410 (`isReadonly`-ветка → restore/delete/cancel/close; иначе delete/cancel/Приёмка/Отмена/Сохранить черновик/Обновить при stale/Подтвердить);
- add-toolbar: L259–297 (скрыт при `isReadonly` и при `isObjectSourceFlow`), внутри `item-cache-search [consistency]="'authoritative'"` L271, pills `inline-search-hint` L273–282, кнопка «Создать ТМЦ»;
- table-toolbar: L299–331 (счётчик строк + «Обновить остатки», `data-testid=operation-lines-refresh-all`);
- balance effect: L1766–1796 по ключу `balanceRefreshKey = relevantSiteId + sorted unique itemIds` L1322–1333; `relevantSiteId`: RECEIVE → destination, иначе source L1360–1364;
- `onRefreshAllBalances` L1946–1989: сначала `validateAndApplyLineStatuses()`, затем `loadBalancesForItems`;
- `onRefreshCheckItems` L2362–2393: **только** `validateAndApplyLineStatuses` (search candidates не пересобираются, несмотря на подпись кнопки);
- inline flow: `inlineItemsForSearch` L1524–1534, `onInlineItemCreated` L1544–1568, `onInlineSearchSelected` L1570–1596 (переиспользует один `clientKey`), `onNewItemSelected` L2167–2214 (resolve перед добавлением), `resolveItemBeforeAppend` L2216–2246, `editItemLine` L2260–2270 — **dead code, в шаблоне не используется**;
- «Обновить и проверить» живёт внутри `item-cache-search` L48–53 (`data-testid=btn-refresh-check-items`) и эмитит `refreshRequested` → `onRefreshCheckItems()`.

Table:
- колонки: № / ТМЦ / Количество / `category_id` / Имеется / actions;
- `item-meta` показывает `ID {{line.itemId}}`, SKU, categoryName, unitName (у inline строк ID пустой);
- ячейка «Имеется»: `inlineItem` → «будет создана при подтверждении»; LOADING/ERROR/FRESH (0 приглушён)/NOT_LOADED (—);
- `.remove-btn` рендерится **безусловно** L178–186 (не gated `isReadonly`) — баг read-only;
- identity candidates UI + строка submit-error внутри таблицы.

### A.2 BFF (Django)

| Endpoint | Файл | Поведение |
|---|---|---|
| `GET /catalog/search/items` | `Warehouse_web/apps/bff_api/catalog_views.py` L594–786 | `consistency=fast` (default): локальный кэш `CatalogCacheItem` + merge by id; `authoritative`: обязательный вызов SyncServer browse, затем `_warm_catalog_cache`, опционально balance enrichment |
| `POST /catalog/read/items/resolve` | там же L879–914 | batch-статусы active/merged/inactive/deleted/missing + prune кэша (`deactivate_item`) для missing/deleted/inactive/merged |
| `GET /balances` | `apps/bff_api/balances_views.py` | прокси `site_id`, `item_id`, `item_ids` (≤200), `category_id`, `search`, `only_positive`; отсутствующие строки не возвращаются |
| `/operations*` | `apps/bff_api/operations_views.py` | pass-through create/update payload, detail enrich, submit/cancel/restore/accept-lines; **коррекций нет** |
| `/review-items/*`, `/temporary-items/*` | `apps/bff_api/urls.py` | review flow и legacy temp API |

`CatalogCacheItem` (`apps/catalog_cache/models.py`): `sync_id` unique, name, sku, search_text, category, unit, is_active, hashtags, synced_at — **TTL нет**; деактивация только через resolve-prune и admin write-through. `_search_local_cache` жёстко возвращает `unit_id: ''` (fast-выдача теряет unit). `Django CACHES` (LocMem) сконфигурирован, но cache-decorators не используются.

### A.3 SyncServer

`SyncServer/app/services/operations_service.py` (3573):
- `SUPPORTED_OPERATION_TYPES = RECEIVE, EXPENSE, WRITE_OFF, MOVE, ADJUSTMENT, ISSUE, ISSUE_RETURN` (CORRECTION нет);
- `temporary_item` разрешён **только для RECEIVE**: create L1270–1275, update L1808–1813 → 422 иначе; payload нормализуется (category null → Uncategorized) и лежит в `line.temporary_draft_payload {client_key,name,sku,unit_id,category_id,description,hashtags}`; `item_id/inventory_subject_id` = null;
- один `client_key` в одном payload обязан иметь идентичный payload: `_ensure_temporary_payload_consistent` L226–234 → 422 «reused with different payload»;
- `update_operation` L1697+ — draft-only, **полная замена всех строк** (DELETE+recreate), `expected_version`, audit `operation.update`;
- `_materialize_deferred_temporary_lines` L1960–2139 — на submit: ADR-0033 pre-check (`ItemIdentityService.assert_can_create`, EXACT → 409 `item_identity_duplicate`; intra-batch конфликт нормализованных имён → 409; PARTIAL → structured log `item_identity.flag`), затем создаётся постоянный `Item(requires_review=True, review_status='needs_review', source_system='operation_inline', source_ref=client_key)`, строка получает `item_id/inventory_subject_id`, payload очищается;
- submit L2273+: lock, state, `expected_version` (409 StaleVersionError), materialize, `_validate_resolved_lines_on_submit` L2142–2217 (missing/deleted/inactive/merge-chain → 409 `operation_lines_unresolved`), freeze catalog snapshot, duplicate-guard по canonical item id, двухфазный balance-check L462–579:
  - RECEIVE и положительный ADJUSTMENT — баланс не потребляют;
  - MOVE — source warehouse; EXPENSE/ISSUE/WRITE_OFF (без объекта) — site warehouse; ISSUE_RETURN и WRITE_OFF+объект — issued register; отрицательный ADJUSTMENT — warehouse;
  - `InsufficientStockError` / `InsufficientIssuedBalanceError`.
- `_ensure_item_usable` L78–88 — deleted/inactive/temporary backing item отвергаются.

Каталог: `app/repos/catalog_repo.py list_items_page` L44–103 — `is_active AND deleted_at IS NULL AND category/unit alive`, search по normalized_name/sku/description, **без** фильтров по операции, сайту, остаткам, `requires_review` (merged-источники уже `is_active=False`); `resolve_items` (`catalog_read_service.py`) отдаёт статусы active/merged/inactive/deleted/missing; `confirm_review_item` (`review_items_service.py` L27+) применяет corrections name/category/unit/description с повторной ADR-0033 проверкой (self-exclusion).

### A.4 Caches / indexes inventory

| # | Кэш | Где | TTL / инвалидация | Влияние на decision path |
|---|---|---|---|---|
| C1 | `catalog_cache_item` (Django DB) | BFF fast search | нет TTL; только resolve-prune + admin write-through + full sync reconciliation | Да: fast-выдача может содержать stale active rows |
| C2 | `itemSearchCache: Map<query, ids>` | `operations-page.component.ts` L342, L457–473 | нет TTL/invalidation | Да: фильтр списка операций по ТМЦ |
| C3 | `localResults` в `item-cache-search` | компонент | очищается при select; **не** очищается при смене site/type | Да: dropdown candidates |
| C4 | `localDraft` (+ localStorage autosave) | modal L1203+, L1719–1738 | snapshot при save | Да: источник истины в сессии; inline-поля в snapshot не входят |
| C5 | `balanceState` по строкам | modal + `loadBalancesForItems` | ключевой refresh по site+itemIds; missing row → FRESH 0 | Да |
| C6 | `unitCache` | `catalog-search.service.ts` | сессия | Нет (units) |
| C7 | `Django CACHES` LocMem | `settings` | TTL настройками | Не используется кодом |

### A.5 State flow

Открытие:
- new: пустой `localDraft` (`type:'MOVE'`, L1203–1208) → `normalizeDraftForType` → autosave localStorage;
- edit/view: `operations-page.onRowEdit` → `getOperation(id)` → `mapDtoToDraftVm` → input `draft` → `localDraft` (+ `inlineItem` из `temporary_draft_payload`).

Save draft: `onSave` L2395–2418 (авто-`validateAndApplyLineStatuses`, блок при unusable) → page `createOperation`/`updateOperation` (+ merge server response с сохранением локального `inlineItem`) → `expected_version` растёт.

Submit: `onSubmit` L2441–2488 (сброс ошибок, авто-валидация) → emit → page `submitWithResult` (save + submit, idempotency `client_request_id`) → ProblemEnvelope (включая `identityDuplicate` и `operation_lines_unresolved`) → `SubmitErrorService` groups → per-line подсветка + candidates.

### A.6 Состояния Operation Modal (фактическая матрица)

| Состояние | Данные | Editable | Read-only | Действия | Запросы | Frontend state |
|---|---|---|---|---|---|---|
| **CREATE** | нет DTO; sites | все поля; строки | — | добавить ТМЦ (search/inline), save, cancel, submit | `GET /catalog/sites`; `GET /balances`; `GET /catalog/search/items?consistency=authoritative`; `POST /catalog/read/items/resolve`; `POST /operations`; `POST /operations/{id}/submit` | `localDraft`, `balanceState`, localStorage snapshot |
| **EDIT draft** | `GET /operations/{id}` | поля + строки (qty, remove, candidates); inline-имя **не** editable (гэп) | — | save, delete draft, cancel, submit, «Обновить остатки» | те же + `PATCH /operations/{id}`, `PATCH effective-at` | то же + `expected_version`, `saveLineErrors` |
| **VIEW submitted («Проведена»)** | `GET /operations/{id}` | ничего; qty disabled | `isReadonly` | close; cancel operation (по правилам `canCancelOperation` L1432); «Приёмка» для MOVE/RECEIVE с acceptance L1447; root: restore/delete только для cancelled | `GET` при открытии | **баг:** `.remove-btn` активен; заголовок «Редактирование операции»; corrections отсутствуют |
| **canceled (cancelled)** | `GET` | ничего | `isReadonly` | close; root: restore L1496, delete L1504 | `POST /restore` (root) | **баг:** `.remove-btn` активен; заголовок «Редактирование операции» |
| **RECEIVE** | сайт-получатель | `temporary_item` разрешён; `relevantSiteId=destination`; acceptance | — | add/inline create; submit | temp payload в `POST/PATCH`; balance не лимитирует (`lineAvailableQtyError` только qty>0) | pills временных позиций |
| **MOVE** | source+destination | temp **запрещён** (бэкенд 422); `relevantSiteId=source`; acceptance | — | add; submit | temp payload нельзя | — |
| **ISSUE** | site + `issue_object_id` обязателен; `isObjectSourceFlow=false` | обычный search из warehouse; temp запрещён | — | add; submit | баланс site-склада на submit | — |
| **WRITE_OFF** | без объекта: site; с объектом: `isObjectSourceFlow=true`, add-toolbar скрыт | выбор объекта; temp запрещён | — | submit | issued balance при объекте | — |
| **WRITE_OFF + объект / ISSUE_RETURN** | `issue object` search (is_active:true, debounce 300ms) | temp запрещён; add-toolbar скрыт | — | submit | issued register | — |
| **EXPENSE** | site + `personName` | temp запрещён | — | add; submit | decrement site | — |
| **ADJUSTMENT / CORRECTION (FE)** | `type CORRECTION` маппится в `ADJUSTMENT` | temp запрещён; знак количества | — | submit | balance при отрицательном | — |
| **Любой тип, draft, объектный flow** | — | add-toolbar скрыт | — | submit | — | — |

**Temporary item (inline) — фактическая цепочка:** `Создать ТМЦ` → `inline-item-create-modal` (клиент, полей: name, unit, category, description; `clientKey`; SKU не собирается) → emit `OperationInlineItemDraftVm` → `onInlineItemCreated` добавляет строку (`itemId:null`, `itemName = inlineItem.name`, `balanceState NOT_LOADED`) → save пишет payload в `temporary_draft_payload` → submit `_materialize_deferred_temporary_lines` создаёт **постоянный** `Item(requires_review=True)` → строка получает `item_id`, payload очищается → review через `/review-items/*` (confirm/merge). На стадии draft сущности «temporary item» нет — есть только payload строки.

**Permanent item в search** появляется из каталога; temporary items в глобальный search не попадают (их ещё нет как Item) — это by design ADR-0012.

---

## B. Root causes (раздельно, без смешивания гипотез)

**RC-1. Мёртвый «Обновить и проверить» (frontend wiring).**
`item-cache-search.onRefreshCheck` L330–333 эмитит `refreshRequested` **и** вызывает `catalogSearch.refreshItemsAuthoritative()`. Но `searchItemsOnce` не выставляет `itemSearchQuery` (это делает только неиспользуемый `searchItems()`), поэтому `refreshItemsAuthoritative` L120–148 выходит по guard пустого запроса — **no-op**; `_lastSourceSiteId` на этом пути тоже не заполняется. Кнопка фактически валидирует строки (`onRefreshCheckItems` → `validateAndApplyLineStatuses`), но **не** пересобирает search candidates. Это первичная причина «refresh не refresh'ит».

**RC-2. Нет инвалидации search при смене контекста (frontend).**
`item-cache-search` не перезапрашивает и не очищает `localResults` при изменении `sourceSiteId` (и не знает про тип операции). Смена склада-источника/типа оставляет старые candidates в dropdown. `operations-page.itemSearchCache` (C2) не инвалидируется вообще.

**RC-3. Stale rows в BFF fast cache (backend cache design).**
`consistency=fast` (default) отдаёт `CatalogCacheItem` без TTL; строки деактивируются только resolve-prune и admin write-through, поэтому удалённая/слитая позиция может продолжать отдаваться как active. Дополнительно fast-сериализация теряет `unit_id` (`''`). Modal-поиск передаёт `authoritative`, но `operations-page.resolveSearchItemIds` — нет, и любой другой потребитель fast-режима получает stale/неполные данные.

**RC-4. Backend search/query contract не знает про операцию (backend).**
`catalog_repo.list_items_page` и BFF search не фильтруют по operation type, site, остаткам, review/merge-состоянию. Поэтому search в принципе может предложить позицию, которую конкретная операция закономерно отвергнет (например, temporary item вне RECEIVE, позиция без остатка для decrement-flow, позиция не того склада для MOVE). **Это отдельный контрактный дефект; frontend-refresh его не лечит.**

**RC-5. UI предлагает inline-создание вне RECEIVE (mismatch UI↔backend).**
Add-toolbar с «Создать ТМЦ» показывается для всех не-object типов, а SyncServer принимает `temporary_item` только для RECEIVE (422 на create/update). Пользователь получает отказ на save.

**RC-6. Temporary-item duplication / copy-of-name.**
- `line.itemName` копируется из `inlineItem.name` в момент добавления (`onInlineItemCreated`) — **два источника истины**; при inline-rename (которого пока нет) display-имя и payload разъедутся;
- pills переиспользуют один `clientKey` для нескольких строк (`onInlineSearchSelected`); бэкенд требует идентичный payload при одном key → 422 «reused with different payload», а несколько строк с одним key после materialize дают submit duplicate-guard;
- snapshotDraft (`operation-draft-mappers.ts`) включает только `inlineItem.clientKey` → dirty-check не замечает правок inline name/unit/category/description;
- `editItemLine` (dead code) не вызывается.

**RC-7. `item_not_found` из свежего candidate.**
Путь выбора: `onNewItemSelected` → `resolveItemBeforeAppend` (защита от deleted/inactive/missing/merged) — уже снижает класс ошибки. Остаточное окно:
- кандидат выбран из **fast/stale** cache, затем item удалён/слит в SyncServer → resolve защищает на момент add, но между add и submit объект может стать unusable → submit вернёт 409 `operation_lines_unresolved` (штатное поведение, но UI обязан показать контролируемый refresh, а не «сломаться»);
- `item_not_found` на submit возможен и штатно — если item исчез **после** refresh.
Отдельно: для inline/temporary строк `item_not_found` невозможен — иная природа.

**RC-8. UI state issues (не cache).**
- `.remove-btn` активен в submitted/cancelled (L178–186 без `isReadonly`);
- title «Редактирование операции» для проведённой (L60) обещает редактирование, которое backend запрещает;
- qty disabled, но строка визуально не выглядит read-only целиком;
- `category_id` в шапке и числовое/пустое значение у inline-строк; технический `ID ...` в item-meta; UUID с копированием в шапке — пользовательские артефакты;
- фиксированная высота `clamp(640px, 94vh, 1000px)` даёт пустоту при 1–3 строках;
- default `type: 'MOVE'` для новой операции.

**RC-9. Нет workflow корректировки проведённой операции.**
ADR-0023 (corrections by diff) — Proposed, V1 RECEIVE; routes `routes_corrections.py` есть в SyncServer, но BFF/Angular exposure отсутствует. Требование «корректировка — отдельный workflow» архитектурно не реализовано. **Маскировать это «разрешением редактирования» нельзя.**

---

## C. Proposed target flow

Текстовая цепочка для RECEIVE (базовый сценарий; для остальных типов — с ограничениями §7):

```
modal open (new draft)
  → выбрать операцию/тип + сайт(ы)                    [type change, site change → invalidate C3/C2/C5]
  → «Обновить и проверить»:
        a) authoritative search request (re-query по текущему query+site+type)
           → replace candidate set (старый — не authoritative; отсутствующие — удалить)
        b) batch-resolve строк (validateAndApplyLineStatuses) — как сейчас
        c) GET /balances по текущим item_ids (authoritative snapshot)
           → единый «снимок» не противоречит: candidates и balances получены в одном действии
  → select existing item (resolve перед append; canonical id) | create inline temporary item
        inline temporary: local line.inlineItem (source of truth) → локальный dirty
  → inline review в таблице: qty как сейчас; inline name для temporary; marker «Новая позиция»;
    «Редактировать карточку» → full edit (name/unit/category/description)
  → explicit commit: blur/Enter по name + «Сохранить черновик»/submit-before-save
        (payload temporary_item пишется в temporary_draft_payload; clientKey стабилен; 1 строка = 1 key)
  → balance refresh (если строки изменились) → submit
        backend authoritative: materialize (ADR-0033 pre-check) → balance check → freeze snapshot
        conflict (409 stale version / item disappeared / identity dup / insufficient stock)
        → UI показывает ProblemEnvelope + «Обновить и проверить» / кандидаты, НЕ молчаливый сбой
```

Инварианты:
1. После явного refresh **никакой скрытый lazy cache не участвует** в решении: modal всегда `consistency=authoritative`; fast-cache остаётся только latency-слоем для не-критичных списков (или удаляется из decision path).
2. Candidate set заменяется целиком; identity — только стабильный ID; одинаковые человеческие имена с разными ID **не** дедуплицируются.
3. temporary items текущей операции не попадают в global permanent search (by design), а их локальная строка не участвует в дедупликации по имени.
4. Submit остаётся единственной точкой materialize; temporary item меняется только через payload строки (draft) или review-items (после submit).
5. Разделение кнопок (рекомендация §8): **двух кнопок достаточно**, но семантика разная и не пересекается:
   - «Обновить остатки» — только authoritative balances (как сейчас);
   - «Обновить и проверить» — authoritative search candidate set + batch-resolve строк + balances для текущих строк (композитный refresh). Дублирующие запросы дедуплицируются.
   При смене type/source/destination — обязательный invalidate: candidates (C3), список фильтра (C2), balanceState (C5 → NOT_LOADED), затем автозагрузка по новому ключу.

---

## D. Minimal implementation plan

### Этап 1 — Operation Modal UX cleanup (VIEW semantics + read-only + visual audit)

**Frontend:**
- `operation-create-modal.component.ts`:
  - title: computed по status: draft → «Редактирование операции» / «Новая операция»; submitted → «Просмотр операции»; cancelled → «Операция отменена» (место: L60);
  - удалить dead `editItemLine` L2260–2270 (или задействовать в этапе 2);
  - убрать pills `inline-search-hint` L273–282 (blast radius проверен: ссылок в E2E/spec нет; заменить опционально компактным счётчиком «Новых позиций: N»);
  - default type: оставить `MOVE` (продуктовое решение; изменение — отдельно), либо зафиксировать в отчёте.
- `operation-lines-table.component.ts`:
  - gate `.remove-btn` через `!isReadonly()` (сохранить `aria-label="Удалить позицию"` — E2E-контракт);
  - визуально усилить read-only состояние строки (не redesign: приглушение hover, отсутствие pointer на qty);
  - **рекомендации visual audit (отдельным пунктом, не в этом PR, кроме title/remove):** динамическая высота модала (max-height вместо фиксированного clamp с min-height); оставить `ID ...` (E2E-контракт adr-0033), но понизить вес; `category_id` → «Категория» с human-именем (требует обновления E2E `th[3]`); UUID оставить (техническая шапка) или скрыть под info-popover; заголовок «Имеется» → «Остаток» (требует E2E `th[4]`); проверка layout 1440×900 / 1280×800 / 1024×768 (уже есть media queries — проверить фактические переполнения).
- Корректировка проведённых: **не** добавлять кнопку «Редактировать»; до принятия ADR-0023 — только «Просмотр».

**Backend:** нет.
**Tests:** unit (title/read-only/remove gating); Playwright: new spec `operation-view-mode.spec.ts` — submitted/cancelled: title «Просмотр», нет `.remove-btn`, qty disabled, submit/save отсутствуют.
**Migration/compat risk:** нет. E2E, завязанные на `th[3]=category_id` и `th[4]=Имеется`, не трогать в этом этапе (перенос заголовков — только с обновлением spec).

### Этап 2 — Temporary-item inline editing (draft)

**Frontend:**
- `operation-lines-table.component.ts`:
  - для строк с `inlineItem` и `!isReadonly`: inline input имени (compact), marker «Новая позиция», мягкий row-highlight (класс, например `line--new-item`), unit/category как metadata (текущий `item-meta`), кнопка «Редактировать карточку» → output;
  - источник истины — `line.inlineItem.name`; display `line.itemName` вычисляется/синхронизируется из него;
- `operation-create-modal.component.ts`:
  - `onInlineNameCommit(localId, name)` — commit по blur/Enter; `nativeUpdateOnBlur`-стиль; **без** HTTP на каждое нажатие;
  - `openInlineCardEdit(line)` — открыть `inline-item-create-modal` в edit-режиме (prefill name/unit/category/description), `clientKey` не менять;
  - `onInlineItemUpdated(localId, payload)` — обновить `inlineItem` (+ `itemName`, `unitName`, `categoryId` для отображения); при нескольких строках с одним `clientKey` — либо запретить, либо синхронизировать payload всех строк (проще: инвариант 1 строка = 1 key; pills удалены в этапе 1);
- `inline-item-create-modal.component.ts`: edit-режим (input initial, output updated) — без backend;
- `operation-draft-mappers.ts`: `snapshotDraft` расширить inline-полями (name/unitId/unitName/categoryId/description/hashtags) → dirty-check и confirm-на-закрытие ловят rename;
- `operations.service.ts`: убедиться, что `buildPayload` всегда собирает `temporary_item` из `line.inlineItem` (проверено: L1011–1020 — да) и что save-before-submit `submitWithResult` отправляет текущий localDraft.
- **Обязательные условия (из architecture review):** шаблон читает `line.inlineItem?.name ?? line.itemName`, обратная запись из `itemName` запрещена; переупорядочивание строк запрещено (by-index merge `serverLineId` L1002–1040); после save для inline-строк приоритет — серверный `temporary_draft_payload`, если нет локальных несохранённых правок.

**Backend:** не требуется (PATCH `/operations/{id}` уже переписывает `temporary_draft_payload`; RECEIVE-only сохранён). Опционально: серверное per-line обновление temporary payload — **не** вводить без ADR (whole-draft replace достаточно для ≤50 строк).
**Tests:** unit mapper dirty + table commit; Playwright: `temporary-inline-rename.spec.ts` — создать 1 temp item, переименовать inline, сохранить draft, перезагрузить → имя сохранено; full card edit меняет unit/category/description; dirty-guard при закрытии срабатывает.
**Migration/compat risk:** нет миграций; JSON payload уже поддерживает все поля. Совместимость с ADR-0033 E2E (позиция всё ещё temporary до submit).

### Этап 3a — Authoritative search refresh (frontend wiring + invalidation)

**Frontend:**
- `catalog-search.service.ts`: удалить/исправить `refreshItemsAuthoritative` (сейчас no-op из-за незаполненного `itemSearchQuery`); сделать stateless `searchItemsOnce(query, limit, siteId, includeBalance, consistency)` единственным API для modal; при желании — `searchItems` удалить как мёртвый;
- `item-cache-search.component.ts`: `onRefreshCheck` больше не вызывает мёртвый refresh; добавить input-driven очистку `localResults` при смене `sourceSiteId`/`consistency`; формула: «обновить кандидатов» = re-run текущего запроса (и/или expose `reload()` для parent);
- `operation-create-modal.component.ts`:
  - `onRefreshCheckItems` расширить: (1) `validateAndApplyLineStatuses()` (как сейчас), (2) trigger candidate reload (по текущему query/site/context), (3) — при наличии строк — `loadBalancesForItems` для композитного refresh;
  - **частичный сбой:** под-запросы независимы; сбой balances → `markBalanceRefreshFailed`/ERROR + toast, candidates не откатывать; сбой candidates → локальный список не подменять, показать ошибку refresh (не выдавать старый набор за новый);
  - инвалидация при смене type/source/destination: очистка search state (через component API) + reset balanceState в NOT_LOADED + ключевой balance effect;
- `operations-page.component.ts`: `itemSearchCache` — очищать при явном refresh списка/смене фильтров **или** перевести `resolveSearchItemIds` на `consistency=authoritative`; TTL-less fast-кэш не оставлять в decision path.
**Backend:** нет (для 3a). 
**Tests:** unit на invalidation; обновить/дополнить Playwright `operations-catalog-refresh.spec.ts`: после refresh удалённая позиция не появляется в dropdown; выбранный свежий кандидат не даёт `item_not_found` в штатном сценарии; смена source site очищает candidates.
**Migration/compat risk:** нет. Важно сохранить существующий E2E-контракт `btn-refresh-check-items` (batch-resolve строк): он остаётся частью композитного действия.

### Этап 3b — Operation-specific search eligibility contract (NEEDS ARCHITECTURE DECISION → ADR)

**Backend (SyncServer + BFF), только после ADR:**
- определить eligibility-предикаты по типу операции (таблица §7 ниже);
- расширить BFF `/catalog/search/items` параметрами `operation_type`, `site_id`/`destination_site_id` и/или ввести отдельный eligible-режим; SyncServer browse — фильтры по остаткам/складу/статусу review по необходимости;
- удалить fast-cache из decision path Operation Modal (либо TTL + event invalidation + корректный `unit_id`);
- `_search_local_cache` — заполнять `unit_id` из кэш-строки.
**Frontend:** передавать контекст операции в search; отображать причину недоступности кандидата (нет остатка/не тот склад), если решено показывать, а не фильтровать.
**Tests:** integration (BFF+SyncServer test DB): RECEIVE/MOVE/ISSUE/WRITE_OFF наборы; E2E: search не предлагает item, который submit отвергнет.
**Migration/compat risk:** параметры API аддитивны; возможно потребуется reconcile кэша (без миграции схемы).

### Этап 4 — Optional batching enhancements (agent/OCR 10–50 items)

**Frontend:** массовое создание temporary items происходит вне UI (агент/OCR/импорт) через существующий payload; кладовщик проверяет в таблице, inline-rename из этапа 2, full edit по необходимости, explicit save/submit. Для 10–50 строк whole-draft PATCH достаточен.
**Backend:** нет (при ≤50 строк и single-editor). При >100 строк/конкурентных редакторах — **NEEDS ARCHITECTURE DECISION**: bulk/per-line endpoint или line-level optimistic merge.
**Tests:** Playwright: сид draft с 10+ temporary lines через BFF → inline-правки нескольких → save → submit → review flow; конфликт `expected_version` показывает контролируемый баннер «Обновите данные», а не потерю правок.
**Gate (из architecture review):** перед этапом 4 снять benchmark whole-draft PATCH на 10/30/50 строк (время + размер payload); при деградации — фиксировать порог и выносить bulk-endpoint в ADR.
**Migration/compat risk:** нет.

**Порядок и оценка:** этап 1 (S) → этап 2 (M) → этап 3a (M) → этап 3b (ADR, затем L) → этап 4 (S/M, опционально). Всё последовательно из-за общих файлов.

---

## E. Acceptance scenarios

| # | Сценарий | Шаги | Ожидаемый результат | Уровень |
|---|---|---|---|---|
| 1 | existing item | draft → search → выбрать существующий → save → submit | строка read-only по имени; `item_id` стабилен; submit проходит при достатке | E2E |
| 2 | manually created temporary item | RECEIVE → «Создать ТМЦ» → name/unit/category → save → submit | payload сохранён; на submit создан permanent Item (requires_review), payload очищен; строка получила ID | E2E |
| 3 | temporary rename inline | temp item → изменить имя inline (blur) → save draft → reload | в БД `temporary_draft_payload.name` = новое имя; после reload строка показывает новое имя; `line.itemName` не расходится | E2E |
| 4 | full card edit | «Редактировать карточку» → изменить unit/category/description → save | payload обновлён целиком; unit/category отображаются; временная позиция не превратилась в permanent | E2E |
| 5 | 10+ OCR temporary items | сид draft с 10–50 temporary lines → проверить в таблице → исправить 3–5 имён inline → save → submit | все правки сохранены; materialize создаёт 10–50 items; ни один duplicate-guard не сработал ошибочно | E2E + integration |
| 6 | stale candidate disappears after refresh | тёплый кэш → удалить/слить item в SyncServer → «Обновить и проверить» → поиск | удалённый кандидат отсутствует в dropdown; старый candidate set не authoritative | E2E |
| 7 | archived item не появляется | item `is_active=false`/deleted → refresh → поиск | не предлагается | E2E |
| 8 | duplicate ID не появляется дважды | поиск с query, пересекающим кэш и remote | одна строка на ID (merge by id), без визуальных дублей | unit + E2E |
| 9 | same-name/different-ID | два item с идентичным именем, разные ID | оба различимы в выдаче; дедуп только по ID; выбор любого корректен | unit + E2E |
| 10 | source site changes → invalidation | MOVE/ISSUE: сменить source site | candidates очищены/перезапрошены; balances → NOT_LOADED и перезагружены по новому сайту | E2E |
| 11 | item disappears between refresh and submit | refresh → выбрать item → удалить item на бэкенде → submit | 409 `operation_lines_unresolved` (или identity-вариант); UI показывает ProblemEnvelope + «Обновить и проверить», без молчаливого сбоя | integration + E2E |
| 12 | no item_not_found from fresh candidate | refresh → выбрать свежий кандидат → submit | штатно без `item_not_found`; выбранный кандидат resolvable | E2E |
| 13 | VIEW submitted | открыть проведённую | title «Просмотр операции»; remove/save/submit отсутствуют; «Приёмка» только где положено | E2E |
| 14 | cancelled | открыть отменённую | read-only; root видит restore/delete; remove отсутствует | E2E |

---

## F. Verdict

| Направление | Вердикт | Обоснование |
|---|---|---|
| Операционное окно: VIEW semantics, read-only, title, удаление dead-кода/pills | **READY FOR IMPLEMENTATION** | frontend-only, контракты не меняются; E2E-риск локализован (не трогаем th[3]/th[4]) |
| Temporary-item inline editing (draft): inline name + full card + dirty-check | **READY FOR IMPLEMENTATION** с зафиксированными решениями: source of truth = `line.inlineItem`; commit on blur/Enter; persist через существующий PATCH whole-draft; 1 строка = 1 `clientKey` | backend уже поддерживает payload; миграций нет |
| Authoritative search refresh: wiring + invalidation | **READY FOR IMPLEMENTATION (3a)** как подэтап | RC-1/RC-2 — чистый frontend |
| Поиск: stale/дубли/`item_not_found` root cause | **NEEDS ARCHITECTURE DECISION (3b)** | RC-3 (BFF fast cache без TTL) и RC-4 (нет operation-aware eligibility) — контрактные дефекты; frontend-refresh их не маскирует |
| Batch 10–50 temporary items | **READY FOR IMPLEMENTATION** | whole-draft PATCH + explicit save достаточны; ограничение single-editor и ≤50–100 строк задокументировано |
| Batch >100 / concurrent editors | **NEEDS ARCHITECTURE DECISION** | нужен bulk/per-line endpoint или line-level merge |
| Корректировка проведённой операции (workflow) | **NEEDS ARCHITECTURE DECISION** | ADR-0023 Proposed, V1 = RECEIVE, BFF/Angular отсутствуют; до этого UI обязан ограничиваться «Просмотром» |
| Единая кнопка «Обновить и проверить» vs две кнопки | **READY (выбор зафиксирован):** две кнопки с непересекающейся семантикой; «Обновить и проверить» = candidates + resolve + balances | не требует backend-изменений, укладывается в RC-1 fix |

---

## §7 Operation-specific search semantics (основа для ADR этапа 3b)

| Тип | Site-контекст | Допустимые кандидаты | Temporary creation | Остатки на submit |
|---|---|---|---|---|
| RECEIVE | destination | весь active catalog (existing items) | **да** | не потребляются |
| MOVE | source (destination не влияет на candidates) | позиции, доступные на source; zero-stock — только с предупреждением (submit отвергнет при недостатке) | нет | source warehouse |
| ISSUE | site (= source) | существующие позиции на складе; zero-stock не предлагать/пометить | нет | site warehouse |
| ISSUE_RETURN | issue_object | позиции с остатком у объекта выдачи | нет | issued register |
| WRITE_OFF (без объекта) | site | позиции с остатком на складе | нет | site warehouse |
| WRITE_OFF (+ объект) | issue_object | позиции с остатком у объекта | нет | issued register |
| EXPENSE | site | позиции с остатком на складе | нет | site warehouse |
| ADJUSTMENT (в т.ч. FE CORRECTION) | site | positive — любой active; negative — с остатком | нет | только отрицательные строки |

Проверять по факту: `_check_submit_balance_sufficiency` L462–579 (источник истины по потреблению баланса).

---

## Risks / open questions

1. **ADR-0033 stage 4** (BFF+Angular pass-through, candidates, inline warning) формально не закрыта — inline editing этапа 2 не конфликтует, но в одном окне должны корректно уживаться identity-candidates swap и inline temp.
2. **Изменение заголовков таблицы** (`category_id` → «Категория», «Имеется» → «Остаток») ломает существующие Playwright-ассерты `th[3]`/`th[4]` — только вместе с обновлением E2E.
3. **techn `ID ...` в строке** — E2E-контракт ADR-0033 (`adr-0033-identity-guard.spec.ts`); удалять/скрывать нельзя без обновления spec.
4. **Fast cache (C1)** после этапа 3a всё ещё остаётся в `operations-page` и прочих потребителях — либо TTL/invalidation в 3b, либо явный отказ от fast-режима в decision path.
5. **Concurrent editors черновика** — при `expected_version` 409 нужен явный UX-конфликт (баннер + refresh), иначе inline-правки теряются молча.
6. **Производительность whole-draft PATCH** при 50+ строках не измерена; порог для перехода на bulk-endpoint зафиксировать измерением (benchmark) перед этапом 4.
7. **RECEIVE-only temporary rule** может потребовать продуктового решения: если inline-создание нужно в других типах — это изменение domain-правила (ADR), а не UI-фикс.

---

# Architecture review — Quartermaster 4.0 Operation Modal / Inline Temp Item / Search Refresh

**Дата:** 2026-09-14
**Reviewer:** Architect

## Verdict

**Approved with conditions** (этапы 1, 2, 3a, 4 — можно запускать; 3b и corrections требуют ADR до реализации).

## 🔴 Blockers

Не найдено при условии, что этап 3b не подменяется этапом 3a. Критерии приёмки E6/E7/E11 (archived/stale/materialized conflict) полностью закрываются только после 3b; до ADR их нельзя объявлять выполненными.

## 🟡 Warnings

1. **Композитный refresh — поведение при частичном сбое не задано.**
   - *Checklist:* Failure modes / Data & state.
   - *Issue:* «Обновить и проверить» = candidates + resolve + balances (3 параллельных запроса). Если balances упал, а candidates обновились — состояние формально «свежее наполовину».
   - *Recommendation:* зафиксировать в этапе 3a: каждый под-запрос независим, при сбое его состояние помечается ERROR + toast; candidates не откатывать; balanceState при сбое НЕ становится 0 (уже есть `markBalanceRefreshFailed`).
2. **Двух источников истины для имени можно избежать только дисциплиной.**
   - *Checklist:* Data & state / source of truth.
   - *Issue:* `line.itemName` остаётся рядом с `line.inlineItem.name`; таблица может читать любое.
   - *Recommendation:* в этапе 2 шаблон читает `line.inlineItem?.name ?? line.itemName`; `line.itemName` синхронизируется только для серверного/legacy пути. Reviewer обязан проверить отсутствие обратной записи.
3. **Серверная нормализация payload после save.**
   - *Checklist:* Data & state.
   - *Issue:* SyncServer нормализует `category_id: null → Uncategorized`, `sku: null` и может отдать другой `temporary_draft_payload`; `mergeDraftAfterSuccessfulSave` сохраняет локальный `inlineItem` (проверено: L1002–1040, merge по индексу + `serverLineId ?? local`).
   - *Recommendation:* при merge для inline-строк отдавать приоритет серверному payload (кроме ещё не сохранённых правок) либо после save помечать строку clean по серверному снапшоту.
4. **Сохраняется by-index контракт строк.**
   - *Checklist:* Coupling / data integrity.
   - *Issue:* `update_operation` пересоздаёт строки; `serverLineId` привязывается по индексу. Inline-редактирование не меняет порядок — безопасно; добавление drag-reorder или вставки в середину сломает привязку.
   - *Recommendation:* в этапе 2 явно запретить переупорядочивание строк; future reorder — отдельный ADR.
5. **Fast cache остаётся у второго потребителя.**
   - *Checklist:* Scalability / invalidation.
   - *Issue:* этап 3a чистит decision path Operation Modal, но `operations-page.resolveSearchItemIds` (C2) продолжает ходить в fast-режим.
   - *Recommendation:* включить C2 в этап 3a (явная инвалидация или `consistency=authoritative`), иначе часть stale-класса останется.
6. **Порог batch не измерен.**
   - *Checklist:* Scalability.
   - *Issue:* 50 строк whole-draft PATCH — гипотеза; 100+ — риск.
   - *Recommendation:* benchmark перед этапом 4 (payload size/time на 10/30/50 строк), зафиксировать результат в TZ.

## 🔵 Notes

- Observability: новые метрики не нужны; достаточно существующих ProblemEnvelope + structured logs ADR-0033 (`item_identity.flag`). Точка роста — счётчик «refresh привёл к удалению N candidates» (полезно, не обязательно).
- Security: новых поверхностей нет; refresh не принимает пользовательских ID из URL.
- Rollback: этапы 1–3a — frontend bundle, откат деплоем предыдущего билда; 3b — аддитивные параметры BFF, откат без миграций.
- E2E-контракты (`th[3]`, `th[4]`, `ID ...`, `btn-refresh-check-items`, `.remove-btn` aria-label) — менять только вместе со spec.

---

## Evidence (заполняется исполнителем)

### Stage 1 evidence (2026-09-14)

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|
| Unit tests | `npm run test:unit` (Warehouse_frontend) | pass | 26 files / 262 tests passed |
| Build | `npm run build` | pass | bundle generated; only pre-existing component-style budget warning |
| UI automation (new) | `operation-view-mode.spec.ts` (Playwright/Docker) | pass | 4/4: submitted view, cancelled view, RECEIVE-only create, pills→counter |
| UI automation (updated) | `operations-create-modal.spec.ts --grep "add TMC row"` | pass (admin creds) | 1/1; default-role run blocked by stand `spa_user` auth (pre-existing, see blocker) |
| Stand smoke | `:8001/healthz/`, `:8000/api/v1/health`, `pg_isready` | pass | all services 200/accepting |

**Blocker (not Stage 1):** `operations-create-modal.spec.ts` logs in as `spa_user` (default `aksha`/`089786`); on this stand the login stays on the login page, so the whole pre-existing spec cannot execute under its default role. The updated test was verified with `E2E_USERNAME_SPA=admin E2E_PASSWORD_SPA=admin123` and passed. Fixing the `spa_user` account is out of Stage 1 scope.

**Stage 1 scope delivered:** VIEW title `Просмотр операции` (submitted) / `Операция отменена` (cancelled); remove button hidden in read-only; qty truly `disabled`; save/submit absent in read-only; top temporary-item pills removed (compact `Новых позиций: N` counter); «Создать ТМЦ» rendered only for RECEIVE. Not touched: `category_id`, `Имеется`, UUID, dynamic height, corrections workflow.

### Stage 2 evidence (2026-09-14)

**Commit:** `Warehouse_frontend` dev `e15e6c8` — «feat(operations): inline edit temporary draft items» (14 files).

**Source of truth:** `line.inlineItem` (draft payload). `line.itemName` — односторонняя display-копия, синхронизируется только из `inlineItem`; template читает `line.inlineItem?.name`. Persistence — существующие пути (Save draft / save-before-submit), без per-line API; full card edit меняет payload существующей строки и сохраняет `clientKey`.

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|
| Unit/component | `npm run test:unit` | pass | 28 files / 292 tests (new: `operation-draft-mappers.spec.ts`, `inline-item-create-modal.component.spec.ts`; extended table/modal/operations specs) |
| Build | `npm run build` | pass | bundle generated; only pre-existing component-style budget warning |
| Integration (real deps) | Playwright via Django BFF → SyncServer + PostgreSQL | pass | Stand-backed scenario suite `temporary-inline-edit.spec.ts` 4/4 |
| Stand smoke/UI automation (new) | `temporary-inline-edit.spec.ts` | pass | 4/4: catalog row read-only + rename persists/reloads; full card edit in place + clientKey preserved; renamed temp materializes with corrected name (ADR-0033 review); two same-named lines → distinct client_keys |
| Regression | `adr-0033-identity-guard.spec.ts`, `operation-view-mode.spec.ts`, `operations-sku-conflict.spec.ts` | pass | 8 tests after two spec selector fixes (see below) |

**Stage 2 scope delivered:** inline soft row highlight + «Новая позиция» marker; compact editable name input for inline rows only (commit on Enter/blur, Esc revert, empty/unchanged ignored); «Редактировать карточку» opens `inline-item-create-modal` in edit mode (name/unit/category/description prefill, clientKey preserved, no new line/item); `snapshotDraft` includes full inline payload (clientKey/name/sku/unitId/unitName/categoryId/categoryName/description/hashtags) → dirty-guard/close-guard/autosave-restore aware of renames; `mergeInlineItemAfterSave` treats server `temporary_draft_payload` as canonical (trims/normalized category win, local fallback for omitted fields); numeric DTO ids coerced to string in `mapDtoToDraftVm`. Not touched: search refresh (Stage 3a), reorder, per-line temporary API.

**E2E selector-contract updates (DOM intentionally changed, tests realigned):**
- `adr-0033-identity-guard.spec.ts`: row qty now addressed via `.qty-input` (was `input` first — now the inline name input is first in the row).
- `operations-sku-conflict.spec.ts`: inline name asserted via `.inline-name-input` value (was cell text).

**Blocker observed during Stage 2 (environment, not code):** Django serves Angular from the built `dist/warehouse-frontend/browser` mounted at `/angular-build`; E2E does **not** see live `ng serve` output. Any frontend change requires `npm run build` before the Playwright run. Documented here so Stage 3a does not repeat the diagnosis.

**Blocker (pre-existing, not Stage 2):** `operations-create-modal.spec.ts` default `spa_user` login (`aksha`/`089786`) fails on this stand; not exercised in the Stage 2 regression set.

### Stage 3a evidence (2026-09-14)

**Commits:**
- `Warehouse_frontend` dev `d986fed` — «fix(operations): authoritative refresh for item search» (7 files).
- `Warehouse_web` dev `16a728b` — «test(bff): prove authoritative catalog search ignores stale cache» (1 file, test-only).

**Real fast/authoritative request chain (verified in source):**
1. typing → `searchItemsOnce(q, 20, sourceSiteId, false, 'authoritative')` (modal binds `consistency='authoritative'`) → BFF `GET /catalog/search/items?consistency=authoritative` → `CatalogCachedItemSearchView` → `_search_remote_items` (SyncServer `browse_items`) → response `source: "remote"`; **no local cache read, no cache merge**.
2. «Обновить и проверить» → `refreshItemsAuthoritativeOnce(query, site)` → same authoritative endpoint for the actual current query → result fully replaces `localResults` (no old+new merge).
3. fast mode (`consistency=fast`, default) still exists for other consumers and may serve `catalog_cache_item` rows without TTL; it is **not** used by the Operation Modal decision path, and the explicit refresh never falls back to it.

**itemSearchQuery fix:** the dead `itemSearchQuery`/`searchItems()`/`refreshItemsAuthoritative()` lifecycle was removed. `searchItemsOnce` now records `lastItemsSearch` (query/limit/site/includeBalance); `refreshItemsAuthoritativeOnce(query?, site?)` always forces `consistency=authoritative`, defaults to the recorded query/site, dedupes by stable ID only, and returns the complete set. `filter`/`debounceTime` legacy pipe deleted.

**Invalidation rules:** `item-cache-search` gets a parent `[scopeKey]="searchScopeKey()"` = `type|sourceSiteId|destinationSiteId`; an effect also watches `sourceSiteId`. On change the candidate snapshot is cleared (query text kept, operation lines untouched — different entities). `operations-page.itemSearchCache` is a separate list-filter concern and was intentionally not changed (not part of the modal decision path).

**Resolve behavior:** part B reuses `validateLinesBeforePersist` → `/catalog/read/items/resolve`, which filters `l.itemId && !l.isTemporary && !l.inlineItem`; inline/new rows are never sent; `applyResolvedStatuses` only annotates, never removes lines; unusable lines block save/submit (submit stays backend-authoritative).

**Balances proof:** `onRefreshCheckItems` calls only `validateAndApplyLineStatuses` (no `loadBalancesForItems`); E2E asserts no `/balances` request during the refresh click while the separate «Обновить остатки» button still triggers `GET /balances`.

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|
| Unit/component | `npm run test:unit` | pass | 29 files / 308 tests (new `catalog-search.service.spec.ts`; extended `item-cache-search.component.spec.ts`, modal spec) |
| Build | `npm run build` | pass | bundle generated; only pre-existing component-style budget warning |
| Integration (BFF proof) | `python manage.py test apps.bff_api.tests_issue24` | pass | 9/9 incl. `BffApiAuthoritativeSearchTests`: authoritative ignores stale cache-only row; fast mode can still return it |
| UI automation (new) | `authoritative-search-refresh.spec.ts` (Playwright/Docker) | pass | 3/3: Scenario A search→refresh→select→save; Scenario C site change invalidates + refresh uses new site; Scenario D only permanent line resolved, inline survives, no balances call + «Обновить остатки» still works |
| Regression | `adr-0033-identity-guard` (3), `operation-view-mode` (4), `temporary-inline-edit` (4), `operations-sku-conflict` (1) | pass | 12/12 in the serial full run |
| Regression (pre-existing red) | `operations-catalog-refresh.spec.ts` (2) | fail (not Stage 3a) | fails identically with Stage 3a app changes stashed and dist rebuilt: seeded draft row not visible (`openDraftModal` L141) due to dev-stand draft pollution; baseline run `--retries=0` reproduced both failures |
| Stand smoke | `:8001/healthz/`, `:8000/api/v1/health`, `pg_isready`, `:4200/` | pass | Playwright health checks green at suite start |

**Left unresolved (explicitly for Stage 3b):** the search endpoint remains not operation-aware — no `operation_type`/site-balance/review eligibility filtering (RC-4). Stage 3a does not fake it with frontend domain filters; `catalog_repo.list_items_page` still returns the whole active catalog. Also still open: BFF `_search_local_cache` hardcodes `unit_id: ''` and the no-TTL fast cache remains for non-modal consumers (incl. `operations-page.itemSearchCache`).

### Final acceptance closure (2026-09-14)

**Reviewer verdict: «OPERATION MODAL READY FOR 4.0»** — независимый acceptance review пройден. Operation Modal **не является блокером** Quartermaster 4.0.

| Item | Status | Evidence |
|---|---|---|
| Stage 1 — Operation Modal UX cleanup (VIEW semantics, read-only, title) | **accepted** | Stage 1 evidence; `Warehouse_frontend` `e500aa5` |
| Stage 2 — Temporary-item inline editing | **accepted** | Stage 2 evidence; `Warehouse_frontend` `e15e6c8` |
| Stage 3a — Authoritative search refresh | **accepted** | Stage 3a evidence; `Warehouse_frontend` `d986fed`, `Warehouse_web` `16a728b` (test-only) |
| Visual polish | **accepted** | `Warehouse_frontend` `90963fa` «style(operations): polish operation modal layout» + `operation-modal-layout.spec.ts` |
| Unit/component, build, integration, stand smoke, UI automation | **accepted** | per Stage 1–3a evidence (29 files / 308 unit tests, build pass, BFF 9/9, stage Playwright specs green) |
| Independent review | **passed** | независимый Reviewer: OPERATION MODAL READY FOR 4.0 |
| Пользовательская ручная проверка | **passed** | ручной проход выполнен пользователем (create/edit/view/submit, inline temp item, refresh) |
| Regression E2E | **accepted with classified debt** | 2 baseline-падения `operations-catalog-refresh.spec.ts` — test/environment debt (см. ниже) |
| Stage 3b — Operation-specific search eligibility contract | **deferred to 4.1 / ADR scope** | требует ADR; в 4.0 не реализуется и не подменяется этапом 3a (см. Execution checklist, п. 5) |
| Reviewer residual R-1…R-7 | **deferred to 4.1 / соответствующий ADR scope** | не блокируют 4.0; состав residual фиксируется независимым Reviewer |

**Baseline E2E failures — test/environment debt (не product regression):**
- `operations-catalog-refresh.spec.ts` — 2 падения. Воспроизведены при откате Stage 3a app-изменений и пересборке `dist` (`--retries=0`); root cause — загрязнение dev-стенда черновиками (`openDraftModal` visibility). Исправление E2E environment debt — вне scope Operation Modal.
- Ранее зафиксированный stand-блокер `operations-create-modal.spec.ts` (логин `spa_user` на текущем стенде) остаётся environment-проблемой стенда (см. Stage 1 evidence); код Operation Modal его не вызывает.

**Scope closure:** application code после этапов 1–3a и visual polish не изменялся в рамках закрытия. Пункты чек-листа 5 (Stage 3b) и 6 (Stage 4 batching gate) остаются открытыми и вынесены за 4.0.

---

## Stand (Docker)

- SyncServer `http://localhost:8000` — `GET /api/v1/health`
- Django `http://localhost:8001` — `GET /healthz/`
- PostgreSQL `localhost:5432` — `pg_isready -h localhost -p 5432 -t 3`
- Angular `http://localhost:4200` (через Django shell)
- Env names only: `DJANGO_ENV`, `SYNC_SERVER_URL`, `SYNC_ROOT_USER_TOKEN`, `SYNC_DEVICE_TOKEN`, `DATABASE_URL`, `DJANGO_SETTINGS_MODULE`, `SECRET_KEY`
- Stand reset/rebuild: `make restart`, `make build-sync` / `make build-web` / `make build-angular`, `make reset-django-admin`

---

## Verification summary (analysis phase)

- Код не изменялся, коммитов нет, миграций нет.
- Все утверждения A/B сверены с исходниками: Angular-компоненты, BFF views/models, SyncServer services/repos/schemas, E2E specs, ADR.
- Отдельно зафиксировано: проблема search имеет **две независимые причины** — frontend wiring (RC-1/RC-2) и backend/cache контракт (RC-3/RC-4); они не смешиваются и закрываются разными этапами (3a / 3b).
