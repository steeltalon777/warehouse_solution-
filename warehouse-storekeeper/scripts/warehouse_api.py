#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""warehouse_api.py — CLI-клиент Warehouse SyncServer для Hermes-скилла warehouse-storekeeper.

Единый машинно-читаемый формат ответа (JSON в stdout):
{
  "ok": true|false,
  "command": "catalog.search",
  "request_id": "...",
  "status_code": 200,
  "data": {...} | null,
  "warnings": [...],
  "errors": [{"code": "...", "message": "...", "field": "...", "details": {...}}]
}

Коды выхода: 0 — ok; 1 — серверная/бизнес-ошибка; 2 — локальная ошибка
использования/конфигурации; 3 — сетевая ошибка.

Жёсткая граница полномочий реализована здесь allowlist'ом эндпоинтов:
клиент умеет только читать справочники/остатки и создавать/редактировать
СВОИ черновики операций. Submit/accept/cancel/restore/delete/merge/admin/
arbitrary-URL отсутствуют как команды и блокируются на уровне транспорта.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import httpx
except ImportError:  # pragma: no cover
    sys.stderr.write(
        "Требуется пакет httpx. Установите зависимости: "
        "python -m pip install -r requirements.txt\n"
    )
    sys.exit(2)

CLIENT_VERSION = "1.0.0"
API_PREFIX = "/api/v1"

CONNECT_TIMEOUT = 5.0
READ_TIMEOUT = 30.0
WRITE_TIMEOUT = 30.0
POOL_TIMEOUT = 5.0

EXIT_OK = 0
EXIT_SERVER_ERROR = 1
EXIT_USAGE_ERROR = 2
EXIT_NETWORK_ERROR = 3

# ---------------------------------------------------------------------------
# Граница полномочий: allowlist эндпоинтов (defense-in-depth).
# Универсальной команды вида `request METHOD URL` в CLI НЕТ и не будет.
# ---------------------------------------------------------------------------

_UUID_RE = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"

ALLOWED_ENDPOINTS: list[tuple[str, "re.Pattern[str]"]] = [
    ("GET", re.compile(rf"^{API_PREFIX}/health$")),
    ("GET", re.compile(rf"^{API_PREFIX}/auth/(me|context|sites)$")),
    ("GET", re.compile(rf"^{API_PREFIX}/catalog/(units|sites)$")),
    ("GET", re.compile(rf"^{API_PREFIX}/catalog/read/items$")),
    ("GET", re.compile(rf"^{API_PREFIX}/catalog/read/items/\d+$")),
    ("GET", re.compile(rf"^{API_PREFIX}/catalog/read/categories$")),
    ("GET", re.compile(rf"^{API_PREFIX}/catalog/read/categories/\d+/(items|children|parent-chain)$")),
    ("GET", re.compile(rf"^{API_PREFIX}/catalog/admin/items$")),
    ("GET", re.compile(rf"^{API_PREFIX}/catalog/admin/items/\d+$")),
    ("POST", re.compile(rf"^{API_PREFIX}/catalog/admin/items$")),
    ("PATCH", re.compile(rf"^{API_PREFIX}/catalog/admin/items/\d+$")),
    ("GET", re.compile(rf"^{API_PREFIX}/catalog/admin/units$")),
    ("GET", re.compile(rf"^{API_PREFIX}/catalog/admin/categories$")),
    ("GET", re.compile(rf"^{API_PREFIX}/balances(/by-site|/summary)?$")),
    ("GET", re.compile(rf"^{API_PREFIX}/operations$")),
    ("GET", re.compile(rf"^{API_PREFIX}/operations/{_UUID_RE}$")),
    ("POST", re.compile(rf"^{API_PREFIX}/operations$")),
    ("POST", re.compile(rf"^{API_PREFIX}/operations/from-source-document$")),
    ("PATCH", re.compile(rf"^{API_PREFIX}/operations/{_UUID_RE}$")),
]

# Явно запрещённые области — проверяются ДО allowlist.
DENIED_PATH_RE = re.compile(
    r"(submit|accept-lines|/cancel|/restore|/merge|/sync|/push|/pull"
    r"|/bootstrap|/corrections|/temporary-items|/documents|/diagnostics"
    r"|/review-items|/assets|/reports|/issue-objects"
    r"|/admin/(users|sites|roles|devices|sync|settings|batch|bulk)|/items/(bulk|archive|delete))",
    re.IGNORECASE,
)

# Типы операций, которые помощник кладовщика может готовить (только draft).
# ADJUSTMENT запрещён: это прямое изменение остатков.
ALLOWED_OPERATION_TYPES = {"RECEIVE", "MOVE", "ISSUE", "ISSUE_RETURN", "EXPENSE", "WRITE_OFF"}

# Типы, уменьшающие остатки (для локальной проверки достаточности).
DECREMENT_OPERATION_TYPES = {"EXPENSE", "WRITE_OFF", "ISSUE", "MOVE"}

CASE_STATES = [
    "RECEIVED",
    "COLLECTING_PAGES",
    "RECOGNIZING",
    "WAITING_FOR_INTENT",
    "MATCHING_CATALOG",
    "NEEDS_CLARIFICATION",
    "CREATING_DRAFT",
    "DRAFT_READY",
    "FAILED",
    "CANCELLED",
]

STATUS_ERROR_CODES = {
    400: "VALIDATION_ERROR",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMIT_EXCEEDED",
    500: "INTERNAL_SERVER_ERROR",
}

MASK = "***"


class EndpointNotAllowed(Exception):
    """Попытка обратиться к эндпоинту вне allowlist."""


class ConfigError(Exception):
    """Ошибка конфигурации/секретов (локальная, до сети)."""

    def __init__(self, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


# ---------------------------------------------------------------------------
# Конверт ответа
# ---------------------------------------------------------------------------

def make_envelope(
    command: str,
    *,
    ok: bool,
    request_id: str | None = None,
    status_code: int | None = None,
    data: Any = None,
    warnings: list | None = None,
    errors: list | None = None,
) -> dict:
    return {
        "ok": ok,
        "command": command,
        "request_id": request_id,
        "status_code": status_code,
        "data": data,
        "warnings": warnings or [],
        "errors": errors or [],
    }


def error_entry(code: str, message: str, field: str | None = None, details: dict | None = None) -> dict:
    return {"code": code, "message": message, "field": field, "details": details or {}}


def emit(envelope: dict, pretty: bool = False) -> None:
    text = json.dumps(envelope, ensure_ascii=False, indent=2 if pretty else None)
    sys.stdout.write(text + "\n")


# ---------------------------------------------------------------------------
# Маскирование секретов
# ---------------------------------------------------------------------------

_AUTH_HEADER_RE = re.compile(
    r"(?i)\b(authorization|x-user-token|x-device-token|x-api-key|proxy-authorization)"
    r"([\s]*[:=][\s]*)([^,}\n]+)"
)


def redact_text(text: str, secret_values: list[str] | None = None) -> str:
    """Маскирует значения секретов и auth-заголовков в произвольном тексте."""
    if not text:
        return text
    result = text
    for value in secret_values or []:
        if value and len(value) >= 6:
            result = result.replace(value, MASK)
    result = _AUTH_HEADER_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{MASK}", result)
    return result


def redact_obj(obj: Any, secret_values: list[str] | None = None) -> Any:
    if isinstance(obj, str):
        return redact_text(obj, secret_values)
    if isinstance(obj, dict):
        return {k: redact_obj(v, secret_values) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_obj(v, secret_values) for v in obj]
    return obj


# ---------------------------------------------------------------------------
# Конфигурация и секреты
# ---------------------------------------------------------------------------

def default_secrets_path() -> Path:
    override = os.environ.get("WAREHOUSE_AGENT_SECRETS_PATH")
    if override:
        return Path(override)
    if platform.system() == "Windows":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "WarehouseAgent" / "secrets" / "syncserver.env"
    return Path.home() / ".config" / "WarehouseAgent" / "secrets" / "syncserver.env"


def default_cases_dir() -> Path:
    override = os.environ.get("WAREHOUSE_AGENT_CASES_DIR")
    if override:
        return Path(override)
    if platform.system() == "Windows":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "WarehouseAgent" / "cases"
    return Path.home() / ".local" / "share" / "WarehouseAgent" / "cases"


def parse_env_file(text: str) -> dict[str, str]:
    """Парсит KEY=VALUE построчно. Комментарии (#) и пустые строки игнорируются."""
    result: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key:
            result[key] = value
    return result


def load_config(secrets_path: Path | None = None) -> dict[str, str]:
    path = secrets_path or default_secrets_path()
    file_values: dict[str, str] = {}
    if path.is_file():
        file_values = parse_env_file(path.read_text(encoding="utf-8-sig"))
    config = dict(file_values)
    for key in (
        "SYNC_SERVER_BASE_URL",
        "SYNC_SERVER_USER_TOKEN",
        "SYNC_SERVER_DEVICE_TOKEN",
        "SYNC_SERVER_SITE_ID",
        "SYNC_SERVER_ALLOW_INSECURE_LOCAL",
        "CATALOG_ACCESS_MODE",
        "CATALOG_CREATE_REQUIRE_CONFIRMATION",
        "CATALOG_MERGE_ENABLED",
    ):
        if os.environ.get(key):
            config[key] = os.environ[key]
    return config


def secret_values_from_config(config: dict[str, str]) -> list[str]:
    return [v for k, v in config.items() if "TOKEN" in k and v]


def parse_icacls_output(output: str, allowed_principals: set[str]) -> tuple[bool, list[str]]:
    """Разбирает вывод `icacls <file>`. Возвращает (safe, offenders).

    Разрешены только ACE для allowed_principals (сравнение без учёта регистра,
    по полному имени или по «хвосту» после backslash).
    """
    offenders: list[str] = []
    allowed_norm = {p.lower() for p in allowed_principals}
    allowed_tails = {p.split("\\")[-1].lower() for p in allowed_principals}
    for raw in output.splitlines():
        line = raw.strip()
        if not line or ":(" not in line:
            continue
        principal = line.split(":(", 1)[0].strip().strip('"')
        if not principal:
            continue
        norm = principal.lower()
        tail = norm.split("\\")[-1]
        if norm in allowed_norm or tail in allowed_tails:
            continue
        offenders.append(principal)
    return (len(offenders) == 0, offenders)


def check_secrets_acl(path: Path) -> tuple[bool, str]:
    """Проверяет, что файл секретов доступен только текущему пользователю и SYSTEM.

    Возвращает (safe, detail). На не-Windows — проверка POSIX-прав (0o600).
    """
    if not path.is_file():
        return False, f"файл секретов не найден: {path}"
    if platform.system() == "Windows":
        try:
            whoami = subprocess.run(
                ["whoami"], capture_output=True, text=True, timeout=10, check=False
            ).stdout.strip()
            proc = subprocess.run(
                ["icacls", str(path)], capture_output=True, text=True, timeout=15, check=False
            )
        except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
            return False, f"не удалось выполнить icacls: {exc}"
        if proc.returncode != 0:
            return False, f"icacls завершился с кодом {proc.returncode}"
        allowed = {whoami, "NT AUTHORITY\\SYSTEM", "NT AUTHORITY\\СИСТЕМА", "SYSTEM", "СИСТЕМА"}
        safe, offenders = parse_icacls_output(proc.stdout, allowed)
        if safe:
            return True, "ACL: только текущий пользователь и SYSTEM"
        return False, "ACL небезопасен, лишние principal'ы: " + ", ".join(offenders)
    st = path.stat()
    mode = stat.S_IMODE(st.st_mode)
    if mode & 0o077:
        return False, f"небезопасные права {oct(mode)}; требуется 0o600"
    if st.st_uid != os.getuid():
        return False, "файл секретов принадлежит другому пользователю"
    return True, "права 0o600, владелец — текущий пользователь"


def enforce_acl_or_raise(secrets_path: Path) -> None:
    safe, detail = check_secrets_acl(secrets_path)
    if not safe:
        raise ConfigError(
            "SECRETS_ACL_UNSAFE",
            "Отказ в работе: " + detail + ". Запустите scripts/protect_secrets.ps1.",
        )


def is_private_or_local_host(hostname: str) -> bool:
    host = (hostname or "").lower()
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)\.(\d+)$", host)
    if not m:
        return False
    a, b = int(m.group(1)), int(m.group(2))
    return a == 10 or (a == 192 and b == 168) or (a == 172 and 16 <= b <= 31)


# ---------------------------------------------------------------------------
# Маппинг ошибок сервера в конверт (сохраняем доменные коды)
# ---------------------------------------------------------------------------

def map_error_response(status_code: int, body: bytes, secret_values: list[str]) -> list[dict]:
    """Преобразует тело ошибки SyncServer в errors[] конверта.

    Поддерживаемые серверные форматы (см. references/ERROR_HANDLING.md):
      A. {"error": {"code", "message", "details"?}, "request_id"?}
      B. {"detail": "строка"}
      C. {"detail": {"code", "message", ...}}          (доменные 409)
      D. {"detail": [{"loc", "msg", "type"}, ...]}      (pydantic 422)
    """
    default_code = STATUS_ERROR_CODES.get(status_code, f"HTTP_{status_code}")
    text = body.decode("utf-8", errors="replace") if body else ""
    try:
        payload = json.loads(text) if text.strip() else None
    except json.JSONDecodeError:
        snippet = redact_text(text[:300], secret_values)
        return [error_entry("INVALID_JSON", f"Тело ответа не является JSON (HTTP {status_code})",
                            details={"snippet": snippet})]
    if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
        err = payload["error"]
        return [error_entry(
            str(err.get("code") or default_code),
            redact_text(str(err.get("message") or f"HTTP {status_code}"), secret_values),
            details=redact_obj(err.get("details") or {}, secret_values),
        )]
    if isinstance(payload, dict) and "detail" in payload:
        detail = payload["detail"]
        if isinstance(detail, str):
            return [error_entry(default_code, redact_text(detail, secret_values))]
        if isinstance(detail, dict):
            extra = {k: v for k, v in detail.items() if k not in ("code", "message")}
            return [error_entry(
                str(detail.get("code") or default_code),
                redact_text(str(detail.get("message") or default_code), secret_values),
                details=redact_obj(extra, secret_values),
            )]
        if isinstance(detail, list):
            errors = []
            for item in detail[:10]:
                if isinstance(item, dict):
                    loc = item.get("loc") or []
                    field = ".".join(str(p) for p in loc if p != "body") or None
                    errors.append(error_entry(
                        default_code,
                        redact_text(str(item.get("msg") or "validation error"), secret_values),
                        field=field,
                        details={"type": item.get("type")},
                    ))
            return errors or [error_entry(default_code, f"HTTP {status_code}")]
    if payload is None:
        return [error_entry(default_code, f"HTTP {status_code} без тела ответа")]
    snippet = redact_text(text[:300], secret_values)
    return [error_entry(default_code, f"HTTP {status_code}", details={"snippet": snippet})]


def classify_network_error(exc: Exception) -> tuple[str, str]:
    text = str(exc)
    lowered = text.lower()
    if isinstance(exc, (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout)):
        return "TIMEOUT", f"Таймаут соединения с SyncServer: {text}"
    if isinstance(exc, httpx.ConnectError):
        if "getaddrinfo" in lowered or "name or service not known" in lowered or "nodename" in lowered:
            return "DNS_ERROR", f"Не удалось разрешить имя хоста SyncServer: {text}"
        if "connection refused" in lowered or "errno 111" in lowered or "10061" in lowered:
            return "CONNECT_REFUSED", f"Соединение отклонено SyncServer: {text}"
        return "NETWORK_ERROR", f"Сетевая ошибка: {text}"
    return "NETWORK_ERROR", f"Сетевая ошибка: {text}"


# ---------------------------------------------------------------------------
# HTTP-клиент
# ---------------------------------------------------------------------------

class SyncClient:
    def __init__(
        self,
        config: dict[str, str],
        *,
        transport: httpx.BaseTransport | None = None,
        retry_backoff: tuple[float, ...] = (0.5, 1.5),
    ):
        self.config = config
        self.base_url = (config.get("SYNC_SERVER_BASE_URL") or "").rstrip("/")
        self.user_token = config.get("SYNC_SERVER_USER_TOKEN") or ""
        self.device_token = config.get("SYNC_SERVER_DEVICE_TOKEN") or ""
        self.secret_values = secret_values_from_config(config)
        self.retry_backoff = retry_backoff
        self.last_request_id: str | None = None
        self.last_status: int | None = None
        self._transport = transport
        self._validate_base_url()

    def _validate_base_url(self) -> None:
        if not self.base_url:
            raise ConfigError("CONFIG_MISSING", "SYNC_SERVER_BASE_URL не задан в файле секретов")
        parsed = httpx.URL(self.base_url)
        if parsed.scheme not in ("http", "https"):
            raise ConfigError("CONFIG_INVALID", f"Недопустимая схема URL: {parsed.scheme}")
        if parsed.scheme == "http":
            allow_insecure = (self.config.get("SYNC_SERVER_ALLOW_INSECURE_LOCAL") or "").lower() == "true"
            if not (allow_insecure and is_private_or_local_host(parsed.host or "")):
                raise ConfigError(
                    "INSECURE_URL_FORBIDDEN",
                    "HTTP без TLS разрешён только для локальных/частных адресов "
                    "при SYNC_SERVER_ALLOW_INSECURE_LOCAL=true. "
                    "verify=false не поддерживается и не будет.",
                )

    # -- граница полномочий --
    @staticmethod
    def enforce_allowlist(method: str, path: str) -> None:
        if not path.startswith(API_PREFIX + "/"):
            raise EndpointNotAllowed(f"Путь вне {API_PREFIX} запрещён: {method} {path}")
        if DENIED_PATH_RE.search(path):
            raise EndpointNotAllowed(f"Эндпоинт запрещён политикой скилла: {method} {path}")
        for allowed_method, pattern in ALLOWED_ENDPOINTS:
            if allowed_method == method and pattern.match(path):
                return
        raise EndpointNotAllowed(f"Эндпоинт вне allowlist: {method} {path}")

    def _headers(self, request_id: str, with_auth: bool) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "X-Request-Id": request_id,
            "User-Agent": f"warehouse-storekeeper/{CLIENT_VERSION}",
        }
        if with_auth:
            if self.user_token:
                headers["X-User-Token"] = self.user_token
            if self.device_token:
                headers["X-Device-Token"] = self.device_token
        return headers

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json_body: Any = None,
        with_auth: bool = True,
        idempotent: bool = False,
    ) -> tuple[int, Any, list[dict]]:
        """Выполняет запрос. Возвращает (status_code, payload, errors).

        При HTTP-ошибке payload=None, errors заполнен. Сетевые ошибки
        выбрасываются как httpx.HTTPError — перехватываются в run_command.
        Автоповторы — только для idempotent (GET) запросов.
        """
        self.enforce_allowlist(method, path)
        if with_auth and not self.user_token:
            raise ConfigError(
                "TOKEN_MISSING",
                "SYNC_SERVER_USER_TOKEN не задан. Заполните файл секретов "
                "(см. templates/syncserver.env.example).",
            )
        request_id = str(uuid.uuid4())
        self.last_request_id = request_id
        url = self.base_url + path
        attempts = 1 + (len(self.retry_backoff) if idempotent else 0)
        last_exc: Exception | None = None
        with httpx.Client(
            timeout=httpx.Timeout(
                connect=CONNECT_TIMEOUT, read=READ_TIMEOUT,
                write=WRITE_TIMEOUT, pool=POOL_TIMEOUT,
            ),
            verify=True,
            transport=self._transport,
        ) as client:
            for attempt in range(attempts):
                if attempt:
                    time.sleep(self.retry_backoff[attempt - 1])
                try:
                    response = client.request(
                        method,
                        url,
                        params={k: v for k, v in (params or {}).items() if v is not None},
                        json=json_body,
                        headers=self._headers(request_id, with_auth),
                    )
                except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                    last_exc = exc
                    continue
                self.last_status = response.status_code
                resp_request_id = response.headers.get("X-Request-Id")
                if resp_request_id:
                    self.last_request_id = resp_request_id
                if response.status_code in (502, 503, 504) and idempotent and attempt < attempts - 1:
                    continue
                if response.status_code >= 400:
                    return response.status_code, None, map_error_response(
                        response.status_code, response.content, self.secret_values
                    )
                try:
                    payload = response.json() if response.content else None
                except json.JSONDecodeError:
                    return response.status_code, None, map_error_response(
                        response.status_code, response.content, self.secret_values
                    )
                # HTTP 200 не гарантирует бизнес-успех, если тело содержит errors.
                if isinstance(payload, dict) and isinstance(payload.get("errors"), list) and payload["errors"]:
                    mapped = [
                        error_entry(
                            str(e.get("code", "BUSINESS_ERROR")) if isinstance(e, dict) else "BUSINESS_ERROR",
                            redact_text(str(e.get("message", e)) if isinstance(e, dict) else str(e), self.secret_values),
                            field=e.get("field") if isinstance(e, dict) else None,
                            details=redact_obj(e.get("details", {}), self.secret_values) if isinstance(e, dict) else {},
                        )
                        for e in payload["errors"]
                    ]
                    return response.status_code, None, mapped
                return response.status_code, payload, []
        assert last_exc is not None
        raise last_exc


# ---------------------------------------------------------------------------
# Утилиты команд
# ---------------------------------------------------------------------------

def read_json_file(path_str: str) -> Any:
    path = Path(path_str)
    if not path.is_file():
        raise ConfigError("INPUT_NOT_FOUND", f"Файл не найден: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ConfigError("INPUT_INVALID_JSON", f"Некорректный JSON в {path}: {exc}")


def require_uuid(value: str, field: str) -> str:
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError, TypeError):
        raise ConfigError("VALIDATION_ERROR", f"Поле {field} должно быть UUID, получено: {value!r}")


def require_operation_type(value: str) -> str:
    op_type = (value or "").upper()
    if op_type == "ADJUSTMENT":
        raise ConfigError(
            "OPERATION_TYPE_NOT_ALLOWED",
            "ADJUSTMENT запрещён политикой скилла (прямое изменение остатков).",
        )
    if op_type not in ALLOWED_OPERATION_TYPES:
        raise ConfigError(
            "VALIDATION_ERROR",
            f"Недопустимый тип операции: {value!r}. Допустимы: {sorted(ALLOWED_OPERATION_TYPES)}.",
        )
    return op_type


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _qty_positive(qty: Any) -> bool:
    try:
        return float(qty) > 0
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# Команды: чтение. Все хендлеры возвращают (data, warnings, errors).
# ---------------------------------------------------------------------------

def cmd_health(client: SyncClient, args) -> tuple[Any, list, list]:
    _, payload, errors = client.request("GET", f"{API_PREFIX}/health", with_auth=False, idempotent=True)
    return (None, [], errors) if errors else (payload, [], [])


def cmd_whoami(client: SyncClient, args) -> tuple[Any, list, list]:
    _, payload, errors = client.request("GET", f"{API_PREFIX}/auth/me", idempotent=True)
    return (None, [], errors) if errors else (payload, [], [])


def cmd_capabilities(client: SyncClient, args) -> tuple[Any, list, list]:
    _, payload, errors = client.request("GET", f"{API_PREFIX}/auth/context", idempotent=True)
    return (None, [], errors) if errors else (payload, [], [])


def cmd_sites_list(client: SyncClient, args) -> tuple[Any, list, list]:
    _, payload, errors = client.request("GET", f"{API_PREFIX}/auth/sites", idempotent=True)
    return (None, [], errors) if errors else (payload, [], [])


def cmd_units_list(client: SyncClient, args) -> tuple[Any, list, list]:
    params = {"updated_after": args.updated_after, "limit": args.limit}
    _, payload, errors = client.request("GET", f"{API_PREFIX}/catalog/units", params=params, idempotent=True)
    return (None, [], errors) if errors else (payload, [], [])


def cmd_catalog_search(client: SyncClient, args) -> tuple[Any, list, list]:
    params = {
        "search": args.query,
        "category_id": args.category_id,
        "page": args.page,
        "page_size": args.page_size,
        "site_id": args.site_id,
    }
    _, payload, errors = client.request("GET", f"{API_PREFIX}/catalog/read/items", params=params, idempotent=True)
    if errors:
        return None, [], errors
    warnings = []
    if isinstance(payload, dict):
        total = payload.get("total_count", 0)
        if total == 0:
            warnings.append({"code": "catalog_empty",
                             "message": "Позиции не найдены — оставьте строку unresolved или уточните запрос."})
        elif total > 1:
            warnings.append({"code": "catalog_ambiguous",
                             "message": f"Найдено {total} похожих позиций — требуется выбор пользователя, "
                                        "не считайте первую точным совпадением."})
    return payload, warnings, []


def cmd_catalog_get(client: SyncClient, args) -> tuple[Any, list, list]:
    _, payload, errors = client.request("GET", f"{API_PREFIX}/catalog/read/items/{int(args.item_id)}", idempotent=True)
    return (None, [], errors) if errors else (payload, [], [])


def _default_site_id(client: SyncClient) -> int | None:
    raw = client.config.get("SYNC_SERVER_SITE_ID")
    if raw:
        try:
            return int(raw)
        except ValueError:
            return None
    return None


def cmd_catalog_balances(client: SyncClient, args) -> tuple[Any, list, list]:
    params = {
        "site_id": args.site_id if args.site_id is not None else _default_site_id(client),
        "search": args.search,
        "item_id": args.item_id,
        "only_positive": args.only_positive or None,
        "page": args.page,
        "page_size": args.page_size,
    }
    _, payload, errors = client.request("GET", f"{API_PREFIX}/balances", params=params, idempotent=True)
    return (None, [], errors) if errors else (payload, [], [])


def cmd_catalog_categories(client: SyncClient, args) -> tuple[Any, list, list]:
    params = {"search": args.query, "page": args.page, "page_size": args.page_size}
    _, payload, errors = client.request("GET", f"{API_PREFIX}/catalog/read/categories", params=params, idempotent=True)
    return (None, [], errors) if errors else (payload, [], [])
# Команды: каталог (chief_storekeeper guarded)
# ---------------------------------------------------------------------------

def _require_catalog_admin(client: SyncClient) -> None:
    mode = (client.config.get("CATALOG_ACCESS_MODE") or "").lower()
    if mode != "chief_guarded":
        raise ConfigError(
            "CATALOG_ACCESS_DISABLED",
            "Создание/изменение каталога отключено. Установите CATALOG_ACCESS_MODE=chief_guarded "
            "в файле секретов для активации guarded-режима.",
        )
    merge_enabled = (client.config.get("CATALOG_MERGE_ENABLED") or "").lower()
    if merge_enabled == "true":
        raise ConfigError(
            "CATALOG_MERGE_FORBIDDEN",
            "CATALOG_MERGE_ENABLED=true запрещено политикой скилла. "
            "Merge каталога не выполняется агентом ни при каких настройках.",
        )


def _require_confirmation(client: SyncClient) -> None:
    required = (client.config.get("CATALOG_CREATE_REQUIRE_CONFIRMATION") or "").lower()
    if required != "true":
        raise ConfigError(
            "CONFIRMATION_DISABLED",
            "CATALOG_CREATE_REQUIRE_CONFIRMATION должен быть true для guarded-режима.",
        )


def _catalog_duplicate_check(client: SyncClient, name: str, sku: str | None) -> tuple[list, list]:
    """Многоэтапная проверка дубликатов. Возвращает (warnings, errors)."""
    warnings: list[dict] = []
    errors: list[dict] = []

    # Этап 1: точный поиск
    _, result, _ = client.request(
        "GET", f"{API_PREFIX}/catalog/read/items",
        params={"search": name, "page_size": 5},
        idempotent=True,
    )
    exact = (result or {}).get("items") or []
    for item in exact:
        if (item.get("name") or "").strip().lower() == name.strip().lower():
            warnings.append({"code": "duplicate_exact_name", "message": f"Точное совпадение имени: item_id={item['id']}, name={item['name']}", "details": {"item_id": item["id"], "name": item["name"]}})

    # Этап 2: SKU/артикул (если задан)
    if sku:
        _, result, _ = client.request(
            "GET", f"{API_PREFIX}/catalog/read/items",
            params={"search": sku, "page_size": 5},
            idempotent=True,
        )
        for item in (result or {}).get("items") or []:
            if (item.get("sku") or "").strip().lower() == sku.strip().lower():
                warnings.append({"code": "duplicate_sku", "message": f"Точное совпадение артикула: item_id={item['id']}, sku={item['sku']}", "details": {"item_id": item["id"], "sku": item["sku"], "name": item["name"]}})

    # Этап 3: нормализованный поиск + неактивные
    norm = re.sub(r"[-/_.()]", " ", name.lower()).strip()
    _, result, _ = client.request(
        "GET", f"{API_PREFIX}/catalog/admin/items",
        params={"search": norm, "page_size": 10},
        idempotent=True,
    )
    admin_items = (result or {}).get("items") or []
    for item in admin_items:
        item_norm = re.sub(r"[-/_.()]", " ", (item.get("name") or "").lower()).strip()
        confidence = _name_similarity(norm, item_norm)
        if confidence >= 0.85 and item.get("id"):
            warnings.append({"code": "duplicate_similar", "message": f"Похожая позиция (confidence={confidence:.0%}): item_id={item['id']}, name={item['name']}, active={item.get('is_active')}", "details": {"item_id": item["id"], "name": item["name"], "is_active": item.get("is_active"), "confidence": confidence}})

    if warnings:
        errors.append(error_entry("DUPLICATE_CANDIDATES", "Найдены вероятные дубликаты — создание запрещено. Проверьте candidates в warnings.", details={"candidates_count": len(warnings)}))
    return warnings, errors


def _name_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    # Jaccard по символам (быстро и без зависимостей)
    set_a, set_b = set(a.split()), set(b.split())
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def cmd_catalog_create(client: SyncClient, args) -> tuple[Any, list, list]:
    _require_catalog_admin(client)
    _require_confirmation(client)

    data = read_json_file(args.input)
    if not isinstance(data, dict):
        raise ConfigError("VALIDATION_ERROR", "catalog_create_request должен быть JSON-объектом")
    name = str(data.get("name") or "").strip()
    unit_id = data.get("unit_id")
    if not name or not isinstance(unit_id, int) or unit_id < 1:
        return None, [], [error_entry("VALIDATION_ERROR", "name (строка) и unit_id (int≥1) обязательны", field="name/unit_id")]

    # Шаг 1: проверка дубликатов (всегда, даже с --confirmed)
    dup_warnings, dup_errors = _catalog_duplicate_check(client, name, data.get("sku"))
    if dup_errors:
        return None, dup_warnings, dup_errors

    # Шаг 2: подтверждение
    if not args.confirmed:
        return None, dup_warnings, [error_entry(
            "CONFIRMATION_REQUIRED",
            f"Создание позиции «{name}»: дубликатов не найдено ({len(dup_warnings)} похожих с низкой уверенностью). "
            "Покажите кладовщику сводку и запросите явное «подтверждаю». Затем повторите с флагом --confirmed.",
        )]

    body: dict[str, Any] = {"name": name, "unit_id": unit_id}
    if data.get("sku"):
        body["sku"] = str(data["sku"])[:100]
    if data.get("category_id"):
        body["category_id"] = int(data["category_id"])
    if data.get("description"):
        body["description"] = str(data["description"])
    if data.get("hashtags"):
        body["hashtags"] = [str(t) for t in data["hashtags"]]

    _, payload, errors = client.request("POST", f"{API_PREFIX}/catalog/admin/items", json_body=body)
    if errors:
        return None, dup_warnings, errors
    if isinstance(payload, dict) and payload.get("id"):
        dup_warnings.append({"code": "catalog_item_created", "message": f"Создана позиция item_id={payload['id']}, name={payload.get('name')}", "details": {"item_id": payload["id"], "name": payload.get("name"), "created_at": payload.get("created_at")}})
    return payload, dup_warnings, []


def cmd_catalog_admin_get(client: SyncClient, args) -> tuple[Any, list, list]:
    _require_catalog_admin(client)
    _, payload, errors = client.request("GET", f"{API_PREFIX}/catalog/admin/items/{int(args.item_id)}", idempotent=True)
    return (None, [], errors) if errors else (payload, [], [])


def cmd_catalog_admin_search(client: SyncClient, args) -> tuple[Any, list, list]:
    _require_catalog_admin(client)
    params = {"search": args.query, "page": args.page or 1, "page_size": min(args.page_size or 50, 200)}
    _, payload, errors = client.request("GET", f"{API_PREFIX}/catalog/admin/items", params=params, idempotent=True)
    if errors:
        return None, [], errors
    return payload, [], []


def cmd_catalog_update(client: SyncClient, args) -> tuple[Any, list, list]:
    _require_catalog_admin(client)
    item_id = int(args.item_id)
    data = read_json_file(args.input) if args.input else {}
    warnings: list[dict] = []

    # Гвард: деактивация запрещена
    if isinstance(data.get("is_active"), bool) and data["is_active"] is False:
        return None, warnings, [error_entry("DEACTIVATION_FORBIDDEN", "Деактивация позиций каталога запрещена политикой скилла (is_active=false недопустимо).", field="is_active")]

    # Гвард: нельзя менять unit_id / category_id на этом уровне
    if data.get("unit_id") or data.get("category_id"):
        warnings.append({"code": "update_limited", "message": "Изменение unit_id / category_id не разрешено (можно: name, sku, description, hashtags). Поля игнорируются."})

    _, existing, errors = client.request("GET", f"{API_PREFIX}/catalog/admin/items/{item_id}", idempotent=True)
    if errors:
        return None, warnings, errors
    if not existing.get("is_active"):
        warnings.append({"code": "item_inactive", "message": f"Позиция item_id={item_id} уже неактивна — редактирование небезопасно."})

    body: dict[str, Any] = {}
    for field in ("sku", "name", "description"):
        if data.get(field) is not None:
            body[field] = data[field]
    if data.get("hashtags") is not None:
        body["hashtags"] = [str(t) for t in data["hashtags"]]
    if not body:
        return None, warnings, [error_entry("VALIDATION_ERROR", "Нет изменяемых полей (name, sku, description, hashtags)", field="input")]

    _, payload, errors = client.request("PATCH", f"{API_PREFIX}/catalog/admin/items/{item_id}", json_body=body)
    if errors:
        return None, warnings, errors
    return payload, warnings, []

def _build_server_line(line: dict, line_number: int, *, for_source_document: bool) -> dict:
    server_line: dict[str, Any] = {
        "line_number": line_number,
        "item_id": line.get("item_id"),
        "qty": line.get("qty"),
    }
    if line.get("batch"):
        server_line["batch"] = line["batch"]
    comment = line.get("comment")
    raw_name = line.get("raw_name")
    if for_source_document:
        if raw_name:
            server_line["source_item_name"] = str(raw_name)[:255]
        if line.get("raw_sku"):
            server_line["source_item_sku"] = str(line["raw_sku"])[:100]
        if line.get("raw_unit"):
            server_line["source_unit_name"] = str(line["raw_unit"])[:100]
        if comment:
            server_line["comment"] = comment
    else:
        if not comment and raw_name:
            comment = str(raw_name)
        if comment:
            server_line["comment"] = comment
    return server_line


def _validate_draft_input(data: dict) -> tuple[str, int, list, list]:
    errors = []
    op_type = require_operation_type(str(data.get("operation_type") or ""))
    site_id = data.get("site_id")
    if not isinstance(site_id, int) or site_id < 1:
        errors.append(error_entry("VALIDATION_ERROR", "site_id обязателен (int >= 1)", field="site_id"))
    lines = data.get("lines")
    if not isinstance(lines, list) or not lines:
        errors.append(error_entry("VALIDATION_ERROR", "lines: требуется непустой список", field="lines"))
        lines = []
    if op_type == "MOVE":
        src, dst = data.get("source_site_id"), data.get("destination_site_id")
        if not src or not dst or src == dst:
            errors.append(error_entry(
                "VALIDATION_ERROR",
                "MOVE требует source_site_id и destination_site_id, и они должны различаться",
                field="source_site_id/destination_site_id",
            ))
    return op_type, site_id or 0, lines, errors


def cmd_draft_create(client: SyncClient, args) -> tuple[Any, list, list]:
    data = read_json_file(args.input)
    if not isinstance(data, dict):
        raise ConfigError("VALIDATION_ERROR", "draft_request должен быть JSON-объектом")
    op_type, site_id, lines, errors = _validate_draft_input(data)
    if errors:
        return None, [], errors

    source_doc = data.get("source_document")
    warnings: list = []
    server_lines: list[dict] = []
    for index, line in enumerate(lines, start=1):
        if not isinstance(line, dict):
            warnings.append({"code": "line_skipped", "message": f"Строка {index} пропущена: не объект", "details": {}})
            continue
        line_number = int(line.get("line_number") or index)
        if not _qty_positive(line.get("qty")):
            warnings.append({"code": "line_skipped",
                             "message": f"Строка {line_number} пропущена: qty не положительно",
                             "details": {"line_number": line_number, "raw_name": line.get("raw_name")}})
            continue
        if line.get("item_id") is None:
            warnings.append({"code": "line_unresolved_skipped",
                             "message": f"Строка {line_number} «{line.get('raw_name')}» не сопоставлена каталогу — "
                                        "в черновик не включена, остаётся unresolved",
                             "details": {"line_number": line_number, "raw_name": line.get("raw_name")}})
            continue
        server_lines.append(_build_server_line(line, line_number, for_source_document=bool(source_doc)))
    if not server_lines:
        return None, warnings, [error_entry(
            "VALIDATION_ERROR",
            "Нет сопоставленных строк с item_id — черновик не создан. Сначала сопоставьте позиции каталога.",
            field="lines",
        )]

    if source_doc:
        source_ref = source_doc.get("source_ref")
        if not source_ref:
            return None, warnings, [error_entry(
                "VALIDATION_ERROR",
                "source_document.source_ref обязателен (используйте sha256 исходного файла) — "
                "иначе дедупликация повторной отправки не сработает",
                field="source_document.source_ref",
            )]
        body: dict[str, Any] = {
            "operation_type": op_type,
            "site_id": site_id,
            "source_ref": str(source_ref)[:255],
            "source_document_type": source_doc.get("source_document_type") or "ocr_scan",
            "lines": server_lines,
        }
        if source_doc.get("source_document_date"):
            body["source_document_date"] = source_doc["source_document_date"]
        notes = data.get("notes")
        if not notes and source_doc.get("number"):
            notes = f"Накладная №{source_doc.get('number')}"
            if source_doc.get("date"):
                notes += f" от {source_doc.get('date')}"
            if source_doc.get("supplier"):
                notes += f", {source_doc.get('supplier')}"
        if data.get("client_request_id"):
            body["client_request_id"] = str(data["client_request_id"])[:100]
        path = f"{API_PREFIX}/operations/from-source-document"
    else:
        body = {"operation_type": op_type, "site_id": site_id, "lines": server_lines}
        notes = data.get("notes")
        client_request_id = data.get("client_request_id") or args.client_request_id or uuid.uuid4().hex
        body["client_request_id"] = str(client_request_id)[:100]
        warnings.append({"code": "idempotency_key",
                         "message": f"client_request_id={body['client_request_id']} — "
                                    "сохраните его: повтор с тем же ключом и телом безопасен (дедуп на сервере)."})
        path = f"{API_PREFIX}/operations"

    for field in ("effective_at", "source_site_id", "destination_site_id", "issued_to_name"):
        if data.get(field) is not None:
            body[field] = data[field]
    if notes:
        body["notes"] = str(notes)[:1000]

    _, payload, req_errors = client.request("POST", path, json_body=body)
    if req_errors:
        return None, warnings, req_errors
    # Добавляем сводку сопоставления: сколько строк вошло, сколько пропущено.
    resolved = len(server_lines)
    total = resolved + len([w for w in warnings if w.get("code") == "line_unresolved_skipped"])
    if isinstance(payload, dict):
        payload["_resolved_count"] = resolved
        payload["_total_input_lines"] = total
        payload["_unresolved_count"] = total - resolved
        payload["_unresolved_lines"] = [
            w["details"] for w in warnings if w.get("code") == "line_unresolved_skipped"
        ]
        payload["_draft_partial"] = resolved < total
    return payload, warnings, []


def cmd_draft_get(client: SyncClient, args) -> tuple[Any, list, list]:
    draft_id = require_uuid(args.draft_id, "draft_id")
    _, payload, errors = client.request("GET", f"{API_PREFIX}/operations/{draft_id}", idempotent=True)
    return (None, [], errors) if errors else (payload, [], [])


def cmd_draft_list_own(client: SyncClient, args) -> tuple[Any, list, list]:
    _, me, errors = client.request("GET", f"{API_PREFIX}/auth/me", idempotent=True)
    if errors:
        return None, [], errors
    user_id = ((me or {}).get("user") or {}).get("id")
    if not user_id:
        return None, [], [error_entry("UNEXPECTED_RESPONSE", "Не удалось определить текущего пользователя из /auth/me")]
    params = {
        "created_by_user_id": user_id,
        "status": args.status,
        "site_id": args.site_id,
        "page": args.page,
        "page_size": args.page_size,
    }
    _, payload, errors = client.request("GET", f"{API_PREFIX}/operations", params=params, idempotent=True)
    return (None, [], errors) if errors else (payload, [], [])


def _fetch_draft_for_edit(client: SyncClient, draft_id: str) -> tuple[dict | None, list]:
    _, payload, errors = client.request("GET", f"{API_PREFIX}/operations/{draft_id}", idempotent=True)
    if errors:
        return None, errors
    if payload.get("status") != "draft":
        return None, [error_entry(
            "OPERATION_IN_WRONG_STATE",
            f"Операция в статусе {payload.get('status')!r}: изменять можно только свои черновики (draft).",
            details={"current_state": payload.get("status"), "allowed_states": ["draft"]},
        )]
    return payload, []


def _response_line_to_request(line: dict) -> dict:
    """Конвертирует строку ответа сервера в строку запроса PATCH (full-replace).

    Ограничение сервера: PATCH принимает только OperationLineCreate, поэтому
    source_*-снимки не пересылаются; raw_name сохраняем в comment, если он пуст.
    """
    item_id = line.get("item_id") if line.get("item_id") is not None else line.get("resolved_item_id")
    comment = line.get("comment")
    if not comment and line.get("source_item_name"):
        comment = line["source_item_name"]
    request_line: dict[str, Any] = {
        "line_number": line.get("line_number"),
        "item_id": item_id,
        "qty": line.get("qty"),
    }
    if line.get("batch"):
        request_line["batch"] = line["batch"]
    if comment:
        request_line["comment"] = comment
    return request_line


def _patch_lines(client: SyncClient, draft: dict, new_lines: list, warnings: list) -> tuple[Any, list, list]:
    body = {"lines": new_lines, "expected_version": draft.get("version")}
    _, payload, errors = client.request("PATCH", f"{API_PREFIX}/operations/{draft['id']}", json_body=body)
    if errors:
        return None, warnings, errors
    warnings.append({
        "code": "lines_replaced",
        "message": "Сервер заменяет строки целиком: идентификаторы строк (id) перевыпущены, "
                   "source_*-снимки строк не пересылаются (ограничение API, см. API_GAPS.md).",
    })
    return payload, warnings, []


def cmd_draft_add_lines(client: SyncClient, args) -> tuple[Any, list, list]:
    draft_id = require_uuid(args.draft_id, "draft_id")
    data = read_json_file(args.input)
    lines = data.get("lines") if isinstance(data, dict) else None
    if not isinstance(lines, list) or not lines:
        raise ConfigError("VALIDATION_ERROR", "input-файл должен содержать непустой список lines")
    draft, errors = _fetch_draft_for_edit(client, draft_id)
    if errors:
        return None, [], errors
    warnings: list = []
    merged = [_response_line_to_request(l) for l in draft.get("lines") or []]
    next_number = max([l.get("line_number") or 0 for l in draft.get("lines") or []] + [0]) + 1
    added = 0
    for line in lines:
        if not isinstance(line, dict) or line.get("item_id") is None or not _qty_positive(line.get("qty")):
            warnings.append({
                "code": "line_skipped",
                "message": "Строка пропущена: нет item_id или qty <= 0",
                "details": {"raw_name": line.get("raw_name") if isinstance(line, dict) else None},
            })
            continue
        explicit_number = line.get("line_number")
        server_line = _build_server_line(line, int(explicit_number or next_number), for_source_document=False)
        next_number = max(next_number, int(explicit_number) + 1) if explicit_number else next_number + 1
        merged.append(server_line)
        added += 1
    if not added:
        return None, warnings, [error_entry("VALIDATION_ERROR", "Ни одной валидной строки для добавления", field="lines")]
    return _patch_lines(client, draft, merged, warnings)


def cmd_draft_update_line(client: SyncClient, args) -> tuple[Any, list, list]:
    draft_id = require_uuid(args.draft_id, "draft_id")
    draft, errors = _fetch_draft_for_edit(client, draft_id)
    if errors:
        return None, [], errors
    warnings: list = []
    line_numbers = [l.get("line_number") for l in draft.get("lines") or []]
    if args.line_number not in line_numbers:
        return None, warnings, [error_entry(
            "NOT_FOUND", f"Строка line_number={args.line_number} не найдена в черновике", field="line_number")]
    if args.qty is not None and not _qty_positive(args.qty):
        return None, warnings, [error_entry("VALIDATION_ERROR", "qty должно быть > 0", field="qty")]
    merged = []
    for line in draft.get("lines") or []:
        req_line = _response_line_to_request(line)
        if req_line["line_number"] == args.line_number:
            if args.qty is not None:
                req_line["qty"] = args.qty
            if args.item_id is not None:
                req_line["item_id"] = int(args.item_id)
            if args.comment is not None:
                req_line["comment"] = args.comment
            if args.batch is not None:
                req_line["batch"] = args.batch
        merged.append(req_line)
    return _patch_lines(client, draft, merged, warnings)


def cmd_draft_validate(client: SyncClient, args) -> tuple[Any, list, list]:
    """Локальная валидация черновика (отдельного серверного validate-API нет — см. API_GAPS)."""
    draft_id = require_uuid(args.draft_id, "draft_id")
    _, draft, errors = client.request("GET", f"{API_PREFIX}/operations/{draft_id}", idempotent=True)
    if errors:
        return None, [], errors
    warnings: list = []
    checks: list[dict] = []
    unresolved: list[int] = []
    lines = draft.get("lines") or []
    op_type = draft.get("operation_type")
    site_id = draft.get("site_id")

    if draft.get("status") != "draft":
        warnings.append({"code": "not_draft", "message": f"Операция уже в статусе {draft.get('status')!r}"})
    if not lines:
        checks.append({"check": "lines_present", "result": "fail", "details": {}})

    qty_by_item: dict[int, float] = {}
    for line in lines:
        line_no = line.get("line_number")
        item_id = line.get("item_id") if line.get("item_id") is not None else line.get("resolved_item_id")
        if not _qty_positive(line.get("qty")):
            checks.append({"line_number": line_no, "check": "qty_positive", "result": "fail", "details": {"qty": line.get("qty")}})
            continue
        checks.append({"line_number": line_no, "check": "qty_positive", "result": "pass", "details": {}})
        if item_id is None:
            unresolved.append(line_no)
            checks.append({"line_number": line_no, "check": "item_resolved", "result": "fail",
                           "details": {"raw_name": line.get("source_item_name")}})
            continue
        _, item, item_errors = client.request("GET", f"{API_PREFIX}/catalog/read/items/{item_id}", idempotent=True)
        if item_errors:
            unresolved.append(line_no)
            checks.append({"line_number": line_no, "check": "item_resolved", "result": "fail",
                           "details": {"item_id": item_id, "error": item_errors[0]["code"]}})
            continue
        if not item.get("is_active", True):
            checks.append({"line_number": line_no, "check": "item_active", "result": "fail",
                           "details": {"item_id": item_id, "name": item.get("name")}})
        else:
            checks.append({"line_number": line_no, "check": "item_active", "result": "pass",
                           "details": {"item_id": item_id, "name": item.get("name")}})
        qty_by_item[item_id] = qty_by_item.get(item_id, 0.0) + float(line.get("qty"))

    if op_type in DECREMENT_OPERATION_TYPES and site_id and qty_by_item:
        for item_id, required in qty_by_item.items():
            _, balances, bal_errors = client.request(
                "GET", f"{API_PREFIX}/balances",
                params={"site_id": site_id, "item_id": item_id, "page_size": 200},
                idempotent=True,
            )
            if bal_errors:
                warnings.append({"code": "balance_check_skipped",
                                 "message": f"Остаток по item_id={item_id} не проверен: {bal_errors[0]['code']}"})
                continue
            available = 0.0
            for row in (balances or {}).get("items") or []:
                try:
                    available += float(row.get("qty") or 0)
                except (TypeError, ValueError):
                    continue
            result = "pass" if available >= required else "warn"
            checks.append({"check": "stock_sufficient", "item_id": item_id, "result": result,
                           "details": {"required": required, "available": available, "site_id": site_id}})
            if result == "warn":
                warnings.append({"code": "insufficient_stock",
                                 "message": f"item_id={item_id}: требуется {required}, доступно {available} на site_id={site_id}"})

    failed = [c for c in checks if c.get("result") == "fail"]
    data = {
        "draft_id": draft_id,
        "status": draft.get("status"),
        "operation_type": op_type,
        "site_id": site_id,
        "lines_count": len(lines),
        "valid": not failed,
        "unresolved_lines": unresolved,
        "checks": checks,
        "validation_scope": "local",
        "note": "Серверного validate-эндпоинта нет; финальная проверка произойдёт при submit "
                "в Warehouse (скилл submit не выполняет).",
    }
    return data, warnings, []


# ---------------------------------------------------------------------------
# Команды: дело документа (case)
# ---------------------------------------------------------------------------

def _iter_case_states(cases_dir: Path):
    if not cases_dir.is_dir():
        return
    for state_file in sorted(cases_dir.glob("*/case_state.json")):
        try:
            yield state_file.parent.name, json.loads(state_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue


def cmd_case_init(client: SyncClient | None, args) -> tuple[Any, list, list]:
    source = Path(args.file)
    if not source.is_file():
        raise ConfigError("INPUT_NOT_FOUND", f"Файл не найден: {source}")
    cases_dir = Path(args.cases_dir) if args.cases_dir else default_cases_dir()
    digest = sha256_file(source)
    for case_id, state in _iter_case_states(cases_dir) or []:
        if state.get("sha256") == digest:
            return {
                "duplicate": True,
                "case_id": case_id,
                "case_dir": str(cases_dir / case_id),
                "sha256": digest,
                "state": state.get("state"),
                "draft_id": state.get("draft_id"),
                "message": "Этот файл уже обрабатывался. Создайте новое дело явно или откройте "
                           "существующее — второй draft автоматически не создаётся.",
            }, [], []
    case_id = f"case-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"
    case_dir = cases_dir / case_id
    (case_dir / "source").mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, case_dir / "source" / source.name)
    state = {
        "case_id": case_id,
        "state": "RECEIVED",
        "sha256": digest,
        "source_file": source.name,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "draft_id": None,
    }
    (case_dir / "case_state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"duplicate": False, "case_id": case_id, "case_dir": str(case_dir),
            "sha256": digest, "state": "RECEIVED"}, [], []


def cmd_case_find(client: SyncClient | None, args) -> tuple[Any, list, list]:
    cases_dir = Path(args.cases_dir) if args.cases_dir else default_cases_dir()
    digest = (args.sha256 or "").lower()
    matches = [
        {"case_id": cid, "state": st.get("state"), "draft_id": st.get("draft_id"),
         "source_file": st.get("source_file")}
        for cid, st in (_iter_case_states(cases_dir) or [])
        if (st.get("sha256") or "").lower() == digest
    ]
    return {"found": bool(matches), "matches": matches}, [], []


def cmd_case_set_state(client: SyncClient | None, args) -> tuple[Any, list, list]:
    cases_dir = Path(args.cases_dir) if args.cases_dir else default_cases_dir()
    state_file = cases_dir / args.case_id / "case_state.json"
    if not state_file.is_file():
        raise ConfigError("NOT_FOUND", f"Дело не найдено: {args.case_id}")
    new_state = args.state.upper()
    if new_state not in CASE_STATES:
        raise ConfigError("VALIDATION_ERROR", f"Недопустимое состояние. Допустимы: {CASE_STATES}")
    state = json.loads(state_file.read_text(encoding="utf-8"))
    state["state"] = new_state
    state["updated_at"] = now_iso()
    if args.draft_id:
        state["draft_id"] = require_uuid(args.draft_id, "draft_id")
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return state, [], []


# ---------------------------------------------------------------------------
# Диагностика конфигурации (без значений секретов)
# ---------------------------------------------------------------------------

def cmd_config_check(secrets_path: Path) -> dict:
    config = load_config(secrets_path)
    base_url = config.get("SYNC_SERVER_BASE_URL") or ""
    acl_safe, acl_detail = check_secrets_acl(secrets_path)
    insecure = (config.get("SYNC_SERVER_ALLOW_INSECURE_LOCAL") or "").lower() == "true"
    scheme = base_url.split("://", 1)[0] if "://" in base_url else None
    data = {
        "base_url_configured": bool(base_url),
        "base_url_scheme": scheme,
        "insecure_local_allowed": insecure,
        "user_token_present": bool(config.get("SYNC_SERVER_USER_TOKEN")),
        "device_token_present": bool(config.get("SYNC_SERVER_DEVICE_TOKEN")),
        "site_id_configured": bool(config.get("SYNC_SERVER_SITE_ID")),
        "secrets_file_exists": secrets_path.is_file(),
        "secrets_acl_safe": acl_safe,
        "secrets_acl_detail": acl_detail,
        "cases_dir": str(default_cases_dir()),
        "catalog_access_mode": config.get("CATALOG_ACCESS_MODE") or "read_only",
        "catalog_create_require_confirmation": (config.get("CATALOG_CREATE_REQUIRE_CONFIRMATION") or "").lower() == "true",
        "catalog_merge_enabled": (config.get("CATALOG_MERGE_ENABLED") or "").lower() == "true",
    }
    ok = bool(data["base_url_configured"] and data["user_token_present"] and acl_safe)
    return make_envelope("config.check", ok=ok, data=data)


# ---------------------------------------------------------------------------
# Диспетчер
# ---------------------------------------------------------------------------

LOCAL_ONLY_COMMANDS = {"config.check", "case.init", "case.find", "case.set-state"}


def run_command(args) -> int:
    command_name = getattr(args, "command_name", "unknown")
    secrets_path = Path(args.secrets_path) if getattr(args, "secrets_path", None) else default_secrets_path()
    pretty = getattr(args, "pretty", False)

    if command_name == "config.check":
        envelope = cmd_config_check(secrets_path)
        emit(envelope, pretty)
        return EXIT_OK if envelope["ok"] else EXIT_USAGE_ERROR

    client: SyncClient | None = None
    try:
        if command_name not in LOCAL_ONLY_COMMANDS:
            enforce_acl_or_raise(secrets_path)
            config = load_config(secrets_path)
            client = SyncClient(config)
        else:
            config = load_config(secrets_path)
            client = None
    except ConfigError as exc:
        emit(make_envelope(command_name, ok=False,
                           errors=[error_entry(exc.code, exc.message, details=exc.details)]), pretty)
        return EXIT_USAGE_ERROR

    try:
        data, warnings, errors = args.handler(client, args)
    except EndpointNotAllowed as exc:
        emit(make_envelope(command_name, ok=False,
                           errors=[error_entry("ENDPOINT_NOT_ALLOWED", str(exc))]), pretty)
        return EXIT_USAGE_ERROR
    except ConfigError as exc:
        emit(make_envelope(command_name, ok=False,
                           errors=[error_entry(exc.code, exc.message, details=exc.details)]), pretty)
        return EXIT_USAGE_ERROR
    except httpx.HTTPError as exc:
        secret_values = client.secret_values if client else []
        code, message = classify_network_error(exc)
        emit(make_envelope(command_name, ok=False,
                           errors=[error_entry(code, redact_text(message, secret_values))]), pretty)
        return EXIT_NETWORK_ERROR

    request_id = client.last_request_id if client else None
    status_code = client.last_status if client else None
    emit(make_envelope(command_name, ok=not errors, request_id=request_id, status_code=status_code,
                       data=data, warnings=warnings, errors=errors), pretty)
    return EXIT_OK if not errors else EXIT_SERVER_ERROR


# ---------------------------------------------------------------------------
# argparse
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="warehouse_api.py",
        description="CLI-клиент Warehouse SyncServer (только чтение и черновики операций).",
    )
    parser.add_argument("--secrets-path",
                        help="Путь к syncserver.env (по умолчанию %%LOCALAPPDATA%%\\WarehouseAgent\\secrets\\syncserver.env)")
    parser.add_argument("--pretty", action="store_true", help="Форматировать JSON с отступами")

    # Глобальные флаги, принимаемые и ПОСЛЕ подкоманды (default=SUPPRESS,
    # чтобы не затирать значения, заданные до подкоманды).
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--secrets-path", default=argparse.SUPPRESS)
    common.add_argument("--pretty", action="store_true", default=argparse.SUPPRESS)

    sub = parser.add_subparsers(dest="group", required=True)

    p = sub.add_parser("health", help="GET /api/v1/health", parents=[common])
    p.set_defaults(handler=cmd_health, command_name="health")
    p = sub.add_parser("whoami", help="GET /api/v1/auth/me", parents=[common])
    p.set_defaults(handler=cmd_whoami, command_name="whoami")
    p = sub.add_parser("capabilities", help="GET /api/v1/auth/context (роль, права, площадки)", parents=[common])
    p.set_defaults(handler=cmd_capabilities, command_name="capabilities")

    p_config = sub.add_parser("config", help="Диагностика конфигурации (без значений секретов)")
    config_sub = p_config.add_subparsers(dest="config_cmd", required=True)
    p = config_sub.add_parser("check", help="Проверить конфигурацию и ACL секретов", parents=[common])
    p.set_defaults(command_name="config.check")

    p_sites = sub.add_parser("sites", help="Площадки/склады")
    sites_sub = p_sites.add_subparsers(dest="sites_cmd", required=True)
    p = sites_sub.add_parser("list", help="GET /api/v1/auth/sites", parents=[common])
    p.set_defaults(handler=cmd_sites_list, command_name="sites.list")

    p_units = sub.add_parser("units", help="Единицы измерения")
    units_sub = p_units.add_subparsers(dest="units_cmd", required=True)
    p = units_sub.add_parser("list", help="GET /api/v1/catalog/units", parents=[common])
    p.add_argument("--updated-after")
    p.add_argument("--limit", type=int, default=1000)
    p.set_defaults(handler=cmd_units_list, command_name="units.list")

    p_catalog = sub.add_parser("catalog", help="Каталог ТМЦ и остатки")
    catalog_sub = p_catalog.add_subparsers(dest="catalog_cmd", required=True)
    p = catalog_sub.add_parser("search", help="GET /api/v1/catalog/read/items?search=", parents=[common])
    p.add_argument("--query", required=True)
    p.add_argument("--category-id", type=int)
    p.add_argument("--site-id", type=int)
    p.add_argument("--page", type=int, default=1)
    p.add_argument("--page-size", type=int, default=20)
    p.set_defaults(handler=cmd_catalog_search, command_name="catalog.search")
    p = catalog_sub.add_parser("get", help="GET /api/v1/catalog/read/items/{id}", parents=[common])
    p.add_argument("--item-id", type=int, required=True)
    p.set_defaults(handler=cmd_catalog_get, command_name="catalog.get")
    p = catalog_sub.add_parser("balances", help="GET /api/v1/balances", parents=[common])
    p.add_argument("--site-id", type=int)
    p.add_argument("--search")
    p.add_argument("--item-id", type=int)
    p.add_argument("--only-positive", action="store_true")
    p.add_argument("--page", type=int, default=1)
    p.add_argument("--page-size", type=int, default=100)
    p.set_defaults(handler=cmd_catalog_balances, command_name="catalog.balances")
    p = catalog_sub.add_parser("create", help="POST /catalog/admin/items (только с --confirmed после проверки дублей)", parents=[common])
    p.add_argument("--input", required=True, help="Путь к catalog_create_request.json")
    p.add_argument("--confirmed", action="store_true", help="Подтверждение пользователя получено — выполнить создание")
    p.set_defaults(handler=cmd_catalog_create, command_name="catalog.create")
    p = catalog_sub.add_parser("admin-get", help="GET /catalog/admin/items/{id} (включая неактивные)", parents=[common])
    p.add_argument("--item-id", type=int, required=True)
    p.set_defaults(handler=cmd_catalog_admin_get, command_name="catalog.admin-get")
    p = catalog_sub.add_parser("admin-search", help="GET /catalog/admin/items?search= (включая неактивные)", parents=[common])
    p.add_argument("--query", required=True)
    p.add_argument("--page", type=int, default=1)
    p.add_argument("--page-size", type=int, default=50)
    p.set_defaults(handler=cmd_catalog_admin_search, command_name="catalog.admin-search")
    p = catalog_sub.add_parser("update", help="PATCH /catalog/admin/items/{id} (только name/sku/description/hashtags)", parents=[common])
    p.add_argument("--item-id", type=int, required=True)
    p.add_argument("--input", help="Путь к JSON с полями для обновления (name, sku, description, hashtags)")
    p.set_defaults(handler=cmd_catalog_update, command_name="catalog.update")
    p = catalog_sub.add_parser("categories", help="GET /catalog/read/categories", parents=[common])
    p.add_argument("--query")
    p.add_argument("--page", type=int, default=1)
    p.add_argument("--page-size", type=int, default=20)
    p.set_defaults(handler=cmd_catalog_categories, command_name="catalog.categories")

    p_draft = sub.add_parser("draft", help="Черновики операций (только свои, без проведения)")
    draft_sub = p_draft.add_subparsers(dest="draft_cmd", required=True)
    p = draft_sub.add_parser("create", help="Создать черновик из JSON-файла", parents=[common])
    p.add_argument("--input", required=True, help="Путь к draft_request.json")
    p.add_argument("--client-request-id", help="Ключ идемпотентности (иначе генерируется)")
    p.set_defaults(handler=cmd_draft_create, command_name="draft.create")
    p = draft_sub.add_parser("get", help="Получить черновик", parents=[common])
    p.add_argument("--draft-id", required=True)
    p.set_defaults(handler=cmd_draft_get, command_name="draft.get")
    p = draft_sub.add_parser("list-own", help="Список своих операций", parents=[common])
    p.add_argument("--status", default="draft")
    p.add_argument("--site-id", type=int)
    p.add_argument("--page", type=int, default=1)
    p.add_argument("--page-size", type=int, default=50)
    p.set_defaults(handler=cmd_draft_list_own, command_name="draft.list-own")
    p = draft_sub.add_parser("add-lines", help="Добавить строки из JSON-файла", parents=[common])
    p.add_argument("--draft-id", required=True)
    p.add_argument("--input", required=True, help="Путь к extracted-lines.json")
    p.set_defaults(handler=cmd_draft_add_lines, command_name="draft.add-lines")
    p = draft_sub.add_parser("update-line", help="Изменить строку черновика", parents=[common])
    p.add_argument("--draft-id", required=True)
    p.add_argument("--line-number", type=int, required=True)
    p.add_argument("--qty")
    p.add_argument("--item-id", type=int)
    p.add_argument("--comment")
    p.add_argument("--batch")
    p.set_defaults(handler=cmd_draft_update_line, command_name="draft.update-line")
    p = draft_sub.add_parser("validate", help="Локальная валидация черновика", parents=[common])
    p.add_argument("--draft-id", required=True)
    p.set_defaults(handler=cmd_draft_validate, command_name="draft.validate")

    p_case = sub.add_parser("case", help="Локальное дело документа")
    case_sub = p_case.add_subparsers(dest="case_cmd", required=True)
    p = case_sub.add_parser("init", help="Создать дело (sha256, дедупликация)", parents=[common])
    p.add_argument("--file", required=True)
    p.add_argument("--cases-dir")
    p.set_defaults(handler=cmd_case_init, command_name="case.init")
    p = case_sub.add_parser("find", help="Найти дело по sha256", parents=[common])
    p.add_argument("--sha256", required=True)
    p.add_argument("--cases-dir")
    p.set_defaults(handler=cmd_case_find, command_name="case.find")
    p = case_sub.add_parser("set-state", help="Обновить состояние дела", parents=[common])
    p.add_argument("--case-id", required=True)
    p.add_argument("--state", required=True)
    p.add_argument("--draft-id")
    p.add_argument("--cases-dir")
    p.set_defaults(handler=cmd_case_set_state, command_name="case.set-state")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "handler") and getattr(args, "command_name", None) != "config.check":
        parser.error("команда не выбрана")
    return run_command(args)


if __name__ == "__main__":
    sys.exit(main())
