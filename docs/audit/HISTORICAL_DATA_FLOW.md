# Historical Data Flow — SyncServer

**Назначение:** визуальные карты write-path и audit chain для оценки
полноты воспроизводимости истории.

Все диаграммы ниже соответствуют реальному коду в `SyncServer/`.
Ссылки на конкретные файлы/строки приведены в `HISTORICAL_INTEGRITY_AUDIT.md`.

---

## 1. Полный жизненный цикл одной операции (draft → submit → effects → balances)

```mermaid
flowchart TD
    subgraph Client["Online / offline client"]
        A1[operator draft REQ]
    end

    subgraph Create["create_operation<br/>app/services/operations_service.py:915-1144"]
        B1[validate type and sites]
        B2[ensure item usable<br/>or temporary payload consistent]
        B3[create Operation draft<br/>creation_source=manual]
        B4[create OperationLine<br/>snapshot item/unit/cat]
        B5[draft DocumentService.generate_from_operation<br/>waybill auto, savepoint]
        B6[audit_event 'operation.create'<br/>record_audit_event]
        B1 --> B2 --> B3 --> B4 --> B5 --> B6
    end

    subgraph Update["update_operation (draft only)<br/>app/services/operations_service.py:1384-1660"]
        U1[workflow: require_draft_for_update]
        U2[delete_operation_lines ONLY for draft]
        U3[recreate lines with fresh snapshots]
        U4[audit_event 'operation.update'<br/>fields_changed]
    end

    subgraph SourceDoc["create_operation_from_source_document<br/>app/services/operations_service.py:1147+"]
        S1[idempotency check source_ref+hash]
        S2[validate item_id per line]
        S3[creation_source='source_document']
        S4[audit_event 'operation.create'<br/>source_ref in summary]
    end

    subgraph Submit["submit_operation<br/>app/services/operations_service.py:1881-2266"]
        C1[lock operation + state check + version check]
        C2[materialize deferred temporary lines<br/>create Catalog Item requires_review=True]
        C3[_freeze_catalog_snapshot for manual/source_doc]
        C4[two-phase aggregated balance sufficiency check]
        C5[apply per-line effects<br/>warehouse / pending / issued]
        C6[OperationRevision N+1 immutable<br/>revision_number=max+1]
        C7[rebuild OperationLines current projection<br/>via update/insert]
        C8[submit DocumentService<br/>auto_finalize and supersede]
        C9[audit_event 'operation.submit'<br/>lines_count, total_qty]
        C10[audit_event_resources catalog_resolved for change]
        C11[_write_captured_effects → audit_item_effects]
        C1 --> C2 --> C3 --> C4 --> C5 --> C6 --> C7 --> C8 --> C9 --> C10 --> C11
    end

    subgraph Effects["audit_item_effects journal<br/>0026 migration"]
        E1[effect_type in receipt/move_in/move_out/issue/issue_return/adjustment]
        E2[is_system_generated for merge/temp_resolution]
        E3[caused_by_event_id links to parent business event]
    end

    subgraph Balances["balances table<br/>app/repos/balances_repo.py:32-70"]
        D1[UPSERT by site_id + inventory_subject_id]
        D2[computed item_id via inventory_subjects]
        D3[no audit_event on direct row state]
    end

    A1 --> Create
    A1 --> SourceDoc
    Create --> Update
    Create --> Submit
    Update --> Submit
    SourceDoc --> Submit
    Submit --> Effects
    Submit --> Balances
```

---

## 2. Acceptance / partial resolve / lost → финализация принятых строк

```mermaid
flowchart TD
    subgraph Accept["accept_operation_lines<br/>app/services/operations_service.py:2269-2406"]
        F1[workflow: require_submitted + acceptance_required + not_resolved]
        F2{per line update}
        F2 -- accepted_qty>0 --> F3[pending_acceptance_balances -accepted_delta]
        F3 --> F4[balances.upsert +accepted_delta at destination]
        F4 --> F5[operation_lines.accepted_qty += delta]
        F5 --> F6[OperationAcceptanceAction row action=accept]
        F2 -- lost_qty>0 --> F7[pending_acceptance_balances -lost_delta]
        F7 --> F8[lost_asset_balances +lost_delta]
        F8 --> F9[operation_lines.lost_qty += delta]
        F9 --> F10[OperationAcceptanceAction action=mark_lost]
    end

    subgraph Resolve["resolve_lost_asset<br/>app/services/operations_service.py:2409-2476"]
        G1{lost row qty validate}
        G1 -- found_to_destination --> G2[balances + qty at destination_site]
        G1 -- return_to_source --> G3[balances + qty at source_site]
        G1 -- write_off --> G4[no balance change, only OperationAcceptanceAction]
        G2 --> G5[OperationAcceptanceAction row]
        G3 --> G5
        G4 --> G5
    end

    subgraph FinalAudit["audit_event 'operation.acceptance_complete'<br/>only on full resolve"]
        H1[recorded when next_state = 'resolved']
    end

    F2 --> F11{all lines resolved?}
    F11 -- yes --> H1
    F11 -- no --> F12[set acceptance_state='in_progress'<br/>no audit_event per-action]
    F11 -- block --> F12
```

---

## 3. Cancel / Restore — мутации балансов и операций

```mermaid
flowchart TD
    subgraph Cancel["cancel_operation<br/>app/services/operations_service.py:2511-2775"]
        K1[workflow: not cancelled]
        K2{operation.status?}
        K2 -- draft --> K3[soft transition, no balances change]
        K2 -- submitted --> K4[per-line inverse effects<br/>effect_type='cancel_reversal']
        K4 --> K5[RECEIVE: rollback pending+accepted+lost]
        K4 --> K6[WRITE_OFF issue_object: +issued_register]
        K4 --> K7[DECREMENT: +balance at source]
        K4 --> K8[ADJUSTMENT: -balance]
        K4 --> K9[MOVE: -source +destination<br/>validate sufficient destination]
        K4 --> K10[ISSUE: -issued +warehouse]
        K4 --> K11[ISSUE_RETURN: -warehouse +issued]
        K4 --> K12[operations.status='cancelled'<br/>cancelled_at, by_user, version+1]
        K4 --> K13[_delete_temporary_items_of_operation]
        K4 --> K14[audit_event 'operation.cancel' effect_type=cancel_reversal]
        K4 --> K15[_write_captured_effects audit_item_effects rows]
    end

    subgraph Restore["restore_operation<br/>app/services/operations_service.py:2778-2793"]
        R1[require_root_for_restore]
        R2[workflow: status=cancelled]
        R3[status='draft', cleared cancelled_*]
        R4[version+1, NO OperationRevision]
        R5[NO audit_event written<br/>GAP]
        R6[operation editable again]
    end

    Delete["delete_operation<br/>app/services/operations_service.py:2479-2508<br/>workflow: requires cancelled<br/>soft_delete, audit_event 'operation.delete'"]

    Cancel --> Restore
    Restore -.follow-up submit.-> SubmitAgain[submit_operation as if new]
    Cancel --> Delete
```

---

## 4. Merge каталога — мутация OperationLine

```mermaid
flowchart TD
    subgraph Merge["merge_items<br/>app/services/catalog_admin_service.py:511-746"]
        M1[validate source/target active and not frozen]
        M2[parent audit_event 'item.merge'<br/>summary, changes schema]
        M3[UoW context: audit_parent_event_id and caused_by_event_id]
        M4[for each site with non-zero source balance]
        M5[service ADJUSTMENT write-off<br/>system_origin, system_reason=item_merge, -qty]
        M6[service ADJUSTMENT receipt<br/>+qty to target_subject]
        M7[physical UPDATE<br/>operation_lines.item_id=target WHERE item_id=source<br/>line:678-684 audit_items WITHOUT per-line resource]
        M8[archive source inventory_subject]
        M9[deactivate source Item<br/>merged_into_id, merged_at, merged_by, merge_comment]
        M10[audit_event_resources merge_source/merge_target/generated*N]
        M11[restore UoW context]
    end

    subgraph AfterMerge["после merge_items"]
        N1[operation_lines.item_id указывают на target]
        N2[item_name_snapshot остаётся прежним]
        N3[unit/category snapshot сохраняются]
        N4[audit_item_effects с effect_type merge_write_off/receipt]
        N5[отчёты по item_id=source дают нулевые результаты]
        N6[line_map отсутствует — невозможно восстановить]
    end

    Merge --> AfterMerge
```

---

## 5. Correction flow (V1, RECEIVE without acceptance_required)

```mermaid
flowchart TD
    subgraph Begin["begin_correction<br/>app/services/corrections_service.py:90-159"]
        CB1[operation.status='submitted' check]
        CB2[partial unique index: one active draft per op]
        CB3[clone baseline OperationRevision lines]
        CB4[create OperationCorrection status='draft']
    end

    subgraph Edit["update_correction_put/add/remove_line"]
        CE1[version optimistic check]
        CE2[no correction_kind from client allowed]
        CE3[replace_all_lines or insert single]
        CE4[audit_event 'operation.create' on draft creation]
    end

    subgraph SubmitCorr["submit_correction<br/>app/services/corrections_service.py:415-700"]
        CS1[lock correction; idempotency_key by (op, key)]
        CS2[lock operation; verify base_revision is current]
        CS3[_compute_diff: unchanged/metadata/quantity/item_replaced/added/removed]
        CS4[_validate_deltas against current balances]
        CS5[lock inventory_subjects ASC then balances]
        CS6[OperationRevision N+1 immutable]
        CS7[rebuild_operation_lines<br/>UPDATE by line_uuid, INSERT for added, DELETE for removed]
        CS8[operation.current_revision_id = N+1, correction_count++, last_corrected_at]
        CS9[DocumentService.generate_from_operation operation_revision_id=N+1]
        CS10[supersede old docs]
        CS11[audit_event 'operation.correction.applied'<br/>and document.revision_created, document.superseded]
        CS12[_write_captured_effects audit_item_effects rows]
    end

    subgraph Abandon["abandon_correction"]
        CA1[audit_event 'operation.correction.abandoned']
    end

    Begin --> Edit --> SubmitCorr
    SubmitCorr -.no changes.-> Begin
    Edit -.cancel by client.-> Abandon
```

---

## 6. Cancel reversal: что и где остаётся

```mermaid
flowchart TD
    subgraph Before["submitted operation"]
        B[operation status=submitted, submitted_at, has audit_item_effects forward]
    end

    subgraph Cancel["cancel_operation"]
        C1[status=cancelled, cancelled_at, version+1]
        C2[audit_event 'operation.cancel'<br/>effect_type=cancel_reversal for each line]
        C3[audit_item_effects rows effect_type=cancel_reversal<br/>is_system_generated based on origin]
    end

    subgraph AfterState["persistent state after cancel"]
        S1[Operation.status='cancelled' — excluded from list_item_movement]
        S2[audit_event.cancel + parent_event_id=opts]
        S3[audit_item_effects.first submission forward direction stays]
        S4[audit_item_effects.cancel_reversal rows]
        S5[balances reflect net effect of forward and cancel_reversal]
    end

    Before --> Cancel --> AfterState
```

---

## 7. Report flow — что считает `reports_repo.list_item_movement`

```mermaid
flowchart TD
    R0[reports_repo.list_item_movement]
    R0 --> R1[RECEIVE rows UnionA<br/>where status=submitted, qty or accepted_qty<br/>operation_at = coalesce effective_at, created_at]
    R0 --> R2[EXPENSE/WRITE_OFF rows UnionA<br/>delta = -qty]
    R0 --> R3[ADJUSTMENT rows UnionA<br/>delta = qty<br/>INCLUDES merge_write_off/receipt, cancel_reversal]
    R0 --> R4[MOVE rows split:<br/>source_site -qty and destination_site +/- qty]

    R1 --> R5[aggregate by site_id, inventory_subject_id<br/>sum incoming, outgoing, net_qty, last_operation_at]
    R2 --> R5
    R3 --> R5
    R4 --> R5

    R5 --> R6[join items, categories, units, sites, temp_item]
    R6 --> R7[filter by user_site_ids; date_from/date_to on operation_at]
    R7 --> R8[response: per row incoming, outgoing, net_qty — current canonical names]
```

---

## 8. Audit chain: merge → system ADJUSTMENT → effects

```mermaid
flowchart LR
    subgraph MergeEvent["audit_events row #100 'item.merge'"]
        M1[parent_event_id = NULL]
        M2[correlation_id from uow.batch_correlation_id]
        M3[summary contains source→target]
        M4[changes: source_item_id, target_item_id,<br/>op_lines_reassigned_count, balances_transferred]
    end

    subgraph Res["audit_event_resources rows for #100"]
        R1[relation=merge_source snapshot_before/after]
        R2[relation=merge_target snapshot_before/after]
        R3[relation=generated × N]
    end

    subgraph SysAdj1["audit_events row #101 'operation.submit'<br/>ADJUSTMENT write-off"]
        S1[parent_event_id = #100.event_id]
        S2[actor_user_id = resolved_by_user_id]
        S3[changes.op_lines_reassigned_count inherits via UoW context]
    end

    subgraph SysAdj2["audit_events row #102 'operation.submit'<br/>ADJUSTMENT receipt"]
        T1[parent_event_id = #100.event_id]
        T2[actor_user_id = resolved_by_user_id]
    end

    subgraph Effects["audit_item_effects rows"]
        E1[effect_type=merge_write_off caused_by_event_id=#100]
        E2[effect_type=merge_receipt caused_by_event_id=#100]
        E3[is_system_generated=True]
    end

    MergeEvent --> Res
    MergeEvent --> SysAdj1
    MergeEvent --> SysAdj2
    SysAdj1 --> Effects
    SysAdj2 --> Effects
```

---

## 9. Окружение данных вне PostgreSQL — где что лежит

```mermaid
flowchart LR
    subgraph Docker["Docker compose<br/>docker-compose.yml:18+"]
        PG[(postgres_data volume<br/>var/lib/postgresql/data<br/>PITR NOT enabled)]
        SS[SyncServer app<br/>mount: ./SyncServer:/app<br/>hot reload only]
        DW[Warehouse_web<br/>mount: ./Warehouse_web:/app]
        ANG[Angular<br/>mount: ./Warehouse_frontend:/app]
        NO[mounted node_modules]
    end

    subgraph Backups["backups/ folder"]
        BK1[manual pg_dump file<br/>name=warehouse_YYYYmmdd_HHMMSS.sql]
        BK2[older devstand_backup_*.dump]
        BK3[older prod_backup_*.sql.gz]
    end

    PG -.pg_dump.-> Backups
    SS --> PG
    DW --> PG
    DW --> SS
    ANG --> DW
```

---

## 10. Кто видит данные — RBAC

```mermaid
flowchart LR
    subgraph RBAC["SyncServer roles"]
        ROOT[root<br/>full bypass]
        CHIEF[chief_storekeeper<br/>all sites, can_view_cancelled, audit API]
        STORE[storekeeper<br/>only assigned sites<br/>no audit API]
        OBS[observer<br/>read-only on assigned sites]
    end

    ROOT --> AuditAll[GET /api/v1/audit<br/>GET /api/v1/audit/{event_id}<br/>Merge API /catalog/items merge<br/>Restore POST /operations/id/restore]
    CHIEF --> AuditAll
    STORE --> NoAudit[no access to audit history<br/>no restore<br/>no unmerge]
    OBS --> NoAudit

    CHIEF --> CancelSubmit[POST /operations/id/cancel<br/>after policy require_operation_cancel_permission]
    STORE --> CancelSubmit
    OBS --> ReadOnly
    ROOT --> Any[ANY endpoint]
```

---

## 11. Time-line одной операции в каноническом виде (как сейчас)

```mermaid
gantt
    title Что остаётся в БД для одной RECEIVE операции id=42
    dateFormat X
    axisFormat %s
    section Lifecycle
    01_create         :done, 0, 1
    02_update_x2      :done, 1, 3
    03_submit         :done, 3, 4
    04_merge_lines_rewrite :crit, 8, 9
    05_cancel_pending :done, 10, 11
    06_restore        :crit, 11, 12
    07_resubmit       :done, 12, 13
    section Persistent artefacts
    audit_event_create        :done, 0, 13
    audit_event_update_x2     :done, 1, 3
    audit_event_submit        :done, 3, 13
    audit_event_merge_parent  :crit, 8, 9
    audit_event_cancel        :done, 10, 11
    audit_item_effects rows   :done, 3, 13
    OperationRevision lines N+1:done, 3, 13
    OperationLines current    :done, 0, 13
    balances affected         :done, 3, 13
```

Эта диаграмма демонстрирует главный риск: шаги `04_merge_lines_rewrite`
и `06_restore` не имеют соответствующих `audit_event` строк (или
имеют частичное покрытие), но меняют канонические projections.

---

## 12. Сводная легенда потоков

| Класс узла | Цвет | Что означает |
|------------|------|--------------|
| Rectangle | blue | API endpoint / service method |
| Subgraph | gray | Транзакционная единица |
| Диск | yellow | Persistent table |
| Audit * | green | Audit_event / resource / effect |
| Толстая стрелка | black | Запись в БД |
| Пунктир | gray | Read-only или no-effect |
| `crit` | red | Многая найденных gaps |

Эти диаграммы соответствуют коду в
`SyncServer/app/services/operations_service.py`,
`SyncServer/app/services/catalog_admin_service.py`,
`SyncServer/app/services/corrections_service.py`,
`SyncServer/app/repos/{reports_repo,balances_repo,audit_events_repo,operations_repo}.py`,
`SyncServer/app/models/{operation,balance,audit_event,audit_item_effect,document}.py`,
`SyncServer/alembic/versions/0026_audit_item_effects.py`.

Полные риски по каждой связи — в `HISTORICAL_RISK_REGISTER.md`.
