# Contract Package: Draft Protection (Stage 4)

**Дата заморозки:** 2026-07-15
**Источник ТЗ:** `docs/TZ-DRAFT_PROTECTION_STAGE4.md`
**Архитектурное ревью:** `docs/archive/ARCHITECTURE_REVIEW_ANGULAR_UI_DIAGNOSTICS.md` §7, RISK-005, RISK-008 (frozen)
**Статус:** Заморожено до старта реализации. Изменения только через ADR.

---

## Содержание

1. [Глоссарий](#1-глоссарий)
2. [Storage contract](#2-storage-contract)
3. [DraftStorageService API](#3-draftstorageservice-api)
4. [Integration в Angular](#4-integration-в-angular)
5. [CanDeactivate guard](#5-candeactivate-guard)
6. [beforeunload](#6-beforeunload)
7. [Диагностические события](#7-диагностические-события)
8. [Acceptance criteria](#8-acceptance-criteria)
9. [PII и scope guard](#9-pii-и-scope-guard)
10. [Файлы-зоны](#10-файлы-зоны)

---

## 1. Глоссарий

| Термин | Значение |
|---|---|
| `draft` | `OperationDraftVm` — сериализуемая модель черновика |
| `sessionStorage` | Browser API, очищается при закрытии вкладки (НЕ переживает рестарт браузера) |
| `PREFIX` | префикс ключа sessionStorage: `warehouse.draft.v1` |
| `snapshotDraft()` | Существующий (Этап 0-2) helper — возвращает JSON-строку draft'а |
| `isDraftClean()` | Существующий helper — `snapshotDraft(d) === d.lastSavedSnapshot` |
| `TTL черновика` | 24 часа (после — `load()` возвращает null) |
| `Debounce` | 2 секунды бездействия перед автосохранением |

---

## 2. Storage contract

### 2.1 Storage key

```text
warehouse.draft.v1.<session_id>
```

- **Per-session:** ключ включает `session_id` из `DiagnosticsSessionService` (Этап 1).
- Это обеспечивает разделение черновиков между разными логическими сессиями пользователя (например, разные пользователи за одним браузером).
- В **одной** сессии — один черновик.

### 2.2 Storage value (JSON-serialized `SavedDraft`)

```typescript
interface SavedDraft {
  /** JSON-строка из snapshotDraft(draft) — содержит все сериализуемые поля. */
  draft: string;
  /** ISO 8601 — когда был сохранён. */
  savedAt: string;
  /** Idempotency key из draft'а. */
  idempotencyKey: string;
  /** Draft id из draft'а. */
  draftId: string;
  /** Operation type (для diagnostics). */
  operationType: string;
  /** Schema version — для будущей миграции. */
  schemaVersion: 1;
}
```

### 2.3 Что НЕ сохраняется (PII guard)

Per TZ §1 и §9: **НЕ** сохраняется:
- `personName` (персональные данные)
- `comment` (опционально — НЕ сохраняем в v1 для простоты)

`DraftStorageService.save()` обязан стереть эти поля перед сериализацией. Это defense-in-depth: даже если в `OperationDraftVm` появятся новые PII-поля, они НЕ попадут в sessionStorage, пока сервис явно не разрешит.

### 2.4 TTL

- **24 часа** от `savedAt`. После — `load()` возвращает `null`, `clear()` удаляет запись.
- `hasDraft()` учитывает TTL (если expired, возвращает `false`).

---

## 3. DraftStorageService API

Файл: `Warehouse_frontend/src/app/core/services/draft-storage.service.ts` (NEW).

```typescript
@Injectable({ providedIn: 'root' })
export class DraftStorageService {
  /** Полный ключ (с session_id). */
  private storageKey(): string;

  /** Сохранить draft. Идемпотентно — сохраняет только если lines.length > 0. */
  save(draft: OperationDraftVm): boolean;

  /** Загрузить черновик. Возвращает null если нет или expired (>24h). */
  load(): SavedDraft | null;

  /** Проверить наличие валидного (не expired) черновика. */
  hasDraft(): boolean;

  /** Удалить черновик из sessionStorage. */
  clear(): void;

  /** Получить метаданные черновика без полного payload (для UI). */
  getMetadata(): { savedAt: string; itemsCount: number; operationType: string } | null;
}
```

### 3.1 Контракт `save()`

- **Input:** `OperationDraftVm`
- **Output:** `boolean` — `true` если сохранено, `false` если отказано (нет lines или другая причина)
- **Side-effect:** пишет в `sessionStorage` под ключом `warehouse.draft.v1.<session_id>`
- **Edge cases:**
  - `draft.lines.length === 0` → возвращает `false`, ничего не пишет
  - sessionStorage недоступен (private mode в некоторых браузерах) → `try/catch` → возвращает `false`
  - `personName`/`comment` стираются перед сериализацией

### 3.2 Контракт `load()`

- **Input:** —
- **Output:** `SavedDraft | null`
- **Поведение:**
  - Нет записи в sessionStorage → `null`
  - Запись есть, но `savedAt` > 24h назад → `null` (и автоматически `clear()`)
  - `schemaVersion !== 1` → `null` (будуще-совместимо)
  - JSON parse error → `null` (и `clear()`)
- **Side-effect:** может удалить expired/invalid записи

### 3.3 Контракт `clear()`

- Удаляет ключ из sessionStorage
- **Безопасно вызывать** если ключа нет (no-op)

### 3.4 Контракт `hasDraft()`

- Возвращает `load() !== null` — т.е. учитывает TTL и валидность

### 3.5 Контракт `getMetadata()`

- Возвращает **только метаданные** (savedAt, itemsCount, operationType) — для показа в UI-баннере восстановления
- Не возвращает полный `SavedDraft` (нет смысла — UI не показывает контент до явного restore)

---

## 4. Integration в Angular

### 4.1 Автосохранение (effect в modal)

Файл: `operation-create-modal.component.ts` — constructor, новый effect.

```typescript
effect(() => {
  const draft = this.localDraft();
  if (draft.lines.length > 0) {
    // Debounce 2s
    this.scheduleAutosave(draft);
  }
});
```

**Реализация debounce** через `setTimeout`:
- Каждый вызов effect'а **отменяет** предыдущий timer
- Через 2 секунды бездействия — `draftStorage.save(draft)` + `diag.track('draft_autosaved', ...)`

### 4.2 Восстановление при открытии

Файл: `operation-create-modal.component.ts` — `ngOnInit` (или effect на input draft()).

```typescript
ngOnInit(): void {
  // ... существующая логика ...
  this.attemptRestore();
}

private attemptRestore(): void {
  const saved = this.draftStorage.load();
  if (saved && !this.draft()) {
    const restore = confirm('Найден несохранённый черновик. Восстановить?');
    if (restore) {
      // Парсим saved.draft, создаём draft через обратный mapper
      // (нужно изучить, как draft'ы десериализуются)
      this.diag.track('draft_restored', { draft: { draftId: saved.draftId } });
    } else {
      this.draftStorage.clear();
    }
  }
}
```

**Edge case:** если пользователь **отказался** восстанавливать — очищаем storage, чтобы не спрашивать снова.

### 4.3 Подтверждение при закрытии модала

Файл: `operation-create-modal.component.ts` — новый метод `onCancelClick()` (если ещё нет), или модификация `onCancel()`.

```typescript
onCancel(): void {
  if (this.hasUnsavedChanges() && this.linesCount() > 0) {
    const ok = confirm('У вас есть несохранённые изменения. Закрыть без сохранения?');
    if (!ok) return;
    this.diag.track('draft_lost', { draft: this.localDraft() });
  }
  this.draftStorage.clear();
  this.cancel.emit();
}
```

### 4.4 Очистка после успешного submit

Файл: `operations-page.component.ts` — `onDraftSubmit` после успеха.

```typescript
async onDraftSubmit(draft: OperationDraftVm): Promise<void> {
  // ... существующий код ...
  try {
    const result = await this.service.submitWithResult(draft);
    this.applySubmitResult(result);
    await this.refreshListAfterSubmit();
    // WP-4: после успешного submit очищаем черновик
    this.draftStorage.clear();
    this.diag.track('draft_cleared', { draft });
  } catch (err: any) {
    // ... существующая обработка ...
  }
}
```

---

## 5. CanDeactivate guard

Файл: `Warehouse_frontend/src/app/core/guards/unsaved-draft.guard.ts` (NEW).

```typescript
import { CanDeactivateFn } from '@angular/router';
import { OperationsPageComponent } from '../../features/operations/pages/operations-page/operations-page.component';

export const unsavedDraftGuard: CanDeactivateFn<OperationsPageComponent> = (
  component: OperationsPageComponent,
): boolean => {
  if (component.showCreateModal() && component.editingDraftHasChanges()) {
    return confirm('У вас есть несохранённые изменения. Покинуть страницу?');
  }
  return true;
};
```

**Контракт:**
- Возвращает `true` если можно покинуть
- Возвращает `true` если нет открытого модала (route guard только при активном draft)
- Возвращает `boolean` (Angular сам интерпретирует `false` как отмену навигации)
- `component.editingDraftHasChanges()` — публичный метод на `OperationsPageComponent` (см. §6.2)

### 5.1 Регистрация в routes

Файл: `app.routes.ts` — модифицировать.

```typescript
import { unsavedDraftGuard } from './core/guards/unsaved-draft.guard';

{
  path: 'operations',
  loadComponent: () => import('./features/operations/pages/operations-page/operations-page.component').then(m => m.OperationsPageComponent),
  canDeactivate: [unsavedDraftGuard],  // ← NEW
},
```

> **Важно:** guard не должен блокировать навигацию на дочерние роуты типа `/operations/:id/acceptance` — там нет открытого модала. Проверка `showCreateModal()` это обеспечивает.

---

## 6. beforeunload

Файл: `operations-page.component.ts` — HostListener.

```typescript
@HostListener('window:beforeunload', ['$event'])
onBeforeUnload(event: BeforeUnloadEvent): void {
  if (this.showCreateModal() && this.editingDraftHasChanges()) {
    event.preventDefault();
    event.returnValue = '';
  }
}
```

**Контракт:**
- Срабатывает при закрытии вкладки / refresh / переходе на внешний URL
- **НЕ** срабатывает при in-app роутинге (для этого — CanDeactivate)
- Браузер сам показывает системный диалог (Chrome, Firefox, Edge) — мы только сигнализируем

### 6.1 `editingDraftHasChanges()` на компоненте

Файл: `operations-page.component.ts` — публичный метод.

```typescript
public editingDraftHasChanges(): boolean {
  const draft = this.editingDraft();
  if (!draft) return false;
  return this.hasUnsavedChangesForDiagnostics();
  // или переиспользовать существующий hasUnsavedChanges
}
```

---

## 7. Диагностические события

Per TZ §4. Используем существующий `DiagnosticsService` из Этапа 3.

| event_type | Severity | Когда | details |
|-----------|----------|-------|---------|
| `draft_autosaved` | debug | Каждое автосохранение (debounced 2s) | `{ items_count }` |
| `draft_restored` | info | Пользователь подтвердил восстановление | `{ draftId, items_count }` |
| `draft_lost` | warning | Пользователь закрыл модал с несохранёнными | `{ draft, items_count }` |
| `draft_cleared` | info | После успешного submit | `{ draft, operationType }` |

**Расширение `DiagnosticEventType` enum (TZ §3.1):** добавить 4 новых типа в `diagnostics.models.ts`.

**Расширение `severityFor()` в `diagnostics.service.ts`:** добавить маппинг для 4 новых типов:
- `draft_autosaved` → `debug`
- `draft_restored`, `draft_cleared` → `info`
- `draft_lost` → `warning`

---

## 8. Acceptance criteria

Per TZ §7:

1. ✅ Черновик автосохраняется в `sessionStorage` при изменении
2. ✅ Автосохранение debounced (2 с)
3. ✅ При открытии модала предлагается восстановить черновик
4. ✅ При переходе по меню — CanDeactivate guard с confirm
5. ✅ При закрытии вкладки — browser beforeunload
6. ✅ При закрытии модала с изменениями — confirm
7. ✅ После успешного submit черновик очищается
8. ✅ Диагностические события (`draft_autosaved`/`restored`/`lost`/`cleared`) отправляются
9. ✅ `personName`/`comment` НЕ сохраняются
10. ✅ Все unit + e2e тесты проходят

---

## 9. PII и scope guard

### 9.1 Что НЕ сохраняется

Per TZ §1:
- `personName` (ФИО получателя) — **НИКОГДА**
- `comment` — **НЕ сохраняем в v1** для простоты (может содержать PII)

`DraftStorageService.save()` явно стирает эти поля:

```typescript
const safeDraft = { ...draft };
delete safeDraft.personName;
delete safeDraft.comment;
const draftJson = snapshotDraft(safeDraft);
```

### 9.2 Session-scope

Черновик хранится **per session** (через `session_id` в ключе). При logout / new session — старый черновик остаётся в sessionStorage, но **не виден** (другой session_id → другой ключ). После закрытия вкладки — sessionStorage очищается браузером.

### 9.3 Не сохраняется в localStorage / IndexedDB

Per TZ §1. Используется ТОЛЬКО `sessionStorage`. Это сознательное ограничение: не хотим, чтобы черновики с конфиденциальными данными (имена ТМЦ, описания) жили дольше одной сессии.

---

## 10. Файлы-зоны

### Создать (NEW)
- `Warehouse_frontend/src/app/core/services/draft-storage.service.ts`
- `Warehouse_frontend/src/app/core/services/draft-storage.service.spec.ts`
- `Warehouse_frontend/src/app/core/guards/unsaved-draft.guard.ts`
- `Warehouse_frontend/src/app/core/guards/unsaved-draft.guard.spec.ts`

### Модифицировать
- `Warehouse_frontend/src/app/core/diagnostics/diagnostics.models.ts` — добавить 4 event_type
- `Warehouse_frontend/src/app/core/diagnostics/diagnostics.service.ts` — добавить severity mapping
- `Warehouse_frontend/src/app/app.routes.ts` — добавить `canDeactivate: [unsavedDraftGuard]`
- `Warehouse_frontend/src/app/features/operations/components/operation-create-modal/operation-create-modal.component.ts` — autosave effect + restore + onCancel confirm
- `Warehouse_frontend/src/app/features/operations/pages/operations-page/operations-page.component.ts` — `editingDraftHasChanges()` + beforeunload + onDraftSubmit clear

### Не трогать
- `SyncServer/`, `Warehouse_web/` (только Angular)
- Существующие E2E тесты (если только не нужно обновить fixtures)

### E2E (опционально)
- `Warehouse_frontend/e2e/draft-protection.spec.ts` (NEW) — seed-independent сценарии

---

**Конец контракта.** Никакой production-код в WP-0. Реализация начинается в WP-1 (singleton, в одном проходе).
