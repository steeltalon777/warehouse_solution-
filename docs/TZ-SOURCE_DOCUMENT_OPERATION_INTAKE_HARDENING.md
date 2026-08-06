# TZ-SOURCE_DOCUMENT_OPERATION_INTAKE_HARDENING

> **Пакет A из корректирующей директивы главного архитектора (2026-07-21).**
>
> Этот TZ независим от `TZ-OPERATION_REOPEN_AND_DOCUMENT_REVISION` (Пакет B).
> Можно передавать младшей модели отдельно.

## TZ References

- Корректирующая директива: текущая пользовательская директива (полевой архитектор, 2026-07-21)
- ADR-0021-source-document-operations-require-resolved-items.md (архитектурное решение)
- ADR-0021-operation-reopen-and-document-revisions.md (отдельный пакет B)
- Supersedes (частично): `docs/adr/0019-operation-intake-duplicate-protection.superseded.md`
- Supersedes (частично): `docs/TZ-V3.3_OPERATION_INTAKE_DUPLICATE_PROTECTION.md` (Phase 0 отменён, Phase 1+3 остаются)
- Supersedes (частично): `docs/TZ-OPERATION_INVOICE_RESOLUTION_AND_REVISION.md` (Superseded by two documents)
- `Functional and WorkLogik.md` §VII, §IX.9, §II.6.7
- ADR-0012 (Deprecate Temporary Items — сохраняется для manual flow)
- ADR-0016 (Offline Sync — сохраняется)

## Execution Strategy

- [x] 🔴 **Sequential execution required**
- **Reason:** schema additions (Operation.creation_source, OperationLine.source_item_*) должны быть до изменений в submit pipeline. Endpoint добавление независимо от schema, но логика сервиса зависит от schema.

---

## Execution Checklist

- [x] 0. Context verified — обследование проведено (см. секцию 2), все ссылки на код подтверждены
- [x] 1. Architecture boundaries confirmed — SyncServer source of truth, BFF проксирует, не решает
- [x] 2. Schema additions — `Operation.creation_source`, `OperationLine.source_item_*`
- [x] 3. New schemas — `SourceDocumentOperationCreate`, `SourceDocumentOperationLineCreate`
- [x] 4. New endpoint — `POST /api/v1/operations/from-source-document`
- [x] 5. Service method — `OperationsService.create_operation_from_source_document`
- [x] 6. Submit pipeline — `_validate_resolved_lines` + `_freeze_catalog_snapshot`
- [x] 7. Pre-submit rejection — temporary_item невозможен schema-уровнем
- [x] 8. Alembic migration — backfill `creation_source='legacy'`, source snapshots (без номера, проверить head)
- [x] 9. Unit tests — schema enforcement, submit pipeline, snapshot freeze
- [x] 10. Integration tests — все 6 сценариев из секции 8 (+ idempotency) — **8/8 passed** (2026-08-06: scenario_5 pollution исправлен)
- [x] 11. Stand smoke — бизнес-сценарий на dev-стенде 2026-08-06: create → idempotency → submit — все этапы пройдены
- [x] 12. BFF compatibility — `/bff/api/v1/operations/from-source-document` endpoint
- [x] 13. Offline client impact — manual operations не затронуты (legacy behavior сохранён)
- [x] 14. Documentation — `Functional and WorkLogik.md` обновлён (§VII.4), `API_MAP.md` не существует (устаревшая ссылка), `ARCHITECTURE.md` не существует (ADR-0021 — канонический)
- [x] 15. Final acceptance — evidence table заполнен, все тесты пройдены, stand smoke выполнен

---

## 1. Problem Statement

### 1.1. Продуктовая установка

> «Накладная не должна создавать новые ТМЦ. Каждая строка накладной должна быть сопоставлена с существующим `item_id` до создания или сохранения полноценного draft операции.»

### 1.2. Текущее состояние (verified)

| Установка | Состояние | Ссылка |
|---|---|---|
| Накладная не создаёт ТМЦ | ❌ Через `temporary_item` создаёт | `operations_service.py:1138-1222` |
| Строка накладной → `item_id` до draft | ❌ Schema допускает `temporary_item` без `item_id` | `schemas/operation.py:27-65` |
| Submit не ищет по имени | ✅ Поиска нет, но и нет валидации resolved | `operations_service.py:1224-1543` |
| Submit не создаёт ТМЦ | ❌ Создаёт review-Item для temporary_item | `operations_service.py:1178-1192` |
| Submit фиксирует catalog snapshot | ⚠️ Snapshot с draft-time, не с submit-time | `operations_service.py:707-764` |

### 1.3. Инцидент на проде

12 дублей в батче накладной №51 (14 июля 2026):
- IDs 3186-3197 vs 3213-3224
- `Круг 10мм (арматура А1) ст3сп Гост 5781-82 6м` vs `Круг 10 мм (арматура АI) ст3сп ГОСТ 5781-82 6м`
- ~59 дублей суммарно смержено через `POST /api/v1/catalog/admin/items/merge`

### 1.4. Корневая причина

1. Backend не имеет понятия «source-document operation»
2. `POST /operations` принимает `temporary_item` для любой операции (только RECEIVE по проверке)
3. Submit жёстко материализует `temporary_item` в `Item` без проверки на дубли
4. Snapshot фиксируется на draft-time, не на submit-time

---

## 2. Verified Current Architecture

### 2.1. OperationCreate schema (текущая)

```python
# schemas/operation.py:27-65
class OperationLineCreate(BaseModel):
    line_number: int = Field(ge=1)
    item_id: int | None = None                    # ← NULL допустим
    temporary_item: TemporaryItemInlineCreate | None = None  # ← допустим
    qty: Decimal
    batch: str | None = None
    comment: str | None = None

    @model_validator(mode="after")
    def validate_item_xor_temporary(self):
        if self.item_id is None and self.temporary_item is None:
            raise ValueError("either item_id or temporary_item must be provided")
        if self.item_id is not None and self.temporary_item is not None:
            raise ValueError("item_id and temporary_item cannot be provided together")
        return self
```

**Проблема**: schema допускает `item_id=null + temporary_item=set`.

### 2.2. submit_operation (текущая)

```python
# operations_service.py:1224-1543
async def submit_operation(uow, operation_id, user_id, expected_version=None):
    operation = await uow.operations.get_operation_by_id(operation_id)
    ...
    await OperationsService._materialize_deferred_temporary_lines(
        uow, operation, user_id,
    )
    # ↑ СОЗДАЁТ Item для каждой temporary_item, без проверки дублей
    ...
```

### 2.3. _materialize_deferred_temporary_lines (текущая)

```python
# operations_service.py:1138-1222
async def _materialize_deferred_temporary_lines(uow, operation, user_id):
    deferred_lines = [line for line in operation.lines if line.temporary_draft_payload is not None]
    if not deferred_lines:
        return

    grouped = OrderedDict()
    for line in deferred_lines:
        ck = line.temporary_draft_payload["client_key"]
        grouped.setdefault(ck, []).append(line)

    for client_key, lines in grouped.items():
        payload = lines[0].temporary_draft_payload
        review_item = Item(
            sku=payload.get("sku"),
            name=payload["name"].strip(),
            normalized_name=normalize_for_storage(payload["name"]),
            category_id=payload["category_id"],
            unit_id=payload["unit_id"],
            ...
            requires_review=True,
            review_status="needs_review",
            source_system="operation_inline",  # ← признак источника для Item
            source_ref=client_key,
        )
        try:
            review_item = await uow.catalog.create_item(review_item)
        except IntegrityError as exc:
            if "items_sku_key" in str(exc):
                # только SKU-конфликт
                ...
```

**Проблема**: INSERT без проверки дубликатов, единственная защита — `items_sku_key`.

### 2.4. OperationLine model (текущая)

```python
# models/operation.py:285-300
item_name_snapshot: Mapped[str | None]      # snapshot с draft-time
item_sku_snapshot: Mapped[str | None]       # ← не перезаписывается на submit
unit_name_snapshot: Mapped[str | None]
unit_symbol_snapshot: Mapped[str | None]
category_name_snapshot: Mapped[str | None]

temporary_draft_payload: Mapped[dict | None]  # JSONB для inline creation
```

### 2.5. Endpoint surface

```python
# routes_operations.py
POST   /api/v1/operations                       # generic
POST   /api/v1/operations/{id}/submit           # submit
POST   /api/v1/operations/{id}/cancel           # cancel
POST   /api/v1/operations/{id}/restore          # restore cancelled only
PATCH  /api/v1/operations/{id}                  # update draft
POST   /api/v1/operations/{id}/accept-lines     # acceptance

# ОТСУТСТВУЕТ: /api/v1/operations/from-source-document
```

### 2.6. Operation model — source поля

```python
# models/operation.py:169-180
origin: Mapped[str] = mapped_column(
    String(16),
    nullable=False,
    server_default="user",
    default="user",
)
system_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)

# ОТСУТСТВУЕТ: creation_source, source_ref, source_item_*
```

### 2.7. CatalogReadService.resolve_items (existing, reuse)

```python
# catalog_read_service.py:41-149
async def resolve_items(uow, request) -> ItemsResolveResponse:
    """Уже реализует merge-chain resolution через _follow_merge_chain."""
    # Возвращает: requested_id, status, canonical_item_id, canonical_status
    # Используется в OperationsService.update_operation (line 957-984)
```

**Это уже готовый сервис, можно переиспользовать для pre-submit валидации.**

---

## 3. Product Invariants

### 3.1. Обязательные инварианты (Пакет A)

```
INV-A1: Source-document operation endpoint физически не допускает temporary_item.
INV-A2: Каждая строка source-document operation обязана иметь item_id.
INV-A3: Source-document operation submit никогда не создаёт Item.
INV-A4: Submit source-document operation валидирует resolved lines
        (canonical через merge-chain, is_active, deleted_at IS NULL).
INV-A5: Submit source-document operation перезаписывает catalog snapshot
        актуальными canonical значениями.
INV-A6: OperationLine.item_id после submit = canonical Item ID.
INV-A7: Замена ID на canonical фиксируется в audit event.
INV-A8: Django BFF не является источником истины о canonical Item.
```

### 3.2. НЕ покрывается этим TZ

- INV для reopen и document revision — отдельный Пакет B (TZ-OPERATION_REOPEN_AND_DOCUMENT_REVISION)
- Manual operations с temporary_item — сохраняют текущее поведение (ADR-0012)
- Pre-submit validation для legacy `POST /operations` — out of scope для этого пакета

---

## 4. Target Architecture

### 4.1. Новый endpoint `POST /api/v1/operations/from-source-document`

```python
# routes_operations.py — NEW
@router.post("/from-source-document", response_model=OperationResponse)
async def create_operation_from_source_document(
    payload: SourceDocumentOperationCreate,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> OperationResponse:
    """Создать draft операцию из source-document (накладная, OCR, импорт).

    Schema физически не допускает temporary_item.
    Каждая строка обязана иметь item_id.
    Endpoint самостоятельно проставляет creation_source='source_document'.
    """
    OperationsPolicy.require_create_draft(identity, payload.site_id)

    async with uow:
        result = await OperationsService.create_operation_from_source_document(
            uow=uow,
            payload=payload,
            user_id=identity.user_id,
        )

    operation = result["operation"]
    logger.info(
        "create_operation_from_source_document",
        request_id=get_request_id(request),
        id=operation.id,
        source_ref=payload.source_ref,
        source_document_type=payload.source_document_type,
        user=identity.user_id,
    )
    return OperationResponse.model_validate(operation)
```

### 4.2. Schema endpoint

```python
# schemas/operation.py — NEW

SourceDocumentType = Literal[
    "invoice",          # накладная (для backward понимания в логах/аудите)
    "ocr_scan",         # OCR-распознанный документ
    "csv_import",       # импорт из CSV
    "json_import",      # импорт из JSON
    "external_api",     # из внешней системы
]


class SourceDocumentOperationLineCreate(BaseModel):
    """Operation line для source-document. НЕ ДОПУСКАЕТ temporary_item.

    extra="forbid" — любое поле, не объявленное в schema, вызовет 422.
    Это критично для безопасности: если кто-то попытается передать
    temporary_item или другое непредусмотренное поле, запрос падает,
    а не молча игнорируется.
    """
    model_config = ConfigDict(extra="forbid")

    line_number: int = Field(ge=1)

    # ОБЯЗАТЕЛЬНОЕ поле — schema физически не допускает null
    item_id: int = Field(ge=1)

    qty: Decimal = Field(gt=0, validation_alias=AliasChoices("qty", "quantity"))
    batch: str | None = Field(default=None, max_length=100)
    comment: str | None = Field(default=None, max_length=1000)

    # SOURCE snapshot (опциональные, но рекомендуемые для audit)
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


class SourceDocumentOperationCreate(BaseModel):
    """Source-document operation create payload.

    Schema не имеет temporary_item — backend физически не может создать Item.
    Все строки обязаны иметь item_id.

    extra="forbid" — любое поле, не объявленное в schema, вызовет 422.
    Это защищает от тихих ошибок интеграции (если кто-то пытается
    добавить поле вроде temporary_item в будущем).
    """
    model_config = ConfigDict(extra="forbid")

    operation_type: OperationType = Field(validation_alias=AliasChoices("operation_type", "type"))
    site_id: int = Field(ge=1)

    # Идентификация source
    source_ref: str = Field(min_length=1, max_length=255)  # ОБЯЗАТЕЛЬНО
    source_document_type: SourceDocumentType
    source_document_date: datetime | None = None

    # Стандартные поля операции
    effective_at: datetime | None = None
    source_site_id: int | None = None
    destination_site_id: int | None = Field(
        default=None,
        validation_alias=AliasChoices("destination_site_id", "target_site_id"),
    )
    issued_to_user_id: UUID | None = None
    issued_to_name: str | None = Field(default=None, max_length=255)
    issue_object_id: int | None = None
    issue_object_name_snapshot: str | None = Field(default=None, max_length=255)
    lines: list[SourceDocumentOperationLineCreate] = Field(min_length=1)
    notes: str | None = Field(default=None, max_length=1000)

    # ОБЯЗАТЕЛЬНЫЙ idempotency key — стабильный идентификатор source-document.
    # Повторная отправка одного и того же source-document с тем же source_ref
    # через этот endpoint не должна создавать вторую Operation.
    # В отличие от client_request_id (на уровне Operation), source_ref
    # семантически привязан к содержимому source-document.
    # Idempotency enforced через комбинацию source_ref + creation_source + user.
    client_request_id: str | None = Field(default=None, max_length=100)
```

### 4.2.1. Source-document idempotency

**Критичное требование:** повторная отправка одного и того же source-document не должна создавать вторую Operation.

**Механизм:** используется комбинация:
- `source_ref` (обязательное поле, семантически стабильный идентификатор source-document)
- `creation_source='source_document'`
- `created_by_user_id` (опционально, для персонального idempotency)

При получении `POST /operations/from-source-document`:
1. Проверить существование Operation с `source_ref=payload.source_ref AND creation_source='source_document' AND created_by_user_id=payload.user_id`
2. Если существует И payload совпадает (canonical hash) → вернуть существующую Operation (idempotency response)
3. Если существует И payload отличается → 409 conflict (как для `client_request_id` в существующем коде)
4. Если не существует → создать новую Operation

**Реализация:** переиспользовать существующую логику idempotency для `client_request_id` (`operations_repo.py:105-122`, `operations_service.py:602-620`). Привязка к `source_ref` — дополнительная проверка перед созданием Operation.

**Тест:** повторная отправка одного source-document должна возвращать ту же Operation (HTTP 200/201 с тем же ID).

### 4.3. Operation.creation_source

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
        server_default="legacy",
        default="legacy",
    )
    # Значения:
    # - "manual" — ручное создание через UI (POST /operations без temporary_item)
    # - "source_document" — через dedicated endpoint (POST /operations/from-source-document)
    # - "system" — служебная (merge, review resolution, system ADJUSTMENT)
    # - "legacy" — существующие операции до этого TZ (default при backfill)

    # НОВОЕ: ref на source документ (например, "invoice-2026-07-21-001")
    source_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
```

### 4.4. OperationLine SOURCE snapshot поля

```python
# models/operation.py — NEW (4 columns)
class OperationLine(Base):
    # SOURCE snapshot (от исходного документа, фиксируется на draft)
    source_item_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_item_sku: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_unit_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_category_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # EXISTING — переиспользуются как catalog snapshot (записываются на submit)
    item_name_snapshot: Mapped[str | None]
    item_sku_snapshot: Mapped[str | None]
    unit_name_snapshot: Mapped[str | None]
    unit_symbol_snapshot: Mapped[str | None]
    category_name_snapshot: Mapped[str | None]
```

### 4.5. OperationLine.resolution_mode (computed property, не новое поле)

```python
# models/operation.py — добавить в OperationLine
@property
def resolution_mode(self) -> Literal["existing_item", "inline_item"]:
    """existing_item: item_id != null, temporary_draft_payload = null
    inline_item: temporary_draft_payload != null (item_id = null до submit)
    """
    if self.temporary_draft_payload is not None:
        return "inline_item"
    return "existing_item"
```

**Не добавлять новое поле** — `temporary_draft_payload` уже однозначно выражает это состояние.

### 4.6. Service method

```python
# operations_service.py — NEW
@staticmethod
async def create_operation_from_source_document(
    uow: UnitOfWork,
    payload: SourceDocumentOperationCreate,
    user_id: UUID,
) -> dict[str, object]:
    """Создать draft операцию из source-document.

    Этап 1: серверная валидация каждого item_id (canonical, active, not deleted).
    Этап 2: snapshot SOURCE (из payload).
    Этап 3: создание draft без materialize.
    Этап 4: draft waybill.
    """
    # Шаг 1: серверная валидация item_id
    validated_lines = []
    for line_data in payload.lines:
        await OperationsService._validate_source_document_line(uow, line_data)
        validated_lines.append(line_data)

    # Шаг 2: prepare для create_operation
    # Конвертируем SourceDocumentOperationLineCreate → OperationLineCreate-like
    # с предзаполненным snapshot
    effective_at = payload.effective_at or datetime.now(UTC)
    display_number = _compute_operation_display_number(payload.site_id, effective_at)

    # Создаём draft
    operation = await uow.operations.create_operation(
        site_id=payload.site_id,
        operation_type=payload.operation_type,
        created_by_user_id=user_id,
        effective_at=effective_at,
        source_site_id=payload.source_site_id,
        destination_site_id=payload.destination_site_id,
        issued_to_user_id=payload.issued_to_user_id,
        issued_to_name=payload.issued_to_name,
        issue_object_id=payload.issue_object_id,
        issue_object_name_snapshot=payload.issue_object_name_snapshot,
        acceptance_required=payload.operation_type in ACCEPTANCE_REQUIRED_TYPES,
        notes=payload.notes,
        client_request_id=payload.client_request_id,
        display_number=display_number,
        origin="user",  # backward compat
    )
    # Проставляем creation_source и source_ref напрямую
    operation.creation_source = "source_document"
    operation.source_ref = payload.source_ref

    # Шаг 3: создаём строки с SOURCE snapshot
    for line_data in payload.lines:
        item = await uow.catalog.get_item_by_id(line_data.item_id)
        if item is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"item with id {line_data.item_id} not found",
            )

        unit = await uow.catalog.get_unit_by_id(item.unit_id)
        category = await uow.catalog.get_category_by_id(item.category_id)

        # Сначала SOURCE snapshot (от исходного документа)
        # Потом catalog snapshot (от draft-времени — будет перезаписан на submit)
        await uow.operations.create_operation_line(
            operation_id=operation.id,
            line_number=line_data.line_number,
            item_id=line_data.item_id,  # ← уже валидирован
            inventory_subject_id=None,  # будет создан на submit
            qty=line_data.qty,
            batch=line_data.batch,
            comment=line_data.comment,
            source_item_name=line_data.source_item_name,
            source_item_sku=line_data.source_item_sku,
            source_unit_name=line_data.source_unit_name,
            source_category_name=line_data.source_category_name,
            # catalog snapshot предзаполняется для preview (INV-A5: перезаписывается на submit)
            item_name_snapshot=item.name,
            item_sku_snapshot=item.sku,
            unit_name_snapshot=unit.name if unit else None,
            unit_symbol_snapshot=unit.symbol if unit else None,
            category_name_snapshot=category.name if category else None,
        )

    # Шаг 4: draft waybill
    created_operation = await uow.operations.get_operation_by_id(operation.id)
    draft_doc_type = draft_document_type_for_operation(created_operation.operation_type)
    if draft_doc_type:
        try:
            async with uow.session.begin_nested():
                await DocumentService.generate_from_operation(
                    uow=uow,
                    operation_id=created_operation.id,
                    document_type=draft_doc_type,
                    auto_finalize=False,
                    created_by_user_id=user_id,
                )
        except Exception as exc:
            logger.warning("waybill_auto_create_failed", ...)

    # Audit
    await record_audit_event(
        uow,
        event_type="operation.create",
        actor_user_id=user_id,
        site_id=payload.site_id,
        entity_type="operation",
        entity_id=str(created_operation.id),
        summary=f"Пользователь создал черновик операции №{created_operation.short_id} из source-document ({payload.source_document_type})",
        changes={
            "creation_source": "source_document",
            "source_ref": payload.source_ref,
            "source_document_type": payload.source_document_type,
            "lines_count": len(payload.lines),
        },
    )
    return {"operation": created_operation}


@staticmethod
async def _validate_source_document_line(uow, line_data) -> int:
    """Валидация строки source-document operation.

    Возвращает canonical_item_id.
    Бросает HTTPException 422 если item не подходит.
    """
    if line_data.item_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"line {line_data.line_number} has no item_id",
        )

    # Resolve merge chain
    canonical, reason = await CatalogReadService._follow_merge_chain(
        uow, await uow.catalog.get_item_by_id(line_data.item_id), depth=0
    )
    if canonical is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "source_document_line_unresolvable",
                "line_number": line_data.line_number,
                "item_id": line_data.item_id,
                "reason": reason or "merge_chain_unresolvable",
            },
        )

    if canonical.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "source_document_line_deleted",
                "line_number": line_data.line_number,
                "item_id": line_data.item_id,
                "canonical_item_id": canonical.id,
            },
        )

    if not canonical.is_active:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "source_document_line_inactive",
                "line_number": line_data.line_number,
                "item_id": line_data.item_id,
                "canonical_item_id": canonical.id,
            },
        )

    # Если client прислал item_id, но canonical_id отличается — обновляем
    if canonical.id != line_data.item_id:
        # Запоминаем в audit resource
        return canonical.id
    return canonical.id
```

### 4.7. Submit pipeline changes

```python
# operations_service.py:submit_operation — модификация
async def submit_operation(uow, operation_id, user_id, expected_version=None):
    operation = await uow.operations.get_operation_by_id_for_update(operation_id)
    OperationsWorkflowPolicy.require_exists(operation)
    OperationsWorkflowPolicy.require_draft_for_submit(operation)

    # NEW: validate resolved lines (для source_document и для обычных)
    await OperationsService._validate_resolved_lines_on_submit(uow, operation)

    # NEW: freeze catalog snapshot (на момент submit)
    await OperationsService._freeze_catalog_snapshot(uow, operation)

    # EXISTING: materialize ТОЛЬКО для manual операций с temporary_item
    # Для source_document: temporary_draft_payload гарантированно null (schema запрещает)
    if operation.creation_source != "source_document":
        await OperationsService._materialize_deferred_temporary_lines(
            uow, operation, user_id,
        )

    # EXISTING: apply inventory effects
    ...


@staticmethod
async def _validate_resolved_lines_on_submit(uow, operation) -> None:
    """Повторная валидация resolved lines на submit.

    Проверяет:
    - item_id != null (для source_document гарантировано, для manual тоже теперь обязательно
      после _materialize_deferred_temporary_lines)
    - canonical_id через merge chain
    - canonical.is_active
    - canonical.deleted_at IS NULL
    """
    unresolved = []
    for line in operation.lines:
        if line.item_id is None:
            unresolved.append({
                "line_id": line.id,
                "line_number": line.line_number,
                "reason": "missing_item_id",
            })
            continue

        canonical, reason = await CatalogReadService._follow_merge_chain(
            uow, await uow.catalog.get_item_by_id(line.item_id), depth=0
        )
        if canonical is None:
            unresolved.append({
                "line_id": line.id,
                "line_number": line.line_number,
                "previous_item_id": line.item_id,
                "reason": reason or "unresolvable",
            })
            continue

        if canonical.deleted_at is not None:
            unresolved.append({
                "line_id": line.id,
                "line_number": line.line_number,
                "previous_item_id": line.item_id,
                "canonical_item_id": canonical.id,
                "reason": "deleted",
            })
            continue

        if not canonical.is_active:
            unresolved.append({
                "line_id": line.id,
                "line_number": line.line_number,
                "previous_item_id": line.item_id,
                "canonical_item_id": canonical.id,
                "reason": "inactive",
            })
            continue

    if unresolved:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "operation_lines_unresolved",
                "operation_id": str(operation.id),
                "lines": unresolved,
            },
        )


@staticmethod
async def _freeze_catalog_snapshot(uow, operation) -> None:
    """Зафиксировать catalog snapshot на момент submit.

    Перезаписывает item_name_snapshot, item_sku_snapshot, unit_*_snapshot,
    category_name_snapshot актуальными canonical значениями.
    Также обновляет OperationLine.item_id на canonical_id (если отличается).
    Замена фиксируется в audit event (resource link).
    """
    catalog_changes = []
    for line in operation.lines:
        if line.item_id is None:
            continue  # temporary_item будет materialized отдельно (manual only)

        canonical, _ = await CatalogReadService._follow_merge_chain(
            uow, await uow.catalog.get_item_by_id(line.item_id), depth=0
        )
        if canonical is None:
            continue  # already validated

        old_id = line.item_id
        new_id = canonical.id

        if old_id != new_id:
            catalog_changes.append({
                "line_id": line.id,
                "line_number": line.line_number,
                "previous_item_id": old_id,
                "canonical_item_id": new_id,
                "reason": "merged",
            })

        line.item_id = new_id
        line.item_name_snapshot = canonical.name
        line.item_sku_snapshot = canonical.sku
        if canonical.unit:
            line.unit_name_snapshot = canonical.unit.name
            line.unit_symbol_snapshot = canonical.unit.symbol
        if canonical.category:
            line.category_name_snapshot = canonical.category.name

    await uow.session.flush()

    if catalog_changes:
        # Audit resource links для traceability
        # (записываются в event resource links через caller)
        # Caller (submit_operation) логирует operation.submit с changes
        pass
```

---

## 5. Submit Pipelines

### 5.1. Source-document submit (раздельный порядок)

> **Принцип:** для source-document валидация `item_id` происходит на этапе создания draft (т.к. schema требует его наличия). На submit — повторная валидация и фиксация catalog snapshot. `temporary_item` отсутствует физически.

```
1. require_draft_for_submit
2. _validate_resolved_lines_on_submit (повторная серверная валидация):
   - для каждой строки:
     - resolve merge chain → canonical
     - canonical.is_active=True, deleted_at IS NULL
     - canonical.category.is_active=True, canonical.unit.is_active=True
3. _freeze_catalog_snapshot:
   - для каждой строки:
     - line.item_id = canonical.id
     - line.item_name_snapshot = canonical.name
     - line.item_sku_snapshot = canonical.sku
     - line.unit_name_snapshot = canonical.unit.name (если canonical.unit)
     - line.unit_symbol_snapshot = canonical.unit.symbol (если canonical.unit)
     - line.category_name_snapshot = canonical.category.name (если canonical.category)
     - audit resource: previous_item_id → canonical_item_id (если merge)
4. _ensure_line_inventory_subject
5. apply inventory effects (RECEIVE/MOVE/EXPENSE/WRITE_OFF/ISSUE/ISSUE_RETURN)
6. submit doc generation
7. operation.submit audit event
```

**Запрещено:**
- temporary_item (schema физически не допускает — `extra="forbid"`)
- materialize Item
- name/fuzzy resolution
- Item creation

### 5.2. Manual submit (раздельный порядок)

> **Принцип:** для manual операций с `temporary_item` валидация `item_id` НЕ происходит до materialization. Сначала создаётся `Item` (review-flow), потом валидируется результат. Это даёт кладовщику возможность создать новую ТМЦ без предварительного сопоставления.

```
1. require_draft_for_submit
2. _materialize_deferred_temporary_lines (existing, создаёт Item(requires_review=true)):
   - для каждой строки с temporary_draft_payload:
     - INSERT Item(name=payload.name, requires_review=true, review_status="needs_review", ...)
     - line.item_id = созданный ID
     - line.temporary_draft_payload = None
3. _validate_resolved_lines_on_submit:
   - для каждой строки (включая materialized):
     - resolve merge chain → canonical
     - canonical.is_active=True, deleted_at IS NULL
     - canonical.category.is_active=True, canonical.unit.is_active=True
   - При ошибке: 409 operation_lines_unresolved
4. _freeze_catalog_snapshot:
   - для каждой строки:
     - line.item_id = canonical.id
     - line.item_name_snapshot = canonical.name
     - line.item_sku_snapshot = canonical.sku
     - line.unit_name_snapshot = canonical.unit.name
     - line.unit_symbol_snapshot = canonical.unit.symbol
     - line.category_name_snapshot = canonical.category.name
     - audit resource: previous_item_id → canonical_item_id (если merge)
5. _ensure_line_inventory_subject
6. apply inventory effects
7. submit doc generation
8. operation.submit audit event
```

**Важно:** `_validate_resolved_lines_on_submit` для manual операций срабатывает **после** materialize, не до. Это позволяет создать новую ТМЦ inline без предварительного сопоставления, и затем валидировать canonical.

### 5.3. Сравнение pipelines (исправленное)

| Шаг | source_document | manual |
|---|---|---|
| Schema | `SourceDocumentOperationCreate` (нет temporary_item) | `OperationCreate` (есть temporary_item) |
| `extra="forbid"` | да | нет (legacy) |
| creation_source | "source_document" | "manual" |
| temp_item check | schema запрещает | runtime check `require_temporary_item_create` |
| pre-validate item_id (create) | ДА (`create_operation_from_source_document`) | нет |
| materialize | НЕТ | ДА (если temporary_item) |
| validate item_id (submit) | ДА | ДА (ПОСЛЕ materialize) |
| freeze catalog snapshot | ДА (canonical) | ДА (canonical) |
| audit creation_source | "source_document" | "manual" |

---

## 6. Database Migrations

### 6.1. Migration (НЕ фиксировать номер)

> **Примечание**: номер Alembic миграции НЕ указан в этом TZ. Перед созданием миграции проверить `alembic heads` и использовать следующий номер в текущей head-цепочке.

```python
"""Phase A: source-document operation hardening.

Adds:
- Operation.creation_source (NOT NULL DEFAULT 'legacy')
- Operation.source_ref (nullable)
- OperationLine.source_item_name, source_item_sku, source_unit_name, source_category_name

Backfill:
- Operation.creation_source:
    - 'system' для operations WHERE origin = 'system'
    - 'legacy' для ВСЕХ остальных существующих операций (консервативный fallback)
  НЕ классифицируем origin="user" как 'manual' — исторические операции
  могут быть как ручными, так и legacy-импортом, различать невозможно.

Indexes:
- ix_operations_creation_source (один индекс, без дублей)
"""

def upgrade():
    # 1. Operation columns
    op.add_column("operations", sa.Column("creation_source", sa.String(32), nullable=False, server_default="legacy"))
    op.add_column("operations", sa.Column("source_ref", sa.String(255), nullable=True))

    # 2. Backfill Operation.creation_source
    op.execute("UPDATE operations SET creation_source = 'system' WHERE origin = 'system'")
    # Все остальные остаются 'legacy' (default) — НЕ backfill-ить как 'manual'

    # 3. Один индекс (без дублей)
    op.create_index("ix_operations_creation_source", "operations", ["creation_source"], unique=False)

    # 4. OperationLine SOURCE snapshot columns
    op.add_column("operation_lines", sa.Column("source_item_name", sa.String(255), nullable=True))
    op.add_column("operation_lines", sa.Column("source_item_sku", sa.String(100), nullable=True))
    op.add_column("operation_lines", sa.Column("source_unit_name", sa.String(100), nullable=True))
    op.add_column("operation_lines", sa.Column("source_category_name", sa.String(255), nullable=True))

    # 5. НЕ backfill-ить source_item_* from item_name_snapshot
    # Эти данные не являются достоверным исходным текстом накладной.
    # Для legacy операций source_* остаются NULL.
    # Существующий catalog snapshot (item_name_snapshot и др.) остаётся без изменений.


def downgrade():
    op.drop_index("ix_operations_creation_source", "operations")
    op.drop_column("operations", "source_ref")
    op.drop_column("operations", "creation_source")
    op.drop_column("operation_lines", "source_category_name")
    op.drop_column("operation_lines", "source_unit_name")
    op.drop_column("operation_lines", "source_item_sku")
    op.drop_column("operation_lines", "source_item_name")
```

**Важно:**
- НЕ дублировать индекс `ix_operations_source_system` (был в предыдущем TZ, был удалён в корректировке)
- НЕ фиксировать revision номер
- **НЕ backfill-ить `creation_source='manual'`** для существующих операций: они классифицируются как `legacy` (консервативно). Новые операции через generic endpoint будут явно получать `creation_source='manual'` (см. секцию 10.4)
- **НЕ backfill-ить `source_item_*`** из `item_name_snapshot`: эти данные не являются достоверным исходным текстом накладной. Для legacy строк `source_item_*` остаются `NULL`

---

## 7. Audit Events

### 7.1. Новые event types

| event_type | Когда | Что фиксирует |
|---|---|---|
| `operation.create` | (existing) | расширен полями `creation_source`, `source_ref`, `source_document_type` |

### 7.2. Audit resource links

```python
# create_operation_from_source_document
await record_audit_event(
    uow,
    event_type="operation.create",
    actor_user_id=user_id,
    site_id=payload.site_id,
    entity_type="operation",
    entity_id=str(operation.id),
    summary=...,
    changes={
        "creation_source": "source_document",
        "source_ref": payload.source_ref,
        "source_document_type": payload.source_document_type,
        "lines_count": len(payload.lines),
    },
)

# submit_operation: фиксация catalog resolution
if catalog_changes:
    for change in catalog_changes:
        await uow.audit_events.insert_resource(
            audit_event_id=int(submit_event.id),
            resource_type="operation_line",
            resource_id=str(change["line_id"]),
            relation="catalog_resolved",
            snapshot_before={"item_id": change["previous_item_id"]},
            snapshot_after={"item_id": change["canonical_item_id"]},
            extra_metadata={"reason": change["reason"]},
        )
```

---

## 8. API Changes

### 8.1. Request schemas

#### `POST /api/v1/operations/from-source-document`

```json
{
  "operation_type": "RECEIVE",
  "site_id": 1,
  "source_ref": "invoice-2026-07-21-001",
  "source_document_type": "invoice",
  "source_document_date": "2026-07-21T00:00:00Z",
  "effective_at": "2026-07-21T12:00:00Z",
  "lines": [
    {
      "line_number": 1,
      "item_id": 3186,
      "qty": 10,
      "batch": "LOT-2026-07-A",
      "comment": null,
      "source_item_name": "Круг 10 мм (арматура А1)",
      "source_item_sku": null,
      "source_unit_name": "килограмм",
      "source_category_name": "Металлопрокат"
    },
    {
      "line_number": 2,
      "item_id": 4102,
      "qty": 5,
      "source_item_name": "Уголок 50x50",
      "source_item_sku": "ANG-50-50"
    }
  ],
  "notes": "Накладная №51 от 21.07.2026",
  "client_request_id": "invoice-51-2026-07-21"
}
```

### 8.2. Response

```json
{
  "id": "uuid",
  "operation_uuid": "uuid",
  "site_id": 1,
  "operation_type": "RECEIVE",
  "type": "RECEIVE",
  "status": "draft",
  "version": 1,
  "creation_source": "source_document",  // ← НОВОЕ
  "source_ref": "invoice-2026-07-21-001",  // ← НОВОЕ
  "lines": [...],
  ...
}
```

### 8.3. Error contracts

#### Source-document line without item_id

```json
// HTTP 422 (validation error от pydantic)
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "lines", 0, "item_id"],
      "msg": "Field required",
      "input": {...}
    }
  ]
}
```

#### Item unresolvable (merged chain broken)

```json
// HTTP 422
{
  "code": "source_document_line_unresolvable",
  "line_number": 5,
  "item_id": 3186,
  "reason": "merge_chain_unresolvable"
}
```

#### Item deleted

```json
// HTTP 422
{
  "code": "source_document_line_deleted",
  "line_number": 3,
  "item_id": 3500,
  "canonical_item_id": null
}
```

#### Item inactive

```json
// HTTP 422
{
  "code": "source_document_line_inactive",
  "line_number": 7,
  "item_id": 9999,
  "canonical_item_id": 9999
}
```

#### Submit failed (lines unresolved on submit)

```json
// HTTP 409
{
  "code": "operation_lines_unresolved",
  "operation_id": "uuid",
  "lines": [
    {
      "line_id": 123,
      "line_number": 5,
      "previous_item_id": 3186,
      "canonical_item_id": 3210,
      "reason": "merged"
    }
  ]
}
```

### 8.4. BFF mirroring

Django BFF должен зеркалировать endpoint:

```python
# Warehouse_web/apps/sync_client/views.py — NEW
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_operation_from_source_document(request):
    """BFF проксирует запрос к SyncServer /from-source-document."""
    response = requests.post(
        f"{settings.SYNC_SERVER_URL}/api/v1/operations/from-source-document",
        json=request.data,
        headers={
            "X-User-Token": str(request.user.syncserver_user_token),
            "X-Device-Token": settings.SYNC_DEVICE_TOKEN,
        },
    )
    return Response(response.json(), status=response.status_code)
```

---

## 9. Schema/Model Changes

### 9.1. Operation

```python
# models/operation.py
class Operation(Base):
    # EXISTING — deprecated, остаётся для backward compat
    origin: Mapped[str]
    system_reason: Mapped[str | None]

    # NEW
    creation_source: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="legacy",
        default="legacy",
    )
    source_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
```

### 9.2. OperationLine

```python
# models/operation.py
class OperationLine(Base):
    # NEW: SOURCE snapshot
    source_item_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_item_sku: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_unit_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_category_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # EXISTING (semantic shift: catalog snapshot, frozen at submit)
    item_name_snapshot: Mapped[str | None]
    item_sku_snapshot: Mapped[str | None]
    unit_name_snapshot: Mapped[str | None]
    unit_symbol_snapshot: Mapped[str | None]
    category_name_snapshot: Mapped[str | None]

    # EXISTING — temporary draft payload (для manual operations)
    temporary_draft_payload: Mapped[dict | None]

    # NEW: computed property (не schema)
    @property
    def resolution_mode(self) -> Literal["existing_item", "inline_item"]:
        if self.temporary_draft_payload is not None:
            return "inline_item"
        return "existing_item"
```

### 9.3. Schemas (schemas/operation.py)

```python
# NEW: SourceDocumentOperationCreate
class SourceDocumentOperationLineCreate(BaseModel):
    line_number: int = Field(ge=1)
    item_id: int = Field(ge=1)  # ← ОБЯЗАТЕЛЬНОЕ
    qty: Decimal = Field(gt=0, validation_alias=AliasChoices("qty", "quantity"))
    batch: str | None = None
    comment: str | None = None
    source_item_name: str | None = None
    source_item_sku: str | None = None
    source_unit_name: str | None = None
    source_category_name: str | None = None

# NEW: SourceDocumentOperationCreate
class SourceDocumentOperationCreate(BaseModel):
    operation_type: OperationType
    site_id: int
    source_ref: str = Field(min_length=1, max_length=255)
    source_document_type: SourceDocumentType
    source_document_date: datetime | None = None
    effective_at: datetime | None = None
    source_site_id: int | None = None
    destination_site_id: int | None = None
    issued_to_user_id: UUID | None = None
    issued_to_name: str | None = None
    issue_object_id: int | None = None
    issue_object_name_snapshot: str | None = None
    lines: list[SourceDocumentOperationLineCreate] = Field(min_length=1)
    notes: str | None = None
    client_request_id: str | None = None

# EXISTING: OperationCreate — без изменений (manual operations)
```

---

## 10. Backward Compatibility

### 10.1. Generic `POST /operations` endpoint

- Сохраняется без изменений для manual operations
- `OperationCreate` schema не меняется
- temporary_item продолжает работать для manual операций
- Новые manual операции через этот endpoint получают `creation_source='manual'` явно
- Существующие операции остаются с `creation_source='legacy'`

### 10.2. `creation_source` backfill (консервативный)

Политика:
- `origin='system'` → `creation_source='system'` (однозначно)
- **ВСЕ остальные** существующие операции → `creation_source='legacy'` (консервативный default)

**Не классифицируем `origin='user'` как `manual'`.** Исторические операции с `origin='user'` могут быть:
- ручными (manual);
- legacy-импортом через generic endpoint;
- legacy-импортом через временные endpoints (например, удалённый `POST /operations/legacy` или внешние скрипты).

Безопасная политика — классифицировать как `legacy`. Это означает:
- Reopen (если будет в будущем) обрабатывает их как legacy с консервативной политикой
- UI может пометить их как "до внедрения source-document flow"
- Если нужно отличить manual от legacy — это можно сделать вручную через ad-hoc запрос

**Trade-off**: legacy operations невозможно точно классифицировать автоматически. Консервативный fallback гарантирует безопасное поведение.

### 10.3. Source snapshot backfill — НЕ выполняется

Политика:
- `OperationLine.source_item_*` НЕ backfill-ятся из `item_*_snapshot`
- Для legacy строк `source_item_*` остаются `NULL`
- Существующий catalog snapshot (`item_name_snapshot` и др.) остаётся без изменений

**Причина:** `item_name_snapshot` фиксирует состояние каталога **на момент submit**, а не исходный текст накладной. Эти данные не могут считаться достоверным source snapshot. Если для legacy строки `source_item_name = NULL`, в UI это можно отобразить как "(исходный документ неизвестен)".

Для новых source-document операций `source_item_*` заполняются явно из payload клиента (BFF/OCR pipeline знает исходный текст).

### 10.4. Manual operations через generic endpoint

- WarehouseDesktop/WarehouseMobile используют `creation_source='manual'` (новый explicit marker)
- Используют temporary_item через generic endpoint — работает как раньше
- Не нужно переключать на новый endpoint (manual operations сохраняются)
- Для idempotency manual operations используют существующий `client_request_id`

### 10.5. BFF compatibility

- Django BFF может проксировать новый endpoint без изменений логики
- BFF не должен решать о canonical Item (см. ADR-0021)
- Для source-document: BFF резолвит item_id на клиентской стороне (через `GET /catalog/read/items?search=...`) и передаёт в `SourceDocumentOperationCreate`
- BFF может добавить дополнительный preflight endpoint для UX, но финальное решение остаётся на SyncServer

### 10.6. Source-document idempotency

Повторная отправка одного и того же source-document через `POST /operations/from-source-document` не должна создавать вторую Operation.

**Механизм:** используется существующая инфраструктура idempotency через `client_request_id` (`operations_service.py:602-620`, `operations_repo.py:105-122`) + дополнительная проверка по `source_ref`:

1. При получении запроса проверяется существование Operation с:
   - `source_ref = payload.source_ref`
   - `creation_source = 'source_document'`
   - `created_by_user_id = identity.user_id`
2. Если существует И canonical hash payload совпадает → вернуть существующую Operation (idempotency response, HTTP 200)
3. Если существует И payload отличается → 409 conflict (`code: "source_document_idempotency_conflict"`)
4. Если не существует → создать новую Operation

**Тест:** повторная отправка одного source-document должна возвращать ту же Operation (тот же `operation.id`).

---

## 11. Test Ladder

### 11.1. Unit tests (Пакет A)

| Тест | Что проверяет |
|---|---|
| `test_source_document_schema_no_temporary_item` | Schema физически не имеет `temporary_item` поля |
| `test_source_document_line_requires_item_id` | item_id обязательное |
| `test_source_document_line_qty_positive` | qty > 0 enforced |
| `test_create_from_source_document_validates_item_id` | _validate_source_document_line вызывается |
| `test_create_from_source_document_sets_creation_source` | creation_source='source_document' |
| `test_create_from_source_document_skips_materialize` | _materialize_deferred_temporary_lines НЕ вызывается |
| `test_submit_skips_materialize_for_source_document` | Source-document submit не вызывает _materialize |
| `test_submit_validates_resolved_lines` | _validate_resolved_lines_on_submit проверяет canonical |
| `test_submit_freezes_catalog_snapshot` | _freeze_catalog_snapshot перезаписывает snapshot |
| `test_submit_records_catalog_resolution_audit` | audit resource links для замены item_id |

### 11.2. Integration tests

| # | Сценарий | Что проверяет |
|---|---|---|
| 1 | Source-document со всеми resolved items | 200, draft создан, creation_source='source_document' |
| 2 | Source-document с одной unresolved line | 422 на create (не 409 на submit) |
| 3 | Попытка передать temporary_item (если кто-то добавит в schema) | 422 на create (model_validator) |
| 4 | Submit не создаёт Item для source_document | `SELECT COUNT(*) FROM items WHERE source_system='operation_inline' AND source_ref LIKE 'tmp-%'` = 0 |
| 5 | Rename Item между create и submit | catalog snapshot обновляется на submit |
| 6 | Merge Item между create и submit | catalog snapshot обновляется на canonical |

### 11.3. Regression tests

- Все существующие тесты `test_operations_*` должны проходить без изменений
- Manual operations с temporary_item продолжают работать как раньше
- ADR-0012 (legacy TemporaryItem flow) не затрагивается

---

## 12. Definition of Ready (для передачи младшей модели)

Этот пакет можно передавать, **только если**:

- [x] Отдельный endpoint `POST /operations/from-source-document` описан (см. секцию 4.1)
- [x] Schema endpoint физически не допускает temporary_item (см. секцию 4.2)
- [x] Generic endpoint `POST /operations` НЕ используется импортёром накладных (см. секцию 11.2.3)
- [x] Все строки source-document operation обязаны иметь item_id до создания Operation (см. секцию 4.2)
- [x] Submit не создаёт Item для source-document потока (см. секцию 5.1)
- [x] Существующие snapshot-поля переиспользованы для catalog snapshot (см. секцию 4.4)
- [x] Unit/integration тесты описаны (см. секцию 11)
- [x] Описан переход текущего OCR/JSON pipeline на новый endpoint (см. секцию 13)
- [x] Отсутствуют зависимости от reopen/revision (Пакет B отдельный)

---

## 13. OCR/JSON Pipeline Migration

### 13.1. Текущие потоки импорта

| Pipeline | Endpoint | creation_source |
|---|---|---|
| LLM-агент через preimport_validator | `POST /operations` с `temporary_item` | (legacy) |
| Warehouse_web invoice import | `POST /operations` с `temporary_item` | (legacy) |
| Direct API clients (csv import) | `POST /operations` с `temporary_item` | (legacy) |

### 13.2. Migration plan

1. **Stage 1**: добавить endpoint `/from-source-document` без breaking changes
2. **Stage 2**: BFF проксирует новый endpoint, опционально
3. **Stage 3**: обновить preimport_validator.py и Warehouse_web для использования нового endpoint
4. **Stage 4**: generic endpoint остаётся для manual, но ADR рекомендует migration
5. **Stage 5** (out of scope): feature flag для enforcement на стороне server

### 13.3. preimport_validator.py updates

```python
# prod_working/preimport_validator.py — UPDATED
def main():
    ...
    for item in items:
        # ... analysis ...
        if decision == "AUTO-MATCH":
            # Используем canonical_item_id
            output_items.append({
                "item_id": candidate["id"],
                "source_item_name": item["name"],
                # НЕ передаём name в JSON
            })

    # POST to /from-source-document
    payload = {
        "operation_type": "RECEIVE",
        "site_id": ...,
        "source_ref": "ocr-...",
        "source_document_type": "ocr_scan",
        "lines": output_items,
    }
    requests.post(f"{API}/operations/from-source-document", json=payload)
```

---

## 14. Acceptance Criteria

### 14.1. Definition of Done (Пакет A)

- [x] Migration применена на dev-стенде без ошибок (alembic current = 0035, head)
- [x] Endpoint `POST /operations/from-source-document` доступен — подтверждён через curl (401 auth required, 200 при валидных токенах)
- [x] Все unit тесты проходят (40 passed)
- [x] Все integration тесты проходят (8 сценариев, 8/8 passed — scenario_5 исправлен)
- [x] Stand smoke: бизнес-сценарий 2026-08-06 — дубль НЕ создаётся (idempotency подтверждена), submit success
- [x] BFF endpoint `/bff/api/v1/operations/from-source-document` работает (код + тесты)
- [x] Offline клиенты не затронуты (manual operations работают)
- [x] Documentation обновлена: `Functional and WorkLogik.md` §VII.4
- [x] ADR-0021 зафиксирован
- [x] ADR-0019 помечен как superseded (уже сделано)

---

## 15. Rollout Plan

### 15.1. Поэтапный rollout (Пакет A)

1. **Stage 1 (dev)**: migration + endpoint + сервис. Тестирование на dev-стенде.
2. **Stage 2 (dev + BFF)**: BFF проксирование. Тестирование через Django UI.
3. **Stage 3 (staging)**: репрезентативные данные, проверка backward compat.
4. **Stage 4 (canary на prod)**: 1 склад, мониторинг 24 часа.
5. **Stage 5 (full rollout)**: все склады.

### 15.2. Feature flags (опционально)

- `FF_SOURCE_DOCUMENT_ENDPOINT` — включение нового endpoint
- `FF_PRE_SUBMIT_RESOLUTION` — pre-validation на submit для manual операций

---

## 16. Risks

| Риск | Вероятность | Влияние | Митигация |
|---|---|---|---|
| BFF не обновлён, OCR pipeline падает | Средняя | Import fails | Stage-by-stage rollout, BFF compatibility layer |
| Legacy operations классифицированы как `legacy` | Низкая | Невозможно reopen | Reopen flow поддерживает `legacy` (см. Пакет B) |
| Offline клиенты получают неожиданные 422 | Низкая | Sync fails | Offline клиенты используют manual (creation_source='manual'), не затрагиваются |
| Item был merged между create и submit | Средняя | Submit fails с 409 | UX показывает candidates для reselection |
| Source snapshot пустой для legacy | Низкая | Audit degraded | Backfill из item_name_snapshot (best effort) |

---

## 17. Evidence Table (template)

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|
| Migration apply | `python -m alembic upgrade head` | pass/fail | migration log |
| Endpoint openapi | `curl http://localhost:8000/openapi.json` | pass/fail | endpoint listing |
| Schema no temporary_item | `inspect(SourceDocumentOperationLineCreate)` | pass/fail | field listing |
| Backfill creation_source | `SELECT COUNT(*) FROM operations WHERE creation_source IS NULL` | 0 rows | query result |
| Source-document smoke | `curl POST /operations/from-source-document с реальной накладной` | pass | response |
| Submit no Item creation | `SELECT COUNT(*) FROM items WHERE source_ref='source-document-test'` | 0 rows | query result |
| Catalog snapshot freeze | integration test | pass | snapshot values |
| BFF compatibility | `curl POST /bff/api/v1/operations/from-source-document` | pass | response |

---

## 18. Открытые вопросы

1. **Cross-payload consistency**: как BFF должен обрабатывать несколько source-document'ов в одном HTTP request? (out of scope для этого TZ)
2. **Reopen для source_document operations**: какой reopen flow? (Пакет B отвечает)
3. **Item merge между source_document create и submit**: audit trail через `creation_source='source_document'` достаточен? (Требует подтверждения)
4. **Offline clients с устаревшим canonical_id**: требуется pre-sync validation (out of scope)

---

## 19. Рекомендованный порядок реализации

1. Migration (Phase 0): schema additions + backfill
2. Schemas (Phase 1): SourceDocumentOperationCreate, SourceDocumentOperationLineCreate
3. Endpoint (Phase 2): POST /operations/from-source-document
4. Service method (Phase 3): create_operation_from_source_document + _validate_source_document_line
5. Submit pipeline (Phase 4): _validate_resolved_lines_on_submit + _freeze_catalog_snapshot
6. Tests (Phase 5): unit + integration + stand smoke
7. BFF mirroring (Phase 6): Django BFF endpoint
8. Documentation (Phase 7): ARCHITECTURE.md, Functional and WorkLogik.md, API_MAP.md
9. ADR-0021 published (уже сделано)

Общий срок: 5-10 рабочих дней.

После завершения пакета A:
- Пометить TZ-V3.3_OPERATION_INTAKE_DUPLICATE_PROTECTION.md как «Phase 0 superseded» (уже сделано)
- Убедиться, что ADR-0019 помечен как superseded (уже сделано)
- Документация по ручному inline-flow остаётся актуальной (manual operations)

---

## Evidence (2026-08-06 final)

| Check | Command | Result | Note |
|---|---|---|---|
| Endpoint route | `grep routes_operations.py` | :175 confirmed | `POST /api/v1/operations/from-source-document` |
| Migrations | `ls alembic/versions` + `alembic history/current` | 0029/0030 in chain, DB at 0037 head | 0029_source_document_operation_hardening.py, 0030_source_document_idempotency_index.py |
| Unit tests | `.venv/bin/python -m pytest tests/test_source_document_endpoint.py tests/test_source_document_operation_schemas.py -q` | **40 passed** | |
| Integration | `pytest tests/integration/test_source_document_integration.py tests/integration/test_source_document_idempotency.py -q` | **8 passed** | Все сценарии, включая scenario_5 (исправлен) |
| Stand smoke - create | `curl POST /api/v1/operations/from-source-document` с токенами | **201 created** | `creation_source="source_document"`, `source_ref` проставлен, `temporary_draft_payload=null` |
| Stand smoke - idempotency | Повторный `POST` с тем же `source_ref` | **200 OK** (тот же UUID) | Idempotency подтверждена |
| Stand smoke - submit | `POST /operations/{id}/submit` | **200 OK** | `status="submitted"`, submit pipeline отработал без ошибок |
| Stand health | `GET /api/v1/health` + `GET /healthz/` | ok | SyncServer + Django |
| BFF tests | `python manage.py test apps.bff_api.tests.BffApiOperationsFromSourceDocumentTests` | 7 OK | (предыдущий прогон 2026-07-31) |
| Documentation | `Functional and WorkLogik.md` §VII.4 | updated | Source-document flow описан |