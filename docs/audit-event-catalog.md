# Audit Event Catalogue — Phase 1 (Storage Foundation)

Generated from `docs/TZ-AUDIT_BACKEND_FOUNDATION.md` §8.
For architectural rationale and FK policy, see
`docs/adr/0018-audit-architecture.md`.

Phase 1 records **24 distinct event types** across four groups (Stage A
additions marked `+`):

- **Operations** — 8 (`operation.line_accepted`, `operation.line_mark_lost`,
  `operation.line_lost_resolved`, `operation.restore`)
- **Catalog** — 11 (`unit.delete`, `category.delete`, `item.delete`)
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

## 1. Operations (8 events)

| event_type | outcome | changes (v2 schema) | resources | item_effects |
|---|---|---|---|---|
| `operation.create` | `success` | `{operation_type, site_id, source_site_id?, destination_site_id?, lines_count, has_temporary_items}` | `primary=operation` | — |
| `operation.update` | `success` | `{fields_changed: [...], lines_count_before, lines_count_after}` | `primary=operation` | — |
| `operation.update` (effective_at route only) | `success` | `{fields_changed: ["effective_at"], diff: {effective_at: {old, new}}, lines_count_before, lines_count_after}` | `primary=operation` | — |
| `operation.submit` | `success` | `{operation_type, lines_count, total_qty}` | `primary=operation` | yes — effect_type derived from operation_type (`receipt`/`expense`/`write_off`/`move_out`/`move_in`/`adjustment`/`issue`/`issue_return`); `effective_at` = `Operation.effective_at` |
| `operation.acceptance_complete` | `success` | `{resolved_lines, accepted_qty, lost_qty}` | `primary=operation` | yes — aggregate lifecycle event, does **not** own per-line effects |
| `operation.line_accepted` | `success` | `{operation_id, line_id, accepted_qty, action_id}` | `primary=operation_line` | yes — `effect_type='acceptance'`, `effective_at` = `OperationAcceptanceAction.performed_at` |
| `operation.line_mark_lost` | `success` | `{operation_id, line_id, lost_qty, action_id}` | `primary=operation_line` | **no** warehouse effect — lost moves from pending to lost register, balance unchanged |
| `operation.line_lost_resolved` | `success` | `{operation_id, line_id, action_type: found_to_destination\|return_to_source\|write_off, qty, action_id}` | `primary=operation_line` | yes only for `found_to_destination` and `return_to_source` (`effect_type='acceptance'`); `write_off` writes no warehouse effect |
| `operation.restore` | `success` | `{previous_status: cancelled, new_status: draft, previous_version, new_version, cancelled_at_before, cancelled_by_user_id_before?, cancel_reason_before?, restored_by_user_id, cancel_event_missing?}` | `primary=operation`; `parent_event_id` points to last successful `operation.cancel` of the same operation when available | — |
| `operation.cancel` | `success` | `{reason?, was_submitted, reversal_lines_count}` | `primary=operation` | yes — effect_type=`cancel_reversal` (inverse sign); `effective_at` = `Operation.cancelled_at` |
| `operation.delete` | `success` | `{status_before_delete}` | `primary=operation` | — |

### Notes — operations

- `operation.update` covers both the meta change route
  (`PATCH /operations/{id}`) and the dedicated
  `PATCH /operations/{id}/effective-at` route. The latter packs a
  `diff` block so the chronicle can show what changed. The dedicated
  `effective_at` route only mutates `effective_at` on operations whose
  status is `draft` (ADR-0028 §2 / Stage A-1).
- `operation.submit` writes one `audit_item_effects` per balance change
  with `effective_at = Operation.effective_at`. For MOVE operations two
  effects are produced (one per site). The `outcome` is `success`;
  cancellation/rejection goes through `operation.cancel` with
  `cancel_reversal` (`effective_at = Operation.cancelled_at`).
- `operation.acceptance_complete` writes effects when the acceptance
  lifecycle promotes pending balances to real; it is the aggregate
  lifecycle event and **does not own per-line effects** (ADR-0028 §4.3).
  Per-line warehouse mutations belong to the per-action events below.
- `operation.line_accepted` / `operation.line_mark_lost` /
  `operation.line_lost_resolved` carry the per-action observability for
  acceptance and lost-resolution flows. Only `accept` and the
  `found_to_destination`/`return_to_source` lost resolutions write
  `audit_item_effects` rows (`effect_type='acceptance'`); `mark_lost` and
  lost `write_off` write events but no warehouse effect because the
  warehouse balance is unchanged (the qty only moves between pending and
  lost registers).
- `operation.restore` is the causal child of the last successful
  `operation.cancel` for the same operation. `parent_event_id` points to
  that cancel event when available; otherwise the `changes` payload
  carries `cancel_event_missing=true`.

---

## 2. Catalog (11 events)

| event_type | outcome | changes (v2 schema) | resources |
|---|---|---|---|
| `unit.create` | `success` | `{name, symbol, is_active}` | `primary=unit` |
| `unit.update` | `success` | `{fields_changed: [...], diff: {field: {old, new}}}` | `primary=unit` |
| `unit.delete` | `success` | `{deleted_at, deleted_by_user_id}` | `primary=unit` (snapshot_before/snapshot_after per ADR-0028 §3.2 allow-list) |
| `category.create` | `success` | `{name, code?, parent_id?}` | `primary=category` |
| `category.update` | `success` | `{fields_changed: [...], diff: {field: {old, new}}}` | `primary=category` |
| `category.delete` | `success` | `{deleted_at, deleted_by_user_id}` | `primary=category` (snapshot_before/snapshot_after) |
| `category.merge` | `success` | `{source_category_id, target_category_id, comment?, items_moved_count, subcategories_reparented_count}` | `merge_source=category`, `merge_target=category`, `category_changed=item_id` (per item), `reparented=category_id` (per subcategory) |
| `item.create` | `success` | `{name, sku?, category_id, unit_id, is_active, requires_review}` | `primary=item` |
| `item.update` | `success` | `{fields_changed: [...], diff: {field: {old, new}}}` | `primary=item` |
| `item.delete` | `success` | `{deleted_at, deleted_by_user_id}` | `primary=item` (snapshot_before/snapshot_after) |
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
| `acceptance` | per-action accept/found/return effects (ADR-0028 §4.3 effect ownership). The aggregate `operation.acceptance_complete` does **not** write acceptance effects. |
| `merge_write_off` | source write-off inside an `item.merge` ADJUSTMENT. |
| `merge_receipt` | target receipt inside an `item.merge` ADJUSTMENT. |
| `temporary_write_off` | source-side delta inside `temporary_item.{approve,merge}`. |
| `temporary_receipt` | target-side delta inside `temporary_item.{approve,merge}`. |
| `review_write_off` | source-side delta inside `review_item.merge`. |
| `review_receipt` | target-side delta inside `review_item.merge`. |
| `cancel_reversal` | inverse delta in `operation.cancel`. |

Any new effect type added in Phase 2 MUST be one of these strings or a
new entry added to the catalogue above.

### `effective_at` semantics

`audit_item_effects.effective_at` (added in migration `0037`) is the
immutable business timestamp at which the specific balance mutation
becomes effective. It is **distinct** from `created_at`, which is the
physical insert time. Stage A uses a cause-specific matrix so late
acceptance and cancel reversal do not get re-dated to the original
operation:

| Producer / cause | New effect `effective_at` |
|---|---|
| forward effect at `operation.submit` | `Operation.effective_at` |
| system ADJUSTMENT submit (merge/review/temporary) | the generated operation's `effective_at` |
| per-line acceptance (`operation.line_accepted`) | `OperationAcceptanceAction.performed_at` |
| lost resolution acceptance (`operation.line_lost_resolved`) | `OperationAcceptanceAction.performed_at` |
| cancel reversal | `Operation.cancelled_at` |
| correction delta | application timestamp / `operation.correction.applied.created_at` |
| unknown future producer | explicit cause timestamp; server default is the safety net, not the source of truth |

The backfill for pre-Stage A effects uses the same matrix and never
silently inserts `now()`; migration 0037 aborts if any NULL remains.
