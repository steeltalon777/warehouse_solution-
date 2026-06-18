# ADR-0013: Migration Schema Validation Hardening

## Status

Accepted

## Date

2026-06-18

## Context

### Incident Timeline

On 2026-06-18, a production incident occurred when `POST /api/v1/operations/{id}/submit` for an ISSUE operation failed with:

```
IntegrityError: null value in column "item_id" of relation "issued_asset_balances" violates not-null constraint
```

Root cause analysis traced the issue through the migration chain:

1. **Migration 0004** (`0004_operations_acceptance_asset_registers.py`) created `issued_asset_balances` with `PRIMARY KEY (recipient_id, item_id)`. PostgreSQL implicitly makes PK columns NOT NULL, so `item_id` became NOT NULL despite the SQLAlchemy model declaring `nullable=True`.

2. **Migration 0008** (`0008_inventory_subjects_backfill.py`) attempted `ALTER COLUMN item_id DROP NOT NULL` with a guard condition: «only if `item_id` is NOT part of the PK». At that moment `item_id` WAS still part of the PK — the guard **silently skipped the DROP**. The PK was rebuilt as `(recipient_id, inventory_subject_id)` immediately after the guard, but the guard had already decided.

3. **Migration 0012** (`0012_issue_objects.py`) rebuilt the PK again as `(issue_object_id, inventory_subject_id)`. It never touched `item_id` — the NOT NULL constraint persisted undetected.

4. **Same bug in `balances` table**: The same guard pattern left `balances.item_id` as NOT NULL. This will fail when `InventorySubject.item_id IS NULL` (temporary items) — `BalancesRepo.upsert()` passes `item_id` from `InventorySubject.item_id` which is NULL for temporary items.

### Manual Fix

Both tables were fixed manually on production on 2026-06-18:
```sql
ALTER TABLE issued_asset_balances ALTER COLUMN item_id DROP NOT NULL;
ALTER TABLE balances ALTER COLUMN item_id DROP NOT NULL;
```

### Dev Stand Verification

On the dev stand, both `balances.item_id` and `issued_asset_balances.item_id` were confirmed NOT NULL before the fix (migration chain 0004→0008→0012).

## Decision

1. **Accept ADR-0013** documenting the incident and preventive rules.
2. **Migration 0018** (`0018_fix_item_id_nullable.py`) applies the DDL fix with idempotent guards using `DO $$ BEGIN ... EXCEPTION ... END $$` pattern.
3. **Post-deploy schema validation** will be handled in a separate hardening TZ (out of scope for this ADR).

## Preventive Rules for Future Migrations

The following rules are adopted for all future Alembic migrations in SyncServer:

### Rule 1: No state-dependent guard conditions for DDL

Do NOT write guard conditions in `upgrade()` that check a column's or constraint's current state and skip DDL based on it, when the same migration later changes that state. Example of the anti-pattern:

```python
# ANTI-PATTERN — DO NOT USE
def upgrade():
    if column_is_part_of_pk("issued_asset_balances", "item_id"):
        # skip — guard silently drops the critical ALTER
        pass
    else:
        op.execute("ALTER TABLE issued_asset_balances ALTER COLUMN item_id DROP NOT NULL;")
    # later in same migration... PK changed!
    op.execute("ALTER TABLE issued_asset_balances DROP CONSTRAINT pk_...;")
```

✅ **Preferred**: Idempotent DDL with exception handling (PostgreSQL `DO $$ BEGIN ... EXCEPTION ... END $$`), or pre-flight `ALTER TABLE ... DROP NOT NULL` before PK change.

### Rule 2: Verify model-DB schema alignment after migration

After any migration that changes column nullability, constraints, or types, run a verification step:
- Query `information_schema.columns` for the affected tables
- Compare `is_nullable` with the SQLAlchemy model's `nullable` attribute
- Fail CI if mismatch found

### Rule 3: Review migration chain for cumulative effects

When reviewing a migration PR, trace the full chain of previous migrations for the affected tables. A column may have been created in migration A, modified in migration B, and the modification may have been silently skipped or partially applied.

### Rule 4: Test migrations on both clean and dirty databases

Run `alembic upgrade head` against:
- A clean database (no prior migrations) — verifies full chain works
- A database at the previous head — verifies incremental upgrade
- A database where the fix was already applied manually — verifies idempotency

## Consequences

### Positive

- The fix is applied and verified on the dev stand
- The incident root cause is documented for future reference
- Preventive rules reduce the likelihood of similar incidents
- Migration 0018 is idempotent and handles clean, dirty, and manually-fixed databases

### Negative

- Schema validation is not yet automated in CI — this is deferred to a separate hardening TZ
- Developers must manually learn and apply the preventive rules until automated checks exist

### Risks

- If another migration introduces a similar guard anti-pattern before automated validation is in place, the same class of bug could recur
- Migration 0018 downgrade may silently skip `SET NOT NULL` if NULL values exist in `item_id` — this is intentional and documented

## References

- Migration 0004: `SyncServer/alembic/versions/0004_operations_acceptance_asset_registers.py` (lines 77-82)
- Migration 0008: `SyncServer/alembic/versions/0008_inventory_subjects_backfill.py` (lines 211-229, 371-403)
- Migration 0012: `SyncServer/alembic/versions/0012_issue_objects.py` (lines 91-120)
- Migration 0018: `SyncServer/alembic/versions/0018_fix_item_id_nullable.py`
- TZ-0018: `docs/TZ-0018-FIX_ITEM_ID_NULLABLE.md`
- Model: `SyncServer/app/models/asset_register.py` (lines 122-153)
