# Historical Integrity — active status

**As of:** 2026-08-06  
**Authority:** active coordination status; source research remains in the sibling audit documents.

## Current state

| Area | Status | Evidence |
|---|---|---|
| Read-only historical-integrity audit | Complete (2026-07-31) | `HISTORICAL_INTEGRITY_AUDIT.md` |
| Risk register R-01…R-40 | Complete | `HISTORICAL_RISK_REGISTER.md` |
| Staged roadmap A→E | Complete as planning research | `HISTORICAL_INTEGRITY_ROADMAP.md` |
| Stage A architecture decision | Accepted (ADR-0028) | `../adr/0028-historical-integrity-stage-a.md` |
| Stage A executable TZ | Implementation complete under ADR-0028 (Stage A-wide) | `../TZ-HISTORICAL_INTEGRITY_STAGE_A.md` §11/§17/§18 |
| Stage A architecture review | Approved with conditions | `../reviews/architecture-review-historical-integrity-stage-a.md` |
| Runtime code/migration A-1…A-7 | **Implemented** | see Evidence §18 of TZ + Stage A focused suites |
| Shared dev database | `alembic_version` = `0037_audit_item_effects_effective_at`; 21 effects preserved; NULL=0 | `SELECT version_num FROM alembic_version` |
| Stage B/C/D ADR/TZ | Not issued | Deferred until Stage A QA review and separate user authorization |

## Accepted Stage A scope

1. Draft-only mutation of operation `effective_at`.
2. `operation.restore` with cancel causal link where available.
3. `item.delete` / `category.delete` / `unit.delete` snapshots.
4. Per-action acceptance/lost audit plus missing warehouse effects for accept/found/return.
5. Event-aware `audit_item_effects.effective_at` migration and explicit producer timestamps.
6. `item-movement` system-operation filter, default `exclude_system_effects=true`, without replacing the operation-based report source; Django BFF transparently forwards explicit true/false.
7. Read-only `make integrity-check` with stable symbolic check codes.

## Corrections to the original research plan

Code verification before ADR release found four material details:

- Acceptance and lost resolution mutate `balances` without `audit_item_effects`; per-line audit events alone cannot satisfy the balance/effect invariant.
- Cancel reversal and late acceptance cannot be backfilled from the original operation date; each effect needs cause-specific time.
- `item-movement` is operation/line-based, not effect-based; system filtering must use `Operation.origin` in Stage A.
- R-26 requires a schedule, not only a CLI. Stage A closes diagnostic capability but leaves scheduling `partial/deferred`.

The accepted resolution is documented in ADR-0028 and reflected in the TZ. Historical audit documents are retained as research evidence and are not silently rewritten.

## Next gate

Executor starts from Stage 0 of the TZ:

1. confirm nested `SyncServer` branch/ownership and current Alembic head;
2. run baseline diagnostics read-only on a safe DB/clone;
3. implement sequentially A-1…A-7;
4. complete migration/test/stand/evidence ladder;
5. keep season-report/data acceptance blocked on unexplained critical integrity findings.

## Risk status rule

No R-risk is marked closed merely because ADR/TZ exists. Closure requires implementation evidence and QA verification. R-06 and R-26 remain partial even after Stage A unless the late-acceptance cutoff and scheduled execution are separately delivered.
