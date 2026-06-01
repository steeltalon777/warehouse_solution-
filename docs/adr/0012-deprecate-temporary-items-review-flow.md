# ADR-0012: Deprecate Temporary Items For New Operations

## Status
Accepted

## Date
2026-06-01

## Context

`TemporaryItem` and `/api/v1/temporary-items/*` were introduced for fast warehouse intake when the catalog was incomplete.

Client review on 2026-06-01 confirmed that this is no longer the target product flow for new operations. The desired behavior is:

- draft operations may still carry inline temporary payload in `temporary_draft_payload`;
- submit must materialize that payload into a regular catalog `Item`;
- the created item must be marked with `requires_review=true` and `review_status="needs_review"`;
- legacy `temporary_items` tables and APIs must remain available for backward compatibility with old data and old review history.

## Decision

For new operation submit flow, SyncServer creates a permanent catalog item directly instead of creating a new `TemporaryItem` row.

Rules:

1. `create operation` stores inline payload only in draft line snapshots and `temporary_draft_payload`.
2. `submit operation` creates a permanent `Item` with review flags and a normal `InventorySubject`.
3. `temporary_draft_payload` is cleared after materialization.
4. Review moderation for these items goes through `/api/v1/review-items/*`.
5. Legacy `/api/v1/temporary-items/*` endpoints stay supported only for already-existing `TemporaryItem` records.

## Consequences

- New warehouse operations participate in balances and registers through normal catalog items immediately after submit.
- Review-specific UX and tests must target `review-items`, not creation of fresh `TemporaryItem` records.
- Old temporary item data can still be listed, resolved, and deleted through legacy compatibility endpoints.

## Confidence

High. This matches the current product decision, implemented service behavior, and updated functional requirements.
