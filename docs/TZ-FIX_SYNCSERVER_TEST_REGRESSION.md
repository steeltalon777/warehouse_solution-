# TZ: Исправление регрессии тестов SyncServer после TZ Transport Hardening и Catalog Created/Updated By

## Execution Strategy

- [x] 🟢 Parallel execution recommended
- **Reason:** Stage 0 (архитектурное решение) принят клиентом — целевой flow: постоянные ТМЦ с `requires_review`. Шесть проблем независимы по файлам. Пять правок (rate limiter, пути, моки, FK, delete policy) делаются параллельно. Stage 3 (переписывание тестов) зависит от Stage 0 и может стартовать сразу.

## Execution Checklist

- [x] 0. Context verified
- [x] 1. Stage 0: Архитектурное решение принято — новый Review Item flow, обратная совместимость с TemporaryItem
- [x] 2. Stage 1-A: Rate limiter reset fixture в тестах
- [x] 3. Stage 1-B: Исправить пути в `test_temporary_items_delete.py`
- [x] 4. Stage 1-C: Добавить `temporary_draft_payload` в тестовые моки `OperationLine`
- [x] 5. Stage 1-D: Исправить FK `resolved_item_id=999` в `test_delete_temporary_item_already_resolved`
- [x] 6. Stage 2: Согласовать и исправить Operation Delete Policy + порядок проверок
- [x] 7. Stage 3: Переписать тесты phase1/stage3a/stage3b на Review Item flow
- [x] 8. Static checks: импорты, collect-only
- [x] 9. Unit/component tests: полный прогон
- [x] 10. Integration tests: DB-backed
- [x] 11. Stand smoke tests (SyncServer + PostgreSQL)
- [x] 12. Regression: все тесты SyncServer — `python -m pytest`
- [x] 13. Documentation updated
- [x] 14. Final acceptance review complete

---

## 1. Контекст

После реализации двух TZ:
- `TZ-DJANGO_SYNCSERVER_TRANSPORT_HARDENING.md`
- `TZ-CATALOG_CREATED_BY_UPDATED_BY.md`

в SyncServer накопились несоответствия между кодом и тестами. Рецензент зафиксировал 28 падений, сгруппированных в 6+1 проблем. Данное TZ описывает все необходимые исправления.

**Источники:**
- `Functional and WorkLogik.md` — канонические требования
- `SyncServer/app/api/deps.py` — rate limiter
- `SyncServer/app/api/routes_operations.py` — delete endpoint
- `SyncServer/app/services/operations_policy.py` — delete permission
- `SyncServer/app/services/operations_service.py` — `_materialize_deferred_temporary_lines`
- `SyncServer/app/services/operations_workflow_policy.py` — workflow guards
- `SyncServer/tests/test_temporary_items_delete.py` — неправильные пути
- `SyncServer/tests/test_operations_service_inventory_subject_write_path.py` — устаревшие моки
- `SyncServer/tests/test_operations_permissions.py` — unit-тесты delete permission
- `SyncServer/tests/test_operations_delete_api.py` — API-тесты delete
- `SyncServer/tests/test_temporary_items_phase1.py` — тесты старого TemporaryItem flow

---

## 2. Диагностика проблем

### Problem 1: Rate limiter сохраняет состояние между тестами

**Симптом:** `test_pull_ordering` получает `429 Too Many Requests`.

**Причина:** `InMemoryRateLimiter` — глобальный синглтон уровня модуля (`deps.py:41`). Ключи строятся как `{route}:{ip}:{device_id}`. С `ASGITransport` IP всегда `"unknown"`, device_id уникален в каждом тесте — НО при быстром последовательном запуске тестов push/ping в пределах одного файла rate limiter может срабатывать по пересекающимся ключам. Кроме того, состояние словаря `_last_hit` накапливается и не очищается между тест-функциями.

Класс уже имеет метод `reset()`, но он нигде не вызывается в тестовой инфраструктуре. Единственное исключение — `test_auth_unified.py:27,39`, но это локальная фикстура только для того файла.

**Исправление:** Добавить `autouse` fixture в `SyncServer/tests/conftest.py`:
```python
import pytest
from app.api.deps import rate_limiter

@pytest.fixture(autouse=True)
async def reset_rate_limiter():
    await rate_limiter.reset()
    yield
```

**Альтернативно:** отключать rate-limit при `APP_ENV=testing` — в `deps.py` проверять `get_settings().APP_ENV` и пропускать `enforce_rate_limit`.

**Рекомендация:** fixture reset — минимальное вмешательство, не меняет production-код.

**Файлы:**
- Изменить: `SyncServer/tests/conftest.py` — добавить fixture
- Не трогать: `SyncServer/app/api/deps.py`

---

### Problem 2: Тесты `test_temporary_items_delete.py` используют пути без `/api/v1`

**Симптом:** `DELETE /temporary-items/{id}` → `404 Not Found`.

**Причина:** Роутер `temporary_items_router` зарегистрирован с префиксом `/api/v1` (`main.py:116`), и его собственный префикс `/temporary-items` даёт полный путь `/api/v1/temporary-items/{id}`. Но все 7 вызовов `client.delete()` в `test_temporary_items_delete.py` используют `/temporary-items/...` без `/api/v1/`.

**Исправление:** Во всех 7 местах заменить:
```python
f"/temporary-items/{...}"  →  f"/api/v1/temporary-items/{...}"
```

**Файлы:**
- Изменить: `SyncServer/tests/test_temporary_items_delete.py` (строки 136, 187, 243, 259, 284, 299, 326)

**Важно:** Не добавлять compatibility route. `/api/v1` — canonical contract (зафиксировано TZ transport hardening, раздел 5).

---

### Problem 3: Конфликт `require_operation_delete_permission` с тестами

**Текущий код** (`operations_policy.py:88-95`):
```python
def require_operation_delete_permission(identity, operation):
    if identity.is_root:
        return
    raise HTTPException(403, "only root may delete cancelled operations")
```
Только root может удалять cancelled операции.

**API тесты ожидают** (`test_operations_delete_api.py`):
| Тест | Роль | Операция | Ожидание |
|------|------|----------|----------|
| `test_delete_cancelled_operation_returns_204` | storekeeper | своя cancelled | **204** ✅ |
| `test_storekeeper_cannot_delete_other_creators_...` | storekeeper | чужая cancelled | 403 |
| `test_chief_storekeeper_can_delete_any_cancelled_operation` | chief | любая cancelled | **204** ✅ |
| `test_root_can_delete_any_cancelled_operation` | root | любая cancelled | 204 |
| `test_observer_cannot_delete_cancelled_operation` | observer | любая cancelled | 403 |
| `test_delete_draft_operation_returns_409` | storekeeper | своя draft | **409** |
| `test_delete_submitted_operation_returns_409` | chief | submitted | **409** |

**Unit тесты permissions ожидают** (`test_operations_permissions.py`):
| Тест | Роль | Ожидание | Конфликт |
|------|------|----------|----------|
| `test_root_can_delete_any_cancelled_operation` | root | ✅ pass | — |
| `test_chief_storekeeper_cannot_delete_cancelled_operation` | chief | ❌ 403 | **конфликтует с API тестом** |
| `test_storekeeper_cannot_delete_cancelled_operation` | storekeeper (своя) | ❌ 403 | **конфликтует с API тестом** |

**Порядок проверок в `routes_operations.delete_operation`** (строка 242-263):
```python
operation = await uow.operations.get_operation_by_id(...)  # 404 если нет
OperationsPolicy.require_operate_site(...)                   # 403 если нет доступа к сайту
OperationsPolicy.require_operation_delete_permission(...)    # 403 если не root
await OperationsService.delete_operation(...)                # 409 если не cancelled
```
Permission check (403) вызывается ДО workflow check (409). Draft/submitted операции получают 403 вместо 409.

**Исправление:**

1. **Обновить `require_operation_delete_permission`** — проверять статус операции:
```python
@staticmethod
def require_operation_delete_permission(identity, operation) -> None:
    # Root: always
    if identity.is_root:
        return
    # Chief: any cancelled
    if identity.role == "chief_storekeeper" and operation.status == "cancelled":
        return
    # Storekeeper: own cancelled
    if (identity.role == "storekeeper"
        and operation.status == "cancelled"
        and operation.created_by_user_id == identity.user_id):
        return
    # Everyone else: 403 (observers, non-owners, non-cancelled — см. следующий пункт)
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                        detail="only the operation owner (storekeeper), chief_storekeeper, "
                               "or root may delete cancelled operations")
```

2. **Поменять порядок проверок в `routes_operations.delete_operation`** — workflow ДО permission для некорректных статусов:
```python
async def delete_operation(...):
    async with uow:
        operation = await uow.operations.get_operation_by_id(operation_id)
        if not operation:
            raise HTTPException(404, ...)
        OperationsPolicy.require_operate_site(identity, operation.site_id)

        # Workflow guard FIRST: non-cancelled → 409 сразу, не проходя permission
        OperationsWorkflowPolicy.require_cancelled_for_delete(operation)

        OperationsPolicy.require_operation_delete_permission(identity, operation)

        await OperationsService.delete_operation(...)
```

Но тогда `require_cancelled_for_delete` будет вызываться из роута, а не из сервиса. Нужно добавить импорт `OperationsWorkflowPolicy` в роут. Текущий код в сервисе (`delete_operation` на `operations_service.py:1102`) тоже вызывает `require_cancelled_for_delete` — его надо убрать ИЛИ оставить как defence-in-depth.

**Рекомендация:** workflow guard в роуте (чтобы гарантировать 409 до 403), а в сервисе оставить как defence-in-depth.

3. **Обновить unit-тесты `test_operations_permissions.py`:**
   - `test_chief_storekeeper_cannot_delete_cancelled_operation` → переименовать в `test_chief_storekeeper_can_delete_cancelled_operation`, ожидать pass
   - `test_storekeeper_cannot_delete_cancelled_operation` → переименовать в `test_storekeeper_can_delete_own_cancelled_operation`, ожидать pass для своей операции
   - Добавить `test_storekeeper_cannot_delete_others_cancelled_operation` → 403 для чужой

**Файлы:**
- Изменить: `SyncServer/app/services/operations_policy.py` (строки 88-95)
- Изменить: `SyncServer/app/api/routes_operations.py` (строки 243-261)
- Изменить: `SyncServer/app/services/operations_service.py` (строка 1103 — опционально)
- Изменить: `SyncServer/tests/test_operations_permissions.py` (строки 188-212)

**Соответствие `Functional and WorkLogik.md`:**
- II.6.9: «root может отменять подтверждённые операции, остальные роли — только неподтверждённые / свои черновики» — это про cancel, не про delete. Delete для cancelled — расширение логики: создатель может удалить свою отменённую операцию, chief — любую.

---

### Problem 4: Unit тесты `test_operations_service_inventory_subject_write_path.py` — `AttributeError: temporary_draft_payload`

**Симптом:** `SimpleNamespace has no attribute temporary_draft_payload`

**Причина:** `_materialize_deferred_temporary_lines` (строка 634) итерирует `operation.lines` и обращается к `line.temporary_draft_payload`. Но хелпер `_operation_line()` в тестах создаёт `SimpleNamespace` без этого атрибута. Python выбрасывает `AttributeError` при попытке доступа к несуществующему атрибуту `SimpleNamespace` (в отличие от чтения `None`).

**Исправление:** Добавить `temporary_draft_payload=None` в `_operation_line()`:
```python
def _operation_line(*, line_id, item_id, inventory_subject_id, qty):
    return SimpleNamespace(
        id=line_id,
        item_id=item_id,
        inventory_subject_id=inventory_subject_id,
        qty=qty,
        accepted_qty=0,
        lost_qty=0,
        temporary_draft_payload=None,  # ← добавить
    )
```

Также добавить отдельный positive test для строки с реальным temporary draft payload, чтобы покрыть ветку materialization.

**Файлы:**
- Изменить: `SyncServer/tests/test_operations_service_inventory_subject_write_path.py` (строка 13-21)
- Опционально: добавить новый тест в этот же файл

---

### Problem 5: Старые тесты TemporaryItem vs новый Review Item flow

**Архитектурное решение (принято клиентом 01.06.2026):**

Концепция временных ТМЦ признана ненужной. Целевой flow:
- При создании операции inline-ТМЦ материализуются как **постоянные `Item` с `requires_review=true`** (уже реализовано в `_materialize_deferred_temporary_lines`)
- Старая таблица `temporary_items` и legacy-эндпоинты `/api/v1/temporary-items/*` **сохраняются** для обратной совместимости с существующими данными
- Новые операции **НЕ** создают записи в `temporary_items`

**Суть конфликта:**

В коде `_materialize_deferred_temporary_lines` (строка 617-692):
```python
# New flow creates a permanent catalog item directly
# with requires_review=true
review_item = Item(
    ...
    is_active=True,
    requires_review=True,
    review_status="needs_review",
    review_created_by_user_id=user_id,
    source_system="operation_inline",
    source_ref=client_key,
)
review_item = await uow.catalog.create_item(review_item)
review_subject = await uow.inventory_subjects.get_or_create_for_item(item_id=review_item.id)
```
**Целевой flow:** permanent `Item` с `requires_review=True`, **НЕ** создаёт `TemporaryItem`.

Тесты `test_temporary_items_phase1.py` всё ещё ожидают создание `TemporaryItem`:
- `test_submit_materializes_deferred_temporary_lines` (строка 217): ожидает `len(TemporaryItem) == 1` после submit → **падение**
- `test_cancel_submitted_operation_deletes_materialized_temporary_items` (строка 372): ожидает `TemporaryItem.status == "deleted"` → **падение**
- Тесты stage3a/stage3b: аналогичные ожидания

Тесты `test_temporary_items_delete.py`:
- Создают `TemporaryItem` напрямую через БД — тестируют **legacy-эндпоинты**, которые сохраняются для обратной совместимости
- Не зависят от `create_operation` → изолированы, продолжат работать после исправления путей и FK

**Что менять:**

1. **Код `_materialize_deferred_temporary_lines` — НЕ менять.** Он уже реализует целевой flow.
2. **Legacy-эндпоинты `/api/v1/temporary-items/*` — НЕ удалять.** Они нужны для обратной совместимости с существующими данными в таблице `temporary_items`.
3. **Переписать тесты phase1/stage3a/stage3b:**
   - Вместо `select(TemporaryItem)` → проверять `select(Item).where(Item.requires_review == True)`
   - Вместо `assert temporary_items[0].status == "deleted"` → проверять `item.review_status` созданного review-Item
   - Вместо `assert temporary_items[0].name == "..."` → проверять атрибуты созданного `Item`
   - Утверждения про `TemporaryItem` заменить на утверждения про `Item` с `requires_review=True`
   - Поле `temporary_draft_payload` в `OperationLine` очищается после materialization (строка 690) — это поведение сохраняется
4. **Обновить `Functional and WorkLogik.md` (раздел IV):**
   - Пометить концепцию временных ТМЦ как deprecated
   - Добавить описание нового Review Item flow
5. **Документировать решение** — короткий ADR в `docs/adr/`

**Файлы:**
- Не менять: `SyncServer/app/services/operations_service.py`
- Не удалять: `SyncServer/app/api/routes_temporary_items.py`, `SyncServer/app/models/temporary_item.py`
- Изменить: `SyncServer/tests/test_temporary_items_phase1.py`
- Изменить: `SyncServer/tests/test_temporary_items_stage3a.py`
- Изменить: `SyncServer/tests/test_temporary_items_stage3b.py`
- Изменить: `Functional and WorkLogik.md` (раздел IV)
- Создать: `docs/adr/0012-deprecate-temporary-items-review-flow.md`

---

### Problem 6: FK violation — `resolved_item_id=999`

**Симптом:** `ForeignKeyViolationError: resolved_item_id=999 отсутствует в items`

**Файл:** `test_temporary_items_delete.py:277`
```python
db_item.resolved_item_id = 999  # несуществующий FK
```

**Исправление:** Создать реальный `Item` и использовать его `id`:
```python
resolved_item = Item(sku="RESOLVED-...", name="Resolved", ..., is_active=True)
session.add(resolved_item)
await session.flush()
db_item.resolved_item_id = resolved_item.id
```

**Файлы:**
- Изменить: `SyncServer/tests/test_temporary_items_delete.py` (строки 264-280)

---

### Problem 7 (дополнительно): Transport TZ — deferred пункты

Из `TZ-DJANGO_SYNCSERVER_TRANSPORT_HARDENING.md` остались незакрытыми:
- Пункт 3 (BFF screen-level aggregation) — deferred
- Пункт 7 (Unix domain socket) — deferred

Для текущих падений это не blocker, но для будущей стабильности рекомендуется отдельно запланировать:
- BFF endpoints для operation detail / review item detail
- Smoke through Django для operation journal, temporary/review list
- Проверку маппинга `403/404/409/422/429` от SyncServer → Django

**В данном TZ не исправляется.** Требуется отдельное планирование.

---

## 3. Параллельная декомпозиция

```
Stage 0: Архитектурное решение — ПРИНЯТО (01.06.2026)
  ✅ Целевой flow: постоянные ТМЦ с requires_review
  ✅ Legacy TemporaryItem таблицы и эндпоинты сохраняются для обратной совместимости

Stage 1 (4 исполнителя, параллельно):
  ├── 1-A: Rate limiter reset fixture  [conftest.py]
  ├── 1-B: Исправить пути в delete-тестах  [test_temporary_items_delete.py]
  ├── 1-C: Моки OperationLine + temporary_draft_payload  [test_operations_service_...py]
  └── 1-D: FK fixture fix  [test_temporary_items_delete.py]

Stage 2: Operation Delete Policy (1 исполнитель, параллельно со Stage 1)
  └── Policy + routes + permissions tests
       [operations_policy.py, routes_operations.py, test_operations_permissions.py]

Stage 3: TemporaryItems tests rewrite (1 исполнитель, независим от Stage 1-2)
  └── Переписать phase1/stage3a/stage3b тесты на Review Item flow
       [test_temporary_items_phase1.py, test_temporary_items_stage3a.py,
        test_temporary_items_stage3b.py]
  └── Обновить Functional and WorkLogik.md (раздел IV)
  └── Создать ADR-0012

Stage 4: Verification (после Stage 1-3)
  └── python -m pytest, stand smoke
```

**Правило:** Stage 1-A, 1-B, 1-C, 1-D, Stage 2, и Stage 3 не конфликтуют по файлам — все могут выполняться параллельно.

---

## 4. Тестовая стратегия

### Уровень 1: Static checks
```bash
cd SyncServer && python -m pytest --collect-only
```

### Уровень 2: Unit/component tests
- `test_operations_permissions.py` — обновлённые тесты delete permission
- `test_operations_service_delete.py` — без изменений (уже тестирует корректно)
- `test_operations_service_inventory_subject_write_path.py` — обновлённые моки

### Уровень 4: Integration tests (DB-backed)
- `test_operations_delete_api.py` — без изменений (уже ожидает корректное поведение)
- `test_temporary_items_delete.py` — исправленные пути + FK
- `test_temporary_items_phase1.py` — переписанные на Review Item flow
- `test_temporary_items_stage3a.py` — переписанные
- `test_temporary_items_stage3b.py` — переписанные
- `test_http_sync.py` — должен проходить после rate limiter fix

### Уровень 5: Stand smoke tests
```bash
# Проверить, что все эндпоинты работают
curl -s --max-time 5 http://localhost:8000/api/v1/health
# CRUD operation + delete cancelled через API
```

### Уровень 8: Regression
```bash
cd SyncServer && python -m pytest
```
Целевой результат: 0 падений (или только known issues с xfail).

---

## 5. Acceptance criteria

- [x] `python -m pytest --collect-only` — импорты не сломаны
- [x] `.venv` rate limiter НЕ сохраняет состояние между тестами (подтверждено fixture reset)
- [x] Все пути в `test_temporary_items_delete.py` используют `/api/v1/`
- [x] `test_operations_service_inventory_subject_write_path.py` проходит без AttributeError
- [x] `test_delete_temporary_item_already_resolved` не падает с ForeignKeyViolationError
- [x] Удаление cancelled операции: storekeeper может удалить свою, chief — любую, root — любую
- [x] Удаление draft/submitted операции возвращает 409, а не 403
- [x] Unit-тесты permissions НЕ конфликтуют с API-тестами
- [x] Тесты phase1/stage3a/stage3b переписаны: вместо `TemporaryItem` проверяют `Item` с `requires_review=True`
- [x] Legacy-эндпоинты `/api/v1/temporary-items/*` и таблица `temporary_items` сохранены
- [x] `Functional and WorkLogik.md` (раздел IV) обновлён: временные ТМЦ помечены как deprecated, описан Review Item flow
- [x] ADR-0012 создан и документирует решение
- [x] Полный `python -m pytest` даёт 0 падений (или только xfail)

---

## 6. Риски

| Риск | Вероятность | Митигация |
|------|-------------|-----------|
| ~~Решение по TemporaryItem vs Review Item затянется~~ | ~~Средняя~~ | ✅ Решение принято 01.06.2026 — новый Review Item flow |
| Stage 3 (переписывание тестов) — большой объём | Высокая | Разрешить xfail для не-critical тестов, закрывать их в отдельном PR |
| Изменение порядка проверок в delete_operation сломает другие тесты | Низкая | Проверить все тесты на операции: cancel, submit, delete |
| Конфликт имён `created_by_user_id` в Item (review vs audit) | Низкая | Уже учтено в TZ-CATALOG: разделены `item.created_by_user_id` (аудит) и `item.review_created_by_user_id` (review) |
| Удаление legacy `/api/v1/temporary-items/*` эндпоинтов | Низкая | **Не делаем.** Эндпоинты сохраняются для обратной совместимости |

---

## 7. Порядок выполнения

```
Stage 0 → ✅ Решение принято (01.06.2026): новый Review Item flow + обратная совместимость
    ↓
Stage 1-A, 1-B, 1-C, 1-D, Stage 2, Stage 3 (полный параллелизм — независимые файлы)
    ↓
Stage 4 → Verification → Acceptance
```
