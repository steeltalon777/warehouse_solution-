# TZ: Merge Categories And Items — Frontend

## Execution Strategy

- [ ] 🟢 Parallel execution recommended
- **Reason:** merge-модалка для ТМЦ и merge-модалка для категорий — независимые UI-компоненты с общим сервисом. Можно распараллелить:
  - Unit A: модалка + кнопка для merge ТМЦ (на базе `temp-item-merge-permanent-form`)
  - Unit B: модалка + кнопка для merge категорий (аналогичный паттерн, проще)
  - Unit C: BFF-сервисные методы и модели DTO (общий код, делается первым или параллельно с A/B после согласования интерфейса)

### Parallel work units

| Stage | Unit | Owner area | Writable files | Required inputs | Output |
|---|---|---|---|---|---|
| 0 | BFF service + DTO | `core/services/`, `core/models/` | `catalog-admin.service.ts`, `catalog.models.ts` (merge DTO) | BFF контракт из backend TZ | Методы `mergeItems()`, `mergeCategories()` |
| 1A | Item merge modal + button | `features/nomenclature/` | `item-edit-form/`, новый `merge-modal/` или переиспользование | DTO из Stage 0 | Кнопка «Слить» в форме ТМЦ → модалка → успех |
| 1B | Category merge modal + button | `features/nomenclature/` | `category-edit-form/`, `merge-modal/` | DTO из Stage 0 | Кнопка «Слить» в форме категории → модалка → успех |
| 2 | Integration QA | Orchestrator | — | 1A + 1B | Сборка, smoke, финальная проверка |

## Execution Checklist

- [x] 0. Context verified — 2026-06-10
- [x] 1. Architecture boundaries confirmed — SPA contract: modal overlay z-index 1100 covers content area only (fixed within Angular shell), no Django shell redraw
- [x] 2. Implementation stage 0 complete — BFF service methods + DTO
- [x] 3. Implementation stage 1A complete — item merge UI
- [x] 4. Implementation stage 1B complete — category merge UI
- [x] 5. Stage 2 complete — integration QA
- [x] 6. Unit/component tests complete — 40/40 passed (npm test --watch=false)
- [x] 7. Stand smoke tests complete — Playwright smoke on localhost:8001/nomenclature
- [x] 8. UI automation tests complete — Playwright: active/inactive visibility, modal open, search filter, self-merge exclusion
- [x] 9. User scenario tests complete — Playwright: merge item + merge category full flows
- [x] 10. Regression checks complete — build + unit tests + existing CRUD verified
- [x] 11. Documentation updated — skipped (no doc changes required for this feature)
- [x] 12. Final acceptance review complete — accepted 2026-06-10

## Check Rules

- Architect creates this checklist and acceptance criteria.
- Executor agents may check implementation and test items only after running the required verification.
- QA verifier may check final acceptance only after reviewing evidence.
- Angular component tests опциональны (инфраструктура может быть недоступна) — компенсировать Playwright.
- Если реальный стенд недоступен, использовать blocker note: `стенд недоступен`.

---

## 1. Goal

Добавить в Angular-интерфейс номенклатуры (`/nomenclature`) возможность слияния (merge) категорий и ТМЦ:

- Кнопка «Слить» в форме редактирования ТМЦ → модалка выбора целевой ТМЦ → подтверждение → merge
- Кнопка «Слить» в форме редактирования категории → модалка выбора целевой категории → подтверждение → merge

---

## 2. Functional Requirements Alignment

`Functional and WorkLogik.md`, раздел III:
- Управление каталогом доступно chief_storekeeper и root
- Слияние ТМЦ переносит все операции и остатки на целевую ТМЦ
- Слияние категорий переносит все ТМЦ в целевую категорию

---

## 3. Existing Implementation Reference

### 3.1 Текущий интерфейс номенклатуры

- **Страница**: `/nomenclature` (lazy-loaded, standalone)
- **Левая панель**: дерево категорий и ТМЦ (`catalog-tree` + `catalog-tree-node`)
- **Правая панель**: форма редактирования выбранной сущности
  - `category-edit-form` — для категорий
  - `item-edit-form` — для ТМЦ
  - `unit-edit-form` — для единиц измерения
- **Кнопки в форме**: `[Деактивировать] [Удалить] ... [Сбросить] [Сохранить]`
- **Нет inline-кнопок в узлах дерева** — все действия через правую панель

### 3.2 Существующий паттерн merge-модалки

`temp-item-merge-permanent-form` (`features/temporary-items/components/`) — **лучший референс**:
- Модальное окно 560px
- Источник: инфо-баннер с названием и остатками
- Поиск целевой ТМЦ с debounce (через `BffApiService.getList('/catalog/read/items', ...)`)
- Выпадающий список результатов поиска
- Превью выбранной цели (зелёный блок)
- Предупреждение о несовпадении единиц измерения (жёлтый блок + чекбокс)
- Поле комментария
- Кнопки: «Слить с выбранной ТМЦ» + «Отмена»

### 3.3 Существующие сервисы

- `BffApiService.getList()` — для поиска ТМЦ/категорий
- `BffApiService.postData()` — для вызова merge API
- `CatalogService` / `NomenclatureService` — управление состоянием дерева

### 3.4 BFF-контракт (из backend TZ)

```
POST /bff/api/v1/catalog/admin/items/merge
  body: { source_item_id: number, target_item_id: number, comment?: string }
  response: { ok: true, data: <ItemResponse> }

POST /bff/api/v1/catalog/admin/categories/merge
  body: { source_category_id: number, target_category_id: number, comment?: string }
  response: { ok: true, data: <CategoryResponse> }
```

Ошибки: 403 (нет прав), 404 (не найдено), 409 (frozen), 422 (self-merge).

---

## 4. Implementation

### Stage 0 — BFF Service + DTO

#### 4.0.1 DTO модели

Добавить в `src/app/core/models/catalog.models.ts`:

```typescript
export interface ItemMergeRequest {
  source_item_id: number;
  target_item_id: number;
  comment?: string;
}

export interface CategoryMergeRequest {
  source_category_id: number;
  target_category_id: number;
  comment?: string;
}
```

#### 4.0.2 Сервисные методы

Добавить в `CatalogAdminService` (или создать):

```typescript
mergeItem(sourceItemId: number, targetItemId: number, comment?: string): Observable<ItemResponse> {
  return this.bffApi.postData<ItemResponse>('/catalog/admin/items/merge', {
    source_item_id: sourceItemId,
    target_item_id: targetItemId,
    comment,
  });
}

mergeCategory(sourceCategoryId: number, targetCategoryId: number, comment?: string): Observable<CategoryResponse> {
  return this.bffApi.postData<CategoryResponse>('/catalog/admin/categories/merge', {
    source_category_id: sourceCategoryId,
    target_category_id: targetCategoryId,
    comment,
  });
}
```

### Stage 1A — Item Merge UI

#### 4.1.1 Кнопка «Слить» в item-edit-form

Добавить в `item-edit-form.component.ts`:

- Новая кнопка «Слить» в футере формы (слева, до «Деактивировать»)
- Стиль: danger/outline (оранжевый/красный оттенок, как у деактивации)
- `@Output() mergeRequest = new EventEmitter<number>()` — эмитит `item.id`
- Видна только для существующих ТМЦ (не для новых/создаваемых)
- Видна только если ТМЦ активна (`is_active === true`) и не удалена

#### 4.1.2 Модалка merge

Новый компонент `MergeItemModalComponent` (в `features/nomenclature/components/`):

**Структура (на базе `temp-item-merge-permanent-form`):**

```
┌─────────────────────────────────────────┐
│ Слияние ТМЦ                          ✕  │
├─────────────────────────────────────────┤
│ Источник:                               │
│ ┌─────────────────────────────────────┐ │
│ │ Кабель ВВГ 2х2,5                    │ │
│ │ SKU: —  ·  Категория: Электро       │ │
│ │ Ед. изм: м  ·  Остатки: 150.0       │ │
│ └─────────────────────────────────────┘ │
│                                         │
│ Целевая ТМЦ:                            │
│ ┌─────────────────────────────────────┐ │
│ │ 🔍 Поиск ТМЦ...                     │ │
│ └─────────────────────────────────────┘ │
│ ┌─────────────────────────────────────┐ │
│ │ ○ Провод ПВС 2х1,5                  │ │
│ │   SKU: PVS-2x15 · Кат: Электро     │ │
│ │   Ед. изм: м                        │ │
│ │ ○ Кабель ВВГ 2х4                    │ │
│ │   SKU: — · Кат: Электро · Ед: м    │ │
│ └─────────────────────────────────────┘ │
│                                         │
│ ⚠️ Единицы измерения различаются:      │
│ «шт» → «м». Подтвердите.          [✓]  │
│                                         │
│ Комментарий:                            │
│ ┌─────────────────────────────────────┐ │
│ │                                     │ │
│ └─────────────────────────────────────┘ │
├─────────────────────────────────────────┤
│              [Отмена]  [Слить ТМЦ]      │
└─────────────────────────────────────────┘
```

**Логика:**
1. `@Input() sourceItem: CatalogItemVm` — исходная ТМЦ
2. Поиск целевой ТМЦ через `BffApiService.getList('/catalog/read/items', {search, page_size: 10})`
3. Debounce 300ms, минимальная длина поиска — 2 символа
4. Выпадающий список результатов (name, SKU, category, unit)
5. При выборе цели: показывается зелёный блок с информацией о target
6. Если `source.unit_id !== target.unit_id` — предупреждение + чекбокс
7. Кнопка «Слить ТМЦ» неактивна, пока не выбрана цель и не подтверждено расхождение единиц
8. По нажатию: вызов `CatalogAdminService.mergeItem()` → успех → закрыть модалку → `mergeComplete.emit()`
9. Ошибка: показать сообщение в модалке

**Фильтрация поиска:**
- Исключить source из результатов поиска
- Только активные и не удалённые ТМЦ

#### 4.1.3 Интеграция в nomenclature-page

В `nomenclature-page.component.ts`:

```typescript
onItemMergeRequest(itemId: number) {
  const item = this.nomenclatureService.getItemById(itemId);
  if (!item) return;
  // Открыть MergeItemModalComponent
  const modalRef = this.modalService.open(MergeItemModalComponent, { sourceItem: item });
  modalRef.closed.subscribe(() => {
    this.nomenclatureService.reloadBootstrap(); // перезагрузить дерево
    this.nomenclatureService.clearSelection();  // сбросить выбор (source удалён)
  });
}
```

В `right-panel.component.html` — пробросить `mergeRequest` от `item-edit-form` к `nomenclature-page`.

### Stage 1B — Category Merge UI

#### 4.2.1 Кнопка «Слить» в category-edit-form

Аналогично item-edit-form:
- Кнопка «Слить» в футере
- `@Output() mergeRequest = new EventEmitter<number>()`
- Видна для существующих активных категорий
- Не видна для корневых категорий (?) — на усмотрение, можно и для корневых

#### 4.2.2 Модалка merge категорий

`MergeCategoryModalComponent` — упрощённая версия (без балансов, без единиц измерения):

```
┌─────────────────────────────────────────┐
│ Слияние категорий                    ✕  │
├─────────────────────────────────────────┤
│ Источник:                               │
│ ┌─────────────────────────────────────┐ │
│ │ Электрорасходники                   │ │
│ │ Код: EL · ТМЦ: 5 шт.               │ │
│ └─────────────────────────────────────┘ │
│                                         │
│ Целевая категория:                      │
│ ┌─────────────────────────────────────┐ │
│ │ 🔍 Поиск категории...               │ │
│ └─────────────────────────────────────┘ │
│ ┌─────────────────────────────────────┐ │
│ │ ○ Расходники                        │ │
│ │   Код: CONS · ТМЦ: 3 шт.           │ │
│ │ ○ Инструменты                       │ │
│ │   Код: TOOL · ТМЦ: 12 шт.          │ │
│ └─────────────────────────────────────┘ │
│                                         │
│ ⚠️ Все ТМЦ (5 шт.) и подкатегории      │
│ будут перенесены в целевую категорию.   │
│                                         │
│ Комментарий:                            │
│ ┌─────────────────────────────────────┐ │
│ │                                     │ │
│ └─────────────────────────────────────┘ │
├─────────────────────────────────────────┤
│           [Отмена]  [Слить категорию]   │
└─────────────────────────────────────────┘
```

**Логика:**
1. `@Input() sourceCategory: CatalogTreeNodeVm`
2. Поиск через `BffApiService.getList('/catalog/read/categories', {search, page_size: 10})`
3. Исключить source и её подкатегории из результатов
4. Предупреждение о переносе всех ТМЦ и подкатегорий
5. Вызов `CatalogAdminService.mergeCategory()` → успех → reload → close

#### 4.2.3 Интеграция

Аналогично item merge — через `nomenclature-page`.

### Stage 2 — Integration QA

- `npm run build` — без ошибок
- Playwright smoke: зайти в `/nomenclature`, выбрать ТМЦ, нажать «Слить», выполнить поиск, выбрать цель, подтвердить
- Проверить: после merge дерево обновляется, source исчезает, балансы на target увеличиваются
- Проверить: merge категории, все ТМЦ в новой категории

---

## 5. UX-соображения

### Куда именно поместить кнопку?

**Рекомендация:** кнопка «Слить» в правой панели (edit form), в ряду с «Деактивировать» и «Удалить». Причина:
- Не ломает текущий tree-дизайн (нет inline-кнопок в узлах)
- Контекст уже выбран (кликнули на ТМЦ → она в правой панели)
- Естественное соседство с другими деструктивными действиями

**Альтернатива:** inline-кнопка в узле дерева. Плюс: быстрее доступ. Минус: захламляет дерево, ломает текущий дизайн.

### Права доступа

Кнопка «Слить» видна только если `user.permissions.can_manage_catalog === true` (chief_storekeeper или root).

---

## 6. Test Strategy

### Static checks
```bash
cd Warehouse_frontend && npm run build
```

### Component tests (опционально)

Если тестовая инфраструктура Angular доступна:
- Модалка: поиск фильтрует результаты, self-merge исключён
- Кнопка «Слить» неактивна без выбора цели
- Предупреждение о единицах измерения показывается при несовпадении
- Кнопка не видна для не-admin пользователей

Если инфраструктура недоступна — оставить unchecked с пометкой «Angular test infra unavailable», компенсировать Playwright.

### Stand smoke tests (Playwright)

1. Залогиниться как admin
2. Перейти на `/nomenclature`
3. Выбрать ТМЦ в дереве → открылась форма редактирования
4. Нажать «Слить» → открылась модалка
5. Ввести поисковый запрос → появились результаты
6. Выбрать целевую ТМЦ → показалось превью
7. Нажать «Слить ТМЦ» → модалка закрылась, дерево обновилось
8. Повторить для категорий
9. Проверить 403 для не-admin пользователя

### UI automation (Playwright)

- Полный сценарий merge ТМЦ
- Полный сценарий merge категорий
- Негативный: попытка self-merge (одна и та же ТМЦ не должна быть в списке)
- Негативный: закрытие модалки без сохранения

### Regression checks

- Существующий CRUD номенклатуры: создать, редактировать, деактивировать, удалить — не сломаны
- Пакетное применение изменений (batch apply) работает
- Дерево корректно перерисовывается после merge
- Переключение вкладок «Категории и ТМЦ» / «Единицы измерения» не сломано

---

## 7. Real Test Stand

Docker-стенд: Angular `:4200` (или через Django `:8001/nomenclature`).

Требования к данным:
- Минимум 3 ТМЦ с разными единицами измерения (для теста несовпадения единиц)
- Минимум 3 категории (одна с подкатегориями)
- Пользователь admin (root)
- Пользователь observer (для теста 403)

Предполагается, что backend merge API уже работает (либо мокаем BFF-ответы для раннего тестирования UI).

---

## 8. Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Merge API не готов к моменту тестирования UI | Нельзя протестировать end-to-end | Мокать BFF-ответы на время разработки UI |
| Поиск возвращает source в результатах | Self-merge | Фильтровать source.id из результатов |
| Несовпадение единиц измерения проигнорировано | Некорректные остатки | Чекбокс подтверждения обязателен |
| Модалка не закрывается после успеха | UI-зависание | `modalRef.close()` в `subscribe` |
| Права доступа не проверяются на фронте | Кнопка видна, но API возвращает 403 | Проверять `can_manage_catalog` перед показом кнопки |

---

## 9. Acceptance Criteria

- Кнопка «Слить» видна в форме редактирования ТМЦ для admin/chief_storekeeper
- Кнопка «Слить» видна в форме редактирования категории для admin/chief_storekeeper
- Кнопка не видна для observer
- Модалка merge ТМЦ: поиск, выбор, превью, предупреждение о единицах, комментарий
- Модалка merge категорий: поиск, выбор, превью, предупреждение, комментарий
- После успешного merge: модалка закрывается, дерево обновляется, source исчезает
- Ошибка (403/404/409/422) показывается в модалке, модалка не закрывается
- Self-merge невозможен (source исключён из поиска)
- Существующий CRUD номенклатуры не сломан
- `npm run build` проходит без ошибок

---

## 10. Files In Scope

### Новые файлы
- `src/app/features/nomenclature/components/merge-item-modal/merge-item-modal.component.ts`
- `src/app/features/nomenclature/components/merge-item-modal/merge-item-modal.component.html`
- `src/app/features/nomenclature/components/merge-item-modal/merge-item-modal.component.scss`
- `src/app/features/nomenclature/components/merge-category-modal/merge-category-modal.component.ts`
- `src/app/features/nomenclature/components/merge-category-modal/merge-category-modal.component.html`
- `src/app/features/nomenclature/components/merge-category-modal/merge-category-modal.component.scss`

### Изменяемые файлы
- `src/app/core/models/catalog.models.ts` — DTO
- `src/app/core/services/catalog-admin.service.ts` — методы merge
- `src/app/features/nomenclature/components/item-edit-form/item-edit-form.component.ts` — кнопка «Слить» + @Output
- `src/app/features/nomenclature/components/item-edit-form/item-edit-form.component.html` — кнопка в футере
- `src/app/features/nomenclature/components/category-edit-form/category-edit-form.component.ts` — кнопка «Слить» + @Output
- `src/app/features/nomenclature/components/category-edit-form/category-edit-form.component.html` — кнопка в футере
- `src/app/features/nomenclature/components/right-panel/right-panel.component.ts` — проброс событий
- `src/app/features/nomenclature/components/right-panel/right-panel.component.html` — проброс событий
- `src/app/features/nomenclature/pages/nomenclature-page/nomenclature-page.component.ts` — обработка merge, открытие модалок

---

## 11. Out Of Scope

- Merge units (единиц измерения)
- Undo/отмена merge
- Массовый merge (выбор нескольких source)
- История merge (аудит-лог в UI)
- SSR-формы merge (уже существуют, без изменений)
- Backend API merge (отдельный TZ)
