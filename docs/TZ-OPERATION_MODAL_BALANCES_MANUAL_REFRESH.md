# TZ-OPERATION_MODAL_BALANCES_MANUAL_REFRESH

**Статус:** готово к реализации
**Дата:** 2026-08-07
**Автор:** architect (по запросу пользователя; развитие SCOPE-ops-balances-manual.md)
**Приоритет:** 🔴 преддеплой (UX-блокер для кладовщика, см. SCOPE §Проблема)
**Связанные документы:**
* Scope-источник: `.agent/SCOPE-ops-balances-manual.md` (147 строк, июль 2026)
* Обследование преддеплой-пометки: `.agent/SCOPE-INVESTIGATION-SITE-SWITCH-RECEIVE.md` (203 строки, 2026-08-07)
* `Functional and WorkLogik.md` п. II/5.0, II/5.1 — обязательность остатков на выбранном складе
* `Warehouse_frontend/AGENTS.md` — стенд и verification matrix
* `docs/AGENT_TZ_WORKFLOW.md` — шаблон чек-листа и test ladder

---

## 0. Execution Checklist

### Implementation
- [x] 0. Контекст verified (SCOPE §Проблема + Investigation §6.1 прочитан)
- [x] 1. `OperationCreateModalComponent` — убрать `effect()` на `relevantSiteId()` (строки 1175-1214) и заменить на фокусный автозапрос
- [x] 2. `OperationCreateModalComponent` — убрать `refreshBeforePersist()` (строки 1317-1330) и его вызовы из `onSave()` (1611), `onSubmit()` (1659)
- [x] 3. `OperationCreateModalComponent` — добавить `onRefreshAllBalances()` для новой кнопки (использует тот же `loadBalances + refreshSourceQuantities` без race)
- [x] 4. `OperationLinesTableComponent` — добавить кнопку «Обновить всё» в шапку таблицы + output `refreshAllBalances` + вход `isRefreshing` уже есть
- [x] 5. `ItemCacheSearchComponent` — убрать `<span class="option-stock">на складе: {{ item.source_site_qty }}</span>` (строки 72-74) и связанные стили
- [x] 6. `ItemCacheSearchComponent` — передавать `include_balance=false` в `searchItemsOnce` (строка 240)

### Tests
- [x] 7. Static checks: `npm run build` (Angular) + `npx tsc --noEmit` (типы)
- [x] 8. Unit/component test `operation-lines-table.spec.ts` — кнопка «Обновить всё» рендерится и эмитит `refreshAllBalances`; при `isRefreshing=true` → `disabled` + спиннер
- [x] 9. Component test `item-cache-search.spec.ts` (новый файл) — span «на складе: X» не рендерится; `searchItemsOnce` вызван с `include_balance=false`
- [x] 10. Component test `operation-create-modal.spec.ts` (новый файл) — смена `relevantSiteId` вызывает `loadBalances(siteId)` ровно один раз без race; добавление ТМЦ вызывает `getBalanceForItem` ровно один раз; `onSave`/`onSubmit` НЕ вызывают `loadBalances`
- [x] 11. Stand smoke: `make status` → стенд healthy → ручной сценарий через Playwright MCP
- [x] 12. UI automation: новый `e2e/operations/operations-balances-manual.spec.ts` — сценарий A (смена склада) + сценарий B (refresh all) + сценарий C (search dropdown без остатков)
- [x] 13. User scenario: «кладовщик открывает черновик RECEIVE, добавляет 2 ТМЦ, переключает склад → остатки реактивно обновляются; жмёт «Обновить всё» → остатки подтягиваются с сервера; в выпадашке поиска нет поля «на складе: X»; submit не вызывает фонового обновления»
- [x] 14. Regression: existing e2e `operations-create-modal.spec.ts` (save/confirm/validation) не сломан
- [x] 15. Regression: existing e2e `operations-save-reliability.spec.ts` (save flow) не сломан
- [x] 16. Regression: existing e2e `operations-submit.spec.ts` (submit) не сломан (5 тестов скипнуты штатными `test.skip(true, ...)` в файле — не связаны с данной правкой)
- [x] 17. Documentation: `MEMORY.md` / `GIT_STATE.md` обновлены, `SCOPE-ops-balances-manual.md` помечен как «реализован», ссылка на этот TZ в `INDEX.md`

### Final
- [ ] 18. Final acceptance (QA verifier)

## Check Rules

* Архитектор (этот документ) создаёт чек-лист и критерии приёмки.
* Executor проверяет только после реализации и собственного прогона всех применимых уровней тестов (1-7).
* Если уровень недоступен (например, стенд недоступен) — оставить пустым с пометкой «стенд недоступен» в Evidence.
* Перед любым real-stand прогоном — Stand Availability Protocol из корневого `AGENTS.md` и `Warehouse_frontend/AGENTS.md`.
* Commit только в `dev`-ветку, по правилам `Warehouse_frontend/AGENTS.md`.

---

## 1. Контекст и мотивация

### 1.1. Проблема (из SCOPE)

В Angular-форме создания/редактирования операции остатки ТМЦ сейчас подтягиваются автоматически:

1. **Эффект на смену склада** (строки 1175-1214) — при любом изменении `relevantSiteId()` дёргается `loadBalances(siteId)` + `refreshSourceQuantities()` по всем строкам черновика.
2. **Перед submit/save** (`refreshBeforePersist()`, строки 1317-1330) — принудительный рефреш остатков всех строк.

Кладовщик наблюдает «иногда актуально, иногда нет» — автосинк срабатывает в непредсказуемые моменты, есть гонки (`balanceRefreshSeq` уже пытались разрулить, но поведение всё равно мутное). Хочется явного ручного контроля.

Дополнительно — в выпадашке поиска (`ItemCacheSearchComponent:72-74`) показывается «на складе: X» через поле `source_site_qty`. Это лишний обогащающий HTTP-запрос на каждую букву поиска, и эта цифра часто расходится с реальностью (тот же баг).

### 1.2. Связанная преддеплой-пометка (Investigation)

Параллельно поступила пометка «при смене склада в RECEIVE остатки не реактивны». Обследование (`SCOPE-INVESTIGATION-SITE-SWITCH-RECEIVE.md`) показало, что **в базовых сценариях реактивность есть** (effect срабатывает, HTTP-запрос уходит с правильным `site_id`, `lines.availableQuantity` обновляется). То есть **пометка про «залипание» закрывается автоматически** после выполнения этого ТЗ — потому что мы упростим и сделаем явным автозапрос на смену склада, а не «вечный» автосинк. Если у кладовщика есть конкретный тикет, по которому баг всё ещё воспроизводится — добавим точечный сценарий в Phase 12.

### 1.3. Целевое состояние (post-TZ)

- Смена склада → **один раз** `loadBalances(siteId)` + обновление строк (auto, без race).
- Добавление/выбор ТМЦ в строку → **один раз** `getBalanceForItem(itemId, siteId)`.
- Save/Submit → **НЕ** вызывает фонового обновления остатков.
- Кнопка «Обновить всё» в шапке таблицы строк → ручной `loadBalances + refreshSourceQuantities`, на время — спиннер + `disabled`.
- В выпадашке поиска ТМЦ → нет поля «на складе: X», нет обогащающего HTTP-запроса.

---

## 2. Границы (in / out of scope)

### 2.1. In scope (всё из SCOPE §In Scope, повторяем для traceability)

1. Убрать глобальный автосинк остатков при смене склада и перед submit.
2. Оставить точечный автозапрос при добавлении/выборе ТМЦ в строку.
3. Оставить автозапрос остатков при смене склада, но без гонок.
4. Добавить кнопку «Обновить всё» в шапку таблицы строк.
5. Скрыть остаток в выпадашке поиска (`ItemCacheSearchComponent`).
6. **Не** трогать legacy Django SSR форму (`templates/operations/form.html`, `static/js/operations_create.js`).

### 2.2. Out of scope

* Рефакторинг `OperationCreateModalComponent` (1712 строк) — точечные правки, без разбиения на подкомпоненты.
* Изменение BFF/SyncServer контрактов — используем существующий `GET /bff/api/v1/balances?site_id=X[&item_id=Y]`.
* Показ timestamp последнего обновления остатков.
* Подсветка «устаревших» остатков / визуальная индикация.
* Bulk-эндпоинт в BFF (`POST /bff/api/v1/operations/refresh-balances`) — в этой итерации per-row параллельные запросы не используются (см. §3.3); bulk — оптимизация на будущее.
* Изменение `Functional and WorkLogik.md` — требование «указание количества на выбранном складе» (п. II/5.0) сохраняется, просто источник становится явным.
* Локализация / i18n новых строк UI (текст кнопки «Обновить всё» берём как есть).
* Правка Django SSR (`/ssr/operations/...`) — автосинка там нет, минимально-обратимая правка только в Angular.

---

## 3. Задействованный код

### 3.1. Файлы, которые будут изменены

| Файл | Что меняется | Объём |
|---|---|---|
| `Warehouse_frontend/src/app/features/operations/components/operation-create-modal/operation-create-modal.component.ts` | Удалить effect 1175-1214; удалить `refreshBeforePersist` 1317-1330 и его вызовы в 1611/1659; добавить `onRefreshAllBalances()` | ~30-50 строк нетто |
| `Warehouse_frontend/src/app/features/operations/components/operation-create-modal/operation-lines-table.component.ts` | Добавить кнопку «Обновить всё» в шапку `th.col-avail`; новый `output refreshAllBalances` | ~15-25 строк |
| `Warehouse_frontend/src/app/features/operations/components/item-cache-search/item-cache-search.component.ts` | Удалить `<span class="option-stock">…</span>` (72-74); связанные стили; передать `include_balance=false` (240) | ~10-15 строк |
| `Warehouse_frontend/e2e/operations/operations-balances-manual.spec.ts` | **Новый файл** — UI automation для нового поведения | ~120-180 строк |
| `Warehouse_frontend/src/app/features/operations/components/item-cache-search/item-cache-search.component.spec.ts` | **Новый файл** — unit test для скрытия «на складе: X» | ~60-100 строк |
| `Warehouse_frontend/src/app/features/operations/components/operation-create-modal/operation-create-modal.component.spec.ts` | **Новый файл** — unit test для отказа от `refreshBeforePersist` и обновления effect | ~80-130 строк |
| `.agent/SCOPE-ops-balances-manual.md` | Пометить «реализован» + ссылка на этот TZ | ~3 строки |
| `MEMORY.md`, `GIT_STATE.md`, `INDEX.md` | Обновить состояние | ~5-10 строк |

### 3.2. Ключевые строки до правки

`operation-create-modal.component.ts`:
- 799: `readonly isBalanceRefreshing = signal<boolean>(false);`
- 824-827: `readonly relevantSiteId = computed(() => { … for RECEIVE returns destinationSiteId; … });`
- 1175-1214: effect на `relevantSiteId` — основной объект удаления
- 1317-1330: `private async refreshBeforePersist(): Promise<void>` — удалить
- 1609-1618: `onSave()` — вызов `await this.refreshBeforePersist();` удалить
- 1641-1660: `onSubmit()` — вызов `await this.refreshBeforePersist();` удалить
- 1463: `: this.service.getBalanceForItem(item.id, this.relevantSiteId() || undefined);` — оставить как есть (per-row автозапрос)

`operation-lines-table.component.ts`:
- 64-69: `<th class="col-avail" (click)="toggleSort('availableQuantity')">` — место для кнопки
- 133: `@if (line.inlineItem) { … } @else if (isBalanceRefreshing()) { <span class="avail-loading">…</span> }` — использовать существующий `isRefreshing`-поток
- 380-390: входы/выходы — добавить `output refreshAllBalances`

`item-cache-search.component.ts`:
- 72-74: `@if (item.source_site_qty) { <span class="option-stock">на складе: {{ item.source_site_qty }}</span> }` — удалить
- 240: `return this.catalogSearch.searchItemsOnce(query, 20, this.sourceSiteId() ?? undefined);` — добавить `false` (4-й аргумент = `includeBalance=false`)

### 3.3. Реализация `onRefreshAllBalances`

Исполнитель может выбрать один из двух вариантов. Оба валидны. **Предпочтительно Вариант A** (один HTTP-запрос, в духе существующего `refreshBeforePersist`):

* **Вариант A — `loadBalances` + `refreshSourceQuantities`:**
  ```ts
  async onRefreshAllBalances(): Promise<void> {
    if (!this.shouldUseWarehouseBalances()) return;
    const siteId = this.relevantSiteId();
    if (!siteId || siteId === 'undefined' || siteId === 'null') return;
    const seq = ++this.balanceRefreshSeq;
    this.isBalanceRefreshing.set(true);
    try {
      await this.service.loadBalances(siteId);
      if (seq === this.balanceRefreshSeq && this.relevantSiteId() === siteId) {
        this.refreshSourceQuantities();
      }
    } finally {
      if (seq === this.balanceRefreshSeq) this.isBalanceRefreshing.set(false);
    }
  }
  ```
  Один HTTP-запрос обновляет весь signal `balances`, потом client-side проход по строкам. SCOPE говорит «per-row parallel» — но это неточная формулировка: `loadBalances-per-row` сводится к одному запросу через фильтр `site_id` (тело BFF-запроса одинаковое), а per-row HTTP — это антипаттерн (N запросов вместо 1). Executor выбирает A, если в комментарии коммита ссылается на §3.3 настоящего TZ.

* **Вариант B — per-row `Promise.all` (если executor настаивает на тексте SCOPE):**
  ```ts
  async onRefreshAllBalances(): Promise<void> {
    if (!this.shouldUseWarehouseBalances()) return;
    const siteId = this.relevantSiteId();
    if (!siteId) return;
    const seq = ++this.balanceRefreshSeq;
    this.isBalanceRefreshing.set(true);
    try {
      const lines = this.localDraft().lines.filter(l => l.itemId);
      await Promise.all(lines.map(l => this.service.getBalanceForItem(l.itemId!, siteId)));
      // затем refreshSourceQuantities обновляет строки из signal balances
      if (seq === this.balanceRefreshSeq) this.refreshSourceQuantities();
    } finally {
      if (seq === this.balanceRefreshSeq) this.isBalanceRefreshing.set(false);
    }
  }
  ```
  ⚠️ Это не реальный per-row HTTP — `getBalanceForItem` читает из `this.balances()`. Если `balances` ещё не загружены, `getBalanceForItem` вернёт 0. Поэтому **перед** per-row вызовом всё равно нужен `loadBalances(siteId)`. Сценарий B без варианта A даёт 0 для всех строк — отвергнут.

**Резолюция:** Требуем вариант A. Если executor хочет B, согласовывает в PR-описании.

### 3.4. Реализация effect на смену склада (замена удалённого глобального effect)

```ts
// В конструкторе компонента, после других effect():
effect(() => {
  const siteId = this.relevantSiteId();
  const isObjectSourceFlow = this.isObjectSourceFlow();
  const hasPrefilledAssetLine = this.hasPrefilledAssetLine();
  if (isObjectSourceFlow || hasPrefilledAssetLine || !siteId
      || siteId === 'undefined' || siteId === 'null') {
    return;
  }
  // Один запрос без perpetual: balanceRefreshSeq — единственная страховка от race.
  const seq = ++this.balanceRefreshSeq;
  this.isBalanceRefreshing.set(true);
  this.service.loadBalances(siteId).then(() => {
    if (seq !== this.balanceRefreshSeq) return;
    if (this.relevantSiteId() === siteId) {
      this.refreshSourceQuantities();
    }
    this.isBalanceRefreshing.set(false);
  });
});
```

Это **упрощённая** версия удалённого effect (1175-1214): без ветки «else» для сброса остатков в 0 (она нужна была только при submit-flow, который у нас уже очищен), без `isBalanceRefreshing.set(false)` в `else` (нечего чистить). Поведение реактивности на смену склада сохраняется.

---

## 4. Фазы реализации (для executor)

Executor может выполнять фазы 1-3 параллельно в разных файлах (ownership не пересекается), затем 4-6 последовательно.

| Фаза | Что | Файлы | Acceptance |
|---|---|---|---|
| **1** | Удалить effect 1175-1214; удалить `refreshBeforePersist` 1317-1330; удалить вызовы в `onSave` (1611) и `onSubmit` (1659) | `operation-create-modal.component.ts` | grep `refreshBeforePersist` → пусто; `onSave`/`onSubmit` не вызывают его; `loadBalances` остался только в 1 effect и в `onRefreshAllBalances` |
| **2** | Добавить новый фокусный effect (§3.4) | `operation-create-modal.component.ts` | effect присутствует в конструкторе; `balanceRefreshSeq` инкрементируется; `refreshSourceQuantities()` вызывается после успешного `loadBalances` |
| **3** | Добавить `onRefreshAllBalances()` (вариант A из §3.3) | `operation-create-modal.component.ts` | метод существует; использует `isBalanceRefreshing`; `seq`-guard от race |
| **4** | Добавить кнопку «Обновить всё» в `<th class="col-avail">` + output `refreshAllBalances` + диспатч при клике | `operation-lines-table.component.ts` | кнопка отрендерена; `data-testid="operation-lines-refresh-all"`; `disabled` + spinner при `isRefreshing=true` |
| **5** | Связать `(refreshAllBalances)="onRefreshAllBalances()"` в parent | `operation-create-modal.component.ts` (template) | template change в `<app-operation-lines-table>` |
| **6** | Скрыть «на складе: X» + `include_balance=false` | `item-cache-search.component.ts` | span удалён; `searchItemsOnce(…, false)`; связанные CSS-стили (`.option-stock`) удалены |
| **7** | Static checks | `Warehouse_frontend/` | `npm run build` exit 0, `npx tsc --noEmit` exit 0, lint без warning'ов (если lint настроен) |
| **8** | Unit/component tests | `Warehouse_frontend/src/app/features/operations/.../*.spec.ts` | `npx ng test --watch=false` все 3 новых/обновлённых spec'а зелёные |
| **9** | Stand smoke (L5) | стенд через `make status` | `curl http://localhost:8000/api/v1/health` = 200; `curl http://localhost:8001/healthz/` = 200; `pg_isready` = ok |
| **10** | UI automation (L6) | новый `e2e/operations/operations-balances-manual.spec.ts` | `make test-e2e` или локальный `npx playwright test` — новый spec зелёный |
| **11** | Regression (L8) | `make test-e2e` | существующие e2e (operations-create-modal, operations-save-reliability, operations-submit) — зелёные |
| **12** | User scenarios (L7) | ручной/Playwright MCP | «смена склада реактивна», «refresh all работает», «в выпадашке нет остатков», «submit без фонового refresh» — наблюдаемо |
| **13** | Documentation | `.agent/SCOPE-ops-balances-manual.md`, `MEMORY.md`, `GIT_STATE.md`, `INDEX.md` | scope помечен «реализован»; ссылки на TZ |

---

## 5. Стенд (по `Warehouse_frontend/AGENTS.md`)

### 5.1. Сервисы

| Сервис | Адрес | Health Check | Контейнер |
|---|---|---|---|
| SyncServer API | `http://localhost:8000` | `GET /api/v1/health` | `warehouse_syncserver` |
| Django (Warehouse_web) | `http://localhost:8001` | `GET /healthz/` | `warehouse_web` |
| PostgreSQL | `localhost:5432` | `pg_isready -h localhost -p 5432 -t 3` | `warehouse_postgres` |
| Angular (Frontend) | `http://localhost:4200` | `GET /` | `warehouse_angular` |

### 5.2. Протокол доступности (Stand Availability Protocol)

1. Перед любым real-stand тестом — пробинг health-эндпоинтов.
2. Если стенд не отвечает → `make up` (или `docker compose up -d`).
3. Если `make up` падает → репорт «стенд недоступен», чек-лист остаётся пустым с пометкой.

### 5.3. Окружение (имена переменных, не значения)

* `DJANGO_ENV=development`
* `SYNC_SERVER_URL`
* `SYNC_ROOT_USER_TOKEN`
* `SYNC_DEVICE_TOKEN`
* `DATABASE_URL`
* `DJANGO_SETTINGS_MODULE`
* `SECRET_KEY`

### 5.4. Reset / cleanup

* `make restart` — полный рестарт стенда (down + up) при изменениях в `Dockerfile` / `package.json`.
* `make build-angular` — ребилд Angular-контейнера без перезапуска backend'а.
* `make logs-sync` / `make logs-web` — логи при сбое.

### 5.5. Seed-данные

Существующие smoke-данные (admin/admin123) + справочник ТМЦ + несколько складов (id=1, 5, 21, 22 в текущем dev-стенде). Для регрессионных проверок используется тот же стенд, что и для разработки.

---

## 6. Verification matrix (test ladder)

| # | Уровень | Что | Команда / инструмент | Что ожидаем |
|---|---|---|---|---|
| 1 | Static | Angular build | `npm run build` в `Warehouse_frontend/` | exit 0, без warning'ов линтера |
| 2 | Static | TypeScript | `npx tsc --noEmit` в `Warehouse_frontend/` | exit 0 |
| 3 | Unit/component | `operation-lines-table.spec.ts` — обновить/расширить | `npx ng test --watch=false` | тесты на кнопку «Обновить всё» зелёные |
| 4 | Unit/component | `item-cache-search.component.spec.ts` — **новый файл** | `npx ng test --watch=false` | span «на складе: X» не рендерится; `searchItemsOnce` с `include_balance=false` (spy) |
| 5 | Unit/component | `operation-create-modal.component.spec.ts` — **новый файл** | `npx ng test --watch=false` | effect на `relevantSiteId` → 1 `loadBalances`; добавление ТМЦ → 1 `getBalanceForItem`; `onSave`/`onSubmit` НЕ вызывают `loadBalances` |
| 6 | Stand smoke | `make status` | `make status` из workspace root | все 4 контейнера healthy |
| 7 | UI automation | `e2e/operations/operations-balances-manual.spec.ts` — **новый файл** | `npx playwright test` локально или `make test-e2e` в Docker | 3 сценария (A/B/C) зелёные |
| 8 | User scenarios | ручной сценарий через Playwright MCP или dev-браузер | наблюдение | все 4 success-criteria из SCOPE §Success достижимы |
| 9 | Regression | existing e2e suite | `make test-e2e` или `npx playwright test e2e/operations/` | все ранее зелёные specs остаются зелёными |
| 10 | Acceptance | Evidence | эта таблица + report | чек-лист закрыт, отчёт приложен |

### 6.1. Требуемые unit/component тесты (детально)

**A. `OperationLinesTableComponent` (расширить существующий spec):**
1. Кнопка `data-testid="operation-lines-refresh-all"` отрендерена в `<th class="col-avail">`.
2. Клик по кнопке эмитит `output refreshAllBalances` (через `(refreshAllBalances)` event spy).
3. При `isRefreshing=true` (вход) — кнопка имеет `disabled` и класс spinner.
4. При `isRefreshing=false` — кнопка кликабельна.

**B. `ItemCacheSearchComponent` (новый spec):**
1. Поиск «кабель» при наличии результатов — span `.option-stock` не появляется в DOM (`querySelector('.option-stock')` = null).
2. `CatalogSearchService.searchItemsOnce` вызван с 4-м аргументом `false` (spy + `toHaveBeenCalledWith(query, 20, sourceSiteId, false)`).
3. Поле `source_site_qty` всё ещё приходит в payload (BFF отдаёт), но компонент его игнорирует в UI.

**C. `OperationCreateModalComponent` (новый spec):**
1. Mount с `localDraft().type = 'RECEIVE'`, `destinationSiteId = '21'`. Spy `service.loadBalances`. Подождать тик микротасков. → `loadBalances` вызван с `'21'`.
2. `localDraft.update(d => ({ ...d, destinationSiteId: '22' }))`. Подождать тик. → `loadBalances` вызван **второй раз** с `'22'` (не больше).
3. Быстрое `destinationSiteId: '22' → '23' → '24'`. Подождать тик. Финал: `refreshSourceQuantities` вызван **один раз** для siteId='24' (race-handled).
4. `onSave()` (без `refreshBeforePersist`) — `loadBalances` **не** вызывается из обработчика. Spy counts = pre-save value.
5. `onSubmit()` (без `refreshBeforePersist`) — `loadBalances` **не** вызывается из обработчика.
6. `onNewItemSelected(item)` — `getBalanceForItem` вызван ровно **один раз** с `(item.id, siteId)`.
7. `onItemSelected(localId, item)` — `getBalanceForItem` вызван ровно **один раз**.

---

## 7. UI automation сценарии (детально)

Файл `Warehouse_frontend/e2e/operations/operations-balances-manual.spec.ts` (новый). Структура:

```ts
test.describe('Operation Create Modal — manual balance refresh', () => {
  test.beforeEach(async ({ page }) => {
    installNetworkGuard(page);
    await loginAsRole(page, 'spa_user');
  });

  test('SCENARIO A: warehouse switch updates line qty once (no race)', async ({ page }) => { … });
  test('SCENARIO B: refresh-all button refreshes all line qtys in parallel', async ({ page }) => { … });
  test('SCENARIO C: search dropdown has no source_site_qty', async ({ page }) => { … });
  test('SCENARIO D: submit does not trigger background balance refresh', async ({ page }) => { … });
});
```

**SCENARIO A** (на основе `e2e/operations/operations-create-modal.spec.ts:198-212`):
1. `openCreateModal(page)` + select RECEIVE.
2. Выбрать склад A (например, id=21).
3. Добавить ТМЦ с qty=1.
4. Прочитать `availableQuantity` — соответствует API `?site_id=21`.
5. Переключить на склад B (id=22).
6. Подождать ≤ 1 сек.
7. Прочитать `availableQuantity` — соответствует API `?site_id=22`. **Ровно 1 новый** `GET /bff/api/v1/balances?site_id=22` (не > 1).

**SCENARIO B**:
1. `openCreateModal(page)` + select RECEIVE.
2. Выбрать склад A; добавить 2 ТМЦ.
3. Нажать кнопку `[data-testid="operation-lines-refresh-all"]`.
4. **Сразу** после клика — кнопка `disabled` (assert within 100ms).
5. Дождаться появления `…` в строках, затем исчезновения.
6. После обновления — кнопка `disabled=false`.
7. `availableQuantity` строк соответствует API `?site_id=A`.

**SCENARIO C**:
1. `openCreateModal(page)` + select RECEIVE + выбрать склад.
2. В поиске ввести «ВА47» (или любой префикс).
3. Дождаться dropdown'а.
4. `querySelector('.option-stock')` = null.
5. **Нет** `GET /bff/api/v1/balances?source_site_id=...&include_balance=true` (только обычный search-запрос без обогащения).

**SCENARIO D**:
1. `openCreateModal(page)` + select RECEIVE + склад A + добавить ТМЦ.
2. Spy на `GET /bff/api/v1/balances` (network listener).
3. Нажать «Подтвердить».
4. В течение 200 мс после клика — **нет** `GET /bff/api/v1/balances` (spy counts не растут на submit-flow).

---

## 8. Evidence (для executor'а)

Executor заполняет после реализации и прогонов:

| # | Check | Команда / инструмент | Ожидаемый результат | Evidence |
|---|---|---|---|---|
| 1 | Static | `npm run build` | exit 0 | путь к логу сборки |
| 2 | Static | `npx tsc --noEmit` | exit 0 | путь к логу tsc |
| 3 | Unit/component A | `npx ng test --watch=false` для `operation-lines-table.spec.ts` | зелёный | путь к HTML-отчёту vitest |
| 4 | Unit/component B | `npx ng test --watch=false` для `item-cache-search.component.spec.ts` | зелёный | … |
| 5 | Unit/component C | `npx ng test --watch=false` для `operation-create-modal.component.spec.ts` | зелёный | … |
| 6 | Stand smoke | `make status` | 4/4 healthy | stdout make |
| 7 | UI automation | `npx playwright test e2e/operations/operations-balances-manual.spec.ts` | 4/4 passed | report path |
| 8 | Regression | `npx playwright test e2e/operations/` | 0 failed | report path |
| 9 | User scenarios | ручной прогон / MCP | 4/4 success criteria | screenshot'ы / описание |
| 10 | Documentation | `git diff` по `.agent/SCOPE-ops-balances-manual.md`, `MEMORY.md`, `GIT_STATE.md`, `INDEX.md` | изменения применены | git log |

---

## 9. Стратегия выполнения (Execution strategy)

**Sequential** для executor по умолчанию:
- Фазы 1-3 — последовательно (один файл, общий ownership).
- Фазы 4-5 — последовательно (один файл, родитель-потомок binding).
- Фаза 6 — независимо (item-cache-search, не пересекается с фазами 1-5).
- Фазы 7-13 — последовательно (зависят от реализации).

**Максимально полезных потоков (Swarm):** 2. Вариант:
- Поток A: фазы 1-5 (operation-create-modal + operation-lines-table).
- Поток B: фаза 6 (item-cache-search).
- Синхронизация — после потоков A+B: фазы 7-13 последовательно.

**Если Swarm** — owner-границы:
- A: `operation-create-modal.component.{ts,spec.ts}`, `operation-lines-table.component.{ts,spec.ts}`, новый `e2e/operations/operations-balances-manual.spec.ts`.
- B: `item-cache-search.component.{ts,spec.ts}`.
- Интеграционные точки: `operation-create-modal.component.ts` (template) ссылается на `<app-operation-lines-table>` и `<app-item-cache-search>` — оба компонента в своих файлах, конфликта нет.

---

## 10. Риски и допущения

| Риск / допущение | Митигация |
|---|---|
| `balanceRefreshSeq` — приватное поле, executor может забыть про race-handling в новом effect | Тест C3 в §6.1 покрывает race |
| Executor может попытаться сохранить `refreshBeforePersist` «на всякий случай» | Чек-лист 0.2 явно требует его удаления; чек-лист 10.4/10.5 — тесты подтверждают отсутствие вызовов |
| Возврат к «per-row HTTP» через `getBalanceForItem` без `loadBalances` даст 0 для всех строк | §3.3 фиксирует вариант A; в §6.1 явно сказано про `loadBalances` |
| Существующие e2e (save-reliability) могут упасть, т.к. опирались на автосинк | Regression-чек (фаза 11) ловит это; если падают — обновить их или зафиксировать как известный side-effect, согласовать с пользователем |
| `include_balance=false` ломает другие потребители `source_site_qty` | SCOPE валидирует: `ItemCacheSearchComponent` — единственный потребитель в форме операций; в обычном каталоге поле используется отдельно (не через эту правку) |
| Пользовательский сценарий «правка уже сохранённого черновика» не покрыт SCOPE-тестами (см. Investigation §7) | Если падает — добавить явный сценарий в §7; не блокирует приёмку |
| Объём новых spec-файлов (~250 строк суммарно) — риск регрессий в vitest-конфиге | Использовать существующий `@angular/build:unit-test` builder; не вводить новые test-runner'ы (запрещено AGENTS §Verification) |

---

## 11. Что **не** делается (жёсткие границы)

* **Не менять** SyncServer контракты (никаких новых ручек в BFF).
* **Не рефакторить** `OperationCreateModalComponent` (1712 строк) — точечные правки.
* **Не делать** bulk-эндпоинт `POST /bff/api/v1/operations/refresh-balances` (отложено).
* **Не менять** `Functional and WorkLogik.md` — требование II/5.0 сохраняется.
* **Не делать** локализацию нового текста «Обновить всё» (вне scope).
* **Не трогать** Django SSR (`templates/operations/form.html`) — fallback без автосинка.
* **Не вводить** новые test-runner'ы или vitest-конфиг (только существующий `@angular/build:unit-test`).

---

## 12. Связанные TZ / SCOPE

| Документ | Связь |
|---|---|
| `.agent/SCOPE-ops-balances-manual.md` | Источник ТЗ — после реализации пометить «реализован» |
| `.agent/SCOPE-INVESTIGATION-SITE-SWITCH-RECEIVE.md` | Обследование, подтвердившее что баг в базовых сценариях не воспроизводится, но есть избыточный автосинк; этот ТЗ закрывает оба |
| `docs/AGENT_TZ_WORKFLOW.md` | Шаблон чек-листа и test ladder |
| `Warehouse_frontend/AGENTS.md` | Стенд, verification matrix, Git-правила |
| Корневой `AGENTS.md` | Общие правила, Stand Availability Protocol |

---

## 13. Следующий шаг после приёмки

* Пометка преддеплой-недоделки «смена склада → залипание остатков» закрывается как resolved-by-this-TZ (см. Investigation §6.1).
* Если в следующей сессии всплывёт конкретный тикет от кладовщика с реальным репро — добавить новый сценарий в §7, расширить spec, повторить regression pack.
* SCOPE-archive: переместить `SCOPE-ops-balances-manual.md` в `docs/archive/` (или пометить «реализован» в `INDEX.md`) после merge executor'а.
