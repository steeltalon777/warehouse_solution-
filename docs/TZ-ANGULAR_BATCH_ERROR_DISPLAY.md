# TZ: Отображение ошибок batch-операций каталога в Angular

## Execution Strategy

- [ ] 🟡 Sequential execution recommended
- **Reason:** Единственный файл изменений (`nomenclature.service.ts`), плюс тесты в том же файле. Нет параллельных work units.

## Execution Checklist

- [ ] 0. Context verified
- [ ] 1. Implementation: проверка ошибок в `applyBatch()`
- [ ] 2. Static checks: `npm run build`
- [ ] 3. Unit/component tests: проверка сценариев ошибок batch
- [ ] 4. Stand smoke tests: реальный batch с ошибкой SKU
- [ ] 5. UI automation tests: Playwright-сценарий
- [ ] 6. Regression checks: успешный batch не сломан
- [ ] 7. Documentation updated
- [ ] 8. Final acceptance review complete

---

## 1. Контекст и проблема

### Текущее поведение

При batch-операциях каталога (создание/обновление/удаление unit, category, item) SyncServer **всегда** возвращает HTTP 200. Ошибки кодируются внутри тела ответа:

```json
{
  "status": "failed",
  "summary": {"create": 0, "update": 0, "error": 1},
  "records": [
    {"local_id": "...", "entity_type": "item", "action": "create", "status": "error", "error_code": "item sku already exists", "error_message": "item sku already exists"}
  ]
}
```

Цепочка прохождения ответа:
1. SyncServer → HTTP 200, `status: "failed"` в теле
2. Django BFF → `_ok(data)` → `{ok: true, data: {...}}`
3. Angular `BffApiService.postData()` → извлекает `.data`, catchError **не срабатывает** (HTTP 200)
4. Angular `NomenclatureService.applyBatch()` → **не проверяет** `response.status` / `summary.error` → вызывает `reloadBootstrapAfterBatch()` как при успехе
5. `NomenclaturePageComponent.onApplyAll()` → очищает буфер изменений (`clearAll()`), т.к. исключения не было

**Результат:** пользователь не видит ошибку, думает что изменения сохранились, буфер очищен — данные потеряны.

### Корневая причина

`applyBatch()` не проверяет тело ответа на наличие application-level ошибок. Смотрит только на транспортные ошибки (catch блок).

---

## 2. Цель

При ошибке batch-операции (HTTP 200, но `status: "failed"` в теле):
- Пользователь видит сообщение об ошибке в красном баннере
- Буфер изменений **не очищается** — пользователь может исправить проблему и повторить

---

## 3. Scope

### In scope
- `Warehouse_frontend/src/app/core/services/nomenclature.service.ts` — метод `applyBatch()` (строки 938–970)
- `Warehouse_frontend/src/app/features/nomenclature/nomenclature-page/nomenclature-page.spec.ts` — тесты компонента (если `applyBatch` теперь может бросать исключения при batch-ошибках, тесты должны это учитывать)

### Out of scope
- SyncServer: разделение `error_code` (машинный) и `error_message` (человеческий) — отдельная задача
- Django BFF: проверка `data["status"]` и возврат HTTP-ошибки — отдельная задача
- Toast/notification-система — отдельная задача
- Подсветка конкретных failed-записей в буфере — отдельная задача

---

## 4. Реализация

### 4.1 Изменения в `applyBatch()` (nomenclature.service.ts:938–970)

**Файл:** `Warehouse_frontend/src/app/core/services/nomenclature.service.ts`

**Текущий код (строки 962–969):**
```typescript
      const response = await firstValueFrom(this.bff.postData<CatalogBatchResponse>('/catalog/admin/batch', batchRequest));
      await this.reloadBootstrapAfterBatch(changes, response);
    } catch (err: any) {
      this.error.set(err?.message || 'Batch apply failed');
      throw err;
    } finally {
      this.isSaving.set(false);
    }
```

**Новый код:**
```typescript
      const response = await firstValueFrom(this.bff.postData<CatalogBatchResponse>('/catalog/admin/batch', batchRequest));

      // Check for application-level errors in batch response (HTTP 200, but status: "failed")
      if (response.status === 'failed' || (response.summary?.error ?? 0) > 0) {
        const errorRecords = (response.records ?? []).filter(r => r.status === 'error');
        const message = this._buildBatchErrorMessage(errorRecords);
        this.error.set(message);
        throw new Error(message);  // trigger caller's catch to preserve buffer
      }

      await this.reloadBootstrapAfterBatch(changes, response);
    } catch (err: any) {
      // Only set error if not already set by batch-error check above
      if (!this.error()) {
        this.error.set(err?.message || 'Batch apply failed');
      }
      throw err;
    } finally {
      this.isSaving.set(false);
    }
```

### 4.2 Новый приватный метод `_buildBatchErrorMessage()`

**Файл:** `Warehouse_frontend/src/app/core/services/nomenclature.service.ts`

Добавить приватный метод в класс `NomenclatureService`:

```typescript
  /**
   * Build a user-facing error message from failed batch records.
   * Returns a general message with the first unique error detail.
   */
  private _buildBatchErrorMessage(errorRecords: Array<{ error_code?: string; error_message?: string }>): string {
    if (errorRecords.length === 0) {
      return 'Batch apply failed';
    }
    // Collect unique error messages (deduplicate)
    const uniqueMessages = [...new Set(
      errorRecords.map(r => r.error_message || r.error_code || 'Unknown error')
    )];
    const detail = uniqueMessages.join('; ');
    return `Ошибка сохранения (${errorRecords.length}): ${detail}`;
  }
```

### 4.3 Точное место вставки

Метод `_buildBatchErrorMessage` разместить **перед** методом `applyBatch()` (перед строкой 938), в той же секции `// ─── Batch apply ───`.

---

## 5. Приёмочные критерии

### AC-1: Ошибка batch отображается пользователю
- **Дано:** в буфере есть изменение, вызывающее ошибку (например, item с существующим SKU)
- **Когда:** пользователь нажимает «Применить все»
- **Тогда:** появляется красный баннер с текстом ошибки (например: «Ошибка сохранения (1): item sku already exists»)

### AC-2: Буфер не очищается при ошибке
- **Дано:** batch завершился с ошибкой
- **Когда:** пользователь видит баннер ошибки
- **Тогда:** pending changes остаются в буфере, кнопка «Применить все» активна, пользователь может исправить и повторить

### AC-3: Успешный batch работает как прежде
- **Дано:** все изменения валидны
- **Когда:** пользователь нажимает «Применить все»
- **Тогда:** изменения применены, буфер очищен, бутстрап перезагружен, ошибок нет

### AC-4: Транспортные ошибки работают как прежде
- **Дано:** SyncServer недоступен
- **Когда:** пользователь нажимает «Применить все»
- **Тогда:** красный баннер с сообщением о недоступности сервера, буфер не очищен

### AC-5: Несколько ошибок агрегируются
- **Дано:** batch содержит несколько записей с разными ошибками
- **Когда:** batch завершается с `status: "failed"` и несколькими error-записями
- **Тогда:** сообщение содержит количество ошибок и уникальные сообщения (дедуплицированные)

---

## 6. Тестовая стратегия

| Уровень | Что проверяется | Как |
|---|---|---|
| 1. Static checks | Сборка без ошибок | `npm run build` в `Warehouse_frontend/` |
| 2. Unit tests | `_buildBatchErrorMessage` с разными входными данными | Новые unit-тесты (опционально, если в проекте есть test runner) |
| 3. Component tests | `onApplyAll` при ошибке batch не очищает буфер | Обновить `nomenclature-page.spec.ts` — убедиться что `clearAll` не вызывается при rejected `applyBatch` |
| 4. Stand smoke | Реальный batch с конфликтом SKU | Создать item с существующим SKU через UI, проверить баннер ошибки |
| 5. UI automation | Playwright-сценарий: создать item с дублирующимся SKU | `make test-e2e` или headed-режим |
| 6. Regression | Успешный batch всё ещё работает | Создать уникальный item через UI, проверить что применился без ошибок |

### 6.1 Stand smoke-тест (ручной)

**Стенд:** Docker, `make up` из корня workspace.

1. Открыть `http://localhost:8001/nomenclature/editable/`
2. Создать новый item с SKU, который уже существует в каталоге
3. Нажать «Применить все»
4. **Ожидается:** красный баннер «Ошибка сохранения (1): item sku already exists»
5. **Ожидается:** изменения остались в буфере
6. Исправить SKU на уникальный
7. Нажать «Применить все»
8. **Ожидается:** изменения применены, баннера ошибки нет

### 6.2 Playwright-тест

Добавить в `Warehouse_frontend/e2e/` сценарий:
1. Залогиниться как chief_storekeeper
2. Перейти на `/nomenclature/editable/`
3. Создать item с заведомо существующим SKU (взять из seed-данных)
4. Нажать «Применить все»
5. Проверить видимость `.wh-state--error` с текстом содержащим «item sku already exists»
6. Проверить что кнопка «Применить все» всё ещё активна (буфер не очищен)

---

## 7. Файлы затрагиваемые

| Файл | Характер изменений |
|---|---|
| `Warehouse_frontend/src/app/core/services/nomenclature.service.ts` | Добавить `_buildBatchErrorMessage()`, изменить `applyBatch()` |
| `Warehouse_frontend/src/app/features/nomenclature/nomenclature-page/nomenclature-page.spec.ts` | Обновить тесты если `applyBatch` теперь выбрасывает исключения при batch-ошибках |

---

## 8. Риски

| Риск | Вероятность | Влияние | Митигация |
|---|---|---|---|
| Двойная установка `this.error` (в `applyBatch` и в `catch`) | Низкая | Дублирование сообщения | Проверка `if (!this.error())` перед установкой в catch |
| `onApplyAll` не ожидает исключения от `applyBatch` при batch-ошибках | Низкая | Буфер очистится | Уже обрабатывается: `onApplyAll` имеет `try/catch`, в catch ничего не делает (буфер не чистится) |

---

## 9. Архитектурный обзор

**Вердикт:** Approved — no blockers.

См. полный stress-test в разделе «Архитектурный stress-test» выше по контексту. Кратко:

- ✅ Простейшее возможное решение (один файл, ~15 строк кода)
- ✅ Не меняет контракты API
- ✅ Не добавляет новых зависимостей
- ✅ Не создаёт новых failure modes
- ✅ Полностью обратно совместимо

---

## Check Rules

- Architect создаёт checklist и acceptance criteria.
- Executor agents отмечают implementation и test items только после запуска требуемой верификации.
- QA verifier отмечает final acceptance только после проверки evidence.
- Если проверка пропущена — остаётся unchecked с причиной в отчёте.
