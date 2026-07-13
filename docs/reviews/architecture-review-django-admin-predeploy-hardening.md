# Architecture Review — Django Admin Pre-Deploy Hardening

**Date:** 2026-07-11  
**Reviewer:** Architect  
**Plan:** `docs/TZ-DJANGO_ADMIN_PREDEPLOY_HARDENING.md`

## Verdict

**Approved with conditions.** Архитектурных блокеров после ревизии плана нет. Реализация не может перейти к deployment, пока security, credential и consistency acceptance criteria не подтверждены evidence.

## Extracted Architecture

### Components

- Django Admin: authentication, technical user/password state, management UI.
- `Warehouse_web/apps/users/`: local bindings, sync orchestration, diagnostic cache.
- `Warehouse_web/apps/sync_client/`: единственный HTTP transport к SyncServer.
- SyncServer `/api/v1`: source of truth для users, roles, scopes, sites, devices и tokens.
- PostgreSQL: раздельные application schemas/databases через существующие services.
- Playwright: browser acceptance Django Admin.

### Data flow

```text
Superuser POST + CSRF
  -> Django local validation
  -> Django transaction: User/Binding/PENDING/stable ID
  -> commit
  -> Django sync service
  -> SyncServer root-only idempotent API
  -> validated + sanitized response
  -> Binding SYNCED or REPAIR_REQUIRED
```

### External dependencies

- SyncServer availability and root/device credentials from environment.
- PostgreSQL and Django migrations.
- Existing persistent HTTP transport/timeouts.
- No new queue, worker, broker or third-party service.

## Checklist Results

### Complexity

- [x] Simplest solution that works: synchronous saga reuses existing status/binding model.
- [x] Off-the-shelf mechanisms used: Django permissions, CSRF, `require_POST`, transactions, migrations.
- [x] Responsibilities are separated: Admin gate, service orchestration, SyncServer authority, contract validation.
- [x] Staged plan and explicit state transitions are understandable without new infrastructure.

### Coupling & Cohesion

- [x] Security guards, sanitizer, services and API contracts can be tested in isolation.
- [x] No circular dependency introduced.
- [x] Data ownership is explicit.
- [x] API addition is minimal: one idempotent device ensure endpoint.

### Data & State

- [x] Source of truth is defined for password, roles/scopes, tokens and sync status.
- [x] SyncServer outage leaves local `PENDING`/`REPAIR_REQUIRED` and retry path.
- [x] No new global mutable state.
- [x] Pre-scrub inventory, protected backup, irreversible scrub and post-scrub audit order are planned.

### Failure Modes

- [x] User multi-step partial failure is convergent through stable UUID and idempotent scope replacement.
- [x] Device lost-response is handled by ensure-by-code.
- [x] I/O uses existing timeouts; GET retry policy remains bounded.
- [x] Non-idempotent token rotation is never automatically retried.
- [x] Partial failure is visible to admin/profile user and audit command.

### Security

- [x] Admin mutations require active superuser, POST and CSRF.
- [x] Secrets remain in environment/primary credential storage only.
- [x] Django technical root and SyncServer domain roles are separated.
- [x] Diagnostic payload is recursively sanitized.
- [x] SyncServer mutations enforce least privilege.
- [x] Credential-bearing Playwright scenarios disable trace/video/screenshot and never read token values.

### Scalability

- [x] Admin traffic is low-volume; synchronous model is adequate.
- [x] Full site pagination is bounded and validated.
- [x] No N+1 requirement is introduced in request-critical business APIs.
- [x] Background jobs are intentionally deferred; state remains repairable.

### Observability

- [x] Structured, secret-free operation logs are required.
- [x] Existing health endpoints remain deployment probes.
- [x] Errors surface as binding status + admin/profile message + audit result.
- [x] Request ID is included in operation evidence.

### Operability

- [x] Deployment stages new images before pre-scrub audit/migrations and switches traffic only afterward.
- [x] Rollback cannot reactivate the vulnerable admin: `/admin/` is blocked unless rollback image includes Stage 1 guards.
- [x] Environment variable names and stand differences are documented.
- [x] Exact seed/cleanup and GO/NO-GO gate are defined.

## 🔴 Blockers

None after plan revision.

The original plan concept was revised to resolve these would-be blockers:

1. **Undefined repair state after remote-before-local mutation** — remote writes moved after durable local commit.
2. **Non-idempotent device create after lost response** — root-only ensure-by-code API added.
3. **Conflict between security and functional token-copy requirement** — explicit root-only credential display retained, diagnostic duplication removed.
4. **Audit information destroyed by credential scrub** — redacted pre-scrub inventory now runs before migration; protected backup has owner/retention/deletion policy.
5. **Credential leakage through Playwright artifacts** — dedicated spec disables trace/video/screenshot and never reads token input values.
6. **Unsafe migration/rollback order** — new images are staged before audit/migrate; insecure rollback requires external `/admin/` block or backported guards.
7. **Ambiguous swarm ownership** — each unit has exact writable manifest, dependency, worker report contract and parent-only checklist updates.

## 🟡 Warnings

### 1. Process crash can leave `PENDING`

- **Checklist item:** Failure Modes — partial request interruption.
- **Issue:** Без durable outbox процесс может завершиться после local commit и до remote sync.
- **Impact:** Изменение не синхронизируется автоматически.
- **Recommendation:** Audit command блокирует deploy для `PENDING` старше 300 секунд и active unresolved statuses; manual retry использует stable ID. Если частота станет операционно неприемлемой — отдельный ADR на outbox worker.

### 2. Device ensure returns a credential

- **Checklist item:** Security — minimal secret exposure.
- **Issue:** Idempotent ensure должен вернуть текущий token root-клиенту, иначе потерянный create response не восстанавливается.
- **Impact:** Новый sensitive response contract.
- **Recommendation:** Root-only authorization, no response-body logging/cache, TLS/network boundary, sanitizer before diagnostic storage, contract tests на отсутствие browser exposure.

### 3. Offset pagination snapshot can change during refresh

- **Checklist item:** Data & State — consistent snapshot.
- **Issue:** Stable ordering снижает, но не устраняет изменение dataset между страницами.
- **Impact:** Mirror может пропустить newly-created site в одном refresh.
- **Recommendation:** Запрет prune делает это безопасным; следующий explicit refresh добавит запись. Cursor/revision API не требуется для текущей нагрузки.

### 4. Default Django success message may coexist with sync warning

- **Checklist item:** Failure Modes — user-visible partial result.
- **Issue:** Admin local save завершается до remote sync.
- **Impact:** Пользователь может увидеть local success и sync warning одновременно.
- **Recommendation:** Формулировки должны явно разделять local save и remote sync; тест запрещает сценарий «только success при remote failure».

### 5. Historical token compromise cannot be inferred automatically

- **Checklist item:** Security — credential response.
- **Issue:** Наличие token в старом payload не доказывает, что его видел недоверенный пользователь.
- **Impact:** Либо избыточная rotation, либо сохранение потенциально раскрытого token.
- **Recommendation:** Pre-scrub audit выдаёт только binding IDs/key paths/counts до migration, post-scrub audit подтверждает очистку; решение о точечной rotation принимает оператор, token values не печатаются.

## 🔵 Notes

### 1. Circuit breaker intentionally omitted

Admin operations малочастотны, имеют timeout и explicit repair state. Circuit breaker добавит состояние и сложность без доказанной пользы. Пересмотреть при массовых admin jobs.

### 2. No SyncServer database migration for device ensure

Существующий unique `device_code` достаточен. Требуются service-level race handling и tests, но не Alembic migration.

### 3. UI automation does not require Angular runtime

Django Admin browser scenarios могут выполняться через Django stand. Полный `make test-e2e` остаётся regression gate для общего web stack.

## Gate

План может быть передан executor-агентам по стадиям. Deployment остаётся запрещён до закрытия checklist и повторного QA pre-deploy verdict `GO`.
