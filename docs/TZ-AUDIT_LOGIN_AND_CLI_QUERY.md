# TZ: Centralized Login Audit + CLI Query Script

## Scope Decision (2026-06-18)

- **Accepted:** CLI script `scripts/query_audit.py` and its tests (Unit C).
- **Deferred:** SyncServer `POST /auth/audit-event` endpoint (Unit A) and Django login/logout push (Unit B) — deferred to dashboard/statistics phase.

## Execution Strategy

- [x] 🟢 Parallel execution recommended (initial scope)
- **Current scope:** только CLI-скрипт `query_audit.py` принят. Login/logout audit (`POST /auth/audit-event`, Django push) deferred до фазы dashboard/statistics.

> **Решение от 2026-06-18:** Units A и B (endpoint и Django push) отложены. В кодовой базе оставлен только Unit C (CLI) + его тесты и документация. Причина: endpoint вводит слабый trust-boundary без насущной необходимости, синхронный HTTP в Django login/logout сигнале нежелателен без архитектурного обсуждения. Dashboard-фаза позволит спроектировать API, права, фильтры и UI единообразно.

## Architecture Review

**Date:** 2026-06-18 | **Reviewer:** Architect/QA | **Verdict:** ✅ Approved for CLI-only scope

| Category | Result |
|----------|--------|
| Complexity | ✅ Минимально: один operator-only CLI-скрипт `scripts/query_audit.py` (~200 строк) плюс тесты/доки. |
| Coupling & Cohesion | ✅ SyncServer-only утилита: прямое чтение через SQLAlchemy/repo слой, без Django/Angular/runtime API изменений. |
| Data & State | ✅ Без миграций и без новых write-paths; читает существующие `AuditEvent`. |
| Failure Modes | ✅ Ошибка CLI не влияет на web/login/business flows. |
| Security | ✅ Нет нового HTTP endpoint/trust boundary; оператор запускает утилиту внутри контейнера. |
| Scalability | ✅ `--limit` по умолчанию ограничивает вывод; фильтры сужают выборку. |
| Observability | ✅ CLI выводит читаемый markdown/table/json для ручного анализа. |
| Operability | ✅ Откат = убрать CLI/доки; dashboard/API auth audit отложены отдельно. |

**🔴 Blockers:** 0  
**🟡 Warnings:**
1. CLI принимает пользовательский token как аргумент; оператор должен избегать публикации токенов в логах/чатах/shell history.
2. Endpoint `POST /auth/audit-event` и Django login/logout push намеренно не входят в текущую приёмку.

**🔵 Notes:**
1. `query_audit.py` подключается к БД через `SessionFactory` из `app.core.db` — тот же паттерн, что в `bootstrap_root.py`.
2. `query_audit_events()` — переиспользуемая функция для будущего API-эндпоинта дашборда.

---

## Execution Checklist

- [x] 0. Context verified
- [x] 1. Architecture boundaries confirmed
- [ ] 2. ~~Implementation: SyncServer `POST /auth/audit-event` endpoint~~ → **deferred** (dashboard/statistics phase)
- [ ] 3. ~~Implementation: Django push login/logout to SyncServer~~ → **deferred**
- [x] 4. Implementation: CLI script `scripts/query_audit.py` ✅ **принято**
- [x] 5. Unit tests complete (CLI only: 11/11 pass)
- [x] 6. Integration tests with real DB complete (CLI query_audit_events)
- [x] 7. Stand smoke tests complete (CLI docker exec ✅)
- [ ] 8. UI automation tests (N/A — CLI-only, console output)
- [x] 9. User scenario tests complete (CLI сценарии)
- [x] 10. Regression checks complete
- [x] 11. Documentation updated
- [ ] 12. Final acceptance review complete (ожидает подтверждения CLI-only scope)

---

## Уровень 0: Context Verified

### Что есть сейчас
- **SyncServer**: модель `AuditEvent`, репо `AuditEventsRepo.list_events()` с фильтрами, хелпер `record_audit_event()`, админский `GET /admin/audit`
- **SyncServer**: бизнес-операции уже пишут аудит: `operation.create`, `operation.submit`, `operation.acceptance_complete`, `operation.delete`, `operation.cancel`, `catalog.*`
- **Django**: модель `LoginAttempt`, сигнал `_record_login_attempt()` при входе/выходе, пишет локально
- **Django**: `SyncUserBinding.sync_user_token` — токен пользователя в SyncServer
- **Django**: `get_device_token()` — Django device token из env

### Что НЕ реализовано
- Нет эндпоинта в SyncServer для приёма auth-событий от Django → **deferred** (dashboard/statistics, Unit A)
- Django не отправляет login/logout в SyncServer → **deferred** (dashboard/statistics, Unit B)
- CLI-скрипт для запроса аудит-логов → **реализован** (Unit C, принят)

### Файлы, которые затрагиваются

| Проект | Файл | Действие |
|--------|------|----------|
| SyncServer | `app/api/routes_auth.py` | Добавить `POST /auth/audit-event` → **deferred** (Unit A) |
| SyncServer | `app/schemas/auth.py` | **Новый/дополнить**: `AuthAuditEventCreate` → **deferred** (Unit A) |
| SyncServer | `scripts/query_audit.py` | **Новый файл**: CLI-скрипт ✅ |
| Django | `apps/users/simple_sync_signals.py` | Дополнить `_record_login_attempt()` → **deferred** (Unit B) |
| Django | `apps/sync_client/audit_push.py` | **Новый файл**: функция отправки в SyncServer → **deferred** (Unit B) |

### Что НЕ затрагивается
- Angular-фронтенд
- Модели БД (без миграций — AuditEvent уже существует)
- Существующие бизнес-аудит записи (operation.*, catalog.*)

---

## Уровень 1: Architecture Boundaries Confirmed

### Принципы текущего scope
1. **SyncServer — источник истины для существующего бизнес-аудита**. CLI читает уже существующую таблицу `audit_events`.
2. **CLI-скрипт — в SyncServer**. Запрос к БД напрямую (через SQLAlchemy), без HTTP endpoint и без Django push.
3. **Auth login/logout centralization deferred**. Django продолжает писать локальный `LoginAttempt`; отправка login/logout в SyncServer будет спроектирована в dashboard/statistics phase.
4. **Утилита не влияет на runtime flows**. Ошибка CLI не ломает логин/логаут или бизнес-операции.

### Data Flow

```
Query:
  docker compose exec syncserver python scripts/query_audit.py --username <username>
    └─ SQLAlchemy → AuditEventsRepo.list_events(filters)
         └─ Markdown / JSON / Table → файл или stdout
```

### Deferred auth-audit API

`POST /auth/audit-event` и Django login/logout push не являются частью текущего accepted scope. Исторический дизайн сохранён ниже в [Deferred Design Notes](#deferred-design-notes).

---

## Уровень 2: Implementation

> **Note:** Units A and B (SyncServer `POST /auth/audit-event` endpoint and Django push) are deferred to dashboard/statistics phase. Design notes preserved in [Deferred Design Notes](#deferred-design-notes) below.

### Unit C: CLI Query Script
**Владелец:** executor-agent | **Проект:** SyncServer

#### C1. `scripts/query_audit.py` — структура

```python
#!/usr/bin/env python3
"""
Audit log query tool for SyncServer.

Usage:
  python scripts/query_audit.py --token <UUID> [options]

Examples:
  # Last 15 events for user token
  python scripts/query_audit.py --token a1b2c3d4-...

  # Filter by event type and date range, output to console
  python scripts/query_audit.py --token ... --event-type auth.login \
    --date-from 2026-06-01 --date-to 2026-06-18 --console

  # JSON output for piping
  python scripts/query_audit.py --token ... --format json --console | jq .
"""

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

# ---------------------------------------------------------------------------
# 1. Core query function (reusable for future API endpoint)
# ---------------------------------------------------------------------------

async def query_audit_events(
    *,
    user_token: UUID,
    event_type: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = 15,
) -> list[dict]:
    """
    Query audit events for a user by their token UUID.
    
    Returns list of dicts with keys:
      timestamp, event_type, actor_username, entity_type, entity_id, summary, changes
    """
    from app.core.db import SessionFactory
    from app.repos.audit_events_repo import AuditEventsRepo
    from app.repos.users_repo import UsersRepo

    async with SessionFactory() as session:
        users_repo = UsersRepo(session)
        user = await users_repo.get_by_user_token(user_token)
        if user is None:
            raise ValueError(f"User not found for token: {user_token}")

        audit_repo = AuditEventsRepo(session)
        events, _ = await audit_repo.list_events(
            event_type=event_type,
            actor_user_id=user.id,
            site_id=None,
            entity_type=entity_type,
            entity_id=entity_id,
            date_from=date_from,
            date_to=date_to,
            page=1,
            page_size=limit,
        )

        return [
            {
                "timestamp": e.created_at.isoformat(),
                "event_type": e.event_type,
                "actor_username": user.username,  # all events are for this user
                "entity_type": e.entity_type,
                "entity_id": e.entity_id,
                "summary": e.summary,
                "changes": e.changes,
            }
            for e in events
        ]


# ---------------------------------------------------------------------------
# 2. Formatters
# ---------------------------------------------------------------------------

def _ts(iso_str: str) -> str:
    """Format ISO timestamp to DD.MM.YYYY HH:MM."""
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%d.%m.%Y %H:%M")
    except (ValueError, TypeError):
        return iso_str[:19]


def format_as_markdown(events: list[dict], user_token: str, limit: int) -> str:
    """Format audit events as Markdown table."""
    lines = [
        f"# Аудит действий пользователя",
        f"",
        f"**Токен:** `{user_token}`",
        f"**Найдено записей:** {len(events)} (лимит: {limit})",
        f"",
        f"| Дата | Тип события | Сущность | Описание |",
        f"|------|------------|----------|----------|",
    ]
    for e in events:
        entity = f"{e['entity_type']}#{e['entity_id']}" if e['entity_id'] else "—"
        summary = (e['summary'] or "")[:120]
        lines.append(
            f"| {_ts(e['timestamp'])} | {e['event_type']} | {entity} | {summary} |"
        )
    return "\n".join(lines)


def format_as_jsonlines(events: list[dict]) -> str:
    """Format audit events as JSON lines."""
    import json
    return "\n".join(json.dumps(e, ensure_ascii=False) for e in events)


def format_as_table(events: list[dict]) -> str:
    """Format audit events as plain-text table (no markdown)."""
    if not events:
        return "Нет записей."
    header = f"{'Дата':<19} {'Тип':<28} {'Сущность':<24} {'Описание'}"
    sep = "-" * len(header)
    rows = [header, sep]
    for e in events:
        entity = f"{e['entity_type']}#{e['entity_id']}" if e['entity_id'] else "—"
        summary = (e['summary'] or "")[:80]
        rows.append(
            f"{_ts(e['timestamp']):<19} {e['event_type']:<28} {entity:<24} {summary}"
        )
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# 3. CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Query SyncServer audit events for a user token.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --token a1b2c3d4-...
  %(prog)s --token a1b2c3d4-... --event-type operation.submit --limit 50 --console
  %(prog)s --token a1b2c3d4-... --format json --console | jq .
        """,
    )
    parser.add_argument("--token", required=True, help="User token UUID")
    parser.add_argument("--event-type", help="Filter by event type (e.g. auth.login, operation.submit)")
    parser.add_argument("--entity-type", help="Filter by entity type (e.g. operation, inventory_subject)")
    parser.add_argument("--entity-id", help="Filter by entity ID")
    parser.add_argument("--date-from", help="Start date YYYY-MM-DD (default: 30 days ago)")
    parser.add_argument("--date-to", help="End date YYYY-MM-DD (default: today)")
    parser.add_argument("--limit", type=int, default=15, help="Max records (default: 15)")
    parser.add_argument("--format", choices=["markdown", "json", "table"], default="markdown",
                        help="Output format (default: markdown)")
    parser.add_argument("--output", help="Write to file (default: auto-generated report file)")
    parser.add_argument("--console", action="store_true", help="Print to stdout instead of file")

    args = parser.parse_args()

    # Parse dates
    date_from = None
    date_to = None
    if args.date_from:
        date_from = datetime.strptime(args.date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        date_from = datetime.now(timezone.utc) - timedelta(days=30)
    if args.date_to:
        date_to = datetime.strptime(args.date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
    else:
        date_to = datetime.now(timezone.utc)

    try:
        user_token = UUID(args.token)
    except ValueError:
        print(f"Ошибка: невалидный UUID токена: {args.token}", file=sys.stderr)
        sys.exit(1)

    # Query
    try:
        events = asyncio.run(query_audit_events(
            user_token=user_token,
            event_type=args.event_type,
            entity_type=args.entity_type,
            entity_id=args.entity_id,
            date_from=date_from,
            date_to=date_to,
            limit=args.limit,
        ))
    except ValueError as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Ошибка запроса: {e}", file=sys.stderr)
        sys.exit(1)

    # Format
    if args.format == "json":
        output = format_as_jsonlines(events)
        ext = ".jsonl"
    elif args.format == "table":
        output = format_as_table(events)
        ext = ".txt"
    else:  # markdown
        output = format_as_markdown(events, args.token, args.limit)
        ext = ".md"

    # Output
    if args.console:
        print(output)
    else:
        out_path = args.output or f"audit_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
        Path(out_path).write_text(output, encoding="utf-8")
        print(f"Отчёт сохранён: {out_path}")
        print(f"Записей: {len(events)} (лимит: {args.limit})")


if __name__ == "__main__":
    main()
```

---

## Уровень 3: Unit/Component Tests

### SyncServer Tests (`SyncServer/tests/`)

> **Note:** `POST /auth/audit-event` endpoint tests (Unit A) are deferred. See [Deferred Design Notes](#deferred-design-notes).

#### Test: CLI script
**Файл:** `tests/test_query_audit_cli.py`
- [ ] `test_query_by_token_returns_events` — запрос с валидным токеном возвращает список событий
- [ ] `test_query_nonexistent_token_raises` — несуществующий токен → ValueError
- [ ] `test_format_markdown` — проверка структуры markdown-вывода
- [ ] `test_format_jsonlines` — проверка JSON-вывода
- [ ] `test_date_range_filter` — фильтр по датам работает

```bash
python -m pytest tests/test_query_audit_cli.py -v
```

### Django Tests (`Warehouse_web/apps/users/tests/`)

> **Note:** Audit push tests (Unit B) are deferred. See [Deferred Design Notes](#deferred-design-notes).

---

## Уровень 4: Integration Tests (Real DB)

### SyncServer
- [ ] `test_cli_script_end_to_end` — `python scripts/query_audit.py --token ... --console` возвращает данные

### Django
> **Note:** Audit event persistence and login-to-audit integration tests (Units A/B) are deferred. See [Deferred Design Notes](#deferred-design-notes).

---

## Уровень 5: Stand Smoke Tests

### Стенд
Docker: SyncServer :8000, Django :8001, PostgreSQL :5432

### Smoke-тесты

> **Note:** Smoke tests for `POST /auth/audit-event` (Unit A) and E2E login-to-audit (Unit B) are deferred. See [Deferred Design Notes](#deferred-design-notes).

#### 1. Проверка CLI-скрипта
```bash
# Запросить аудит по username (последние 5 записей)
docker compose exec syncserver python scripts/query_audit.py \
  --username <username> \
  --limit 5 \
  --console

# Ожидается: markdown-таблица с записями аудита
```

---

## Уровень 6: UI Automation Tests

**N/A** — CLI-скрипт, без UI. Достаточно smoke-тестов через curl и проверки консольного вывода.

---

## Уровень 7: User Scenario Tests

### Сценарий 1: Администратор проверяет действия пользователя
1. Администратор выполняет в контейнере SyncServer:
   ```bash
   docker compose exec syncserver python scripts/query_audit.py \
     --username ivanov \
     --date-from 2026-06-18 \
     --console
   ```
2. В выводе видны все записи аудита для пользователя «ivanov»

### Сценарий 2: Экспорт аудита в файл для отчёта
1. Администратор выполняет:
   ```bash
   docker compose exec syncserver python scripts/query_audit.py \
     --username <username> \
     --date-from 2026-06-01 --date-to 2026-06-18 \
     --format markdown \
     --output /tmp/audit_june.md
   ```
2. Файл `/tmp/audit_june.md` в контейнере содержит markdown-таблицу
3. Файл можно скопировать из контейнера:
   ```bash
   docker cp warehouse_syncserver:/tmp/audit_june.md .
   ```

### Сценарий 3: JSON-экспорт для обработки
1. Администратор выполняет:
   ```bash
   docker compose exec syncserver python scripts/query_audit.py \
     --username <username> \
     --event-type operation.submit \
     --format json --console | jq '.'
   ```
2. Вывод — JSON lines, фильтруемый через jq

### Сценарий 4: Отказ SyncServer не ломает логин (deferred)

---

## Уровень 8: Regression Checks

- [ ] Существующие тесты SyncServer: `python -m pytest` — проходят
- [ ] `GET /api/v1/admin/audit` — работает как раньше
- [ ] Существующие audit-записи (operation.*, catalog.*) не затронуты
- [ ] Django login/logout не затрагивались текущим CLI-only scope

---

## Уровень 9: Documentation Updated

- [ ] Добавить `scripts/query_audit.py` в `SyncServer/README.md` или `docs/`
- [ ] Записать примеры использования в `docs/` (audit-query-examples.md)
- [ ] Закрыть Fix #6 в `docs/V3.0_POST_DEPLOY_FIXES.md` (или отметить как «частично выполнено — login audit»)

---

## Уровень 10: Final Acceptance Review

### Критерии приёмки
1. При входе пользователя в Django создаётся AuditEvent в SyncServer с `event_type="auth.login"` → **deferred** (Unit B)
2. При выходе — `event_type="auth.logout"` → **deferred** (Unit B)
3. При недоступности SyncServer логин не ломается → **deferred** (Units A/B)
4. CLI-скрипт `query_audit.py` работает из Docker-контейнера: ✅
   - `--username` (рекомендуется) или `--token` идентифицирует пользователя
   - `--event-type`, `--date-from`, `--date-to` фильтруют результаты
   - `--limit` ограничивает количество записей
   - `--format markdown` (по умолчанию) пишет .md файл
   - `--format json --console` выводит JSON в stdout
   - `--console` выводит в консоль вместо файла
5. Все существующие тесты проходят

### Evidence Table

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|
| SyncServer unit tests (Unit A) | `python -m pytest tests/test_audit_auth_endpoint.py` | deferred | dashboard phase |
| CLI unit tests (Unit C) | `python -m pytest tests/test_query_audit_cli.py` | pass | 11/11 pass |
| Django unit tests (Unit B) | `python manage.py test apps.users.tests.test_audit_push` | deferred | dashboard phase |
| Stand smoke: endpoint (Unit A) | curl `POST /auth/audit-event` | deferred | dashboard phase |
| Stand smoke: CLI (Unit C) | `docker compose exec ... query_audit.py --username ... --console` | pass | console output |
| Stand smoke: E2E login (Unit B) | логин → проверка audit-event | deferred | dashboard phase |
| Regression: SyncServer | `python -m pytest` | pass | all tests pass |
| Regression: Django | `python manage.py test` | N/A | not touched by CLI-only scope |

---

## Deferred Design Notes

> **Status (2026-06-18):** Units A and B deferred to dashboard/statistics phase. Content below preserved as historical reference for future implementation.

### Unit A: SyncServer `POST /auth/audit-event` endpoint
**Проект:** SyncServer

#### A1. Schema (`app/schemas/auth.py` — дополнить)
```python
from pydantic import BaseModel, Field

class AuthAuditEventCreate(BaseModel):
    event_type: str = Field(..., pattern=r"^auth\.(login|logout)$")
    ip_address: str | None = None
    user_agent: str | None = Field(None, max_length=256)
    request_id: str | None = Field(None, max_length=64)
```

#### A2. Endpoint (`app/api/routes_auth.py` — добавить)
```python
from app.schemas.auth import AuthAuditEventCreate
from app.services.audit_helper import record_audit_event

@router.post("/audit-event", status_code=201)
async def record_auth_audit_event(
    payload: AuthAuditEventCreate,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
):
    """Record auth event (login/logout) from trusted client (Django BFF)."""
    async with uow:
        await record_audit_event(
            uow,
            event_type=payload.event_type,
            actor_user_id=identity.user_id,
            actor_device_id=identity.device_id,
            entity_type="auth",
            entity_id=str(identity.user_id),
            summary=f"User {identity.username}: {'вход' if payload.event_type == 'auth.login' else 'выход'}",
            changes={
                "ip_address": payload.ip_address,
                "user_agent": payload.user_agent,
            },
            request_id=payload.request_id,
        )
    return {"status": "recorded", "event_type": payload.event_type}
```

### Unit B: Django push login/logout to SyncServer
**Проект:** Warehouse_web

#### B1. Push-функция (`apps/sync_client/audit_push.py` — новый файл)
```python
import structlog
from django.conf import settings
from apps.sync_client.transport import get_sync_client

logger = structlog.get_logger()

def push_auth_audit_event(
    *,
    user_token: str,
    device_token: str,
    event_type: str,  # "auth.login" or "auth.logout"
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> bool:
    """
    Push login/logout event to SyncServer audit.
    
    Returns True if successfully recorded, False on any failure.
    Audit failure must not break auth flow.
    """
    try:
        client = get_sync_client()
        response = client.post(
            f"{settings.SYNC_SERVER_URL}/auth/audit-event",
            json={
                "event_type": event_type,
                "ip_address": ip_address,
                "user_agent": (user_agent or "")[:256],
                "request_id": request_id or "",
            },
            headers={
                "X-User-Token": user_token,
                "X-Device-Token": device_token,
                "Content-Type": "application/json",
            },
            timeout=5.0,  # short timeout for audit
        )
        return response.status_code == 201
    except Exception:
        logger.exception("audit_push_failed", event_type=event_type)
        return False
```

#### B2. Интеграция в сигнал (`apps/users/simple_sync_signals.py`)
В `_record_login_attempt()` добавить после создания `LoginAttempt`:

```python
# Push to SyncServer audit (fire-and-forget, failure is non-blocking)
try:
    binding = getattr(user, "sync_binding", None)
    if binding and binding.sync_user_token:
        from apps.sync_client.audit_push import push_auth_audit_event
        from apps.sync_client.token_resolver import get_device_token
        
        push_auth_audit_event(
            user_token=binding.sync_user_token,
            device_token=get_device_token() or "",
            event_type=f"auth.{action}",
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
        )
except Exception:
    logger.exception("audit_push_to_syncserver_failed")
```

**Важно:** обернуть в try/except внутри уже существующего внешнего try/except в `_record_login_attempt()`. Отказ SyncServer не должен прерывать запись локального `LoginAttempt`.

### Unit A Tests: `POST /auth/audit-event`
**Файл:** `tests/test_audit_auth_endpoint.py`
- [ ] `test_record_login_event` — POST с event_type="auth.login", ip, user_agent → 201, AuditEvent в БД
- [ ] `test_record_logout_event` — POST с event_type="auth.logout" → 201, AuditEvent в БД
- [ ] `test_invalid_event_type` — POST с event_type="invalid" → 422 validation error
- [ ] `test_no_auth_header` — без X-User-Token → 403
- [ ] `test_invalid_token` — несуществующий токен → 401

```bash
python -m pytest tests/test_audit_auth_endpoint.py -v
```

### Unit B Tests: Django Audit Push
**Файл:** `tests/test_audit_push.py`
- [ ] `test_push_auth_audit_success` — мок ответа 201 от SyncServer → True
- [ ] `test_push_auth_audit_failure_no_block` — мок ошибки соединения → False, исключение не пробрасывается
- [ ] `test_push_auth_audit_timeout` — таймаут 5с не блокирует логин

```bash
python manage.py test apps.users.tests.test_audit_push
```

### Integration Tests (A/B)
- [ ] `test_audit_event_persisted` — созданный AuditEvent виден через `GET /admin/audit`
- [ ] `test_login_creates_syncserver_audit` — логин → AuditEvent в SyncServer (проверить через API)

### Smoke Tests (CLI only — оператор вводит параметры вручную, токены не печатать)

#### CLI через docker exec
```bash
# Запрос по username (рекомендуется)
docker compose exec syncserver python scripts/query_audit.py \
  --username <username> \
  --limit 10 --console

# Запрос по токену (когда username неизвестен)
docker compose exec syncserver python scripts/query_audit.py \
  --token <user_token> \
  --limit 10 --console
# Expected: markdown-таблица с записями аудита
```

### User Scenario: Отказ SyncServer не ломает логин
1. Остановить SyncServer: `docker compose stop warehouse_syncserver`
2. Залогиниться в Django
3. Логин успешен (локальный LoginAttempt записан)
4. Audit push в SyncServer молча fails (логгируется ошибка)
5. Запустить SyncServer: `docker compose start warehouse_syncserver`
