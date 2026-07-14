# ADR-0018: Audit journal architecture (Phase 1 Storage Foundation)

## Status

Accepted — TZ-AUDIT_BACKEND_FOUNDATION implementation (2026-07-14).

## Context

SyncServer is the authoritative warehouse backend. All business writes
(operations, catalog merges, item resolutions, batch applies) happen on
this service. The previous audit story (`audit_events` table + a
dedicated `record_audit_event()` helper) only captured a single
summary line per event; it had no way to record:

- resource links (a merge event references source + target items);
- balance effects (every operation submit touches N balances; we want
  a row per delta, not a single rolled-up counter);
- parent-child relationships between merge events and the system
  ADJUSTMENT operations they generate;
- batch correlations between a `catalog.batch.apply` summary and its
  child events;
- operational metadata (`outcome`, `source_client`, username
  snapshot, idempotency key for Phase 2 inbound events).

The chronicle must be **append-only and reconstructable**: given a
canonical item, we must be able to find every balance delta, even
after several merge rounds.

## Decision

We split the journal into three tables and a one-shot capture helper.

### 1. `audit_events` (extended) — the spine

Append-only event log. New fields:

| Field | Type | Purpose |
|---|---|---|
| `event_version` | int NOT NULL default 2 | Schema version of `changes`. Existing 339 rows backfilled to 1. |
| `outcome` | string(32) | `success` / `partial` / `failed` / `denied`. |
| `correlation_id` | string(64) | Groups events of one batch. |
| `parent_event_id` | UUID FK → `audit_events.event_id` ON DELETE RESTRICT | Child-of link (merge → its system ADJUSTMENT submits). |
| `credential_kind`, `credential_fingerprint` | strings | Phase 2 hooks. Columns exist now, populated later when the Auth outbox lands. |
| `source_client` | string(32) | `web` / `desktop` / `mobile` / `cli` / `unknown`. |
| `actor_username_snapshot` | string(128) | Username at event time (snapped, not joined). |
| `external_event_id` | string(128) UNIQUE | Idempotency key (Phase 2). |

### 2. `audit_event_resources` — edge table

`(event × resource × relation × snapshot)` edges. Lets one event
reference many entities with named roles:

- `merge_source`, `merge_target` (item.merge, category.merge,
  issue_object.merge, review_item.merge, temporary_item.merge);
- `generated` (system ADJUSTMENT operations under a merge);
- `reparented`, `category_changed`, `primary`, `affected`,
  `inventory_subject`.

No FK to the linked resource. By design — audit must outlive the
domain entity. Resolved at the application layer.

### 3. `audit_item_effects` — balance delta journal

One row per actual balance change. INVARIANT: the row is written
**before** any destructive domain mutation that would erase the link
to the source. Append-only.

| Field | Notes |
|---|---|
| `inventory_subject_id` | mandatory; the journal can't exist without a subject. |
| `item_id` | nullable (temporary items have no catalog row yet). |
| `item_name_snapshot`, `item_sku_snapshot`, `subject_type` | Survive deactivation. |
| `quantity_before`, `quantity_delta`, `quantity_after` | Numbers in NUMERIC(18,4). |
| `effect_type` | `receipt` / `expense` / `write_off` / `move_out` / `move_in` / `adjustment` / `issue` / `issue_return` / `merge_write_off` / `merge_receipt` / `temporary_write_off` / `temporary_receipt` / `review_write_off` / `review_receipt` / `cancel_reversal`. |
| `is_system_generated` | true when produced by an `origin='system'` op. |
| `caused_by_event_id` | FK → `audit_events.id` RESTRICT. Causal link. |

### 4. `record_audit_event()` helper

A small async helper (≈40 lines) that wraps `AuditEvent` + insert.
Service-layer code calls it for every business event; the helper
validates `source_client` against an allow-list (anything else →
`'unknown'`) and inherits `correlation_id` from the UoW context when
the caller doesn't pass one.

### 5. UoW context slots

| Slot | Read by | Written by |
|---|---|---|
| `batch_correlation_id` | `record_audit_event` | `catalog.apply_batch` (top of the loop). |
| `audit_parent_event_id` | `record_audit_event`, `submit_operation`, `cancel_operation` | `item.merge` / `temporary_item.merge` / `review_item.merge`. |
| `audit_caused_by_event_id` | `_write_captured_effects` | same. |
| `audit_effect_type_override` | `_write_captured_effects` | same. |

Each slot is set under a `try / finally` so the values cannot leak into
unrelated calls. Restoring them after the merge block keeps the
helper signature stable without losing per-call metadata.

## Ordering invariants

### `item.merge` (`merge_items`)

```text
BEGIN UoW
  1. INSERT AuditEvent(item.merge)           ← parent event FIRST
  2. Set uow.audit_parent_event_id = merge_event.event_id
  3. Set uow.audit_effect_type_override = 'merge_write_off'
  4. Create + submit system ADJUSTMENT for write-off
  5. Set uow.audit_effect_type_override = 'merge_receipt'
  6. Create + submit system ADJUSTMENT for receipt
  7. INSERT audit_item_effects rows (effect_type = merge_write_off/merge_receipt,
     item_id = source)        ← BEFORE reassignment
  8. INSERT audit_event_resources (merge_source, merge_target, generated → op ids)
  9. UPDATE OperationLine.item_id: source → target   ← LAST destructive mutation
 10. UPDATE items SET is_active=false, merged_into_id=target
COMMIT

If any step fails → rollback → E1 (the merge event) is gone too.
```

Why the effect rows are written before the OperationLine update:
**effects are the durable proof** that balance once belonged to the
source item. Reassigning the line first would erase every FK between
the line and the source while leaving the effects orphaned in id-space.
Writing effects first, with `item_id = source_id` captured, makes the
chronicle reconstructable even after the FK update.

### `submit_operation` / `cancel_operation`

Effects are written AFTER the audit event so `audit_event_id` is
available. Capture happens in a per-call list:

```text
for line in operation.lines:
    await _capture_balance_change(... capture=effects_capture ...)
    # this locks the row, computes before/after, mutates balance,
    # appends to the capture list with effect_type from operation_type
    # or from uow.audit_effect_type_override (for system flows)

await record_audit_event(... operation.submit ...)
for c in effects_capture:
    await uow.audit_events.insert_effect(AuditItemEffect(audit_event_id=submit_id, ...))
```

For cancel, the loop uses `_apply_balance_delta(... capture=...)` with
`effect_type='cancel_reversal'` to flip sign.

## FK policy (the table of trade-offs)

| Column | Domain | Behaviour | Rationale |
|---|---|---|---|
| `audit_events.parent_event_id` | `audit_events` | RESTRICT | Audit is append-only. |
| `audit_event_resources.audit_event_id` | `audit_events` | RESTRICT | same. |
| `audit_item_effects.audit_event_id` | `audit_events` | RESTRICT | same. |
| `audit_item_effects.audit_event_id` (caused_by) | `audit_events` | RESTRICT | Reasoning chain preserved. |
| `audit_item_effects.operation_id` | `operations` | SET NULL | Operations may be hard-deleted later. |
| `audit_item_effects.inventory_subject_id` | `inventory_subjects` | RESTRICT | A subject must exist for its effect. |
| `audit_item_effects.item_id` | `items` | RESTRICT | History of an item must not vanish. |
| `audit_item_effects.site_id` | `sites` | SET NULL | Sites are configuration data. |
| `audit_events.parent_event_id` self-FK | `audit_events` | RESTRICT | Same as above. |

`audit_event_resources` has **no FK to domain entities**. The
referenced target may be hard-deleted later and the audit must remain
correct — that's why snapshot fields exist on the edge row.

## Merge closure vs canonical_item_id

Earlier proposals stored `canonical_item_id` on each effect row. We
rejected that because:

```
January:  audit_item_effects (canonical_item_id=10)
March:    Item 10 → Item 20 (merge)
June:     Item 20 → Item 30 (merge)
```

Searching "history of canonical item 30 with follow_merges" by
`canonical_item_id = 30` would miss the January row.

Instead we keep `merged_into_id` on the **item** and use a closure
algorithm on read:

```python
async def build_merge_closure(uow, item_id):
    closure = {item_id}
    current = item_id
    while await uow.catalog.get_item_by_id(current):
        item = await uow.catalog.get_item_by_id(current)
        if item.merged_into_id is None: break
        current = item.merged_into_id
        closure.add(current)
    # and predecessors
    ...
    return closure
```

The closure walks both directions of the merge chain and is short
(1–3 levels in practice). Read-side cost is bounded; if it ever
becomes a hotspot, the lazy option is to materialise the closure in a
materialised view.

## What's deferred to Phase 2

- Django `AuditOutbox` table and `deliver_audit_outbox` command.
- SyncServer `POST /system/audit-event` accepting outbox events with
  retry/dedup using `external_event_id`.
- `credential_kind` / `credential_fingerprint` population.
- Admin / security events (`user.create`, `device.rotate_token`, …).
- Read API: `GET /admin/audit/items/{id}/history` with merge closure,
  `GET /admin/audit/batch/{correlation_id}` for batch detail.
- Retention policy and management commands.
- Frontend: timeline, filters, card UI.

## Consequences

### Positive

- Reconstructable balance history per item, even after merges.
- Batch parent and child events link via `correlation_id` — easy to
  pull "what changed when this batch ran".
- Append-only invariant is enforced at the DB level via RESTRICT.
- Schema-ready for Phase 2 auth outbox (columns in place).
- 27 new unit + integration tests cover the storage layer.
- Smoke tests on the live stand confirm the journal writes for
  operation submit, item merge, and partial batch.

### Negative

- The Merge closure is computed at read time. If merge chains become
  very deep or `get_effects_by_item` is hot, this is a measurable
  cost. Materialised view is the mitigation; we have not built it yet.
- `audit_event_resources` is row-per-link. A 1000-item batch in the
  future would write 2000 resource rows (item_changed × 1000 +
  merge pairs). Not a problem at current sizes.
- The journal is in the same database as the business data. A
  long-term retention or archival split is **out of scope** for
  Phase 1 — Phase 2 will need to address it before retention cleanup
  starts deleting old events.

## Alternatives considered

1. **Single `audit_events` row per change, JSONB-serialised effects.**
   We rejected this because read-history-by-item would have to scan
   `audit_events` and JSON-parse every row; `audit_item_effects`
   gives a proper index on `item_id`.

2. **Kafka / outbox from the start.** Rejected for Phase 1. The
   storage is the foundation; transport comes in Phase 2 when the
   Django outbox is built.

3. **Celery / external broker.** Rejected — out of scope. SyncServer
   stays synchronous; the outbox pattern can pull events into any
   transport later.

## References

- `docs/TZ-AUDIT_BACKEND_FOUNDATION.md` — the TZ this ADR
  implements (sections 6, 7, 8, 10).
- `docs/audit-event-catalog.md` — the catalogue of every event
  recorded in Phase 1.
- ADR-0003 (Unit of Work) — the transactional boundary this ADR
  relies on.
- ADR-0011 (Django ↔ SyncServer internal transport) — leaves the
  Auth outbox transport to Phase 2.
