# TZ-SYNCSERVER_OPERATION_SUBMIT_DOMAIN_ERRORS

**Статус:** готово к реализации
**Дата:** 2026-07-31
**Автор:** architect (по запросу пользователя)
**Связанные документы:**
* ADR-0025 — `docs/adr/0025-operation-submit-domain-errors.md`
* Scope — `.agent/SCOPE-operation-submit-domain-errors.md`
* Парный TZ для UI — `docs/TZ-FRONTEND_OPERATION_SUBMIT_ERROR_SURFACE.md`

---

## 0. Execution Checklist

- [x] 0. Контекст verified
- [x] 1. Контекст и подтверждённые факты репозитория
- [x] 2. Цели и не-цели
- [x] 3. Доменные исключения и схемы
- [x] 4. Exception handler и регистрация
- [x] 5. Агрегированная проверка остатков
- [x] 6. Конкурентная защита (усиление)
- [x] 7. Порядок проверок
- [x] 8. Django BFF: pass-through шаблон
- [x] 9. Обратная совместимость
- [x] 10. OpenAPI-схема
- [x] 11. Unit-тесты
- [x] 12. Integration-тесты
- [x] 13. Concurrency-тесты
- [x] 14. Стенд smoke
- [x] 15. Документация
- [x] 16. Final acceptance

## Check Rules

* Архитектор создаёт чек-лист и критерии приёмки.
* Executor проверяет только после реализации и собственного прогона всех применимых уровней тестов.
* Если уровень недоступен — оставить пустым с пометкой «стенд недоступен».
* Перед любым real-stand прогоном — Stand Availability Protocol из `AGENTS.md`.

---

## 1. Подтверждённые факты репозитория

Зафиксированы при разведке 2026-07-31.

### 1.1. Ключ остатка

* Таблица `balances` (`SyncServer/app/models/balance.py:12-33`), составной PK `(site_id, inventory_subject_id)`.
* Поле `qty: Numeric(18, 3)`, серверный default `0`.
* `item_id` — nullable, заполняется из `inventory_subjects.item_id` при создании строки (`balances_repo.py:42-44`).
* **`unit_id` в таблице `balances` отсутствует.** Единица определяется через JOIN с `Item.unit_id` (`balances_repo.py:97-99`) только для отображения.
* **Ключ агрегации остатков — строго `(site_id, inventory_subject_id)`. `unit_id` не участвует в ключе и не используется для идентификации остатка.** `unit_id` (если есть у строки) возвращается клиенту только как отображаемые данные в `errors[].unit`.
* Агрегировать строки можно только в пределах одного `(site_id, inventory_subject_id)`. Строка с другим `inventory_subject_id` — это другой субъект учёта и другой ключ.

### 1.2. Типы идентификаторов

| Поле | Тип |
| --- | --- |
| `operations.id` | UUID |
| `users.id` | UUID |
| `sites.id` | integer |
| `items.id` | integer |
| `inventory_subjects.id` | integer |
| `operation_lines.id` | BigInteger (autoincrement) |
| `operation_lines.line_uuid` | UUID nullable |
| `operation_lines.inventory_subject_id` | integer nullable |
| `operation_lines.item_id` | integer nullable |
| `operations.version` | integer |
| `units.id` | integer |
| `expected_version` | integer |

Преобразовывать в строку только UUID. Integer и BigInteger остаются как есть.

### 1.3. Конкурентная защита — что уже есть

* `balances_repo.get_for_update` (`balances_repo.py:23-30`) использует `with_for_update()`.
* `operations_repo.get_operation_by_id_for_update` (`operations_repo.py:156-174`) использует `with_for_update()`.
* Optimistic lock через `expected_version` в `operations_repo.py:196-203` (`update_operation`) и `operations_repo.py:240-256` (`submit_operation`).
* `_capture_balance_change` берёт блокировку внутри, не вызывая `update_balance_quantity` (по комментарию в коде — чтобы не было двойной блокировки).
* Транзакция — `routes_operations.py:303` `async with uow:`.

### 1.4. Где формируются текущие submit-ошибки

| Место | Текущий формат | Что нужно |
| --- | --- | --- |
| `operations_service.py:82-96` `_ensure_sufficient_balance` | `HTTPException(409, "insufficient stock for ...: inventory_subject=..., site=..., required=...")` | `InsufficientStockError` |
| `operations_service.py:99-113` `_ensure_sufficient_issued_balance` | то же для issued balance | `InsufficientIssuedBalanceError` |
| `operations_service.py:1650-1807` индивидуальные ветки для WRITE_OFF/ADJUSTMENT/MOVE/ISSUE | вызывают `_ensure_sufficient_balance` через `_apply_balance_delta` или напрямую | доменные исключения + агрегация |
| `operations_repo.py:196-212` `update_operation` (старая версия) | `HTTPException(409, {code, message, current_version})` | `StaleVersionError` (новый envelope) |
| `operations_repo.py:240-260` `submit_operation` (старая версия) | то же | `StaleVersionError` |
| `operations_workflow_policy.py:31-36` `require_draft_for_submit` | `HTTPException(409, "operation is already {status}")` | `OperationInWrongStateError` |
| `operations_workflow_policy.py:10-12` `require_exists` | `HTTPException(404, "operation not found")` | `OperationNotFoundError` |
| `operations_policy.py:26-32, 75-116` `require_operate_site`, `require_operation_submit_permission` | `HTTPException(403, "operate permission required" / "user has no submit permission...")` | `RoleNotPermittedError` (отдельный envelope, не submit-flow envelope) |

### 1.5. Где НЕ надо менять

* `OperationsPolicy.require_temporary_item_create`, `require_temporary_item_moderation` — для временных ТМЦ, не submit.
* `OperationsPolicy.require_operation_cancel_permission`, `require_root_for_restore`, `require_cancelled_for_delete` — другие workflow-эндпоинты, не submit.
* `OperationsWorkflowPolicy.require_submitted_for_acceptance`, `require_acceptance_required` и т.д. — acceptance-flow, не submit.
* `access_service_v2.py` — общий доступ, не submit.
* `corrections_service.py:912` — отдельный envelope `correction_insufficient_balance`, миграция вне scope этого TZ.
* `routes_documents.py`, `routes_admin_*`, `routes_temporary_items.py` — не submit.

### 1.6. Django BFF

* `Warehouse_web/apps/sync_client/client.py:124-163` — `_raise_for_response` сохраняет полный payload SyncServer в `exc.payload` (`payload=sanitized`), берёт `str(sanitized.get("detail"))` для `message`.
* `Warehouse_web/apps/catalog/api_views.py:68-69, 80-81, ...` — текущий шаблон `_error(str(exc), "sync_error", status=...)` отбрасывает `exc.payload`.
* `Warehouse_web/apps/bff_api/operations_views.py` — нужен посмотреть актуальный шаблон и заменить.

### 1.7. Правила временных ТМЦ

* `Functional and WorkLogik.md:77` — «теперь это легаси».
* `Functional and WorkLogik.md:80` — «Для новых операций целевой поток больше не должен создавать записи во временной таблице».
* `temporary_item_blocked` **исключён** из этой итерации.

---

## 2. Цели и не-цели

### In scope

1. Доменные исключения для submit-flow.
2. Pydantic/OpenAPI-схемы envelope и `errors[]`.
3. Зарегистрированный exception handler в FastAPI app.
4. Агрегированная проверка остатков: двухфазный алгоритм с глобальной сортировкой ключей балансов (§5).
5. Жёсткий авторитетный порядок проверок в `submit_operation` (§7), включая формализованный шаг взятия блокировки операции.
6. Django BFF: structured proxy `api_error_response` с fallback для submit-endpoint.
7. OpenAPI-схема envelope в `/openapi.json`.
8. Тесты: unit, integration (БД-backed), concurrency с barrier.

### Out of scope

1. Другие ошибки API (auth, validation, 5xx).
2. Корректировки (`corrections_service.py:912`).
3. Acceptance-flow, cancel-flow, restore-flow, delete-flow — у них свой envelope в будущем.
4. Оффлайн-клиенты.
5. Client-side precheck остатков.
6. Bulk-validate endpoint.

---

## 3. Доменные исключения и схемы

### 3.1. Файлы

* `SyncServer/app/services/operation_submit_errors.py` — **новый**, доменные исключения + маппер в envelope.
* `SyncServer/app/schemas/operation_submit_error.py` — **новый**, Pydantic-схемы envelope.
* `SyncServer/app/schemas/__init__.py` — экспорт схем.

### 3.2. Доменные исключения

Базовый класс:

```python
class OperationSubmitError(Exception):
    """Base for all submit-flow domain errors. Carries HTTP status and problem-class."""

    problem_class: str = "operation-submit-rejected"
    http_status: int = 409
```

Подклассы (поля):

* `InsufficientStockError(OperationSubmitError)`:
  * `deficits: list[StockDeficit]`
  * `StockDeficit(stock_site_id, stock_site_name, item_id, item_name, unit_id: int | None, unit_name: str | None, unit_symbol: str | None, required_qty: Decimal, available_qty: Decimal, operation_line_ids: list[int])`
  * `problem_class = "operation-submit-rejected"`
  * `http_status = 409`
* `InsufficientIssuedBalanceError(OperationSubmitError)`:
  * `deficits: list[IssuedStockDeficit]` (то же + `issue_object_id`, `issue_object_name`, нет `stock_site`)
  * `http_status = 409`
* `StaleVersionError(OperationSubmitError)`:
  * `expected_version: int`, `actual_version: int`
  * `http_status = 409`
* `OperationInWrongStateError(OperationSubmitError)`:
  * `current_state: str`, `allowed_states: list[str]`
  * `http_status = 409`
* `OperationNotFoundError(OperationSubmitError)`:
  * `operation_id: UUID`
  * `http_status = 404`
  * `problem_class = "operation-not-found"` (отдельный envelope)
* `RoleNotPermittedError(OperationSubmitError)`:
  * `http_status = 403`
  * `problem_class = "operation-submit-rejected"` (envelope submit-flow, но без `errors[].item`/`stock_site`)

`TemporaryItemBlockedError` **не существует** в этой итерации. См. ADR-0025 §0 — отменённое положение scope.

### 3.3. Pydantic-схемы envelope

Каждый код имеет **отдельную** Pydantic-модель с `Literal[code]`. OpenAPI union отражает реальные обязательные поля, а не разрешает произвольные комбинации.

```python
# schemas/operation_submit_error.py
from typing import Annotated, Literal
from pydantic import BaseModel, Field

class ItemRef(BaseModel):
    id: int
    name: str

class SiteRef(BaseModel):
    id: int
    name: str

class IssueObjectRef(BaseModel):
    id: int
    name: str

class UnitRef(BaseModel):
    id: int
    name: str
    symbol: str

class ProblemErrorScope(BaseModel):
    scope: Literal["operation", "line_group"]

# --- line_group codes (обязательные поля) ---

class InsufficientStockError(ProblemErrorScope):
    code: Literal["insufficient_stock"]
    scope: Literal["line_group"]
    operation_line_ids: list[int]
    item: ItemRef
    stock_site: SiteRef
    required_qty: str                              # Decimal as string
    available_qty: str
    unit: UnitRef | None = None                    # display-only

class InsufficientIssuedBalanceError(ProblemErrorScope):
    code: Literal["insufficient_issued_balance"]
    scope: Literal["line_group"]
    operation_line_ids: list[int]
    item: ItemRef
    issue_object: IssueObjectRef
    required_qty: str
    available_qty: str
    unit: UnitRef | None = None

# --- operation codes (обязательные поля) ---

class StaleVersionError(ProblemErrorScope):
    code: Literal["stale_version"]
    scope: Literal["operation"]
    expected_version: int
    actual_version: int

class OperationInWrongStateError(ProblemErrorScope):
    code: Literal["operation_in_wrong_state"]
    scope: Literal["operation"]
    current_state: str
    allowed_states: list[str]

class RoleNotPermittedError(ProblemErrorScope):
    code: Literal["role_not_permitted"]
    scope: Literal["operation"]

class OperationNotFoundError(ProblemErrorScope):
    code: Literal["operation_not_found"]
    scope: Literal["operation"]

# --- envelope ---

ProblemError = Annotated[
    InsufficientStockError
    | InsufficientIssuedBalanceError
    | StaleVersionError
    | OperationInWrongStateError
    | RoleNotPermittedError
    | OperationNotFoundError,
    Field(discriminator="code"),
]

class ProblemEnvelope(BaseModel):
    type: str                                  # "urn:warehouse:problem:<class>"
    title: str
    status: int
    code: str                                  # верхнеуровневый
    detail: str                                # строка для legacy
    instance: str | None = None
    trace_id: str | None = None
    errors: list[ProblemError] = Field(default_factory=list)
```

Обязательные поля по кодам:

| Код | Обязательные |
| --- | --- |
| `insufficient_stock` | `operation_line_ids`, `item`, `stock_site`, `required_qty`, `available_qty` |
| `insufficient_issued_balance` | `operation_line_ids`, `item`, `issue_object`, `required_qty`, `available_qty` |
| `stale_version` | `expected_version`, `actual_version` |
| `operation_in_wrong_state` | `current_state`, `allowed_states` |
| `role_not_permitted` | только `code`, `scope` |
| `operation_not_found` | только `code`, `scope` |

`unit` остаётся optional display-only. `errors: []` допустим только для технического fallback (см. §8.2).

### 3.4. Детерминированный порядок `errors[]`

Сортируется по позиции первой строки соответствующей группы в операции (`line_number` первой строки группы ascending). Не зависит от порядка блокировок (`sorted_keys`) или ответа БД. Это стабильно для тестов и фокуса.

---

## 4. Exception handler

### 4.1. Регистрация

Файл: `SyncServer/app/api/exceptions_handlers.py` (**новый**).
Регистрация в `SyncServer/app/main.py` (или эквивалентном `create_app`) через `app.add_exception_handler(OperationSubmitError, ...)`.

### 4.2. Маппинг

```python
async def operation_submit_error_handler(request: Request, exc: OperationSubmitError):
    envelope = exc.to_envelope(
        instance=str(request.url.path),
        trace_id=request.headers.get("X-Request-Id"),
    )
    return JSONResponse(
        status_code=exc.http_status,
        content=envelope.model_dump(exclude_none=True),
    )
```

`exc.to_envelope` собирает `errors[]` по подклассу, добавляет `type`, `title`, `code`, `detail`.

`type` строится как `f"urn:warehouse:problem:{exc.problem_class}"`.

`trace_id` берётся из заголовка `X-Request-Id` запроса (если есть). Никакой отдельной middleware не пишем.

### 4.3. Что НЕ маппится этим handler

* `HTTPException` других эндпоинтов — стандартный FastAPI handler.
* `ValueError` из `asset_registers_repo.upsert_pending` (строки 109, 126, 150, 167, 188, 202) — это уже сейчас ловится и превращается в `HTTPException(409, ...)` в `operations_service.py:230-234`. **Оставляем как есть**, поскольку это не submit-flow envelope. Эти ошибки попадают в detail как сейчас.
* `IntegrityError`, `SQLAlchemyError` — стандартный 500-handler.

---

## 5. Агрегированная проверка остатков

### 5.1. Алгоритм — двухфазный

**Фаза 1. Сбор расходующих эффектов.**

Один проход по строкам операции (упорядоченным по `line_number` ascending). Для каждой строки определяется:

* реальный эффект — уменьшение warehouse balance или уменьшение issued balance;
* ключ баланса — `(site_id, inventory_subject_id)` для warehouse, `(issue_object_id, inventory_subject_id)` для issued;
* `required_qty = Decimal(line.qty)` (для ADJUSTMENT: только если `qty < 0`; положительные ADJUSTMENT не идут в проверку).

Строки, не уменьшающие баланс (RECEIVE, ADJUSTMENT с `qty > 0`, и т.п.), **не участвуют** в проверке.

Результат фазы 1: `dict[BalanceKey, list[(line, required_qty)]]` — словарь, ключи — уникальные ключи балансов, значения — список строк и их количеств.

**Фаза 2. Блокировка и проверка.**

1. Из `dict` извлекается отсортированный список уникальных ключей `sorted_keys = sorted(dict.keys())`. Сортировка — **глобальная**, детерминированная. Это исключает deadlock при параллельных submit (порядок блокировок одинаков во всех транзакциях).
2. Для каждого ключа `k` из `sorted_keys` ровно один раз вызывается `await uow.balances.get_for_update(k.site_id, k.inventory_subject_id)` (или аналог для issued). Внутри блокировки читается `available_qty`.
3. Суммарный расход по ключу `sum_required = sum(qty for _, qty in dict[k])` сравнивается с `available_qty`. Если `sum_required > available_qty` — формируется запись `StockDeficit` (или `IssuedStockDeficit`):
   * `operation_line_ids` — `[line.id for line, _ in dict[k]]` в порядке `line.line_number`;
   * `required_qty` — `sum_required` (Decimal, сериализуется строкой);
   * `available_qty` — прочитанное внутри блокировки значение.
4. Все `StockDeficit` собираются в `deficits`, `IssuedStockDeficit` — в `issued_deficits`.
5. **Порядок возврата** — `deficits` и `issued_deficits` сортируются по позиции первой строки соответствующей группы в операции (`line_number` первой строки группы). Это независимо от порядка `sorted_keys` (порядок блокировок) и от порядка возврата из БД.
6. Если `deficits` или `issued_deficits` непустые — поднимается **одно** исключение:
   * `InsufficientStockError(deficits=...)` если есть warehouse-дефициты;
   * `InsufficientIssuedBalanceError(deficits=...)` если есть issued-дефициты;
   * если есть и те и другие — первое поднимается по приоритету (warehouse сначала), второе логируется для отладки. В текущей модели операции оба типа одновременно не возникают (RECEIVE/MOVE/WRITE_OFF/ADJUSTMENT/ISSUE используют warehouse; ISSUE_RETURN использует issued).

**Что НЕ делается:**

* `get_for_update` не вызывается на каждую строку — только на уникальный ключ;
* проверка не падает на первой строке с дефицитом;
* порядок возврата не зависит от порядка блокировок или ответа БД.

### 5.2. Пример: две строки одной ТМЦ (60 + 60 при остатке 80)

Операция MOVE с двумя строками:

* строка 1: `inventory_subject_id=100, qty=60`
* строка 2: `inventory_subject_id=100, qty=60`
* остаток warehouse: `(site_id=1, inventory_subject_id=100) = 80`

**Фаза 1.** `dict = {(1, 100): [(line1, 60), (line2, 60)]}` (строки в порядке `line_number`).

**Фаза 2.**

* `sorted_keys = [(1, 100)]`.
* `await get_for_update(1, 100)` → `available_qty = 80`.
* `sum_required = 60 + 60 = 120 > 80` → дефицит.
* `StockDeficit(operation_line_ids=[1, 2], required_qty=Decimal("120.000"), available_qty=Decimal("80.000"))`.

Поднимается одно `InsufficientStockError(deficits=[StockDeficit(...)])`. Кладовщик видит обе строки подсвеченными, текст «На складе: 80, запрошено: 120». Дефицит обнаружен.

### 5.3. Сортировка ключей

Ключ `(site_id, inventory_subject_id)` сортируется как `tuple[int, int]`. Это даёт **глобальный порядок блокировок**:

* `(1, 100)` → `(1, 101)` → `(2, 5)` → …
* Все транзакции, использующие один и тот же ключ, получают блокировки в одном и том же порядке → deadlock невозможен.

Для issued: `(issue_object_id, inventory_subject_id)` — тот же принцип.

### 5.4. Детерминированный порядок `errors[]`

Не зависит от `sorted_keys`:

* группы сортируются по `line_number` **первой строки группы** (ascending);
* `operation_line_ids` внутри группы — по `line_number` (ascending);
* это даёт стабильный порядок для тестов и фокуса.

### 5.5. Имя и единица для deficit

При формировании `StockDeficit`:

* `stock_site_name` — `await uow.sites.get_by_id(site_id).name` (один lookup на уникальный `site_id` в дефицитах; не на каждую строку).
* `item_name` — `await uow.inventory_subjects.get_by_id(inventory_subject_id).item.name` (один lookup на уникальный `inventory_subject_id`).
* `unit_id`, `unit_name`, `unit_symbol` — `await uow.units.get_by_id(item.unit_id)` или join в одном запросе.

Если lookup не сработал (item удалён, временный — legacy), используется `name="(неизвестно)"`, поле не поднимается (`exclude_none`).

### 5.6. Совместимость с issued balance

`ISSUE_RETURN` уменьшает `IssuedAssetBalance`, а не warehouse balance. Алгоритм — тот же двухфазный, с ключом `(issue_object_id, inventory_subject_id)` и итоговым `InsufficientIssuedBalanceError`. Структура `IssuedStockDeficit` аналогична `StockDeficit`.

### 5.7. Что НЕ трогаем

* `_apply_balance_delta` (`operations_service.py:142-207`) — используется другими путями (например, корректировками). **Не модифицируем** в этой итерации.
* `_upsert_pending` (`operations_service.py:209-234`) — это про pending acceptance, не про остатки. Оставляем.
* `corrections_service.py` — отдельный flow.

---

## 6. Конкурентная защита (без изменений в механизме)

### 6.1. Существующие механизмы

В этой итерации **никаких новых блокировок не вводится**. Используются уже существующие:

* row-level lock баланса: `balances_repo.get_for_update` (`balances_repo.py:23-30`) — `with_for_update()`;
* row-level lock операции: `operations_repo.get_operation_by_id_for_update` (`operations_repo.py:156-174`) — `with_for_update()`, вызывается в `submit_operation` репозитория (`operations_repo.py:242`);
* optimistic lock через `expected_version`: `operations_repo.update_operation` (`operations_repo.py:196-203`) и `operations_repo.submit_operation` (`operations_repo.py:240-256`);
* транзакция: `routes_operations.py:303` `async with uow:` — все ошибки приводят к откату.

См. ADR-0025 §0 — отменённое положение scope «ранняя блокировка операции в начале сервиса». Существующая защита достаточна.

### 6.2. Стратегия

* Блокировка операции — пессимистическая (`with_for_update` в `operations_repo.py:161`), берётся **в начале транзакции submit** через `get_operation_by_id_for_update` (см. §7.1 шаг 4). Авторитетные проверки состояния и версии (§7.1 шаги 5-6) выполняются уже по заблокированной операции.
* Блокировка баланса — пессимистическая (`with_for_update` в `balances_repo.py:23`), берётся в фазе 2 алгоритма §5.1 **ровно один раз на уникальный ключ**, до чтения `available_qty`. Ключи берутся в глобальном порядке (§5.3) — это исключает deadlock.
* Версия — optimistic lock поверх пессимистической блокировки операции: после блокировки читаем `operation.version` и сравниваем с `expected_version`. Если не совпало — `StaleVersionError(expected, actual)`. **Проверка состояния выполняется до этой проверки** (state-before-version, см. §7.3).
* Если `expected_version` не передан клиентом — пропускается только этот один optimistic version check. Проверки состояния и прав — **не** пропускаются.

### 6.3. Что НЕ делаем

* `SELECT ... FOR UPDATE NOWAIT`.
* Advisory locks.
* Изменение уровня изоляции транзакций.
* Retry-механизм для клиента.
* Любые новые блокировки поверх существующих.

---

## 7. Порядок проверок

### 7.1. Авторитетный порядок

Внутри транзакции (`async with uow:`) — строго в этом порядке:

1. **Аутентификация** — проверка `X-User-Token` / `X-Device-Token` (выполняется middleware / dependency, до сервиса; здесь не дублируется).
2. **Первичная безопасная загрузка** — `operation = await uow.operations.get_operation_by_id(operation_id)` (без блокировки, read-only). Цель — только авторизация до открытия транзакции с блокировкой, чтобы не давать storekeeper'у блокировать операции, к которым у него нет доступа.
3. **Первичная авторизация** — `OperationsPolicy.require_operation_submit_permission(identity, operation)`, для MOVE — `require_move_access`. Если прав нет → `RoleNotPermittedError` (403) до взятия блокировки.
4. **Внутри транзакции — блокировка операции**: `operation = await uow.operations.get_operation_by_id_for_update(operation_id)`. Это **существующий** метод (`operations_repo.py:156-174`), не новый.
5. **Авторитетная проверка состояния заблокированной операции** — `OperationsWorkflowPolicy.require_draft_for_submit(operation)` → `OperationInWrongStateError` (409), если статус не DRAFT.
6. **Авторитетная проверка версии заблокированной операции** — `if expected_version and int(operation.version) != expected_version: raise StaleVersionError(...)`. Если `expected_version` не передан клиентом — пропускается (только этот один optimistic check). Проверка прав и состояния **не** пропускается.
7. **Авторитетная повторная проверка прав**, если они зависят от изменяемых полей (например, site_id, source_site_id, destination_site_id могли измениться между первичной загрузкой и взятием блокировки). В текущей реализации — `OperationsPolicy` уже валидирует эти поля; повторная проверка = вызов тех же методов на заблокированной операции.
8. **Валидация строк** — материализация временных ТМЦ (`_materialize_deferred_temporary_lines`) и `_validate_resolved_lines_on_submit`.
9. **Группировка и блокировка балансов** — фаза 1 алгоритма §5.1 (сбор расходующих эффектов), затем фаза 2 (сортировка ключей, `get_for_update` для каждого ключа, проверка суммарного расхода).
10. Если есть дефициты — **одно** исключение `InsufficientStockError` / `InsufficientIssuedBalanceError` (409). Submit прерывается.
11. **Проведение** — `_capture_balance_change` (без `_ensure_sufficient_balance`, поскольку уже проверили), `submit_operation` репозитория (инкремент версии, статус SUBMITTED), `audit_event` + `audit_item_effects`.

### 7.2. Конкурентная защита — формулировка

**Новая разновидность блокировки не вводится.** Существующий механизм `with_for_update()` переиспользуется, но авторитетные проверки выполняются по заблокированной операции.

* `balances_repo.get_for_update` (`balances_repo.py:23-30`) — row-level lock баланса.
* `operations_repo.get_operation_by_id_for_update` (`operations_repo.py:156-174`) — row-level lock операции.
* Optimistic `expected_version` (`operations_repo.py:196-203, 240-256`) — поверх пессимистической блокировки.

Что меняется в этой итерации — **только**:

* §7.1 — формализованный авторитетный порядок (выше);
* §5 — двухфазная агрегация остатков с глобальной сортировкой ключей.

### 7.3. Семантика повторного submit

* **Submit уже проведённой операции (статус SUBMITTED, ACCEPTED, CANCELLED)** → `OperationInWrongStateError` (409), независимо от наличия `expected_version`. Это инвариант: `expected_version` не отменяет проверку состояния.
* **`stale_version`** возникает только если операция остаётся в DRAFT, но была изменена другим запросом между загрузкой клиентом и submit'ом.
* **Submit без `expected_version`** пропускает только optimistic version check (шаг 6). Проверки состояния (шаг 5) и прав (шаги 3 и 7) — **не** пропускаются.

### 7.4. Когда 403, когда 404

Текущее поведение `OperationsPolicy` (строки 75-116) сохраняется:

* Если пользователь не имеет operate-доступа к `operation.site_id` (и нет `has_global_business_access`) — `RoleNotPermittedError` 403.
* Если пользователь не имеет доступа к чужой операции — 403 (не 404). **Не вводится masking через 404** в этой итерации: это отдельная задача, требующая решения о раскрытии информации и пересмотра всех авторизационных проверок.
* Если операция не существует — 404 (через `OperationsWorkflowPolicy.require_exists`).

---

## 8. Django BFF: structured proxy для submit-flow

### 8.1. Новый helper с fallback

Файл: `Warehouse_web/apps/sync_client/api_error_response.py` (**новый**).

```python
from apps.sync_client.exceptions import SyncServerAPIError

_FALLBACK_TYPE = "urn:warehouse:problem:sync-error"
_FALLBACK_TITLE = "Ошибка взаимодействия с сервером"
_FALLBACK_CODE = "sync_error"
_FALLBACK_STATUS = 502

def api_error_response(exc: SyncServerAPIError):
    """
    Structured proxy for SyncServer errors in submit-flow.

    - If exc.payload is a JSON object/dict, pass it through unchanged.
    - For None, string, list, or any other non-dict payload, return a fallback envelope.
    - HTTP status: exc.status_code if valid (>= 400, <= 599), else 502.
    - Payload already passed through sanitize_payload in client.py; do not re-sanitize.
    """
    if isinstance(exc.payload, dict) and exc.payload:
        status = exc.status_code if 400 <= (exc.status_code or 0) <= 599 else _FALLBACK_STATUS
        return JsonResponse(exc.payload, status=status)

    return JsonResponse(
        {
            "type": _FALLBACK_TYPE,
            "title": _FALLBACK_TITLE,
            "status": _FALLBACK_STATUS,
            "code": _FALLBACK_CODE,
            "detail": str(exc),
            "errors": [],
        },
        status=_FALLBACK_STATUS,
    )
```

### 8.2. Применение — только submit-flow

Заменяем шаблон **только** в одном BFF endpoint:

* `Warehouse_web/apps/bff_api/operations_views.py` — `submit_operation_view`. Текущий код использует `_error(str(exc), "sync_error", status=...)`; заменяем на `api_error_response(exc)`.

### 8.3. Что НЕ трогаем

* `Warehouse_web/apps/catalog/api_views.py` — общий `_error` остаётся (это не submit-flow).
* `Warehouse_web/apps/client/services.py` — общий `_execute` остаётся (это для SSR-flow, не Angular).
* Любые другие BFF endpoints — не трогаем.

### 8.4. Почему отдельный helper, а не изменение `_error`

`_error` используется в catalog (`apps/catalog/api_views.py:68-69, 80-81, 93-94, ...`) и в других доменах. Изменение `_error` задним числом сломало бы контракт всех этих endpoints и потребовало бы миграции всех их клиентов одновременно — за рамками этой итерации. Отдельный `api_error_response` — точечное изменение с минимальной площадью воздействия.

### 8.5. BFF-тесты

Файл: `Warehouse_web/apps/sync_client/test_api_error_response.py` (**новый**).

* `test_dict_payload_passed_through` — `exc.payload = {...}` → ответ содержит тот же dict, HTTP-статус из `exc.status_code`.
* `test_http_status_preserved` — `exc.status_code = 409` → ответ 409; `exc.status_code = None` → 502.
* `test_invalid_status_falls_back_to_502` — `exc.status_code = 200` (невалидный) → 502.
* `test_none_payload_returns_fallback_envelope` — `exc.payload = None` → fallback envelope с `type=urn:warehouse:problem:sync-error`, `code=sync_error`, `errors=[]`.
* `test_string_payload_returns_fallback_envelope` — `exc.payload = "plain text"` → fallback.
* `test_list_payload_returns_fallback_envelope` — `exc.payload = [...]` → fallback.
* `test_other_submit_endpoints_unchanged` — снапшот-тест: список эндпоинтов и их хелперов остаётся прежним, кроме `submit_operation_view`.

### 8.6. Что НЕ делаем

* Не пишем единый `_error` шаблон для всех BFF — расширение scope, отдельный ADR.
* Не модифицируем `sanitize_payload` в `client.py` — он уже работает на уровне всего payload.
* Не добавляем middleware для трассировки — `trace_id` берётся из `X-Request-Id`, если он есть.

---

## 9. Обратная совместимость

### 9.1. Dual response

* `detail` остаётся **строкой** в любом случае.
* Полные машинные данные — в `errors[]`.
* Старый curl или Django SSR видит `detail` и работает.

### 9.2. Формат `detail`

* `insufficient_stock`: «Недостаточно товара: <имя первой проблемной ТМЦ> — запрошено {required}, на складе {available}. Всего проблемных групп: {N}.»
* `insufficient_issued_balance`: «Недостаточно выданного остатка по <имя первой проблемной ТМЦ>.»
* `stale_version`: «Операция была изменена в другой вкладке. Актуальная версия {actual}.»
* `operation_in_wrong_state`: «Операция в статусе «{current_state}», для проведения требуется «{allowed[0]}».»
* `operation_not_found`: «Операция не найдена.»
* `role_not_permitted`: «Недостаточно прав для проведения операции.»

Сокращение или удаление `detail` запрещено без отдельного ADR.

### 9.3. Backward-compat тесты

* `tests/test_syncserver_envelope_compat.py` (**новый**) — submit-ответ содержит `detail` как строку и `errors[]` со всеми ожидаемыми полями.
* Существующие тесты, проверяющие `detail` как строку (`test_stale_balance_conflict.py:160, 207` и аналогичные), обновляются: они проверяют и строку, и структуру `errors[]`. Если `errors[]` отсутствует в старом формате — тест явно фиксирует `expected_format="legacy"`.

---

## 10. OpenAPI-схема

### 10.1. Регистрация

Файл: `SyncServer/app/schemas/operation_submit_error.py` (тот же, что §3.3).
В `routes_operations.py` для `submit_operation`:

```python
@router.post(
    "/{operation_id}/submit",
    response_model=OperationResponse,
    responses={
        403: {"model": ProblemEnvelope, "description": "Role not permitted"},
        404: {"model": ProblemEnvelope, "description": "Operation not found"},
        409: {"model": ProblemEnvelope, "description": "Submit rejected"},
    },
)
```

### 10.2. Версионирование

`type: "urn:warehouse:problem:operation-submit-rejected"` фиксируется как часть API contract. Изменение URN требует новой версии API (за рамками этой итерации).

---

## 11. Unit-тесты

Файл: `SyncServer/tests/test_operation_submit_errors.py` (**новый**).

* `test_envelope_insufficient_stock_serializes_correctly` — проверка всех полей, `required_qty`/`available_qty` как строки, `operation_line_ids` в правильном порядке.
* `test_envelope_stale_version_serializes_correctly`.
* `test_envelope_operation_in_wrong_state_serializes_correctly`.
* `test_envelope_operation_not_found_serializes_correctly`.
* `test_envelope_role_not_permitted_serializes_correctly`.
* `test_envelope_detail_is_string_for_all_codes`.
* `test_envelope_type_is_urn_for_all_codes`.
* `test_envelope_trace_id_from_request_header` — handler берёт `X-Request-Id`.
* `test_envelope_excludes_none_fields` — `unit: None` не попадает в JSON.

---

## 12. Integration-тесты (БД-backed)

Файл: `SyncServer/tests/test_submit_aggregated_deficits.py` (**новый**).

* `test_single_line_insufficient_returns_one_group`.
* `test_multiple_items_insufficient_returns_multiple_groups` — несколько разных `(site_id, inventory_subject_id)`.
* `test_two_lines_same_item_aggregate` — две строки одной ТМЦ, дефицит только по сумме, обе строки в `operation_line_ids`. **Это сценарий из §5.2: 60 + 60 при остатке 80 — обе строки в `operation_line_ids`, `required_qty = "120.000"`, `available_qty = "80.000"`.**
* `test_two_lines_same_item_one_alone_sufficient_aggregate` — две строки одной ТМЦ (например, 90 и 20 при остатке 80), обе в `operation_line_ids`.
* `test_adjustment_positive_does_not_trigger_check` — ADJUSTMENT с `qty > 0` не проходит проверку достаточности (только отрицательные).
* `test_decimal_precision_in_qty` — `Decimal("120.000")` как строка, без `120.00000001`.
* `test_stale_version_returns_envelope` — ожидаемая и фактическая версия.
* `test_operation_in_wrong_state_returns_envelope` — текущее состояние и allowed_states.
* `test_submit_after_submit_returns_operation_in_wrong_state` — успешный submit, второй submit той же операции → `OperationInWrongStateError` (409), **не** `StaleVersionError`. Порядок проверок: state-before-version.
* `test_submit_without_expected_version_still_checks_state` — submit без `expected_version` всё равно проверяет состояние: на SUBMITTED операции получает `OperationInWrongStateError`.
* `test_submit_without_expected_version_skips_version_check_only` — submit без `expected_version` пропускает только optimistic version check; все остальные проверки работают.
* `test_issue_return_insufficient_issued_balance` — отдельный flow для issued.
* `test_role_not_permitted_returns_403_envelope`.
* `test_operation_not_found_returns_404_envelope`.
* `test_legacy_detail_string_still_present_in_envelope`.
* `test_deterministic_order_of_deficits` — `operation_line_ids` и группы в фиксированном порядке независимо от hash seed.
* `test_get_for_update_called_once_per_unique_key` — мокируется `balances_repo.get_for_update`; для двух строк одного ключа — ровно один вызов; для трёх строк двух ключей — ровно два вызова.

Файл: `SyncServer/tests/test_submit_transaction.py` (**новый**).

* `test_submit_rollback_on_insufficient_stock` — после неудачного submit `balances` не изменились, `audit_events` не появилось.
* `test_submit_rollback_on_stale_version` — то же.
* `test_submit_rollback_on_wrong_state` — то же.
* `test_submit_repeated_after_failure_is_safe` — после неудачи второй submit с исправленными данными проходит.

---

## 13. Concurrency-тесты

Файл: `SyncServer/tests/test_submit_concurrency.py` (**новый**).

`asyncio.gather` сам по себе не считается доказательством гонки. Каждый тест использует `asyncio.Event` (barrier) или hook на критической секции, гарантирующий одновременный вход двух транзакций в проверяемую область.

### 13.1. Общий шаблон

```python
async def test_concurrent_*():
    barrier = asyncio.Event()
    hook = AsyncMock(side_effect=lambda *a, **kw: (barrier.set(), await asyncio.sleep(0))[0] or None)

    # мокируем критическую точку (например, get_for_update) так, чтобы она
    # сигналила barrier и ждала вторую транзакцию
    monkeypatch.setattr(uow.balances, "get_for_update", hook)

    async def submit(op_id):
        return await client.post(f"/api/v1/operations/{op_id}/submit", json={...})

    # запускаем обе транзакции; barrier гарантирует, что обе дошли до критической точки
    t1 = asyncio.create_task(submit(op_id_1))
    await barrier.wait()
    t2 = asyncio.create_task(submit(op_id_2))
    r1, r2 = await asyncio.gather(t1, t2)
    assert ...
```

### 13.2. Сценарии

* `test_concurrent_submit_one_wins_one_gets_in_wrong_state` — две параллельные транзакции на одну операцию: первая успешно проводит (DRAFT → SUBMITTED), вторая получает `operation_in_wrong_state` (статус уже не DRAFT). **Не `stale_version`**: порядок проверок state-before-version (§7.1).
  * Проверки: точный HTTP-код (409), точный `errors[0].code == "operation_in_wrong_state"`, финальный статус операции (SUBMITTED), финальные остатки не изменились (т.к. вторая транзакция откатилась), отсутствие частичных `audit_events` (ровно один `operation.submit`).

* `test_concurrent_submit_one_wins_one_gets_stale_version_when_version_changes` — первая транзакция изменяет состояние через `update_operation` (без submit), вторая транзакция submit с предыдущей `expected_version` → `stale_version`. Здесь нет state-конфликта, только version.
  * Проверки: HTTP 409, `errors[0].code == "stale_version"`, `expected_version` / `actual_version` корректны.

* `test_concurrent_submit_one_consumes_balance_other_gets_insufficient_stock` — две разные операции MOVE с одного source, уменьшающие одну и ту же группу `(site_id, inventory_subject_id)`. Первая проходит и уменьшает остаток до 0; вторая получает `insufficient_stock` (через блокировку баланса `with_for_update`).
  * Проверки: HTTP 409, `errors[0].code == "insufficient_stock"`, финальный остаток корректен (не отрицательный), обе операции имеют согласованный `audit_item_effects`.

* `test_concurrent_submit_no_deadlock_with_reversed_line_order` — **deadlock-сценарий**. Две разные операции (A и B) расходуют две одинаковые группы балансов: `(site, item_X)` и `(site, item_Y)`. В операции A строки идут `[item_X, item_Y]`, в операции B — `[item_Y, item_X]`. Без глобальной сортировки ключей — deadlock. С сортировкой — обе проходят, остатки корректны.
  * Проверки: обе операции успешно завершаются (HTTP 200), финальные остатки корректны, нет deadlock (тест завершается в течение разумного timeout, например 5 секунд).

* `test_concurrent_submit_different_operations_different_sites_dont_block` — две операции на разных сайтах не блокируют друг друга (нет общего ключа баланса).

* `test_no_partial_audit_on_concurrent_failure` — при одновременном submit, если один успешен и второй откатывается, в `audit_events` ровно одна запись `operation.submit` от успешной транзакции. Никаких половинчатых записей.

Каждый тест обязан проверить:

* точные HTTP-коды;
* точные `errors[].code`;
* финальный статус операций;
* финальный остаток;
* отсутствие частичных `audit_events` / `audit_item_effects`.

### 13.3. Что НЕ делаем

* Не используем `asyncio.gather` без barrier — это не доказывает гонку, тесты будут flaky.
* Не мокируем всю `submit_operation` — мокируем только критическую точку (`get_for_update` для баланса, `get_operation_by_id_for_update` для операции).

---

## 14. Стенд smoke

После реализации — на dev-стенде (`make up`):

1. `curl -X POST .../api/v1/operations -d '{...}'` — создать draft с одной ТМЦ.
2. Создать ещё один draft с quantity > остатка.
3. `curl -X POST .../api/v1/operations/{id}/submit` — проверить, что envelope содержит:
   * HTTP 409;
   * `detail` — строка с именем ТМЦ;
   * `errors[0].code = "insufficient_stock"`;
   * `errors[0].operation_line_ids = [<integer>]`;
   * `errors[0].item.name` совпадает с именем ТМЦ;
   * `errors[0].required_qty` и `errors[0].available_qty` — строки.
4. Проверить тот же submit через Django BFF — `exc.payload` содержит те же поля, HTTP-ответ 4xx (для доменных ошибок submit ожидается 409) с телом envelope.
5. Проверить legacy curl: `detail` видна как строка, `jq -r .detail` возвращает текст.
6. Открыть `http://localhost:8000/api/v1/openapi.json` — envelope в `responses`.

Если стенд недоступен — `make up`, иначе чекбокс остаётся пустым с пометкой.

---

## 15. Документация

1. Обновить `SyncServer/app/services/operations_service.py` — docstring модуля: «Submit flow uses OperationSubmitError envelope. See ADR-0025.»
2. Обновить `API_MAP.md` — раздел `/operations/{id}/submit` содержит ссылку на envelope и URN.
3. Добавить запись в `CHANGELOG` (если есть) или в `docs/INDEX.md` (если есть changelog-секция).

---

## 16. Критерии приёмки

1. Submit-ответ для всех известных доменных ошибок содержит envelope из §3.3.
2. `detail` остаётся строкой во всех случаях.
3. `type` — URN вида `urn:warehouse:problem:<class>`.
4. `errors[]` содержит хотя бы одну запись для известной доменной ошибки.
5. `errors[].operation_line_ids[]` — массив integer-ов в порядке `line_number`; для ADJUSTMENT с `qty > 0` строки не участвуют в проверке.
6. `required_qty`/`available_qty` — строки.
7. UUID-ы остаются UUID-ами; integer-ы остаются integer-ами (`Number.isSafeInteger` ограничение зафиксировано в ADR-0025 §2.2).
8. При `stale_version` клиент НЕ получает `insufficient_stock` в том же ответе.
9. Агрегированный дефицит для двух строк одного `inventory_subject_id` (например, 60 + 60 при остатке 80) → обе строки в `operation_line_ids`, `required_qty = "120.000"`, `available_qty = "80.000"`. Это сценарий из §5.2, проверяется `test_two_lines_same_item_aggregate`.
10. **`get_for_update` вызывается ровно один раз на уникальный ключ баланса**, не на каждую строку. Проверяется `test_get_for_update_called_once_per_unique_key`.
11. **Порядок проверок state-before-version**: повторный submit проведённой операции → `operation_in_wrong_state`, не `stale_version`. Проверяется `test_submit_after_submit_returns_operation_in_wrong_state`.
12. **Submit без `expected_version`** пропускает только version check; проверки состояния и прав работают. Проверяется `test_submit_without_expected_version_still_checks_state` и `test_submit_without_expected_version_skips_version_check_only`.
13. **Deadlock-сценарий с обратным порядком строк** в двух операциях не вызывает deadlock; обе проходят, остатки корректны. Проверяется `test_concurrent_submit_no_deadlock_with_reversed_line_order`.
14. **Concurrency-тесты** проверяют точные HTTP-коды, `errors[].code`, финальный статус, финальный остаток, отсутствие частичных `audit_events`. Реализованы через `asyncio.Event` (barrier), не через голый `asyncio.gather`.
15. Django BFF: `api_error_response(exc)` для dict-payload пробрасывает `exc.payload` как есть; для non-dict возвращает fallback envelope `urn:warehouse:problem:sync-error`. Применяется **только** в `submit_operation_view`.
16. `tests/test_operation_submit_errors.py`, `tests/test_submit_aggregated_deficits.py`, `tests/test_submit_transaction.py`, `tests/test_submit_concurrency.py`, `apps/sync_client/test_api_error_response.py` — все зелёные.
17. `python -m pytest` (SyncServer), `python manage.py test` (Warehouse_web) — без регрессий.
18. Stand smoke §14 — пройден.

---

## 17. Исполнитель

Стандартный workflow executor: реализация → unit-тесты → integration-тесты → стенд smoke → отчёт с evidence table → commit на `dev` (после зелёных проверок).