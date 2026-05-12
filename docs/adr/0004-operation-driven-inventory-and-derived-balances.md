# ADR-0004: Operation-Driven Inventory And Derived Balances

## Status
Accepted

## Context
Warehouse state must be auditable, support transfer acceptance workflows, and track pending, lost, and issued assets. The repository includes `Operation`, `OperationLine`, `Balance`, `InventorySubject`, and dedicated asset-register tables, which together show that stock is managed through warehouse operations rather than manual balance editing.

## Evidence
- `SyncServer/app/models/operation.py` — Operation entity with status lifecycle (DRAFT → SUBMITTED → COMPLETED/CANCELED)
- `SyncServer/app/models/operation_line.py` — Individual line items within operations
- `SyncServer/app/models/balance.py` — Derived balance read model
- `SyncServer/app/models/pending_acceptance_balance.py`, `lost_asset_balance.py`, `issued_asset_balance.py` — Dedicated register tables for acceptance/lost/issued states
- `SyncServer/app/models/operation_acceptance_action.py` — Acceptance action records
- `SyncServer/app/models/inventory_subject.py` — Stable stock identity bridging catalog items and temporary items
- `SyncServer/app/services/operations_service.py` — Core workflow: creates operations, derives balances and registers from operations
- `SyncServer/app/repos/operations_repo.py`, `balances_repo.py` — Queries for operations and derived balances
- `SyncServer/app/api/routes_operations.py` — POST/PATCH/SUBMIT/CANCEL endpoints, no direct balance mutation endpoints
- `SyncServer/app/api/routes_balances.py` — GET-only endpoints (read-only balances API)
- `SyncServer/tests/test_operations_workflow_policy.py`, `test_operations_service_cancel.py` — Tests verify operation lifecycle rules

## Decision
Inventory changes are driven by operations processed by `OperationsService`. `Balance` and related asset-register tables (`PendingAcceptanceBalance`, `LostAssetBalance`, `IssuedAssetBalance`) are derived state maintained by the backend workflow, not primary business inputs edited independently.

## Consequences

### Pros
- Auditable stock movement history (every change traceable to an operation)
- Explicit support for acceptance, lost-asset, and issued-asset workflows
- Less risk of silent balance drift from arbitrary stock edits
- GET-only balance API enforces the write-through-operation constraint at API level

### Cons
- Operation workflows are more complex than direct balance updates
- Derived tables must stay consistent with the operation lifecycle
- Additional test surface for operation → balance → register derivation correctness

## Alternatives Considered

### Option 1
Use balances as the primary editable stock record.
Why not chosen: Would weaken auditability and bypass workflow rules already implemented in `OperationsService`.

### Option 2
Recompute balances on every read directly from operations.
Why not chosen: The current design explicitly stores derived read models and workflow registers for performance and workflow state tracking.

## Confidence
- **Confirmed by code** — Operation models, service, and GET-only balance routes demonstrate this decision
