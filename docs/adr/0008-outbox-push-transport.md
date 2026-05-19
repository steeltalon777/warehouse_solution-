# ADR-0008: Outbox Push Transport Strategy

## Status
Proposed

## Date
2026-05-16

## Context

Offline clients create operation drafts, then submit them when network is available. Two transport paths exist in SyncServer:

1. **Device sync `/push`**: Accepts `EventIn` payloads authenticated by `X-Device-Token`. Events are idempotent by `event_uuid`. The existing server endpoint processes operation-like events. However, it is designed for device-level events, not full user-context operation replay.

2. **User-token operation endpoints** (`POST /operations`, `PATCH /operations/{id}/submit`, etc.): These are the normal REST API authenticated by `X-User-Token`. They support the full operation workflow but lack built-in offline queuing semantics.

## Decision

**Two-phase transport with HTTP command outbox as primary, device push as secondary.**

### Phase 1 (Levels 7-8): HttpCommandOutboxTransport

- Outbox replays user-intent commands through normal user-token endpoints.
- Draft submit → outbox event → `POST /operations`.
- Draft edit → `PATCH /operations/{id}`.
- Draft cancel → `POST /operations/{id}/cancel`.
- Each outbox record stores the HTTP method, path, and serialized body.
- Idempotency is handled via `Idempotency-Key` header where SyncServer supports it; otherwise by tracking server-assigned operation IDs.

### Phase 2 (Level 9+): DevicePushTransport (when feasible)

- If `/push` event schema proves semantically complete for all operation commands, add push as an alternative transport.
- Transport selection is configurable per outbox event type.
- Device sync remains primary for `EventIn`-style commands; user-token transport for anything `/push` cannot express.

### Rationale

- **User-token transport is complete today** — no SyncServer changes needed.
- **Device push event schema** may not yet cover all operation states (draft edits, effective-date changes, accept-lines). Mapping gaps would block the core.
- **Hybrid approach**: push what fits in events, REST for what doesn't. Outbox abstraction makes the transport swap transparent.

## Consequences

- Phase 1 delivers immediately: offline draft → queued → online replay.
- Phase 2 `/push` adoption reduces REST round-trips and enables event-level idempotency.
- Outbox events must store enough context to replay through either transport.
- If both transports are used, ordering guarantees must be documented.

## Confidence
**High** for Phase 1; **Medium** for Phase 2 pending SyncServer `/push` capability review.
