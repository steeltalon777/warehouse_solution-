# Investigation: реактивность таблицы операций на смену склада в RECEIVE

**Дата:** 2026-08-07
**Тип:** обследование (не фикс)
**Источник:** пометка преддеплой-исправления в учёте недоделок
**Файл-источник жалобы:** `Warehouse_frontend/src/app/features/operations/components/operation-create-modal/operation-create-modal.component.ts`
**Связанный scope:** `.agent/SCOPE-ops-balances-manual.md` (пересекается, но не дублирует)

---

## 1. Заявленная проблема

> При смене склада в операции приход (RECEIVE) накладная обновляется, но таблица операций и остатки не реактивны на смену склада; остатки приходят на исходно выбранный склад.

**Предварительная диагностика автора пометки (статический анализ):**
- `site` хранится в `signal localDraft`, передаётся в `lines` через `computed relevantSiteId()` (строки 824-827).
- `<select>` использует `[ngModel]="logicalWarehouseSiteId()" (ngModelChange)="onLogicalWarehouseSiteChange($event)"` (строка 109).
- Хендлеры `onLogicalWarehouseSiteChange` / `onSourceSiteChange` / `onDestinationSiteChange` не обновляют `lines.sourceSiteQuantity` / `lines.availableQuantity` напрямую — данные в таблице «залипают» на первоначальный склад.
- Эффект автосинка балансов на смену склада (строки ~1175-1214) — отдельная цепочка, потенциально тоже не реактивна на этот путь.

**Приоритет (по пометке):** 🔴 преддеплой — UX-блокер для кладовщика.

---

## 2. Цель обследования

Подтвердить или опровергнуть наблюдение в живом стенде. На выходе — не фикс, а:
1. Подтверждённый статус (воспроизводится / не воспроизводится / воспроизводится в частном сценарии).
2. Карта кодовых узлов, через которые должен идти сигнал смены склада до `lines.availableQuantity`.
3. Список возможных первопричин с указанием, какие из них подтверждены.
4. Рекомендация для следующей сессии (фиксить / закрыть / расширить обследование).

---

## 3. Карта задействованного кода

| Слой | Файл | Ключевые узлы |
|---|---|---|
| UI select (RECEIVE) | `operation-create-modal.component.ts` | строка 109: `<select [ngModel]="isMove() ? (localDraft().sourceSiteId ?? '') : (logicalWarehouseSiteId() ?? '')" (ngModelChange)="isMove() ? onSourceSiteChange($event) : onLogicalWarehouseSiteChange($event)">` |
| Computed warehouse | `operation-create-modal.component.ts` | строки 824-833: `relevantSiteId`, `logicalWarehouseSiteId` |
| Хендлеры | `operation-create-modal.component.ts` | строки 1340-1353: `onSourceSiteChange`, `onLogicalWarehouseSiteChange`, `onDestinationSiteChange` |
| Effect автосинка | `operation-create-modal.component.ts` | строки 1175-1214: effect на `relevantSiteId` → `loadBalances` → `refreshSourceQuantities` |
| Per-line обновление | `operation-create-modal.component.ts` | строки 1276-1289: `updateLineStockHint`; строки 1291-1311: `refreshSourceQuantities` |
| BFF / SyncServer | `Warehouse_web/apps/sync_client/balances_api.py`, `Warehouse_web/apps/bff_api/balances_views.py` | `GET /bff/api/v1/balances?site_id=X&item_id=Y` — фильтрует по `site_id` на стороне SyncServer |
| Service (frontend) | `Warehouse_frontend/src/app/core/services/operations.service.ts` | строки 702-725: `loadBalances(siteId)` → `this.balances.set(rows)`; `getBalanceForItem(itemId, siteId)` |
| Read отображение | `operation-lines-table.component.ts` | строки 449-451: `availableQuantity(line) = line.availableQuantity ?? 0` |
| Create payload | `operations.service.ts` | строки 909-948: для RECEIVE `site_id = safeId(draft.destinationSiteId)`, `destination_site_id = draft.destinationSiteId` |

---

## 4. Статический анализ потока данных (RECEIVE)

Шаг 1. **Пользователь меняет склад в `<select>` (строка 109).**
Шаг 2. `ngModelChange` → `onLogicalWarehouseSiteChange(newValue)` (строка 1344-1349):
```ts
this.localDraft.update(d => d.type === 'RECEIVE'
  ? { ...d, destinationSiteId: value || null }
  : { ...d, sourceSiteId: value || null }
);
```
Шаг 3. `localDraft` обновляется → зависимые `computed` пересчитываются:
- `relevantSiteId()` (для RECEIVE → `destinationSiteId`)
- `isObjectSourceFlow()` → `false` для RECEIVE
- `hasPrefilledAssetLine()` → зависит от флага в `localDraft`
Шаг 4. Effect (строки 1175-1214) **должен** перезапуститься, потому что читает `relevantSiteId()`. Внутри:
- Если есть `siteId` и это не placeholder — `++this.balanceRefreshSeq`, `loadBalances(siteId)`, затем `refreshSourceQuantities()`.
- `refreshSourceQuantities()` итерирует `localDraft().lines` и для каждой строки с `itemId` обновляет `availableQuantity` и `sourceSiteQuantity` через `getBalanceForItem(itemId, siteId)`.

**Промежуточный вывод по статике:** код выглядит рабочим. Реактивность в Angular Signals идёт через dependency tracking, и effect на `relevantSiteId()` должен перезапускаться при изменении `destinationSiteId` в RECEIVE.

---

## 5. Динамическая проверка (Playwright + живой dev-стенд)

### 5.1 Методика

- Стенд: `make status` — все 4 контейнера healthy.
- Авторизация: Django admin (admin/admin123) — для удобства, без X-user-токенов.
- Воспроизведение: временный spec в `/tmp/opencode/repro-site-switch/`, запуск `npx playwright test` с индивидуальной конфигурацией.
- Сценарий: открыть «Создать операцию» → RECEIVE → выбрать склад A → добавить ТМЦ → переключиться на склад B → наблюдать DOM, BFF-запросы и `availableQuantity`.
- Скриншоты: `/tmp/opencode/repro-site-switch/scenario-{A,B,C}.png`.

### 5.2 Сценарий A — смена склада ДО добавления ТМЦ

| Шаг | Действие | Наблюдение |
|---|---|---|
| 1 | `<select>` → `sa-smoke-847 site` (id=22) | `GET /balances?site_id=22` — 1 запрос |
| 2 | `<select>` → `sa-smoke-817 site` (id=21) | `GET /balances?site_id=21` — 2-й запрос |
| 3 | Поиск «ВА47» → клик «ВА47-63N 3Р 40А» | строка появилась |
| 4 | qty = 1 | `availableQuantity` в DOM = **"5"** (stock at site 21) |

**Итог:** эффект сработал, `availableQuantity` отображает stock нового склада.

### 5.3 Сценарий B — быстрые переключения (race)

| Шаг | Действие | Наблюдение |
|---|---|---|
| 1 | Выбор A, добавление ТМЦ, qty=1 | `availableQuantity` = "1" (stock at 22) |
| 2 | Быстрое переключение: 22 → 21 → 22 → 21 (без wait) | через 2 секунды `availableQuantity` = **"5"** (stock at 21) |

**Итог:** `balanceRefreshSeq` корректно отсекает устаревшие `then`-коллбэки — финальное состояние соответствует последнему выбранному складу. Гонок нет.

### 5.4 Сценарий C — несколько ТМЦ и смена склада между ними

| Шаг | Действие | Наблюдение |
|---|---|---|
| 1 | Склад A (22), добавление ТМЦ «ВА47-63N 3Р 40А», qty=1 | `availableQuantity` = "1" |
| 2 | Переключение на B (21) | `availableQuantity` = **"5"** (для уже добавленной строки) |
| 3 | Добавление второй ТМЦ | строка получила qty для B |

**Итог:** ранее добавленные строки реактивно обновляются, новые получают qty для текущего склада. Всё работает.

### 5.5 Сценарий D — создание/правка черновика (save → reopen → switch)

В пометке автор предполагал, что эффект может не сработать при редактировании **существующего** черновика. Попытка воспроизвести: после `Сохранить черновик` модалка остаётся открытой, кнопки «Отмена» нет (она называется «Закрыть» / иконка ×), что усложнило сценарий. Прямой замер того, что происходит при переоткрытии уже сохранённого черновика, не проведён — требует ручной возни с locator'ами.

> Это единственный не покрытый динамикой путь. См. §7 «Что не обследовано».

---

## 6. Выводы

### 6.1 Воспроизводимость

**Базовый путь (создание нового черновика RECEIVE) — баг НЕ воспроизводится.**
Эффект на `relevantSiteId()` срабатывает, `loadBalances(siteId)` уходит на BFF с правильным `site_id`, `refreshSourceQuantities()` обновляет `availableQuantity`/`sourceSiteQuantity` для всех строк черновика.

### 6.2 Правки к предварительной диагностике

| Утверждение автора пометки | Статус |
|---|---|
| `onLogicalWarehouseSiteChange` не обновляет `lines` напрямую | **Подтверждено** — так и есть (строки 1344-1349). |
| `onSourceSiteChange` не обновляет `lines` напрямую | **Подтверждено** (строки 1340-1342). |
| `onDestinationSiteChange` не обновляет `lines` напрямую | **Подтверждено** (строки 1351-1353). |
| Данные в таблице «залипают» на первоначальный склад | **НЕ подтверждено** в сценариях A/B/C. Effect в строках 1175-1214 компенсирует это. |
| Effect потенциально не реактивен на этот путь | **НЕ подтверждено** — effect реактивен в трёх протестированных сценариях. |

### 6.3 Возможные причины, по которым пользователь мог увидеть «залипание»

Не подтверждено динамикой, но логически возможно:

1. **Рассинхрон UX-восприятия:** между выбором нового склада и обновлением `availableQuantity` проходит ~50-300 мс (HTTP-запрос `GET /balances`). Кладовщик может интерпретировать кратковременное «0» или «1» (значение предыдущего склада, пока грузится новое) как «не обновилось». Мигает `isBalanceRefreshing=true` → `…` (строка 134 шаблона) — это видно.
2. **Совпадение значений:** если на обоих складах qty одинаковое (например, оба = 0), пользователь видит то же число и считает, что обновления не было. Тест на 22/21 показал 1 и 5 — наглядная разница. Но если на обоих складах 0 — кладовщик не отличит «не обновилось» от «обновилось на 0».
3. **Сохранённый черновик с устаревшими `availableQuantity`:** эффект при смене склада вызывает `refreshSourceQuantities`, которая **перезаписывает** `availableQuantity` для всех строк с `itemId`. Но если строка добавлена как `inlineItem` (временная ТМЦ) — у неё нет `itemId`, и `refreshSourceQuantities` оставляет её без изменений (строка 1299: `if (!l.itemId) return l;`). Если у кладовщика смешанный черновик (обычные + inline) и при смене склада он смотрит на inline-строку — её `availableQuantity` действительно останется прежним. Это не баг, а фича (у inline-ТМЦ ещё нет warehouse-привязки), но визуально может выглядеть как «залипание».
4. **`sourceSiteQuantity` vs `availableQuantity`:** модель `OperationLineDraftVm` (operations.models.ts:309-311) различает `availableQuantity` и `sourceSiteQuantity`. `refreshSourceQuantities` обновляет оба (`availableQuantity: qty, sourceSiteQuantity: qty`). Но `submit` отправляет только `qty` (operations.service.ts:961), а `availableQuantity`/`sourceSiteQuantity` в payload не уходят. То есть **на сервер** уходит чистое количество, введённое кладовщиком; warehouse-сторона берётся из `destinationSiteId` в корне draft'а. Это значит, что даже если бы `availableQuantity` в UI не обновился, **на submit это не повлияло бы** — `destinationSiteId` уже корректно сидит в `localDraft`.

### 6.4 Соприкосновение с SCOPE-ops-balances-manual.md

SCOPE-ops-balances-manual.md (от 2026-07-14, 147 строк) планирует:
- удалить `effect()` на `relevantSiteId()` (строки 963-1002 в SCOPE; в текущем HEAD — 1175-1214);
- удалить `refreshBeforePersist()` (строки 1049-1062 в SCOPE; в текущем HEAD — 1317-1330, всё ещё вызывается из `onSave`/`onSubmit`);
- оставить точечный автозапрос при добавлении/выборе ТМЦ и при смене склада;
- добавить кнопку «Обновить всё».

**SCOPE не выполнен** (это видно по коду: `refreshBeforePersist` жив, `effect` на `relevantSiteId` жив, вызовы в `onSave`/`onSubmit` остались).

**Преддеплой-пометка и SCOPE — про разное:**
- SCOPE — про убрать **избыточный** автосинк.
- Пометка — про **отсутствующую** реактивность.

По динамике: реактивность в базовых сценариях есть, избыточность автосинка (refreshBeforePersist на каждый save/submit) — действительно отдельная история, и SCOPE по ней в работе.

---

## 7. Что не обследовано

- **Сценарий D (правка существующего сохранённого черновика)** — динамикой не покрыт. Стоит закрыть в следующей сессии, если есть подозрение именно на этот путь. Подозрение слабое: эффект `draft()` (строки 1149-1173) переписывает `localDraft` из `this.draft()` входа только когда меняется входной `draft()`. Если родитель при правке не меняет `editingDraft`, этот эффект не перезапускается и не конфликтует с effect на `relevantSiteId`. Но это гипотеза — не замер.
- **MOVE с двумя `<select>`** — `onDestinationSiteChange` обновляет `destinationSiteId`, но `relevantSiteId` для MOVE = `sourceSiteId`, поэтому effect на смену **destination** в MOVE не сработает. Это **не баг** для отображения `availableQuantity` (потому что `availableQuantity` берётся со **source** склада, который в MOVE и есть «источник»), но это расхождение с пометкой (пометка — про RECEIVE).
- **WRITE_OFF с переключателем «Со склада / С объекта»** — `onWriteOffSourceChange` (строки 1359-1365) при переключении на «С объекта» очищает `sourceSiteId` если он не задан. Effect тогда попадёт в ветку `else` (строка 1197-1213) и сбросит `availableQuantity` в 0. Это намеренное поведение для object-source flow, но кладовщик может воспринять как «потерял остатки».
- **ISSUE_RETURN** — effect в строке 1183-1186 уходит в early return для object-source flow; `availableQuantity` остаётся как назначенный на объект. Это by design.
- **Slow network** — не симулировали. На медленной сети `…` (loading) видно дольше, и в этом промежутке кладовщик может кликнуть submit. `refreshBeforePersist` (SCOPE-ом помечен на удаление) компенсирует это — но в текущем HEAD он есть. Это, наоборот, **защита** от рассинхрона.
- **Stale-version** при смене склада — не проверялось.

---

## 8. Рекомендация

| Действие | Где | Почему |
|---|---|---|
| **Закрыть пометку как «не воспроизводится в базовых сценариях»** | в учёте недоделок | В сценариях A/B/C effect работает корректно; дополнительный HTTP-запрос на смену склада уходит, `availableQuantity` обновляется. |
| **Сначала закрыть SCOPE-ops-balances-manual.md** (он блокирует реальные UX-проблемы: «иногда актуально, иногда нет», «гонки», «на складе: X в выпадашке») | отдельный TZ, ссылающийся на этот scope | SCOPE уже проработан, acceptance criteria понятны, приоритет 🔴 совпадает с пометкой. Когда он уйдёт, поведение автосинка станет явным и предсказуемым — и любые оставшиеся аномалии будет легче локализовать. |
| **Если у кладовщика есть конкретный тикет** (например, номер операции, имя склада, ожидаемое vs фактическое поведение) — повторить обследование прицельно | в следующей сессии | Без конкретного тикета сценарий D и любые edge-кейсы — это гадание. |
| **Добавить unit-тест** на effect: «смена `relevantSiteId` → новый `loadBalances(siteId)` → `refreshSourceQuantities`» | `operation-create-modal.component.spec.ts` (сейчас отсутствует) | Компонент 1712 строк без прямых unit-тестов — это само по себе рискованно. Тест закроет регрессию, если кто-то решит «оптимизировать» effect. |

**Альтернативный ход (если пользователь не согласен закрыть):** завести TZ в `docs/TZ-OPERATION_MODAL_SITE_SWITCH_REACTIVITY.md` с минимальным фиксом — добавить **явный reset** строк при смене склада (как предлагает автор пометки: «effect() на relevantSiteId или явный reset lines.update(...)»). Это и сейчас работает (effect), но явный reset даст независимый от Angular Signals страховочный путь и упростит диагностику будущих багов. Минимально-инвазивная правка — добавить `effect(() => { const siteId = this.relevantSiteId(); if (siteId) { /* явный refresh lines без loadBalances */ } })` или хендлер `onLogicalWarehouseSiteChange` дополнить `this.localDraft.update(d => ({ ...d, lines: d.lines.map(l => l.itemId ? { ...l, availableQuantity: 0, sourceSiteQuantity: 0 } : l) }))`. Это **дополнительная** страховка, а не исправление реального бага.

---

## 9. Артефакты обследования

| Артефакт | Расположение |
|---|---|
| Временный Playwright spec | удалён после прогона; логи в `/tmp/opencode/repro-site-switch/results/` (можно оставить как локальный трейс). |
| Скриншоты | `/tmp/opencode/repro-site-switch/scenario-{A,B,C}.png`, `edit-after-switch.png` |
| Целевой файл | `Warehouse_frontend/src/app/features/operations/components/operation-create-modal/operation-create-modal.component.ts` |
| Связанный scope | `.agent/SCOPE-ops-balances-manual.md` |
| Функциональные требования | `Functional and WorkLogik.md` п. II/5.0, II/5.1 |

---

## 10. Резюме (одной строкой для учёта)

> Преддеплой-пометка о нереактивности таблицы на смену склада в RECEIVE **не воспроизводится** в базовых сценариях (новый черновик, pick A → add → switch B): effect на `relevantSiteId` отрабатывает, `GET /bff/api/v1/balances?site_id=B` уходит, `lines.availableQuantity` обновляется. Фиксить пока нечего; **приоритетный преддеплой-кандидат** — довести до конца SCOPE-ops-balances-manual.md (убрать `refreshBeforePersist`, добавить кнопку «Обновить всё», скрыть «на складе: X» в выпадашке).
