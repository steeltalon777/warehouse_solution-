# Architecture review — Historical Integrity Stage A

**Date:** 2026-08-05  
**Reviewer:** Architect Agent  
**Reviewed artifacts:** `docs/adr/0028-historical-integrity-stage-a.md`, `docs/TZ-HISTORICAL_INTEGRITY_STAGE_A.md`  
**Method:** architecture-review checklist (complexity, coupling, data/state, failure modes, security, scalability, observability, operability)

## Verdict

**Approved with conditions.** Architecture blockers found during review were resolved in ADR-0028/TZ before this verdict. Runtime implementation may begin only from TZ Stage 0. Data/season acceptance remains separate from feature acceptance and is blocked by unexplained critical integrity findings.

## Summary

| Class | Count | Release effect |
|---|---:|---|
| 🔴 Blockers | 0 | Architecture may proceed to executor Stage 0 |
| 🟡 Warnings | 8 | Tracked below and in ADR/TZ risks/out-of-scope |
| 🔵 Notes | 4 | Informational |

## Checklist result

| Category | Result | Evidence |
|---|---|---|
| Complexity | Pass | Existing operation-driven model, audit tables and report projection are retained; no event sourcing/new domain tables |
| Coupling & cohesion | Pass with condition | SyncServer owns rules/data; Django only forwards one query param; ownership shards and integration order are explicit |
| Data & state | Pass with condition | Cause-specific effect-time, event-aware migration, fail-closed effect persistence and rollback are specified |
| Failure modes | Pass | UoW atomicity, migration abort, read-only CLI errors, unavailable stand and unexplained data drift have explicit outcomes |
| Security | Pass | No secrets in output/evidence; CLI transaction is read-only; samples are bounded; browser remains behind Django BFF |
| Scalability | Pass with warning | Per-action O(N) writes and migration lock are measured/tested; no unbounded report join introduced |
| Observability | Pass with warning | JSON/text diagnostics and exit threshold exist; production scheduling/alerting is intentionally deferred |
| Operability | Pass with conditions | Clone dry-run, one-head check, downgrade/upgrade, explicit report fallback and NO-GO data gate are defined |

## Resolved blockers

### 1. Balance/effect invariant was impossible after acceptance

- **Checklist item:** Data & state / source of truth.
- **Issue found:** `accept_operation_lines` and `resolve_lost_asset` mutate `balances` directly but create no `audit_item_effects`. Literal roadmap A-4 added only events, so `BALANCE_EFFECT_DRIFT` could never pass.
- **Impact:** Silent forensic gap and permanent false critical drift.
- **Resolution applied:** A-4 now captures `acceptance` effects for accept/found/return and per-action events for all actions. Mark-lost/write-off correctly create no warehouse effect.

### 2. Simple operation-date backfill misdated reversals and late acceptance

- **Checklist item:** Data & state / migration correctness.
- **Issue found:** Backfilling every row from `operations.effective_at` would place July cancellation/acceptance into the original May period.
- **Impact:** Stage A itself would corrupt season attribution.
- **Resolution applied:** ADR-0028 cause-time matrix: submit uses operation date; acceptance/lost resolution uses action time; cancel uses cancellation time; correction uses application/event time. Migration is event-aware.

### 3. Adding the column with default before backfill could fabricate history

- **Checklist item:** Data & state / migration ordering.
- **Issue found:** Adding `effective_at DEFAULT now()` to existing rows before event-aware UPDATE risks treating migration time as historical fact or accidentally skipping rows when updating only NULLs.
- **Impact:** Irreversible-looking but false timestamps.
- **Resolution applied:** Add nullable without default → update all pre-existing rows → validate NULL=0 → set server default + NOT NULL.

### 4. Report filter was designed against the wrong physical source

- **Checklist item:** Coupling & cohesion / minimal API.
- **Issue found:** `list_item_movement` is operation/line UNION, not effect-based. Joining effects would multiply rows and force a report rewrite.
- **Impact:** Incorrect aggregates or Stage B/C scope explosion.
- **Resolution applied:** Filter each UNION arm by `COALESCE(Operation.origin,'user') != 'system'`; retain existing projection. Django BFF transparently forwards the option.

### 5. Existing item-movement endpoint already has a blocking xfail

- **Checklist item:** Failure modes / testability.
- **Issue found:** DB-backed test is xfail because `TemporaryItem.name` is missing from GROUP BY.
- **Impact:** New filter could appear implemented while the real PostgreSQL endpoint still fails.
- **Resolution applied:** A-6 prerequisite fixes GROUP BY and removes xfail before filter acceptance.

### 6. Effect persistence helper was fail-open

- **Checklist item:** Failure modes / partial failure.
- **Issue found:** `_write_captured_effects` silently returns when audit repo/insert hook is absent, even for non-empty capture.
- **Impact:** Misconfiguration or incomplete test double can let balance mutation commit without proof.
- **Resolution applied:** Non-empty capture becomes fail-closed; only empty capture may no-op. Test doubles must implement the audit contract.

### 7. Ordinal check labels were ambiguous

- **Checklist item:** Observability / operator contract.
- **Issue found:** Risk register and Season Readiness assign different meanings to Q1…Q7.
- **Impact:** Automation/evidence could report the wrong check as passing.
- **Resolution applied:** Stable symbolic codes such as `BALANCE_EFFECT_DRIFT`, `ACCEPTANCE_EFFECT_GAP`, `EFFECT_DATE_NULL`.

## 🟡 Warnings

### 1. Stage A does not make `item-movement` a true effect-time report

- **Issue:** Endpoint remains operation-based; accepted quantity may still be grouped under operation date.
- **Impact:** Historical as-of reports involving late acceptance remain conditional.
- **Mitigation:** ADR marks R-05/R-06 partial; Stage B/C must define effect-time/historical projection. Stage A stores correct effect timestamps and prevents new post-submit re-dating.

### 2. R-26 remains partial without schedule and alert owner

- **Issue:** `make integrity-check` is manual.
- **Impact:** Drift may remain undetected between operator runs.
- **Mitigation:** Do not mark R-26 closed. Separate operational TZ must define schedule, overlap policy, alert destination and first-run evidence.

### 3. Service guard does not stop privileged direct SQL

- **Issue:** Draft-only `effective_at` policy is application-enforced.
- **Impact:** DBA/manual SQL can still mutate submitted rows.
- **Mitigation:** Stage B DB trigger/policy; meanwhile no direct DB edits are permitted operationally and diagnostics flag backdated submitted rows.

### 4. Existing legacy/opening drift may remain critical

- **Issue:** Audit journal may postdate some balances or contain historical gaps.
- **Impact:** CLI can correctly fail even after code implementation.
- **Mitigation:** Feature acceptance records findings; season/data acceptance remains NO-GO until compensating operations, documented reconciliation or explicit owner risk acceptance. No silent suppression.

### 5. Migration lock duration is data-size dependent

- **Issue:** Event-aware UPDATE + index + NOT NULL can hold locks.
- **Impact:** Unplanned write downtime.
- **Mitigation:** Stage 0 row-count and timed clone dry-run. Split expand/backfill/contract revisions if outside agreed deployment window; update ADR/TZ before proceeding.

### 6. Per-action audit increases write amplification

- **Issue:** Mixed acceptance may add events, resources and effects per line/action.
- **Impact:** Larger transactions for high-line-count operations.
- **Mitigation:** One event only per non-zero action; realistic batch performance test; no speculative indexes beyond measured need.

### 7. Cancel after partial lost-resolution remains separate domain debt

- **Issue:** Current cancel logic derives rollback from cumulative `OperationLine.accepted_qty/lost_qty`; lost resolution later changes registers without reducing line lost_qty.
- **Impact:** Cancel may reject/rollback poorly after found/return actions, although UoW prevents partial commit.
- **Mitigation:** Stage A records the chain and tests atomic failure but does not redesign cancel math. Open a dedicated risk/TZ if reproducible; do not hide it inside A-4.

### 8. Default report totals intentionally change

- **Issue:** `exclude_system_effects=true` removes system ADJUSTMENT rows from default totals.
- **Impact:** Consumers comparing old/new reports see different values.
- **Mitigation:** ADR-accepted safety default, explicit `false` fallback through SyncServer and Django BFF, release note and truth-table/stand evidence.

## 🔵 Notes

1. No external service, broker, cache or new runtime dependency is introduced.
2. FULL OUTER JOIN is necessary: a balances-left-only query misses effect-only keys. SQL NUMERIC/`ROUND(...,3)` avoids float drift.
3. UI automation is correctly N/A: UI is unchanged; FastAPI and Django BFF component tests cover public behavior.
4. Maximum useful implementation concurrency is two threads only for the independent Django passthrough; SyncServer sensitive files/migration remain single-owner.

## Conditions before implementation changes

1. Executor completes TZ Stage 0 and records current nested repo branch/ownership/Alembic head.
2. Baseline diagnostics run read-only against a safe DB/clone; no secret/DSN values enter evidence.
3. Migration timing is measured on the clone and remains within an agreed window, otherwise architecture documents are revised first.
4. The existing item-movement xfail is made green before A-6 filter acceptance.
5. Non-empty effect capture is fail-closed before any new acceptance effect path is considered complete.

## Final gate

Architecture is ready for execution. This review does **not** verify runtime implementation and does not close any TZ implementation checkbox or historical risk. Final acceptance remains with QA verifier after the complete test/evidence ladder.
