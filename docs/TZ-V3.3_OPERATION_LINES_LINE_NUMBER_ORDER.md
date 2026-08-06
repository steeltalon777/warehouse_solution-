# TZ-V3.3: Гарантированный порядок строк операции по `line_number`

## Execution Checklist

- [x] 0. Stage 0 — фактическая разведка перед первым изменением кода (endpoints, constraints, имена relationship)
- [x] 1. Stage A — ORM `order_by` на трёх relationship (`Operation.lines`, `OperationRevision.lines`, `OperationCorrection.lines`)
- [x] 2. Stage B — `document_service._build_payload` сортирует `source_lines` по `line_number` + tie-breaker `id`
- [x] 3. Stage C — `document_renderer` принимает **локальную** отсортированную коллекцию (без мутации `payload`)
- [x] 4. Stage D — централизованная сортировка `OperationResponse.lines` через Pydantic `model_validator(mode='after')` — **единственная точка сортировки для всех API endpoints**
- [x] 5. Static, unit и component-тесты завершены (relationship `order_by`, payload sort, renderer sort, OperationResponse validator)
- [x] 6. DB-backed integration-тесты завершены (`test_create_operation_response_lines_sorted`, `test_update_operation_response_lines_sorted`, `test_get_operation_response_lines_sorted`, `test_submit_deficits_order_after_reverse_patches`, `test_corrections_lines_order`)
- [x] 7. Реальный stand smoke завершён (генерация документа по операции 3ad7a293-style, проверка строк 1..N)
- [x] 8. Regression-проверки существующих тестов (`test_document_service.py`, `test_operation_snapshots.py`, `test_submit_aggregated_deficits.py`, `test_corrections_cancel.py`)
- [x] 9. ADR-0026 создан в статусе **Proposed**; документация (`SyncServer/docs/API_MAP.md`) обновлена
- [x] 10. ADR-0026 переведён в **Accepted** после прохождения acceptance + QA verifier
- [x] 11. Final acceptance review завершён (QA verifier)

## Check Rules

- Архитектор создаёт checklist и acceptance criteria, не отмечает implementation-пункты.
- Executor отмечает stage/check только после реализации и указанной проверки.
- QA verifier отмечает пункт 11 только после проверки Evidence и всех обязательных сценариев.
- Пропущенная или заблокированная проверка остаётся `[ ]` с причиной; unit-тест не заменяет stand или DB integration.
- Изменения checklist выполняются в этом файле; массовое закрытие пунктов «по факту кода» запрещено.
- Без git push и без коммита до явного указания пользователя.
- ADR-0026 создаётся в статусе **Proposed**; перевод в **Accepted** — отдельный пункт checklist, после полного acceptance и QA.

## Metadata

| Поле | Значение |
|---|---|
| Target release | Warehouse 3.3 (patch / hotfix в рамках 3.x) |
| Status | Ready for execution |
| Date | 2026-08-05 (revised 2026-08-05 after API ordering correction) |
| Source evidence | `prod_working/document_line_order_bug.md` (operation `3ad7a293`, MOVE, 30 строк добавлены PATCH'ами в порядке `10–18`, затем `1–9`, затем `19–30`; рендер выдал `10,11,12,13,14,15,16,17,18,1,2,3,4,5,6,7,8,9,19,20,…,30`) |
| Decision authority | ADR-0026 (новый, Proposed → Accepted после acceptance) + согласованность с ADR-0025, TZ-V3.1I, TZ-V3.2, TZ-SYNCSERVER_OPERATION_SUBMIT_DOMAIN_ERRORS |
| Runtime scope | `SyncServer/` только |
| Companion docs | ADR-0026 (Proposed → Accepted), правки в `SyncServer/docs/API_MAP.md` |
| Risk class | Low — ORM-level order + Pydantic validator + локальная сортировка; миграций БД нет |
| Sensitive areas touched | **NONE.** `app/models/operation.py`, `app/services/document_service.py`, `app/services/document_renderer.py`, `app/schemas/operation.py` — все НЕ в списке sensitive (`operations_service.py`, `operations_policy.py`, `uow.py`, `identity_service.py`, `catalog_admin_service.py`, `alembic/versions/`). |

## Executor Handoff

1. **Stage 0 — обязательная разведка перед первым изменением кода.** Без неё не начинать Stage A. См. §3.
2. Начинать со Stage A; не объединять несколько stages одним неделимым коммитом.
3. Перед каждым stage перечитать `SyncServer/AGENTS.md`, проверить ветку `dev`, текущие чужие изменения в nested repository (`git status`).
4. **Централизация сортировки на API границе — обязательна.** Не добавлять ручной `sorted()` в каждом endpoint. Единственная точка сортировки API — Pydantic `model_validator(mode='after')` на `OperationResponse`. Если `OperationRevisionResponse` / `OperationCorrectionResponse` тоже возвращаются клиентам — те же правила.
5. **Tie-breaker обязателен.** Ни в одном месте сортировка не должна быть только по `line_number`. Контракт: `sort by line_number ascending, then by id ascending`. Это защищает от недетерминированного порядка при теоретически возможных дубликатах `line_number`.
6. **Не мутировать входной `payload`** в renderer. Использовать `render_payload = {**payload, "lines": sorted(...)}` или передавать отсортированную коллекцию как локальную переменную.
7. Не менять формат API-контракта: `OperationResponse.lines: list[OperationLineResponse]`, без `?sort=line_number`, без новых полей.
8. После focused tests запускать полный обязательный check `SyncServer/` (`python -m pytest`); только затем отмечать stage checkbox и Evidence.
9. Не коммитить production-токены, секреты и сгенерированный PDF в репозиторий.
10. Не вводить отдельный hotfix только для одного клиента — фикс должен действовать для всех клиентов (Django BFF, Angular, будущий `Warehouse_client_core`).
11. Если на любом stage обнаружится дополнительная manifestation point — обновить scope TZ, не закрывать stage «по факту».

## 0. Goal

Для Warehouse 3.3 устранить production-баг: документы (накладная / акт / acceptance certificate), API-ответы `GET /api/v1/operations/{id}` и детерминированный порядок `StockDeficit.operation_line_ids` в submit-flow возвращают строки операции в порядке **физической вставки в БД** (по `id`), а не в порядке **`line_number`** (бизнес-смысловой порядок).

Это нарушает:

- ADR-0025 (Accepted 2026-07-31): `operation_line_ids` в `StockDeficit` должны идти «в порядке `line.line_number` ascending».
- `TZ-SYNCSERVER_OPERATION_SUBMIT_DOMAIN_ERRORS` §5: группы сортируются по первому `line_number`; `deficits` и `issued_deficits` отсортированы по `line_number`.
- `TZ-V3.1I_WAYBILL_PAGINATION_AND_SYNC_HARDENING`: тест `pages[0]["lines"][0]["line_number"] == 1` требует упорядоченных строк.
- `TZ-V3.2_CATALOG_CACHE_AND_OPERATION_PERSISTENCE_HARDENING`: SHA-256 hash операции включает «ordered lines (line_number, …)».

Релиз сохраняет SyncServer как source of truth, Django как BFF и Angular как presentation layer.

### Confirmed production evidence

Подтверждённый инцидент в `prod_working/document_line_order_bug.md`:

- Операция `3ad7a293`, тип `MOVE`.
- 30 строк добавлены через PATCH в три пачки: сначала `line_number` `10..18`, затем `1..9`, затем `19..30`.
- Документ отрендерился в порядке `10,11,12,13,14,15,16,17,18,1,2,3,4,5,6,7,8,9,19,20,…,30`.
- Контрольный прогон всех 30 строк одним POST даёт корректный порядок `1..30` (один `INSERT` сохраняет id ↔ line_number).

Дополнительные manifest points (см. §3.3) обнаружены в коде: `document_service.py:535`, `corrections_service.py` (8 точек), `operations_service.py` (10 точек итерации `.lines` без сортировки), API response `OperationResponse` (10 точек вызова).

## 1. Scope

### In scope

1. Stage 0 — фактическая разведка перед кодом: реальные endpoints, constraints `line_number`, имена relationship.
2. ORM-level `order_by` на трёх relationship:
   - `Operation.lines` (`SyncServer/app/models/operation.py:216-220`)
   - `OperationRevision.lines` (`SyncServer/app/models/operation.py:~449`)
   - `OperationCorrection.lines` (`SyncServer/app/models/operation.py:~545`)
   - Все — с tie-breaker `id` ascending.
3. Payload builder `document_service._build_payload` (`SyncServer/app/services/document_service.py:535`): явная сортировка `source_lines` по `(line_number, id)` перед построением payload (defense-in-depth, не зависит от ORM).
4. Renderer `document_renderer` (`SyncServer/app/services/document_renderer.py`): передача **локальной** отсортированной коллекции шаблону, без мутации входного `payload`.
5. **API response ordering (централизованная):** Pydantic `@model_validator(mode='after')` на `OperationResponse` (и аналогичных, если применимо) сортирует `self.lines` по `(line_number, id)` ascending. Это единственная точка сортировки API — ручной `sorted()` в routes запрещён.
6. Regression-тесты на каждый manifestation point (см. §5).
7. Обязательные API-тесты: `test_create_operation_response_lines_sorted`, `test_update_operation_response_lines_sorted`, `test_get_operation_response_lines_sorted` (см. §5.2).
8. ADR-0026 (новый) — **Proposed** при создании, **Accepted** после acceptance + QA.
9. Правка в `SyncServer/docs/API_MAP.md` (одна строка в описании `OperationResponse`).

### Out of scope / P2

1. Изменение схемы БД, миграций, типов полей.
2. Изменение HTTP/JSON транспорта, введение `?sort=line_number`, расширение API контракта.
3. Перенос документа-генерации в Django или Angular.
4. Полный рефакторинг `operations_service.py` / `corrections_service.py` (точечные правки вне scope; см. §3.4 — они покрываются defense-in-depth ORM + payload).
5. Audit-log и event-feed (если они итерируют `.lines` — это отдельный TZ).
6. Offline-клиенты (`WarehouseDesktop`, `WarehouseMobile`, `Warehouse_client_core`) — инвариант будет для них автоматически через ORM + API.
7. Замена WeasyPrint / Jinja / любых зависимостей рендера.
8. Пересчёт `line_number` для существующих операций.
9. Добавление UNIQUE constraints на `(operation_id, line_number)` и т.п. — это отдельный data-quality TZ, требует миграции (sensitive area `alembic/versions/`).

## 2. Canonical requirements

> ADR-0025 (Accepted 2026-07-31): «operation_line_ids в `StockDeficit` — `[line.id for line in group]` в порядке `line.line_number` ascending».

> `TZ-SYNCSERVER_OPERATION_SUBMIT_DOMAIN_ERRORS` §5: «groups sorted by first row line_number; deficits and issued_deficits sorted by line_number».

> `TZ-V3.1I_WAYBILL_PAGINATION_AND_SYNC_HARDENING` Stage F-1: «pages[0]["lines"][0]["line_number"] == 1».

> `TZ-V3.2_CATALOG_CACHE_AND_OPERATION_PERSISTENCE_HARDENING` §4.5: «ordered lines (line_number, item_id, quantity, …) включены в SHA-256 hash».

> `Functional and WorkLogik.md`, II.8: «кладовщик создаёт операцию -> добавляет построчно ТМЦ … -> делает подтверждение». Бизнес-смысл «построчно» предполагает стабильный порядок строк, определяемый `line_number`, а не порядком сетевых вызовов.

## 3. Architecture boundaries & Stage 0 preflight

### 3.1. Stage 0 — обязательная разведка перед первым изменением кода

Это **не блокер** для запуска, но обязательная прелюдия Stage A. Исполнитель **не имеет права** писать код до получения следующих подтверждений:

#### 3.1.1. Фактические endpoints, возвращающие `OperationResponse`

По разведке `2026-08-05` (см. `SyncServer/app/api/routes_operations.py`):

| Endpoint | Файл:строка | Возвращает `OperationResponse`? |
|---|---|---|
| `GET /api/v1/operations` (list) | L131 / `routes_operations.py:123-128` | да (`OperationListResponse` оборачивает `OperationResponse`) |
| `GET /api/v1/operations/{id}` | L137-148 | да |
| `POST /api/v1/operations` (create) | L157-172 | да |
| `POST /api/v1/operations/from-source-document` | L181-206 | да |
| `PATCH /api/v1/operations/{id}` (update) | L216-258 | да |
| `PATCH /api/v1/operations/{id}/effective-at` | L268-290 | да |
| `POST /api/v1/operations/{id}/submit` | L308-325 | да |
| `POST /api/v1/operations/{id}/cancel` | L360-382 | да |
| `POST /api/v1/operations/{id}/restore` | L392-403 | да |
| `POST /api/v1/operations/{id}/accept-lines` | L413-441 | да |

Все 10 точек используют один и тот же паттерн: `OperationResponse.model_validate(operation)`. Это делает Pydantic `model_validator` идеальной точкой централизации — без необходимости править routes.

**TODO исполнителя в Stage 0:** обновить таблицу по актуальному состоянию `routes_operations.py` и `docs/adr/0007-core-http-sync-contract.md` (если есть несоответствия — зафиксировать и сообщить архитектору).

#### 3.1.2. Constraints на `line_number`

По разведке `2026-08-05` (см. `SyncServer/alembic/versions/`):

| Таблица | NOT NULL | UNIQUE constraint | Tie-breaker нужен? |
|---|---|---|---|
| `operation_lines.line_number` | да (`0001`: `INTEGER NOT NULL`) | **нет** UNIQUE(operation_id, line_number); только `line_uuid` (миграция 0033) | **да — `id`** |
| `operation_revision_lines.line_number` | да (миграция 0034 L171) | PK `(revision_id, line_uuid)` (миграция 0036), **нет** UNIQUE(revision_id, line_number) | **да — `line_uuid`** ⚠️ (колонки `id` НЕТ) |
| `operation_correction_lines.line_number` | да (миграция 0034 L222) | UNIQUE только `(correction_id, line_uuid)`, **нет** UNIQUE(correction_id, line_number) | **да — `id`** |

**Вывод:** во всех трёх таблицах `line_number` NOT NULL, но дубликаты `line_number` внутри одного parent **технически возможны** (UNIQUE на `(parent_id, line_uuid)` не запрещает два разных UUID с одинаковым `line_number`). Поэтому tie-breaker обязателен везде.

> **⚠️ Расхождение, зафиксированное исполнителем в Stage 0 (2026-08-05):** у `OperationRevisionLine` **нет колонки `id`** — PK `(revision_id, line_uuid)` (миграция 0036, модель `operation.py:461-471`). Tie-breaker для `OperationRevision.lines` — `line_uuid` (детерминированный, уникальный в рамках revision благодаря PK). Для `Operation.lines` и `OperationCorrection.lines` tie-breaker — `id` (BigInteger PK, есть в обеих таблицах). Бизнес-инвариант не меняется: первичный ключ сортировки — `line_number` ascending; tie-breaker только стабилизирует порядок при дубликатах.

**TODO исполнителя в Stage 0:** подтвердить по `SyncServer/alembic/versions/*.py` (sensitive area — только чтение). Если в текущей ветке появились новые UNIQUE constraints — обновить вывод.

**Бизнес-инвариант остаётся:** порядок определяется `line_number` ascending. `id` — только стабилизатор для теоретически возможных повреждённых или legacy-данных.

#### 3.1.3. Реальные имена relationship и наличие `line_number`

По разведке `2026-08-05` (`SyncServer/app/models/operation.py`):

| Модель | Relationship | Поле | Файл:строка |
|---|---|---|---|
| `Operation` | `lines` | `line_number: Mapped[int] = mapped_column(nullable=False)` | `operation.py:299` |
| `OperationRevision` | `lines` | `line_number: Mapped[int] = mapped_column(Integer, nullable=False)` | `operation.py:473` |
| `OperationCorrection` | `lines` | `line_number: Mapped[int] = mapped_column(Integer, nullable=False)` | `operation.py:574` |

> **⚠️ Расхождение (см. §3.1.2):** `OperationRevisionLine` не имеет колонки `id` (PK — `(revision_id, line_uuid)`, `operation.py:461-471`). Tie-breaker для revision lines — `line_uuid`.

**TODO исполнителя в Stage 0:** перед изменением `operation.py` **перечитать строки 200-230, 440-470, 540-580** и сверить с приведённой выше сводкой. Если имена или типы отличаются — остановиться и сообщить архитектору.

#### 3.1.4. `OperationResponse` — текущая реализация

- `SyncServer/app/schemas/operation.py:228` — `class OperationResponse(ORMBaseModel)`.
- `SyncServer/app/schemas/operation.py:264` — `lines: list[OperationLineResponse] = Field(default_factory=list)`.
- `model_validator` отсутствует.
- Все 10 endpoints (см. §3.1.1) вызывают `OperationResponse.model_validate(operation)` — никакой дополнительной обработки.

**Это подтверждает:** централизованная сортировка через `@model_validator(mode='after')` покрывает все endpoints одним изменением.

### 3.2. Границы ответственности по уровням

| Уровень | Файл | Гарантия порядка |
|---|---|---|
| ORM relationship | `SyncServer/app/models/operation.py` | `order_by=(OperationLine.line_number, OperationLine.id)` (или эквивалент для ORM) |
| Payload builder | `SyncServer/app/services/document_service.py` | явный `sorted(source_lines, key=lambda l: (l.line_number, l.id))` |
| Renderer | `SyncServer/app/services/document_renderer.py` | передаёт шаблону **локальную** отсортированную коллекцию; не мутирует `payload` |
| **API response (централизованная)** | `SyncServer/app/schemas/operation.py` | **`@model_validator(mode='after')` на `OperationResponse`** — единственная точка сортировки для всех 10 endpoints |

### 3.3. Manifestation map (post-fix)

| Файл | До фикса | После фикса | Защита |
|---|---|---|---|
| `models/operation.py` `Operation.lines` | по id | по `(line_number, id)` | ORM `order_by` |
| `models/operation.py` `OperationRevision.lines` | по id | по `(line_number, id)` | ORM `order_by` |
| `models/operation.py` `OperationCorrection.lines` | по id | по `(line_number, id)` | ORM `order_by` |
| `services/document_service.py:_build_payload` | по id | по `(line_number, id)` | явный `sorted()` |
| `services/document_renderer.py` `payload["lines"]` | по id | по `(line_number, id)` | **локальная** `sorted()`, без мутации `payload` |
| `schemas/operation.py:OperationResponse` (10 endpoints) | по id (порядок ORM-relationship) | по `(line_number, id)` | **`model_validator`** |
| `operations_service.py:_line_sort_key` (L344) | уже корректно | без изменений | существующая защита |
| `operations_service.py` ×10 (1397, 1680, …) | по id | по id (порядок не критичен) | ORM-плюс защита не требуется для агрегаций |
| `machine_repo.py:656` | уже корректно | без изменений | существующая защита |
| `corrections_service.py` ×8 | по id | по id | через ORM-relationship `OperationCorrection.lines` автоматически |

> Примечание: `operations_service.py` ×10 и `corrections_service.py` ×8 оставлены без явного `sorted()` **намеренно** — порядок в этих местах не влияет на бизнес-контракт (агрегации, lookups, condition checks). Если в будущем аудит выявит, что какой-то из этих путей зависит от порядка — отдельный TZ. ORM `order_by` гарантирует, что relationship iteration всегда стабилен, что достаточно для идемпотентности логики.

## 4. Target contracts

### 4.1. ORM relationship invariant

Каждый relationship строк операции обязан декларировать `order_by` по `(line_number, id)`:

```python
# SyncServer/app/models/operation.py:216-220
lines: Mapped[list["OperationLine"]] = relationship(
    "OperationLine",
    back_populates="operation",
    cascade="all, delete-orphan",
    order_by=(OperationLine.line_number.asc(), OperationLine.id.asc()),  # NEW
)
```

Аналогично для `OperationRevision.lines` (tie-breaker `line_uuid`, т.к. колонки `id` нет — см. §3.1.2) и `OperationCorrection.lines` (tie-breaker `id`).

**Почему tie-breaker обязателен:** см. §3.1.2 — UNIQUE на `(parent_id, line_number)` отсутствует, дубликаты `line_number` теоретически возможны. Без tie-breaker порядок при дубликатах недетерминирован, что нарушает ADR-0025 и идемпотентность submit-flow.

### 4.2. Document payload contract

`document_service._build_payload` (`SyncServer/app/services/document_service.py:535`) обязан возвращать `payload["lines"]` отсортированным по `(line_number, id)` ascending, **независимо** от того, пришёл ли `revision_lines` или `operation.lines`:

```python
# pseudo-diff
source_lines = revision_lines if revision_lines is not None else list(operation.lines)
source_lines = sorted(source_lines, key=lambda line: (line.line_number, line.id))
```

### 4.3. Renderer contract

Renderer (`document_renderer.py`) принимает `payload["lines"]` и **не мутирует входной dict**. Вместо `payload["lines"] = sorted(...)` использовать:

```python
# вариант A — локальная переменная
sorted_lines = sorted(payload.get("lines", []), key=lambda line: (line["line_number"], line["line_number" if False else "id"]))
render_payload = {**payload, "lines": sorted_lines}

# вариант B — sorted копия (только для list)
sorted_lines = sorted(payload["lines"], key=...)
del payload["lines"]  # НЕ делать так; это мутация
```

Допустим любой вариант, который **не оставляет payload в изменённом состоянии** для последующего использования (hash, audit, повторный рендер).

### 4.4. API response contract (централизованная)

`OperationResponse` (`SyncServer/app/schemas/operation.py:228`) получает `@model_validator(mode='after')`:

```python
# pseudo-diff
from pydantic import model_validator

class OperationResponse(ORMBaseModel):
    # ... existing fields ...
    lines: list[OperationLineResponse] = Field(default_factory=list)

    @model_validator(mode="after")
    def _sort_lines_by_line_number(self) -> "OperationResponse":
        self.lines = sorted(self.lines, key=lambda line: (line.line_number, line.id))
        return self
```

**Это единственная точка сортировки для API.** Запрещается:

- добавлять `sorted()` в каждом из 10 endpoints (см. §3.1.1);
- добавлять `sorted()` в каждом месте, где создаётся `OperationResponse`;
- делать `reload(operation, ["lines"])` перед `model_validate` (антипаттерн — лишний запрос к БД).

Если в проекте есть аналогичные response (`OperationRevisionResponse`, `OperationCorrectionResponse`, `OperationListResponse`) — те же правила применяются в этом TZ или в парном TZ, если объём превышает scope.

### 4.5. Контракт на отсутствие мутации payload

Никакой код в этом TZ не имеет права мутировать входной `payload` (или любой другой переданный dict) renderer'а, валидатора или service. Любая сортировка — на копии или на локальной переменной.

## 5. Test ladder

### 5.1. Unit-тесты

| Тест | Цель | Файл |
|---|---|---|
| `test_operation_lines_order_by` | Создать operation, добавить строки в обратном порядке (`line_number` `5,4,3,2,1`), прочитать `operation.lines` — ожидается упорядоченный по `(line_number, id)` | `tests/unit/test_operation_relationship_order.py` (новый) |
| `test_operation_revision_lines_order_by` | То же для `OperationRevision` | там же |
| `test_operation_correction_lines_order_by` | То же для `OperationCorrection` | там же |
| `test_build_payload_lines_sorted_with_tie_break` | Mock `_build_payload` с перемешанными `source_lines` (включая случай дубликата `line_number`) — проверить выход | `tests/unit/test_document_service_payload_order.py` (новый) |
| `test_document_renderer_does_not_mutate_payload` | Передать в renderer payload, после рендера убедиться, что исходный dict не изменён (`lines` в исходном порядке) | `tests/unit/test_document_renderer_order.py` (новый) |
| `test_operation_response_validator_sorts_lines` | Создать `OperationResponse` через `model_validate(operation)` где `operation.lines` в обратном порядке — проверить, что `response.lines` отсортированы по `(line_number, id)` | `tests/unit/test_operation_response_order.py` (новый) |
| `test_operation_response_validator_handles_duplicates` | `operation.lines` содержит две строки с одинаковым `line_number` — проверить, что tie-breaker по `id` стабилизирует порядок | там же |

### 5.2. DB-backed integration-тесты

| Тест | Endpoint | Цель |
|---|---|---|
| `test_create_operation_response_lines_sorted` | `POST /api/v1/operations` (создание через `from-source-document` или сразу с `lines`) | Создать операцию с предзаполненными `lines` в обратном порядке. Проверить, что response содержит `lines` в порядке `(line_number, id)`. |
| `test_update_operation_response_lines_sorted` | `PATCH /api/v1/operations/{id}` (добавление строк) | Создать operation, отправить три PATCH'а в порядке `10..18, 1..9, 19..30`. Проверить, что response содержит `lines` в порядке `1..30`. |
| `test_get_operation_response_lines_sorted` | `GET /api/v1/operations/{id}` | После `test_update_operation_response_lines_sorted` проверить, что GET возвращает `lines` в порядке `1..30`. |
| `test_submit_response_lines_sorted` | `POST /api/v1/operations/{id}/submit` | Аналогично, для submit-flow. |
| `test_patch_reverse_order_then_generate_document` | `POST /api/v1/documents/generate-from-operation` (или внутренний `DocumentService.generate_from_operation`) | После PATCH в обратном порядке — проверить, что `payload["lines"]` отсортирован по `(line_number, id)`. |
| `test_submit_deficits_order_after_reverse_patches` | `POST /api/v1/operations/{id}/submit` (с дефицитом) | Создать operation с дефицитом, отправить строки в обратном порядке через PATCH, submit → проверить, что `StockDeficit.operation_line_ids` идёт по `(line_number, id)` (ADR-0025). |
| `test_corrections_lines_order` | внутренний flow | Создать корректировку, добавить строки через PATCH в обратном порядке → `correction.lines` по `(line_number, id)`. |

Все тесты — в `tests/integration/test_operation_lines_order.py` (новый файл, можно разбить).

### 5.3. Существующие тесты — regression

Файлы, в которых тесты **не должны сломаться**, но будут затронуты:

- `tests/unit/test_document_service.py:54, 327, 330` — должны по-прежнему проходить; добавить assert на порядок.
- `tests/integration/test_operation_snapshots.py:94, 96, 142, 167, 253, 281, 336, 338, 339` — должны проходить без изменений (lines уже добавляются в `line_number` порядке).
- `tests/integration/test_corrections_cancel.py:112, 152` — должны проходить.
- `tests/integration/test_submit_aggregated_deficits.py:571 test_deterministic_order_of_deficits` — должен по-прежнему проходить; **дополнительно** добавить вариант с PATCH в обратном порядке.
- `tests/conftest.py:303` — без изменений.

### 5.4. Stand smoke

1. Запустить стенд (`make up` или `docker compose up -d`).
2. Получить токен root / device, подготовить seed (operation type `MOVE`, site, item, unit).
3. Создать operation через `POST /api/v1/operations` (или через `from-source-document`).
4. Добавить 30 строк тремя `PATCH /api/v1/operations/{id}/lines`: сначала `10..18`, потом `1..9`, потом `19..30`.
5. `GET /api/v1/operations/{id}` → assert `lines[0].line_number == 1`, `lines[29].line_number == 30`.
6. `POST /api/v1/documents/generate-from-operation` → assert `payload["lines"][i].line_number == i+1`.
7. Получить PDF → assert рендер содержит строки `1..30` в этом порядке.
8. **Дополнительно:** повторить шаги 3-5 через `POST /api/v1/operations/from-source-document` (проверить второй endpoint из §3.1.1).

### 5.5. UI automation (Playwright)

Вне scope этого TZ (документ генерируется backend'ом; UI только отображает). Если появится e2e сценарий «черновик → PDF download → визуальная проверка» — отдельный TZ.

## 6. Stages

### Stage 0 — фактическая разведка

**Файлы:** только чтение, без модификаций.

**Что делаем:**

1. Прочитать `SyncServer/app/api/routes_operations.py` целиком. Сверить список endpoints из §3.1.1.
2. Прочитать `SyncServer/alembic/versions/*.py` (sensitive area — только чтение). Сверить constraints из §3.1.2.
3. Прочитать `SyncServer/app/models/operation.py` (200-230, 440-470, 540-580). Сверить имена relationship и поля из §3.1.3.
4. Прочитать `SyncServer/app/schemas/operation.py` (220-280). Сверить состояние `OperationResponse` из §3.1.4.
5. Если расхождений нет — Stage 0 закрыт, исполнитель фиксирует подтверждение в отчёте Evidence.
6. Если есть расхождения — остановиться, обновить §3 в этом TZ, уведомить архитектора.

**Acceptance criteria:**

- Все 4 пункта выполнены.
- Сводка в отчёте исполнителя совпадает с §3.1.1–§3.1.4 (или TZ обновлён).
- Никаких изменений кода не сделано.

### Stage A — ORM `order_by`

**Файлы:** `SyncServer/app/models/operation.py` (только).

**Изменения:**

1. `Operation.lines` → `order_by=(OperationLine.line_number.asc(), OperationLine.id.asc())`.
2. `OperationRevision.lines` → `order_by=(OperationRevisionLine.line_number.asc(), OperationRevisionLine.id.asc())`.
3. `OperationCorrection.lines` → `order_by=(OperationCorrectionLine.line_number.asc(), OperationCorrectionLine.id.asc())`.

**Acceptance criteria:**

- Статический анализ: `python -c "from app.models.operation import Operation; print(Operation.lines.property._order_by)"` показывает корректный tuple из двух `OrderByClause`.
- Unit-тест `test_operation_lines_order_by` (и два аналогичных) проходят.
- Существующие unit-тесты не сломаны.

**Не делаем:** никаких других изменений в `operation.py` (cascade, back_populates, и т.п. — без изменений).

### Stage B — `document_service._build_payload`

**Файлы:** `SyncServer/app/services/document_service.py`.

**Изменения:**

1. В `_build_payload` (~L535) после определения `source_lines` добавить сортировку по `(line_number, id)`.
2. Никаких новых зависимостей.

**Acceptance criteria:**

- Unit-тест `test_build_payload_lines_sorted_with_tie_break` проходит.
- Существующий `tests/unit/test_document_service.py:54, 327, 330` проходит; assert на порядок добавлен.

### Stage C — `document_renderer` defense-in-depth без мутации

**Файлы:** `SyncServer/app/services/document_renderer.py`.

**Изменения:**

1. На входе в функцию рендера (или в начало основной render-функции) создать **локальную** отсортированную коллекцию; не мутировать `payload`.
2. Шаблону передавать либо `render_payload = {**payload, "lines": sorted_lines}`, либо передавать `sorted_lines` как именованный параметр контекста.

**Acceptance criteria:**

- Unit-тест `test_document_renderer_does_not_mutate_payload` проходит: после вызова рендера `payload["lines"]` сохраняет исходный порядок.
- Ручной smoke: документ с payload в обратном порядке рендерится в `1..N`.

### Stage D — централизованная сортировка API response

**Файлы:** `SyncServer/app/schemas/operation.py` (только).

**Изменения:**

1. Добавить `@model_validator(mode='after')` в `OperationResponse`:
   ```python
   @model_validator(mode="after")
   def _sort_lines_by_line_number(self) -> "OperationResponse":
       self.lines = sorted(self.lines, key=lambda line: (line.line_number, line.id))
       return self
   ```
2. Если есть `OperationRevisionResponse` / `OperationCorrectionResponse` / другие аналогичные response с полем `lines` — те же правила (расширение scope Stage D; если их нет — Stage D ограничен одним классом).

**Acceptance criteria:**

- Unit-тест `test_operation_response_validator_sorts_lines` проходит.
- Unit-тест `test_operation_response_validator_handles_duplicates` проходит.
- Integration-тесты `test_create_operation_response_lines_sorted`, `test_update_operation_response_lines_sorted`, `test_get_operation_response_lines_sorted`, `test_submit_response_lines_sorted` проходят.
- Никаких изменений в `routes_operations.py` (централизация через Pydantic, не через routes).
- Все 10 endpoints (см. §3.1.1) проверены: возвращают `lines` в порядке `(line_number, id)`.

**Запрещено:**

- Ручной `sorted()` в каждом из 10 endpoints.
- `reload(operation, ["lines"])` перед `model_validate`.
- Изменение схемы ответа (новые поля, новые query params).

## 7. Stand requirements

Активный стенд — dev (Docker). Агенты используют `make up` / `make down` / `make logs-sync` из корня.

| Сервис | Health Check | Контейнер |
|---|---|---|
| SyncServer API | `GET /api/v1/health` (8000) | `warehouse_syncserver` |
| PostgreSQL | `pg_isready` (5432) | `warehouse_postgres` |
| Warehouse_web (опционально для smoke) | `GET /healthz/` (8001) | `warehouse_web` |

**Stand Availability Protocol** (из `AGENTS.md`) обязателен перед любым DB-backed или stand smoke прогоном.

**Seed данные** — типы операций `MOVE`, `WRITE_OFF`, `INVENTORY_ADJUSTMENT`, `ISSUE`, `INVENTORY_RECEIPT` уже есть в стандартном seed; для теста нужен `MOVE` operation на существующем site с ≥30 items в каталоге.

## 8. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| ORM `order_by` приводит к N+1 на загрузке relationship | Low | В существующих hot paths используется явный `selectinload` / `joinedload`; сортировка на уровне БД через `order_by` SQLAlchemy выполнится одной командой. Дополнительно — проверить `EXPLAIN ANALYZE` на `submit_operation`. |
| `OperationResponse.model_validator` добавляет O(N log N) на каждый response | Negligible | `lines` редко >100; сортировка list в Python — наносекунды. Не требует оптимизации. |
| `model_validator` замедляет `OperationListResponse` (список операций, у каждой свой sort) | Low | Даже для 50 операций × 100 строк — сортировка <1ms. Не требует оптимизации. |
| `model_validator(mode='after')` изменяет `self.lines` — может быть неожиданно для вызывающего кода | Low | Pydantic v2 стандартный паттерн; `model_validate` всегда создаёт новый объект, оригинальный `operation.lines` не затронут. |
| Мутация `payload` в renderer — побочный эффект для hash / audit | Medium (предотвращена §4.3) | Renderer использует `render_payload = {**payload, ...}` или локальную коллекцию. Unit-тест `test_document_renderer_does_not_mutate_payload` фиксирует. |
| Существующие тесты неявно полагались на порядок `id` | Low | Обнаруженные тесты добавляют строки в `line_number` порядке → `id` совпадает с `line_number` → тесты должны проходить. Stage D — integration тесты явно проверят обратный порядок. |
| Дубликаты `line_number` существуют в БД | Low | Tie-breaker `id` обязателен (§3.1.2). Если обнаружатся реальные дубликаты в prod-данных — data-quality audit, не блокирует этот TZ. |
| Performance impact на 100k+ строк операции | Negligible | Операции редко превышают 200 строк. |

## 9. Acceptance criteria (финальные)

Все следующие пункты должны быть `True`:

1. **Stage 0** выполнен: разведка подтвердила endpoints, constraints, relationship из §3.1.
2. ORM relationship `Operation.lines`, `OperationRevision.lines`, `OperationCorrection.lines` декларируют `order_by=(line_number.asc(), id.asc())`.
3. `document_service._build_payload` явно сортирует `source_lines` по `(line_number, id)`.
4. `document_renderer` использует **локальную** отсортированную коллекцию; не мутирует входной `payload`.
5. `OperationResponse` имеет `@model_validator(mode='after')` с сортировкой `self.lines` по `(line_number, id)`. Это **единственная** точка сортировки API.
6. Все 10 endpoints из §3.1.1 проверены: возвращают `lines` в порядке `(line_number, id)`.
7. Integration-тесты `test_create_operation_response_lines_sorted`, `test_update_operation_response_lines_sorted`, `test_get_operation_response_lines_sorted`, `test_submit_response_lines_sorted` проходят.
8. Integration-тест `test_patch_reverse_order_then_generate_document` проходит.
9. Integration-тест `test_submit_deficits_order_after_reverse_patches` проходит (ADR-0025).
10. Unit-тест `test_document_renderer_does_not_mutate_payload` проходит.
11. Stand smoke на 30-строчной операции показывает `lines[0].line_number == 1`, `lines[29].line_number == 30`.
12. `test_submit_aggregated_deficits::test_deterministic_order_of_deficits` и его вариант «PATCH в обратном порядке» проходят.
13. `python -m pytest` в `SyncServer/` зелёный.
14. ADR-0026 создан в статусе **Proposed**.
15. После acceptance всех стадий и QA verifier ADR-0026 переведён в **Accepted**.
16. `SyncServer/docs/API_MAP.md` содержит пометку «строки операции всегда возвращаются в порядке `line_number` ascending, tie-breaker `id`».

## 10. Out of scope (явно)

Это **не** входит в TZ и должно быть отдельным документом, если потребуется:

- Изменение схемы БД, миграции, data-quality исправления (например, добавление UNIQUE на `(operation_id, line_number)`).
- Изменение API контракта (новые query params, новая схема).
- Полный рефакторинг `operations_service.py` / `corrections_service.py`.
- Audit log / event feed.
- Offline clients (`Warehouse_client_core`).
- UI / Angular / Django BFF.

## 11. References

- `prod_working/document_line_order_bug.md` — production evidence.
- `docs/adr/0025-operation-submit-domain-errors.md` — ADR-0025 (Accepted).
- `docs/TZ-SYNCSERVER_OPERATION_SUBMIT_DOMAIN_ERRORS.md` — TZ для submit-flow.
- `docs/TZ-V3.1I_WAYBILL_PAGINATION_AND_SYNC_HARDENING.md` — порядок строк в пагинации.
- `docs/TZ-V3.2_CATALOG_CACHE_AND_OPERATION_PERSISTENCE_HARDENING.md` — ordered lines в hash.
- `Functional and WorkLogik.md` — канонические функциональные требования.
- `SyncServer/app/api/routes_operations.py` — endpoints, возвращающие `OperationResponse`.
- `SyncServer/app/schemas/operation.py` — текущая реализация `OperationResponse`.
- `SyncServer/app/models/operation.py` — relationship, поля `line_number`.
- `SyncServer/alembic/versions/` — constraints `line_number` (только чтение в этом TZ).

---

**Архитектор:** TZ готов к исполнению. Stage 0 — обязательная прелюдия. Stage D — централизованная сортировка на API через Pydantic `model_validator`. Tie-breaker `id` — везде. ADR-0026 — **Proposed** → **Accepted** после acceptance + QA.