# TZ: V3.1G — Operations UX Hardening

**Date:** 2026-06-22
**Based on:** Инцидент на проде 22.06.2026 — 500 при submit с дубликатом SKU
**Status:** Ready

## Execution Strategy

- [x] 🔴 Sequential: backend → BFF → frontend
- **Reason:** Backend должен вернуть читаемую ошибку, BFF пробросить, фронтенд показать. Каждый слой зависит от предыдущего.

---

## Execution Checklist

- [x] 0. Context verified — инцидент разобран, цепочка восстановлена
- [x] 1. Stage G1: SyncServer — человекочитаемые ошибки submit
- [x] 2. Stage G1 tests: unit tests for error mapping
- [x] 3. Stage G2: Warehouse_web BFF — проброс detail в errors
- [x] 4. Stage G2 tests: unit + stand smoke
- [x] 5. Stage G3: Angular — модалка/тост с ошибкой
- [x] 6. Stage G3 tests: Playwright smoke (вызвать ошибку → проверить отображение)
- [x] 7. Integration: E2E flow с искусственной ошибкой
- [x] 8. Regression: SyncServer 410+ tests, Django 325 tests, Angular build
- [x] 9. Final acceptance review

---

## Диагноз (контекст)

22.06.2026 кладовщик создал операцию прихода с inline-ТМЦ, указал SKU `М0001789`, который уже существует в каталоге (item id=1576, создан 02.06.2026). При submit SyncServer вернул 500:

```
IntegrityError: duplicate key value violates unique constraint "items_sku_key"
```

Фронтенд не показал читаемую ошибку — кладовщик не понял, что не так.

**Корень:** три проблемы:
1. SyncServer возвращает 500 вместо HTTP 409 с понятным `detail`
2. BFF не маппит ошибку в читаемый формат
3. Angular не показывает `detail` пользователю

---

## Stage G1: SyncServer — человекочитаемые ошибки submit

### Задача G1.1: Обработать `IntegrityError` на дубликат SKU

**Файл:** `SyncServer/app/services/operations_service.py`

В методе `_materialize_deferred_temporary_lines` обернуть `uow.catalog.create_item(review_item)` в try/except:

```python
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from starlette import status

try:
    review_item = await uow.catalog.create_item(review_item)
except IntegrityError as exc:
    # Check if it's a SKU duplicate
    if "items_sku_key" in str(exc):
        sku = payload.get("sku") or "(без SKU)"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"SKU «{sku}» уже занят. Укажите другой SKU или оставьте поле пустым для автоматической генерации.",
        )
    raise
```

### Задача G1.2: Обработать другие возможные ошибки submit

**Файл:** `SyncServer/app/services/operations_service.py`

В `submit_operation` добавить универсальный обработчик для бизнес-ошибок:

```python
except HTTPException:
    raise  # пробрасываем как есть
except IntegrityError as exc:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"Конфликт данных при подтверждении операции: {_extract_user_message(exc)}",
    )
```

### Задача G1.3: Валидация SKU на этапе создания inline-черновика

**Файл:** `SyncServer/app/api/routes_operations.py` (или соответствующий эндпоинт)

При добавлении строки с `temporary_draft_payload`, если в payload есть `sku`, проверить `items_sku_key` uniqueness **до** submit:

```python
if payload.get("sku"):
    existing = await uow.items.get_by_sku(payload["sku"])
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"SKU «{payload['sku']}» уже занят товаром «{existing.name}»",
        )
```

Это даст мгновенную обратную связь кладовщику при добавлении строки, а не при submit.

### Acceptance criteria G1

- [x] Submit с дубликатом SKU → HTTP 409 с читаемым сообщением
- [x] Submit с валидными данными → 200, операция подтверждена
- [x] Добавление строки с занятым SKU → HTTP 409 до submit
- [x] Существующие тесты проходят (415 тестов)

---

## Stage G2: Warehouse_web BFF — проброс ошибок

### Задача G2.1: Маппинг SyncServer-ошибок в BFF

**Файл:** `Warehouse_web/apps/sync_client/client.py`

В `_raise_for_response` добавить маппинг 409:

```python
elif status_code == 409:
    detail = resp_json.get("detail", "Конфликт данных")
    raise SyncServerAPIError(status_code=409, detail=detail, ...)
```

### Задача G2.2: BFF view — возврат detail клиенту

**Файл:** `Warehouse_web/apps/bff_api/views.py` (или где обрабатывается submit)

Убедиться, что ошибка из SyncServer возвращается фронтенду с сохранением `detail`:

```python
except SyncServerAPIError as exc:
    return JsonResponse(
        {"error": exc.detail, "status": exc.status_code},
        status=exc.status_code,
    )
```

### Acceptance criteria G2

- [x] BFF пробрасывает 409 от SyncServer как JSON с полем `error`
- [x] BFF возвращает правильный HTTP-статус
- [x] `python manage.py test` — BFF-тесты зелёные (3 независимых pre-existing failure)

---

## Stage G3: Angular — отображение ошибок

### Задача G3.1: Перехват ошибок в operation-create-modal

**Файл:** `Warehouse_frontend/src/app/features/operations/components/operation-create-modal/operation-create-modal.component.ts`

В методе submit перехватывать ошибку и показывать в UI:

```typescript
this.operationsService.submit(this.operationId()).subscribe({
    next: () => { /* success */ },
    error: (err) => {
        this.submitError.set(err.error?.error || err.error?.detail || 'Не удалось подтвердить операцию');
    }
});
```

### Задача G3.2: Компонент ошибки (alert/тост)

**Файлы:**
- `Warehouse_frontend/src/app/shared/components/error-alert/error-alert.component.ts` — новый компонент
- Использовать в operation-create-modal, operation-acceptance-page

```html
@if (submitError()) {
    <div class="alert alert-error">
        <span class="alert-icon">⚠️</span>
        <span>{{ submitError() }}</span>
        <button (click)="submitError.set('')">×</button>
    </div>
}
```

### Задача G3.3: Валидация SKU на фронтенде

**Файл:** `Warehouse_frontend/src/app/features/operations/components/inline-item-create-modal/`

При вводе SKU — проверять через BFF `/bff/api/v1/catalog/check-sku?sku=...` (если такой эндпоинт есть) или показывать предупреждение.

Минимально: после ошибки 409 от сервера — показать понятное сообщение.

### Acceptance criteria G3

- [x] Ошибка submit показывается в модалке/алерте
- [x] Текст ошибки — тот `detail`, который пришёл от SyncServer
- [x] Пользователь может закрыть алерт и исправить данные
- [x] `npm run build` — успешно

---

## Files in scope

| Файл | Этап | Тип изменений |
|---|---|---|
| `SyncServer/app/services/operations_service.py` | G1 | `IntegrityError` → `HTTPException(409)` |
| `SyncServer/app/api/routes_operations.py` | G1 | SKU validation на этапе draft |
| `Warehouse_web/apps/sync_client/client.py` | G2 | Маппинг 409 |
| `Warehouse_web/apps/bff_api/views.py` | G2 | Проброс detail |
| `Warehouse_frontend/src/app/features/operations/` | G3 | Error alert в модалках |
| `Warehouse_frontend/src/app/shared/components/error-alert/` | G3 | Новый компонент |

## Out of scope

- Рендеринг накладных (3.1H)
- Валидация SKU на каждый keystroke (дорого, можно в будущем)
- Локализация ошибок (пока русский)
- Алерты/тосты за пределами operations-экранов

## Test Ladder

| Level | Применение |
|---|---|
| Static checks | ✅ ruff + mypy для SyncServer, Angular build |
| Unit tests | ✅ test IntegrityError → 409 в SyncServer, test BFF error mapping |
| Component tests | ✅ Django test client: submit → 409 → JSON error |
| Integration tests | ✅ SyncServer + PostgreSQL: submit с дубликатом → 409 |
| Stand smoke tests | ✅ Dev-стенд: создать операцию с дубликатом SKU → проверить ответ |
| UI automation | ✅ Playwright: заполнить inline-ТМЦ → submit → проверить алерт |
| User scenarios | ✅ Кладовщик: создать приход с занятым SKU → увидеть ошибку → исправить → подтвердить |
| Regression pack | ✅ SyncServer 410+ tests, Django 325 tests, Angular build |
| Acceptance review | ✅ Evidence table |

## Stand Requirements

- Docker dev-стенд: все сервисы
- Django admin: `admin`/`admin123`
- Данные: нужен хотя бы один существующий item с известным SKU для теста дубликата
