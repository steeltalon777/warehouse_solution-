# ADR-0023: Operation Correction by Immutable OperationRevision

## Status

Proposed (revision после архитектурной корректировки)

## Date

2026-07-21 (v1 отозван)
2026-07-21 (v2: с immutable OperationRevision model)

## Context

Пакет C (correction-by-diff) был отправлен на доработку по 5 архитектурным блокерам (TZ-C v1, ADR-0023 v1):

1. **Нет immutable storage для history** — TZ-C v1 хранил историю через mutable `OperationLine.id` (autoincrement, нестабильный между revisions) и предлагал `get_lines_by_revision` поверх тех же mutable строк.
2. **Client-side correction_kind** — клиент мог передавать `correction_kind`, что смешивает intent с computation.
3. **Partial PATCH semantics** — отсутствие строки в PATCH могло означать "removed" или "unchanged", что неоднозначно.
4. **Empty correction draft** — begin correction возвращал пустой draft, что не давало baseline context.
5. **`base_document_id` linkage** — correction был привязан к конкретному документу, а не к revision операции.
6. **Statuses обещают failed** — но failed транзакция откатывается, обещание невыполнимо.
7. **V1 scope не определён** — весь effect-diff matrix в TZ-C v1, без приоритизации.

ADR-0023 v2 вводит immutable `OperationRevision` / `OperationRevisionLine` как единственный источник истины для history. `OperationLine` остаётся как **current projection** для совместимости с существующим API.

## Decision

### Решение 1: OperationRevision — immutable entity

```python
class OperationRevision(Base):
    __tablename__ = "operation_revisions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    operation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("operations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    created_by_correction_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("operation_corrections.id"),
        nullable=True,  # NULL для initial submit
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # IMMUTABLE: нет updated_at, нет version. Update запрещён на уровне repo.

    __table_args__ = (
        UniqueConstraint("operation_id", "revision_number", name="uq_operation_revisions_op_rev"),
    )
```

```python
class OperationRevisionLine(Base):
    __tablename__ = "operation_revision_lines"

    revision_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("operation_revisions.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    line_uuid: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        # server_default НЕ используется (см. ADR-0023 Решение 11)
    )

    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    item_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("items.id"))
    inventory_subject_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("inventory_subjects.id")
    )

    qty: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    accepted_qty: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=0)
    lost_qty: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=0)
    batch: Mapped[str | None] = mapped_column(String(100))
    comment: Mapped[str | None] = mapped_column(Text)

    # Source snapshots (от исходного документа, передаётся явно для added lines)
    source_item_name: Mapped[str | None] = mapped_column(String(255))
    source_item_sku: Mapped[str | None] = mapped_column(String(100))
    source_unit_name: Mapped[str | None] = mapped_column(String(100))
    source_category_name: Mapped[str | None] = mapped_column(String(255))

    # Catalog snapshots (frozen at submit)
    item_name_snapshot: Mapped[str | None] = mapped_column(String(255))
    item_sku_snapshot: Mapped[str | None] = mapped_column(String(100))
    unit_name_snapshot: Mapped[str | None] = mapped_column(String(100))
    unit_symbol_snapshot: Mapped[str | None] = mapped_column(String(20))
    category_name_snapshot: Mapped[str | None] = mapped_column(String(255))
```

### Решение 2: Operation.current_revision_id

```python
class Operation(Base):
    # EXISTING + NEW
    current_revision_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("operation_revisions.id"),
        nullable=True,  # nullable для legacy операций
    )
```

`current_revision_id` указывает на текущую применённую revision. При initial submit устанавливается на созданную revision 0. При correction submit обновляется на revision N+1.

### Решение 3: Document.operation_revision_id

```python
class Document(Base):
    # EXISTING + NEW
    operation_revision_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("operation_revisions.id"),
        nullable=True,
    )
```

Документ знает, из какой revision создан. Это позволяет генерировать документы из `OperationRevisionLine` (immutable source), а не из `OperationLine` (mutable projection).

### Решение 4: OperationLine остаётся current projection

`OperationLine` остаётся для backward-compatibility с существующим API и запросами, но перестаёт быть источником истории. После correction:

```python
async def submit_correction(...):
    # 1. Создать immutable OperationRevision N+1 (snapshot нового состояния)
    new_revision = await create_operation_revision(
        operation_id=correction.operation_id,
        revision_number=correction.base_revision.revision_number + 1,
        created_by_user_id=user_id,
        created_by_correction_id=correction.id,
        lines=final_state_lines,  # из corrected baseline
    )

    # 2. В ТОЙ ЖЕ транзакции: rebuild mutable OperationLine current projection
    await uow.operations.delete_operation_lines(correction.operation_id)
    for line in final_state_lines:
        await uow.operations.create_operation_line(...)

    # 3. Update current_revision_id
    operation.current_revision_id = new_revision.id

    # 4. Apply delta effects (immutable history through OperationRevisionLine)
    ...
```

History хранится **только** в `OperationRevisionLine`. `OperationLine` — кэш/projection для API.

### Решение 5: OperationCorrection — simplified model

```python
class OperationCorrection(Base):
    __tablename__ = "operation_corrections"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    operation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("operations.id", ondelete="RESTRICT"),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="draft",
    )
    # 'draft' | 'applied' | 'abandoned' (БЕЗ failed/submitted)

    # REMOVED: base_document_id, base_document_revision
    # NEW: привязка к OperationRevision (НЕ к конкретному документу)
    base_operation_revision_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("operation_revisions.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # Optimistic locking
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1", default=1,
    )

    # Idempotency (отдельно от client_request_id на Operation)
    idempotency_key: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
    )

    # Snapshot of source_ref на момент begin (для audit)
    source_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now())
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'applied', 'abandoned')",
            name="ck_operation_corrections_status",
        ),
        # Partial unique index: одна active draft на operation
        Index(
            "uq_active_correction_per_operation",
            "operation_id",
            unique=True,
            postgresql_where=sa.text("status = 'draft'"),
        ),
        Index("ix_operation_corrections_operation_id", "operation_id"),
    )
```

### Решение 6: OperationCorrectionLine — server-generated line_uuid для added lines

```python
class OperationCorrectionLine(Base):
    __tablename__ = "operation_correction_lines"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    correction_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("operation_corrections.id", ondelete="CASCADE"),
        nullable=False,
    )
    line_uuid: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # TARGET STATE (только целевое состояние; correction_kind НЕ хранится здесь)
    item_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("items.id"))
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    batch: Mapped[str | None] = mapped_column(String(100))
    comment: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("correction_id", "line_uuid", name="uq_correction_lines_line_uuid"),
    )
```

**`correction_kind` НЕ хранится в OperationCorrectionLine.** Он вычисляется сервером при submit на основе сравнения с baseline.

**Added lines получают server-generated `line_uuid`** через `uuid.uuid4()` в `create_operation_correction_line`.

### Решение 7: статусная модель — только три состояния

```
draft      → correction создана, можно редактировать
applied    → correction успешно применена
abandoned  → correction отменена пользователем
```

**Failure correction остаётся в `draft`**, никаких effects не меняется (UoW rollback). Сервер возвращает 409/422.

Если нужен аудит неудачных submit попыток, это отдельная задача (для V1 не требуется, не входит в этот ADR).

### Решение 8: safe-delete policy — explicit matrix

| Correction kind | Baseline Item state | New Item state | Allowed? | Pre-validation |
|---|---|---|---|---|
| `unchanged` | active / soft-deleted | — (не меняется) | ✅ | — (нет effect) |
| `metadata_changed` | active / soft-deleted | — (не меняется) | ✅ | — (нет effect) |
| `quantity_changed_same_item` (+ qty) | active / soft-deleted | — (не меняется) | ✅ | item valid (active или soft-deleted) |
| `quantity_changed_same_item` (- qty) | active | — (не меняется) | ✅ | item valid, sufficient balance |
| `quantity_changed_same_item` (- qty) | soft-deleted | — | ❌ | root-only с effect validation |
| `removed` | active | — | ✅ | sufficient balance check |
| `removed` | soft-deleted | — | ⚠️ | проверять available balance (legacy can have остатки) |
| `item_replaced` | active | active | ✅ | both valid, sufficient balance на old |
| `item_replaced` | soft-deleted | active | ❌ | reversal невозможен на deleted item |
| `item_replaced` | active | soft-deleted / inactive | ❌ | new Item must be active |
| `added` | — | active | ✅ | item valid |
| `added` | — | soft-deleted / inactive | ❌ | new Item must be active |

**Правило:** `added` и `item_replaced` (new side) требуют **active** Item (`is_active=True, deleted_at IS NULL`). Все остальные случаи допускают soft-deleted на baseline side с проверками.

**Правило:** Любая negative delta (removed, quantity reduction, item_replaced old side) требует проверки текущего остатка на `inventory_subject_id` (или соответствующего register).

### Решение 9: V1 scope — только RECEIVE без acceptance

**V1 принимает:**
- `operation_type = "RECEIVE"` (только)
- `acceptance_required = false` (только)
- Kinds: `metadata_changed`, `quantity_changed_same_item`, `item_replaced`, `added`, `removed`
- `unchanged` (no-op, но допустимо как явный kind)

**V1 НЕ принимает (отдельные фазы):**

| Фаза | Scope |
|---|---|
| C2 | RECEIVE с acceptance_required, без accepted/lost changes |
| C3 | EXPENSE, WRITE_OFF (warehouse) |
| C4 | MOVE |
| C5 | ISSUE, ISSUE_RETURN |
| C6 | Acceptance accepted/lost corrections |
| C7 | ADJUSTMENT |
| C8 | WRITE_OFF (issue_object) |

**V1 принимает acceptance invariants** для будущих фаз:
```
new_qty >= accepted_qty + lost_qty
new_pending = new_qty - accepted_qty - lost_qty
pending_delta = new_pending - old_pending
```

В V1 `accepted_qty` и `lost_qty` не изменяются (для non-acceptance RECEIVE они всегда 0).

**Если correction target operation_type не в V1 scope:** return `correction_operation_type_not_supported`.

### Решение 10: correction_kind вычисляется на submit

```python
@staticmethod
async def _compute_correction_diff(
    baseline: list[OperationRevisionLine],
    correction: list[OperationCorrectionLine],
) -> CorrectionDiff:
    """Вычислить diff на submit. correction_kind НЕ передаётся клиентом."""
    baseline_by_uuid = {l.line_uuid: l for l in baseline}
    correction_by_uuid = {l.line_uuid: l for l in correction}

    unchanged, metadata_changed, quantity_changed, item_replaced, added, removed = [], [], [], [], [], []

    for uuid in baseline_by_uuid.keys() & correction_by_uuid.keys():
        bl, cl = baseline_by_uuid[uuid], correction_by_uuid[uuid]
        if bl.item_id != cl.item_id:
            item_replaced.append((bl, cl))
        elif bl.qty != cl.qty:
            quantity_changed.append((bl, cl))
        elif bl.batch != cl.batch or bl.comment != cl.comment:
            metadata_changed.append((bl, cl))
        else:
            unchanged.append((bl, cl))

    for line in correction:  # new line_uuids
        if line.line_uuid not in baseline_by_uuid:
            added.append(line)
    for uuid in baseline_by_uuid.keys() - correction_by_uuid.keys():
        removed.append(baseline_by_uuid[uuid])

    return CorrectionDiff(
        unchanged=unchanged,
        metadata_changed=metadata_changed,
        quantity_changed=quantity_changed,
        item_replaced=item_replaced,
        added=added,
        removed=removed,
    )
```

### Решение 11: line_uuid migration (2-step)

**Не использовать UUID5** из бизнес-полей. Не использовать `server_default=uuid4()`.

```python
# Migration A: ADD NULLABLE
op.add_column("operation_revision_lines", sa.Column("line_uuid", PGUUID, nullable=True))
op.add_column("operation_lines", sa.Column("line_uuid", PGUUID, nullable=True))

# Backfill (отдельный Python-скрипт):
# Для каждой legacy строки: random UUID через uuid.uuid4()
# Не использовать uuid.uuid5 (не детерминированно для разных баз)
# Не использовать server_default (отключен для legacy)

# Migration B: SET NOT NULL + UNIQUE
op.alter_column("operation_revision_lines", "line_uuid", nullable=False)
op.alter_column("operation_lines", "line_uuid", nullable=False)
op.create_unique_constraint("uq_orl_line_uuid", "operation_revision_lines", ["line_uuid"])
op.create_unique_constraint("uq_ol_line_uuid", "operation_lines", ["line_uuid"])

# Либо доказать возможность одной транзакционной migration с gen_random_uuid()
# (PostgreSQL поддерживает pgcrypto extension; требует verification)
```

### Решение 12: документы генерируются из OperationRevisionLine

```python
@staticmethod
async def generate_revision_document(
    uow, operation, revision, document_type,
):
    """Сгенерировать документ из immutable OperationRevisionLine."""
    revision_lines = await uow.revisions.get_lines(revision.id)
    payload = DocumentService._build_payload_from_revision_lines(
        operation=operation,
        revision=revision,
        revision_lines=revision_lines,
        document_type=document_type,
    )
    document = Document(
        operation_revision_id=revision.id,  # ← НОВОЕ
        payload=payload,
        payload_hash=SHA256(payload),
        ...
    )
    return document
```

**Snapshots policy:**

| Correction kind | Source snapshot | Catalog snapshot |
|---|---|---|
| `unchanged` | inherit from baseline | inherit from baseline (OperationRevisionLine N) |
| `metadata_changed` | inherit from baseline | inherit from baseline |
| `quantity_changed_same_item` | inherit from baseline | freeze from current canonical at submit |
| `item_replaced` | inherit from baseline | freeze new Item from current canonical |
| `added` | inherit from baseline (если есть) | freeze new Item from current canonical |
| `removed` | inherit from baseline | inherit from baseline |

**Для unchanged/metadata-only/quantity_changed** с soft-deleted baseline Item: catalog snapshot наследуется из baseline revision (не читаем live catalog).

### Решение 13: cancel после correction

**Проблема:** если correction прошла, current projection содержит cumulative state. Cancel должен отменить cumulative state, не только initial.

**Решение V1:** существующий `cancel_operation` использует current `OperationLine` projection. Если projection обновлена после correction, cancel отменяет cumulative state. Это работает корректно, **ЕСЛИ** projection всегда синхронизирована с revision.

**Тест:**
```
RECEIVE +100 → revision 0 (qty=100)
correction +20 → revision 1 (qty=120) — added line
correction -10 → revision 2 (qty=110) — quantity reduction
cancel → отменяет revision 2 cumulative state
final balance = state before initial operation
```

**Если projection рассинхронизирована с revision** (из-за ошибки в submit_correction) — cancel работает неправильно. Это покрывается тестом `cancel after multiple corrections restores pre-operation state`.

**V1 не требует отдельного cumulative reversal через revision chain.** Если тест покажет проблемы, описать отдельный ADR.

### Решение 14: API contracts

#### Begin correction — клонирование baseline

```http
POST /api/v1/operations/{operation_id}/corrections
```

```json
// Response
{
  "id": "uuid-correction",
  "operation_id": "uuid-operation",
  "status": "draft",
  "base_operation_revision_id": "uuid-revision-0",
  "base_operation_revision_number": 0,
  "version": 1,
  "lines": [
    {
      "line_uuid": "uuid-1",
      "line_number": 1,
      "item_id": 3186,
      "qty": 100,
      "batch": "LOT-A",
      "comment": null
    },
    {
      "line_uuid": "uuid-2",
      "line_number": 2,
      "item_id": 4102,
      "qty": 5,
      "batch": null,
      "comment": null
    }
  ]
}
```

**Correction draft не пустой** — все baseline lines скопированы.

#### Update correction — PUT full target state или command endpoints

**PUT full target state:**
```http
PUT /api/v1/operations/{operation_id}/corrections/{correction_id}
{
  "expected_version": 1,
  "lines": [
    {
      "line_uuid": "uuid-1",
      "line_number": 1,
      "item_id": 3186,
      "qty": 120,
      "batch": "LOT-A",
      "comment": "исправление"
    },
    {
      "line_uuid": "uuid-new-1",
      "line_number": 2,
      "item_id": 4200,
      "qty": 10,
      "batch": null,
      "comment": null
    }
  ]
}
```

**Отсутствие строки в PUT = REMOVED** (явно). Это полный target state, а не partial PATCH.

**Альтернатива: command endpoints (PATCH line, POST line, DELETE line)** — для incremental UI edits:

```http
PATCH /operations/{id}/corrections/{cid}/lines/{line_uuid}
{
  "expected_version": 1,
  "qty": 120
}

POST /operations/{id}/corrections/{cid}/lines
{
  "line_number": 3,
  "item_id": 4200,
  "qty": 10,
  "batch": null,
  "comment": null
}

DELETE /operations/{id}/corrections/{cid}/lines/{line_uuid}
{
  "expected_version": 1
}
```

DELETE устанавливает `correction_lines.deleted_at` (soft delete) или удаляет row. Рекомендуется: soft delete для audit.

**Не использовать partial PATCH списка строк** — неоднозначно.

#### Submit correction

```http
POST /api/v1/operations/{operation_id}/corrections/{correction_id}/submit
{
  "expected_version": 1,
  "idempotency_key": "uuid-or-string"
}
```

```json
// Response
{
  "correction": {
    "id": "uuid-correction",
    "status": "applied",
    "applied_at": "2026-07-21T15:00:00Z"
  },
  "operation": {
    "id": "uuid-operation",
    "status": "submitted",
    "current_revision_id": "uuid-revision-1",
    "current_revision_number": 1,
    "correction_count": 1,
    "last_corrected_at": "2026-07-21T15:00:00Z",
    "version": 3
  },
  "new_operation_revision": {
    "id": "uuid-revision-1",
    "revision_number": 1,
    "lines": [...]
  },
  "new_documents": [
    {
      "id": "uuid-doc-1",
      "document_type": "waybill",
      "revision": 1,
      "status": "finalized",
      "operation_revision_id": "uuid-revision-1",
      "supersedes_document_id": "uuid-doc-0"
    },
    {
      "id": "uuid-doc-2",
      "document_type": "acceptance_certificate",
      ...
    }
  ],
  "computed_diff": {
    "unchanged": [{"line_uuid": "uuid-1"}],
    "metadata_changed": [],
    "quantity_changed": [{"line_uuid": "uuid-2", "old_qty": 5, "new_qty": 10}],
    "item_replaced": [],
    "added": [],
    "removed": []
  }
}
```

Если validation fails:
```json
// HTTP 422
{
  "code": "correction_delta_validation_failed",
  "correction_id": "uuid",
  "correction_status": "draft",  // остаётся draft
  "delta": {
    "line_uuid": "uuid",
    "kind": "removed",
    "diff_qty": -100,
    "current_balance": 50
  },
  "reason": "insufficient_balance"
}
```

### Решение 15: lock order

```python
async def submit_correction(uow, correction_id, user_id):
    correction = await uow.corrections.get_for_update(correction_id)
    # Lock 1: Correction

    operation = await uow.operations.get_operation_by_id_for_update(correction.operation_id)
    # Lock 2: Operation

    affected_subjects = collect_affected_inventory_subjects(correction.lines)
    for subject_id in sorted(affected_subjects):  # ASC order
        await uow.inventory_subjects.get_for_update(subject_id)
    # Lock 3: inventory_subjects в ASC order

    for line in correction.lines:
        await uow.balances.get_for_update(site_id, inventory_subject_id)
    # Lock 4: balances/registers

    # Generate documents (Lock 5 если нужны)
    ...
```

**Фиксированный lock order критичен** для предотвращения deadlock при параллельных correction.

### Решение 16: документ revisions per operation_revision

```python
# Correction submit:
async def _supersede_documents_for_revision(uow, operation, new_revision):
    """Для каждого document_type:
    1. Найти active finalized document текущей OperationRevision
    2. Создать successor для новой OperationRevision (draft/finalize)
    3. Только после успешного создания всех successor перевести старые в superseded
    """
    document_types = ["waybill", "acceptance_certificate", "act", "invoice"]

    for doc_type in document_types:
        old_doc = await uow.documents.get_active_for_revision(
            operation_id=operation.id,
            operation_revision_id=operation.current_revision_id,
            document_type=doc_type,
        )
        if old_doc is None:
            # Документа этого типа ещё нет (например, act для RECEIVE)
            continue
        new_doc = await uow.documents.create_document(
            operation_revision_id=new_revision.id,
            document_type=doc_type,
            revision=old_doc.revision + 1,
            supersedes_document_id=old_doc.id,
            payload=generate_payload_from_revision(new_revision),
            ...
        )

    # Только после успешного создания всех successor перевести старые
    for doc_type in document_types:
        old_doc = await uow.documents.get_active_for_revision(
            operation_id=operation.id,
            operation_revision_id=operation.current_revision_id,
            document_type=doc_type,
        )
        if old_doc is not None:
            await uow.documents.update_document_status(old_doc.id, "superseded")
```

**Атомарность:** все create + update в одной UoW transaction.

## Альтернативы, рассотренённые

### A. TZ-C v1 (mutable OperationLine как history)

- **Минусы**: history хранится в mutable projection, невозможно гарантировать immutability
- **Решение**: отклонено. ADR-0023 v2 вводит immutable OperationRevisionLine

### B. Хранить history в audit_events.changes JSONB

- **Минусы**: нет типизации, сложно query, нет FK integrity
- **Решение**: отклонено. OperationRevisionLine — typed storage

### C. correction_kind на уровне request (от клиента)

- **Минусы**: client-server coupling, риск inconsistency
- **Решение**: отклонено. Kind вычисляется сервером

### D. Partial PATCH со списком строк

- **Минусы**: неоднозначная семантика (отсутствие = removed или unchanged?)
- **Решение**: отклонено. PUT full target state или command endpoints

### E. Empty correction draft (отдельное заполнение)

- **Минусы**: требует GET baseline, лишний round-trip, риск inconsistency
- **Решение**: отклонено. Begin correction клонирует baseline

### F. Status 'failed' для correction

- **Минусы**: failed транзакция откатывается, статус не сохраняется
- **Решение**: отклонено. Validation failure → correction остаётся draft

## Consequences

### Positive

- Immutable `OperationRevisionLine` гарантирует auditability истории
- `OperationLine` остаётся current projection для совместимости
- Клиент не передаёт `correction_kind` — server computes deterministically
- PUT full state устраняет неоднозначность
- 3-state model (draft/applied/abandoned) исключает failed обещание
- Partial unique index предотвращает concurrent corrections
- Lock order предотвращает deadlock
- Documents привязаны к operation_revision_id — генерируются из immutable source

### Negative

- Schema changes: 2 новые таблицы (operation_revisions, operation_revision_lines)
- 2-step migration для line_uuid
- Текущий `cancel_operation` может потребовать доработки для cumulative reversal
- Document generation переписан с `OperationLine` на `OperationRevisionLine`
- V1 scope ограничен RECEIVE без acceptance

### Neutral

- ADR-0022 (reopen) остаётся Needs redesign
- Пакет A (source-document) независим и готов

## Compliance

### Functional and WorkLogik.md

- §VII.1 — накладная может быть скорректирована через correction
- §IX — инлайн создание не затрагивается (manual operations)

### ADR-0012 (Deprecate Temporary Items)

- Не затрагивается.

### ADR-0016 (Offline Sync)

- Offline клиенты НЕ используют correction (root-only online flow)

## Confidence

Medium-High. ADR-0023 v2 устраняет основные блокеры v1. Остаются вопросы: cumulative cancel через revision chain, scaling corrections, UI для diff view.

## Related

- TZ-OPERATION_CORRECTION_BY_DIFF (детальный TZ с V1 scope)
- ADR-0022.superseded (отменён)
- TZ-OPERATION_REOPEN_AND_DOCUMENT_REVISION.md (Needs redesign)
- TZ-SOURCE_DOCUMENT_OPERATION_INTAKE_HARDENING (Пакет A — независимый, готов)
- ADR-0021 (Пакет A)