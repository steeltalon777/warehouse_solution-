# ERROR_HANDLING — форматы ошибок SyncServer и их маппинг

SyncServer использует **четыре** разных формата ошибок. Клиент
(`warehouse_api.py`, `map_error_response`) разбирает все и сохраняет
доменные коды сервера в `errors[].code`.

## Форматы сервера

### A. Канонический конверт (`SyncServerException`)

```json
{"error": {"code": "CONFLICT", "message": "cannot update operation with status submitted",
           "details": {...}}, "request_id": "..."}
```

Коды-константы: `VALIDATION_ERROR` (400), `UNAUTHORIZED` (401),
`FORBIDDEN` (403), `NOT_FOUND` (404), `CONFLICT` (409),
`RATE_LIMIT_EXCEEDED` (429), `INTERNAL_SERVER_ERROR` (500),
`HTTP_<status>` (fallback).

### B. Стандартный FastAPI `{"detail": "строка"}`

Самый частый формат: `{"detail": "invalid X-User-Token"}`,
`{"detail": "operation not found"}`, `{"detail": "catalog read access denied"}`.
Клиент маппит код из HTTP-статуса (401→`UNAUTHORIZED` и т.д.),
сообщение сохраняет.

### C. Доменные конфликты `{"detail": {"code", "message", ...}}` (409)

```json
{"detail": {"code": "source_document_idempotency_conflict",
            "message": "Source document conflict: source_ref 'sha256:...' was already used with a different payload"}}
```

Доменные коды (verbatim, сохраняются клиентом как есть):
`idempotency_payload_conflict`, `idempotency_key_conflict`,
`source_document_idempotency_conflict`,
`source_document_line_unresolvable`, `source_document_line_inactive`,
`source_document_line_deleted`, `catalog_item_unusable`.

### D. Pydantic 422

```json
{"detail": [{"loc": ["body", "lines", 0, "qty"], "msg": "Input should be greater than 0", "type": "greater_than"}]}
```

Клиент: `code=VALIDATION_ERROR`, `field="lines.0.qty"`, до 10 записей.

### Отдельно: OperationSubmitError (RFC7807-подобный)

`{"type", "title", "status", "code", "detail", "instance", "trace_id",
"errors": [...]}` с доменными кодами `insufficient_stock`,
`insufficient_issued_balance`, `stale_version`, `operation_in_wrong_state`,
`role_not_permitted`, `operation_not_found`. Скилл submit не вызывает —
формат задокументирован для полноты.

## Коды ошибок самого клиента

| code | Значение | exit |
|---|---|---|
| `CONFIG_MISSING` / `CONFIG_INVALID` | Нет base_url / битый URL | 2 |
| `TOKEN_MISSING` | Нет `SYNC_SERVER_USER_TOKEN` | 2 |
| `SECRETS_ACL_UNSAFE` | Небезопасный ACL файла секретов | 2 |
| `INSECURE_URL_FORBIDDEN` | HTTP вне localhost/частной сети или без флага | 2 |
| `ENDPOINT_NOT_ALLOWED` | Путь вне allowlist (submit/merge/admin/…) | 2 |
| `OPERATION_TYPE_NOT_ALLOWED` | ADJUSTMENT | 2 |
| `VALIDATION_ERROR` | Локальная валидация входных данных | 1/2 |
| `INPUT_NOT_FOUND` / `INPUT_INVALID_JSON` | Файл --input | 2 |
| `OPERATION_IN_WRONG_STATE` | Изменение не-draft операции | 1 |
| `INVALID_JSON` | Сервер вернул не-JSON | 1 |
| `DNS_ERROR` / `CONNECT_REFUSED` / `TIMEOUT` / `NETWORK_ERROR` | Сеть | 3 |

## Правила надёжности HTTP (реализовано в клиенте)

- connect timeout 5 c, read 30 c, write 30 c, pool 5 c.
- TLS: `verify=True` всегда; `verify=false` не поддерживается.
  HTTP разрешён только для localhost/частных IP при
  `SYNC_SERVER_ALLOW_INSECURE_LOCAL=true` (по умолчанию false).
- Автоповторы: только GET (идемпотентные), до 2 повторов при
  connect-ошибках и 502/503/504, backoff 0.5/1.5 c.
- POST/PATCH автоматически НЕ повторяются. Безопасный повтор —
  через тот же `client_request_id` / `source_ref` (дедуп на сервере).
- `X-Request-Id` генерируется на запрос; из ответа сохраняется в
  `envelope.request_id` для расследований.
- 401 и 403 обрабатываются раздельно (коды `UNAUTHORIZED`/`FORBIDDEN`).
- 409 — бизнес-конфликт: показать пользователю, не «переводить» в общую ошибку.
- 422 — ошибка данных: показать `field` и `msg`.
- HTTP 200 с непустым `errors` в теле → `ok=false`.

## Реакции агента на типовые ошибки

| Ошибка | Действие агента |
|---|---|
| `UNAUTHORIZED` | Сообщить: токен отклонён/истёк → обратиться к администратору за новым; НЕ переспрашивать токен у пользователя в чате |
| `FORBIDDEN` | Сообщить о нехватке прав (роль/площадка); не пытаться обойти |
| `NOT_FOUND` (draft/item) | Проверить id; предложить `draft list-own` |
| `source_document_idempotency_conflict` | Файл уже обработан с другим составом: показать существующий draft, спросить, что делать; новый draft молча не создавать |
| `idempotency_payload_conflict` | Ключ повторно использован с другим телом → сгенерировать новый `client_request_id` и показать предупреждение |
| `source_document_line_unresolvable` | Позиция недоступна → вернуть строку в unresolved, спросить замену |
| `stale_version` / 409 на PATCH | Перечитать draft (`draft get`), повторить изменение по свежей `version` |
| `TIMEOUT`/`CONNECT_REFUSED` | Сообщить о недоступности SyncServer, предложить повторить позже; не спамить повторами |
