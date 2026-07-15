# TZ: Защита черновика складской операции — Этап 4

**Дата:** 2026-07-15  
**Источник:** замороженное ревью `docs/archive/ARCHITECTURE_REVIEW_ANGULAR_UI_DIAGNOSTICS.md`, §7, RISK-005, RISK-008  
**Статус:** ТЗ — без реализации  
**Режим:** соло (1 агент, без SWARM)

---

## 1. Executive Summary

### Проблема

Кладовщик заполнил форму на 20+ позиций, случайно нажал на пункт меню, закрыл модал или обновил страницу — вся работа потеряна. Никакого предупреждения, никакого восстановления.

### Решение

Три механизма защиты:

1. **Автосохранение в `sessionStorage`** — черновик сохраняется каждые 2 секунды бездействия
2. **Защита от ухода** — `CanDeactivate` guard + `beforeunload` + подтверждение при закрытии модала
3. **Восстановление** — при открытии модала предложение восстановить последний черновик

Плюс диагностические события: `draft_autosaved`, `draft_restored`, `draft_lost`.

### Что НЕ делаем

- Не сохраняем в `localStorage` (persistent across sessions) — только `sessionStorage`
- Не сохраняем в IndexedDB
- Не синхронизируем между вкладками
- Не храним персональные данные (`personName` не сохраняется)

---

## 2. Существующая инфраструктура

| Что | Где | Как использовать |
|-----|-----|-----------------|
| `snapshotDraft()` / `isDraftClean()` | `operation-draft-mappers.ts` | Сериализация черновика в JSON-строку |
| `hasUnsavedChanges` | `operation-create-modal.component.ts:649-653` | Уже вычисляется |
| `DiagnosticsService.track()` | `diagnostics.service.ts` (Этап 3) | События draft_autosaved/draft_restored/draft_lost |
| `DiagnosticsSessionService` | `diagnostics-session.service.ts` (Этап 1) | session_id для ключа storage |
| `OperationDraftVm` | `operations.models.ts` | Сериализуемая модель |

---

## 3. Реализация

### 3.1 DraftStorageService (новый)

```typescript
// Warehouse_frontend/src/app/core/services/draft-storage.service.ts (NEW)

@Injectable({ providedIn: 'root' })
export class DraftStorageService {
  private readonly PREFIX = 'warehouse.draft.v1';

  save(draft: OperationDraftVm): void {
    // Сериализовать через snapshotDraft
    // Сохранить: { draft: snapshot, savedAt: ISO, idempotencyKey, draftId }
    // Только если есть lines.length > 0
  }

  load(): SavedDraft | null {
    // Прочитать из sessionStorage
    // Вернуть null если нет или expired (>24h)
  }

  clear(): void {
    // Удалить из sessionStorage
  }

  hasDraft(): boolean {
    // Проверить наличие
  }
}

interface SavedDraft {
  draft: string;           // JSON from snapshotDraft
  savedAt: string;         // ISO timestamp
  idempotencyKey: string;
  draftId: string;
}
```

**Что НЕ сохраняется:**
- `personName`
- `comment` (опционально — решить на реализации)

### 3.2 Автосохранение (effect в модале)

```typescript
// operation-create-modal.component.ts

constructor() {
  // ... существующие effects ...

  effect(() => {
    const draft = this.localDraft();
    if (draft.lines.length > 0) {
      this.draftStorage.save(draft);
      this.diagnostics.track('draft_autosaved', {
        draft,
        details: { items_count: draft.lines.length }
      });
    }
  }, { allowSignalWrites: true });
}
```

Добавить `debounce` через `setTimeout`: сохранять через 2 секунды после последнего изменения.

### 3.3 Восстановление при открытии

```typescript
// operation-create-modal.component.ts — ngOnInit

ngOnInit(): void {
  const saved = this.draftStorage.load();
  if (saved && !this.draft()) {
    const restore = confirm(
      'Найден несохранённый черновик. Восстановить?'
    );
    if (restore) {
      // Создать draft из saved
      this.diagnostics.track('draft_restored', { draftId: saved.draftId });
    } else {
      this.draftStorage.clear();
    }
  }
}
```

### 3.4 CanDeactivate guard

```typescript
// Warehouse_frontend/src/app/core/guards/unsaved-draft.guard.ts (NEW)

export const unsavedDraftGuard: CanDeactivateFn<OperationsPageComponent> = (
  component: OperationsPageComponent
) => {
  if (component.showCreateModal() && component.editingDraftHasChanges()) {
    return confirm('У вас есть несохранённые изменения. Покинуть страницу?');
  }
  return true;
};
```

```typescript
// app.routes.ts — добавить
{
  path: 'operations',
  loadComponent: ...,
  canDeactivate: [unsavedDraftGuard]
}
```

### 3.5 beforeunload

```typescript
// OperationsPageComponent

@HostListener('window:beforeunload', ['$event'])
onBeforeUnload(event: BeforeUnloadEvent): void {
  if (this.showCreateModal() && this.editingDraftHasChanges()) {
    event.preventDefault();
    event.returnValue = '';
  }
}
```

### 3.6 Подтверждение при закрытии модала

```typescript
// operation-create-modal.component.ts

onCancelClick(): void {
  if (this.hasUnsavedChanges() && this.lines().length > 0) {
    const ok = confirm(
      'У вас есть несохранённые изменения. Закрыть без сохранения?'
    );
    if (!ok) return;
    this.diagnostics.track('draft_lost', {
      draft: this.localDraft(),
      details: { items_count: this.lines().length }
    });
  }
  this.draftStorage.clear();
  this.cancel.emit();
}
```

### 3.7 Очистка черновика

```typescript
// operations-page.component.ts — onDraftSubmit

async onDraftSubmit(draft: OperationDraftVm): Promise<void> {
  // ... существующий код ...
  // После УСПЕШНОГО submit:
  this.draftStorage.clear();  // ← новый вызов
  this.diagnostics.track('draft_cleared', { draft });
}
```

---

## 4. Диагностические события (на базе Этапа 3)

| event_type | Когда | severity |
|-----------|-------|----------|
| `draft_autosaved` | Каждое автосохранение (debounced) | debug |
| `draft_restored` | Пользователь восстановил черновик | info |
| `draft_lost` | Пользователь закрыл модал без сохранения | warning |
| `draft_cleared` | Черновик удалён после успешной операции | info |

---

## 5. Файлы

| Файл | Статус | Что |
|------|--------|-----|
| `core/services/draft-storage.service.ts` | **NEW** | Сохранение/загрузка/очистка черновика |
| `core/guards/unsaved-draft.guard.ts` | **NEW** | CanDeactivate guard |
| `app.routes.ts` | modify | Добавить canDeactivate на /operations |
| `operation-create-modal.component.ts` | modify | Автосохранение, восстановление, подтверждение закрытия |
| `operations-page.component.ts` | modify | beforeunload, очистка при submit, метод editingDraftHasChanges() |

**Бэкенд-изменений нет.** Всё в Angular.

---

## 6. Тесты

### Unit

| Тест | Описание |
|------|----------|
| DraftStorageService сохраняет и загружает черновик | Round-trip save/load |
| DraftStorageService.clear удаляет запись | sessionStorage пуст после clear |
| Автосохранение срабатывает после изменения линий | Effect + debounce |
| CanDeactivate показывает confirm при изменениях | Guard + мок компонента |
| beforeunload показывает предупреждение | HostListener |

### E2E

| Сценарий | Ожидаемый результат |
|----------|-------------------|
| Заполнить форму → перейти по меню | Предупреждение, черновик сохранён |
| Заполнить форму → закрыть вкладку | Предупреждение браузера |
| Открыть модал → есть сохранённый черновик | Предложение восстановить |
| Восстановить черновик → продолжить | Данные восстановлены |
| Submit успешен → открыть модал заново | Черновик очищен, нет предложения восстановить |

---

## 7. Acceptance Criteria

1. ✅ Черновик автосохраняется в `sessionStorage` при изменении
2. ✅ Автосохранение debounced (2 с)
3. ✅ При открытии модала предлагается восстановить черновик
4. ✅ При переходе по меню — предупреждение
5. ✅ При закрытии вкладки — browser beforeunload
6. ✅ При закрытии модала с изменениями — confirm
7. ✅ После успешного submit черновик очищается
8. ✅ Диагностические события отправляются
9. ✅ `personName` не сохраняется
10. ✅ Все тесты проходят

---

## 8. Оценка

- **Сложность:** низкая
- **Время:** 1–2 часа (соло)
- **Конфликты:** нет (новые файлы + точечные правки)
- **Зависимости:** Этап 3 (DiagnosticsService для событий)
