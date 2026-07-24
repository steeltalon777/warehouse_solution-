# TZ-OPERATION_CORRECTION_BY_DIFF

> **REVISION 2 (после архитектурной корректировки)** — основные изменения:
>
> 1. **Immutable `OperationRevision` + `OperationRevisionLine`** — основной storage истории. `OperationLine` остаётся как current projection.
> 2. **`Operation.current_revision_id`** + **`Document.operation_revision_id`** — указатели на revision.
> 3. **3-state correction**: draft / applied / abandoned (без failed/submitted).
> 4. **Client doesn't pass `correction_kind`** — сервер вычисляет на submit.
> 5. **PUT full target state** (не partial PATCH) + command endpoints как альтернатива.
> 6. **Begin correction клонирует baseline** (не пустой draft).
> 7. **V1 scope ограничен**: только RECEIVE без acceptance_required.
> 8. **line_uuid migration 2-step** (add nullable → backfill random → set NOT NULL UNIQUE).

## TZ References

- Корректирующая директива: 2026-07-21 (revision 2)
- ADR-0023: Operation Correction by Immutable OperationRevision (revised)
- Superseded: TZ-C v1 (440 строк с mutable OperationLine approach)
- `Functional and WorkLogik.md` §VII (накладные), §IX.9 (инлайн)
- ADR-0012 (Deprecate Temporary Items — сохраняется)
- ADR-0018 (Audit Architecture)

## Execution Strategy

- [x] 🔴 **Sequential execution required**
- **Reason:** immutable OperationRevision требует новой схемы + 2-step migration. Document generation переписывается с OperationLine на OperationRevisionLine. Каждая фаза зависит от предыдущей. Lock order критичен для предотвращения deadlock.

---

## Execution Checklist

- [x] 0. Context verified — обследование immutable storage и document generation
- [x] 1. Architecture boundaries confirmed — SyncServer source of truth
- [x] 2. Migration A: add nullable line_uuid (0031) — applied on dev-stand
- [x] 3. Backfill line_uuid (0032, gen_random_uuid) — applied on dev-stand
- [x] 4. Migration B: SET NOT NULL + UNIQUE (0033) — applied on dev-stand
- [x] 5. Repo: OperationRevisionsRepo (CRUD, immutable, update запрещён)
- [x] 6. Repo: CorrectionsRepo (version + idempotency_key + partial unique)
- [x] 7. Service: submit_operation (создаёт revision 0/N+1 после restore)
- [x] 8. Service: begin_correction (клонирует baseline, partial unique reject)
- [x] 9. Service: update_correction (PUT full / command endpoints)
- [x] 10. Service: _compute_correction_diff (server-side kind computation)
- [x] 11. Service: _validate_delta (safe-delete matrix V1) — 🔴 FIXED rev.2: _validate_new_item заменён на рабочий async; item_replaced проверяет полный old_qty
- [x] 12. Service: submit_correction (atomic, immutable revision create, lock order) — 🔴 FIXED rev.2: idempotent retry (INV-C13), _collect_affected_subjects реализован, документы без try/except
- [x] 13. Document: OperationRevisionLine вместо OperationLine (INV-C16) — 🔴 FIXED rev.2: operation_revision_id прокинут в generate_from_operation
- [x] 14. Document: operation_revision_id FK + supersede chain — 🔴 FIXED rev.2: новые документы создаются, старые supersede'ятся, audit пишется
- [x] 15. Endpoints: begin + PUT + POST/PATCH/DELETE line + submit + DELETE abandon + GET draft + root-only auth — REVIEW: исправлено rev.2
- [x] 16. Audit events: operation.correction.{applied,abandoned} + document.revision_created + document.superseded — 🔴 FIXED rev.2
- [x] 17. Cancel after correction — 4 unit tests (cancel after correction, cancel without correction, abandon+resubmit, draft rejection)
- [x] 18. Unit tests: 22 теста (mock-based) pass; полный прогон reviewer'ом 2026-07-24: 656 passed, 3 skipped, 7 xfailed, 13 deselected (stand), 709s — регрессий нет
- [ ] 19. Integration tests: 7 scenarios; import fixed (from main import create_app); require dedicated test DB — 🟡 REVIEW 2026-07-24: починено rev.2
- [x] 20. Concurrency tests: 5 unit tests (version conflicts, status transitions, abandon+submit) — REVIEW note: mock-based, реальную DB-concurrency не проверяют; partial unique + version conflict проверены reviewer'ом live на стенде (409)
- [x] 21. Documentation: ARCHITECTURE.md (data model + correction flow + principles), Functional and WorkLogik.md (section II.6.8.1)
- [ ] 22. Final acceptance review: 🔴 REJECTED 2026-07-24 → 🔄 FIXED rev.2 (4 блокера устранены). Требуется повторное ревью.

---

## 1. Problem Statement

### 1.1. Целевой продуктовый сценарий

Root может частично скорректировать проведённую RECEIVE накладную:
- Изменить количество одной строки (qty 100 → 120, delta +20)
- Добавить новую строку (added line, delta +qty)
- Удалить ошибочную строку (removed, delta -qty)
- Заменить Item в одной строке (item_replaced: reversal old + apply new)
- Исправить batch/comment (metadata_changed, no effect)

Без:
- Отката effects для unchanged строк
- Блокировки от downstream operations
- Потери audit trail

### 1.2. V1 scope (обязательное ограничение)

**V1 принимает:**
- `operation_type = "RECEIVE"` (только)
- `acceptance_required = false` (только)
- Kinds: `metadata_changed`, `quantity_changed_same_item`, `item_replaced`, `added`, `removed`, `unchanged`

**V1 НЕ принимает** (отдельные фазы C2..C8):

| Фаза | Scope | Когда |
|---|---|---|
| C2 | RECEIVE с acceptance_required, без accepted/lost changes | После V1 |
| C3 | EXPENSE, WRITE_OFF (warehouse) | После C2 |
| C4 | MOVE | После C3 |
| C5 | ISSUE, ISSUE_RETURN | После C4 |
| C6 | Acceptance accepted/lost corrections | После C2 |
| C7 | ADJUSTMENT | После C3 |
| C8 | WRITE_OFF (issue_object) | После C5 |

**Если correction target operation_type не в V1 scope:** `correction_operation_type_not_supported` (HTTP 422).

### 1.3. Acceptance invariants (для будущих фаз C2..C6)

Зафиксировать заранее:

```
new_qty >= accepted_qty + lost_qty
new_pending = new_qty - accepted_qty - lost_qty
pending_delta = new_pending - old_pending
```

**В V1** `accepted_qty` и `lost_qty` всегда 0 (RECEIVE без acceptance), `pending_delta` не применяется.

**Изменение accepted/lost в V1 запрещено** (только root-only с effect validation в будущей C6).

---

## 2. Verified Current Architecture

### 2.1. OperationLine (current, становится projection)

```python
# models/operation.py:240-352
class OperationLine(Base):
    id: int (BigInteger PK, autoincrement)
    operation_id, line_number, item_id, inventory_subject_id
    qty, accepted_qty, lost_qty, batch, comment
    item_name_snapshot, item_sku_snapshot, unit_name_snapshot, unit_symbol_snapshot, category_name_snapshot
    temporary_draft_payload: dict | None
```

**Подтверждено**: `id` autoincrement, не стабильный. `OperationLine` остаётся mutable для backward compat, но теряет роль source of truth для history.

### 2.2. Operation (current)

```python
# models/operation.py:25-237
class Operation(Base):
    id: UUID PK
    site_id, source_site_id, destination_site_id
    operation_type, status, version
    correction_count (TZ-C v1), last_corrected_at (TZ-C v1)
```

**Подтверждено**: нет `current_revision_id` — НОВОЕ поле.

### 2.3. Document model (current)

```python
# models/document.py
class Document(Base):
    id, document_number, revision, status, supersedes_document_id
    payload, payload_hash, void_reason (TZ-B), finalized_at
    template_name, template_version, payload_schema_version
```

**Подтверждено**: нет `operation_revision_id` — НОВОЕ поле.

### 2.4. audit_item_effects (current)

```python
# models/audit_item_effect.py
class AuditItemEffect(Base):
    audit_event_id (FK RESTRICT)
    operation_id (FK SET NULL)
    inventory_subject_id (FK RESTRICT)
    item_id (FK RESTRICT)
    site_id (FK SET NULL)
    quantity_before, quantity_delta, quantity_after
    effect_type: 'receipt' | 'expense' | ...
```

**Подтверждено**: используется для delta effects. Без изменений.

### 2.5. Document generation (current)

```python
# document_service.py:504-517
for line in operation.lines:
    line_data = {
        "item_name": line.item_name_snapshot or "",
        "item_sku": line.item_sku_snapshot or "",
        ...
    }
```

**Подтверждено**: документ генерируется из mutable OperationLine. После revision — должен генерироваться из immutable OperationRevisionLine.

### 2.6. submit_operation (current)

```python
# operations_service.py:1224-1543
async def submit_operation(uow, operation_id, user_id, expected_version=None):
    # ... effects ...
    # submit document generation
    await DocumentService.generate_from_operation(...)
    # status transition: draft → submitted
    operation.status = "submitted"
```

**Подтверждено**: должен дополнительно создавать `OperationRevision 0`.

### 2.7. cancel_operation (current)

```python
# operations_service.py:1788-2052
async def cancel_operation(uow, operation_id, user_id, reason=None):
    if operation.status == "submitted":
        for line in operation.lines:
            # rollback effects
            ...
```

**Подтверждено**: cancel работает с current OperationLine projection. После correction projection обновлена, cancel отменяет cumulative state.

---

## 3. Product Invariants

### 3.1. Обязательные инварианты

```
INV-C1:  OperationRevision и OperationRevisionLine immutable после создания.
INV-C2:  OperationLine — current projection, мутабельна для API совместимости.
INV-C3:  Operation.current_revision_id указывает на активную revision.
INV-C4:  Document.operation_revision_id указывает, из какой revision создан документ.
INV-C5:  Initial submit создаёт revision 0.
INV-C6:  Correction submit создаёт revision N+1.
INV-C7:  Correction draft начинается со всех baseline lines (не пустой).
INV-C8:  Client не передаёт correction_kind (вычисляется сервером на submit).
INV-C9:  PUT full target state или command endpoints (PATCH/POST/DELETE line).
INV-C10: Status: draft | applied | abandoned (без failed/submitted).
INV-C11: Validation failure → correction остаётся draft, эффекты не меняются.
INV-C12: Correction.version + expected_version для optimistic locking.
INV-C13: Correction.idempotency_key для retry safety.
INV-C14: Новый Item для added/replaced: active, deleted_at IS NULL.
INV-C15: Любая negative delta требует проверки текущего остатка.
INV-C16: Document generation читает из OperationRevisionLine (НЕ из OperationLine).
INV-C17: Document supersede: per-document_type, atomic с revision create.
INV-C18: Lock order: Correction → Operation → inventory_subject_id ASC → balances → Documents.
INV-C19: Partial unique index: одна active draft на operation.
INV-C20: line_uuid мигрируется random UUID (не UUID5, не server_default).
```

### 3.2. НЕ покрывается этим TZ

- Source-document hardening — Пакет A (готов)
- Full reversal — отменён (ADR-0022)
- C2..C8 phases (acceptance, MOVE, ISSUE, ADJUSTMENT) — отдельные фазы
- Cumulative cancel через revision chain — out of scope V1, требует отдельного ADR если тест покажет проблемы
- UI для diff view — отдельный TZ
- Cross-operation correction (multi-source-document) — out of scope

---

## 4. Target Architecture

### 4.1. Domain model — immutable OperationRevision

```python
# models/operation.py — NEW
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

    # IMMUTABLE: нет updated_at, нет version.
    # Update запрещён на уровне repo (raise NotImplementedError на update).

    __table_args__ = (
        UniqueConstraint("operation_id", "revision_number", name="uq_operation_revisions_op_rev"),
    )


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

    # Source snapshots (для added lines с source-document)
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


class Operation(Base):
    # EXISTING + NEW
    current_revision_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("operation_revisions.id"),
        nullable=True,  # nullable для legacy операций
    )
```

### 4.2. OperationCorrection — simplified model

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
        String(16), nullable=False, default="draft",
    )
    # 'draft' | 'applied' | 'abandoned' (БЕЗ failed/submitted)

    base_operation_revision_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("operation_revisions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # REMOVED: base_document_id, base_document_revision (v1)

    version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1", default=1,
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(100), nullable=True)

    created_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now())
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # REMOVED: failure_reason, failure_code (v1)

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'applied', 'abandoned')",
            name="ck_operation_corrections_status",
        ),
        # Partial unique index: одна active draft на operation (v2 ADR-0023 Решение 5)
        Index(
            "uq_active_correction_per_operation",
            "operation_id",
            unique=True,
            postgresql_where=sa.text("status = 'draft'"),
        ),
        Index("ix_operation_corrections_operation_id", "operation_id"),
    )


class OperationCorrectionLine(Base):
    __tablename__ = "operation_correction_lines"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    correction_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("operation_corrections.id", ondelete="CASCADE"),
        nullable=False,
    )
    line_uuid: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    # REMOVED: correction_origin_line_uuid (v1) — вычисляется на submit
    # REMOVED: correction_kind (v1) — вычисляется на submit
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # TARGET STATE (только целевое; kind вычисляется сервером)
    item_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("items.id"))
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    batch: Mapped[str | None] = mapped_column(String(100))
    comment: Mapped[str | None] = mapped_column(Text)

    # Snapshots НЕ хранятся здесь — вычисляются на submit из canonical catalog

    __table_args__ = (
        UniqueConstraint("correction_id", "line_uuid", name="uq_correction_lines_line_uuid"),
    )
```

### 4.3. Document — operation_revision_id FK

```python
class Document(Base):
    # EXISTING + NEW
    operation_revision_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("operation_revisions.id"),
        nullable=True,
    )
```

### 4.4. Domain model visualization

```
Operation (status="submitted", current_revision_id=uuid-N)
    │
    ├── OperationRevision (revision_number=N, immutable)
    │       ├── created_by_correction_id = NULL (initial) или uuid-correction (correction submit)
    │       └── OperationRevisionLine[]
    │               ├── line_uuid (стабильный)
    │               ├── item_id, qty, snapshot fields
    │               └── IMMUTABLE
    │
    ├── OperationRevision (revision_number=N+1, immutable)  -- correction 1
    │       └── OperationRevisionLine[]  -- cumulative state after correction
    │
    ├── Document (status="finalized", revision=N, operation_revision_id=uuid-N)
    └── Document (status="superseded", revision=N, operation_revision_id=uuid-N)  -- after correction
            ↓ superseded
    Document (status="finalized", revision=N+1, operation_revision_id=uuid-(N+1),
             supersedes_document_id=old.id)

OperationCorrection (status="applied" или "draft" или "abandoned")
    │
    ├── base_operation_revision_id (не base_document_id!)
    ├── OperationCorrectionLine[]  -- target state
    │       ├── line_uuid (стабильный или server-generated для added)
    │       └── item_id, qty, batch, comment (только целевое состояние)
    │
    └── version (optimistic locking)
```

### 4.5. OperationLine — current projection

`OperationLine` остаётся mutable. При correction submit:

```python
async def submit_correction(...):
    # 1. Создать immutable OperationRevision N+1
    new_revision = await create_operation_revision(
        operation_id=correction.operation_id,
        revision_number=correction.base_operation_revision.revision_number + 1,
        created_by_user_id=user_id,
        created_by_correction_id=correction.id,
        lines=final_state_lines,  # из OperationRevisionLine после apply
    )

    # 2. Apply delta effects (НЕ mutation OperationLine, а реальные effects)
    capture = []
    for delta in computed_diff.deltas:
        await _apply_delta_atomic(uow, delta, capture)
    await _write_captured_effects(uow, capture, audit_event_id, operation_id)

    # 3. В ТОЙ ЖЕ транзакции: rebuild OperationLine current projection
    await uow.operations.delete_operation_lines(correction.operation_id)
    for line in final_state_lines:
        await uow.operations.create_operation_line(
            operation_id=correction.operation_id,
            line_uuid=line.line_uuid,  # ← propagate from immutable revision
            line_number=line.line_number,
            item_id=line.item_id,
            qty=line.qty,
            ...
        )

    # 4. Update current_revision_id
    operation.current_revision_id = new_revision.id

    # 5. Generate documents from OperationRevisionLine (immutable source)
    new_documents = await _generate_revision_documents(uow, operation, new_revision, doc_types)

    # 6. Supersede old documents (только после успешного создания всех successor)
    for old_doc in old_active_documents:
        await uow.documents.update_document_status(old_doc.id, "superseded")

    # 7. Update correction status
    correction.status = "applied"
    correction.applied_at = datetime.now(UTC)

    # 8. Audit
    ...
```

**Ключевое:** history хранится **только** в `OperationRevisionLine`. `OperationLine` — проекция для текущего состояния API.

---

## 5. Correction state machine

```
Operation (status="submitted")
    │
    │ POST /operations/{id}/corrections
    ▼
OperationCorrection (status="draft")
    │ base_operation_revision_id = operation.current_revision_id
    │ копирует ВСЕ OperationRevisionLine → OperationCorrectionLine
    │ version = 1
    │
    │ PUT /corrections/{cid} (full target state)
    │   или PATCH /corrections/{cid}/lines/{line_uuid}
    │   или POST /corrections/{cid}/lines
    │   или DELETE /corrections/{cid}/lines/{line_uuid}
    │   (с expected_version)
    ▼
OperationCorrection (status="draft", version++)
    │
    │ POST /corrections/{cid}/submit (с expected_version + idempotency_key)
    ▼
    ┌─── V1: RECEIVE без acceptance
    │    compute diff (server-side, по OperationRevisionLine baseline)
    │    validate каждый delta
    │      ├── OK: apply delta effects atomic
    │      │      create OperationRevision N+1 (immutable)
    │      │      rebuild OperationLine current projection
    │      │      generate new documents
    │      │      supersede old documents
    │      │      status = "applied"
    │      │
    │      └── FAIL: UoW rollback
    │             status остаётся "draft"
    │             вернуть 422/409 с детальной ошибкой
    │
    │ DELETE /corrections/{cid} (с expected_version)
    ▼
OperationCorrection (status="abandoned")

V1 ограничения:
- Если operation_type != "RECEIVE" → 422 correction_operation_type_not_supported
- Если acceptance_required = true → 422 (V1 не поддерживает)
- Изменение accepted/lost/lost_qty запрещено → 422
```

---

## 6. Safe-delete policy matrix (V1)

| Correction kind | Baseline Item state | New Item state | Allowed? | Pre-validation |
|---|---|---|---|---|
| `unchanged` | active / soft-deleted | — | ✅ | — (нет effect) |
| `metadata_changed` | active / soft-deleted | — | ✅ | — (нет effect) |
| `quantity_changed_same_item` (+ qty) | active / soft-deleted | — | ✅ | item valid |
| `quantity_changed_same_item` (- qty) | active | — | ✅ | item valid, **sufficient balance** |
| `quantity_changed_same_item` (- qty) | soft-deleted | — | ❌ | V1 root-only с effect validation (вне V1 scope) |
| `removed` | active | — | ✅ | **sufficient balance check** |
| `removed` | soft-deleted | — | ⚠️ | проверять available balance (legacy can have остатки) |
| `item_replaced` | active | active | ✅ | both valid, **sufficient balance на old** |
| `item_replaced` | soft-deleted | active | ❌ | reversal невозможен на deleted item |
| `item_replaced` | active | soft-deleted / inactive | ❌ | new Item must be active |
| `added` | — | active | ✅ | item valid |
| `added` | — | soft-deleted / inactive | ❌ | new Item must be active |

**Правила:**

1. **`added` и `item_replaced` (new side)**: новый Item ОБЯЗАТЕЛЬНО `active=True, deleted_at IS NULL`. Иначе 422.
2. **Любая negative delta** (removed, quantity reduction, item_replaced old side): проверка текущего остатка на `inventory_subject_id`.
3. **Removed soft-deleted**: даже при soft-deleted Item может быть legacy остаток. Проверять обязательно.
4. **`unchanged` и `metadata_changed`**: baseline Item может быть soft-deleted — catalog snapshot наследуется из baseline revision, **не читаем live catalog**.

---

## 7. API contracts

### 7.1. POST /api/v1/operations/{id}/corrections

**Клонирует baseline в correction draft. Возвращает полный draft.**

```json
// Response
{
  "id": "uuid-correction",
  "operation_id": "uuid-operation",
  "status": "draft",
  "base_operation_revision_id": "uuid-revision-0",
  "base_operation_revision_number": 0,
  "version": 1,
  "idempotency_key": null,
  "created_by_user_id": "uuid-user",
  "created_at": "2026-07-21T14:00:00Z",
  "lines": [
    // ← ВСЕ baseline lines скопированы (НЕ пустой массив)
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

### 7.2. PUT /api/v1/operations/{id}/corrections/{correction_id}

**Full target state. Отсутствие строки = REMOVED.**

```json
// Request
{
  "expected_version": 1,
  "lines": [
    // unchanged line (optional to include)
    {
      "line_uuid": "uuid-1",
      "line_number": 1,
      "item_id": 3186,
      "qty": 100,
      "batch": "LOT-A",
      "comment": null
    },
    // quantity_changed_same_item
    {
      "line_uuid": "uuid-2",
      "line_number": 2,
      "item_id": 4102,
      "qty": 10,  // было 5
      "batch": null,
      "comment": null
    },
    // added line — line_uuid сервер сгенерирует
    // (UUID НЕ передаётся клиентом для added; сервер выдаёт 422 если передан)
    {
      "line_number": 3,
      "item_id": 4200,
      "qty": 8,
      "batch": null,
      "comment": null
    }
  ]
  // uuid-2 отсутствует → removed (если был в baseline)
}
```

### 7.3. Command endpoints (альтернатива PUT)

```http
PATCH /operations/{id}/corrections/{cid}/lines/{line_uuid}
{ "expected_version": 1, "qty": 120 }
→ { "line_uuid": "...", "qty": 120, ... }

POST /operations/{id}/corrections/{cid}/lines
{ "expected_version": 1, "line_number": 3, "item_id": 4200, "qty": 8 }
→ { "line_uuid": "uuid-new", "line_number": 3, ... }
   (uuid server-generated)

DELETE /operations/{id}/corrections/{cid}/lines/{line_uuid}
{ "expected_version": 1 }
→ 204 No Content
   (soft delete: correction_lines.deleted_at = now)
```

### 7.4. POST /api/v1/operations/{id}/corrections/{correction_id}/submit

```json
// Request
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
    "version": 1,
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
    }
  ],
  "computed_diff": {
    "unchanged": [{"line_uuid": "uuid-1"}],
    "metadata_changed": [],
    "quantity_changed": [
      {"line_uuid": "uuid-2", "old_qty": 5, "new_qty": 10, "diff_qty": 5}
    ],
    "item_replaced": [],
    "added": [{"line_uuid": "uuid-new-1", "item_id": 4200, "qty": 8}],
    "removed": []
  }
}
```

При validation failure:
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

### 7.5. Error contracts

```json
// HTTP 422 — operation_type не в V1 scope
{
  "code": "correction_operation_type_not_supported",
  "operation_type": "MOVE",
  "v1_scope": ["RECEIVE"],
  "phase": "C4"
}

// HTTP 422 — client передал correction_kind (запрещено)
{
  "code": "correction_kind_not_allowed_in_request",
  "message": "correction_kind is computed server-side, do not send"
}

// HTTP 409 — version conflict
{
  "code": "operation_version_conflict",
  "current_version": 3
}

// HTTP 409 — duplicate line_uuid в PUT
{
  "code": "correction_duplicate_line_uuid",
  "line_uuid": "uuid-1"
}

// HTTP 409 — stale base revision
{
  "code": "correction_stale_base_revision",
  "current_base_revision_id": "uuid-revision-2",
  "submitted_base_revision_id": "uuid-revision-0"
}

// HTTP 409 — concurrent correction (partial unique)
{
  "code": "concurrent_correction_exists",
  "operation_id": "uuid",
  "existing_correction_id": "uuid-other"
}

// HTTP 422 — new item invalid
{
  "code": "correction_new_item_invalid",
  "line_uuid": "uuid",
  "item_id": 4102,
  "reason": "soft_deleted"
}

// HTTP 409 — insufficient balance
{
  "code": "correction_insufficient_balance",
  "delta": {
    "line_uuid": "uuid",
    "kind": "removed",
    "diff_qty": -100,
    "current_balance": 50
  }
}
```

---

## 8. Database migrations

### 8.1. Migration sequence (2-step для line_uuid)

```python
# Migration A: add nullable line_uuid
op.add_column("operation_lines", sa.Column("line_uuid", PGUUID(as_uuid=True), nullable=True))
op.add_column("operation_revision_lines", sa.Column("line_uuid", PGUUID(as_uuid=True), nullable=True))

# Backfill скрипт (отдельно):
# Для каждой строки: random UUID через uuid.uuid4()
# Не использовать uuid.uuid5 (не детерминированно между базами)
# Не использовать server_default (для legacy нужен явный backfill)

# Migration B: SET NOT NULL + UNIQUE
op.alter_column("operation_lines", "line_uuid", nullable=False)
op.alter_column("operation_revision_lines", "line_uuid", nullable=False)
op.create_unique_constraint("uq_ol_line_uuid", "operation_lines", ["line_uuid"])
op.create_unique_constraint("uq_orl_line_uuid", "operation_revision_lines", ["line_uuid"])

# Альтернатива: одна транзакционная migration с gen_random_uuid()
# Требует PostgreSQL с pgcrypto extension
# Нужно verification перед использованием
```

### 8.2. Migration: new tables (OperationRevision, OperationCorrection, etc.)

```python
"""Phase C migration: operation correction by immutable OperationRevision.

V1 schema additions:
- Operation.current_revision_id (FK nullable)
- OperationRevision (immutable)
- OperationRevisionLine (immutable, line_uuid + revision_id composite PK)
- OperationCorrection (3-state: draft/applied/abandoned)
- OperationCorrectionLine (target state only, server-generated line_uuid для added)
- Document.operation_revision_id (FK nullable)
"""

def upgrade():
    # 1. Operation.current_revision_id (nullable initially)
    op.add_column("operations", sa.Column("current_revision_id", PGUUID(as_uuid=True), nullable=True))

    # 2. OperationRevision (immutable)
    op.create_table(
        "operation_revisions",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("operation_id", PGUUID(as_uuid=True), ForeignKey("operations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("revision_number", sa.Integer, nullable=False),
        sa.Column("created_by_user_id", PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False),
        sa.Column("created_by_correction_id", PGUUID(as_uuid=True), ForeignKey("operation_corrections.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("operation_id", "revision_number", name="uq_operation_revisions_op_rev"),
    )

    # 3. OperationRevisionLine (composite PK: revision_id + line_uuid)
    op.create_table(
        "operation_revision_lines",
        sa.Column("revision_id", PGUUID(as_uuid=True), ForeignKey("operation_revisions.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("line_uuid", PGUUID(as_uuid=True), nullable=False),  # NOT NULL после Migration B
        sa.Column("line_number", sa.Integer, nullable=False),
        sa.Column("item_id", sa.Integer, ForeignKey("items.id")),
        sa.Column("inventory_subject_id", sa.Integer, ForeignKey("inventory_subjects.id")),
        sa.Column("qty", sa.Numeric(18, 3), nullable=False),
        sa.Column("accepted_qty", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.Column("lost_qty", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.Column("batch", sa.String(100)),
        sa.Column("comment", sa.Text),
        sa.Column("source_item_name", sa.String(255)),
        sa.Column("source_item_sku", sa.String(100)),
        sa.Column("source_unit_name", sa.String(100)),
        sa.Column("source_category_name", sa.String(255)),
        sa.Column("item_name_snapshot", sa.String(255)),
        sa.Column("item_sku_snapshot", sa.String(100)),
        sa.Column("unit_name_snapshot", sa.String(100)),
        sa.Column("unit_symbol_snapshot", sa.String(20)),
        sa.Column("category_name_snapshot", sa.String(255)),
        sa.UniqueConstraint("line_uuid", name="uq_orl_line_uuid"),  # После Migration B
    )

    # 4. OperationCorrection (3-state)
    op.create_table(
        "operation_corrections",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("operation_id", PGUUID(as_uuid=True), ForeignKey("operations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("base_operation_revision_id", PGUUID(as_uuid=True), ForeignKey("operation_revisions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("idempotency_key", sa.String(100)),
        sa.Column("created_by_user_id", PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("submitted_by_user_id", PGUUID(as_uuid=True), ForeignKey("users.id")),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('draft', 'applied', 'abandoned')",
            name="ck_operation_corrections_status",
        ),
    )
    # Partial unique index: одна active draft на operation
    op.execute("""
        CREATE UNIQUE INDEX uq_active_correction_per_operation
        ON operation_corrections (operation_id)
        WHERE status = 'draft'
    """)
    op.create_index("ix_operation_corrections_operation_id", "operation_corrections", ["operation_id"])

    # 5. OperationCorrectionLine
    op.create_table(
        "operation_correction_lines",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("correction_id", PGUUID(as_uuid=True), ForeignKey("operation_corrections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("line_uuid", PGUUID(as_uuid=True), nullable=False),
        sa.Column("line_number", sa.Integer, nullable=False),
        sa.Column("item_id", sa.Integer, ForeignKey("items.id")),
        sa.Column("qty", sa.Numeric(18, 3), nullable=False),
        sa.Column("batch", sa.String(100)),
        sa.Column("comment", sa.Text),
        sa.UniqueConstraint("correction_id", "line_uuid", name="uq_correction_lines_line_uuid"),
    )

    # 6. Document.operation_revision_id
    op.add_column("documents", sa.Column("operation_revision_id", PGUUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_documents_operation_revision",
        "documents", "operation_revisions",
        ["operation_revision_id"], ["id"],
    )

    # 7. Foreign key current_revision_id → operation_revisions (added after Migration A)
    # (FK добавляется в отдельной migration после backfill)


def downgrade():
    op.drop_constraint("fk_documents_operation_revision", "documents", type_="foreignkey")
    op.drop_column("documents", "operation_revision_id")
    op.drop_table("operation_correction_lines")
    op.drop_table("operation_corrections")
    op.drop_table("operation_revision_lines")
    op.drop_table("operation_revisions")
    op.drop_column("operations", "current_revision_id")
```

**ВАЖНО:** Migration A (line_uuid) и Migration C (new tables) — разные миграции, могут быть разные head'ы. Проверить `alembic heads` перед созданием.

---

## 9. Audit Events

### 9.1. Новые event_type

| event_type | Когда | Что фиксирует |
|---|---|---|
| `operation.correction.applied` | На успешном submit correction | applied_at, applied_revision_id, baseline_revision_id, computed_diff |
| `operation.correction.abandoned` | На DELETE correction | abandoned_at, abandoned_by_user_id |
| `document.revision_created` | На новой document revision | new_document_id, parent_revision, operation_revision_id |
| `document.superseded` | На supersede | old_document_id, new_document_id, reason="correction_applied" |

### 9.2. Audit resource links

```python
# operation.correction.applied
await record_audit_event(
    uow,
    event_type="operation.correction.applied",
    actor_user_id=user_id,
    site_id=operation.site_id,
    entity_type="operation_correction",
    entity_id=str(correction.id),
    summary=f"Correction applied to operation #{operation.short_id}",
    changes={
        "correction_id": str(correction.id),
        "baseline_revision_id": str(correction.base_operation_revision_id),
        "new_revision_id": str(new_revision.id),
        "new_revision_number": new_revision.revision_number,
        "delta_count": len(diff.deltas),
        "added_count": len(diff.added),
        "removed_count": len(diff.removed),
        "changed_count": len(diff.changed),
        "unchanged_count": len(diff.unchanged),
    },
)

# Resource links на baseline revision и новую revision
await uow.audit_events.insert_resource(
    audit_event_id=int(audit_event.id),
    resource_type="operation_revision",
    resource_id=str(correction.base_operation_revision_id),
    relation="baseline",
)
await uow.audit_events.insert_resource(
    audit_event_id=int(audit_event.id),
    resource_type="operation_revision",
    resource_id=str(new_revision.id),
    relation="supersedes",
)

# Resource links на superseded documents и новые
for old_doc in old_active_documents:
    await uow.audit_events.insert_resource(
        audit_event_id=int(audit_event.id),
        resource_type="document",
        resource_id=str(old_doc.id),
        relation="superseded",
        snapshot_before={"status": "finalized", "revision": old_doc.revision,
                        "operation_revision_id": str(old_doc.operation_revision_id)},
        snapshot_after={"status": "superseded"},
    )
```

---

## 10. Cancel after correction

### 10.1. Поведение V1

Cancel after correction должен отменить cumulative state.

```
RECEIVE +100 (revision 0, qty=100)
    │ OperationLine: qty=100
    │ OperationRevision 0: line(qty=100)
    │
    │ correction +20 (added line)
    ▼
RECEIVE +100, added +20 (revision 1, qty=100, qty=20)
    │ OperationLine: qty=100, qty=20 (current projection = cumulative)
    │ OperationRevision 1: line(qty=100), line(qty=20) (immutable history)
    │
    │ correction -10 (quantity reduction на added line)
    ▼
RECEIVE +110 (revision 2)
    │ OperationLine: qty=100, qty=10
    │
    │ cancel
    ▼
final balance = state before initial operation
```

### 10.2. Реализация

Существующий `cancel_operation` (operations_service.py:1788-2052) работает с current `OperationLine` projection. После correction, projection содержит cumulative state. Cancel работает корректно.

**Edge case:** если projection рассинхронизирована с revision (из-за ошибки в submit_correction), cancel может работать неправильно.

**Тест:** `cancel after multiple corrections restores pre-operation state` — обязательный.

### 10.3. V1 не требует отдельного cumulative reversal

Если тест показывает проблемы (например, частичное применение effects с ошибкой посередине транзакции), описывать отдельный ADR с cumulative reversal через revision chain.

---

## 11. Lock order

```python
async def submit_correction(uow, correction_id, user_id):
    # Lock 1: Correction
    correction = await uow.corrections.get_for_update(correction_id)

    # Lock 2: Operation (NO deadlock if concurrent submit also locks Operation)
    operation = await uow.operations.get_operation_by_id_for_update(correction.operation_id)

    # Lock 3: inventory_subjects в ASC order (избегаем deadlock)
    affected_subjects = collect_affected_inventory_subjects(correction.lines)
    for subject_id in sorted(affected_subjects):  # ← ASC order
        await uow.inventory_subjects.get_for_update(subject_id)

    # Lock 4: balances / registers (по affected_subjects, ASC order)
    for subject_id in sorted(affected_subjects):
        await uow.balances.get_for_update(site_id, subject_id)
        await uow.asset_registers.get_pending_for_update(subject_id)

    # Генерация документов (Lock 5 если нужны)
    ...

    # ВСЕ операции в одной UoW transaction
```

**Критично:** `sorted(affected_subjects)` — фиксированный order для предотвращения deadlock при параллельных corrections.

**Тесты deadlock/race:**
- Параллельные submit_correction на ту же операцию
- Параллельные submit_operation и submit_correction
- Параллельные cancel и submit_correction

---

## 12. Test Ladder (V1)

### 12.1. Mandatory tests (по директиве)

| Тест | Что проверяет |
|---|---|
| `test_begin_correction_clones_baseline` | POST /corrections возвращает все baseline lines (не пустой) |
| `test_client_cannot_submit_correction_kind` | PUT с correction_kind → 422 (kind вычисляется сервером) |
| `test_duplicate_line_uuid_rejected` | PUT с двумя строками с одним line_uuid → 409 |
| `test_stale_base_revision_rejected` | submit с base_revision_id != operation.current_revision_id → 409 |
| `test_operation_current_projection_updated` | После correction submit OperationLine отражает итоговое состояние |
| `test_document_generated_from_new_revision` | Новый документ читается из OperationRevisionLine, не из OperationLine |
| `test_failed_validation_leaves_correction_draft` | Validation failure → correction.status="draft", эффекты не меняются |
| `test_retry_submit_idempotent` | Submit с тем же idempotency_key → тот же результат |
| `test_cancel_after_multiple_corrections_restores_pre_op_state` | RECEIVE +100, correction +20, correction -10, cancel → final balance = 0 |
| `test_soft_deleted_baseline_line_unchanged` | unchanged с soft-deleted Item → allowed, catalog snapshot наследуется |
| `test_soft_deleted_baseline_line_removed_with_insufficient_balance` | removed с soft-deleted Item при insufficient balance → 409 |
| `test_concurrent_correction_rejected` | Параллельные begin correction → одна succeed, другая 409 (partial unique) |

### 12.2. Unit tests

| Тест | Что проверяет |
|---|---|
| `test_compute_diff_unchanged` | All unchanged → no delta |
| `test_compute_diff_quantity_change` | qty 100→120 → quantity_changed_same_item |
| `test_compute_diff_add_line` | New line_uuid → added |
| `test_compute_diff_remove_line` | Missing line_uuid → removed |
| `test_compute_diff_replace_item` | item_id X→Y → item_replaced |
| `test_compute_diff_metadata_change` | batch change → metadata_changed |
| `test_validate_new_item_inactive` | new Item soft-deleted → 422 |
| `test_validate_insufficient_balance_removed` | removed при insufficient → 409 |
| `test_validate_quantity_reduction_insufficient_balance` | quantity -10 при balance=5 → 409 |
| `test_line_uuid_server_generated_for_added` | POST /corrections/{cid}/lines возвращает server-generated UUID |

### 12.3. Integration tests

| # | Сценарий | Ожидание |
|---|---|---|
| 1 | RECEIVE без acceptance, full happy path | submit OK, revision 1, documents updated |
| 2 | V1 scope: operation_type=MOVE → 422 correction_operation_type_not_supported | 422 |
| 3 | V1 scope: acceptance_required=true → 422 | 422 |
| 4 | Begin correction, затем PUT с удалённой строкой | removed |
| 5 | Begin correction, затем POST новой строки | added (server-generated UUID) |
| 6 | Concurrent corrections на ту же operation | partial unique constraint |
| 7 | Two corrections на разных operations | OK |
| 8 | Submit failed → submit retry с тем же idempotency_key | OK (idempotent) |
| 9 | Submit failed → submit retry с другим idempotency_key | validation re-runs |
| 10 | Cancel after 2 corrections → pre-op state | OK |

### 12.4. Concurrency tests

| Тест | Что проверяет |
|---|---|
| `test_deadlock_parallel_corrections_different_lines` | Lock order предотвращает deadlock |
| `test_deadlock_submit_op_and_correction` | submit operation не блокирует correction |
| `test_concurrent_correction_partial_unique` | partial unique index работает |
| `test_concurrent_abandon_and_submit` | submit после abandon → 422 |

---

## 13. Definition of Ready

Пакет C можно передавать младшей модели, **только если**:

- [x] Immutable OperationRevision как source of truth для истории
- [x] OperationLine остаётся как current projection (мутабельный для API)
- [x] Operation.current_revision_id + Document.operation_revision_id FK
- [x] Begin correction клонирует baseline (не пустой)
- [x] PUT full target state (отсутствие = removed)
- [x] Server-side correction_kind computation (client не передаёт)
- [x] UNIQUE(correction_id, line_uuid), server-generated UUID для added
- [x] 3-state correction (draft/applied/abandoned)
- [x] Correction.version + expected_version + idempotency_key
- [x] V1 scope ограничен RECEIVE без acceptance
- [x] Safe-delete policy explicit matrix (allowed для unchanged/metadata на soft-deleted)
- [x] New Item для added/replaced: active обязательно
- [x] Любая negative delta требует balance check
- [x] Document generation from OperationRevisionLine
- [x] Document supersede: per-document_type, atomic
- [x] Lock order: Correction → Operation → inventory_subject_id ASC → balances → Documents
- [x] line_uuid migration: 2-step (add nullable → backfill random → set NOT NULL UNIQUE)
- [x] Cancel after correction test
- [x] Deadlock tests
- [x] 12 mandatory tests описаны
- [x] C2..C8 phases явно out of scope

---

## 14. Acceptance criteria

### 14.1. Definition of Done (V1)

- [ ] Migration sequence применена на dev-стенде (Migrations A, B, C)
- [ ] line_uuid backfill выполнен для всех existing operations
- [ ] Initial submit создаёт OperationRevision 0
- [ ] Begin correction возвращает клонированный draft
- [ ] PUT full target state обновляет correction draft
- [ ] Server вычисляет correction_kind на submit
- [ ] Submit correction создаёт revision N+1 атомарно
- [ ] OperationLine current projection обновляется
- [ ] Documents генерируются из OperationRevisionLine
- [ ] Cancel after multiple corrections восстанавливает pre-op state
- [ ] Concurrent corrections rejected через partial unique index
- [ ] V1 scope enforced (RECEIVE без acceptance)
- [ ] 12 mandatory tests + unit + integration + concurrency tests pass
- [ ] Documentation обновлена

---

## 15. Risks

| Риск | Вероятность | Влияние | Митигация |
|---|---|---|---|
| line_uuid backfill вызывает коллизии | Низкая | UNIQUE violation | Random UUID, не UUID5 |
| Cumulative cancel через projection | Средняя | Неправильный остаток | Mandatory test; cumulative reversal через revision chain если нужно |
| Lock order deadlock | Средняя | Concurrent correction failure | Fixed order, deadlock tests |
| Partial unique index race | Низкая | Concurrent correction | Partial unique index works |
| Document generation reads mutable OperationLine | Средняя | Wrong snapshots | Document generation читает из OperationRevisionLine |
| V1 scope не покрывает use case | Низкая | Reverted operation | C2..C8 phases последовательно |
| V1 idempotency key не строгий | Низкая | Duplicate effects | UNIQUE constraint + deterministic key check |

---

## 16. Evidence table

| Check | Команда | Результат |
|---|---|---|
| Migration A apply | `alembic upgrade head` | pass/fail |
| line_uuid backfill | `SELECT COUNT(*) FROM operation_lines WHERE line_uuid IS NULL` | 0 |
| Begin correction clone | `curl POST /corrections` → response.lines.length == baseline.lines.length | pass |
| Server-side kind | `curl PUT /corrections/{cid}` с correction_kind → 422 | pass |
| PUT full state | `curl PUT /corrections/{cid}` с отсутствующей строкой → removed | pass |
| Submit atomic | `curl POST /corrections/{cid}/submit` | success/failure atomic |
| Revision create | `SELECT * FROM operation_revisions WHERE operation_id=?` | immutable |
| Document from revision | `SELECT d.operation_revision_id FROM documents d WHERE d.operation_id=?` | matches |
| Cancel cumulative | `test_cancel_after_multiple_corrections_restores_pre_op_state` | pass |
| Partial unique | `BEGIN; INSERT correction (status='draft'); INSERT correction (status='draft');` → second fails | pass |
| Deadlock test | parallel submit_correction на разные строки | pass |

---

## 17. Открытые вопросы

1. **Cumulative cancel через revision chain** — V1 не требует, но если тесты покажут проблемы, нужен отдельный ADR
2. **Snapshot policy для partial unique index** — проверить совместимость с PostgreSQL
3. **Backward compat с TZ-B документом** — `void_reason="operation_reopened"` остаётся для cancelled операций
4. **Idempotency key scope** — на operation или на correction? V1: на correction (`correction.idempotency_key`)
5. **C2 phase** — когда начинать разработку? После V1 acceptance + audit trail
6. **Cross-revision cumulative effects query** — для UI: как показать все effects через все revisions? Через audit_item_effects с parent_event_id chain

---

## 18. Рекомендованный порядок реализации (V1)

1. Migration A: add nullable line_uuid + backfill script + Migration B: NOT NULL UNIQUE
2. Migration C: new tables (OperationRevision, OperationRevisionLine, OperationCorrection, OperationCorrectionLine) + FKs
3. Repo: OperationRevisionsRepo (immutable), CorrectionsRepo (с version + idempotency_key)
4. Service: submit_operation (создаёт revision 0)
5. Service: begin_correction (клонирует baseline через OperationRevisionLine)
6. Service: update_correction (PUT full state)
7. Service: _compute_correction_diff (server-side kind computation)
8. Service: _validate_delta (safe-delete matrix V1)
9. Service: submit_correction (atomic с фиксированным lock order)
10. Document generation: переписать с OperationLine на OperationRevisionLine
11. Endpoints: 4 endpoint'а (begin, PUT update, submit, DELETE abandon)
12. Cancel after correction test
13. Audit events
14. Tests (unit + integration + concurrency + mandatory)
15. Documentation update
16. ADR-0023 published (revised)

Общий срок V1: 10-15 рабочих дней.

После V1 acceptance:
- Пометить TZ-C v1 как superseded (если остался)
- Удалить ADR-0022 superseded и TZ-B Needs redesign (если готовы)
- Начать планирование C2 phase

<dcp-message-id>m0122</dcp-end>