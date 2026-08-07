# ADR-0025 — Доменные ошибки проведения операций: единый envelope

- Status: Accepted
- Date: 2026-07-31
- Deciders: architect, syncserver-lead, frontend-tech-lead
- Supersedes: частично — `corrections_service.py:912` остаётся в текущем виде (см. «Последствия»)
- Source TZ: `docs/TZ-SYNCSERVER_OPERATION_SUBMIT_DOMAIN_ERRORS.md`, `docs/TZ-FRONTEND_OPERATION_SUBMIT_ERROR_SURFACE.md`
- Scope: `.agent/SCOPE-operation-submit-domain-errors.md`

## Контекст

Кладовщик при подтверждении операции получает сырую серверную строку вида `insufficient stock for MOVE: inventory_subject=1655, source_site=1, required=2.000`. В строке нет ни имени ТМЦ, ни доступного остатка, ни стабильного идентификатора строки. Клиент не может надёжно подсветить проблемные позиции в таблице.

Аналогично сырыми строками возвращаются `stale_version`, `operation_in_wrong_state`, `role_not_permitted`. Прецедент структурированной ошибки уже есть: `operations_repo.py:207-212` использует `HTTPException(detail={code, message, current_version})`, `corrections_service.py:912` использует `{"code": "correction_insufficient_balance", ...}`. Но единого формата нет.

Подтверждённые факты репозитория (см. §«Подтверждённые факты репозитория» в TZ 1) показали:

* ключ баланса — `(site_id, inventory_subject_id)`, без `unit_id`;
* `operation.id` и `user_id` — UUID, `operation_line.id` — `BigInteger`, `version` — `int`;
* конкурентная защита уже реализована: `with_for_update()` в `balances_repo.py:23`, `operations_repo.py:161` + optimistic `expected_version` в `operations_repo.py:196, 240`;
* Django BFF **не пробрасывает** полный payload SyncServer в HTTP-ответ Angular — `catalog/api_views.py:_error` возвращает только `str(exc)`;
* `OperationsPolicy` и `OperationsWorkflowPolicy` используются только в `routes_operations.py`; каталог и временные ТМЦ не задевают;
* правила блокировки временных ТМЦ для MOVE/ISSUE в `Functional and WorkLogik.md:77-99` помечены как legacy и не действуют для новых операций (`creation_source ∈ {"source_document","manual"}`);
* `_ensure_sufficient_balance` в `operations_service.py:82-96` падает на первой строке с дефицитом — кладовщик видит только одну ошибку из пяти.

## Решение

### 0. Положения scope, отменённые разведкой

Разведка 2026-07-31 выявила, что следующие положения исходного scope (`.agent/SCOPE-operation-submit-domain-errors.md`) некорректны или преждевременны. Они **отменены** этим ADR, чтобы новые документы не унаследовали технический долг:

| Положение scope | Что было | Что выявила разведка | Что делаем |
| --- | --- | --- | --- |
| Ключ агрегации остатков | `(stock_site_id, item_id, unit_id)` | Таблица `balances` (`SyncServer/app/models/balance.py:12-33`) **не содержит `unit_id`**. Составной PK — `(site_id, inventory_subject_id)`. Единица — отображение через JOIN с `Item.unit_id` | Ключ агрегации — строго `(site_id, inventory_subject_id)`. `unit_id` не участвует в идентичности остатка, возвращается только как отображаемые данные |
| Правило «если одна строка отдельно превышает остаток, остальные не агрегируются» | В `§4.2 Агрегация одинаковых ТМЦ` scope | Неверно: если доступно 80, а строки требуют 90 и 20, общий дефицит = 110 против 80, и обе строки должны быть в ошибке | Отменено. Агрегируем всегда; одна ошибка = все строки группы с суммарным `required_qty` |
| `temporary_item_blocked` как код envelope | «Включён в первую итерацию» | `Functional and WorkLogik.md:77,80,88-89` помечает временные ТМЦ как legacy; для новых операций (`creation_source ∈ {source_document, manual}`) временные ТМЦ не создаются. Бизнес-правила блокировки MOVE/ISSUE для temporary_item не существует | Удалён полностью. Ни в контракте envelope, ни в моделях, ни в тестах, ни в UI. Никаких «зарезервированных» URN или статусов |
| `role_not_permitted` через общий submit-flow envelope с привязкой к строкам | «В scope submit-flow envelope» | `role_not_permitted` — это ошибка envelope-уровня без привязки к строкам; смешивать её с `insufficient_stock` в одной `errors[]` не нужно | `role_not_permitted` использует тот же envelope-формат (`type`, `code`, `errors[]`), но `errors[].scope = "operation"` без `item`/`stock_site`/`operation_line_ids`. Семантика HTTP-уровня остаётся отдельной (403), но **визуально** в UI обрабатывается в одном парсере |
| BFF — «пробросить как есть» | «Django BFF пробрасывает ответ как есть» | Текущий `Warehouse_web/apps/catalog/api_views.py:_error` отбрасывает `exc.payload` и возвращает только `str(exc)`. «Как есть» не получится — нужно менять BFF | BFF — полноценная часть TZ 1. Создаётся отдельный `api_error_response(exc)` helper, который применяется **только** к submit-flow BFF endpoint. Общий `_error` для catalog и других endpoints не меняется |
| Конкурентная защита — «усиление через раннюю блокировку операции» | «Блокировка `Operation` через `get_operation_by_id_for_update` в начале `submit_operation`» | Текущий `operations_repo.get_operation_by_id_for_update` уже вызывается в `submit_operation` репозитория (`operations_repo.py:242`); блокировка баланса (`balances_repo.py:23`) и optimistic `expected_version` (`operations_repo.py:196,240`) уже работают. Дополнительная блокировка не нужна | Текущая защита **переиспользуется как есть**. Добавляется только конкурентный интеграционный тест (§6.3 этого ADR и TZ 1 §13) |
| HTTP-статус для `temporary_item_blocked` (422 vs 409) | «Решается в TZ после проверки правила» | Правила нет | Отменено |

### 1. Единый envelope для всех submit-ошибок `POST /api/v1/operations/{id}/submit`

При любой доменной ошибке submit SyncServer возвращает Problem Details-подобный JSON:

```json
{
  "type": "urn:warehouse:problem:operation-submit-rejected",
  "title": "Операция не может быть проведена",
  "status": 409,
  "code": "operation_submit_rejected",
  "detail": "Исправьте отмеченные ошибки и повторите проведение.",
  "instance": "/api/v1/operations/123/submit",
  "trace_id": "01JXYZ...",
  "errors": [
    {
      "code": "insufficient_stock",
      "scope": "line_group",
      "operation_line_ids": [101, 104],
      "item": { "id": 17, "name": "Кабель ВВГ 3×2.5" },
      "stock_site": { "id": 2, "name": "Склад Чита" },
      "required_qty": "120.000",
      "available_qty": "80.000",
      "unit": { "id": 4, "name": "метр", "symbol": "м" }
    }
  ]
}
```

Решения по форме:

* `type` — URN вида `urn:warehouse:problem:<problem-class>`. Это соответствует RFC 7807/9457.
* `code` верхнего уровня — **класс ответа** (`operation_submit_rejected`, `operation_not_found`, `role_not_permitted`). Один и тот же строковый код не должен быть одновременно классом envelope и конкретной причиной.
* `errors[].code` — **конкретная причина отказа** (`insufficient_stock`, `stale_version`, `operation_in_wrong_state`).
* `errors[]` содержит **хотя бы одну запись** для известных доменных ошибок. `errors: []` допустим **только** для неизвестной ошибки, технического fallback и ответа старого сервера, который BFF не смог нормализовать.
* `errors[].operation_line_ids[]` — массив integer-ов (`operation_line.id`). Используется и для одной строки (`[line_id]`), и для агрегированной группы.
* `item`, `stock_site`, `unit` — объекты с `id` + `name` (для отображения). Идентификация только по `id`.
* `required_qty`, `available_qty` — **строка** (Decimal), не `float`.
* `trace_id` — необязательное поле. Если в request присутствует `X-Request-Id`, SyncServer пробрасывает его в envelope. Отдельная инфраструктура трассировки не создаётся.
* `instance` — путь submit-endpoint, для отладки.
* ID остаются канонических типов: UUID для `operation.id` / `user_id`, integer для `site_id` / `inventory_subject_id` / `item_id` / `line.id` / `version`. Никаких массовых преобразований в строки.

### 2. Коды `errors[]` первой итерации

| `errors[].code` | `scope` | HTTP | Обязательные поля |
| --- | --- | ---: | --- |
| `insufficient_stock` | `line_group` | 409 | `operation_line_ids[]`, `item`, `stock_site`, `required_qty`, `available_qty`; `unit` optional display-only |
| `insufficient_issued_balance` | `line_group` | 409 | `operation_line_ids[]`, `item`, `issue_object`, `required_qty`, `available_qty`; `unit` optional display-only |
| `stale_version` | `operation` | 409 | `expected_version`, `actual_version` |
| `operation_in_wrong_state` | `operation` | 409 | `current_state`, `allowed_states[]` |
| `role_not_permitted` | `operation` | 403 | только `code`, `scope` |
| `operation_not_found` | `operation` | 404 | только `code`, `scope` |

`temporary_item_blocked` **исключён** из первой итерации: правило в `Functional and WorkLogik.md` помечено как legacy (п. IV, статус 01.06.2026), для новых операций временные ТМЦ не создаются.

`role_not_permitted` оформляется через тот же envelope submit-flow, но **без** привязки к строкам (минимальный набор полей — только `code` и `scope`). Детальные поля (`actor_roles`, `required_permission`) **не включаются** в публичный API — они могут раскрывать внутреннюю модель доступа. Сервер пишет их в структурированный лог.

### 2.1. Семантика повторного submit

Повторный submit операции, которая больше не в DRAFT (SUBMITTED, ACCEPTED, CANCELLED), возвращает **`operation_in_wrong_state`** (409), **не** `stale_version`. `stale_version` возникает только когда операция остаётся в DRAFT, но была изменена другим запросом между загрузкой клиентом и submit'ом. Это правило **`state-before-version`** — единое для всех трёх документов и тестов.

Submit без `expected_version` пропускает только optimistic version check. Проверки состояния и прав **не** пропускаются.

### 2.2. Идентификация operation_line

`operation_line.id` — `BigInteger` autoincrement в Postgres. В JSON API он сериализуется как **integer** (стандартный JSON `Number`). Это работает корректно для текущих объёмов (`Number.MAX_SAFE_INTEGER = 2^53 - 1 ≈ 9e15`); BigInteger переполнит `Number.MAX_SAFE_INTEGER` только при ~9 квадриллионах строк, что не является практическим ограничением. Если в будущем потребуется — будет принят отдельный ADR с переходом на сериализацию строкой.

### 2.3. 403 vs 404

Сохраняется текущее поведение `OperationsPolicy`:

* `RoleNotPermittedError` 403 — пользователь не имеет operate-доступа или доступа к чужой операции;
* `OperationNotFoundError` 404 — операция не существует.

**Не вводится masking через 404** для случая «у пользователя нет доступа к существующей операции» — это отдельная задача, требующая решения о раскрытии информации и пересмотра всех авторизационных проверок.

### 3. Обратная совместимость через dual response

Существующие клиенты читают `detail` как строку. Чтобы не сломать никого:

* `detail` остаётся **строкой** и для нового envelope;
* полные машинные данные — в `errors[]`;
* для первой версии `detail` для `insufficient_stock` содержит понятное резюме: количество проблемных групп и первая проблема («Недостаточно товара: Кабель ВВГ 3×2.5 — запрошено 120, на складе 80»);
* `HTTPException(detail=dict)` запрещён — это сломает всех потребителей, которые ожидают строку. Используется собственный exception handler, который собирает envelope из доменного исключения и регистрируется в FastAPI app.

Сокращение или удаление `detail` запрещено без отдельного ADR.

### 4. Архитектура exception flow

```
OperationsPolicy.require_*           ┐
OperationsWorkflowPolicy.require_*   │  → доменные подклассы OperationSubmitError
_ensure_sufficient_balance           │     (InsufficientStockError, StaleVersionError, …)
_ensure_sufficient_issued_balance    │
                                     ↓
                              FastAPI exception handler
                                     ↓
                              Problem envelope (JSON)
```

Сервисный слой не знает про HTTP и не формирует JSON. HTTP-слой маппит доменные исключения в envelope.

`HTTPException` остаётся для **не-submit ошибок** и для других endpoints (`routes_documents.py`, `routes_admin_*`). Только submit-endpoint и его сервисные пути переходят на новый маппер.

### 5. Агрегированная проверка остатков

Сервис `OperationsService.submit_operation` собирает все расходующие строки операции, группирует **строго** по `(site_id, inventory_subject_id)` для warehouse или по `(issue_object_id, inventory_subject_id)` для issued. `unit_id` **не участвует** в ключе агрегации (отменённое положение scope, см. §0): баланс идентифицируется парой `site_id + inventory_subject_id`, единица — отображаемое поле, а не часть идентичности.

Алгоритм — **двухфазный** (см. TZ 1 §5):

* Фаза 1 — один проход по строкам операции, определение реальных расходующих эффектов. Положительные ADJUSTMENT и RECEIVE не участвуют в проверке.
* Фаза 2 — глобальная сортировка уникальных ключей балансов `sorted_keys = sorted(dict.keys())`. Для каждого ключа **ровно один** `get_for_update`. Сравнение суммарного расхода с `available_qty` (прочитанным внутри блокировки).
* Сбор всех дефицитных групп.
* **Один** доменный `InsufficientStockError` / `InsufficientIssuedBalanceError` со всеми дефицитами.
* Порядок возврата — по `line_number` первой строки группы, **не** зависит от порядка блокировок или ответа БД.

Правила:

* агрегация — **только** в пределах одного ключа баланса `(site_id, inventory_subject_id)`;
* строки с разными `inventory_subject_id` уже учтены раздельно — это норма;
* `get_for_update` вызывается ровно один раз на уникальный ключ, не на каждую строку;
* если в группе одна строка уже отдельно превышает остаток, остальные строки группы **тоже агрегируются** — общий дефицит = сумма `required_qty` всех строк группы (отменённое правило scope, см. §0);
* `operation_line_ids` в `StockDeficit` — `[line.id for line in group]` в порядке `line.line_number` ascending;
* группы в итоговом `deficits[]` упорядочены по позиции первой строки в операции;
* `available_qty` читается **после получения блокировки `with_for_update`** на строке `balances`, в той же транзакции, в которой будет выполняться проведение (чтение вне блокировки недопустимо — это путь к ложному «всё ок» при параллельном списании);
* глобальная сортировка ключей исключает deadlock при параллельных submit, расходующих пересекающиеся группы балансов.

### 6. Конкурентная защита (без изменений в механизме)

Текущий код уже защищён:

* row-level lock баланса через `with_for_update()` в `balances_repo.py:23-30`;
* row-level lock операции через `with_for_update()` в `operations_repo.py:156-174` (используется в `submit_operation` репозитория, `operations_repo.py:242`);
* optimistic `expected_version` в `operations_repo.py:196-203` (`update_operation`) и `operations_repo.py:240-256` (`submit_operation`).

Этого достаточно для single-instance SyncServer. **Никаких дополнительных блокировок в этой итерации не вводится** (отменённое положение scope, см. §0).

Что добавляется в TZ 1 — только **наблюдаемость** существующей защиты:

* интеграционный тест двух конкурентных submit на одну операцию с одинаковым `expected_version`: через блокировку операции и проверку версии только один проходит, второй получает `stale_version` 409;
* интеграционный тест двух конкурентных submit с расходом одного остатка: через блокировку баланса только один проходит, второй получает `insufficient_stock` 409.

Уровни изоляции, `SELECT ... FOR UPDATE NOWAIT`, advisory locks, retry-механизм — **не** вводятся в первой итерации.

### 7. Порядок проверок

Жёсткий авторитетный порядок (см. TZ 1 §7.1), который нельзя нарушать:

1. аутентификация;
2. первичная безопасная загрузка `Operation` (read-only) для авторизации до взятия блокировки;
3. первичная авторизация (`require_operation_submit_permission`, для MOVE — `require_move_access`);
4. **внутри транзакции — взятие блокировки `Operation`** через существующий `get_operation_by_id_for_update`;
5. авторитетная проверка **состояния** заблокированной операции → `OperationInWrongStateError`;
6. авторитетная проверка `expected_version` заблокированной операции → `StaleVersionError` (пропускается только если `expected_version` не передан);
7. авторитетная повторная проверка прав, если они зависят от изменяемых полей;
8. валидация строк;
9. **двухфазная группировка и блокировка балансов** с глобальной сортировкой ключей;
10. если есть дефициты — одно `InsufficientStockError` / `InsufficientIssuedBalanceError`;
11. атомарное проведение в одной транзакции.

**`state-before-version`**: проверка состояния выполняется **до** проверки версии. Это значит:

* повторный submit уже проведённой операции → `OperationInWrongStateError` (не `StaleVersionError`);
* `StaleVersionError` возникает только если операция остаётся в DRAFT, но была изменена другим запросом.

Это правило — единое для всех трёх документов (ADR, TZ 1, TZ 2) и concurrency-тестов.

**Новая разновидность блокировки не вводится.** Существующий механизм `with_for_update()` переиспользуется, но авторитетные проверки выполняются по заблокированной операции.

### 8. Django BFF

`Warehouse_web/apps/sync_client/client.py:_raise_for_response` уже сохраняет полный payload SyncServer в `exc.payload` — структура envelope доступна через `exc.payload["errors"]`, `exc.payload["code"]`, `exc.payload["trace_id"]`. Это **не меняется**.

Текущие BFF endpoints (`Warehouse_web/apps/catalog/api_views.py:_error`, `Warehouse_web/apps/bff_api/operations_views.py`) используют helper `_error(str(exc), "sync_error", status=...)`, который отбрасывает `exc.payload` и возвращает только строку. Это **не работает для нового envelope** — клиенту нужны `errors[]`, `code`, `trace_id`.

Решение: создаётся **отдельный** helper `api_error_response(exc)` в `Warehouse_web/apps/sync_client/api_error_response.py`:

* если `exc.payload` — JSON object/dict → возвращает его целиком с HTTP-статусом из `exc.status_code`;
* если `exc.payload` — `None`, строка, список или иной не-dict → возвращает fallback envelope `{"type": "urn:warehouse:problem:sync-error", "title": "Ошибка взаимодействия с сервером", "status": 502, "code": "sync_error", "detail": str(exc), "errors": []}`;
* `exc.status_code` валидируется: если не в `[400..599]` — fallback на 502;
* payload уже прошёл `sanitize_payload` в `client.py`; повторная санитизация не выполняется.

Helper применяется **только** к submit-flow BFF endpoint (`submit_operation_view`). Все остальные BFF endpoints остаются на `_error` и не затрагиваются этой итерацией — изменение `_error` задним числом сломало бы контракт каталога и других доменов.

> **ADR-0027 (cancel-flow):** Helper `api_error_response(exc)` применяется к submit-flow и cancel-flow BFF endpoints (`OperationSubmitView`, `OperationCancelView`). Все остальные BFF endpoints остаются на `_handle_sync_error` и не затрагиваются этой итерацией.

### 9. Что не делается в этой итерации

* `corrections_service.py:912` (`correction_insufficient_balance`) — оставляем как есть. Это другой flow (корректировки), миграция на тот же envelope — отдельный ADR.
* Нормализация остальных API-ошибок (auth, validation, 5xx).
* Offline-клиенты (`Warehouse_client_core` и т.д.) — формат оптимизирован под текущий Django+Angular стек.
* Client-side precheck остатков — оптимизация UX, отдельная задача.
* Bulk-validate endpoint — отдельная задача.

## Отклонённые альтернативы

* **`HTTPException(detail=dict)` с полным envelope в `detail`** — отклонено: ломает всех потребителей, которые ожидают `detail` как строку (`Warehouse_web/apps/client/services.py:58,76` используют `str(exc)`).
* **Только улучшить текст f-строки** — отклонено: не решает агрегацию, не даёт клиенту стабильный `operation_line_id` для inline-подсветки.
* **Precheck endpoint `POST /operations/{id}/validate`** — отложено: решает только UX, не закрывает race conditions и server-side reject.
* **Один `code` для envelope и для причины** — отклонено: смешивает класс ответа и причину, не даёт клиенту одной точкой ветвления.
* **`type` как короткий slug `"operation_submit_rejected"`** — отклонено: не соответствует RFC 7807/9457, где `type` — URI/URN.
* **Переписывать `OperationsPolicy` / `OperationsWorkflowPolicy` на общий envelope для всех API** — отклонено: эти модули используются только операциями, расширять scope не нужно.
* **`actor_roles` / `required_permission` в публичном API** — отклонено: раскрывает внутреннюю модель доступа.

## Последствия

Положительные:

* кладовщик видит имя ТМЦ, доступный остаток, агрегированные дефициты;
* клиент получает стабильный ключ `operation_line_ids` для inline-подсветки и для очистки группы при изменении одной строки;
* один формат envelope покрывает `insufficient_stock`, `stale_version`, `operation_in_wrong_state`, `operation_not_found`, `role_not_permitted`;
* существующие клиенты и curl продолжают работать благодаря dual response;
* тесты на race conditions закрывают реальный класс багов.

Отрицательные и риски:

* расширение публичного контракта `/api/v1/operations/{id}/submit` — формально breaking change без dual response. С dual response риск минимален;
* добавление `trace_id` требует аккуратного обращения с PII (UUID операции в логах);
* изменение `_ensure_sufficient_balance` (с раннего возврата на сбор всех дефицитов) затрагивает sensitive area `operations_service.py`;
* BFF endpoints, которые сейчас возвращают только `str(exc)`, требуют замены шаблона ответа;
* в envelope приходит больше данных, чем раньше — нужен redaction на стороне BFF (уже есть `sanitize_payload` в `client.py:20`).

Миграция:

* Этап 1 (TZ 1 + TZ 2): сервер возвращает новый envelope параллельно со строкой `detail`. Angular переходит на парсер envelope. Все остальные клиенты не меняются.
* Этап 2 (отдельный TZ, не в этой итерации): миграция `corrections_service.py:912` на тот же envelope. Возможно, сокращение `detail` для submit-ошибок.

## Ссылки

* `docs/TZ-SYNCSERVER_OPERATION_SUBMIT_DOMAIN_ERRORS.md` — реализация envelope, exception handler, агрегация, тесты.
* `docs/TZ-FRONTEND_OPERATION_SUBMIT_ERROR_SURFACE.md` — реализация parser, inline-подсветки, toast, a11y.
* `.agent/SCOPE-operation-submit-domain-errors.md` — scope-основа.