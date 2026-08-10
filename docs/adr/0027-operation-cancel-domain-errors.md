# ADR-0027 — Доменные ошибки отмены операций: единый envelope (cancel-flow)

- Status: Proposed
- Date: 2026-08-05
- Deciders: architect, syncserver-lead, frontend-tech-lead
- Supersedes: частично — `operations_service.py:2511-2775` (cancel-flow) и `_apply_balance_delta` остаются в текущей форме, переписываются только точки `raise` и BFF-helper'ы
- Source TZ: `docs/TZ-OPERATION_CANCEL_DOMAIN_ERRORS.md`
- Source ADR: `docs/adr/0025-operation-submit-domain-errors.md`
- Решаемый баг: production «insufficient stock for MOVE rollback from destination: inventory_subject=…, site=…, required=…» (Косяк 2)

## Контекст

### Что подтвердила разведка 2026-08-05

При отмене проведённой операции (cancel-flow) кладовщик получает сырую серверную строку на английском, без имени ТМЦ, без доступного остатка, без `operation_line_id`. Полная цепочка `POST /api/v1/operations/{id}/cancel` → default FastAPI handler → Django BFF `_handle_sync_error` → Angular `service.error`:

1. `SyncServer/app/api/routes_operations.py:353-382` — endpoint тонкий, не ловит `OperationSubmitError`. Любой `HTTPException` уходит в default handler и возвращается как `{"detail": "<строка>"}` со статусом 4xx.
2. `SyncServer/app/services/operations_service.py:2511-2775` (`OperationsService.cancel_operation`) — для каждой submitted-операции прогоняет rollback-балансировку через `_apply_balance_delta` (строки 458-487, шаблон `f"insufficient stock for {error_context}: inventory_subject=..., site=..., required=..."`) и через прямой вызов `_ensure_sufficient_balance` (строки 2662-2671, **самый частый сценарий — MOVE без acceptance_required**).
3. `SyncServer/app/services/operations_service.py:99-114` (`_ensure_sufficient_balance`) и `:752-770` (`_upsert_issued`) поднимают **сырой `HTTPException(409, detail=<english>)`** — никакого доменного `OperationSubmitError`.
4. `SyncServer/app/api/exceptions_handlers.py:1-17` — зарегистрирован только для `OperationSubmitError`. `HTTPException` не покрыт, поэтому envelope не строится.
5. `Warehouse_web/apps/bff_api/operations_views.py:393-417` (`OperationCancelView`) использует `_handle_sync_error` (`apps/bff_api/helpers.py:113-193`), **не** `api_error_response`. Snapshot-тест `apps/sync_client/test_api_error_response.py:96-105` это явно фиксирует.
6. `Warehouse_web/apps/sync_client/client.py:124-163` (`_raise_for_response`, строка 133) кладёт `str(sanitized.get("detail") or "SyncServer error")` в `message` — для dict-`detail` это даёт Python-repr.
7. `Warehouse_frontend/src/app/core/services/operations.service.ts:474-488, :490-505` (`cancelOperation`, `restoreOperation`) в `catch` зовут `normalizeError` (`:973-982`), которая читает **только** `err?.message` и `err?.fields` — `err.raw` отбрасывается.
8. `Warehouse_frontend/src/app/features/operations/pages/operations-page/operations-page.component.ts:582-590` (`onRowCancel`) и `:1028-1041` (`onDraftOperationCancel`) — `catch {}` молча проглатывает ошибку; в баннере `data-testid="operations-error-message"` показывается `service.error()` — то есть английская строка.

10+ rollback-веток в `cancel_operation` идут через `_apply_balance_delta` / `_upsert_issued` / прямой `_ensure_sufficient_balance` (RECEIVE accepted/lost/pending, RECEIVE без acceptance, EXPENSE, WRITE_OFF от issue_object, ADJUSTMENT, MOVE accepted/lost/pending, MOVE без acceptance_required, ISSUE, ISSUE_RETURN).

### Что решил ADR-0025

ADR-0025 (`docs/adr/0025-operation-submit-domain-errors.md`) ввёл единый envelope **только для submit-flow**. Cancel-flow явно out-of-scope (TZ §1.5, §2 #3, §5.7, §8, §9 «Что не делается»). Текущая английская строка — закономерный артефакт этой дисциплины, а не регрессия.

### Что требуется

Распространить тот же envelope-контракт и инфраструктуру на cancel-flow (`POST /api/v1/operations/{id}/cancel`), с теми же кодами, что и в submit-flow: `insufficient_stock`, `insufficient_issued_balance`, `operation_in_wrong_state`, `stale_version`, `role_not_permitted`, `operation_not_found`. Дополнительно — канонический `detail` по-русски и стабильный `operation_line_ids[]` для inline-подсветки строк.

## Решение

### 0. Положения scope, отменённые разведкой

Разведка 2026-08-05 показала, что часть потенциального scope либо преждевременна, либо должна быть ограничена. Эти положения **отменены** этим ADR:

| Положение scope | Что предполагалось | Что выявила разведка | Что делаем |
| --- | --- | --- | --- |
| Точечный текст в f-строке | «Поменять `f"insufficient stock for {error_context}: inventory_subject=..., site=..., required=..."` на русскую f-строку» | Это сломает ADR-0025 §3 (dual response: `detail` остаётся строкой, машиночитаемые данные в `errors[]`) и оставит парсер envelope без структуры. Кладовщик не сможет надёжно подсветить проблемные строки. | Отменено. Минимальный контракт — единый envelope, а не человеческая f-строка |
| Ввести `OperationCancelError` как отдельный базовый класс | «Семантически отличать cancel-flow от submit-flow разными базовыми классами» | `OperationSubmitError` уже умеет `problem_class` (см. `operation_submit_errors.py:51-83`), подклассы `InsufficientStockError`/`InsufficientIssuedBalanceError`/`OperationInWrongStateError`/`StaleVersionError`/`RoleNotPermittedError`/`OperationNotFoundError` подходят и для cancel. Handler `operation_submit_error_handler` (строки 9-17) маппит **весь базовый класс** через `to_envelope()`. Создание параллельного базового класса размоет контракт и удвоит регистрацию handler'ов | Отменено. Переиспользуем `OperationSubmitError` и подклассы с новым `problem_class = "operation-cancel-rejected"` для cancel-flow envelope; handler уже зарегистрирован |
| Перевести все BFF-эндпоинты на `api_error_response` | «Глобально мигрировать `_handle_sync_error` → `api_error_response` для list/detail/submit/cancel/restore/effective-at» | ADR-0025 §8 явно ограничил helper submit-flow, а `OtherSubmitEndpointsSnapshotTests` (`apps/sync_client/test_api_error_response.py:96-105`) фиксирует асимметрию. Глобальная миграция — отдельный TZ, риск регрессий каталога и admin-эндпоинтов | Отменено. Переводим на envelope-as-is **только** `OperationCancelView`, синхронно обновляя snapshot-инвариант и ADR-0025 §8 |
| Клиентский precheck остатков перед отменой | «Проверить доступный остаток на UI до POST /cancel» | Это UX-оптимизация, не закрывает race conditions и server-side reject. Спорный остаток может появиться между precheck и cancel | Отменено. Сервер остаётся авторитетом, клиент только отображает |
| `corrections_service.py:912` (`correction_insufficient_balance`) | «Включить корректировки в cancel-flow envelope» | Корректировки — отдельный flow, миграция на тот же envelope была явно отложена ADR-0025 §9 (Этап 2, отдельный TZ) | Отменено. Out of scope |
| Расширить scope на `restore-flow` | «Тот же envelope применить к restore» | Restore-flow возвращает cancelled-операцию в draft, не вызывает rollback остатков. Текущая ошибка restore (если есть) — `OperationInWrongStateError` / `RoleNotPermittedError`, для них envelope **уже** работает через submit-base handler, если они поднимают `OperationSubmitError`. Адаптация restore — отдельный TZ | Отменено. Только cancel-flow в этой итерации |

### 1. Единый envelope для всех доменных ошибок `POST /api/v1/operations/{id}/cancel`

При любой доменной ошибке cancel SyncServer возвращает тот же формат, что и submit (ADR-0025 §1), с одной модификацией: `type = "urn:warehouse:problem:operation-cancel-rejected"` и `code = "operation_cancel_rejected"` для cancel-flow envelope; `code` верхнего уровня для cancel-flow подклассов:

| Подкласс | `code` верхнего уровня | `problem_class` | `http_status` |
| --- | --- | --- | ---: |
| `InsufficientStockError` (cancel-flow) | `operation_cancel_rejected` | `operation-cancel-rejected` | 409 |
| `InsufficientIssuedBalanceError` (cancel-flow) | `operation_cancel_rejected` | `operation-cancel-rejected` | 409 |
| `OperationInWrongStateError` (cancel-flow) | `operation_cancel_rejected` | `operation-cancel-rejected` | 409 |
| `StaleVersionError` (cancel-flow) | `operation_cancel_rejected` | `operation-cancel-rejected` | 409 |
| `RoleNotPermittedError` (cancel-flow) | `role_not_permitted` | `operation-cancel-rejected` | 403 |
| `OperationNotFoundError` (cancel-flow) | `operation_not_found` | `operation-not-found` | 404 |

**Разделяем `code` верхнего уровня от `code` внутри `errors[]`:**

- `code` верхнего уровня — **класс ответа** (`operation_cancel_rejected` для cancel-flow envelope).
- `errors[].code` — **конкретная причина** (`insufficient_stock`, `insufficient_issued_balance`, `operation_in_wrong_state`, `stale_version`, `role_not_permitted`, `operation_not_found`).

`RoleNotPermittedError` и `OperationNotFoundError` сохраняют те же `code` верхнего уровня, что и в submit-flow (`role_not_permitted` / `operation_not_found`) — это единая семантика для всего API, различается только `type` (URN) и `code` верхнего уровня envelope.

`type` строится как `f"urn:warehouse:problem:{exc.problem_class}"`. Для cancel-flow `problem_class = "operation-cancel-rejected"`. Парсер на фронте различает submit и cancel по `type` и `code` верхнего уровня; `errors[].code` общие.

### 2. Коды `errors[]` первой итерации

Те же, что в submit-flow (ADR-0025 §2), без новых кодов:

| `errors[].code` | `scope` | HTTP | Обязательные поля |
| --- | --- | ---: | --- |
| `insufficient_stock` | `line_group` | 409 | `operation_line_ids[]`, `item`, `stock_site`, `required_qty`, `available_qty`; `unit` optional display-only |
| `insufficient_issued_balance` | `line_group` | 409 | `operation_line_ids[]`, `item`, `issue_object`, `required_qty`, `available_qty`; `unit` optional display-only |
| `operation_in_wrong_state` | `operation` | 409 | `current_state`, `allowed_states[]` |
| `stale_version` | `operation` | 409 | `expected_version`, `actual_version` |
| `role_not_permitted` | `operation` | 403 | только `code`, `scope` |
| `operation_not_found` | `operation` | 404 | только `code`, `scope` |

### 3. Двухфазная агрегированная проверка остатков в cancel-flow

Алгоритм повторяет submit-flow (ADR-0025 §5), но с другим набором «расходующих» эффектов.

**Фаза 1. Сбор инверсивных эффектов rollback.**

Один проход по строкам `operation.lines` (упорядоченным по `line_number` ascending). Для каждой строки в зависимости от `operation_type` определяется **направление rollback** и ключ баланса:

| `operation_type` | `acceptance_required` | Эффект rollback | Ключ баланса | Куда идёт в проверку |
| --- | --- | --- | --- | --- |
| `RECEIVE` | `True` (pending) | `pending_qty` → `_upsert_pending(-)` (не уменьшает warehouse) | — | не участвует в warehouse-проверке |
| `RECEIVE` | `True` (accepted) | `accepted_qty` → `-accepted_qty` на `(operation.site_id, line.inventory_subject_id)` | `(site_id, inventory_subject_id)` | **warehouse** |
| `RECEIVE` | `True` (lost) | `lost_qty` → `_upsert_lost(-)` (не уменьшает warehouse) | — | не участвует |
| `RECEIVE` | `False` | `quantity` → `-quantity` на `(operation.site_id, line.inventory_subject_id)` | `(site_id, inventory_subject_id)` | **warehouse** |
| `EXPENSE` / `WRITE_OFF` (без `issue_object_id`) | — | `quantity` → `+quantity` на `(operation.site_id, line.inventory_subject_id)` (откат EXPENSE/WRITE_OFF означает возврат на склад) | `(site_id, inventory_subject_id)` | **warehouse** |
| `ADJUSTMENT` | — | `-quantity` на `(operation.site_id, line.inventory_subject_id)` (откат ADJUSTMENT инвертирует корректировку) | `(site_id, inventory_subject_id)` | **warehouse** |
| `MOVE` | `True` (accepted) | `accepted_qty` → `-accepted_qty` на `destination_site_id` | `(destination_site_id, line.inventory_subject_id)` | **warehouse** |
| `MOVE` | `True` (pending/lost) | pending/lost → `_upsert_pending(-)` / `_upsert_lost(-)` | — | не участвует |
| `MOVE` (любой) | — | `quantity` → `+quantity` на `source_site_id` (откат перемещения = возврат на source) | `(source_site_id, line.inventory_subject_id)` | **warehouse** |
| `MOVE` | `False` (без acceptance) | `quantity` → `-quantity` на `destination_site_id` (дополнительно к source-rollback) | `(destination_site_id, line.inventory_subject_id)` | **warehouse** |
| `WRITE_OFF` (`issue_object_id is not None`) | — | `quantity` → `+quantity` на `(issue_object_id, line.inventory_subject_id)` (возврат в issued register) | `(issue_object_id, line.inventory_subject_id)` | **issued** |
| `ISSUE` | — | `quantity` → `-quantity` на `(issue_object_id, line.inventory_subject_id)` (откат ISSUE = снять с issue_object) | `(issue_object_id, line.inventory_subject_id)` | **issued** |
| `ISSUE` | — | `quantity` → `+quantity` на `(operation.site_id, line.inventory_subject_id)` (вернуть на склад) | `(operation.site_id, line.inventory_subject_id)` | **warehouse** |
| `ISSUE_RETURN` | — | `quantity` → `-quantity` на `(operation.site_id, line.inventory_subject_id)` (откат ISSUE_RETURN = снять со склада) | `(operation.site_id, line.inventory_subject_id)` | **warehouse** |
| `ISSUE_RETURN` | — | `quantity` → `+quantity` на `(issue_object_id, line.inventory_subject_id)` (вернуть на issue_object) | `(issue_object_id, line.inventory_subject_id)` | **issued** |

Строки, не уменьшающие баланс (RECEIVE pending/lost, MOVE pending/lost, `_upsert_pending(-)` для pending отката), **не участвуют** в проверке.

Результат фазы 1: `dict_warehouse: dict[BalanceKey, list[(line, required_qty)]]` и `dict_issued: dict[IssuedBalanceKey, list[(line, required_qty)]]`.

**Фаза 2. Блокировка и проверка.**

1. Из обоих словарей — глобальная сортировка `sorted_warehouse_keys = sorted(dict_warehouse.keys())` и `sorted_issued_keys = sorted(dict_issued.keys())` (tuple-based). Сортировка детерминирована → deadlock невозможен.
2. Для каждого ключа ровно один `await uow.balances.get_for_update(...)` (или `asset_registers.get_issued_balance(...)`). Внутри блокировки читается `available_qty`.
3. `sum_required = sum(qty for _, qty in dict_warehouse[k])` сравнивается с `available_qty`. Если `sum_required > available_qty` — формируется `StockDeficit`:
   - `operation_line_ids = [line.id for line, _ in dict_warehouse[k]]` в порядке `line.line_number`;
   - `required_qty = sum_required`;
   - `available_qty = balance.qty` (внутри блокировки).
4. Все `StockDeficit` собираются в `deficits_warehouse`; `IssuedStockDeficit` — в `deficits_issued`.
5. **Порядок возврата** — `deficits_warehouse` и `deficits_issued` сортируются по `line_number` первой строки группы ascending.
6. Если `deficits_warehouse` непуст — поднимается `InsufficientStockError(deficits=...)`. Если `deficits_issued` непуст — `InsufficientIssuedBalanceError(deficits=...)`. Если оба непусты — поднимается **одно** исключение по приоритету **warehouse сначала**, второе логируется для отладки. Это согласуется с submit-flow §5.
7. На уровне `cancel_operation` поднимается **одно** доменное исключение, не цикл `raise → catch → raise` по строкам. Handler `operation_submit_error_handler` зарегистрирован на **весь базовый класс** `OperationSubmitError`, поэтому ловит оба cancel-flow и submit-flow исключения без дополнительной регистрации.

### 4. Откуда брать имена ТМЦ и сайтов

- `item_id` / `item_name` — из `uow.catalog.get_item_by_id(line.item_id)` (используется в `_apply_balance_delta` через `item_name_snapshot`, см. `operations_service.py:1063-1093`); добавить явный lookup в новом `cancel_balance_check` (см. §5).
- `unit_id` / `unit_name` / `unit_symbol` — через `uow.catalog.get_unit_by_id(item.unit_id)` (строки 1077-1083).
- `stock_site_name` — через `uow.sites.get_site_name(site_id)` (новый, или переиспользовать `uow.sites.get_by_id` если уже есть).
- `issue_object_name` — через `uow.issue_objects.get_by_id(issue_object_id)`.

Если lookup возвращает `None` (ТМЦ удалён, сайт переименован) — использовать `name = f"<id {item_id}>"` / `f"<id {site_id}>"`, **не** падать 500-ой. Это edge case ADR-0025 не покрывал, добавляем явно.

### 5. Сервисный контракт cancel-flow

Вводится новый private-helper `OperationsService._check_cancel_balance_sufficiency(uow, operation)` рядом с существующим `_check_submit_balance_sufficiency` (строки 319-430):

```python
@staticmethod
async def _check_cancel_balance_sufficiency(
    uow: UnitOfWork, *, operation: Operation
) -> None:
    """Two-phase aggregated balance check for cancel-flow rollback.

    Raises InsufficientStockError / InsufficientIssuedBalanceError with
    fully-populated StockDeficit / IssuedStockDeficit (item.name, site.name,
    operation_line_ids[]). Called by cancel_operation BEFORE
    _apply_balance_delta / _upsert_issued / direct _ensure_sufficient_balance.
    """
```

Семантически — **зеркало** `_check_submit_balance_sufficiency`. Можно даже переиспользовать одну функцию через параметр `mode: Literal["submit", "cancel"]`, но в этой итерации делаем два независимых метода, чтобы не сломать submit-flow (sensitive area `operations_service.py:1-450`, зафиксировано в `SyncServer/AGENTS.md`).

### 6. Изменения в `cancel_operation`

Файл: `SyncServer/app/services/operations_service.py`, строки 2511-2775. Текущая структура:

```python
if operation.status == "submitted":
    for line in operation.lines:
        await OperationsService._ensure_line_inventory_subject(uow, line)
        quantity = Decimal(line.qty)
        ...
        # 10+ branches raising HTTPException with english f-strings
```

Новая структура:

```python
if operation.status == "submitted":
    # PHASE 0: aggregated read-only pre-check. No side effects.
    await OperationsService._check_cancel_balance_sufficiency(uow, operation=operation)
    # Above raises OperationSubmitError -> envelope. No mutations committed.

    for line in operation.lines:
        await OperationsService._ensure_line_inventory_subject(uow, line)
        quantity = Decimal(line.qty)
        ...
        # branches now contain ONLY the mutating calls:
        # _apply_balance_delta, _upsert_pending, _upsert_lost, _upsert_issued.
        # NO HTTPException for insufficient balance — the pre-check already
        # raised the envelope. If a real balance race happens between PHASE 0
        # and the mutation, _apply_balance_delta keeps the safety net
        # (raise HTTPException), but with russian message (see §7).
```

Двухфазный split: pre-check собирает все дефициты, мутации — только применяют их. Если между pre-check и mutation баланс изменился (другая транзакция) — мутация упадёт в `balances_repo.update_balance_quantity` через row-level lock; это путь `IntegrityError`/`ValueError`, **не** envelope, и обрабатывается существующим 500-handler'ом. Это допустимо: race condition во время cancel — крайне редкий случай (cancel идёт через `with uow:` транзакцию с `with_for_update()`).

### 7. Текст русскоязычного fallback в `_apply_balance_delta`

`operations_service.py:482-487` сейчас формирует английский `f"insufficient stock for {error_context}: inventory_subject=..., site=..., required=..."`. Этот код вызывается **не только** cancel-flow, но и корректировками (ADR-0025 §5.7). Двойное использование означает, что менять f-строку опасно.

Решение: **не трогаем** `_apply_balance_delta` (ADR-0025 §5.7 фиксирует это как инвариант). В `cancel_operation` после `_check_cancel_balance_sufficiency` остаётся только «happy path» через `_apply_balance_delta` — он больше не должен поднимать `insufficient stock` HTTPException, потому что pre-check уже всё поймал. Если всё-таки поднимет (race condition) — оставляем английский fallback для логов; envelope придёт раньше.

### 8. Workflow-политики

Файл: `SyncServer/app/services/operations_workflow_policy.py`.

| Текущая строка | Текущая ошибка | Что делаем |
| --- | --- | --- |
| `require_exists` (10-12) | `HTTPException(404, "operation not found")` | Превращаем в `raise OperationNotFoundError(operation_id)`. Подкласс `OperationSubmitError` уже определён, handler зарегистрирован. Cancel-flow получает `code = "operation_not_found"`, `problem_class = "operation-not-found"`, `http_status = 404` |
| `require_not_cancelled_for_cancel` (61-67) | `HTTPException(409, "operation is already cancelled")` | Превращаем в `raise OperationInWrongStateError(current_state="cancelled", allowed_states=["draft", "submitted"])` (или какой реальный список — зафиксировать в TZ). Cancel-flow получает `code = "operation_in_wrong_state"`, `problem_class = "operation-cancel-rejected"`, `http_status = 409` |

`require_root_for_restore` и прочие политики, которые **не вызываются** из cancel-flow — **не** трогаем. ADR-0025 §1.5 явно out-of-scope'нул их.

### 9. Authz-политики

Файл: `SyncServer/app/services/operations_policy.py`.

| Текущая строка | Текущая ошибка | Что делаем |
| --- | --- | --- |
| `require_operate_site` (26-32) | `HTTPException(403, "operate permission required")` | Превращаем в `raise RoleNotPermittedError()`. `problem_class = "operation-cancel-rejected"`, `http_status = 403` |
| `require_operation_cancel_permission` (142-151) | `HTTPException(403, "user has no cancel permission")` | То же — `RoleNotPermittedError` |
| `require_move_access` (159-168) | `HTTPException(403, "user has no move access")` | То же — `RoleNotPermittedError` |

`require_root_for_restore` (176-180) и `require_cancelled_for_delete` — **не** вызываются из cancel-flow, не трогаем.

### 10. Django BFF

Файл: `Warehouse_web/apps/bff_api/operations_views.py`, строки 393-417 (`OperationCancelView`).

Текущая ветка обработки ошибки: `_handle_sync_error(exc)` (`apps/bff_api/helpers.py:113-193`). Заменяем на `api_error_response(exc)` (`apps/sync_client/api_error_response.py`) — тот же helper, что и для `OperationSubmitView`. Это синхронное расширение скоупа ADR-0025 §8; требует:

1. Обновить snapshot-инвариант `OtherSubmitEndpointsSnapshotTests` (`apps/sync_client/test_api_error_response.py:96-105`): `EXPECTED_HELPERS["OperationCancelView"] = "api_error_response"`. Заодно убрать из «invariant that this ADR must not change» комментарий.
2. Добавить `api_error_response` в импорты `operations_views.py`.

Транспорт `client.py::_raise_for_response:131-141` — **опциональный** дополнительный фикс. Если SyncServer теперь отдаёт envelope (dict-`detail`), `str(sanitized.get("detail"))` на строке 133 даёт Python-repr. Нужно:

- если `detail` — dict: `message = detail.get("message") or detail.get("detail") or str(exc)`;
- если `detail` — строка: оставить текущее поведение.

Это **минимизирует** шум в логах и делает `exc.message` внятным; envelope-контракт (`exc.payload`) при этом **не** меняется.

### 11. Frontend

Файл: `Warehouse_frontend/src/app/core/services/operations.service.ts:474-488, :490-505` (`cancelOperation`, `restoreOperation`).

Текущая логика: `catch { this.normalizeError(err) }` → `normalizeError` читает только `err.message`.

Что делаем:

1. В `cancelOperation`/`restoreOperation` после `catch` дополнительно вызвать `submitErrorService.setFromHttpError(err?.raw ?? err)`, если `err.raw` — envelope (содержит `errors[]` или `code`). Это переиспользует существующий парсер (`features/operations/submit-error/parser.ts:97` `normalizeError`).
2. В `operations-page.component.ts` отделить отмену/восстановление от list-load: при cancel/restore не блокировать таблицу, показать ошибку через `submitErrorService`/`submitErrorPayload` + line-group тосты.
3. Расширить `OPERATION_LEVEL_TOAST_MESSAGES` (`features/operations/components/operation-create-modal/submit-error-toasts.ts:10-15`) текстом «Не удалось отменить операцию.» для `operation_cancel_rejected`.
4. В `SubmitErrorService` — добавить `cancelErrorPayload = signal<SubmitErrorViewModel | null>(null)` и helper `setCancelFromHttpError(raw)`, симметричный существующему `setFromHttpError`.

Restore-flow обработка — отдельный TZ (см. §0).

### 12. Совместимость и dual response

ADR-0025 §3 dual response сохраняется:

- `detail` остаётся **строкой**, человекочитаемой, по-русски (например, «Недостаточно товара: Кабель ВВГ — запрошено 120, на складе 80. Всего проблемных групп: 1.»).
- Машиночитаемые данные — в `errors[]`.

Это означает: **все клиенты, которые читают `detail` как строку, продолжают работать** без изменений. Клиенты, которые парсят `errors[]`, получают структуру. Никаких breaking changes, форма `HTTPException(detail=dict)` по-прежнему запрещена.

## Отклонённые альтернативы

- **`HTTPException(detail=dict)` с envelope в `detail`** — отклонено: ломает всех потребителей, которые читают `detail` как строку (ADR-0025 §3 уже зафиксировал это).
- **Один `_check_balance_sufficiency(mode="submit"|"cancel")`** — отклонено: режимы семантически разные (submit-расход vs cancel-rollback), объединение усложнит unit-тесты и сломает sensitive area.
- **Локализация текста в `detail` через фронт** — отклонено: пробрасывает ответственность за корректный текст на клиент, ухудшает UX для оффлайн-клиентов.
- **Клиентский precheck остатков** — отклонено: race condition не закрывает, не заменяет server-side reject.
- **`rollback_insufficient_stock` как новый `errors[].code`** — отклонено: размывает семантику `insufficient_stock`, удваивает парсер на фронте, не даёт ничего нового.
- **Расширение на restore-flow в этой итерации** — отклонено: restore не вызывает rollback остатков, его ошибки — только `OperationInWrongStateError` / `RoleNotPermittedError`, для них envelope **уже** работает (handler зарегистрирован на базовый класс). Отдельный TZ не нужен, отдельная итерация для UX-доработки — нужна, но не в этом scope.
- **Корректировки (`corrections_service.py:912`)** — отклонено: отдельный envelope `correction_insufficient_balance` мигрируется по плану ADR-0025 §9 (Этап 2, отдельный TZ).
- **`actor_roles` / `required_permission` в публичном API** — отклонено: то же, что в ADR-0025 (раскрывает внутреннюю модель доступа).

## Последствия

### Положительные

- кладовщик при отмене видит имя ТМЦ, доступный остаток, агрегированные дефициты **с тем же UX**, что и при submit (единая парсерная инфраструктура);
- серверные ошибки cancel-flow проходят через ту же envelope-инфраструктуру, что и submit — единая точка диагностики, единый лог-формат, единый X-Request-Id tracking;
- `errors[].operation_line_ids[]` даёт фронту стабильный ключ для inline-подсветки проблемных строк (если в будущем cancel-flow получит модалку с разбивкой по строкам);
- ADR-0025 §8 скоуп `api_error_response` расширяется **только** на `OperationCancelView` (минимальное расширение), snapshot-инвариант обновляется синхронно;
- существующие клиенты и curl продолжают работать благодаря dual response.

### Отрицательные и риски

- `operations_service.py:2511-2775` — sensitive area (`SyncServer/AGENTS.md`). Любые правки требуют полного pytest-прогона. **Mitigation:** pre-check выделен в отдельный helper, `cancel_operation` меняется минимально (только вставка pre-check + замена 10 f-строк на null/no-op);
- `cancel_operation` ходит через `_apply_balance_delta` (ADR-0025 §5.7: «не модифицируем в этой итерации»). Cancel-flow не должен ломать другие потребители (корректировки). **Mitigation:** pre-check ловит все дефициты до мутаций; `_apply_balance_delta` остаётся как есть;
- `OtherSubmitEndpointsSnapshotTests` (`apps/sync_client/test_api_error_response.py:96-105`) ломается при переводе `OperationCancelView` на `api_error_response`. **Mitigation:** обновление snapshot в одном коммите с правкой, ADR-0025 §8 синхронно обновляется;
- расширение `problem_class` на cancel-flow формально создаёт новый `type` URN. Это не breaking change (URN — opaque identifier, не API contract), но фиксируется явно;
- `_upsert_issued` (`operations_service.py:752-770`) сейчас поднимает `HTTPException(f"issued asset quantity conflict for {error_context}")` при `ValueError` из репозитория. Это **внутри** cancel-flow для ISSUE/ISSUE_RETURN/WRITE_OFF с issue_object. **Mitigation:** pre-check `dict_issued` ловит дефициты **до** `_upsert_issued`; f-строка fallback остаётся для race condition (английский, не envelope) — допустимо, аналогично submit §7;
- `restoreOperation` на фронте (`:490-505`) сейчас идёт через тот же `cancelOperation` сервисный метод. После фикса cancel — restore **автоматически** получит envelope, если backend будет поднимать `OperationSubmitError` (handler общий). Это **побочный положительный эффект**.

### Миграция

- **Этап 1 (этот TZ)**: сервер отдаёт envelope в cancel-flow, Django BFF пробрасывает через `api_error_response`, Angular парсит и отображает. Snapshot-инвариант и ADR-0025 §8 обновляются синхронно.
- **Этап 2 (отдельный TZ, не в этой итерации)**: миграция `corrections_service.py:912` (`correction_insufficient_balance`) на тот же envelope. Полная унификация envelope для всех business-flow.
- **Этап 3 (отдельный TZ)**: restore-flow UX-доработка, модалка cancel-flow с inline-подсветкой строк (опционально).

## Что НЕ делается в этой итерации

- Изменение формы `detail` для submit-flow (только cancel-flow).
- Изменение `_apply_balance_delta` (ADR-0025 §5.7).
- Глобальная миграция BFF на `api_error_response` для всех эндпоинтов.
- Корректировки (`corrections_service.py:912`).
- Restore-flow envelope (он уже работает, но без UX-доработки).
- Acceptance-flow (`POST /operations/{id}/accept_lines` и др.) — out of scope, следующая итерация.
- Клиентский precheck остатков перед cancel.
- Bulk-validate endpoint.
- Оффлайн-клиенты.

## Ссылки

- `docs/adr/0025-operation-submit-domain-errors.md` — базовый envelope.
- `docs/TZ-SYNCSERVER_OPERATION_SUBMIT_DOMAIN_ERRORS.md` — реализация submit envelope (служит образцом для cancel).
- `docs/TZ-FRONTEND_OPERATION_SUBMIT_ERROR_SURFACE.md` — Angular parser/toasts (переиспользуется для cancel).
- `docs/TZ-OPERATION_CANCEL_DOMAIN_ERRORS.md` — реализация этого ADR (syncserver + BFF + frontend).
- `docs/RAG_SEARCH_GUIDE.md` — якоря для семантического поиска.
- `Functional and WorkLogik.md` §6.8, §6.9 — правила проведения и отмены операций.
