# TZ: Исправление отображения review-items (ТМЦ из операций)

## Execution Strategy

- [ ] 🟢 Parallel execution recommended (с оговорками)
- **Reason:** Stages 1, 2, 4 не пересекаются по файлам с TZ-MERGE_BATCH. Stage 3 (deep-link в каталог) пересекается с `nomenclature-page.ts` и `nomenclature.service.ts` — должен выполняться ПОСЛЕ Stage 3C merge-TZ.

## Execution Checklist

- [x] 0. Context verified ✅
- [x] 1. Stage 1: Исправить маппинг полей `toTempItemVm()` — `item_name` → `name`, `review_status` → `status` ✅ (was already done by prior work)
- [x] 2. Stage 2: Обновить `computeActionFlags()` для review-items ✅ (was already done)
- [x] 3. Stage 3: Таблица — кнопка «✓ Подтвердить» + переименование заголовка ✅ (was already done; added missing `(confirm)` binding in detail modal)
- [x] 4. Stage 4: Модалка деталей — убрать легаси, добавить «Открыть в каталоге» ✅ (was already done)
- [x] 5. Stage 5: Deep-link в каталог (queryParam `selectItem`) — **после merge-TZ Stage 3C** ✅ (IMPLEMENTED: 4 files changed)
- [ ] 6. Stand smoke: проверить что review-items из операций отображаются — стенд запущен, smoke не автоматизирована
- [ ] 7. Stand smoke: confirm с пустым payload — same
- [ ] 8. Stand smoke: навигация в каталог по клику — same
- [ ] 9. Regression: Angular build passed ✅ — legacy temporary-items не сломаны
- [ ] 10. Final acceptance review complete — см. отчёт ниже

---

## Диагноз (из анализа)

ТМЦ, созданные через операции (inline, `requires_review=True`), не отображаются на экране `/temporary-items`. Причина — **три разрыва** в маппинге полей между SyncServer `ReviewItemResponse` и Angular `TemporaryItem`:

| Поле | SyncServer отдаёт | Angular ждёт | Результат |
|------|------------------|-------------|-----------|
| Название | `item_name` | `name` | Пустая ячейка |
| Статус действий | `review_status` | `status` (legacy) | Все кнопки disabled |
| Остаток | Нет в list | `total_balance` | 0 |

Данные приходят, но `toTempItemVm()` не маппит новые поля.

---

## Scope

### In scope
- `Warehouse_frontend/src/app/core/models/temp-items.models.ts` — маппинг `toTempItemVm()`, `computeActionFlags()`
- `Warehouse_frontend/src/app/features/temporary-items/components/temp-items-table.component.ts` — кнопка «✓ Подтвердить»
- `Warehouse_frontend/src/app/features/temporary-items/pages/temp-items-page.component.ts` — обработчик confirm, переименование
- `Warehouse_frontend/src/app/core/services/temp-items.service.ts` — метод `confirmItem()`
- `Warehouse_frontend/src/app/features/temporary-items/components/temp-item-detail-modal.component.ts` — чистка легаси
- `Warehouse_frontend/src/app/features/nomenclature/nomenclature-page/nomenclature-page.ts` — deep-link (Stage 5)
- `Warehouse_frontend/src/app/core/services/nomenclature.service.ts` — `selectItemById()` (Stage 5)

### Out of scope
- SyncServer, Django BFF — данные приходят корректно, менять нечего
- Legacy temporary-items SSR — не трогаем
- Слияние review-items — существующие кнопки остаются (будут работать после фикса маппинга)

---

## Stage 1: Исправить маппинг полей в `toTempItemVm()`

**Файл:** `Warehouse_frontend/src/app/core/models/temp-items.models.ts`

### 1.1 Добавить хелпер `deriveStatusFromReviewStatus()`

```typescript
function deriveStatusFromReviewStatus(reviewStatus?: string): TemporaryItemStatus {
  switch (reviewStatus) {
    case 'confirmed': return 'approved_as_item';
    case 'merged': return 'merged_to_item';
    case 'archived': return 'deleted';
    default: return 'active'; // 'needs_review' или null → active
  }
}
```

### 1.2 Исправить `toTempItemVm()` (строка 213-239)

Заменить обращение к полям:

```typescript
export function toTempItemVm(
  item: TemporaryItem,
  operationsCount: number,
  hasPendingAcceptance: boolean,
  role: string,
): TemporaryItemVm {
  // Маппинг review-item полей
  const name = item.name || (item as any)['item_name'] || '';
  const status: TemporaryItemStatus = item.status || deriveStatusFromReviewStatus(item.review_status);
  const totalBalance = item.total_balance ?? 0;

  const uiStatus = computeUiStatus(status, totalBalance, hasPendingAcceptance);
  const flags = computeActionFlags(status, totalBalance, hasPendingAcceptance, role);

  return {
    id: item.id,
    name,
    sku: item.sku,
    description: item.description,
    categoryName: item.category_name,
    unitSymbol: item.unit_symbol,
    status,
    uiStatus,
    uiStatusLabel: TEMP_ITEM_UI_STATUS_LABELS[uiStatus],
    createdAt: formatDateTime(item.created_at),
    createdByUserId: item.created_by_user_id,
    totalBalance,
    operationsCount,
    ...flags,
    hasPendingAcceptance,
  };
}
```

### 1.3 Добавить `total_balance` в ответ SyncServer (если нет)

**Проверить:** если `ReviewItemResponse` не имеет `total_balance`, то в Angular оно всегда будет 0. Это приемлемо для MVP — кнопка confirm будет доступна в любом случае (см. Stage 2). Позже можно добавить агрегацию остатков в list endpoint.

**Acceptance criteria:**
- Review-items из операций отображаются с корректным названием
- Статус `needs_review` маппится в `active` → действия доступны

---

## Stage 2: Обновить `computeActionFlags()` для review-items

**Файл:** `Warehouse_frontend/src/app/core/models/temp-items.models.ts`

### Изменения в `computeActionFlags()` (строка 163-211)

Сейчас функция блокирует ВСЕ действия если `status !== 'active'`. Для review-items статус `active` (смапленный из `needs_review`) — это нормально. Но нужно также разрешить confirm для `needs_review` и разрешить delete для `can_delete`.

**Логика остаётся прежней**, но с уточнением: после маппинга Stage 1 `status` будет `'active'` для `needs_review`, так что проверка `status !== 'active'` пройдёт корректно.

**Изменение не требуется** — Stage 1 решает проблему автоматически.

**Acceptance criteria:**
- Для review-item с `review_status='needs_review'` кнопки «Преобразовать» и «Слить» активны
- Для review-item с нулевым остатком кнопка «Удалить» активна

---

## Stage 3: Таблица — кнопка «✓ Подтвердить» + переименование

### 3.1 Кнопка подтверждения в таблице

**Файл:** `Warehouse_frontend/src/app/features/temporary-items/components/temp-items-table.component.ts`

Добавить в интерфейс:
- `readonly confirmItem = output<TemporaryItemVm>();`

В шаблоне, в блоке действий (строка 54-74), добавить перед кнопкой convert:

```html
@if (row.uiStatus === 'needs_review') {
  <button class="wh-btn-icon btn-icon btn-confirm" title="Подтвердить" (click)="confirmItem.emit(row)">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <polyline points="20 6 9 17 4 12"/>
    </svg>
  </button>
}
```

CSS:
```css
.btn-confirm { color: #16A34A; }
.btn-confirm:hover { background: #F0FDF4; }
```

### 3.2 Обработчик confirm в странице

**Файл:** `Warehouse_frontend/src/app/features/temporary-items/pages/temp-items-page.component.ts`

- Добавить output `(confirmItem)="onRowConfirm($event)"` в `<app-temp-items-table>`
- Добавить метод:

```typescript
async onRowConfirm(item: TemporaryItemVm): Promise<void> {
  if (!confirm(`Подтвердить ТМЦ «${item.name}»? Она будет убрана из списка проверки.`)) return;
  const ok = await this.service.confirmItem(item.id);
  if (ok) {
    await this.loadList();
  }
}
```

### 3.3 Метод `confirmItem()` в сервисе

**Файл:** `Warehouse_frontend/src/app/core/services/temp-items.service.ts`

Добавить метод:

```typescript
async confirmItem(id: string): Promise<boolean> {
  try {
    await firstValueFrom(
      this.bffApi.postData(`/review-items/${id}/confirm`, {})
    );
    return true;
  } catch {
    return false;
  }
}
```

### 3.4 Переименование заголовка

**Файл:** `Warehouse_frontend/src/app/features/temporary-items/pages/temp-items-page.component.ts`

Строка 34-35:
```html
<h1 class="page-title">Временные ТМЦ</h1>
<p class="page-subtitle">Управление временными позициями: преобразование, слияние и удаление.</p>
```

Заменить на:
```html
<h1 class="page-title">ТМЦ, требующие проверки</h1>
<p class="page-subtitle">Позиции, созданные через операции. Подтвердите или скорректируйте перед включением в каталог.</p>
```

**Acceptance criteria:**
- В строке таблицы для `needs_review` есть зелёная кнопка с галочкой
- При нажатии — confirm-диалог → вызов `POST /review-items/{id}/confirm` → список обновляется
- Заголовок страницы: «ТМЦ, требующие проверки»

---

## Stage 4: Модалка деталей — чистка легаси

**Файл:** `Warehouse_frontend/src/app/features/temporary-items/components/temp-item-detail-modal.component.ts`

### Изменения:

1. **Убрать** «Системная категория» и «Системная единица» (строка 40-47) — это легаси-поля временных ТМЦ. Заменить на реальные:

```html
<div class="meta-item">
  <span class="meta-label">Категория</span>
  <span class="meta-value">{{ detail()?.category_name || '—' }}</span>
</div>
<div class="meta-item">
  <span class="meta-label">Единица измерения</span>
  <span class="meta-value">{{ detail()?.unit_symbol || '—' }}</span>
</div>
```

2. **Убрать** заблокированную кнопку «Слить с другой временной ТМЦ» (строка 119-123)

3. **Заменить** заголовок модалки (строка 15):
```html
<h2 class="modal-title">ТМЦ на проверке: {{ item().name }}</h2>
```

4. **Добавить** кнопку «Подтвердить» (галочка) в секцию действий — вызывает `confirm.emit(item())`:

В компоненте добавить output: `readonly confirm = output<TemporaryItemVm>();`

**Acceptance criteria:**
- Модалка показывает реальные категорию и единицу
- Нет кнопки-заглушки «Слить с временной»
- Есть кнопка «Подтвердить»

---

## Stage 5: Deep-link в каталог (после merge-TZ Stage 3C)

⚠️ **Зависимость от TZ-MERGE_BATCH.md Stage 3C** — оба меняют `nomenclature-page.ts` и `nomenclature.service.ts`.

### 5.1 Поддержка queryParam в странице номенклатуры

**Файл:** `Warehouse_frontend/src/app/features/nomenclature/nomenclature-page/nomenclature-page.ts`

В `ngOnInit()` (после `loadBootstrap()`):

```typescript
ngOnInit(): void {
  this.service.loadBootstrap().then(() => {
    // Deep-link: selectItem=123
    const selectItemId = this.route.snapshot.queryParams['selectItem'];
    if (selectItemId) {
      this.service.selectItemById(selectItemId);
    }
  });
  // ... existing code
}
```

### 5.2 Метод `selectItemById()` в сервисе

**Файл:** `Warehouse_frontend/src/app/core/services/nomenclature.service.ts`

```typescript
selectItemById(itemId: string): void {
  const item = this.allItems().find(i => String(i.id) === String(itemId));
  if (!item) return;

  // Force-show parent category path
  const categoryId = String(item.category_id ?? '');
  if (categoryId) {
    this.forceShowCategory(categoryId);
  }

  // Select the item
  this.selectNode({ type: 'item', id: String(itemId) } as CatalogTreeNodeVm);
}
```

### 5.3 Навигация из таблицы review-items

**Файл:** `Warehouse_frontend/src/app/features/temporary-items/pages/temp-items-page.component.ts`

- Инжектировать `Router`
- Добавить output `(navigateToCatalog)="onNavigateToCatalog($event)"` в таблицу
- Метод:

```typescript
onNavigateToCatalog(itemId: string): void {
  this.router.navigate(['/nomenclature'], { queryParams: { selectItem: itemId } });
}
```

**Файл:** `Warehouse_frontend/src/app/features/temporary-items/components/temp-items-table.component.ts`

- Добавить output `navigateToCatalog`
- Обернуть `row.name` в кликабельную ссылку, которая вызывает `navigateToCatalog.emit(row.id)` вместо `rowClick.emit(row)`:

```html
<td class="col-name">
  <a class="item-link" (click)="$event.stopPropagation(); navigateToCatalog.emit(row.id)" [title]="'Открыть в каталоге: ' + row.name">
    {{ row.name }}
  </a>
</td>
```

**Acceptance criteria:**
- Клик по названию ТМЦ в таблице → переход на `/nomenclature?selectItem=123`
- Страница номенклатуры выделяет ТМЦ в дереве и раскрывает родительскую категорию
- Клик по строке (не по названию) по-прежнему открывает модалку деталей

---

## Test Strategy

| Level | Что проверяем | Как |
|-------|--------------|-----|
| Static checks | Angular build | `cd Warehouse_frontend && npm run build` |
| Stand smoke | Review-items из операций отображаются | Создать операцию с inline-ТМЦ → submit → открыть `/temporary-items` → ТМЦ видна |
| Stand smoke | Быстрое подтверждение | Нажать «✓» → confirm-диалог → ТМЦ исчезает из списка |
| Stand smoke | Навигация в каталог | Клик по названию → переход в `/nomenclature?selectItem=X` → ТМЦ выделена |
| Regression | Legacy temporary-items | Проверить `/temporary-items/ssr/` (старые записи, если есть) |
| Regression | convert/merge/delete кнопки | Работают после фикса маппинга |

### Stand smoke test (ручной)

1. Создать операцию «Приёмка» → добавить строку с inline-созданием ТМЦ «Тест Review Item» → submit
2. Открыть `http://localhost:8001/temporary-items`
3. **Проверить:** в таблице есть «Тест Review Item» со статусом «Требует проверки»
4. Нажать «✓» → подтвердить → **проверить:** ТМЦ исчезла из списка
5. Создать ещё одну → кликнуть по названию → **проверить:** переход в `/nomenclature?selectItem=X`
6. **Проверить:** в каталоге ТМЦ выделена в дереве

---

## Сводка файлов

| Stage | Файл | Изменение |
|-------|------|-----------|
| 1 | `temp-items.models.ts` | `toTempItemVm()` — маппинг `item_name`→`name`, `review_status`→`status` |
| 1 | `temp-items.models.ts` | `deriveStatusFromReviewStatus()` — новый хелпер |
| 3 | `temp-items-table.component.ts` | +кнопка «✓ Подтвердить», +output +CSS |
| 3 | `temp-items-page.component.ts` | +`onRowConfirm()`, +переименование заголовка |
| 3 | `temp-items.service.ts` | +метод `confirmItem()` |
| 4 | `temp-item-detail-modal.component.ts` | Чистка легаси-полей, -заглушка «слить с временной», +confirm output |
| 5 | `nomenclature-page.ts` | +чтение `selectItem` queryParam (**после merge-TZ Stage 3C**) |
| 5 | `nomenclature.service.ts` | +`selectItemById()` (**после merge-TZ Stage 3C**) |
| 5 | `temp-items-page.component.ts` | +`onNavigateToCatalog()`, +Router inject |
| 5 | `temp-items-table.component.ts` | +`navigateToCatalog` output, имя как ссылка |

---

## Риски

| Риск | Вероятность | Митигация |
|------|------------|-----------|
| `total_balance` = 0 для всех review-items | Высокая | Показываем в таблице, подтверждение работает независимо от остатка |
| Конфликт с merge-TZ в `nomenclature-page.ts` | Средняя | Stage 5 делать ПОСЛЕ merge-TZ Stage 3C |
| Legacy временные ТМЦ сломаются | Низкая | У них есть поле `name`, маппинг через `item.name \|\| item.item_name` |
| `window.confirm()` блокирует UI | Низкая | Временное решение, позже заменить на кастомный диалог |
