# Independent Review of Architecture & Security Audit

- **Audit under review:** `docs/AUDIT_ARCHITECTURE_SECURITY_2026-08-10.md` (Qwen, 2026-08-10)
- **Reviewer:** GLM, adversarial read-only verification
- **Date:** 2026-08-11
- **Method:** cross-check of every Critical/High finding + selected Medium + 5 Rejected findings against `SyncServer/`, `Warehouse_web/`, `Functional and WorkLogik.md`, ADRs, tests, CI. Code was not modified, secrets not read.

---

## Executive Verdict

The Qwen audit is **substantially correct and well-grounded**: file:line evidence was reproducible in every checked case, the threat-model framing is mostly aligned with `Functional and WorkLogik.md`, and the rejected findings (SQL injection, SSRF, unsafe deserialization, cross-site read-as-vuln, double-cancel-by-non-root) hold up under adversarial scrutiny. Confidence in the report is high.

However, the audit **overstates one architectural risk and slightly understates one security risk**:

- **ARC-04 ("server-side outbox missing — time bomb")** is mostly a misframing of an intentional pull-based design. The architecture (global `events` journal + per-device `sync_state.last_sequence_number` + client outbox) is a coherent offline-first contract; it does not need an extra "outbox" layer to be safe. Real concerns exist (event retention, multi-device coordination, late joiners), but the term "time bomb" and the implied push-delivery framing are wrong. **Downgrade.**
- **SEC-04 (plaintext UUID tokens, no expiry)** was rated High, but in combination with the actually-confirmed SEC-01 (.env in git history, default DB password, open Postgres port in dev compose) the compound effect is **Critical**: any DB or repo read becomes total impersonation with no expiry horizon. As an isolated finding, High is fine; as part of the realistic attack chain it pushes the priority ceiling. **Upgrade consideration flagged.**

All other Critical/High findings (SEC-01, INT-01, SEC-03, SEC-06, OPS-01, OPS-02, OPS-03, SEC-09) are reproduced exactly as written and the severities are calibrated correctly. No false positives among P0/P1. The audit's three top P0 actions (token rotation, INT-01 fix, prod-hardening of `DJANGO_ENV`+uvicorn workers+runbook) are the right starting line.

A few narrative refinements are warranted (see Detailed Verification), but they do not change the action list.

---

## Finding Verification Matrix

| ID | Original severity | Verdict | Revised severity | Confidence | Main reason |
|----|-------------------|---------|-------------------|------------|-------------|
| SEC-01 | Critical | **CONFIRMED** | Critical | High | `.env` tracked in git (commits `7bd1c21`, `08fab68`), contains `SYNC_ROOT_USER_TOKEN`, `SECRET_KEY`, `POSTGRES_PASSWORD`, `DB_PASSWORD`; `docker-compose.yml` defaults passwords to `warehouse_pass`; Postgres 5432 exposed in dev compose. |
| INT-01 | High | **CONFIRMED** | High | High | Service loads op without `FOR UPDATE` at `operations_service.py:2876`, applies positive inverse delta before re-checking status, repo `cancel_operation` silently no-ops if already cancelled. Test `test_cancel_concurrency.py:284-336` covers RECEIVE only (negative delta → `insufficient_stock` guard catches it); EXPENSE/WRITE_OFF positive deltas have no guard. |
| SEC-03 | High | **CONFIRMED** | High | High | `routes_sync.py:163-164` (`pull`) and `routes_sync.py:103-104` (`push` via `service.process_push(request=payload)`) use `payload.site_id` without comparing to `identity.device_site_id`. `Device.site_id` exists (`device.py:22-26`), `Identity.device_site_id` exists (`identity.py:80-82`), but never enforced. |
| SEC-04 | High | **CONFIRMED** (compound: Critical with SEC-01) | High (standalone) / Critical (compound) | High | `user_token`/`device_token` are `Mapped[UUID] default=uuid4` (User:23-28, Device:16-21); no `expires_at`, `revoked_at`, `token_version`, or hash columns; revoke is `is_active=False` only. Combined with SEC-01, DB read = total impersonation. |
| SEC-06 | High | **CONFIRMED** | High | High | `token_resolver.py:74-75` returns `SYNC_ROOT_USER_TOKEN` for any `is_superuser=True` Django user. Default `admin/admin123` superuser (AGENTS.md, `docker-compose.yml:128-137`); debug-mode auto-login in dev compose. |
| OPS-01 | High | **CONFIRMED** | High | High | `SyncServer/Dockerfile:12` `CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]`. `SyncServer/docker-compose.yml` has no `command:` override. Root `docker-compose.yml:43` repeats `--reload`. No prod compose override exists; `docker-compose.override.yml` only touches `warehouse_web`. |
| OPS-02 | High | **CONFIRMED** | High | High | `Warehouse_web/config/settings/__init__.py:3`: `_environment = os.getenv("DJANGO_ENV", "development").lower()`. `development.py:5-6` sets `DEBUG=True`, `ALLOWED_HOSTS=os.getenv("DJANGO_ALLOWED_HOSTS","*").split(",")`. `DEPLOYMENT.md` lists only `SECRET_KEY` as a Django env var, not `DJANGO_ENV`. `docker-compose.yml:54` defaults to `DJANGO_ENV: ${DJANGO_ENV:-development}`. |
| OPS-03 | High (quality gate) | **CONFIRMED** | Medium-High (process/quality, not security) | High | Only `e2e-tests.yml` and `frontend-unit-tests.yml` exist in `.github/workflows/`. No backend pytest / Django test workflow. Reasonable as a CI gap, but "High" is slightly over for a process issue rather than a code defect. |
| SEC-09 | High | **PARTIALLY_CONFIRMED** | High (compound with OPS-02) | Medium | `production.py:11-12,14-16,21`: `SESSION_COOKIE_SECURE=False`, `CSRF_COOKIE_SECURE=False`, `SECURE_HSTS_SECONDS=0`, `SECURE_SSL_REDIRECT=False`. `SECURE_PROXY_SSL_HEADER` set at line 8 without proxy allowlist. **Caveat:** these settings only matter if `DJANGO_ENV=production` is actually set in prod; given OPS-02, the prod may be running `development.py` instead, which is even worse (DEBUG=True, ALLOWED_HOSTS=*). |
| ARC-04 | Medium (time bomb) | **DOWNGRADE / PARTIALLY_CONFIRMED** | Medium (design discussion) | Medium | No server-side outbox table; sync uses global `events` journal + per-device `sync_state.last_sequence_number` + client outbox. This is a coherent pull-based design, not an incomplete push design. Real concerns: event retention policy, late-joiner resync, multi-device dedup, no DLQ semantics — but "time bomb" framing is wrong. |

---

## Detailed Verification

### SEC-01 — Secrets in git history

**Audit assertion:** `.env` tracked at root; commits `7bd1c21` and `08fab68`; contains `SYNC_ROOT_USER_TOKEN`, `SECRET_KEY`, `POSTGRES_PASSWORD`, `DB_PASSWORD`. Default creds in `docker-compose.yml:13,34,56-57,128-137`. Dev compose exposes Postgres `5432:5432`.

**Reproduction:**

- `git ls-files` confirms `.env` is tracked (not in any nested `.gitignore`).
- `git log -- .env` shows two commits: `7bd1c21` ("chore: setup dev environment — Makefile, docker-compose, .env, quickstart.sh") and `08fab68` ("post-deploy fixes, smoke screenshots, form snapshots").
- `git show --stat 7bd1c21 -- .env` → `.env | 34 ++++++++++++++++++++++++++++++++++` — confirms `.env` was added with real content.
- Root `.gitignore` does NOT contain `.env` (only nested repo dirs, IDE, caches).
- Key names in `.env` (names only, no values read): `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `DATABASE_URL`, `DJANGO_ENV`, `DJANGO_SETTINGS_MODULE`, `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `DB_ENGINE`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `SYNC_SERVER_URL`, `SYNC_ROOT_USER_TOKEN`, `SYNC_DEVICE_TOKEN` — matches the audit's enumeration.
- `docker-compose.yml:13` `POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-warehouse_pass}`; `:34` DATABASE_URL default with `warehouse_user:warehouse_pass`; `:67` `DB_PASSWORD: ${DB_PASSWORD:-warehouse_pass}`; `:129-137` E2E passwords default to `admin123`/`089786` — matches.
- `setup_ubuntu.sh:188,191` hardcodes `sync_user/sync_password` in Postgres init — matches.

**Counter-evidence search:** none. There is no secret manager integration, no environment-injection-only mechanism in any container entrypoint.

**Verdict:** **CONFIRMED**, Critical.

**Revised severity:** Critical (unchanged).

**Rationale:** Even if values in the tracked `.env` are dev defaults (not prod), the tracked file establishes the precedent, the file is in commit history permanently, and prod env-vars in `DEPLOYMENT.md` rely on the same key names (`SYNC_ROOT_USER_TOKEN`, `SECRET_KEY`, `DB_PASSWORD`) — meaning anyone with repo read access learns the schema and likely production values if they were ever pasted into a follow-up commit. Combined with `docker-compose.yml` defaults baked into the image (no env injection in compose), the failure mode is "secret in plain git history" + "fallback to dev default if env missing."

---

### INT-01 — Concurrent cancel: double-apply of positive inverse delta

**Audit assertion:** Two concurrent `cancel_operation` calls on a submitted EXPENSE/WRITE_OFF both apply the positive inverse delta, the second call's `repo.cancel_operation` silently no-ops the status transition, and the balance ends up inflated by `2×quantity`.

**Reproduction chain:**

1. `SyncServer/app/api/routes_operations.py:381-404` — route opens UoW, loads operation via `get_operation_by_id` (no lock) at `:382`, runs `require_exists`, `require_operate_site`, `require_not_cancelled_for_cancel`, `require_operation_cancel_permission` (root-only for submitted at `:178-182` of `operations_policy.py`), then calls `OperationsService.cancel_operation` at `:404`.
2. `SyncServer/app/services/operations_service.py:2870-2878` — service entry:
   ```python
   operation = await uow.operations.get_operation_by_id(operation_id)  # NO LOCK
   OperationsWorkflowPolicy.require_exists(operation)
   OperationsWorkflowPolicy.require_not_cancelled_for_cancel(operation)
   ```
3. `operations_service.py:2885-3100` — for EXPENSE: `elif operation.operation_type in DECREMENT_OPERATION_TYPES: await OperationsService._apply_balance_delta(...quantity_delta=quantity...)` — this is a **positive** delta (`quantity` is positive). For WRITE_OFF with `issue_object_id`: `_upsert_issued(...qty_delta=quantity...)` — also positive.
4. `_apply_balance_delta` (`operations_service.py:608-673`):
   - line 626: `if quantity_delta < 0: await _ensure_sufficient_balance(...)` — only checks sufficiency for **negative** deltas. Positive deltas pass through.
   - line 638: `balance_before_row = await uow.balances.get_for_update(...)` — locks the **balance row**, not the operation row.
   - line 654: `update_balance_quantity(quantity_delta=...)` — applies the delta unconditionally.
5. After all deltas applied, `operations_service.py:3102` calls `uow.operations.cancel_operation`.
6. `SyncServer/app/repos/operations_repo.py:269-276`:
   ```python
   operation = await self.get_operation_by_id_for_update(operation_id)  # LOCKS OP ROW
   if operation and operation.status in ["draft", "submitted"]:
       operation.status = "cancelled"
       ...
   return await self.get_operation_by_id(operation_id)  # returns regardless
   ```
   The `if` block is **skipped** when status is already `cancelled`. No exception is raised. The function returns the operation normally.
7. Test coverage: `SyncServer/tests/test_cancel_concurrency.py:284-336` is the only concurrent-cancel test. It targets RECEIVE — the only case where the negative inverse delta hits `_ensure_sufficient_balance` (`insufficient_stock` for the second cancel). EXPENSE/WRITE_OFF positive deltas have no equivalent guard.

**Race walkthrough (T1, T2 = two root cancels of submitted EXPENSE, qty=10):**

- T1 enters service, loads op (status=submitted) into identity map. Acquires balance row lock, reads `qty=100`. Applies `+10` → balance row = 110 in T1's tx.
- T2 enters service concurrently. Loads op (status=submitted, fresh) — passes guard.
- T2 calls `_apply_balance_delta` → `get_for_update` **blocks** on T1's balance row lock.
- T1 commits: balance = 110, op.status = cancelled, op.version++.
- T2 unblocks. `get_for_update` returns the **fresh** balance row (110). T2's `update_balance_quantity(+10)` → balance = 120 in T2's tx.
- T2 calls `repo.cancel_operation` → `get_operation_by_id_for_update` → reads op.status=cancelled. `if` block skipped. Returns operation. No exception.
- T2's audit event `operation.cancel` is written. T2's captured `audit_item_effects` entries (`+10`) are written. T2 commits.

**Net effect:** balance = 120 (was 100, +20), two `operation.cancel` audit events, one version bump. No error returned to either client. Both T1 and T2 receive HTTP 200.

**Counter-evidence search:**

- No `SELECT ... FOR UPDATE` on the operation row before applying deltas in the service path — confirmed.
- No conditional `UPDATE operations SET status='cancelled' WHERE id=? AND status='submitted'` returning affected row count — confirmed.
- No idempotency key on cancel (`client_request_id` is enforced only on create/submit).
- No `UNIQUE` constraint on `(operation_id, event_type='operation.cancel')` in `audit_event.py:104-112` (only `external_event_id` is unique).

**Verdict:** **CONFIRMED**, High.

**Revised severity:** High (unchanged).

**Rationale:** The audit's reasoning is exact. The bug class is "positive inverse delta has no sufficiency guard" — applies to EXPENSE/WRITE_OFF (rolled-back) and to the `_upsert_issued(+qty)` branch of WRITE_OFF-from-issue-object. Note: ISSUE rollback (line 3061-3077) and MOVE rollback to source (line 3014-3023 / 3035-3044) DO have positive deltas and DO need similar treatment — the audit notes it, and the test gap confirms it.

**Note on cancel being root-only:** This was checked via `operations_policy.py:178-182` (cancel submitted = root only). The audit correctly notes this **reduces likelihood but does not eliminate the bug** — root double-click, retry on timeout, or two admin sessions on the same op all reproduce it.

---

### SEC-03 — Device token cross-site pull/push

**Audit assertion:** `payload.site_id` is trusted for `/pull` and `/push`; `identity.device_site_id` exists but is never compared.

**Reproduction:**

1. `SyncServer/app/models/device.py:22-26` — `site_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("sites.id"), nullable=True)` — device has a site.
2. `SyncServer/app/core/identity.py:80-82` — `Identity.device_site_id` property returns `self.device.site_id`.
3. `SyncServer/app/api/routes_sync.py:152-166` — `/pull`:
   ```python
   async with uow:
       pulled_events = await uow.events.pull(
           site_id=payload.site_id, since_seq=payload.since_seq, limit=limit
       )
       server_seq_upto = await uow.events.get_max_server_seq(payload.site_id)
   ```
   Uses `payload.site_id` directly. No comparison to `identity.device_site_id`.
4. `SyncServer/app/api/routes_sync.py:84-127` — `/push`: calls `service.process_push(uow=uow, request=payload)` at `:103`; site comes from `payload.site_id` inside `service.process_push`. Logger at `:141` echoes `payload.site_id`. No identity check.
5. `SyncServer/app/services/sync_service.py:49-52` — `process_push` starts with site from request; no identity-vs-payload check found.

**Counter-evidence search:**

- Grep for `device_site_id` and `identity.device_site_id` returns no hits in `routes_sync.py` or `sync_service.py`.
- Grep for `payload.site_id == identity` returns no matches.
- `Identity.device_site_id` is read in `identity.py` itself and used elsewhere (`default_site_id` fallback at `:60-66`), but not in the sync trust boundary.

**Verdict:** **CONFIRMED**, High.

**Revised severity:** High (unchanged).

**Rationale:** Cross-site read of `events` is direct leak of operational data (operations, balances, movements). Cross-site push allows event-stream poisoning — for any offline client of site B that subsequently pulls, the foreign events appear as legitimate history. The audit's threat model is correct.

**Architectural note:** if multi-site devices are ever intended (e.g., a regional manager device that legitimately touches several sites), the fix is not to remove the `device.site_id` requirement but to allow multiple site assignments (a join table or list column) and require `payload.site_id ∈ allowed_sites`. The current code does neither.

---

### SEC-04 — Plaintext UUID tokens, no expiry

**Audit assertion:** `user_token` and `device_token` are plaintext UUID columns, no `expires_at`/`revoked_at`/`token_version`, revocation is only `is_active=false`.

**Reproduction:**

1. `SyncServer/app/models/user.py:23-28`:
   ```python
   user_token: Mapped[UUID] = mapped_column(
       PGUUID(as_uuid=True), nullable=False, unique=True, default=uuid4,
   )
   ```
2. `SyncServer/app/models/device.py:16-21`: same shape for `device_token`.
3. `rg -n "expires_at|revoked_at|token_version|hashed_token"` in `SyncServer/app/models/`, `SyncServer/app/services/` returns **only** `document_renderer.py:196-197` (unrelated — Jinja2 template expiry). No hits in user/device/auth models or services.
4. `routes_admin_users.py:148-162` — `rotate_user_token` exists but only flips the token UUID; no expiry metadata.
5. `routes_admin_devices.py:130-138` — same for device.
6. `routes_admin_users.py` searches for `revoke`, `disable` — only `is_active=False` toggles.

**Counter-evidence search:** No bcrypt/argon2/scrypt hash columns. No JWT. No opaque session table.

**Verdict:** **CONFIRMED** standalone (High), and **compound Critical** when combined with SEC-01.

**Revised severity:** High standalone; **Critical in compound** with SEC-01 (DB read or repo read → impersonation of every active user/device with no expiry horizon). The audit rates it High; the compound view should be acknowledged in any P0 plan.

**Rationale:** As an isolated finding (DB not leaked), High is right. But the audit already establishes that (a) `.env` is in git history (SEC-01), (b) Postgres port is open in dev compose, (c) backups include `prod_backup_*.sql.gz`, (d) tokens are in plaintext. The realistic attack chain is "get any of: repo read, dev DB access, backup, log dump" → "read users table → impersonate every active user/device forever." That is Critical-class, not High.

---

### SEC-06 — Django superuser = SyncServer root

**Audit assertion:** Django `is_superuser=True` → `SYNC_ROOT_USER_TOKEN`. Default superuser `admin/admin123`.

**Reproduction:**

1. `Warehouse_web/apps/sync_client/token_resolver.py:74-75`:
   ```python
   if getattr(request_user, "is_superuser", False):
       return _resolve_root_explicit(source="root_superuser")
   ```
2. `_resolve_root_explicit` (`:109-122`) returns `settings.SYNC_ROOT_USER_TOKEN` (from env). The same token used by internal `force_root` flows.
3. Default superuser: `AGENTS.md:141` documents `admin/admin123`; `docker-compose.yml:129` E2E_PASSWORD_ROOT default `admin123`. `make reset-django-admin` resets to `admin/admin123`.
4. The dev `e2e-tests.yml` workflow explicitly creates a Django superuser `admin` with password `admin123` and `is_superuser=True, is_staff=True, is_active=True`.
5. `apps/bff_api/helpers.py:199-200` — `_require_root(user)` uses `is_root(user)` helper, which on the Django side checks `is_superuser`. Same coupling.

**Counter-evidence search:**

- Searched for any role-separation code (e.g., "django_root_role", "separate_root_user", etc.) — none found.
- There is no concept of "Django-side root" vs "SyncServer-side root" in any user model.

**Verdict:** **CONFIRMED**, High.

**Revised severity:** High (unchanged).

**Rationale:** Any compromise of a Django superuser session = SyncServer root. In dev compose this is `admin/admin123` by default. Even with a strong password, the coupling means the Django admin panel itself is the root attack surface — a CSRF chain or session hijack yields total domain control.

---

### OPS-01 — SyncServer prod image runs `--reload`

**Audit assertion:** `SyncServer/Dockerfile` CMD has `--reload`. No prod override. DEPLOYMENT.md uses the same image.

**Reproduction:**

1. `SyncServer/Dockerfile:12`:
   ```
   CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
   ```
2. `SyncServer/docker-compose.yml` — no `command:` key for the `syncserver` service; inherits CMD. Confirmed.
3. Root `docker-compose.yml:43` — also sets `command: uvicorn main:app --host 0.0.0.0 --port 8000 --reload`.
4. `docker-compose.override.yml` — only touches `warehouse_web`, not `syncserver`.
5. `docs/DEPLOYMENT.md:148` — `cd ~/SyncServer && docker compose up -d --build` — uses SyncServer's own compose, which inherits CMD with `--reload`.
6. `docs/DEPLOYMENT.md:276` mentions gunicorn for `warehouse_web` (3 workers) but says nothing about how `syncserver` is actually started in prod (silently relies on CMD).

**Counter-evidence search:**

- No alternative production compose file (`docker-compose.prod.yml`, `compose.production.yml`) — none found.
- No entrypoint script overriding CMD.
- No startup wrapper that strips `--reload`.

**Verdict:** **CONFIRMED**, High.

**Revised severity:** High (unchanged).

**Rationale:** In a non-containerized alternative startup, `--reload` would not be used. But all documented deployment paths run the same image with the same CMD. `--reload` in prod means file-watcher overhead, single worker, no graceful reload, security advisory from uvicorn itself ("never use in production"), and process restart on any code-touch (e.g., a backup script writing near /app). The audit's claim is exact.

---

### OPS-02 — `DJANGO_ENV` defaults to development

**Audit assertion:** `_environment = os.getenv("DJANGO_ENV", "development").lower()`; `development.py` sets `DEBUG=True`, `ALLOWED_HOSTS="*"`. DEPLOYMENT.md doesn't list `DJANGO_ENV` in prod env-vars.

**Reproduction:**

1. `Warehouse_web/config/settings/__init__.py:3`:
   ```python
   _environment = os.getenv("DJANGO_ENV", "development").lower()
   ```
2. `Warehouse_web/config/settings/development.py:5-7`:
   ```python
   DEBUG = True
   ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "*").split(",")
   EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
   ```
3. `Warehouse_web/config/settings/production.py` exists and is more hardened (HSTS, secure cookies, etc.) but is only loaded if `_environment == "production"`.
4. `docker-compose.yml:54` — `DJANGO_ENV: ${DJANGO_ENV:-development}` even in docker.
5. `docs/DEPLOYMENT.md:265` — only `SECRET_KEY` is listed under "required env vars"; `DJANGO_ENV` is absent from any documented prod env list.

**Counter-evidence search:**

- `rg "DJANGO_ENV"` shows only dev defaults; no prod override documented.
- No fail-fast guard (`if not os.getenv("DJANGO_ENV"): raise ImproperlyConfigured`).

**Verdict:** **CONFIRMED**, High.

**Revised severity:** High (unchanged).

**Rationale:** `DEBUG=True` in prod leaks SQL, settings, tracebacks. `ALLOWED_HOSTS="*"` allows Host header injection (Django does not enforce `ALLOWED_HOSTS` when DEBUG=True, actually — Django allows any host in DEBUG, but the misconfiguration still weakens the production posture for non-DEBUG paths). Combined with OPS-01's `--reload` and the open Postgres port (dev compose), the dev stance leaks straight through to prod.

**Note:** `production.py` is more hardened than `development.py` for cookie/HSTS — but in the realistic prod scenario (no `DJANGO_ENV` set), `development.py` is loaded, which lacks any HTTPS hardening at all. SEC-09 is the **conditional** issue (only matters if DJANGO_ENV=production is ever set); OPS-02 is the **actual** issue for the currently-described prod.

---

### OPS-03 — CI doesn't run backend tests

**Audit assertion:** Only `e2e-tests.yml` and `frontend-unit-tests.yml` exist; no pytest/Django-test workflow.

**Reproduction:**

1. `ls .github/workflows/` → `e2e-tests.yml`, `frontend-unit-tests.yml`. No other workflows.
2. `e2e-tests.yml` — runs Playwright against the live stack; no `pytest SyncServer` or `manage.py test Warehouse_web` step.
3. `frontend-unit-tests.yml` — only frontend.
4. No `*-backend-tests.yml`, no `*-unit.yml` workflow.

**Counter-evidence search:** none. Confirmed gap.

**Verdict:** **CONFIRMED**, but severity reframing is warranted.

**Revised severity:** **Medium-High (process/quality)** — not a security/architecture finding, but a regression-risk finding. The audit rated it High (quality gate). The classification is fair, but in a prioritized P0 list this is **not** equivalent to a real vulnerability. The audit's P0 ordering (SEC-01, INT-01, OPS-01/02/08 first) already implicitly agrees.

**Rationale:** Without a backend test gate, INT-01 (and future race-condition bugs) can be reintroduced silently. But the bug exists today regardless of CI — fixing CI does not fix INT-01.

---

### SEC-09 — `production.py` without HTTPS hardening

**Audit assertion:** `production.py:11-12,14-16,21`: `SESSION_COOKIE_SECURE=False`, `CSRF_COOKIE_SECURE=False`, `SECURE_HSTS_SECONDS=0`, `SECURE_SSL_REDIRECT=False`. `SECURE_PROXY_SSL_HEADER` set without allowlist of trusted proxies.

**Reproduction:**

1. `Warehouse_web/config/settings/production.py:8-23` — confirmed verbatim:
   ```python
   SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
   # Пока нет HTTPS
   SESSION_COOKIE_SECURE = False
   CSRF_COOKIE_SECURE = False
   SECURE_HSTS_SECONDS = 0
   SECURE_HSTS_INCLUDE_SUBDOMAINS = False
   SECURE_HSTS_PRELOAD = False
   ...
   SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", False)
   USE_X_FORWARDED_HOST = True
   ```
2. `SECURE_PROXY_SSL_HEADER` with no `ProxyHeadersMiddleware`-style trusted-proxy allowlist is the documented Django footgun.
3. `USE_X_FORWARDED_HOST=True` (line 23) compounds: an attacker that can spoof `X-Forwarded-Host` (e.g., via a misconfigured proxy or by going direct to Django) can poison host-based routing.

**Counter-evidence search:**

- No `ALLOWED_PROXIES` or `SECURE_PROXY_SSL_HEADER` trust list anywhere.
- `production.py` has no `if DEBUG` block to disable these in development — they apply whenever `DJANGO_ENV=production`.

**Verdict:** **PARTIALLY_CONFIRMED**.

**Revised severity:** High **as a code defect**, but **practical impact depends on OPS-02**: if `DJANGO_ENV=production` is actually set on the VPS (and we don't know — DEPLOYMENT.md doesn't say), the issue is real and exploitable on the first HTTP path that bypasses nginx. If `DJANGO_ENV` is unset (the OPS-02 default), `development.py` is loaded, which is even worse (DEBUG=True, ALLOWED_HOSTS=*) — so SEC-09 is **subsumed** by OPS-02's larger problem.

**Rationale:** The audit correctly flags the production settings themselves. The realistic prod path (OPS-02 default) makes these settings moot — Django runs in dev mode. The compound OPS-02+SEC-09 is the real issue: hardening production.py alone doesn't fix prod until `DJANGO_ENV=production` is also forced.

---

### ARC-04 — Server-side outbox missing

**Audit assertion:** No server-side outbox; delivery is best-effort pull. "Time bomb" if multiple offline clients + AI agents appear.

**Reproduction:**

1. `SyncServer/app/models/event.py` — global event journal: `event_uuid` (PK), `site_id`, `device_id`, `event_type`, `payload`, `server_seq` (monotonic global). No per-device delivery state on the event itself.
2. `SyncServer/app/models/sync_state.py` — per-device: `device_id` (unique), `last_sequence_number` (BigInt), `last_sync_at`, `status`. No "events in flight", no DLQ, no retry counters.
3. `rg -n "outbox"` in `SyncServer/app/models`, `SyncServer/alembic/versions/` — no server-side outbox model or table.
4. The `sync_state.last_sequence_number` is updated only when the client successfully pulls (`routes_sync.py:189-194`) or successfully pushes (`routes_sync.py:114-122`). If the client crashes between receiving events and persisting them, it will re-pull the same events — but dedup is by `event_uuid` on push, and pull is by `since_seq` so re-pull is idempotent at the read level (not the client level).
5. Client outbox exists in `Warehouse_client_core` Rust (`outbox_service.rs:72-84`, `storage/repos.rs:642-696`), referenced in `docs/TZ-QUARTERMASTER_3_1.md:403`.

**Counter-evidence search:**

- No `outbox_events`, `pending_delivery`, or similar table.
- No retention policy documented for `events` table; if events are kept indefinitely, late-joining clients can resync; if pruned, late joiners lose data.

**Verdict:** **PARTIALLY_CONFIRMED**, severity **downgraded**.

**Revised severity:** **Medium (design discussion)** — NOT a "time bomb."

**Rationale:**

The framing of ARC-04 in the audit is **misleading in two ways**:

1. **"Outbox" is a push-delivery pattern, but the architecture is pull.** A "server-side outbox" with DLQ semantics only makes sense when the server is responsible for guaranteed push to consumers (SQS/Kafka with at-least-once). Here, the server's contract is "events are persisted in a global ordered log; clients track their own cursor (`last_sequence_number`) and pull on reconnect." This is a coherent, well-known pattern (similar to Kafka compacted topics + consumer offsets, or DynamoDB Streams + checkpoint tables). It is **not** a half-implemented push system.

2. **The real residual concerns** are:
   - **Event retention policy** (not stated in code or docs) — if `events` is pruned aggressively, late joiners lose data; if not pruned, table grows unbounded.
   - **Multi-device dedup at the consumer level** — multiple devices on the same site all pull independently; the server does not dedup reads.
   - **No ack of "device persisted event X"** — `sync_state.last_sequence_number` updates on read, not on client-side persistence.
   - **No DLQ for stuck devices** — a device stuck on a bad cursor just keeps pulling the same events (cheap) but never advances.

None of these are "time bombs" that justify P1 placement. They are legitimate design questions for when the system expands to multiple clients and AI agents. The audit's recommended action ("серверный outbox/курсоры доставки событий до расширения парка офлайн-клиентов") would actually **introduce** push-delivery semantics that the architecture doesn't currently have — the right move is to **formalize** the existing pull contract (retention, ack, cursor invariants) rather than replace it with a different pattern.

**Counter-finding:** the audit's recommendation in §13 #9 (build server-side outbox with delivery cursors before scaling) is **architecturally wrong** if implemented as "push outbox." If the goal is "guarantee delivery before scaling to AI agents," the right answer is **documented retention policy + per-device delivery ack table**, which is a much smaller change than an outbox subsystem.

---

## Review of Rejected Findings

Five rejected findings were selected for adversarial cross-check. All five **hold up** under scrutiny.

### 1. SQL injection — REJECTED (correct)

All `text()` usages in SyncServer are static (`SELECT 1`, `pg_advisory_lock`, `pg_advisory_unlock`, partial-index predicates in `operation.py`). Django ORM used everywhere else. No raw `f"... {var} ..."` SQL in either backend. **Confirmed no SQLi surface.**

### 2. SSRF — REJECTED (correct)

Outgoing HTTP from Django is via `apps/sync_client/transport.py` and `simple_client.py` against the fixed `settings.SYNC_SERVER_URL`. No URL composition from user input. SyncServer has no outbound HTTP at runtime. **Confirmed no SSRF surface.**

### 3. Unsafe deserialization (pickle/yaml/eval/exec) — REJECTED (correct)

`rg "^\s*eval\(|^\s*exec\(|pickle\.loads|yaml\.load\b|yaml\.unsafe"` in all source dirs returns nothing. Earlier false positives (`_exec` method names in `Warehouse_web/apps/catalog/services.py`) are function names, not the built-in. **Confirmed no deserialization risk.**

### 4. SEC-02 — Cross-site read as vulnerability — REJECTED (correct)

`Functional and WorkLogik.md` §2.1.1-2.1.3 explicitly says:

- 2.1.1 Observer: "может смотреть всё"
- 2.1.2 Storekeeper: "может просматривать всё а так же делать операции на приписанных к его токену складам"
- 2.1.3 Chief: "может смотреть всё и работать со всеми складами"

`SyncServer/app/services/operations_policy.py:21-26` (`require_read_site` ignores site_id) and `core/identity.py` access patterns align with this design. **Confirmed: by-design behavior, not a vulnerability.** The audit correctly notes this is ADR-0005 vs Functional-doc drift (code follows Functional, not ADR), but the security posture matches Functional. The remaining issue is dead `site_id` parameters in `require_read_site` / `require_temporary_item_moderation` — a code-cleanliness issue, not an exploit.

### 5. Double-cancel available to non-root — REJECTED (correct)

`SyncServer/app/services/operations_policy.py:171-188` — `require_operation_cancel_permission`:

```python
if operation.status == "submitted":
    if identity.is_root:
        return
    raise RoleNotPermittedError()
```

Cancel of submitted operation is **strictly root-only**. This means the INT-01 attack requires root credentials, which reduces likelihood but does not eliminate the bug (root double-click, retry, multiple admins). The audit correctly frames this as "reduces likelihood, doesn't eliminate."

### Bonus check — SyncServer tokens in browser

`Warehouse_web/apps/bff_api/tests.py:1457-1458` has explicit assertions:

```python
self.assertNotIn("sync_user_token", response_text)
self.assertNotIn("sync_device_token", response_text)
```

This is a **guard test** ensuring BFF responses do not leak tokens to the browser. The Angular models (`admin.models.ts:17,24,43,47`) reference `user_token?`/`device_token` — but those are server-side type definitions (used in `httpClient.get<AdminUser & { user_token: string }>` typing for Django admin pages, not for BFF endpoints). The rejection is correct.

---

## P0/P1 Final Set

After independent verification, the following are the issues that should enter the next TZ/iteration:

### P0 (must-fix before next prod action)

1. **SEC-01** — Rotate `SYNC_ROOT_USER_TOKEN`, `SECRET_KEY`, DB passwords; remove `.env` from tracking (it's already in history — rotation is the only effective control); document secret injection path.
2. **INT-01** — Fix cancel race: `get_operation_by_id_for_update` + status-transition guard BEFORE inverse deltas in `operations_service.cancel_operation`. Add concurrent-cancel tests for EXPENSE, WRITE_OFF (with and without `issue_object_id`), ISSUE, MOVE-acceptance. The bug is a **class**, not a one-off.
3. **OPS-01 / OPS-02 / OPS-08 (compound)** — Prod-hardening bundle:
   - Force `DJANGO_ENV=production` in DEPLOYMENT.md (fail-fast if absent).
   - Override SyncServer CMD to drop `--reload` and add `--workers N --timeout T`.
   - Fix the `docker compose exec web ... migrate` typo (line 159) → `exec warehouse_web`.
   - Run the DEPLOYMENT.md runbook dry end-to-end.

### P1 (next iteration)

4. **SEC-03** — Sync: enforce `payload.site_id == identity.device_site_id` (or multi-site device assignment if ever intended).
5. **SEC-06** — Decouple Django superuser from SyncServer root. Add explicit SyncServer-side admin role assignment. Default admin password reset must not yield root.
6. **OPS-03** — CI workflow for `pytest SyncServer` + `manage.py test Warehouse_web`. Treat test failure as merge gate.
7. **INT-02** — Unify document generation contract across submit and corrections. The current "log and continue" in submit is the wrong default; pick one (atomic rollback OR deferred regeneration queue with visible "document missing" status).
8. **SEC-04** — Token hardening (hash in DB, expiry, `token_version`). Note this compounds with SEC-01 — combined effect is Critical.

### P2 (architectural backlog)

9. **ARC-04** — **DO NOT** add a server-side outbox as the audit suggests. Instead, document the pull contract: event retention policy, per-device delivery ack (separate from cursor), late-joiner resync semantics. The architecture is sound; the contract just needs to be made explicit.
10. **ADR-0005 / ADR-0028 / ADR-0029 / ADR-0025** — Update statuses to match reality (read-scope alignment with Functional doc; ADR-0028 Stage A is largely implemented; ADR-0029 has two renderers in production and a third untracked).
11. **ARC-01** — Separate databases in dev compose to mirror prod (and avoid the "works in dev, breaks in prod" class).
12. **ARC-09** — Public read-only sites endpoint for non-root roles; reduce `force_root=True` surface.

---

## Findings Requiring Runtime Verification

These cannot be conclusively proven by static analysis alone:

| Item | Why | Recommended check |
|---|---|---|
| Does prod VPS actually have `DJANGO_ENV` unset (loading development.py)? | `DEPLOYMENT.md` does not document this env var, but the audit cannot reach the VPS. | Direct query on VPS env, or `curl -sk https://host/healthz/` and inspect `ALLOWED_HOSTS` behaviour. |
| Does prod SyncServer run `--reload`? | Image CMD says so; no override found; but actual prod compose may differ from repo. | `docker exec warehouse_syncserver ps aux \| grep uvicorn` on VPS. |
| Are events in `events` table ever pruned? | No retention policy in code/docs. | `SELECT MIN(event_datetime), MAX(event_datetime) FROM events;` + check cleanup jobs/cron. |
| Does the prod Django process run with `ALLOWED_HOSTS=*`? | If `DJANGO_ENV` unset, yes. | Inspect Django logs for "invalid HTTP_HOST" rejections vs accepts. |
| Are backups in `backups/` actually containing prod data? | Audit observed `prod_backup_20260708_115420.sql.gz` in repo, but didn't read contents. | `gzip -dc backups/prod_backup_*.sql.gz \| head -c 500 \| grep -c "CREATE TABLE"` (without printing secret content). |

---

## Audit Quality Assessment

### Strengths

- **Evidence quality:** file:line references are precise and reproducible. Every Critical/High claim I checked landed on the cited code path. The cross-references between commit hashes, code lines, and ADR docs are tight.
- **Threat model:** the actor list is complete (root, chief, storekeeper, observer, agent, device token, AI agent, compromised client, malicious internal service, replay, stale client, network failure between Django↔SyncServer). The critical invariants (balance = sum of effects, idempotent submit by client_request_id, single-apply inverse delta, site-isolated sync, token-as-identity) are well-stated.
- **Cross-check against `Functional and WorkLogik.md`:** correctly identifies the read-scope design vs ADR-0005 drift and resolves it in favour of Functional doc.
- **Test gap identification:** `test_cancel_concurrency.py` covering only RECEIVE is correctly flagged as the smoking gun for INT-01.
- **Compound finding (SEC-01 + open Postgres port + plaintext tokens + dev defaults in compose):** the chain is correctly recognized as the worst realistic attack path.

### Weaknesses

- **Confirmation bias toward severity:** every finding is rated High or above. ARC-04 ("time bomb") and OPS-03 ("High quality gate") push the urgency up where Medium would be more honest.
- **Mixing concerns:** the report mixes security, architecture, operations, and quality/process in a single severity ladder. SEC-01 is Critical; OPS-03 (no backend CI) is process, not security — yet both are "High" in the same matrix. A triage reader will underestimate the real issues.
- **ARC-04 misframing:** the audit treats "no server-side outbox" as a missing subsystem. For a pull-based architecture, the right framing is "contract needs documentation + ack tracking." The remediation ("серверный outbox/курсоры доставки") would, if implemented as written, **change the architecture** rather than harden it.
- **SEC-09 framing:** the audit treats `production.py` HTTPS settings as the relevant fact. With OPS-02 unfixed, `production.py` is never loaded in prod, so SEC-09 is **subsumed** by OPS-02's bigger problem. The audit should explicitly call out the compound (SEC-09 only matters once OPS-02 is fixed).
- **Severity calibration:** 9 of 10 Critical/High findings cluster around "secret hygiene + deployment hygiene." The actual most dangerous runtime bug (INT-01) is buried in the report's middle. P0 ordering is correct, but the table presentation over-emphasizes secrets and under-emphasizes concurrency.
- **No false positives among P0/P1:** every checked Critical/High is a real defect with reproducible code. The audit's "Rejected Findings" section is the most underappreciated part — it correctly filters out 13 candidate issues (SQL injection, SSRF, eval/pickle, cross-site read, double-cancel-by-non-root, etc.). A reader who skips that section will overestimate fragility.
- **Reproducible evidence:** every checked file:line hit. No fabricated citations.

### Overall grade

**B+ as an audit, A− as a security review of the code, C as a prioritization artifact.** The code-level findings are accurate and well-evidenced. The P0/P1 prioritization is reasonable but slightly distorted by treating process/quality as security at the same severity. The architectural analysis (ARC-04) is the weakest section.

### Recommended corrections to the audit itself (not to the code)

- ARC-04: reframe as "pull-based sync contract needs explicit retention + ack policy" rather than "missing outbox subsystem."
- SEC-09: add explicit caveat that the issue is contingent on OPS-02 being fixed first.
- SEC-04: keep High standalone but call out the compound Critical-with-SEC-01 effect in the risk summary.
- OPS-03: relabel as "Medium-High (process/quality)" rather than "High (quality gate)" so it doesn't compete with real vulnerabilities for the same fix window.

---

## Summary

The Qwen audit is **trustworthy**: 9 of 10 Critical/High findings reproduce exactly as written with no false positives. The one finding that needs reframing is **ARC-04** (the audit misrepresents a pull-based architecture as a missing push outbox and calls it a "time bomb" when it is a Medium design discussion). The most important compound risk (SEC-01 + SEC-04 + open Postgres port + dev-default credentials) deserves an explicit Critical annotation in the P0 list rather than being split across two High rows. The audit's rejected-findings section is unusually disciplined and deserves more reader attention than it typically gets.

Recommended next action: take the P0 list verbatim, fix **INT-01** first (it's the only P0 that's a code-correctness bug rather than a hygiene issue), then run the OPS-01/02/08 hardening bundle as a single deploy, then rotate secrets as a separate, auditable change.