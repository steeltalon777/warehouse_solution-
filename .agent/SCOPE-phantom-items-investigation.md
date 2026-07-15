# Investigation: Phantom Items — why is_active stays True after soft_delete

## Assignment

Investigate the root cause of 38 phantom/zombie items on production (IDs ~3130, 3162-3198).
These items have BOTH `deleted_at` set AND `is_active=True`, contradicting
`catalog_repo.soft_delete_item()` which sets `is_active = False` on line 548.

## Confirmed Facts

1. `catalog_repo.soft_delete_item()` (line 518-549) sets:
   - `item.deleted_at = datetime.now()` (line 546)
   - `item.is_active = False` (line 548)
   - `await self.session.flush()` (line 549)

2. The phantom items on production (admin API confirmed):
   - `is_active: true`
   - `deleted_at: 2026-07-14T06:21:09.992282Z`
   - `requires_review: true`
   - `review_status: "needs_review"`

3. Dev code now filters `deleted_at IS NULL` in read API — so zombies won't appear
   after redeploy. But root cause is still unknown.

## What to Investigate

1. **Can `is_active` be reset after `soft_delete_item`?**
   - Check if any SQLAlchemy event listener, database trigger, or column default
     could override `is_active = False` after flush
   - Check `Item.is_active` column definition for `server_default` or `onupdate`

2. **Is `soft_delete_item` called through an unexpected code path?**
   - `_soft_delete_review_items_of_cancelled_operation` (operations_service.py:2078)
     calls `uow.catalog.soft_delete_item(item_id, user_id)` on line 2119
   - Check if there's a concurrent transaction that reverts `is_active`

3. **What happens with non-zero balances?**
   - `soft_delete_item` checks balances (lines 536-544) and raises ValueError
   - The ValueError is caught at line 2120: `except ValueError: pass`
   - Items WITH non-zero balance are skipped entirely — deleted_at NOT set
   - So zombie items must have had zero balance at deletion time

4. **Check the exact SQL produced by `flush()`:**
   - Mock or log the SQLAlchemy SQL statements during soft_delete
   - Verify both `deleted_at` and `is_active` appear in the UPDATE

## Files to Check

- `SyncServer/app/repos/catalog_repo.py:518-549` — soft_delete_item
- `SyncServer/app/services/operations_service.py:2078-2147` — cancel flow
- `SyncServer/app/services/review_items_service.py:372-381` — alternate delete
- `SyncServer/app/models/item.py` — Item.is_active column definition
- `SyncServer/alembic/versions/` — any migration affecting is_active default

## Deliverable

A report answering:
1. Why `is_active` stays True when `deleted_at` is set?
2. Is this reproducible in dev environment?
3. How many existing items on production are affected?
4. Recommended fix (if different from current dev code)

## Out of Scope

- Fixing the issue (this is investigation only)
- Read API changes (already done)
- Angular changes
