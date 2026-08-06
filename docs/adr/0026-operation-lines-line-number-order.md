# ADR-0026 — Гарантированный порядок строк операции по `line_number`

- Status: Accepted
- Date: 2026-08-05
- Deciders: architect, syncserver-lead
- Supersedes: нет
- Source TZ: `docs/TZ-V3.3_OPERATION_LINES_LINE_NUMBER_ORDER.md`
- Source evidence: `prod_working/document_line_order_bug.md`

## Контекст

Production-баг: документы (накладная / акт / acceptance certificate), API-ответы `GET /api/v1/operations/{id}` и детерминированный порядок `StockDeficit.operation_line_ids` в submit-flow возвращают строки операции в порядке **физической вставки в БД** (по `id`), а не в порядке **`line_number`** (бизнес-смысловой порядок).

Подтверждённый инцидент (`prod_working/document_line_order_bug.md`): операция `3ad7a293` (MOVE), 30 строк добавлены пачками `10..18`, затем `1..9`, затем `19..30`; документ отрендерился в порядке `10..18, 1..9, 19..30`. Контрольный прогон всех 30 строк одним POST даёт корректный порядок `1..30`, что подтверждает: порядок определяется физическим `id`, а не `line_number`.

Это нарушает:

- ADR-0025 (Accepted 2026-07-31): `operation_line_ids` в `StockDeficit` должны идти «в порядке `line.line_number` ascending».
- `TZ-SYNCSERVER_OPERATION_SUBMIT_DOMAIN_ERRORS` §5: группы сортируются по первому `line_number`; `deficits` и `issued_deficits` отсортированы по `line_number`.
- `TZ-V3.1I_WAYBILL_PAGINATION_AND_SYNC_HARDENING`: тест `pages[0]["lines"][0]["line_number"] == 1`.
- `TZ-V3.2_CATALOG_CACHE_AND_OPERATION_PERSISTENCE_HARDENING`: SHA-256 hash операции включает «ordered lines (line_number, …)».

Дополнительные manifest points в коде: `document_service.py:535` (`_build_payload`), `document_renderer.py`, API response `OperationResponse` (10 endpoints), `corrections_service.py` (8 точек), `operations_service.py` (10 точек итерации `.lines`).

Constraints БД: во всех трёх таблицах строк (`operation_lines`, `operation_revision_lines`, `operation_correction_lines`) `line_number` NOT NULL, но **UNIQUE на `(parent_id, line_number)` отсутствует** — только `(parent_id, line_uuid)`. Дубликаты `line_number` внутри одного parent теоретически возможны, поэтому сортировка **только по `line_number`** недетерминирована; обязателен tie-breaker.

## Решение

Контракт: **`sort by line_number ascending, then by tie-breaker ascending`**. Tie-breaker — `id` для таблиц с autoincrement PK (`operation_lines`, `operation_correction_lines`); для `operation_revision_lines` колонки `id` нет (PK — `(revision_id, line_uuid)`, миграция 0036), поэтому tie-breaker — `line_uuid` (детерминированный, уникален в рамках revision).

Четыре уровня защиты, каждый самодостаточен (defense-in-depth):

| Уровень | Файл | Механизм |
|---|---|---|
| ORM relationship | `app/models/operation.py` | `order_by=(line_number.asc(), tie-breaker.asc())` на `Operation.lines`, `OperationRevision.lines`, `OperationCorrection.lines` |
| Payload builder | `app/services/document_service.py` | явный `sorted(source_lines, key=(line_number, tie-breaker))` в `_build_payload` — не зависит от ORM |
| Renderer | `app/services/document_renderer.py` | **локальная** отсортированная коллекция (`render_payload = {**payload, "lines": sorted_lines}`), входной `payload` **не мутируется** (защита hash/audit/повторного рендера) |
| **API response (централизованная)** | `app/schemas/operation.py` | `@model_validator(mode="after")` на `OperationResponse` сортирует `self.lines` по `(line_number, id)` — **единственная точка сортировки для всех 10 endpoints** |

Решения по форме:

- Централизация на API-границе через Pydantic `model_validator(mode='after')` — не через ручной `sorted()` в каждом route (10 endpoints) и не через `reload(operation, ["lines"])` (антипаттерн — лишний запрос к БД).
- `OperationListResponse` оборачивает `OperationResponse` — валидатор покрывает и list-endpoint автоматически.
- Отдельных `OperationRevisionResponse` / `OperationCorrectionResponse` в публичном API нет — правила применяются к ним, если появятся.
- Формат API-контракта не меняется: `lines: list[OperationLineResponse]`, без `?sort=line_number`, без новых полей.
- `operations_service.py` и `corrections_service.py` **не рефакторятся**: их итерации `.lines` не влияют на бизнес-контракт (агрегации, lookups, condition checks) и автоматически стабилизируются ORM `order_by`.
- Миграций БД нет, схема не меняется; пересчёт `line_number` существующих операций и UNIQUE `(operation_id, line_number)` — отдельный data-quality TZ.

## Последствия

### Положительные

- Все клиенты (Django BFF, Angular, будущий `Warehouse_client_core`) получают единый стабильный порядок строк без клиентской логики.
- Документы и API-ответы соответствуют ADR-0025, TZ-V3.1I, TZ-V3.2 (детерминированный hash).
- Один валидатор на 10 endpoints вместо 10 ручных сортировок.

### Отрицательные / риски

- ORM `order_by` на relationship добавляет сортировку в SQL-запросы загрузки `lines` — одна команда БД, N+1 не возникает (в hot paths уже используется `selectinload`/`joinedload`).
- `model_validator(mode='after')` добавляет O(N log N) на response; N редко >100 — наносекунды, оптимизация не требуется.
- Мутация `self.lines` внутри валидатора не влияет на исходный ORM-объект: `model_validate` всегда создаёт новый объект.
- Дубликаты `line_number` в prod-данных не исправляются этим ADR (tie-breaker стабилизирует вывод); при обнаружении реальных дубликатов — отдельный data-quality audit.

### Compliance

- Канонические требования: `Functional and WorkLogik.md` II.8 («кладовщик создаёт операцию -> добавляет построчно ТМЦ … -> делает подтверждение») — стабильный порядок строк по `line_number` соответствует бизнес-смыслу «построчно».
- ADR-0025, TZ-SYNCSERVER_OPERATION_SUBMIT_DOMAIN_ERRORS §5, TZ-V3.1I, TZ-V3.2 — порядок строк и `operation_line_ids` теперь гарантирован.

### Acceptance

Принятие ADR-0026 (перевод в Accepted) — после прохождения acceptance всех стадий TZ-V3.3 и QA verifier (пункт 10 checklist TZ-V3.3).
