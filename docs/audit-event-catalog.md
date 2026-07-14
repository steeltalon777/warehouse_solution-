# Audit Event Catalogue — Phase 1 (Storage Foundation)

Generated from `docs/TZ-AUDIT_BACKEND_FOUNDATION.md` §8.
For architectural rationale and FK policy, see
`docs/adr/0018-audit-architecture.md`.

Phase 1 records **20 distinct event types** across four groups:

- **Operations** — 6
- **Catalog** — 8
- **Related entities** (temporary / review / issue_object) — 5
- **Batch** — 1

Phase 2 will add admin / security events and credential-fingerprint
populations.

---

## Conventions

- Every event row in this catalogue has
  `event_version = 2`.
- The `changes` JSONB is documented below. Older rows created before
  this work has `event_version = 1` and may have a free-form JSONB.
- Read code MUST branch on `event_version` before deserialising
  `changes`.
- `outcome` is one of `success` / `partial` / `failed` / `denied`.
- `correlation_id` is set for batch-driven events so a single query
  pulls the parent + all children.
- `parent_event_id` (UUID) is set on child events whose parent is
  another audit event (e.g. system ADJUSTMENT submits under
  `item.merge`).

### Resource link conventions

The `audit_event_resources` table records edges from an event to
domain entities. Relation values used in Phase 1:

| Relation | Meaning |
|---|---|
| `primary` | The main entity the event is about. |
| `merge_source` / `merge_target` | The two endpoints of a merge. |
| `generated` | A sub-operation (e.g. system ADJUSTMENT) produced by this event. |
| `reparented` | A sub-category reassigned from source to target parent. |
| `category_changed` | An item moved between categories. |

---

## 1. Operations (6 events)

| event_type | outcome | changes (v2 schema) | resources | item_effects |
|---|---|---|---|---|
| `operation.create` | `success` | `{operation_type, site_id, source_site_id?, destination_site_id?, lines_count, has_temporary_items}` | `primary=operation` | — |
| `operation.update` | `success` | `{fields_changed: [...], lines_count_before, lines_count_after}` | `primary=operation` | — |
| `operation.update` (effective_at route only) | `success` | `{fields_changed: ["effective_at"], diff: {effective_at: {old, new}}, lines_count_before, lines_count_after}` | `primary=operation` | — |
| `operation.submit` | `success` | `{operation_type, lines_count, total_qty}` | `primary=operation` | yes — effect_type derived from operation_type (`receipt`/`expense`/`write_off`/`move_out`/`move_in`/`adjustment`/`issue`/`issue_return`) |
| `operation.acceptance_complete` | `success` | `{resolved_lines, accepted_qty, lost_qty}` | `primary=operation` | yes — effect_type=`acceptance` |
| `operation.cancel` | `success` | `{reason?, was_submitted, reversal_lines_count}` | `primary=operation` | yes — effect_type=`cancel_reversal` (inverse sign) |
| `operation.delete` | `success` | `{status_before_delete}` | `primary=operation` | — |

### Notes — operations

- `operation.update` covers both the meta change route
  (`PATCH /operations/{id}`) and the dedicated
  `PATCH /operations/{id}/effective-at` route. The latter packs a
  `diff` block so the chronicle can show what changed.
- `operation.submit` writes one `audit_item_effects` per balance
  change. For MOVE operations two effects are produced (one per
  site). The `outcome` is `success`; cancellation/rejection goes
  through `operation.cancel` with `cancel_reversal`.
- `operation.acceptance_complete` writes effects when the
  acceptance lifecycle promotes pending balances to real.

---

## 2. Catalog (8 events)

| event_type | outcome | changes (v2 schema) | resources |
|---|---|---|---|
| `unit.create` | `success` | `{name, symbol, is_active}` | `primary=unit` |
| `unit.update` | `success` | `{fields_changed: [...], diff: {field: {old, new}}}` | `primary=unit` |
| `category.create` | `success` | `{name, code?, parent_id?}` | `primary=category` |
| `category.update` | `success` | `{fields_changed: [...], diff: {field: {old, new}}}` | `primary=category` |
| `category.merge` | `success` | `{source_category_id, target_category_id, comment?, items_moved_count, subcategories_reparented_count}` | `merge_source=category`, `merge_target=category`, `category_changed=item_id` (per item), `reparented=category_id` (per subcategory) |
| `item.create` | `success` | `{name, sku?, category_id, unit_id, is_active, requires_review}` | `primary=item` |
| `item.update` | `success` | `{fields_changed: [...], diff: {field: {old, new}}}` | `primary=item` |
| `item.merge` | `success` | `{source_item_id, target_item_id, comment?, balances_transferred: [{site_id, qty}], op_lines_reassigned_count}` | `merge_source=item`, `merge_target=item`, `generated=operation` (per system ADJUSTMENT) |

`item.deactivate` and `category.deactivate` do **not** exist as
separate events; deactivation is recorded as `item.update` /
`category.update` with `diff.is_active = {old: true, new: false}`.

### Notes — catalog

- The `item.merge` event id (UUID) appears as `parent_event_id` on
  every child `operation.submit` event generated by the merge.
- The `category.merge` event does not move balances — it only
  reassigns items and subcategories. Resource edges `category_changed`
  and `reparented` give full accounting without effects rows.

---

## 3. Related entities (5 events)

| event_type | outcome | changes (v2 schema) | resources | item_effects |
|---|---|---|---|---|
| `temporary_item.approve` | `success` | `{temporary_item_id, new_item_id, inventory_subject_id}` | `primary=new_item`, `merge_source=temporary_item`, `generated=operation` (per system ADJUSTMENT) | yes — `temporary_write_off` / `temporary_receipt` |
| `temporary_item.merge` | `success` | `{temporary_item_id, target_item_id, inventory_subject_id, comment?}` | `primary=target_item`, `merge_source=temporary_item`, `generated=operation` | yes |
| `review_item.confirm` | `success` | `{item_id, resolution_type: "confirmed", corrections: {...}}` | `primary=item` | — |
| `review_item.merge` | `success` | `{item_id, target_item_id, resolution_note?}` | `primary=target_item`, `merge_source=item`, `generated=operation` | yes — `review_write_off` / `review_receipt` |
| `issue_object.merge` | `success` | `{source_id, target_id}` | `primary=target`, `merge_source=source` | — |

### Notes — related entities

- `issue_object.merge` issues no effect rows because the operation
  side has no balance projection. The chronicle fully reconstructs
  the merge from the event's resource edges.
- All three merge-via-system-ADJUSTMENT flows
  (`item.merge`, `temporary_item.merge`, `review_item.merge`) record
  their effects under the child `operation.submit` events so the
  balance journal always rolls up to a transaction boundary.

---

## 4. Batch (1 event)

| event_type | outcome | changes (v2 schema) | resources |
|---|---|---|---|
| `catalog.batch.apply` | `success` or `partial` | `{total_changes, results: [{local_id, entity_type, action, status, entity_id?, error_code?, error_message?}]}` | `primary=batch` |

### Notes — batch

- The batch summary event is written AFTER every per-change child
  has run, so its `results` array reflects the final state.
- `outcome = success` ⇒ `summary.error == 0`.
- `outcome = partial` ⇒ at least one change has `status = 'error'`
  in `results`.
- Every event recorded DURING the batch (item.update, category.update,
  …) inherits the same `correlation_id` so a single
  `SELECT * FROM audit_events WHERE correlation_id = ?` reconstructs
  the whole batch.

---

## 5. Effect-type vocabulary

The `audit_item_effects.effect_type` column is one of:

| Value | Producer |
|---|---|
| `receipt` | RECEIVE operations. |
| `expense` | EXPENSE operations. |
| `write_off` | WRITE_OFF (without issue object). |
| `move_out` | MOVE source-side decrement. |
| `move_in` | MOVE destination-side increment. |
| `adjustment` | generic ADJUSTMENT operation. |
| `issue` | ISSUE operations. |
| `issue_return` | ISSUE_RETURN operations. |
| `acceptance` | promotion of pending balance during `operation.acceptance_complete`. |
| `merge_write_off` | source write-off inside an `item.merge` ADJUSTMENT. |
| `merge_receipt` | target receipt inside an `item.merge` ADJUSTMENT. |
| `temporary_write_off` | source-side delta inside `temporary_item.{approve,merge}`. |
| `temporary_receipt` | target-side delta inside `temporary_item.{approve,merge}`. |
| `review_write_off` | source-side delta inside `review_item.merge`. |
| `review_receipt` | target-side delta inside `review_item.merge`. |
| `cancel_reversal` | inverse delta in `operation.cancel`. |

Any new effect type added in Phase 2 MUST be one of these strings or a
new entry added to the catalogue above.
