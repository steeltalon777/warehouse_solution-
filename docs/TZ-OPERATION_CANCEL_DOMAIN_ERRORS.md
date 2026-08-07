# TZ-OPERATION_CANCEL_DOMAIN_ERRORS

**Статус:** готово к реализации
**Дата:** 2026-08-05
**Автор:** architect (по запросу пользователя, Косяк 2)
**Связанные документы:**
* ADR-0027 — `docs/adr/0027-operation-cancel-domain-errors.md`
* ADR-0025 — `docs/adr/0025-operation-submit-domain-errors.md` (базовый envelope)
* Серверный TZ submit-envelope — `docs/TZ-SYNCSERVER_OPERATION_SUBMIT_DOMAIN_ERRORS.md` (служит образцом)
* Парный Angular-TZ submit — `docs/TZ-FRONTEND_OPERATION_SUBMIT_ERROR_SURFACE.md`

---

## 0. Execution Checklist

- [x] 0. Контекст verified (re-read ADR-0025 + Functional §6.8-6.9)
- [x] 1. Доменные исключения cancel-flow + Pydantic-схемы
- [x] 2. `_check_cancel_balance_sufficiency` (двухфазный pre-check)
- [x] 3. Встраивание pre-check в `cancel_operation`
- [x] 4. Workflow-политики: `require_exists`, `require_not_cancelled_for_cancel`
- [x] 5. Authz-политики: `require_operate_site`, `require_operation_cancel_permission`, `require_move_access`
- [x] 6. Exception handler: убедиться, что `OperationSubmitError` ловит cancel-flow
- [x] 7. Django BFF: `OperationCancelView` → `api_error_response`, snapshot-инвариант
- [x] 8. Транспорт: `client.py::_raise_for_response` dict-detail fallback
- [x] 9. Frontend: `cancelOperation`/`restoreOperation` + `SubmitErrorService` + toasts
- [x] 10. OpenAPI-схема envelope
- [x] 11. Static checks (SyncServer: pytest --collect-only, mypy; Django: manage.py check; Angular: tsc --noEmit)
- [x] 12. Unit-тесты: `OperationSubmitError` подклассы cancel-flow
- [x] 13. Unit-тесты: `OperationsService._check_cancel_balance_sufficiency`
- [x] 14. Unit-тесты: `OperationsService.cancel_operation` happy-path (RECEIVE, MOVE, ISSUE, ISSUE_RETURN, WRITE_OFF+issue_object, ADJUSTMENT)
- [x] 15. Unit-тесты: `OperationsService.cancel_operation` envelope при rollback-дефиците (все типы)
- [x] 16. Integration-тесты: `tests/test_cancel_rollback_envelope.py` (DB-backed)
- [x] 17. Integration-тесты: `tests/test_operations_service_cancel.py` — расширить до envelope-проверок
- [x] 18. Concurrency-тесты: cancel vs submit на одну операцию
- [x] 19. Django: helper-тесты `_handle_sync_error` cancel-flow
- [x] 20. Django: BFF-тесты `OperationCancelView` с envelope и string-detail
- [x] 21. Django: snapshot-тест `OtherSubmitEndpointsSnapshotTests` обновить
- [x] 22. Django: `apps/sync_client/tests.py` — `_raise_for_response` с dict-detail
- [x] 23. Angular unit: `operations.service.spec.ts` — `cancelOperation`/`normalizeError`
- [x] 24. Angular unit: `submit-error.service.spec.ts` — cancel-flow
- [x] 25. Angular unit: `parser.spec.ts` — `parseSubmitErrorResponse` для cancel envelope
- [x] 26. Angular unit: `submit-error-toasts.spec.ts` — operation-level сообщения cancel
- [x] 27. Angular e2e: новый `e2e/operations/operations-cancel.spec.ts`
- [x] 28. Стend smoke: `make up` + `curl POST /api/v1/operations/{id}/cancel` с известным дефицитом → envelope
- [x] 29. User scenario: «root отменяет MOVE, у которого destination пуст, видит человеческий текст с item/site/qty»
- [x] 30. Regression: submit-flow envelope не сломан (snapshot + happy-path submit)
- [x] 31. Документация: ADR-0025 §8 обновить, README/INDEX ссылка
- [ ] 32. Final acceptance (QA verifier)

## Check Rules

* Архитектор создаёт чек-лист и критерии приёмки.
* Executor проверяет только после реализации и собственного прогона всех применимых уровней тестов.
* Если уровень недоступен — оставить пустым с пометкой «стенд недоступен».
* Перед любым real-stand прогоном — Stand Availability Protocol из `AGENTS.md`.

---

## 1. Подтверждённые факты репозитория

Зафиксированы при разведке 2026-08-05. См. `docs/adr/0027-operation-cancel-domain-errors.md` §«Контекст» для полной цепочки.

### 1.1. Ключ остатка

Без изменений относительно submit-flow (ADR-0025 §1.1, TZ-SYNCSERVER_OPERATION_SUBMIT_DOMAIN_ERRORS §1.1):

* Таблица `balances` (`SyncServer/app/models/balance.py:12-33`), составной PK `(site_id, inventory_subject_id)`.
* `unit_id` в таблице `balances` отсутствует; ключ агрегации — строго `(site_id, inventory_subject_id)`.
* `unit_id` возвращается клиенту только как отображаемые данные в `errors[].unit`.

### 1.2. Типы идентификаторов

Без изменений (см. ADR-0025 §1.2 / TZ-SYNCSERVER_OPERATION_SUBMIT_DOMAIN_ERRORS §1.2).

### 1.3. Конкурентная защита

* Cancel-flow уже работает в транзакции `with uow:` (`routes_operations.py:364`).
* `_check_cancel_balance_sufficiency` (новый, §2) берёт блокировки через `with_for_update()`.
* Optimistic `expected_version` не применим к cancel (cancel не редактирует draft).

### 1.4. Где формируются текущие cancel-ошибки (НЕ envelope)

| Место | Текущий формат | Что нужно |
| --- | --- | --- |
| `operations_service.py:99-114` `_ensure_sufficient_balance` | `HTTPException(409, "insufficient stock for ...: inventory_subject=..., site=..., required=...")` | Доменное исключение `InsufficientStockError` через pre-check |
| `operations_service.py:482-487` `_apply_balance_delta` | `HTTPException(409, f"insufficient stock for {error_context}: inventory_subject=..., site=..., required=...")` | Pre-check ловит **до** мутации. `f`-строка остаётся как safety net (ADR-0025 §5.7), но не должна срабатывать в cancel-flow |
| `operations_service.py:752-770` `_upsert_issued` (`ValueError` из репозитория) | `HTTPException(409, f"issued asset quantity conflict for {error_context}")` | Аналогично pre-check `dict_issued` ловит **до** `_upsert_issued` |
| `operations_service.py:2613-2615` (MOVE без source/destination) | `HTTPException(422, "MOVE operation requires source_site_id and destination_site_id")` | `OperationInWrongStateError` (cancel-flow не имеет source/destination — это invariant violation) |
| `operations_service.py:2693-2694` (ISSUE без `issue_object_id`) | `HTTPException(422, "ISSUE requires issue_object_id")` | `OperationInWrongStateError` |
| `operations_service.py:2713-2714` (ISSUE_RETURN без `issue_object_id`) | `HTTPException(422, "ISSUE_RETURN requires issue_object_id")` | `OperationInWrongStateError` |
| `routes_operations.py:362` (`cancel != True`) | `HTTPException(422, "cancel must be true")` | Оставить `HTTPException` (это не доменная ошибка, валидация payload). BFF пробрасывает через `ValidationError` |
| `routes_operations.py:367` (operation not found) | `HTTPException(404, "operation not found")` | `OperationNotFoundError` (через workflow-policy) |
| `routes_operations.py:369-372` (authz: `require_operate_site`, `require_operation_cancel_permission`, `require_move_access`) | `HTTPException(403, "operate permission required" / "user has no cancel permission" / "user has no move access")` | `RoleNotPermittedError` |
| `operations_workflow_policy.py:10-12` `require_exists` | `HTTPException(404, "operation not found")` | `OperationNotFoundError` |
| `operations_workflow_policy.py:61-67` `require_not_cancelled_for_cancel` | `HTTPException(409, "operation is already cancelled")` | `OperationInWrongStateError(current_state="cancelled", allowed_states=["draft", "submitted"])` |

### 1.5. Где НЕ надо менять (cancel-flow out of scope)

* `OperationsPolicy.require_temporary_item_create`, `require_temporary_item_moderation` — для временных ТМЦ, не cancel.
* `OperationsPolicy.require_root_for_restore`, `require_cancelled_for_delete` — другие workflow-эндпоинты, не cancel.
* `OperationsWorkflowPolicy.require_submitted_for_acceptance`, `require_acceptance_required` — acceptance-flow, не cancel.
* `OperationsService.submit_operation` (строки 1650-1807) — submit-flow, его envelope уже работает.
* `corrections_service.py:912` — корректировки, отдельный envelope.
* `routes_documents.py`, `routes_admin_*`, `routes_temporary_items.py` — не cancel.

### 1.6. Django BFF

* `Warehouse_web/apps/sync_client/client.py:124-163` — `_raise_for_response` сохраняет `payload` в `exc.payload`, но в `message` кладёт `str(sanitized.get("detail"))` (строка 133) — для dict-`detail` даёт Python-repr.
* `Warehouse_web/apps/bff_api/operations_views.py:393-417` — `OperationCancelView.post` зовёт `_handle_sync_error(exc)`.
* `Warehouse_web/apps/sync_client/test_api_error_response.py:96-105` — `EXPECTED_HELPERS` фиксирует `OperationCancelView` → `_handle_sync_error`. Изменение = breaking of invariant.
* `Warehouse_web/apps/sync_client/api_error_response.py:34` — `api_error_response` уже реализован, используется только `OperationSubmitView`.

### 1.7. Frontend

* `Warehouse_frontend/src/app/core/services/operations.service.ts:474-488, :490-505` — `cancelOperation`/`restoreOperation` в `catch` зовут `normalizeError`, которая читает только `err.message` и `err.fields`.
* `Warehouse_frontend/src/app/features/operations/submit-error/parser.ts:97` `normalizeError(raw, envelopeDetail)` — уже парсит envelope. Используется только в `OperationCreateModalComponent` (`operation-create-modal.component.ts:1083-1092`).
* `Warehouse_frontend/src/app/features/operations/components/operation-create-modal/submit-error-toasts.ts:10-15` `OPERATION_LEVEL_TOAST_MESSAGES` — карта кодов в человеческие тексты для operation-level ошибок.
* `Warehouse_frontend/src/app/features/operations/pages/operations-page/operations-page.component.ts:582-590, :1028-1041, :1048-1064` — `onRowCancel`, `onDraftOperationCancel`, `onDraftRestore` молча проглатывают ошибку.

---

## 2. Цели и не-цели

### In scope

1. Доменные исключения cancel-flow с тем же envelope-форматом, что submit.
2. Новый helper `OperationsService._check_cancel_balance_sufficiency` (двухфазный, mirror submit).
3. Замена 11+ английских `HTTPException` на доменные `OperationSubmitError` подклассы (см. §1.4).
4. Workflow-политики: `require_exists` → `OperationNotFoundError`, `require_not_cancelled_for_cancel` → `OperationInWrongStateError`.
5. Authz-политики: `require_operate_site` / `require_operation_cancel_permission` / `require_move_access` → `RoleNotPermittedError`.
6. Django BFF: `OperationCancelView` → `api_error_response`; `client.py::_raise_for_response` dict-detail fallback.
7. Angular: `cancelOperation`/`restoreOperation` пробрасывают `err.raw` в `SubmitErrorService`; operation-level toasts для cancel.
8. Snapshot-инвариант `OtherSubmitEndpointsSnapshotTests` синхронно обновляется.
9. ADR-0025 §8 синхронно расширяется.
10. Тесты: unit, integration (DB-backed), concurrency, BFF-helper, frontend unit, e2e.

### Out of scope

1. Другие ошибки API (auth, validation, 5xx).
2. Корректировки (`corrections_service.py:912`).
3. Acceptance-flow.
4. Restore-flow envelope (он уже работает через базовый handler, но без UX-доработки).
5. Delete-flow.
6. Оффлайн-клиенты.
7. Клиентский precheck остатков.
8. Bulk-validate endpoint.
9. Изменение `_apply_balance_delta` (ADR-0025 §5.7).
10. Глобальная миграция BFF на `api_error_response` для всех эндпоинтов.

---

## 3. Доменные исключения и схемы

### 3.1. Файлы

* `SyncServer/app/services/operation_submit_errors.py` — **изменить** базовый класс `OperationSubmitError` (добавить `problem_class = "operation-cancel-rejected"` через factory method `_set_problem_class("cancel")`, чтобы не дублировать подклассы). Альтернатива: ввести `OperationCancelError(OperationSubmitError)` с `problem_class = "operation-cancel-rejected"` (отменённое положение ADR-0027 §0).
* `SyncServer/app/schemas/operation_submit_error.py` — **без изменений**, тот же `ProblemEnvelope` используется и для cancel.

**Решение по структуре подклассов:** переиспользуем существующие подклассы, но **каждый** принимает `problem_class: str = "operation-cancel-rejected"` через kwarg. Это позволяет handler'у выдать правильный `type` URN без дублирования классов. `to_envelope()` уже использует `self.problem_class`.

### 3.2. Доменные исключения (без новых классов)

Подклассы остаются из ADR-0025, но в cancel-flow они поднимаются с другим `problem_class`:

| Подкласс | `code` (errors[]) | `code` (envelope) | `problem_class` (cancel-flow) | `http_status` |
| --- | --- | --- | --- | ---: |
| `InsufficientStockError` | `insufficient_stock` | `operation_cancel_rejected` | `operation-cancel-rejected` | 409 |
| `InsufficientIssuedBalanceError` | `insufficient_issued_balance` | `operation_cancel_rejected` | `operation-cancel-rejected` | 409 |
| `OperationInWrongStateError` | `operation_in_wrong_state` | `operation_cancel_rejected` | `operation-cancel-rejected` | 409 |
| `StaleVersionError` | `stale_version` | `operation_cancel_rejected` | `operation-cancel-rejected` | 409 |
| `RoleNotPermittedError` | `role_not_permitted` | `role_not_permitted` | `operation-cancel-rejected` | 403 |
| `OperationNotFoundError` | `operation_not_found` | `operation_not_found` | `operation-not-found` | 404 |

Подпись конструктора каждого подкласса расширяется:

```python
class InsufficientStockError(OperationSubmitError):
    def __init__(
        self,
        deficits: list[StockDeficit],
        *,
        problem_class: str = "operation-cancel-rejected",  # НОВОЕ: по умолчанию cancel-flow
    ) -> None:
        super().__init__()
        self.problem_class = problem_class
        self.deficits = deficits
```

То же для остальных 5 подклассов. Submit-flow TZ не меняется — там `problem_class` остаётся `"operation-submit-rejected"`, передаётся явно в `submit_operation` через `InsufficientStockError(deficits, problem_class="operation-submit-rejected")`. Это **расширение** сигнатуры, обратно совместимое с ADR-0025 (kwarg с дефолтом).

### 3.3. Pydantic-схемы envelope

Без изменений. `ProblemEnvelope` (`schemas/operation_submit_error.py:98-106`) уже покрывает оба flow:

* `type` — URN вида `urn:warehouse:problem:operation-cancel-rejected` для cancel-flow, `urn:warehouse:problem:operation-submit-rejected` для submit-flow.
* `code` верхнего уровня — `operation_cancel_rejected` (cancel-flow) или `operation_submit_rejected` (submit-flow).
* `errors[]` — те же 6 типов, что и в submit-flow.

OpenAPI-схема (`SyncServer/app/main.py` или `app/api/openapi.py`) — обновить `tags` и `description` для `cancel_operation`: «Возвращает envelope доменных ошибок с теми же кодами, что и submit».

### 3.4. Детерминированный порядок `errors[]`

Сортируется по `line_number` первой строки группы ascending (без изменений относительно ADR-0025 §1).

---

## 4. Exception handler

### 4.1. Регистрация

Без изменений. `operation_submit_error_handler` (`exceptions_handlers.py:9-17`) уже зарегистрирован для базового класса `OperationSubmitError` в `main.py:148`. Cancel-flow исключения наследуются от `OperationSubmitError` → handler их ловит.

**Однако** — handler зарегистрирован с именем `OperationSubmitError`. Если ввести `OperationCancelError(OperationSubmitError)` — handler **не** поймает его автоматически (FastAPI ищет точный класс). **Решение:** отменяем §0 ADR-0027 «ввести `OperationCancelError`» — переиспользуем `OperationSubmitError` через kwarg `problem_class`.

### 4.2. Маппинг

Без изменений. `exc.to_envelope()` уже использует `self.problem_class` для построения `type` URN и `code` верхнего уровня (через `_code()` — см. `operation_submit_errors.py:74-77`).

Дополнительно: `_code()` метод нужно сделать **overridable** через `problem_class`:

```python
def _code(self) -> str:
    if self.problem_class == "operation-not-found":
        return "operation_not_found"
    if self.problem_class == "operation-cancel-rejected":
        return "operation_cancel_rejected"
    return "operation_submit_rejected"
```

---

## 5. Агрегированная проверка остатков в cancel-flow

### 5.1. Алгоритм — двухфазный (mirror submit)

Файл: `SyncServer/app/services/operations_service.py`, новый helper после `_check_submit_balance_sufficiency` (строки 319-430).

```python
@staticmethod
async def _check_cancel_balance_sufficiency(
    uow: UnitOfWork, *, operation: Operation
) -> None:
    """Two-phase aggregated balance check for cancel-flow rollback.

    Mirror of _check_submit_balance_sufficiency with inverse deltas:
    - RECEIVE rollback decreases warehouse at operation.site_id
    - EXPENSE/WRITE_OFF rollback increases warehouse at operation.site_id
    - ADJUSTMENT rollback inverts the original delta
    - MOVE rollback increases warehouse at source_site_id, decreases at destination_site_id
    - ISSUE/ISSUE_RETURN rollback: warehouse at operation.site_id AND issued at issue_object_id
    - WRITE_OFF with issue_object_id rollback: issued only

    Raises InsufficientStockError / InsufficientIssuedBalanceError with
    StockDeficit / IssuedStockDeficit (item.name, site.name, operation_line_ids[]).
    """
```

**Фаза 1. Сбор инверсивных эффектов.**

Один проход по `operation.lines` (упорядоченным по `line.line_number` ascending). Заполняются два словаря:

```python
dict_warehouse: dict[tuple[int, int], list[tuple[OperationLine, Decimal]]] = {}
dict_issued: dict[tuple[int, int], list[tuple[OperationLine, Decimal]]] = {}
```

См. ADR-0027 §3 таблицу маппинга тип → эффект → ключ.

**Фаза 2. Блокировка и проверка.**

1. `sorted_warehouse_keys = sorted(dict_warehouse.keys())` — глобальная сортировка tuple-based, deadlock-безопасно.
2. Для каждого ключа — `await uow.balances.get_for_update(site_id, inventory_subject_id)` → читаем `available_qty` внутри блокировки.
3. `sum_required = sum(qty for _, qty in dict_warehouse[k])`.
4. Если `sum_required > available_qty` — формируем `StockDeficit(stock_site_id, stock_site_name, item_id, item_name, unit_id, unit_name, unit_symbol, required_qty=sum_required, available_qty, operation_line_ids=[line.id for line, _ in dict_warehouse[k] отсортированных по line_number])`.
5. После прохода — `deficits_warehouse` сортируется по `line_number` первой строки группы ascending.
6. Аналогично для `dict_issued` через `uow.asset_registers.get_issued_balance(issue_object_id, inventory_subject_id)`.

**Поднятие исключений:**

- `deficits_warehouse` непуст → `InsufficientStockError(deficits=deficits_warehouse, problem_class="operation-cancel-rejected")`.
- `deficits_issued` непуст → `InsufficientIssuedBalanceError(deficits=deficits_issued, problem_class="operation-cancel-rejected")`.
- Оба непусты → поднимается warehouse (приоритет), issued логируется.

### 5.2. Lookup имён

```python
item = await uow.catalog.get_item_by_id(line.item_id)
if item is None:
    item_name = f"<id {line.item_id}>"
    unit_id = unit_name = unit_symbol = None
else:
    item_name = item.name
    unit = await uow.catalog.get_unit_by_id(item.unit_id)
    if unit is None:
        unit_id = unit_name = unit_symbol = None
    else:
        unit_id, unit_name, unit_symbol = unit.id, unit.name, unit.symbol

site = await uow.sites.get_by_id(site_id)  # новый, реализуется в uow.sites
site_name = site.name if site else f"<id {site_id}>"

issue_object = await uow.issue_objects.get_by_id(issue_object_id)
issue_object_name = issue_object.name if issue_object else f"<id {issue_object_id}>"
```

**Дополнительно:** `uow.sites.get_by_id` — проверить наличие, при отсутствии — реализовать в `SyncServer/app/repos/sites_repo.py`.

### 5.3. Пример: MOVE с пустым destination

Операция MOVE: `(site_id=1) → (site_id=2)`, `acceptance_required=False`, `quantity=2`, остаток `(2, 100) = 0`.

* **Фаза 1.** `dict_warehouse = {(1, 100): [(line, 2)], (2, 100): [(line, 2)]}` — source и destination оба участвуют (MOVE rollback = возврат на source + снятие с destination).
* **Фаза 2.** `sorted_warehouse_keys = [(1, 100), (2, 100)]`. Блокируем оба.
  - `(1, 100)`: `available_qty = 5`, `sum_required = 2`, `2 <= 5` — ОК.
  - `(2, 100)`: `available_qty = 0`, `sum_required = 2`, `2 > 0` — дефицит.
* `StockDeficit(stock_site_id=2, stock_site_name="...", item_id=..., item_name="...", required_qty=Decimal("2"), available_qty=Decimal("0"), operation_line_ids=[line.id])`.
* `InsufficientStockError(deficits=[deficit], problem_class="operation-cancel-rejected")`.
* Handler строит envelope: `detail = "Недостаточно товара: Кабель ВВГ — запрошено 2, на складе 0. Всего проблемных групп: 1."`.

---

## 6. Изменения в `cancel_operation`

Файл: `SyncServer/app/services/operations_service.py`, строки 2511-2775.

### 6.1. Pre-check вставка

```python
async def cancel_operation(uow, operation_id, user_id, reason=None):
    operation = await uow.operations.get_operation_by_id(operation_id)
    OperationsWorkflowPolicy.require_exists(operation)            # → OperationNotFoundError
    OperationsWorkflowPolicy.require_not_cancelled_for_cancel(operation)  # → OperationInWrongStateError

    balance_effects_capture: list[dict] = []

    if operation.status == "submitted":
        # PHASE 0: aggregated read-only pre-check. Raises OperationSubmitError -> envelope.
        await OperationsService._check_cancel_balance_sufficiency(uow, operation=operation)

        for line in operation.lines:
            # ... existing branches: _apply_balance_delta, _upsert_pending,
            # _upsert_lost, _upsert_issued ...
            # NO more HTTPException for insufficient balance. Pre-check already
            # raised the envelope.
            pass

    # ... existing rest: uow.operations.cancel_operation, _delete_temporary_items_of_operation,
    # record_audit_event, _write_captured_effects ...
```

### 6.2. Authz-политики (вынесенные из routes)

Файл: `SyncServer/app/api/routes_operations.py:369-372`:

```python
OperationsPolicy.require_operate_site(identity, operation.site_id)         # → RoleNotPermittedError
OperationsPolicy.require_operation_cancel_permission(identity, operation) # → RoleNotPermittedError
if operation.operation_type == "MOVE":
    OperationsPolicy.require_move_access(identity, operation.source_site_id, operation.destination_site_id)  # → RoleNotPermittedError
```

Заменяем `HTTPException` на `RoleNotPermittedError` в `operations_policy.py:26-32, 75-116, 142-151, 159-168`. **Минимальный** объём: только эти три метода, остальные политики не трогаем.

### 6.3. Workflow-политики

Файл: `SyncServer/app/services/operations_workflow_policy.py`:

* `require_exists` (10-12) → `raise OperationNotFoundError(operation_id=operation_id)`.
* `require_not_cancelled_for_cancel` (61-67) → `raise OperationInWrongStateError(current_state="cancelled", allowed_states=["draft", "submitted"])`.

### 6.4. Что НЕ меняется

* `_apply_balance_delta` (строки 458-487) — ADR-0025 §5.7. f-строка остаётся как safety net для race condition.
* `_ensure_sufficient_balance` (строки 99-114) — остаётся в текущей форме; в cancel-flow **не вызывается** напрямую (только через `_apply_balance_delta`, который теперь не должен падать).
* `_upsert_issued` (строки 752-770) — `ValueError` → `HTTPException(f"issued asset quantity conflict for ...")` остаётся как safety net.

---

## 7. Django BFF

### 7.1. `OperationCancelView` → `api_error_response`

Файл: `Warehouse_web/apps/bff_api/operations_views.py`, строки 393-417.

```python
class OperationCancelView(View):
    def post(self, request, operation_id):
        if not _require_storekeeper(request):
            return _forbidden(...)
        try:
            payload = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": {...}}, status=400)
        try:
            result = api.cancel_operation(operation_id=operation_id, payload=payload)
        except SyncBackendUnavailable as exc:
            return _operation_outcome_unknown(exc)
        except SyncServerAPIError as exc:
            return api_error_response(exc)   # ← было _handle_sync_error(exc)
        return JsonResponse({"ok": True, "operation": result}, status=200)
```

### 7.2. Snapshot-инвариант `OtherSubmitEndpointsSnapshotTests`

Файл: `Warehouse_web/apps/sync_client/test_api_error_response.py:96-105`.

```python
EXPECTED_HELPERS = {
    ...
    "OperationCancelView": "api_error_response",  # ← было "_handle_sync_error"
    ...
}
```

### 7.3. Транспорт: `client.py::_raise_for_response` dict-detail fallback

Файл: `Warehouse_web/apps/sync_client/client.py:124-163`, строки 131-141:

```python
detail = sanitized.get("detail")
if isinstance(detail, dict):
    # SyncServer envelope case: detail is structured object.
    message = detail.get("message") or detail.get("detail") or str(exc)
elif isinstance(detail, str):
    message = detail or str(exc)
else:
    message = str(exc) if exc else "SyncServer error"
```

Это устраняет Python-repr для dict-`detail`. **Не** меняет `exc.payload` (он сохраняется полностью).

### 7.4. ADR-0025 §8 обновление

Файл: `docs/adr/0025-operation-submit-domain-errors.md`, §8 «Django BFF» — добавить:

> «Helper `api_error_response(exc)` применяется к submit-flow и cancel-flow BFF endpoints (`OperationSubmitView`, `OperationCancelView`). Все остальные BFF endpoints остаются на `_handle_sync_error` и не затрагиваются этой итерацией.»

---

## 8. Frontend

### 8.1. `cancelOperation`/`restoreOperation` — пробрасывание envelope

Файл: `Warehouse_frontend/src/app/core/services/operations.service.ts:474-488, :490-505`.

```typescript
async cancelOperation(id: string): Promise<void> {
  try {
    await firstValueFrom(this.bff.postData<unknown>(`/bff/api/v1/operations/${id}/cancel`, { cancel: true }));
    this.error.set(null);
    this.submitErrorService.clearCancel();
  } catch (err: any) {
    this.normalizeError(err);
    this.submitErrorService.setCancelFromHttpError(err?.raw ?? err);
  }
}
```

Аналогично `restoreOperation`.

### 8.2. `SubmitErrorService` — новый `cancelErrorPayload`

Файл: `Warehouse_frontend/src/app/features/operations/submit-error/submit-error.service.ts`.

```typescript
export class SubmitErrorService {
  readonly submitErrorPayload = signal<SubmitErrorViewModel | null>(null);
  readonly cancelErrorPayload = signal<SubmitErrorViewModel | null>(null);  // НОВОЕ

  setCancelFromHttpError(raw: unknown): void {
    const viewModel = parseSubmitErrorResponse(raw);
    if (viewModel) {
      this.cancelErrorPayload.set(viewModel);
    } else {
      this.cancelErrorPayload.set(null);
    }
  }

  clearCancel(): void {
    this.cancelErrorPayload.set(null);
  }
}
```

### 8.3. Operations page — отображение cancel-ошибки

Файл: `Warehouse_frontend/src/app/features/operations/pages/operations-page/operations-page.component.ts`.

* `onRowCancel` (582-590), `onDraftOperationCancel` (1028-1041), `onDraftRestore` (1048-1064) — не глотать ошибку: показать toast через `submitErrorService` или баннер, **не** блокировать таблицу.
* Добавить шаблон отображения `submitErrorService.cancelErrorPayload()` аналогично существующему для `submitErrorPayload()` в `OperationCreateModalComponent` (строки 1083-1092).

### 8.4. Toasts для cancel

Файл: `Warehouse_frontend/src/app/features/operations/components/operation-create-modal/submit-error-toasts.ts:10-15`.

```typescript
export const OPERATION_LEVEL_TOAST_MESSAGES: Record<OperationLevelErrorCode, string> = {
  stale_version: 'Операция была изменена в другой вкладке. Обновите список и повторите.',
  operation_in_wrong_state: 'Операция уже не в том статусе — обновите страницу.',
  role_not_permitted: 'Недостаточно прав для отмены операции.',
  operation_not_found: 'Операция уже удалена — обновите список.',
  operation_submit_rejected: 'Не удалось провести операцию.',         // существующее
  operation_cancel_rejected: 'Не удалось отменить операцию.',         // НОВОЕ
};
```

### 8.5. Расширение `KnownErrorCode` (если нужно)

Файл: `Warehouse_frontend/src/app/features/operations/submit-error/envelope.ts:49-55`. Проверить, покрывает ли union `OperationLevelErrorCode` значение `operation_cancel_rejected`. Если нет — добавить.

---

## 9. OpenAPI-схема

Файл: `SyncServer/app/main.py` (или эквивалентный `app/api/openapi.py`).

* `OperationCancelView` — `responses[409]` теперь содержит `ProblemEnvelope` (вместо простого `{"detail": "string"}`).
* `responses[403]` — `ProblemEnvelope` с `code: "role_not_permitted"`.
* `responses[404]` — `ProblemEnvelope` с `code: "operation_not_found"`.
* В `description` endpoint — «Возвращает envelope доменных ошибок в формате ADR-0027».

Регенерация OpenAPI — статический шаг (syncserver генерирует при старте). Достаточно обновить docstring роута.

---

## 10. Test Ladder

### 10.1. Static checks (Level 1)

* `cd SyncServer && python -m pytest --collect-only` — синтаксис и импорты.
* `cd SyncServer && python -m mypy app/services/operations_service.py app/services/operation_submit_errors.py app/services/operations_workflow_policy.py app/services/operations_policy.py` (если mypy настроен).
* `cd Warehouse_web && python manage.py check` — Django system check.
* `cd Warehouse_frontend && npx tsc --noEmit` — TypeScript компиляция.

### 10.2. Unit-тесты (Level 2)

SyncServer (`tests/`):
* `test_operation_submit_errors.py` — добавить тесты: `InsufficientStockError` с `problem_class="operation-cancel-rejected"` строит правильный `type` URN и `code="operation_cancel_rejected"`. То же для остальных 5 подклассов.
* `test_operations_service_cancel.py` — расширить: новые тесты на `exc.value` — это `InsufficientStockError` / `OperationInWrongStateError` / `OperationNotFoundError` / `RoleNotPermittedError`, **не** `HTTPException`. Проверить `deficits`, `code`, `problem_class`, `http_status`.
* `test_operations_workflow_policy.py` — добавить тесты: `require_exists` поднимает `OperationNotFoundError`, `require_not_cancelled_for_cancel` поднимает `OperationInWrongStateError`.
* `test_operations_policy.py` — добавить тесты: `require_operate_site` / `require_operation_cancel_permission` / `require_move_access` поднимают `RoleNotPermittedError`.
* Новый `test_check_cancel_balance_sufficiency.py` — тесты на двухфазный алгоритм с моками UoW.

Django (`apps/sync_client/test_*.py`, `apps/bff_api/tests.py`):
* `test_api_error_response.py` — обновить snapshot `OtherSubmitEndpointsSnapshotTests` (см. §7.2). Добавить тесты: `api_error_response` для 409 cancel-flow envelope (dict-`detail`) возвращает body as-is.
* `apps/sync_client/tests.py` — добавить тест: `_raise_for_response` для 409 + dict-`detail` → `exc.message` берётся из `detail.message` / `detail.detail` / fallback `str(exc)`, **не** Python-repr `str(dict)`.
* `apps/bff_api/tests.py` — расширить по образцу `test_operations_submit_sync_conflict_409_preserves_detail`:
  - `test_operations_cancel_409_preserves_status_and_envelope` — `SyncConflictError` с envelope-payload → response body = envelope as-is, status 409.
  - `test_operations_cancel_403_string_detail` — 403 с string-`detail` → `error.message == string`.
  - `test_operations_cancel_422_validation_error` — 422 (cancel != true) → `code = "validation_error"`.
  - `test_operations_cancel_storekeeper_only` — без роли → 403.
  - `test_operations_cancel_unauthenticated_redirect` — без аутентификации → redirect.

### 10.3. Component tests (Level 3)

Django: view-тесты — `apps/bff_api/tests.py::BffApiCancelViewTests` — для каждой ветки 409/403/404/422.

Angular:
* `Warehouse_frontend/src/app/core/services/operations.service.spec.ts` — добавить тесты:
  - `cancelOperation` happy path → `service.error = null`, `submitErrorService.cancelErrorPayload = null`.
  - `cancelOperation` с 409 envelope → `submitErrorService.cancelErrorPayload` заполнен, `service.error` установлен.
  - `cancelOperation` с 403 string-detail → `service.error == 'Доступ запрещён.'`.
  - `restoreOperation` — аналогично.
* `Warehouse_frontend/src/app/features/operations/submit-error/parser.spec.ts` — добавить тесты: `parseSubmitErrorResponse` для cancel envelope (type=`urn:warehouse:problem:operation-cancel-rejected`, code=`operation_cancel_rejected`).
* `Warehouse_frontend/src/app/features/operations/submit-error/submit-error.service.spec.ts` — добавить тесты: `setCancelFromHttpError` правильно парсит envelope и заполняет `cancelErrorPayload`.
* `Warehouse_frontend/src/app/features/operations/components/operation-create-modal/submit-error-toasts.spec.ts` — добавить тест: `OPERATION_LEVEL_TOAST_MESSAGES['operation_cancel_rejected']` = "Не удалось отменить операцию.".

### 10.4. Integration-тесты с реальной БД (Level 4)

* `SyncServer/tests/test_cancel_rollback_envelope.py` (**новый**) — DB-backed:
  - `test_cancel_move_rollback_insufficient_stock_envelope` — submitted MOVE без acceptance_required, destination пуст → `POST /cancel` → 409 + envelope с `code="operation_cancel_rejected"`, `errors[0].code="insufficient_stock"`, `item.name`, `stock_site.name`, `operation_line_ids=[line.id]`, `required_qty`/`available_qty` как строки.
  - `test_cancel_receive_rollback_insufficient_stock_envelope` — submitted RECEIVE, accepted_qty=10, остаток=2 → 409 + envelope.
  - `test_cancel_expense_rollback_insufficient_stock_envelope` — submitted EXPENSE, остаток=0 → 409 + envelope.
  - `test_cancel_adjustment_rollback_insufficient_stock_envelope` — submitted ADJUSTMENT, остаток=0 → 409 + envelope.
  - `test_cancel_issue_rollback_insufficient_issued_balance_envelope` — submitted ISSUE с issue_object_id, issued=0 → 409 + envelope `insufficient_issued_balance`.
  - `test_cancel_issue_return_rollback_insufficient_stock_envelope` — submitted ISSUE_RETURN, остаток=0 → 409 + envelope.
  - `test_cancel_write_off_with_issue_object_rollback_insufficient_issued_balance_envelope` — submitted WRITE_OFF с issue_object_id, issued=0 → 409 + envelope.
  - `test_cancel_move_with_acceptance_required_rollback_envelope` — submitted MOVE с acceptance_required, accepted_qty>0, destination остаток < accepted_qty → 409 + envelope.
  - `test_cancel_operation_in_wrong_state_envelope` — submitted повторный cancel → 409 + envelope `operation_in_wrong_state`, `current_state="cancelled"`.
  - `test_cancel_operation_not_found_envelope` — random UUID → 404 + envelope `operation_not_found`.
  - `test_cancel_role_not_permitted_envelope` — storekeeper токен, чужой site → 403 + envelope `role_not_permitted`.
  - `test_cancel_aggregate_deficits_multiple_lines` — submitted MOVE, две строки с одним inventory_subject_id на destination, остаток < суммы → envelope `errors[0].operation_line_ids = [id1, id2]`, `required_qty` = сумма.
  - `test_cancel_determinism_deficit_order` — submitted операция с 3 строками, 3 разных inventory_subject_id, 2 в дефиците → `errors[]` отсортированы по `line_number` первой строки группы.
  - `test_cancel_happy_path_no_envelope` — submitted EXPENSE с достаточным остатком → 200, операция становится cancelled, balances обновлены.
  - `test_cancel_partial_rollback_failure_leaves_balance_unchanged` — submitted EXPENSE, остаток < quantity → 409, balances не изменились, audit event не записан.

### 10.5. Concurrency-тесты (Level 4+)

* `SyncServer/tests/test_cancel_concurrency.py` (**новый**) — `pytest.mark.asyncio` с `asyncio.gather`:
  - `test_concurrent_cancel_and_submit` — два одновременных запроса на одну операцию (cancel + submit) → один проходит, другой получает envelope (409 `operation_in_wrong_state` или `stale_version`).
  - `test_concurrent_two_cancels` — два cancel на одну операцию → один проходит, другой получает 409 `operation_in_wrong_state` (статус уже cancelled).

### 10.6. Stand smoke (Level 5)

Stand: `make up` из `/home/makc/AI_sandbox/warehouse_solution`. Зонды:

* `curl -s --max-time 5 http://localhost:8000/api/v1/health` → `{"status": "ok"}`.
* `curl -s --max-time 5 http://localhost:8001/healthz/` → `200`.
* `pg_isready -h localhost -p 5432 -t 3` → `accepting connections`.

Сценарий:
1. `curl -X POST http://localhost:8000/api/v1/operations -H "X-User-Token: $ROOT_TOKEN" -d '{...}'` — создать submitted RECEIVE с quantity=10, site_id=1, item_id=1.
2. `curl -X POST http://localhost:8000/api/v1/operations/{id}/cancel -H "X-User-Token: $ROOT_TOKEN" -d '{"cancel": true}'` → **до фикса**: `{"detail": "insufficient stock for RECEIVE rollback: inventory_subject=1, site=1, required=10.000"}` (HTTP 409). **После фикса**: envelope `{type: "urn:warehouse:problem:operation-cancel-rejected", code: "operation_cancel_rejected", detail: "Недостаточно товара: ...", errors: [{code: "insufficient_stock", ...}]}`.
3. `curl -X GET http://localhost:8001/bff/api/v1/operations/{id}/cancel` — нет, GET не поддерживается. Проверка BFF: `curl -X POST http://localhost:8001/bff/api/v1/operations/{id}/cancel -H "Cookie: sessionid=..." -d '{"cancel": true}'` → response body = envelope as-is.

### 10.7. UI automation (Level 6)

Playwright:

* `Warehouse_frontend/e2e/operations/operations-cancel.spec.ts` (**новый**) — основные сценарии:
  - `test_cancel_button_opens_confirm` — клик по «Отменить» в строке списка → появляется `confirm("Отменить операцию?")`.
  - `test_cancel_happy_path_shows_success` — confirm → операция в cancelled, баннер очищен, список обновлён.
  - `test_cancel_insufficient_stock_shows_russian_error` — submitted MOVE с пустым destination → confirm → баннер с русским текстом «Недостаточно товара: ...» (а не «insufficient stock for ...»).
  - `test_cancel_insufficient_stock_highlights_line` — модальная отмена draft → строка подсвечена красным, inline-сообщение «На складе: X, запрошено: Y».
  - `test_cancel_role_not_permitted_shows_403` — storekeeper токен, чужой site → баннер «Недостаточно прав для отмены операции.».
  - `test_cancel_operation_not_found_shows_404` — UUID несуществующей операции → баннер «Операция уже удалена — обновите список.».
  - `test_cancel_keeps_list_visible` — после ошибки отмены таблица остаётся видимой (не блокируется).

* `make test-e2e` из workspace root — общий прогон.

### 10.8. User scenario (Level 7)

Сценарий «Кладовщик отменяет MOVE, у которого destination пуст»:
1. Логин в Django как storekeeper.
2. Открыть `/operations/`, найти submitted MOVE.
3. Нажать «Отменить», подтвердить.
4. Увидеть баннер «Не удалось отменить операцию. Недостаточно товара: Кабель ВВГ 3×2.5 — запрошено 2, на складе 0. Всего проблемных групп: 1.» (а НЕ «insufficient stock for MOVE rollback from destination: ...»).
5. Таблица остаётся видимой, операция — в статусе submitted.

### 10.9. Regression (Level 8)

* `test_syncserver_envelope_compat.py` — submit-flow envelope не сломан.
* `test_submit_transaction.py` — submit rollback не сломан.
* `test_stale_balance_conflict.py` — submit insufficient stock envelope не сломан.
* `apps/bff_api/tests.py::test_operations_submit_*` — submit BFF не сломан.
* `Warehouse_frontend/e2e/operations/submit-errors.spec.ts` — submit envelope UI не сломан.
* `apps/sync_client/test_api_error_response.py::OtherSubmitEndpointsSnapshotTests` — после обновления snapshot'а все остальные endpoints по-прежнему на `_handle_sync_error`.

---

## 11. Файлы в scope

### SyncServer

* `app/services/operation_submit_errors.py` — расширить сигнатуры подклассов (kwarg `problem_class`), добавить ветку `_code()` для `operation-cancel-rejected`.
* `app/services/operations_service.py` — новый `_check_cancel_balance_sufficiency`, вставка pre-check в `cancel_operation`.
* `app/services/operations_workflow_policy.py` — `require_exists`, `require_not_cancelled_for_cancel` → доменные исключения.
* `app/services/operations_policy.py` — три authz-метода → `RoleNotPermittedError`.
* `app/repos/sites_repo.py` — добавить `get_by_id` если отсутствует.
* `app/schemas/operation_submit_error.py` — без изменений.
* `app/api/exceptions_handlers.py` — без изменений (handler уже зарегистрирован для базового класса).
* `app/api/routes_operations.py` — docstring обновить, поведение не меняется.
* `app/main.py` — без изменений.

### Warehouse_web

* `apps/sync_client/client.py` — `_raise_for_response:131-141` dict-detail fallback.
* `apps/sync_client/api_error_response.py` — без изменений.
* `apps/bff_api/operations_views.py` — `OperationCancelView.post` → `api_error_response`.
* `apps/bff_api/helpers.py` — без изменений.
* `apps/sync_client/test_api_error_response.py` — обновить snapshot `OtherSubmitEndpointsSnapshotTests`.
* `apps/sync_client/tests.py` — новые тесты `_raise_for_response` с dict-detail.
* `apps/bff_api/tests.py` — новые тесты `OperationCancelView` envelope.

### Warehouse_frontend

* `src/app/core/services/operations.service.ts` — `cancelOperation`/`restoreOperation` пробрасывают envelope в `SubmitErrorService`.
* `src/app/features/operations/submit-error/submit-error.service.ts` — `cancelErrorPayload` + `setCancelFromHttpError` + `clearCancel`.
* `src/app/features/operations/submit-error/envelope.ts` — расширить `KnownErrorCode` при необходимости.
* `src/app/features/operations/components/operation-create-modal/submit-error-toasts.ts` — `OPERATION_LEVEL_TOAST_MESSAGES['operation_cancel_rejected']`.
* `src/app/features/operations/pages/operations-page/operations-page.component.ts` — отображение cancel-ошибки в баннере + toast.
* `src/app/core/services/operations.service.spec.ts` — тесты `cancelOperation`/`normalizeError`.
* `src/app/features/operations/submit-error/parser.spec.ts` — тесты для cancel envelope.
* `src/app/features/operations/submit-error/submit-error.service.spec.ts` — тесты `setCancelFromHttpError`.
* `src/app/features/operations/components/operation-create-modal/submit-error-toasts.spec.ts` — тест `operation_cancel_rejected`.
* `e2e/operations/operations-cancel.spec.ts` (**новый**) — Playwright сценарии.

### Документация

* `docs/adr/0025-operation-submit-domain-errors.md` §8 — обновить (см. §7.4).
* `docs/adr/0027-operation-cancel-domain-errors.md` — без изменений (уже написан).
* `docs/TZ-OPERATION_CANCEL_DOMAIN_ERRORS.md` — без изменений (этот файл).
* `docs/RAG_SEARCH_GUIDE.md` §9 — обновить якорь «SyncServer: детали ошибки остатка» → добавить cancel-flow.
* `docs/README.md` / `INDEX.md` — добавить ссылку на ADR-0027 и TZ.

---

## 12. Файлы out of scope

* `corrections_service.py` — корректировки, ADR-0025 §9 (Этап 2).
* `operations_service.py:submit_operation` (строки 1650-1807) — submit-flow.
* `routes_documents.py`, `routes_admin_*`, `routes_temporary_items.py` — не cancel.
* `apps/bff_api/helpers.py::_error` — для catalog и других endpoints, не cancel.
* `apps/bff_api/operations_views.py::OperationSubmitView` — submit, не cancel.
* `_apply_balance_delta` (строки 458-487) — ADR-0025 §5.7.
* `OfflineSync` / `Warehouse_client_core` — оффлайн-клиенты.
* `WarehouseAIWorkstation` — paused.

---

## 13. Acceptance Criteria

### 13.1. Server (SyncServer)

* `POST /api/v1/operations/{id}/cancel` с rollback-дефицитом возвращает HTTP 409 + envelope с `type="urn:warehouse:problem:operation-cancel-rejected"`, `code="operation_cancel_rejected"`, `detail` — русский человеческий текст, `errors[0].code="insufficient_stock"`, `errors[0].item.name` (не `<id 123>`), `errors[0].stock_site.name`, `errors[0].operation_line_ids=[...]`, `errors[0].required_qty`/`available_qty` — строки.
* `POST /cancel` с 2+ строками одного inventory_subject_id, попадающими в дефицит → `errors[0].operation_line_ids` содержит оба `line.id`, `required_qty` — сумма.
* `POST /cancel` на cancelled-операцию → 409 + envelope `operation_in_wrong_state`, `current_state="cancelled"`.
* `POST /cancel` без auth → 401 (стандартное поведение FastAPI).
* `POST /cancel` storekeeper токен, чужой site → 403 + envelope `role_not_permitted`.
* `POST /cancel` несуществующий UUID → 404 + envelope `operation_not_found`.
* `POST /cancel` happy path (достаточный остаток) → 200 + операция в `cancelled`, balances обновлены, audit event записан.

### 13.2. BFF (Warehouse_web)

* `POST /bff/api/v1/operations/{id}/cancel` с envelope-ответом SyncServer пробрасывает envelope as-is в response body, status 409.
* Snapshot-инвариант `OtherSubmitEndpointsSnapshotTests` обновлён и проходит.
* `_raise_for_response` для dict-`detail` кладёт в `exc.message` читаемый текст, не Python-repr.

### 13.3. Frontend (Warehouse_frontend)

* `cancelOperation` при 409 envelope → `submitErrorService.cancelErrorPayload` заполнен, баннер/toast отображают русский текст.
* `cancelOperation` при 403 string-detail → баннер «Доступ запрещён.» (существующее поведение).
* `restoreOperation` получает те же улучшения (побочный эффект общего handler'а).
* `OperationLevelErrorCode` union покрывает `operation_cancel_rejected`.
* `OPERATION_LEVEL_TOAST_MESSAGES['operation_cancel_rejected']` = "Не удалось отменить операцию.".

### 13.4. Документация

* ADR-0025 §8 обновлён и синхронизирован с реализацией.
* ADR-0027 и TZ-OPERATION_CANCEL_DOMAIN_ERRORS ссылаются друг на друга.
* `docs/RAG_SEARCH_GUIDE.md` §9 — якорь cancel-flow envelope добавлен.
* README/INDEX ссылаются на новые документы.

### 13.5. Регрессия

* Submit-flow envelope не сломан (полный прогон submit-related tests).
* `_apply_balance_delta` английский fallback работает в корректировках.
* Другие BFF-эндпоинты (`_handle_sync_error`) не затронуты.

---

## 14. Допущения и риски

### Допущения

1. SyncServer тесты на pytest работают (env не проверял — `SyncServer/AGENTS.md` говорит «default verification: `python -m pytest`»).
2. Django стенд работает (`make up` успешен).
3. Angular e2e через Playwright работает (`make test-e2e` успешен).
4. `uow.sites.get_by_id` либо существует, либо будет добавлен в этой итерации.
5. Существующий handler `operation_submit_error_handler` корректно отрабатывает cancel-flow исключения (handler зарегистрирован на базовый класс).

### Риски

1. **Sensitive area** `operations_service.py` (`SyncServer/AGENTS.md`). Минимизирован: pre-check в новом helper, `cancel_operation` — минимальная вставка.
2. **Snapshot-инвариант** `OtherSubmitEndpointsSnapshotTests` ломается — обновление синхронно.
3. **Корректировки** используют `_apply_balance_delta` (ADR-0025 §5.7). Pre-check добавляется **только** в `cancel_operation`, **не** в корректировки. Safety net `_apply_balance_delta` английский fallback продолжает работать для корректировок.
4. **`_upsert_issued`** (строки 752-770) — pre-check `dict_issued` ловит дефициты, но если race condition, fallback `HTTPException(f"issued asset quantity conflict for ...")` останется английским. Это **допустимо** (аналогично submit §7).
5. **Restore-flow** — envelope уже работает через handler базового класса, но UX-доработка (модалка, toast) отложена. Это **не** блокер.
6. **Offline-клиенты** — формат envelope не оптимизирован под оффлайн (ADR-0025 §9). Cancel-flow не ухудшает ситуацию.

---

## 15. Порядок реализации (рекомендация)

Рекомендую **3 параллельных shard'а** (после утверждения плана пользователем):

1. **SyncServer shard** — `operations_service.py` + `operations_policy.py` + `operations_workflow_policy.py` + `operation_submit_errors.py` + новые тесты. Verifies: pytest, alembic (если миграций нет — без миграций).
2. **Django BFF shard** — `apps/sync_client/client.py` + `apps/bff_api/operations_views.py` + `apps/sync_client/test_api_error_response.py` snapshot. Verifies: `python manage.py test apps.sync_client apps.bff_api`.
3. **Angular shard** — `operations.service.ts` + `submit-error.service.ts` + `submit-error-toasts.ts` + новые unit + новый e2e. Verifies: `npm run test:unit`, `make test-e2e`.

После интеграции — прогон ADR-0027 + ADR-0025 regression pack + dev-стенд smoke.

---

## 16. Связанные документы

* ADR-0027 — `docs/adr/0027-operation-cancel-domain-errors.md`
* ADR-0025 — `docs/adr/0025-operation-submit-domain-errors.md`
* TZ-SYNCSERVER_OPERATION_SUBMIT_DOMAIN_ERRORS — `docs/TZ-SYNCSERVER_OPERATION_SUBMIT_DOMAIN_ERRORS.md`
* TZ-FRONTEND_OPERATION_SUBMIT_ERROR_SURFACE — `docs/TZ-FRONTEND_OPERATION_SUBMIT_ERROR_SURFACE.md`
* Functional and WorkLogik — `Functional and WorkLogik.md` §6.8, §6.9
* RAG Search Guide — `docs/RAG_SEARCH_GUIDE.md`
* SyncServer Agent Contract — `SyncServer/AGENTS.md`
* Warehouse_web Agent Contract — `Warehouse_web/AGENTS.md`
* Warehouse_frontend Agent Contract — `Warehouse_frontend/AGENTS.md`
