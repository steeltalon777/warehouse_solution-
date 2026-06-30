# TZ: Исправление слияния ТМЦ и категорий (merge)

## Execution Strategy

- [ ] 🟢 Parallel execution recommended
- **Reason:** Три независимых юнита: (A) устранение первопричины в Angular-странице, (B) исправление поиска в модалке категорий, (C) добавление toast-уведомлений. Юниты не пересекаются по файлам.

## Execution Checklist

- [ ] 0. Context verified
- [ ] 1. Architecture boundaries confirmed
- [ ] 2. Unit A: Reload data + clear selection after merge (nomenclature-page.ts)
- [ ] 3. Unit B: Fix allCategories input in merge-category-modal (nomenclature-page.ts template)
- [ ] 4. Unit C: Add success toast after merge (merge-item-modal.ts, merge-category-modal.ts)
- [ ] 5. Unit tests (Angular build)
- [ ] 6. Stand smoke tests (real merge through Angular UI)
- [ ] 7. Regression checks (Django SSR merge, no breakage)
- [ ] 8. Documentation updated
- [ ] 9. Final acceptance review complete

---

## Диагноз

Обследована цепочка от Angular-модалок до SyncServer:

| Слой | Файл | Статус |
|------|------|--------|
| SyncServer (сервис) | `catalog_admin_service.py:509-747` | ✅ Логика верна, балансы переносятся, source деактивируется |
| SyncServer (роутер) | `routes_catalog_admin.py:397-442` | ✅ Возвращает target entity |
| Django BFF | `catalog_views.py:664-687` | ✅ Проксирует ответ, ошибки маппятся |
| Django SSR | `views.py:945-1011` | ✅ После merge делает redirect на список |
| Angular (модалка) | `merge-item-modal.ts`, `merge-category-modal.ts` | ✅ Форма отправляет правильный запрос |
| Angular (страница) | `nomenclature-page.ts:121-135` | 🔴 **НЕ обновляет данные, НЕ чистит selection** |

### Корневая причина

В `nomenclature-page.ts` (строки 121-135) обработчики `mergeComplete` только закрывают модалку:

```typescript
(mergeComplete)="mergeItemModal.set(null)"
```

Но **не вызывают** `this.service.loadBootstrap({ cacheBust: true })` и `this.service.clearSelection()`.

**Результат:** слияние успешно выполняется на бэкенде (SyncServer деактивирует source, переносит ТМЦ/балансы/подкатегории), но Angular-дерево продолжает показывать устаревшие данные. Пользователь видит source в дереве, как будто ничего не произошло — «изменение не применилось».

### Вторичная проблема

В шаблоне `nomenclature-page.ts` (строка 129-134) компонент `<app-merge-category-modal>` **не получает** `[allCategories]`. Из-за этого логика исключения потомков (`collectDescendants`, `excludedIds`) не работает: поиск по пустому массиву. Бэкенд всё равно ловит циклы, но пользователь видит в результатах поиска категории-потомки, которые заведомо невалидны.

### Третичная проблема

После успешного слияния нет toast/snackbar — пользователь не получает подтверждения. SSR-версия показывает Django messages, Angular — нет.

---

## Scope

### In scope
- `Warehouse_frontend/src/app/features/nomenclature/nomenclature-page/nomenclature-page.ts` — обработчики `mergeComplete`
- `Warehouse_frontend/src/app/features/nomenclature/merge-item-modal/merge-item-modal.ts` — output для успеха
- `Warehouse_frontend/src/app/features/nomenclature/merge-category-modal/merge-category-modal.ts` — output для успеха

### Out of scope
- SyncServer, Django BFF, Django SSR — менять не требуется
- Остальные merge-формы (temporary items, review items, issue objects) — не трогаем
- Добавление нового UI-компонента toast — используем встроенный `window.alert` или существующий механизм, без нового сервиса

---

## Unit A: Reload + clear selection after merge

**Файл:** `Warehouse_frontend/src/app/features/nomenclature/nomenclature-page/nomenclature-page.ts`

**Что изменить в классе `NomenclaturePageComponent`:**

1. Добавить приватный метод `onMergeComplete()`:
```typescript
private async onMergeComplete(): Promise<void> {
  this.mergeItemModal.set(null);
  this.mergeCategoryModal.set(null);
  this.service.clearSelection();
  await this.service.loadBootstrap({ cacheBust: true });
}
```

2. Заменить в шаблоне строки 121-135:
   - `(mergeComplete)="mergeItemModal.set(null)"` → `(mergeComplete)="onMergeComplete()"`
   - `(mergeComplete)="mergeCategoryModal.set(null)"` → `(mergeComplete)="onMergeComplete()"`

**Acceptance criteria:**
- После слияния ТМЦ дерево обновляется, source больше не виден (is_active=false)
- После слияния категорий дерево обновляется, source больше не виден
- Правая панель очищается (нет выделенной сущности)
- При ошибке слияния модалка НЕ закрывается (ошибка показывается внутри модалки)

---

## Unit B: Fix allCategories input for merge-category-modal

**Файл:** `Warehouse_frontend/src/app/features/nomenclature/nomenclature-page/nomenclature-page.ts`

**Что изменить в шаблоне (строка 129-134):**

Добавить входной параметр `[allCategories]="categories()"`:

```html
@if (mergeCategoryModal()) {
  <app-merge-category-modal
    [sourceCategory]="selectedCategory()!"
    [allCategories]="categories()"
    (cancel)="mergeCategoryModal.set(null)"
    (mergeComplete)="onMergeComplete()"
  />
}
```

**Acceptance criteria:**
- При поиске целевой категории потомки source не отображаются в результатах
- Циклическое слияние предотвращается на уровне UI (не только на бэкенде)

---

## Unit C: Success toast after merge

**Файлы:** `merge-item-modal.ts`, `merge-category-modal.ts`

**Что изменить:**

В обоих модальных компонентах добавить вывод success-сообщения перед `mergeComplete.emit()`:

```typescript
// В onSubmit() после успешного вызова API:
this.mergeComplete.emit();
```

Заменить на:

```typescript
this.mergeComplete.emit();
// Используем window.alert как простейший feedback; 
// при появлении toast-сервиса заменить на вызов toast.success(...)
alert('Слияние выполнено успешно.');
```

Либо, если в проекте уже есть toast-сервис — использовать его.

**Acceptance criteria:**
- После успешного слияния ТМЦ пользователь видит сообщение «Слияние выполнено»
- После успешного слияния категорий пользователь видит сообщение «Слияние выполнено»
- При ошибке слияния toast НЕ показывается (ошибка уже отображается в модалке)

---

## Test Strategy

| Level | Что проверяем | Как |
|-------|--------------|-----|
| Static checks | `npm run build` проходит без ошибок | `cd Warehouse_frontend && npm run build` |
| Stand smoke | Реальное слияние через Angular UI | Playwright: логин → номенклатура → выбрать ТМЦ → слить → проверить что дерево обновилось |
| Regression | Django SSR merge не сломан | Проверить `/ssr/items/merge/` и `/ssr/categories/merge/` через браузер |
| Regression | BFF merge endpoints возвращают 200 | `curl -X POST http://localhost:8001/bff/api/v1/catalog/admin/items/merge` |

### Stand smoke test (ручной)

1. Открыть `http://localhost:8001/nomenclature/`
2. Создать две тестовые ТМЦ (если нет): «Тест Source» и «Тест Target»
3. Выбрать «Тест Source» в дереве
4. Нажать кнопку «Слияние ТМЦ» в правой панели
5. В модалке найти «Тест Target», выбрать
6. Нажать «Слияние ТМЦ»
7. **Проверить:** модалка закрылась, появился alert, дерево обновилось, «Тест Source» исчез
8. Повторить для категорий

---

## Риски

| Риск | Вероятность | Митигация |
|------|------------|-----------|
| `loadBootstrap` может быть долгим на проде | Низкая | Используем `cacheBust: true` только после merge; на проде каталог кешируется |
| `clearSelection` сбрасывает форму редактирования | Низкая | После merge это ожидаемое поведение |
| `window.alert` блокирует UI | Низкая | Временное решение до появления toast-сервиса |

---

## Архитектурная проверка (Architecture Stress-Test)

### Verdict: Approved with conditions

### 🔴 Blockers

Нет.

### 🟡 Warnings

1. **No toast service exists yet** — Unit C использует `window.alert` как временное решение. При появлении toast-сервиса (Sprint N+1) заменить на `toast.success()`.
2. **loadBootstrap делает полную перезагрузку** — При большом каталоге может быть заметна задержка. В будущем можно реализовать инкрементальное обновление (удалить source из локального стейта без полной перезагрузки).

### 🔵 Notes

1. SSR merge работает корректно (redirect → полная перезагрузка страницы), трогать не нужно.
2. SyncServer merge-логика проверена тестами (`test_catalog_merge.py`, 418 строк), ошибок в сервисе не найдено.
3. BFF-прослойка корректно пробрасывает ответы и ошибки.
