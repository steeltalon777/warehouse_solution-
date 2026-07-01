# TZ: Переработка слияния ТМЦ и категорий через batch-буфер

## Execution Strategy

- [ ] 🟢 Parallel execution recommended
- **Reason:** Stage 2 (Angular-инфраструктура) и Stage 3 (визуальные индикаторы) можно делать параллельно после Stage 1. Внутри Stage 3 юниты A (tree-node) и B (модалки) — независимы по файлам.

## Execution Checklist

- [x] 0. Context verified
- [x] 1. Stage 1: SyncServer — merge action в batch-контракте (commit 3782dda)
- [x] 2. Stage 2A: Angular — расширение моделей (merge action, payload)
- [x] 3. Stage 2B: Angular — sessionStorage-персистентность буфера
- [x] 4. Stage 3A: Angular — визуальный индикатор merge в дереве
- [x] 5. Stage 3B: Angular — переделка merge-модалок под буфер
- [x] 6. Stage 3C: Angular — интеграция модалок со страницей номенклатуры
- [x] 7. Stage 4: Angular — `applyBatch` с поддержкой merge
- [x] 8. Unit/component tests (Angular build OK, 7.3s, 0 errors)
- [x] 9. SyncServer unit tests (pytest tests/test_catalog_batch_merge.py 5/5 passed)
- [x] 10. Stand smoke tests (реальное слияние через Angular UI) — ✅ Playwright-спека `e2e/regression/merge-batch.smoke.spec.ts` проходит (run5: `1 passed`, 16.8s). Полный flow: seed 2 ТМЦ (category_id=65 «Канцелярские товары») → expand категории → выбрать source → кнопка «Слияние» → модалка → поиск target → submit «Слияние ТМЦ» → apply-all (window.confirm auto-accept через `page.on('dialog')`) → reload → source деактивирован. PG подтверждает: src/tgt `is_active=f`. Предыдущий «UI-блокер» оказался цепочкой багов в самой спеке (wrong category_id=41 вместо 65; не раскрыт правильный path дерева; локатор модалки на host с height:0 вместо `.modal-overlay`; класс `.search-result-item` вместо `.search-result`; авто-дисмисс `window.confirm()` Playwright'ом без `page.on('dialog')`) — код-бага в MERGE_BATCH нет.
- [ ] 11. Regression checks (Django SSR merge НЕ сломан, create/update/delete НЕ сломаны)
- [ ] 12. Documentation updated
- [ ] 13. Final acceptance review complete

---

## Диагноз (из предыдущего анализа)

| Слой | Статус |
|------|--------|
| SyncServer `merge_items` / `merge_categories` | ✅ Логика верна |
| Django BFF | ✅ Проксирует корректно |
| Django SSR | ✅ После merge делает redirect |
| Angular модалки | 🔴 Вызывают API напрямую, минуя буфер |
| Angular страница | 🔴 `mergeComplete` только закрывает модалку, не обновляет дерево |
| `allCategories` в модалке категорий | 🔴 Не проброшен |

**Цель:** привести merge к модели batch-буфера — как create/update/deactivate/delete. Пользователь набирает изменения (включая слияния), видит их в дереве, применяет одной кнопкой «Применить». Буфер хранится в `sessionStorage` и переживает навигацию.

---

## Архитектура целевого потока

```
Пользователь выбирает source ТМЦ/категорию
  → жмёт «Слияние»
  → модалка: поиск target, выбор, комментарий
  → жмёт «Слияние ТМЦ» / «Слияние категории»
  → changeBuffer.addChange({ action: 'merge', entityId: source, payload: {target, comment} })
  → модалка закрывается
  → дерево: source показывает pending-merge индикатор
  → pending-changes-bar: счётчик +1
  → buffer синхронизируется в sessionStorage
  
Пользователь переключается на /operations/, возвращается в /nomenclature/
  → buffer восстанавливается из sessionStorage
  → дерево показывает pending-merge индикатор
  
Пользователь жмёт «Применить»
  → applyBatch отправляет ВСЕ изменения (включая merge) одним запросом
  → SyncServer обрабатывает merge ПОСЛЕ create/update/deactivate
  → успех → clearAll + reloadBootstrap
  → дерево обновлено, source исчез
```

---

## Stage 1: SyncServer — merge action в batch-контракте

### 1.1 Схема `BatchChangeMerge`

**Файл:** `SyncServer/app/schemas/catalog.py`

Добавить после `BatchChangeDelete` (~строка 453):

```python
class BatchChangeMergePayload(BaseModel):
    target_entity_id: int
    comment: str | None = None

class BatchChangeMerge(BatchChangeBase):
    action: Literal["merge"] = "merge"
    entity_id: int  # source entity id (ТМЦ или категория, которую сливаем)
    payload: BatchChangeMergePayload
```

Обновить union-тип `BatchChange` (~строка 457):

```python
BatchChange = BatchChangeCreate | BatchChangeUpdate | BatchChangeDeactivate | BatchChangeDelete | BatchChangeMerge
```

### 1.2 Обработка merge в `apply_batch()`

**Файл:** `SyncServer/app/services/catalog_admin_service.py`

В методе `apply_batch()` (~строка 782) добавить извлечение merge-изменений и их обработку **после** всех create/update/deactivate/delete — в порядке: сначала item-merge, потом category-merge (чтобы items не остались в удалённой категории).

Добавить в `summary` ключ `"merge": 0`.

После обработки всех create/update/deactivate/delete (~строка 838, перед `return results, summary`):

```python
# Process merges: items first, then categories
item_merges = [c for c in payload.changes if c.entity_type == "item" and c.action == "merge"]
category_merges = [c for c in payload.changes if c.entity_type == "category" and c.action == "merge"]

for change in item_merges + category_merges:
    result = await self._apply_merge_change(uow, change, local_id_map, identity.user_id)
    results.append(result)
    if result.status == "applied":
        summary["merge"] += 1
    else:
        summary["error"] += 1
```

Добавить приватный метод `_apply_merge_change()`:

```python
async def _apply_merge_change(
    self, uow, change: BatchChangeMerge, local_id_map: dict, user_id: UUID
) -> BatchChangeResult:
    try:
        payload = change.payload
        if change.entity_type == "item":
            await self.merge_items(
                uow,
                source_item_id=change.entity_id,
                target_item_id=payload.target_entity_id,
                comment=payload.comment,
                resolved_by_user_id=user_id,
            )
        elif change.entity_type == "category":
            await self.merge_categories(
                uow,
                source_category_id=change.entity_id,
                target_category_id=payload.target_entity_id,
                comment=payload.comment,
                resolved_by_user_id=user_id,
            )
        return BatchChangeResult(
            local_id=change.local_id,
            entity_type=change.entity_type,
            action="merge",
            status="applied",
            entity_id=change.entity_id,
        )
    except HTTPException as exc:
        return BatchChangeResult(
            local_id=change.local_id,
            entity_type=change.entity_type,
            action="merge",
            status="error",
            error_code=str(exc.status_code),
            error_message=exc.detail,
        )
```

### 1.3 Тесты

**Файл:** `SyncServer/tests/test_catalog_merge.py` или новый `SyncServer/tests/test_catalog_batch_merge.py`

Добавить тесты:
- merge item через batch (успех)
- merge category через batch (успех)
- merge item в batch вместе с create target item (local_id_map)
- ошибка merge (несуществующий target) не ломает весь batch
- merge в batch НЕ ломает create/update в том же batch

**Acceptance criteria:**
- `BatchChangeMerge` валидируется Pydantic
- `apply_batch` обрабатывает merge после остальных действий
- Item merge выполняется с переносом балансов
- Category merge переносит ТМЦ и подкатегории
- Ошибка merge возвращает `status: "error"`, не рушит транзакцию
- `python -m pytest tests/test_catalog_merge.py tests/test_catalog_batch_merge.py -v` — pass

---

## Stage 2A: Angular — расширение моделей

**Файл:** `Warehouse_frontend/src/app/core/models/nomenclature.models.ts`

1. Расширить `CatalogPendingAction` (строка 82):
```typescript
export type CatalogPendingAction = 'create' | 'update' | 'deactivate' | 'delete' | 'merge';
```

2. Документировать `payload` для merge в `CatalogPendingChange` (строка 114-120) — комментарий над интерфейсом:
```typescript
/** 
 * При action='merge':
 *   payload = { target_entity_id: string, source_entity_id: string, comment?: string }
 */
export interface CatalogPendingChange { ... }
```

3. Расширить `CatalogBatchChange.action` (строка 134):
```typescript
action: 'create' | 'update' | 'deactivate' | 'delete' | 'merge';
```

**Acceptance criteria:**
- `npm run build` проходит без ошибок

---

## Stage 2B: Angular — sessionStorage-персистентность буфера

**Файл:** `Warehouse_frontend/src/app/core/services/catalog-change-buffer.service.ts`

### Изменения:

1. Добавить приватные методы `_saveToStorage()` / `_loadFromStorage()`:

```typescript
private readonly STORAGE_KEY = 'catalog_pending_changes';

private _saveToStorage(): void {
  try {
    sessionStorage.setItem(this.STORAGE_KEY, JSON.stringify(this._changes()));
  } catch { /* quota exceeded — silently ignore */ }
}

private _loadFromStorage(): CatalogPendingChange[] {
  try {
    const raw = sessionStorage.getItem(this.STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}
```

2. В конструкторе — восстановить из `sessionStorage`:
```typescript
constructor() {
  const stored = this._loadFromStorage();
  if (stored.length > 0) {
    this._changes.set(stored);
  }
}
```

3. Во всех мутирующих методах (`addChange`, `removeChange`, `clearAll`, `setChanges`) — вызывать `_saveToStorage()` после изменения сигнала.

**Acceptance criteria:**
- После добавления изменения → оно появляется в `sessionStorage`
- После перезагрузки страницы (F5) → изменения восстанавливаются
- После закрытия вкладки и открытия новой → буфер пуст
- `clearAll()` очищает и сигнал, и `sessionStorage`

---

## Stage 3A: Angular — визуальный индикатор merge в дереве

### 3A.1 CSS-класс и бейдж

**Файл:** `Warehouse_frontend/src/app/features/nomenclature/catalog-tree-node/catalog-tree-node.ts`

Добавить в шаблон (строка 14) класс для merge:

```html
[class.pending-merge]="node().pendingAction === 'merge'"
```

Добавить бейдж (после строки 49, перед блоком `!isActive`):

```html
@if (node().pendingAction === 'merge') {
  <span class="wh-badge badge badge-merge">сливается</span>
}
```

И убрать бейдж «неактивно» для merge (строка 51), чтобы не дублировался:

```html
@if (!node().isActive && node().pendingAction !== 'merge') {
  <span class="wh-badge badge badge-inactive">неактивно</span>
}
```

Также убрать бейдж «изменено» для merge (строка 48), чтобы приоритет был у «сливается»:

```html
@if (node().dirty && node().pendingAction !== 'delete' && node().pendingAction !== 'merge') {
  <span class="wh-badge badge badge-dirty">изменено</span>
}
```

Добавить CSS:

```css
.tree-row.pending-merge {
  background: #F0FDF4;
  border-color: #86EFAC;
}
.tree-row.pending-merge .node-name { color: #166534; }

.badge-merge {
  background: #DCFCE7;
  color: #166534;
  font-size: 10px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 999px;
}
```

### 3A.2 Обновление `_legacy-aliases.scss`

**Файл:** `Warehouse_frontend/src/styles/_legacy-aliases.scss`

Добавить:
```scss
.badge-merge { background: #dcfce7; color: #166534; }
```

### 3A.3 Дерево НЕ скрывает inactive при pending merge

Проверить в `NomenclatureService.buildTree()` (строка 447, 468):

```typescript
if (!cat.is_active && !buffer.hasPending(cat.id, 'category')) continue;
// ...
if (!item.is_active && !buffer.hasPending(item.id, 'item')) continue;
```

Эти строки УЖЕ корректны: если сущность inactive и есть pending change — она остаётся в дереве. Для merge это будет работать, т.к. source будет inactive (is_active=false в данных бэкенда), но buffer.hasPending вернёт true.

**Acceptance criteria:**
- При добавлении merge-изменения source в дереве получает зелёный фон + бейдж «сливается»
- Имя source затемняется (pending-merge класс)
- Бейджи «изменено» и «неактивно» НЕ показываются одновременно с «сливается»
- После успешного applyBatch source исчезает из дерева

---

## Stage 3B: Angular — переделка merge-модалок под буфер

### 3B.1 Merge Item Modal

**Файл:** `Warehouse_frontend/src/app/features/nomenclature/merge-item-modal/merge-item-modal.ts`

**Убрать:**
- Инжект `CatalogAdminService` (строка 165)
- Вызов `this.catalogAdmin.mergeItem()` в `onSubmit()` (строка 231-238)

**Добавить:**
- Новый output `mergeRequested` с типом `{ sourceId: string; targetId: string; comment?: string }`

```typescript
readonly mergeRequested = output<{ sourceId: string; targetId: string; comment?: string }>();
readonly mergeComplete = output<void>();  // оставить для закрытия модалки
```

**В `onSubmit()`:**
```typescript
async onSubmit(): Promise<void> {
  const target = this.selectedTarget();
  if (!target || !this.canSubmit()) return;
  
  this.mergeRequested.emit({
    sourceId: String(this.sourceItem().id),
    targetId: String(target.id),
    comment: this.comment || undefined,
  });
  this.mergeComplete.emit();
}
```

Убрать `isSubmitting` / `error` — они больше не нужны (модалка не делает API-запросов). Оставить возможность закрытия по cancel.

### 3B.2 Merge Category Modal

**Файл:** `Warehouse_frontend/src/app/features/nomenclature/merge-category-modal/merge-category-modal.ts`

Аналогичные изменения:
- Убрать инжект `CatalogAdminService`
- Добавить `mergeRequested` output
- `onSubmit()` эмитит `mergeRequested` + `mergeComplete`

```typescript
readonly mergeRequested = output<{ sourceId: string; targetId: string; comment?: string }>();

async onSubmit(): Promise<void> {
  const target = this.selectedTarget();
  if (!target) return;
  
  this.mergeRequested.emit({
    sourceId: String(this.sourceCategory().id),
    targetId: String(target.id),
    comment: this.comment() || undefined,
  });
  this.mergeComplete.emit();
}
```

**Acceptance criteria:**
- Модалки НЕ делают HTTP-запросов
- При нажатии «Слияние» эмитится `mergeRequested` с sourceId, targetId, comment
- Модалка закрывается по `mergeComplete`

---

## Stage 3C: Angular — интеграция модалок со страницей номенклатуры

**Файл:** `Warehouse_frontend/src/app/features/nomenclature/nomenclature-page/nomenclature-page.ts`

### Изменения в шаблоне:

```html
@if (mergeItemModal()) {
  <app-merge-item-modal
    [sourceItem]="selectedItem()!"
    (cancel)="mergeItemModal.set(null)"
    (mergeComplete)="mergeItemModal.set(null)"
    (mergeRequested)="onMergeRequested('item', $event)"
  />
}

@if (mergeCategoryModal()) {
  <app-merge-category-modal
    [sourceCategory]="selectedCategory()!"
    [allCategories]="categories()"
    (cancel)="mergeCategoryModal.set(null)"
    (mergeComplete)="mergeCategoryModal.set(null)"
    (mergeRequested)="onMergeRequested('category', $event)"
  />
}
```

### Добавить метод в класс:

```typescript
onMergeRequested(
  entityType: 'item' | 'category',
  event: { sourceId: string; targetId: string; comment?: string }
): void {
  this.changeBuffer.addChange({
    localId: `merge-${entityType}-${event.sourceId}-${Date.now()}`,
    entityType: entityType,
    entityId: event.sourceId,
    action: 'merge',
    payload: {
      target_entity_id: event.targetId,
      source_entity_id: event.sourceId,
      comment: event.comment ?? null,
    },
  });
}
```

**Acceptance criteria:**
- После выбора target в модалке и нажатия «Слияние» — изменение попадает в буфер
- Счётчик pending-changes-bar увеличивается
- `allCategories` проброшен в merge-category-modal

---

## Stage 4: Angular — `applyBatch` с поддержкой merge

**Файл:** `Warehouse_frontend/src/app/core/services/nomenclature.service.ts`

В методе `applyBatch()` (строка 936-942) расширить маппинг `action`:

```typescript
const batchChanges: CatalogBatchChange[] = changes.map(c => ({
  local_id: c.localId,
  entity_type: c.entityType as 'unit' | 'category' | 'item',
  action: c.action as 'create' | 'update' | 'deactivate' | 'delete' | 'merge',
  entity_id: c.entityId,
  payload: c.payload,
}));
```

**Без дополнительных изменений** — `CatalogBatchRequest` уже поддерживает произвольный payload, а SyncServer после Stage 1 будет обрабатывать merge в batch.

**Acceptance criteria:**
- `applyBatch()` отправляет merge-изменения в одном запросе с остальными
- После успешного batch — `reloadBootstrapAfterBatch` обновляет дерево

---

## Test Strategy

| Level | Что проверяем | Как |
|-------|--------------|-----|
| Static checks | Angular build | `cd Warehouse_frontend && npm run build` |
| Unit tests | SyncServer batch merge | `cd SyncServer && python -m pytest tests/test_catalog_merge.py tests/test_catalog_batch_merge.py -v` |
| Stand smoke | Реальное слияние через Angular UI | Playwright: логин → номенклатура → слить ТМЦ → проверить индикатор → применить → проверить исчезновение |
| Stand smoke | Персистентность буфера | Набрать merge → перейти на /operations/ → вернуться → буфер на месте |
| Regression | Django SSR merge | Ручной тест `/ssr/items/merge/` и `/ssr/categories/merge/` |
| Regression | create/update/deactivate/delete через batch | Существующий ручной flow |

### Stand smoke test (ручной / Playwright)

1. Открыть `http://localhost:8001/nomenclature/`
2. Создать две ТМЦ (если нет): «Тест Source Merge» и «Тест Target Merge»
3. Выбрать «Тест Source Merge» → нажать «Слияние ТМЦ»
4. Найти «Тест Target Merge» → выбрать → нажать «Слияние ТМЦ»
5. **Проверить:** модалка закрылась, в дереве у source зелёный фон + бейдж «сливается», счётчик pending = 1
6. Перейти на другие экраны (например, /operations/), вернуться в /nomenclature/
7. **Проверить:** буфер восстановился, индикатор merge на месте
8. Нажать «Применить» → подтвердить
9. **Проверить:** дерево обновилось, source исчез, счётчик pending = 0
10. Повторить для категорий

---

## Риски

| Риск | Вероятность | Митигация |
|------|------------|-----------|
| Merge в batch ломает существующие create/update | Средняя | Тесты на batch с миксом create+merge. Порядок обработки: create/update → merge |
| `sessionStorage` quota exceeded | Низкая | Буфер — десятки записей, каждая ~200 байт. try/catch при сохранении |
| Сломанные SSR merge view | Низкая | SSR использует отдельные endpoint'ы, batch-изменения их не трогают |
| Гонка данных: applyBatch во время merge | Низкая | Пользователь не может редактировать и сливать одновременно (модалка блокирует UI) |
| Старые merge-изменения в sessionStorage после деплоя | Низкая | При несовместимости формата — `JSON.parse` молча вернёт `[]` благодаря try/catch |

---

## Сводка файлов по стадиям

| Stage | Файл | Изменение |
|-------|------|-----------|
| 1 | `SyncServer/app/schemas/catalog.py` | +`BatchChangeMergePayload`, +`BatchChangeMerge`, обновить union |
| 1 | `SyncServer/app/services/catalog_admin_service.py` | +`_apply_merge_change`, обработка merge в `apply_batch` |
| 1 | `SyncServer/tests/test_catalog_batch_merge.py` | Новый файл с тестами batch-merge |
| 2A | `Warehouse_frontend/src/app/core/models/nomenclature.models.ts` | Расширить `CatalogPendingAction`, `CatalogBatchChange.action` |
| 2B | `Warehouse_frontend/src/app/core/services/catalog-change-buffer.service.ts` | +sessionStorage save/load, вызовы в мутирующих методах |
| 3A | `Warehouse_frontend/src/app/features/nomenclature/catalog-tree-node/catalog-tree-node.ts` | +CSS `.pending-merge`, +бейдж «сливается», conditional hide других бейджей |
| 3A | `Warehouse_frontend/src/styles/_legacy-aliases.scss` | +`.badge-merge` |
| 3B | `Warehouse_frontend/src/app/features/nomenclature/merge-item-modal/merge-item-modal.ts` | Убрать `CatalogAdminService`, заменить на `mergeRequested` output |
| 3B | `Warehouse_frontend/src/app/features/nomenclature/merge-category-modal/merge-category-modal.ts` | Аналогично |
| 3C | `Warehouse_frontend/src/app/features/nomenclature/nomenclature-page/nomenclature-page.ts` | +`onMergeRequested()`, обновить шаблон (+`allCategories`, +`mergeRequested`) |
| 4 | `Warehouse_frontend/src/app/core/services/nomenclature.service.ts` | Расширить `action` тип в `applyBatch` |

---

## Architecture Review

**Date:** 2026-06-30
**Reviewer:** Architect

### Verdict: Approved with conditions

### 🔴 Blockers

Нет.

### 🟡 Warnings

1. **sessionStorage semantics** — Пользователи могут ожидать, что изменения переживут перезапуск браузера (localStorage), а не только закрытие вкладки. Осознанное решение: `sessionStorage` = «в пределах сессии», при закрытии вкладки буфер чистится браузером. При необходимости в будущем можно добавить localStorage как fallback.

2. **Модалки теряют `isSubmitting`/`error`** — Поскольку модалки больше не делают API-запросов, индикатор загрузки и ошибки переносятся на уровень batch-применения. Пользователь увидит ошибку при нажатии «Применить», а не в модалке. Это допустимо: батч-применение — единая точка обратной связи. При необходимости можно добавить валидацию на уровне буфера (проверка что source и target существуют).

3. **Batch-merge и существующие create в одном батче** — Если пользователь создаёт новую ТМЦ и тут же сливает в неё другую, `local_id_map` должен корректно разрешать `target_entity_id` по `local_id`. В текущем плане `BatchChangeMergePayload.target_entity_id` — всегда реальный `int`, а не `local_id`. Это значит, что слияние в только что созданную сущность в том же батче НЕ поддерживается. Решение: либо запретить (валидация на фронте), либо добавить `target_local_id` в payload. **Пока оставляем без поддержки create+merge в одном батче** — это редкий сценарий.

### 🔵 Notes

1. **Старые direct-merge endpoint'ы сохраняются** — `POST /items/merge`, `POST /categories/merge` остаются для SSR и программного использования. Удалять их не нужно.

2. **BFF-эндпоинты merge не требуют изменений** — `AdminItemMergeView` и `AdminCategoryMergeView` остаются как есть для обратной совместимости. Batch-merge идёт через `/catalog/admin/batch`.

3. **Индикатор merge использует зелёный цвет** — `#F0FDF4` фон, `#166534` текст. Не конфликтует с существующими: жёлтый (dirty), красный (delete/error), серый (inactive), синий (selected).

4. **Нет нового UI-компонента** — Все изменения в существующих файлах. Не добавляем toast-сервис (отложено до общего решения по нотификациям).
