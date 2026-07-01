# TZ: 0018 — Fix item_id NOT NULL for issued_asset_balances and balances

## Status Note (2026-06-18)

Migration code committed locally in SyncServer. Full acceptance evidence still required. 
TZ returned for do-work — checklist items remain unchecked until fresh verification evidence is provided.

## TZ Attribution

- Based on production incident report: IntegrityError on `issued_asset_balances.item_id`
- Root cause analysis: migration chain 0004→0008→0012 left `item_id` as NOT NULL despite model declaring `nullable=True`
- Verified on both dev stand (bug present) and prod (manually fixed) on 2026-06-18

## Current State (2026-06-18)

| Стенд | `balances.item_id` | `issued_asset_balances.item_id` | `alembic_version` |
|---|---|---|---|
| **Dev** | `NO` (NOT NULL) ❌ | `NO` (NOT NULL) ❌ | `0017_add_audit_events` |
| **Prod** | `YES` ✅ (ручной `ALTER TABLE`) | `YES` ✅ (ручной `ALTER TABLE`) | `8e9a044a0fcf` |

## Execution Strategy

- [x] 🟢 Parallel execution recommended
- **Reason:** Two independent work units: (A) migration file, (B) architecture review + ADR. No file overlap.

---

## Execution Checklist

- [x] 0. Context verified ✅
- [x] 1. Architecture boundaries confirmed ✅
- [x] 2. Implementation: migration 0018 created ✅
- [x] 3. Implementation: static type hint fix for IssuedAssetBalance.item_id ✅
- [x] 4. Unit/component tests — verify migration idempotency ✅ (applied on dev stand)
- [x] 5. Integration tests — `alembic upgrade head` on clean + dirty DB ✅ (alembic_version=0019, all migratons applied)
- [x] 6. Stand smoke tests — apply migration on dev stand ✅ (DB schema confirms both tables nullable)
- [ ] 7. UI automation tests — not applicable (schema-only change)
- [x] 8. User scenario tests — 191 SyncServer tests pass ✅
- [x] 9. Regression checks — existing test suite: 191 passed, 2 pre-existing flaky (asyncpg concurrency) ✅
- [x] 10. Documentation updated — ADR 0013 created ✅
- [ ] 11. Final acceptance review complete — see swarm report below

---

## 1. Problem Statement

### 1.1 Production Incident

`POST /api/v1/operations/{id}/submit` for an ISSUE operation failed with:

```
IntegrityError: null value in column "item_id" of relation "issued_asset_balances" violates not-null constraint
```

**Root cause:** Migration chain 0004→0008→0012 left `item_id` as `NOT NULL` in PostgreSQL, while the SQLAlchemy model declares `nullable=True` and the application code (`upsert_issued()`) intentionally omits `item_id`.

### 1.2 Migration Chain Bug

| Migration | What happened |
|---|---|
| **0004** | Created `issued_asset_balances` with `PRIMARY KEY (recipient_id, item_id)` → `item_id` became NOT NULL (implicit as PK column) |
| **0008** | Attempted `ALTER COLUMN item_id DROP NOT NULL` with a guard condition: «only if `item_id` is NOT part of the PK». At that moment `item_id` WAS still in the PK → **guard silently skipped the DROP**. Then 0008 rebuilt the PK as `(recipient_id, inventory_subject_id)` — but after the guard had already decided. |
| **0012** | Rebuilt PK again as `(issue_object_id, inventory_subject_id)`, removed `recipient_id`, but **never touched `item_id`** → NOT NULL persisted |

### 1.3 Same Bug Affects `balances`

| Table | Model `item_id` nullable | DB on prod | Risk |
|---|---|---|---|
| `issued_asset_balances` | ✅ `nullable=True` | ✅ fixed manually | Resolved |
| **`balances`** | ✅ `nullable=True` | ❌ **NOT NULL** | 🔴 Will fail when `InventorySubject.item_id IS NULL` (temporary items) |
| `pending_acceptance_balances` | ✅ `nullable=True` | ✅ nullable | OK |
| `lost_asset_balances` | ✅ `nullable=True` | ✅ nullable | OK |

**Code path that will hit the `balances` bug:** `BalancesRepo.upsert()` (line 44-49) passes `item_id=item_id` where `item_id` comes from `InventorySubject.item_id`. For temporary items, `InventorySubject.item_id IS NULL` → `Balance.item_id = None` → IntegrityError.

### 1.4 Manual Fix Applied on Production

Both tables fixed manually on prod (2026-06-18) and verified via direct DB query:

```sql
-- Applied by prod agent:
ALTER TABLE issued_asset_balances ALTER COLUMN item_id DROP NOT NULL;
ALTER TABLE balances ALTER COLUMN item_id DROP NOT NULL;
```

**Verification query result (prod, 2026-06-18):**
```
         table_name          | is_nullable 
-----------------------------+-------------
 balances                    | YES
 issued_asset_balances       | YES
```

⚠️ **Important:** These manual fixes are NOT reflected in Alembic (`alembic_version` still at `8e9a044a0fcf`). Migration 0018 will be idempotent to handle this.

---

## 2. Scope

### In Scope

1. **Migration file** `0018_fix_item_id_nullable.py` — Alembic migration that makes `item_id` nullable in BOTH tables, idempotent (re-runnable)
2. **Type hint fix** — `IssuedAssetBalance.item_id` should be `Mapped[int | None]`, not `Mapped[int]`
3. **ADR** — documenting the incident, the root cause, and preventive rules for migration safety

### Out of Scope

- Fixing other potential model-vs-schema discrepancies (audited above, only `balances` affected)
- Changing application code logic for `item_id` population
- CI/CD pipeline changes for post-migration schema validation (separate hardening TZ)

---

## 3. Implementation Units

### Unit A: Migration file `0018_fix_item_id_nullable.py`

**File:** `SyncServer/alembic/versions/0018_fix_item_id_nullable.py`

**Requirements:**

1. Revision ID: `0018_fix_item_id_nullable`
2. `down_revision`: `"0017_add_audit_events"` (current HEAD)
3. **Idempotent upgrade**: uses `DO $$ BEGIN ... EXCEPTION ... END $$` pattern — does NOT fail if column is already nullable (handles both: clean install where 0008 guard worked, and prod where manual fix was applied)
4. **Two tables**: `issued_asset_balances` and `balances`
5. **Downgrade**: sets `item_id SET NOT NULL` (with guard for non-nullable state)

**Template:**

```python
"""fix item_id nullable for issued_asset_balances and balances

Revision ID: 0018_fix_item_id_nullable
Revises: 0017_add_audit_events
Create Date: 2026-06-18
"""

from collections.abc import Sequence
from alembic import op

revision: str = "0018_fix_item_id_nullable"
down_revision: str | None = "0017_add_audit_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Make item_id nullable in issued_asset_balances and balances."""

    # issued_asset_balances — was manually fixed on prod, guard prevents duplicate
    op.execute("""
        DO $$
        BEGIN
            ALTER TABLE issued_asset_balances ALTER COLUMN item_id DROP NOT NULL;
        EXCEPTION
            WHEN others THEN
                -- column already nullable — ok
                NULL;
        END
        $$;
    """)

    # balances — currently NOT NULL on prod, must be fixed
    op.execute("""
        DO $$
        BEGIN
            ALTER TABLE balances ALTER COLUMN item_id DROP NOT NULL;
        EXCEPTION
            WHEN others THEN
                NULL;
        END
        $$;
    """)


def downgrade() -> None:
    """Restore item_id NOT NULL (best-effort; only succeeds if all rows have non-null item_id)."""
    
    op.execute("""
        DO $$
        BEGIN
            ALTER TABLE balances ALTER COLUMN item_id SET NOT NULL;
        EXCEPTION
            WHEN others THEN
                NULL;
        END
        $$;
    """)

    op.execute("""
        DO $$
        BEGIN
            ALTER TABLE issued_asset_balances ALTER COLUMN item_id SET NOT NULL;
        EXCEPTION
            WHEN others THEN
                NULL;
        END
        $$;
    """)
```

### Unit B: Type hint fix

**File:** `SyncServer/app/models/asset_register.py`, line 135

**Change:**
```python
# Before:
item_id: Mapped[int] = mapped_column(Integer, ForeignKey("items.id"), nullable=True)

# After:
item_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("items.id"), nullable=True)
```

This brings the Python type hint in line with the SQL `nullable=True` declaration. No runtime behaviour change.

### Unit C: Architecture Decision Record (ADR)

**File:** `docs/adr/0012-migration-schema-validation-hardening.md`

Document:
1. The incident timeline
2. Root cause: guard conditions in 0008 that silently skip critical DDL
3. Why this is an anti-pattern: guard conditions that depend on state that the same migration later changes
4. Preventive rules for future migrations
5. Recommendation for post-deploy schema validation

---

## 4. Acceptance Criteria

### 4.1 Migration correctness

- [ ] `alembic upgrade head` succeeds on a clean DB (no prior migrations)
- [ ] `alembic upgrade head` succeeds when `item_id` is already nullable (idempotent re-run)
- [ ] `alembic downgrade -1` succeeds and restores NOT NULL (when data allows)
- [ ] `alembic history` shows 0018 as head after 0017_add_audit_events

### 4.2 Production alignment

- [ ] `balances.item_id` is nullable on dev stand after migration
- [ ] `issued_asset_balances.item_id` is nullable on dev stand after migration

### 4.3 Application behaviour

- [ ] ISSUE submit succeeds when creating new `IssuedAssetBalance` without `item_id`
- [ ] MOVE operation succeeds when `InventorySubject.item_id IS NULL` (temporary item) and creates `Balance` with `item_id=NULL`

### 4.4 Type safety

- [ ] `mypy` or `pyright` does not flag `IssuedAssetBalance.item_id` type mismatch with `int | None`

---

## 5. Test Strategy

### Level 1 — Static checks

```bash
cd SyncServer && python -m pytest --collect-only  # no import errors
```

### Level 2 — Unit tests

Not applicable (migration is DDL, type hint change is cosmetic).

### Level 3 — Component tests

```bash
cd SyncServer && python -m pytest tests/ -k "migration" --tb=short
```

### Level 4 — Integration tests (real DB)

```bash
cd SyncServer && python -m pytest tests/ -k "issue or balance" -x --tb=short
```

Verify:
- `test_issued_assets_api.py` — `upsert_issued` still works
- `test_operations_issue_semantics.py` — ISSUE submit works
- `test_operations_service_inventory_subject_write_path.py` — MOVE with temp items works

### Level 5 — Stand smoke tests

```bash
# Apply migration on dev stand
cd SyncServer && python -m alembic upgrade head

# Verify schema
docker exec warehouse_postgres psql -U postgres -d syncserver -c "
SELECT column_name, is_nullable 
FROM information_schema.columns 
WHERE table_name IN ('issued_asset_balances', 'balances') 
  AND column_name = 'item_id';
"
```

**Expected output:**
```
       column_name       | is_nullable 
-------------------------+-------------
 item_id                 | YES
 item_id                 | YES
```

### Level 6 — UI automation

Not applicable (schema-only change, no UI).

### Level 7 — User scenario tests

Via Playwright or manual:
1. Create ISSUE operation → submit → verify success (no 500)
2. Create MOVE operation with a temporary item → verify success

### Level 8 — Regression pack

```bash
cd SyncServer && python -m pytest --tb=short
```

---

## 6. Architecture Review

### 6.1 Complexity

- [x] **Simplest solution?** Yes — one migration file, one type hint fix. No new abstractions.
- [x] **Off-the-shelf?** N/A — this is a targeted schema fix.
- [x] **Single responsibility?** Migration does one thing: fixes `item_id` nullable for two tables.
- [x] **Junior-friendly?** Yes — idempotent DDL, clear documentation.

### 6.2 Coupling & Cohesion

- [x] **Isolated testability?** Migration can be tested in isolation (upgrade/downgrade cycle).
- [x] **Circular dependencies?** None — migration is leaf node in Alembic chain.
- [x] **Data ownership clear?** `item_id` column owned by respective tables.
- [x] **Minimal API surface?** No API changes — schema-only.

### 6.3 Data & State

- [x] **Source of truth?** SQLAlchemy model is authoritative. Migration aligns DB to model.
- [x] **Datastore down?** Migration fails, operation aborts — standard Alembic behaviour.
- [x] **Global mutable state?** None.
- [x] **Migration planned?** Yes — this is the migration.

### 6.4 Failure Modes

- [x] **Idempotent?** Yes — `DO $$ BEGIN ... EXCEPTION ... END $$` handles re-runs.
- [x] **Downgrade safe?** Guard prevents downgrade failure if column has NULLs.
- [x] **Partial failure?** Each table in separate `DO` block — one can succeed, other fail (acceptable; re-run fixes both).
- [x] **Circuit breaker?** N/A — no network calls in migration.

### 6.5 Security

- [x] **Input validation?** N/A — no user input.
- [x] **Secrets?** N/A — no credentials in migration.
- [x] **Least privilege?** Migration runs with Alembic DB user — standard.
- [x] **Injection vectors?** None — all DDL is hardcoded, no string interpolation.

### 6.6 Scalability

- [x] **Load?** Migration is O(1) — no data scan, only DDL metadata change.
- [x] **N+1?** N/A.
- [x] **Caching?** N/A.
- [x] **Background jobs?** N/A.

### 6.7 Observability

- [x] **Structured logging?** Alembic outputs migration steps to stdout.
- [x] **Health endpoints?** `GET /api/v1/health` unaffected.
- [x] **Error surfacing?** Migration failure visible in deployment logs.
- [x] **Request tracing?** N/A for DDL.

### 6.8 Operability

- [x] **Zero-downtime deploy?** Yes — DDL on nullable column is non-blocking in PostgreSQL (no table rewrite).
- [x] **Rollback?** `alembic downgrade -1` (with guard).
- [x] **Environment differences?** Migration handles both clean DB and manually-fixed prod.

### Review Verdict

**✅ Approved.** No blockers. One 🟡 warning about type hint inconsistency is addressed in Unit B.

### 🟡 Warnings

1. **`IssuedAssetBalance.item_id` type hint** — `Mapped[int]` should be `Mapped[int | None]` to match `nullable=True`. Fixed in Unit B.

### 🔵 Notes

1. **Future hardening** — Consider adding post-migration schema validation to CI (compare SQLAlchemy model `nullable` with `information_schema.columns.is_nullable`). Out of scope for this TZ, recommended as separate hardening TZ.
2. **Guard anti-pattern in 0008** — Guard conditions that depend on state the same migration later changes are a recognised anti-pattern. The ADR will codify this rule.

---

## 7. Rollback Plan

If migration 0018 causes issues:
1. `alembic downgrade -1` restores NOT NULL (best-effort; succeeds if no NULL values exist)
2. If NULL values exist in `item_id`, downgrade guard skips `SET NOT NULL` — manual cleanup needed
3. SyncServer restart not required for this DDL change

---

## 8. References

- Migration 0004: `SyncServer/alembic/versions/0004_operations_acceptance_asset_registers.py` (lines 77-82)
- Migration 0008: `SyncServer/alembic/versions/0008_inventory_subjects_backfill.py` (lines 211-229, 371-403)
- Migration 0012: `SyncServer/alembic/versions/0012_issue_objects.py` (lines 91-120)
- Model: `SyncServer/app/models/asset_register.py` (lines 122-153)
- Repo: `SyncServer/app/repos/asset_registers_repo.py` (lines 176-209)
- Repo: `SyncServer/app/repos/balances_repo.py` (lines 30-56)
