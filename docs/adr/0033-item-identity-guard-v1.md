# ADR-0033 — Item Identity Guard v1: предотвращение дублей ТМЦ в каталоге при создании

- **Status:** Accepted
- **Date:** 2026-09-08
- **Deciders:** пользователь, Architect Agent
- **Scope:** SyncServer (основной), Warehouse_web (BFF, аддитивно), Warehouse_frontend (минимально); релиз Quartermaster 4.0
- **Related decisions:** ADR-0012 (inline temporary_item → review flow), ADR-0025 (submit ProblemEnvelope), ADR-0027 (переиспользование `OperationSubmitError`), ADR-0021 (source_document запрещает temporary_item), аудит issue #24 `docs/audit/FINAL_AUDIT_OPERATION_MODAL_IDENTITY_BALANCES_2026-08-18.md` (строка 642: очистка дублей каталога — отдельная data-hygiene задача)

---

## Execution Checklist

- [x] 0. Контекст проверен (файлы/строки из раздела «Контекст» соответствуют текущему `dev`)
- [x] 1. Архитектурные границы подтверждены (ItemIdentityService + repo-метод, без миграций)
- [x] 2. Этап 1: ядро — `item_identity_service.py`, `catalog_repo.find_identity_candidates`, схема и класс `item_identity_duplicate`
- [x] 3. Этап 2: guard на точках входа — materialize (submit), admin create/update, review confirm, legacy approve (flag-only), intra-batch
- [x] 4. Этап 3: read-контракты — `GET /catalog/items/identity-candidates`, поле `identity_candidates` в review-item detail
- [ ] 5. Этап 4: BFF + Angular (pass-through, parser `item_identity_duplicate`, candidates в review detail, warning в inline-модалке) — вне Scope backend-задачи 4.0; не выполнено
- [x] 6. Unit-тесты завершены (классификация, intra-batch, self-exclusion)
- [x] 7. Интеграционные тесты с БД завершены (все точки входа + read-контракты)
- [ ] 8. Stand smoke тесты завершены (SyncServer :8000 — пройдено; Django :8001 — BFF вне объёма backend-задачи)
- [ ] 9. UI automation завершена (`make test-e2e`, Playwright)
- [ ] 10. Пользовательские сценарии завершены (RECEIVE с дублем → block; partial → flag; merge через review)
- [ ] 11. Регрессия завершена (`test_temporary_items_phase1.py`, `test_temporary_items_stage3a.py`, `test_operations_service_inventory_subject_write_path.py` — зелёные)
- [ ] 12. Документация обновлена (этот ADR → Accepted, `Functional and WorkLogik.md` сверка, при необходимости README/ARCHITECTURE)
- [ ] 13. Финальное приёмочное ревью (evidence-таблица проверена)

## Check Rules

- Архитектор создаёт чек-лист и критерии приёмки.
- Исполнитель отмечает пункты реализации и тестов только после выполнения И верификации.
- QA-верификатор отмечает финальную приёмку только после проверки evidence-таблицы.
- Пропущенная проверка остаётся неотмеченной с указанием причины.

---

## Контекст

Все факты ниже подтверждены чтением исходников `dev` на 2026-09-08.

1. **Основной путь дублирования — materialize при submit.**
   `SyncServer/app/services/operations_service.py::_materialize_deferred_temporary_lines` (строки 1960–2044, вызов в submit ~2240, после валидации, до snapshot/балансов): группирует отложенные строки по `client_key` из `temporary_draft_payload` и **безусловно** создаёт `Item(sku, name, normalized_name=normalize_for_storage(name), category_id, unit_id, ..., is_active=True, requires_review=True, review_status="needs_review", source_system="operation_inline", source_ref=client_key)`. Никакого поиска по каталогу нет. Единственный обрабатываемый конфликт — `IntegrityError` на `items_sku_key` → HTTP 409. Результат: каждая RECEIVE-операция с inline-ТМЦ порождает новый Item, даже если идентичный уже существует. Остатки при этом разносятся по разным InventorySubject — отчётность и баланс фрагментируются.

2. **Второй путь (legacy).** `temporary_items_resolution_service.py::approve_as_item` (строки 144–270) создаёт Item из legacy TemporaryItem также без проверки каталога. Поток — только старые записи TemporaryItem (ADR-0012).

3. **Третий путь (admin).** `catalog_admin_service.py::create_item` (264–304) проверяет существование category/unit и уникальность SKU; проверки `normalized_name` нет. `update_item` (313–369) при переименовании пересчитывает `normalized_name`, конфликт проверяет только по SKU.

4. **Модель Item** (`app/models/item.py`): `normalized_name` — nullable, индекс `ix_items_normalized_name` **не unique**; soft-delete (`deleted_at`), merge-цепочка (`merged_into_id`, разрешается в `CatalogReadService._follow_merge_chain`); review-поля `requires_review`, `review_status`; `is_active`.

5. **Нормализация** (`app/core/search_utils.py::normalize_for_storage`): strip → lower → ё→е → пунктуация в пробел → схлопывание пробелов; пусто → None. Эта же функция используется во всех трёх путях создания — значит, точное равенство `normalized_name` является корректным и достаточным identity-ключом **без fuzzy matching**. Точного lookup по `normalized_name` в `catalog_repo.py` сегодня нет (только ILIKE-поиск).

6. **Review-поток** (`review_items_service.py`, `routes_review_items.py`): confirm (с коррекциями name/sku/category/unit/description/hashtags), merge (перенос остатков парными системными ADJUSTMENT-операциями — санкционированный механизм dedup), delete. Все роуты за `OperationsPolicy.require_temporary_item_moderation`.

7. **Контракт ошибок submit** (ADR-0025/0027): `OperationSubmitError`-подклассы → `ProblemEnvelope` `{type: "urn:warehouse:problem:operation-submit-rejected", status: 409, code: "operation_submit_rejected", errors: [...]}`; app-level handler зарегистрирован на базовый класс; `ProblemError` — discriminated union по `code` (`app/schemas/operation_submit_error.py:87`). Django BFF пробрасывает envelope через `api_error_response(exc)` на submit-эндпоинтах; фронтенд имеет парсер.

8. **Функциональные требования** (`Functional and WorkLogik.md`, §IV): inline-создание постоянных ТМЦ со статусом review при submit — обязательный поток (UPD 01.06.2026); merge суммирует остатки (§3.1). Guard не меняет поток, а добавляет проверку перед созданием — отклонения от ФТ не требуется.

9. **Границы задачи.** Ограничения заказчика: без глобального unique constraint, без fuzzy matching, без автоматического merge, без изменения существующих остатков. Существующие дубли в каталоге остаются как есть (forward-only guard); их очистка — отдельная data-hygiene задача (аудит #24, строка 642).

---

## Решение

### 1. Термины и identity-ключ

- **Identity-ключ** = `normalize_for_storage(name)`. Только точное равенство. Никаких edit-distance / токенизационных / семантических сравнений.
- **Alive-кандидат** = Item, у которого `deleted_at IS NULL AND merged_into_id IS NULL`. Удалённые и смерженные записи кандидатами не считаются: их имя освобождено для повторного использования.
- Если `normalize_for_storage(name)` возвращает `None` (пустое имя) — identity-проверка пропускается (пустые имена уже отсекаются существующей валидацией).

### 2. Политика поиска кандидата

Новый repo-метод `CatalogRepository.find_identity_candidates(normalized_name: str, *, exclude_item_id: int | None = None) -> list[Item]`:

```sql
SELECT * FROM items
WHERE normalized_name = :normalized_name
  AND deleted_at IS NULL
  AND merged_into_id IS NULL
  [AND id != :exclude_item_id]
-- selectinload(unit, category) для отображения без N+1
```

Запрос использует существующий индекс `ix_items_normalized_name`, точное равенство, результат — единицы записей.

Классификация кандидатов (в сервисе, не в SQL):

| Tier | Условие (все пункты) | Смысл |
|---|---|---|
| **EXACT** | `unit_id` равен И `category_id` равен И `is_active = True` И `requires_review = False` | Это тот же самый товар; создание дубля недопустимо |
| **PARTIAL** | любой другой alive-кандидат (unit/category отличаются, товар неактивен, либо кандидат сам является review-item) | Возможный дубль; решение принимает человек |

`exclude_item_id` используется для self-exclusion (review confirm, admin rename).

### 3. Матрица поведения

| Результат поиска | Поведение |
|---|---|
| 0 кандидатов | Создать как сегодня (zero behavior change) |
| ≥1 EXACT | **BLOCK**: отказ 409 `item_identity_duplicate` со списком кандидатов; сущность не создаётся |
| только PARTIAL | **CREATE + FLAG**: создать, зафиксировать кандидатов в structured log + в ответе/аудите (не блокируя) |

Принцип: детерминированный дубль блокируется всегда; неоднозначность — никогда не блокирует и никогда не разрешается автоматически (merge остаётся явным человеческим действием через review-поток).

### 4. Размещение бизнес-логики

Новый сервис **`SyncServer/app/services/item_identity_service.py` — `ItemIdentityService`**, единственный владелец политики:

```python
class ItemIdentityService:
    def __init__(self, uow: UnitOfWork): ...

    def find_candidates(self, name: str, *, unit_id: int | None = None,
                        category_id: int | None = None,
                        exclude_item_id: int | None = None) -> IdentityCheckResult:
        """IdentityCheckResult: exact: list[Candidate], partial: list[Candidate]"""

    def assert_can_create(self, name: str, *, unit_id: int | None,
                          category_id: int | None,
                          exclude_item_id: int | None = None) -> IdentityCheckResult:
        """Бросает ItemIdentityConflictError при ≥1 EXACT; иначе возвращает результат (для FLAG)."""
```

Обоснование отдельного сервиса (а не логики внутри catalog service):

- три вызывающих сервиса (`operations_service`, `catalog_admin_service`, `review_items_service`) + legacy (`temporary_items_resolution_service`) получают **одну** политику; правило «одного владельца» исключает дрейф;
- `operations_service.py` — чувствительная зона с минимальным бюджетом изменений: guard должен быть одним вызовом, а не встроенной логикой;
- зависимости ацикличны: `ItemIdentityService → catalog_repo` (репозитории сервисы не импортируют);
- соответствует контракту SyncServer: бизнес-правила в `app/services/`, персистенция в `app/repos/` за UnitOfWork.

Вызывающие сервисы получают guard как одну строку: `result = identity.assert_can_create(...)` и сами решают, как упаковать ошибку в свой HTTP-контракт (см. §5).

Внутренняя ошибка сервиса — `ItemIdentityConflictError(Exception)` с полями `requested_name`, `candidates` — не HTTP-специфична; каждый вход транслирует её в свой контракт.

### 5. Контракты точек входа

#### 5.1 RECEIVE inline temporary_item — materialize при submit (основной контракт)

**Проверка выполняется ДО создания каких-либо Item** (pre-check всех client_key-групп одним проходом), поэтому при блокировке:

- ни один Item/InventorySubject не создан,
- `temporary_draft_payload` остаётся **неочищенным**,
- операция остаётся в статусе draft, транзакция откатывается целиком,
- пользователь может исправить строки (переиспользовать существующий товар или изменить имя) и провести повторно.

Новый подкласс в `operation_submit_errors.py`:

```python
class ItemIdentityDuplicateError(OperationSubmitError):
    # problem_class = "operation-submit-rejected" (дефолт), http_status = 409
    def __init__(self, conflicts: list[IdentityConflict]) -> None: ...
```

Новая схема в `schemas/operation_submit_error.py` (добавляется в `ProblemError` union):

```python
class IdentityCandidateRef(BaseModel):
    id: int
    name: str
    sku: str | None = None
    unit: UnitRef | None = None        # display-only
    category: CategoryRef | None = None  # {id, name}
    match: Literal["exact", "partial"]

class ItemIdentityDuplicateError(ProblemErrorScope):
    code: Literal["item_identity_duplicate"]
    scope: Literal["line_group"]
    operation_line_ids: list[int]
    requested_name: str
    candidates: list[IdentityCandidateRef]
```

Пример envelope (существующий app-level handler ADR-0025, роуты не меняются):

```json
{
  "type": "urn:warehouse:problem:operation-submit-rejected",
  "title": "Операция не может быть проведена",
  "status": 409,
  "code": "operation_submit_rejected",
  "detail": "Товар «Болт М8» уже существует в каталоге (id=42). Используйте существующий товар или измените наименование.",
  "trace_id": "...",
  "errors": [
    {
      "code": "item_identity_duplicate",
      "scope": "line_group",
      "operation_line_ids": [17, 18],
      "requested_name": "Болт М8",
      "candidates": [
        {"id": 42, "name": "Болт М8", "sku": "BOLT-M8",
         "unit": {"id": 3, "name": "Штука", "symbol": "шт"},
         "category": {"id": 7, "name": "Крепёж"},
         "match": "exact"}
      ]
    }
  ]
}
```

FLAG-ветка (только PARTIAL): materialize выполняется как сегодня, дополнительно — structured log `item_identity.flag` (created item id + candidate ids). На materialize-пути в v1 флаг фиксируется **только** логом: новых audit-событий и изменений audit-контекста submit нет (кандидаты доступны live через §5.5 и review detail).

#### 5.2 Review confirm («approve temporary_item» в терминологии 4.0)

`ReviewItemsService.confirm_review_item`: identity-проверка выполняется **после применения коррекций** (по финальным значениям name/unit/category), с `exclude_item_id = item_id` (self-exclusion).

- ≥1 EXACT → **BLOCK**: HTTP 409, структурированный detail (конвенция `HTTPException(detail={...})`, как в `operations_repo`/`corrections_service`):

```json
{
  "code": "item_identity_duplicate",
  "message": "Товар с таким наименованием, единицей измерения и категорией уже существует. Подтверждение отклонено — используйте слияние (merge).",
  "candidates": [ {"id": 42, "name": "Болт М8", "match": "exact", "...": "..."} ]
}
```

- только PARTIAL → подтвердить + FLAG (кандидаты в changes audit-события `review_item.confirm`).
- 0 → подтвердить как сегодня.

Конфликт не блокирует dedup: ревьюеру прямо предлагается существующий механизм `POST /review-items/{id}/merge`.

#### 5.3 Admin create / rename

`catalog_admin_service.create_item`: после валидаций category/unit/SKU — `assert_can_create(name, unit_id=..., category_id=...)`; при EXACT → HTTP 409 с тем же detail-форматом, что в §5.2 (code `item_identity_duplicate`, candidates). Кандидаты при FLAG добавляются в changes audit-события `item.create`.

`catalog_admin_service.update_item` (переименование): та же проверка с `exclude_item_id = item.id`; блокирует rename в имя, идентичное другому alive-товару. Это тот же механизм дублирования, стоимость добавления минимальна — включено в v1.

#### 5.4 Legacy resolve (`approve_as_item`) — flag-only в 4.0

`temporary_items_resolution_service.approve_as_item`: вызов `find_candidates` + structured log `item_identity.flag` при любых кандидатах; **без блокировки**. Обоснование: legacy-поток обслуживает только старые записи и предназначен к отмиранию (ADR-0012); риск регрессии от блокировки выше ценности. Решение о hard guard — в 4.1 по фактической статистике логов.

#### 5.5 Read-контракт ранней обратной связи

Новый эндпоинт в `routes_catalog.py` (prefix `/catalog`, доступ `_require_catalog_read_access`):

```
GET /api/v1/catalog/items/identity-candidates?name=<str>&unit_id=<int?>&category_id=<int?>
```

```json
{
  "candidates": [
    {"id": 42, "name": "Болт М8", "sku": "BOLT-M8",
     "unit": {"id": 3, "name": "Штука", "symbol": "шт"},
     "category": {"id": 7, "name": "Крепёж"},
     "is_active": true, "requires_review": false,
     "match": "exact"}
  ]
}
```

Правила: `name` обязателен (min length 1 после strip); `unit_id`/`category_id` опциональны — tier считается EXACT только если все identity-параметры переданы и равны; параметр missing трактуется как «неизвестно» и понижает tier до PARTIAL. Пустая строка нормализации → `{"candidates": []}`.

Дополнительно: в response `GET /api/v1/review-items/{id}` добавляется поле `identity_candidates` (тот же формат, self-excluded, live-вычисление). Поле аддитивное — старые клиенты его игнорируют.

### 6. Intra-batch guard (граница одной операции)

Две разные `client_key` в одном submit, чьи имена нормализуются одинаково, — это создание дубля внутри одной транзакции. Правило v1: **BLOCK независимо от unit/category**, ошибка `item_identity_duplicate` содержит обе line-группы (в `candidates` — ссылка на внутриоперационный конфликт: `"candidates": []` + `detail` поясняет, что дубль возник между строками операции; клиент исправляет переиспользованием одного `client_key` или различением имён).

Обоснование строгости: автор операции тривиально исправляет конфликт на месте (механизм `client_key`-группировки уже существует), а «флаг и два review-item с одним именем» загрязняет очередь ревью. Реализация: pre-check группирует payload'ы по `normalized_name` до обращения к БД; совпадение ≥2 групп — конфликт.

### 7. BFF и фронтенд (минимальный объём 4.0)

**Warehouse_web (Django BFF)** — только аддитивный pass-through:

1. прокси `GET /catalog/items/identity-candidates` (Angular не имеет права звать SyncServer напрямую);
2. поле `identity_candidates` в прокси review-item detail — без трансформации;
3. submit-эндпоинты уже пробрасывают ProblemEnvelope (`api_error_response`) — изменений не требуется;
4. admin-create/review-confirm прокси должны пробрасывать структурированный 409 detail без уплощения (проверить конкретные view; при необходимости точечная правка по образцу `api_error_response`).

**Warehouse_frontend (Angular)** — три минимальных изменения:

1. парсер submit-ошибок узнаёт код `item_identity_duplicate` и рендерит его в существующей поверхности ошибок проведения (строки + имя + кандидаты);
2. review-item detail: список `identity_candidates` + CTA «Слить с существующим» (переход к merge-диалогу с предзаполненным target);
3. inline-модалка temporary_item: на blur поля name (когда unit/category выбраны) — неблокирующий warning со списком кандидатов и действием «Использовать существующий» (заменяет payload строки на `item_id`; существующая валидация дублей строк issue #24 отрабатывает штатно).

Пункт 3 — профилактический UX; пункты 1–2 обязательны, пункт 3 может быть отгружен отдельным инкрементом внутри 4.0 без блокировки backend-релиза.

### 8. Данные и миграции

- **Миграций нет.** Никаких новых таблиц, колонок, индексов, constraint'ов.
- Существующие дубли не трогаются; остатки не пересчитываются. Guard — forward-only.
- Кандидаты нигде не персистятся: вычисляются live при каждом обращении (источник истины — сама таблица `items`).

### 9. Наблюдаемость

- Structured log: `item_identity.block` (точка входа, запрошенное имя, candidate ids, line ids / item id) и `item_identity.flag` (аналогично). Логи дают материал для решения о legacy hard guard и о масштабировании политики в 4.1.
- Audit: кандидаты при FLAG попадают в `changes` существующих событий (`item.create`, `review_item.confirm`); новых типов событий нет.

---

## Минимальный объём 4.0

| # | Изменение | Файл(ы) | Тип |
|---|---|---|---|
| 1 | `ItemIdentityService` + `IdentityCheckResult` + `ItemIdentityConflictError` | `SyncServer/app/services/item_identity_service.py` | новый |
| 2 | `find_identity_candidates` | `SyncServer/app/repos/catalog_repo.py` | метод |
| 3 | Схема `item_identity_duplicate` + union | `SyncServer/app/schemas/operation_submit_error.py` | аддитивно |
| 4 | `ItemIdentityDuplicateError` | `SyncServer/app/services/operation_submit_errors.py` | аддитивно |
| 5 | Pre-check guard в materialize + intra-batch | `SyncServer/app/services/operations_service.py` | точечно |
| 6 | Guard create/rename | `SyncServer/app/services/catalog_admin_service.py` | точечно |
| 7 | Guard confirm | `SyncServer/app/services/review_items_service.py` | точечно |
| 8 | Flag-only legacy approve | `SyncServer/app/services/temporary_items_resolution_service.py` | точечно |
| 9 | `GET /catalog/items/identity-candidates` | `SyncServer/app/api/routes_catalog.py` | новый роут |
| 10 | `identity_candidates` в review detail | `SyncServer/app/api/routes_review_items.py` | аддитивно |
| 11 | BFF pass-through (proxy + detail-поле + 409 detail) | `Warehouse_web/apps/sync_client/`, соответствующие views | аддитивно |
| 12 | Angular: parser + review detail candidates (+ modal warning) | `Warehouse_frontend` | аддитивно |
| 13 | Тесты (см. Test Ladder) | `SyncServer/tests/` | новые |

## Вынесено в 4.1

1. **Hard guard legacy `approve_as_item`** — решение по логам `item_identity.flag` за период; legacy-поток отмирает (ADR-0012), возможно guard не понадобится вовсе.
2. **Import/machine-потоки** (`import_batch_id`, `machine_last_batch_id`): у импорта собственная семантика batch-обновления; guard требует отдельного дизайна (аудит #24, строка 632: место — общий слой материализации строк).
3. **Персистентный реестр дублей и отчёты**: дашборд-метрика «дубли созданные/заблокированные», bulk-dedupe инструментарий над существующим merge.
4. **Warning в draft create/update ответах** (per-client_key, неблокирующий) — ранняя обратная связь v2; в 4.0 покрыта read-эндпоинтом §5.5.
5. **Исследование partial unique index** (`WHERE deleted_at IS NULL AND merged_into_id IS NULL`) — возможно только после data-hygiene очистки существующих дублей; в v1 запрещено ограничением заказчика.

---

## Execution Strategy

- **🟡 Sequential**
- **Reason:** все ключевые правки — в чувствительных файлах SyncServer (`operations_service.py`, `catalog_admin_service.py` — прямые sensitive areas по AGENTS.md); контракт ошибки и read-эндпоинт должны быть заморожены до начала BFF/Angular-работ; миграций нет, но этапы 1–3 имеют жёсткую последовательную зависимость (ядро → guard'ы → read-контракты). Объём мал для распараллеливания.
- **Допущение:** на этапе 4 возможно до 2 потоков (BFF и Angular) после заморозки контрактов этапа 3; Angular-пункт 3 (§7) — независимо отгружаемый инкремент.
- **Порядок интеграции/тестов:** SyncServer unit → SyncServer integration (БД) → регрессия temporary_items → BFF pass-through тесты → stand smoke → Playwright E2E.

## Test Ladder

| Уровень | Применимость | Проверки |
|---|---|---|
| 1. Static | да | SyncServer: штатный линтер/тайп-чек репозитория; Angular: `npm run build` (компиляция) |
| 2. Unit | да | `ItemIdentityService`: классификация EXACT/PARTIAL/none; self-exclusion; deleted/merged не кандидаты; name→None skip; intra-batch группировка |
| 3. Component/Integration (БД) | да | submit RECEIVE: EXACT → 409 envelope `item_identity_duplicate`, draft intact, payload не очищен, Item не создан; PARTIAL → создан review-item + log; 0 → без изменений; intra-batch → 409 обе группы; admin create/rename → 409 + candidates; review confirm: EXACT после коррекций → 409, PARTIAL → confirmed + flag; legacy approve → создан + flag; `GET identity-candidates` (все ветви tier-правил); review detail содержит `identity_candidates` |
| 4. Integration (BFF) | да | `python manage.py test`: proxy candidates, pass-through 409 detail без уплощения, поле в review detail |
| 5. Stand smoke | да | на стенде (:8000/:8001): создать товар через admin → RECEIVE с тем же именем → 409 envelope; partial-кейс → review-item создан; `curl` на candidates-эндпоинт через BFF |
| 6. UI automation | да | `make test-e2e` (Playwright): submit-дубль показывает ошибку с именем и кандидатом; review detail показывает кандидатов; (при отгрузке §7.3) modal warning |
| 7. User scenarios | да | полный цикл: RECEIVE inline дубль → отказ → замена на существующий товар → проведение; RECEIVE partial → review → merge; admin rename в дубль → отказ |
| 8. Regression | да | `python -m pytest` целиком; обязательно зелёные: `test_temporary_items_phase1.py`, `test_temporary_items_stage3a.py`, `test_operations_service_inventory_subject_write_path.py`, `test_search_utils.py` |
| 9. Acceptance | да | evidence-таблица по шаблону TZ-workflow |

**Стенд:** Docker dev-стенд (`make up` из корня workspace): SyncServer :8000 (`GET /api/v1/health`), Django :8001 (`GET /healthz/`), PostgreSQL :5432, Angular :4200. Seed: пользователь с правом temporary_item_moderation, категория, единица измерения, один существующий активный товар (для EXACT-кейса) и один неактивный/иной категории (для PARTIAL). Переменные окружения — только имена (`SYNC_SERVER_URL`, `SYNC_ROOT_USER_TOKEN`, `DATABASE_URL`, ...), значения не документировать. Сброс: `make restart`; данные тестового стенда — пересоздание операций/товаров через API.

## Acceptance Criteria

- **AC-1.** Submit RECEIVE-операции, чей inline temporary_item нормализуется идентично alive-товару с совпадающими `unit_id`, `category_id`, `is_active=True`, `requires_review=False`, отклоняется: HTTP 409, ProblemEnvelope `operation-submit-rejected`, в `errors[]` код `item_identity_duplicate`, `scope=line_group`, `operation_line_ids` затронутых строк, `requested_name`, `candidates[]` с id/name/unit/category. Новый Item не создан, InventorySubject не создан, `temporary_draft_payload` сохранён, операция в draft.
- **AC-2.** Submit с кандидатом только PARTIAL (другая unit или category, неактивный товар, либо кандидат — pending review-item) проходит штатно: review-item создаётся, остаётся в очереди; факт зафиксирован в structured log `item_identity.flag` с ids.
- **AC-3.** Submit без совпадений не меняет текущего поведения (регрессия: `test_temporary_items_phase1.py` зелёный без модификаций, кроме новых тестов).
- **AC-4.** Один submit с двумя разными `client_key`, чьи имена нормализуются одинаково, отклоняется `item_identity_duplicate` независимо от unit/category; в ошибке видны обе группы строк.
- **AC-5.** Deleted (`deleted_at IS NOT NULL`) и merged (`merged_into_id IS NOT NULL`) товары кандидатами не являются: создание с их именем разрешено.
- **AC-6.** `POST /review-items/{id}/confirm` с коррекциями, приводящими к EXACT-совпадению с другим alive-товаром (self исключён), отклоняется 409 `item_identity_duplicate` со структурированным detail и списком кандидатов; review_status не меняется. PARTIAL → подтверждение с флагом в audit changes.
- **AC-7.** `create_item` (admin) с EXACT-совпадением отклоняется 409 `item_identity_duplicate` + candidates; `update_item` rename в EXACT-совпадение другого товара (self исключён) отклоняется так же; SKU-конфликт продолжает работать как раньше.
- **AC-8.** Legacy `approve_as_item` не блокируется ни при каких кандидатах; при наличии кандидатов пишется `item_identity.flag`.
- **AC-9.** `GET /api/v1/catalog/items/identity-candidates?name=...` возвращает живой список alive-кандидатов с tier-классификацией по правилам §5.5; без авторизации/прав catalog-read — штатный 401/403; пустая или whitespace-only `name` → HTTP 200 с `{"candidates": []}` (детерминированно, без 422-ветки).
- **AC-10.** `GET /api/v1/review-items/{id}` содержит поле `identity_candidates` (self-excluded); существующие потребители не сломаны (поле аддитивное).
- **AC-11.** Django BFF: proxy candidates-эндпоинта работает из браузера; структурированный 409 detail admin-create/confirm и submit-envelope пробрасываются на фронтенд без уплощения.
- **AC-12.** Angular: ошибка проведения с кодом `item_identity_duplicate` отображается в существующей поверхности ошибок (имя + кандидаты), а не generic-сообщением; review-item detail показывает `identity_candidates` с переходом к merge.
- **AC-13.** Миграций нет: `alembic upgrade head` не требуется; `git diff` не содержит файлов `alembic/versions/`.
- **AC-14.** Существующие остатки и балансы не изменяются ни в одном сценарии guard'а (блокировка происходит до любых балансовых записей; merge остаётся единственным механизмом переноса).
- **AC-15.** Полная регрессия: `python -m pytest` (SyncServer), `python manage.py test` (Warehouse_web), `npm run build` + `npm run test:unit` (Warehouse_frontend) — зелёные; `make test-e2e` — зелёный или задокументированный блокер стенда.

## Consequences

**Положительные:**

- единственный детерминированный механизм дублирования (materialize) закрыт на всех трёх активных входах; очередь review перестаёт наполняться точными дублями;
- одна политика в одном сервисе — будущее расширение (4.1) не требует ревизии всех входов;
- нулевая схема-стоимость: без миграций, без constraint'ов, без изменения остатков;
- ранняя обратная связь (candidates-эндпоинт + modal warning) предотвращает дубль до submit.

**Deploy/rollback:** миграций и данных нет → zero-downtime deploy обычным катком; rollback = откат кода (никаких данных откатывать не нужно; после отката дубли вновь возможны — статус-кво до ADR).

**Риски и издержки:**

- 🟡 **TOCTOU-окно**: между pre-check и INSERT другой submit может создать идентичный товар. Без unique constraint полная гарантия недостижима; окно мало (материализация внутри одной транзакции submit), последствия ограничены (review-item, который смержит ревьюер). Принято осознанно: ограничение заказчика запрещает constraint. Митигация в 4.1 — partial unique index после data hygiene.
- 🟡 **Блокировка полезна, но требует UX**: кладовщик в поле получает отказ; без понятного сообщения и действия «использовать существующий» guard будет воспринят как регресс. Поэтому AC-12 и §7.3 входят в объём 4.0.
- 🔵 Legacy `approve_as_item` остаётся неблокирующим — осознанный выбор (§5.4), контролируется логами.
- 🔵 Существующие дубли в каталоге guard не лечит — отдельная data-hygiene задача.

## Rejected Alternatives

1. **Unique constraint / partial unique index на `normalized_name`** — прямо запрещён ограничением заказчика; кроме того, существующие дубли сделали бы миграцию неприменимой без предварительной очистки. Перенесено в 4.1 как предмет исследования.
2. **Fuzzy matching (trigram, edit distance, токены)** — запрещён ограничением; недетерминирован, даёт ложные блокировки; `normalize_for_storage` уже склеивает регистр/ё/пунктуацию — основной класс реальных дублей.
3. **Автоматический merge при совпадении** — запрещён ограничением; merge меняет остатки и требует человеческой ответственности (санкционированный поток — review merge с парными adjustment-операциями).
4. **Логика внутри `catalog_admin_service`/`operations_service` без отдельного сервиса** — привела бы к трём копиям политики и дрейфу; противоречит принципу одного владельца правила.
5. **Персистентная таблица «suspected duplicates»** — избыточна для v1: кандидаты дёшево вычисляются live по индексированному точному совпадению; персистентный реестр — предмет 4.1 вместе с отчётностью.
6. **Блокировка legacy `approve_as_item` в 4.0** — риск регрессии отмирающего потока при нулевой измеренной ценности; вместо неё flag-only + логи для решения в 4.1.
