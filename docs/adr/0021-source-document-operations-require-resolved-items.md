# ADR-0021: Source-Document Operations Require Resolved Items

## Status

Accepted

## Date

2026-07-21

## Context

### Проблема

В коде SyncServer отсутствует доверенный технический источник для операций, создаваемых из внешнего документа (накладная, импорт, OCR-pipeline). Текущая реализация позволяет `POST /api/v1/operations` принимать `temporary_item` для строк, что приводит к созданию новых `Item` на submit. Это и есть корень 12 дублей в накладной №51 от 14 июля 2026 (см. `prod_working/duplicate_search_review.md`).

### Что было обнаружено в обследовании

| Что | Где | Проблема |
|---|---|---|
| `POST /api/v1/operations` принимает `temporary_item` | `routes_operations.py:149-170` | Нет разделения source-document / manual |
| `temporary_item` создаёт Item на submit | `operations_service.py:1138-1222` | Без проверки дублей |
| Нет признака source для операции | `models/operation.py:25-237` | `Operation.origin` только user/system |
| Нет доверенного endpoint для source-document | вся архитектура | Generic endpoint слишком гибкий |
| Snapshot заполняется на draft, не на submit | `operations_service.py:707-764, 1037-1085` | Не отражает canonical |

### Корректировка главного архитектора (2026-07-21)

Главный архитектор скорректировал подход:

1. Термин `invoice` не подходит как универсальный технический источник (система сама генерирует накладные и документы). Используется `source_document` / `external source document` / `source_document`.

2. Нельзя полагаться на необязательное клиентское поле `source_system="invoice"`. Требуется отдельный доверенный endpoint `POST /api/v1/operations/from-source-document`.

3. Schema этого endpoint физически не допускает `temporary_item` — строки обязаны иметь `item_id` до создания Operation.

4. Endpoint сохраняет `creation_source="source_document"` самостоятельно, без зависимости от клиента.

5. Snapshot-модель переиспользует существующие поля (`item_name_snapshot` и др.) для catalog snapshot, без параллельного набора `catalog_item_*`. Submit перезаписывает их актуальными canonical значениями.

### Конфликт с ADR-0019 (отменён)

ADR-0019 предлагал «silent reuse» для одного кандидата по `normalized_name`. Этот подход:
- Создаёт неожиданные результаты для кладовщика (silent привязка к Item, который не выбирался)
- Требует fuzzy matching внутри submit (запрещено)
- Не отделяет source-document flow от manual flow

**ADR-0019 отменяется.** Новая политика запрещает `temporary_item` для source-document operations целиком.

## Decision

### Решение 1: Отдельный endpoint для source-document operations

Создать отдельный endpoint `POST /api/v1/operations/from-source-document`:

```python
# routes_operations.py — NEW
@router.post("/from-source-document", response_model=OperationResponse)
async def create_operation_from_source_document(
    payload: SourceDocumentOperationCreate,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
):
    async with uow:
        result = await OperationsService.create_operation_from_source_document(
            uow=uow,
            payload=payload,
            user_id=identity.user_id,
        )
    return OperationResponse.model_validate(result["operation"])
```

### Решение 2: schema endpoint физически не допускает temporary_item

```python
# schemas/operation.py — NEW
class SourceDocumentOperationLineCreate(BaseModel):
    """Operation line for source-document intake.

    НЕ ДОПУСКАЕТ temporary_item.
    extra="forbid" — любое поле, не объявленное в schema, вызовет 422.
    """
    model_config = ConfigDict(extra="forbid")

    line_number: int = Field(ge=1)
    item_id: int = Field(ge=1)  # ОБЯЗАТЕЛЬНОЕ ПОЛЕ, НЕ NULL
    qty: Decimal = Field(gt=0, validation_alias=AliasChoices("qty", "quantity"))
    batch: str | None = None
    comment: str | None = None

    # Source snapshot — фиксируется на момент создания draft
    source_item_name: str | None = Field(default=None, max_length=255)
    source_item_sku: str | None = Field(default=None, max_length=100)
    source_unit_name: str | None = Field(default=None, max_length=100)
    source_category_name: str | None = Field(default=None, max_length=255)

    @field_validator("qty")
    @classmethod
    def validate_qty_positive(cls, value):
        if value <= 0:
            raise ValueError("qty must be positive")
        return value


class SourceDocumentOperationLineCreate(BaseModel):
    """Определение со extra='forbid' — см. ADR-0021 Решение 2.1."""
    pass  # placeholder — см. полное определение в TZ-A §4.2


# В обеих schemas добавляется model_config = ConfigDict(extra="forbid")
# Это критично: если кто-то попытается передать temporary_item или другое
# непредусмотренное поле, запрос падает с 422, а не молча игнорируется.
class SourceDocumentOperationCreate(BaseModel):
    """Source-document operation create payload.

    Schema физически не допускает temporary_item (нет поля в schema).
    extra="forbid" защищает от тихих ошибок интеграции.
    Каждая строка обязана иметь item_id.
    """
    model_config = ConfigDict(extra="forbid")

    operation_type: OperationType
    site_id: int
    source_ref: str = Field(min_length=1, max_length=255)  # ОБЯЗАТЕЛЬНОЕ
    source_document_type: Literal[
        "invoice",          # накладная (для backward понимания)
        "ocr_scan",
        "csv_import",
        "json_import",
        "external_api",
    ]
    source_document_date: datetime | None = None
    effective_at: datetime | None = None
    source_site_id: int | None = None
    destination_site_id: int | None = None
    issued_to_user_id: UUID | None = None
    issued_to_name: str | None = Field(default=None, max_length=255)
    issue_object_id: int | None = None
    issue_object_name_snapshot: str | None = Field(default=None, max_length=255)
    lines: list["SourceDocumentOperationLineCreate"] = Field(min_length=1)
    notes: str | None = Field(default=None, max_length=1000)

    # ОБЯЗАТЕЛЬНЫЙ idempotency key — стабильный идентификатор source-document.
    # Повторная отправка одного source-document не должна создавать вторую Operation.
    # Idempotency enforced через комбинацию source_ref + creation_source + user.
    client_request_id: str | None = Field(default=None, max_length=100)
```

### Решение 3: Operation.creation_source

```python
# models/operation.py — NEW
class Operation(Base):
    # Существующее (deprecated, остаётся для backward compat)
    origin: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="user",
        default="user",
    )

    # НОВОЕ: основной маркер источника
    creation_source: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="manual",
        default="manual",
    )
    # Примеры значений:
    # - "manual" — ручное создание через UI
    # - "source_document" — через dedicated endpoint /from-source-document
    # - "system" — служебная (merge, review resolution)
    # - "legacy" — существующие операции, созданные до этого TZ
```

**Не использовать `operation_inline` как значение для Operation.** Inline создание ТМЦ описывается через `OperationLine.resolution_mode` (см. ниже).

### Решение 4: OperationLine.resolution_mode (computed property, не новое поле)

Использовать существующее наличие `temporary_draft_payload` как маркер:

```python
# models/operation.py — добавить computed property в OperationLine
@property
def resolution_mode(self) -> Literal["existing_item", "inline_item"]:
    """Определяет режим резолюции строки.

    existing_item: строка ссылается на готовый Item (item_id != null, temporary_draft_payload = null)
    inline_item: строка содержит temporary_draft_payload (item_id = null до submit)
    """
    if self.temporary_draft_payload is not None:
        return "inline_item"
    return "existing_item"
```

**Не добавлять новое поле** — `temporary_draft_payload` уже однозначно выражает это состояние.

### Решение 5: SOURCE snapshot поля

Добавить 4 новых поля в `OperationLine`:

```python
# models/operation.py — NEW
class OperationLine(Base):
    # SOURCE snapshot (от исходного внешнего документа, фиксируется на draft)
    source_item_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_item_sku: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_unit_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_category_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
```

Семантика:
- Заполняются при create draft, если клиент передаёт (для source-document operations обязательно)
- Не пересчитываются
- Если источник не передаёт original name — null

### Решение 6: переиспользование существующих catalog snapshot полей

НЕ создавать параллельный набор `catalog_item_*`. Переиспользовать существующие:

```python
# models/operation.py — EXISTING (переосмыслены)
item_name_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
item_sku_snapshot: Mapped[str | None] = mapped_column(String(100), nullable=True)
unit_name_snapshot: Mapped[str | None] = mapped_column(String(100), nullable=True)
unit_symbol_snapshot: Mapped[str | None] = mapped_column(String(20), nullable=True)
category_name_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
```

**Новая семантика:** эти поля фиксируют состояние каталога **на момент submit** (не на draft). Submit обязан перезаписать их актуальными canonical значениями.

`OperationLine.item_id` после submit содержит **canonical Item ID** (после резолюции merge-цепочки).

Замена исходного ID на canonical фиксируется в audit event.

### Решение 7: pre-submit validation pipeline

```python
# operations_service.py:submit_operation — добавить pre-checks
async def submit_operation(uow, operation_id, user_id, expected_version=None):
    operation = await uow.operations.get_operation_by_id_for_update(operation_id)
    OperationsWorkflowPolicy.require_exists(operation)
    OperationsWorkflowPolicy.require_draft_for_submit(operation)

    # NEW: validate resolved lines
    await OperationsService._validate_resolved_lines(uow, operation)

    # NEW: freeze catalog snapshot (на момент submit)
    await OperationsService._freeze_catalog_snapshot(uow, operation)

    # EXISTING: materialize для manual operations с temporary_item
    # НЕ выполняется для source_document (там temporary_item невозможен)
    if operation.creation_source != "source_document":
        await OperationsService._materialize_deferred_temporary_lines(
            uow, operation, user_id,
        )

    # EXISTING: apply inventory effects
    ...
```

### Решение 8: Раздельные submit pipelines

Принцип: для source-document валидация `item_id` происходит на этапе создания draft и повторно на submit. Для manual с `temporary_item` валидация происходит **после** materialize, не до.

#### 8.1. Source-document submit

```
1. require_draft_for_submit
2. _validate_resolved_lines_on_submit:
   - для каждой строки (все уже имеют item_id после создания):
     - resolve merge chain → canonical
     - canonical.is_active=True, deleted_at IS NULL
     - canonical.category.is_active=True, canonical.unit.is_active=True
3. _freeze_catalog_snapshot:
   - для каждой строки:
     - line.item_id = canonical.id
     - line.item_name_snapshot = canonical.name
     - line.item_sku_snapshot = canonical.sku
     - line.unit_name_snapshot = canonical.unit.name
     - line.unit_symbol_snapshot = canonical.unit.symbol
     - line.category_name_snapshot = canonical.category.name
4. _ensure_line_inventory_subject
5. apply inventory effects (existing, type-specific)
6. generate document (existing)
7. commit
```

**Запрещено для source_document:**
- temporary_item (schema физически не допускает — `extra="forbid"`)
- materialize Item
- name/fuzzy resolution
- Item creation

#### 8.2. Manual submit (с temporary_item)

```
1. require_draft_for_submit
2. _materialize_deferred_temporary_lines:
   - для каждой строки с temporary_draft_payload:
     - INSERT Item(name=payload.name, requires_review=true, review_status="needs_review", ...)
     - line.item_id = созданный ID
     - line.temporary_draft_payload = None
3. _validate_resolved_lines_on_submit:
   - для каждой строки (включая materialized):
     - resolve merge chain → canonical
     - canonical.is_active=True, deleted_at IS NULL
     - canonical.category.is_active=True, canonical.unit.is_active=True
4. _freeze_catalog_snapshot:
   - для каждой строки: line.item_id = canonical.id, line.*_snapshot = canonical.*
5. _ensure_line_inventory_subject
6. apply inventory effects (existing)
7. generate document (existing)
8. commit
```

**Ключевое отличие от source-document:** валидация resolved lines происходит **после** materialize (шаг 3 после шага 2). Это позволяет создать новую ТМЦ inline без предварительного сопоставления.

### Решение 8.3: Source-document idempotency

Повторная отправка одного и того же source-document через `POST /operations/from-source-document` не должна создавать вторую Operation.

**Механизм:** используется существующая инфраструктура idempotency (`operations_service.py:602-620`, `operations_repo.py:105-122`) с дополнительной проверкой по `source_ref`:

1. При получении запроса проверить существование Operation с:
   - `source_ref = payload.source_ref`
   - `creation_source = 'source_document'`
   - `created_by_user_id = identity.user_id`
2. Если существует И canonical hash payload совпадает → вернуть существующую Operation (HTTP 200)
3. Если существует И payload отличается → 409 (`code: "source_document_idempotency_conflict"`)
4. Если не существует → создать новую Operation

`client_request_id` (существующее поле) используется для cross-user idempotency если нужно.

### Решение 9: legacy migration (консервативный backfill)

```python
# alembic — НЕ указывать номер, проверить head
"""
Phase A migration: source-document hardening.

1. Operation.creation_source (NOT NULL DEFAULT 'legacy')
2. OperationLine.source_item_* (4 columns, все nullable)
3. Backfill Operation.creation_source:
   - operations where origin='system' → creation_source='system'
   - ВСЕ остальные существующие операции → creation_source='legacy' (default, консервативно)
     НЕ классифицируем origin='user' как 'manual' — исторические операции могут
     быть ручными, legacy-импортом или legacy-импортом через временные endpoints.
4. НЕ backfill-ить source_item_* из item_name_snapshot — эти данные
   не являются достоверным исходным текстом накладной.
   Для legacy строк source_item_* остаются NULL.
5. Indexes (один индекс на creation_source, без дублей):
   - ix_operations_creation_source
"""
```

### Решение 10: BFF boundary

Django BFF НЕ принимает доменное решение о canonical Item:
- BFF может проксировать запрос к `POST /operations/from-source-document`
- BFF может отображать кандидатов из `GET /catalog/read/items?search=...`
- BFF может отправлять выбранные `item_id` пользователем
- BFF НЕ является источником истины о canonical Item
- Resolution и final validation — только SyncServer

## Альтернативы, рассмотренные

### A. Использовать единый `POST /operations` с обязательным `source_system` (предыдущий ADR-0020)

- **Плюсы**: один endpoint.
- **Минусы**: клиент может не передать `source_system` или передать неправильно; schema всё равно допускает `temporary_item`; нет физического запрета.
- **Решение**: отклонено. Главный архитектор скорректировал.

### B. Использовать `temporary_item` + silent reuse (ADR-0019, отменяется)

- **Плюсы**: минимальные schema changes.
- **Минусы**: silent reuse создаёт неожиданные результаты; требует fuzzy matching; не отделяет source-document от manual.
- **Решение**: отклонено.

### C. Полностью запретить `temporary_item` для всех операций

- **Плюсы**: гарантированно нет дублей.
- **Минусы**: нарушает ADR-0012, ADR-0016 (offline clients требуют inline creation); требует предварительного создания всех ТМЦ.
- **Решение**: отклонено. temporary_item остаётся для manual operations.

### D. Использовать middleware/decorator для enforce, не отдельный endpoint

- **Плюсы**: одна schema.
- **Минусы**: runtime-проверки не дают физической гарантии; легко обойти через другой код-путь.
- **Решение**: отклонено. Отдельный endpoint со своей schema — самое надёжное решение.

## Consequences

### Positive

- Source-document operations защищены физически: schema не допускает `temporary_item`.
- Backend может полагаться на инвариант «source_document operation всегда имеет item_id для каждой строки».
- Snapshot-модель переиспользует существующие поля — нет schema bloat.
- Submit pipeline для source_document детерминирован: только ID-резолюция, никакого fuzzy.
- Audit trail: `creation_source` явно фиксирует происхождение.
- Source-document operation может быть подан через тот же generic submit pipeline, что и manual.

### Negative

- Schema addition для `OperationLine.source_item_*` (4 колонки) — additive, non-breaking.
- Schema addition для `Operation.creation_source` (1 колонка) — additive, default='legacy' для existing rows.
- BFF должен обновлять endpoint для импорта накладных, чтобы использовать новый `/from-source-document`.
- OCR/JSON pipeline, использующий `POST /operations` с `temporary_item`, должен быть переключён на `/from-source-document` (это явный migration step).

### Neutral

- ADR-0019 полностью отменяется этим ADR.
- TZ-V3.3 Phase 0 отменяется; Phase 1 (backfill) и Phase 3 (resolve extension) остаются.
- ADR-0020 (invoice) переименован в `.superseded.md`.

## Compliance

### Functional and WorkLogik.md

- §VII.1 «накладная создаётся SyncServer при создании черновика» — расширяется: накладная теперь импортируется через dedicated endpoint.
- §IX.9 «в окно операции добавлено инлайн создание постоянной ТМЦ» — сохраняется только для manual operations (creation_source='manual'), не для source_document.

### ADR-0012 (Deprecate Temporary Items)

- draft хранит temporary_draft_payload → submit материализует — сохраняется для manual operations.
- Для source_document operations — schema физически не допускает temporary_draft_payload.

### ADR-0016 (Offline Sync Architecture)

- Offline клиенты используют `creation_source="manual"` (legacy behavior, используют temporary_item через generic endpoint).
- Не затрагивает.

### ADR-0017 (WPF Migration via Rust Core)

- WarehouseDesktop: `creation_source="manual"` (или legacy).
- Не затрагивает.

## Confidence

High. Изменения локализованы: новая schema для source-document операций, отдельный endpoint, существующий generic endpoint не меняется (только добавляется новый). Additive migration (только ADD COLUMN + DEFAULT 'legacy' для existing). OpenAPI/swagger автоматически подхватит новый endpoint.

## Related

- TZ-SOURCE_DOCUMENT_OPERATION_INTAKE_HARDENING (детальный TZ с фазами)
- TZ-OPERATION_REOPEN_AND_DOCUMENT_REVISION (отдельный пакет B)
- ADR-0021-operation-reopen-and-document-revisions (отдельный ADR для reopen)
- TZ-V3.3_OPERATION_INTAKE_DUPLICATE_PROTECTION.md (Phase 0 отменён, Phase 1+3 остаются)
- ADR-0019.superseded (отменён)
- ADR-0020.superseded (отменён)
- ADR-0012 (Deprecate Temporary Items — сохраняется)
- ADR-0016 (Offline Sync — сохраняется)
- prod_working/duplicate_search_review.md (инцидент)