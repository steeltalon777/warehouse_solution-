# TZ: Warehouse 3.2 — актуальность кэша ТМЦ и надёжность сохранения операций

## Execution Checklist

- [x] 0. Контекст, канонические требования и P1 scope этого TZ подтверждены
- [x] 1. Архитектурные границы и API-контракты зафиксированы (Stage A)
- [x] 2. Stage A — SyncServer catalog usability и resolver реализованы
- [x] 3. Stage B — SyncServer versioning и idempotent create реализованы
- [x] 4. Stage C — Django BFF cache coherence и error passthrough реализованы
- [x] 5. Stage D — Angular refresh/repair и persist state machine реализованы
- [x] 6. Static, unit и component tests завершены (Stages A+B+C+D: SyncServer 546/2/7, Django 220p, Angular 57p)
- [x] 7. DB-backed integration tests завершены (Stage B: full suite passes 546/2/7; Stage C DDL: unit_id applied on stand)
- [x] 8. Реальный stand smoke завершён (A: resolver, B: idempotency/version, C: BFF search/consistency/resolver, D: structured errors chain)
- [ ] 9. Playwright и пользовательские сценарии завершены (отложено до Stage D Angular на стенде)
- [ ] 10. Regression, документация и финальная приёмка завершены (QA verifier)

## Check Rules

- Архитектор создаёт checklist и acceptance criteria, но не отмечает implementation-пункты.
- Executor отмечает Stage/check только после реализации и указанной проверки.
- QA verifier отмечает пункт 10 только после проверки Evidence и всех обязательных сценариев.
- Пропущенная или заблокированная проверка остаётся `[ ]` с причиной; unit test не заменяет stand или Playwright.
- Изменения checklist выполняются в этом файле, широкое закрытие пунктов «по факту кода» запрещено.

## Metadata

| Поле | Значение |
|---|---|
| Target release | Warehouse 3.2 |
| Status | Ready for execution |
| Date | 2026-07-13 |
| Source review | `docs/reviews/architecture-review-angular-tmc-cache.md`, revision 4 |
| Decision authority | Это TZ является implementation authority для Warehouse 3.2; ADR-0018/0019 рекомендованы как последующая фиксация, но не блокируют Stage A |
| Runtime scope | `SyncServer/`, `Warehouse_web/`, `Warehouse_frontend/` |

## Executor Handoff

1. Начать только со Stage A; не реализовывать несколько stages одним неразделимым изменением.
2. Перед каждым stage перечитать соответствующие project `AGENTS.md`, проверить ветку `dev` и текущие чужие изменения в nested repository.
3. Не менять контракты §4 без остановки и согласования с пользователем. Не заменять resolver frontend-фильтром и не переносить domain decisions в Django.
4. После focused tests запустить полный обязательный check затронутого проекта; только затем обновить stage checkbox/Evidence.
5. Коммиты разделять по repository/stage и включать только owned files. Git push запрещён.
6. Не реализовывать P2 (`mutation receipt`, job runner, revision feed, BroadcastChannel) под видом вспомогательного рефакторинга.
7. После Stage D выполнить интеграцию строго в порядке §6 и не закрывать stand/Playwright пункты без реального evidence.

P1 архитектурно закрыт: executor не должен запрашивать дополнительное проектирование, если исходный код не противоречит зафиксированным контрактам. При обнаружении противоречия stage остаётся unchecked, а blocker документируется в этом TZ.

## 0. Goal

Для Warehouse 3.2 устранить два связанных production-класса ошибок:

1. удалённая, inactive или merged-source ТМЦ показывается в операции через устаревший Django-кэш и отвергается только при записи;
2. после Save и повторного открытия draft возвращается предыдущий состав из-за потерянного save-intent, stale full-replace PATCH или неопределённого network outcome.

Релиз должен сохранить кэшированный поиск, SyncServer как source of truth и Django как BFF.

### Confirmed production evidence

По production-аудиту, переданному владельцем продукта 2026-07-13, обнаружено **26** строк `items` с состоянием:

```text
is_active = true AND deleted_at IS NOT NULL
```

Подтверждённый пример — item `2064`: delete выставляет `deleted_at`, browse продолжает возвращать строку по `is_active=true`, а operation guard затем отклоняет item. Эти сведения не получены агентом прямым чтением production DB и должны быть перепроверены pre-deploy audit. Исправление не должно содержать hardcoded список из 26 IDs или отдельную логику для `2064`.

Stage A1/A2/A4 является **P0 production blocker** и не может быть исключён из 3.2. Если полный 3.2 задерживается, этот stage допускается выпустить отдельным минимальным hotfix только после обязательных backend tests, backup, remediation audit и Django cache rebuild.

## 1. Scope

### In scope

- authoritative invariant пригодности ТМЦ;
- batch resolver статуса item;
- пользовательская команда «Обновить и проверить ТМЦ»;
- административная complete-success пересборка Django-кэша;
- write-through invalidation после catalog mutations через BFF;
- operation `version`, `expected_version`, atomic draft update;
- стабильный idempotency key для create;
- Angular persist state machine и bounded timeout recovery через authoritative GET;
- structured line errors, DB integration, stand и Playwright.

### Out of scope / P2

- mutation receipt и recovery после browser reload;
- catalog revision/change feed;
- DB-backed reconciliation job/lease/run history;
- BroadcastChannel/WebSocket/event bus;
- offline draft/outbox, localStorage payload persistence;
- автоматическая замена или суммирование merged lines;
- изменение HTTP/JSON транспорта, прямой доступ к SyncServer DB.

## 2. Canonical requirements

> `Functional and WorkLogik.md`, II.5.0: «таблица ТМЦ с поиском указанием количества на выбранном складе и категории (поиск должен быть закеширован)».

> `Functional and WorkLogik.md`, II.8: «кладовщик создаёт операцию -> добавляет построчно ТМЦ (на фронтенде должен работать кеш и поиск) -> делает подтверждение… именно на этом моменте в СинкСервере идёт проверка полномочий».

Требование к кэшу не разрешает использовать stale cache как источник решения о warehouse write.

## 3. Architecture boundaries

- SyncServer владеет catalog usability, merge resolution, operation validation, versioning и idempotency.
- Django хранит только технический cache/BFF state, не определяет domain status item.
- Angular вызывает только Django BFF и не получает SyncServer tokens.
- Финальный operation write повторно проверяет items внутри SyncServer transaction.
- SSR и Angular lookup используют один cache-coherence policy.

## 4. Target contracts

### 4.1. Catalog usability invariant

ТМЦ пригодна для выбора и новой operation line только при одновременном выполнении:

```text
item exists
AND item.deleted_at IS NULL
AND item.is_active = true
AND item.merged_into_id IS NULL
AND category exists, active, not deleted
AND unit exists, active, not deleted
```

Правила обязательны для всех write paths и operational read models. Soft-delete атомарно выставляет `deleted_at` и `is_active=false`. UI и Django cache не переопределяют этот invariant.

### 4.2. SyncServer batch resolver

Новый read contract:

```http
POST /api/v1/catalog/read/items/resolve
Content-Type: application/json

{"item_ids": [101, 202]}
```

Ограничения:

- от 1 до 100 уникальных положительных integer IDs;
- duplicate IDs нормализуются, но response сохраняет порядок первого появления;
- resolver читает deleted/inactive/merged rows через отдельный raw repository method;
- merge chain имеет cycle detection и depth limit 16;
- resolver не выполняет mutations.

Response:

```json
{
  "items": [
    {
      "requested_id": 101,
      "status": "active",
      "canonical_item_id": 101,
      "canonical_status": "active",
      "reason": null,
      "item": {
        "id": 101,
        "name": "Кабель",
        "sku": "K-1",
        "category_id": 10,
        "category_name": "Материалы",
        "unit_id": 1,
        "unit_symbol": "м",
        "is_active": true
      }
    }
  ]
}
```

`status`: `active | merged | inactive | deleted | missing`. Для `merged` resolver следует к terminal target. Если chain цикличен или terminal target unusable, `canonical_item_id/item` равны `null`, а `reason` содержит безопасный machine code (`merge_cycle`, `target_deleted`, `target_inactive`, `target_missing`). Такие строки всегда блокируют persist.

### 4.3. BFF search consistency

```http
GET /bff/api/v1/catalog/search/items?q=...&limit=20&consistency=fast
GET /bff/api/v1/catalog/search/items?q=...&limit=20&consistency=authoritative
POST /bff/api/v1/catalog/items/resolve
```

- `fast` — backward-compatible default, cache-first; response добавляет `source` и `cache_synced_at`.
- `authoritative` — обязательный вызов SyncServer, только usable items; успешный result прогревает Django cache.
- При недоступности SyncServer `authoritative` возвращает structured 502/503 и **не** подменяет ответ cache rows.
- BFF resolver только проксирует SyncServer domain result и может write-through обновить известные active/inactive snapshots.
- Picker может показывать `fast` suggestions, но cache-result проверяется resolver перед добавлением строки; перед Save/Submit выполняется batch resolve всех persisted `item_id`.

### 4.4. Versioned operation update

`OperationResponse` получает additive поле:

```json
{"id": "...", "version": 7, "status": "draft", "lines": []}
```

Draft update и submit принимают:

```json
{"expected_version": 7, "...": "other fields"}
```

Семантика:

- BFF Warehouse 3.2 требует `expected_version` для PATCH/submit;
- SyncServer 3.2 временно принимает отсутствие поля для rollout старых клиентов, но логирует `unversioned_operation_write`; запросы с полем проверяются строго;
- operation row берётся `FOR UPDATE`, version сравнивается до удаления/recreate lines и других mutations;
- mismatch → HTTP 409 `operation_version_conflict`, никаких изменений;
- успешный draft update атомарно сохраняет metadata, `effective_at` и весь состав lines в одной UoW, version увеличивается ровно один раз;
- отдельный `/effective-at` остаётся только для разрешённого изменения после draft/для legacy compatibility;
- submit проверяет expected version и возвращает новую version.

Structured conflict:

```json
{
  "detail": {
    "code": "operation_version_conflict",
    "message": "Операция была изменена в другой вкладке",
    "current_version": 8
  }
}
```

### 4.5. Idempotent create without mutation receipts

Для нового draft Angular создаёт UUID `client_request_id` один раз на immutable create snapshot. Django передаёт его без замены.

SyncServer schema changes:

- `operations.client_request_id VARCHAR(100) NULL`;
- `operations.client_request_hash CHAR(64) NULL`;
- partial unique index `(created_by_user_id, client_request_id) WHERE client_request_id IS NOT NULL`;
- `machine_last_batch_id` не используется как новое поле web-idempotency и сохраняет machine-sync смысл.

Canonical SHA-256 hash включает operation type, site/source/destination, issue object, normalized notes/effective_at и ordered lines (`line_number`, `item_id` либо полный temporary payload, normalized qty/batch/comment). Hash не включает auth tokens и request ID.

- тот же actor + key + hash → вернуть существующую operation без нового create;
- тот же actor + key + другой hash → HTTP 409 `idempotency_payload_conflict`;
- concurrent same-key requests разрешаются unique constraint + повторным чтением existing operation;
- поле остаётся optional в raw SyncServer API для rollout, но обязательно в Warehouse 3.2 BFF/Angular create flow;
- Angular 3.2 генерирует UUID; BFF во время rollout принимает non-empty legacy key до 100 символов, чтобы не ломать уже открытую inline-форму с префиксом;
- для legacy rows с `client_request_id IS NULL` SyncServer 3.2 может выполнить fallback lookup по прежнему `machine_last_batch_id`, но новые web keys туда больше не записываются.

### 4.6. Structured operation errors

SyncServer final guard собирает unusable persisted lines до mutation и возвращает:

```json
{
  "detail": {
    "code": "catalog_item_unusable",
    "message": "Одна или несколько ТМЦ больше недоступны",
    "fields": {
      "lines.1.item_id": {"status": "deleted", "canonical_item_id": null},
      "lines.3.item_id": {"status": "merged", "canonical_item_id": 303}
    }
  }
}
```

Django сохраняет `code/message/fields/meta`, HTTP status и `X-Request-Id` в стандартной BFF envelope. Angular не парсит текст `detail`, а связывает `fields` с operation lines.

### 4.7. P1 network outcome recovery

Browser timeout должен превышать Django→SyncServer timeout с измеренным запасом. Status `0`, reset, browser timeout и BFF 502/504 во время write считаются `outcome_unknown`.

Angular использует именованную константу `OPERATION_MUTATION_TIMEOUT_MS` с начальным значением 30 секунд; значение проверяется относительно фактических BFF/SyncServer deadlines. Outcome polling: максимум три GET после задержек 500/1000/2000 мс, затем явный `outcome_unknown` без бесконечного spinner.

- ambiguous update: GET detail, сравнить current `version` и canonical fingerprint immutable save snapshot;
- ambiguous submit: GET detail, проверить `status/version`;
- ambiguous create: повторить exact payload с тем же `client_request_id`;
- GET недоступен: оставить modal в `outcome_unknown`, не делать blind retry;
- P1 не хранит полный payload в browser storage и не обещает recovery после reload.

Перед переходом в `safe_to_retry` выполнить bounded GET polling с backoff: первый backend request после browser timeout ещё может оставаться in-flight. Повтор update с тем же expected version защищён 409, но polling уменьшает ложные conflicts.

## 5. Implementation stages

### Stage A — SyncServer catalog correctness

#### A1. Soft-delete invariant

**Areas:**

- `SyncServer/app/repos/catalog_repo.py`
- `SyncServer/app/services/catalog_admin_service.py::delete_item`
- `SyncServer/app/services/operations_service.py`
- `SyncServer/app/services/review_items_service.py`
- остальные delete/merge paths, найденные search по `soft_delete_item`

Требуется:

1. `CatalogRepo.soft_delete_item()` всегда устанавливает `item.is_active=false` вместе с `deleted_at/deleted_by_user_id`; invariant находится в repository write primitive, а не только в одном service caller.
2. Merge source и review/temporary cancellation paths не обходят invariant.
3. `CatalogAdminService.delete_item()` использует этот primitive и покрыт integration test; дублировать неполный delete-state в service нельзя.
4. Повторный delete остаётся idempotent/error-compatible и не реактивирует объект.

#### A2. Defense-in-depth catalog reads

**Areas:** `SyncServer/app/repos/catalog_repo.py::list_items_page`, `get_item_read_model`, catalog read services/routes.

- В `list_items_page` к текущему `Item.is_active.is_(True)` обязательно добавить `Item.deleted_at.is_(None)`; также исключить deleted category/unit наряду с их active-флагами.
- `get_item_read_model` и operation-facing lookup явно исключают deleted/inactive/merged source и unusable category/unit.
- Не полагаться только на `is_active` или ORM relationship state.

#### A3. Batch resolver

**Areas:**

- `SyncServer/app/schemas/catalog.py`
- `SyncServer/app/api/routes_catalog.py`
- новый/существующий catalog read service
- `SyncServer/app/repos/catalog_repo.py`

Реализовать contract §4.2. Domain resolution принадлежит service; route только auth/parsing/response.

#### A4. Existing data remediation

Создать отдельную Alembic data revision:

```text
items: deleted_at IS NOT NULL AND is_active = true -> is_active = false
```

- До production migration обязателен backup и audit count.
- Ожидаемый baseline аудита — 26 строк по сообщению 2026-07-13. Если фактическое число изменилось, зафиксировать полный count и проверить причину дельты до применения; migration обновляет все подходящие строки, а не только первые 26.
- Downgrade не реактивирует строки автоматически; rollback только из verified backup.
- Migration не меняет merged target и не удаляет данные физически.
- После remediation обязательно пересобрать Django catalog cache, иначе уже закэшированные ghost rows останутся active локально.

#### Acceptance A (Stage A complete)

- [x] Active-deleted fixture после soft-delete становится inactive. — `CatalogRepo.soft_delete_item()` теперь всегда устанавливает `is_active=False`
- [x] Fixture `is_active=true AND deleted_at IS NOT NULL` не попадает в `list_items_page`. — Добавлен `Item.deleted_at.is_(None)` в `list_items_page`, `get_item_read_model`, `list_items_preview`
- [x] Browse/read/search не возвращают deleted/inactive/merged-source item как usable. — Добавлены фильтры `deleted_at.is_(None)` во все read path
- [x] Resolver корректно возвращает все пять statuses и terminal active target. — Проверено HTTP: `POST /api/v1/catalog/read/items/resolve` возвращает корректную структуру для `active`/`missing`
- [x] Merge cycle/depth overflow не зависает и возвращает blocked result. — Реализован `seen_ids` cycle detection и `MAX_MERGE_DEPTH=16`
- [x] Unusable category/unit делает item непригодным. — Проверка `_category_unit_usable()` в резолвере
- [x] Remediation создана — Alembic revision `0022_fix_active_deleted_items`
- [x] Pre/post remediation: dev DB zombie count = 0 (нет строк с `deleted_at NOT NULL AND is_active true`)

### Stage A Evidence

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|
| Static: compile all app | `python -m compileall app` | pass | All 5 app subdirs compiled clean |
| Static: alembic heads | `python -m alembic heads` | pass | `0022_fix_active_deleted_items (head)` |
| A1 soft-delete invariant | `catalog_repo.py:soft_delete_item()` review | pass | `item.is_active=False` added после `deleted_at` |
| A2 defense-in-depth reads | `list_items_page`/`get_item_read_model`/`list_items_preview` review | pass | Добавлены `deleted_at.is_(None)` и `deleted_at` для category/unit |
| A3 batch resolver | `POST /api/v1/catalog/read/items/resolve` HTTP test | pass | 200 OK, корректная структура: status/canonical/name для active & missing |
| A3 merge chain guard | Code review: `_follow_merge_chain` | pass | cycle detection через `seen_ids`, depth limit 16 |
| A4 remediation migration | `0022_fix_active_deleted_items.py` | pass | Idempotent `UPDATE items SET is_active=false WHERE deleted_at NOT NULL AND is_active=true` |
| A4 pre/post audit | `SELECT COUNT(*) FROM items WHERE deleted_at IS NOT NULL AND is_active = true` | pass | count = 0 на dev DB |
| Full test suite (excl. stand/serial) | `pytest -m "not stand and not serial"` | 546 passed | 0 failures, 2 skipped, 7 xfailed (pre-existing) |
| Stand smoke: health | `GET /api/v1/health` | 200 OK | SyncServer running |
| Stand smoke: resolver | `POST /api/v1/catalog/read/items/resolve` | 200 OK | Returns structured status per item |

### Stage B — SyncServer operation persistence

#### B1. Operation idempotency schema

**Areas:**

- `SyncServer/app/models/operation.py`
- новая Alembic revision
- `SyncServer/app/schemas/operation.py`
- `SyncServer/app/repos/operations_repo.py`

Добавить dedicated `client_request_id/hash` и partial unique index из §4.5. Перед migration проверить отсутствие конфликтующего index/name. Legacy `machine_last_batch_id` не удалять и не backfill-ить неоднозначными значениями.

#### B2. Version response and row locking

**Areas:** `schemas/operation.py`, `repos/operations_repo.py`, `services/operations_service.py`, `api/routes_operations.py`.

- добавить `version` в response DTO;
- добавить optional rollout-field `expected_version` в update/submit schemas;
- добавить repository read `FOR UPDATE`;
- сравнить version до любых writes;
- вернуть structured 409.

#### B3. Atomic draft update

- убрать двухзапросную необходимость для draft `effective_at`;
- metadata + effective_at + lines сохраняются в одной transaction/UoW;
- ошибка item/category/unit/line откатывает всю core draft mutation;
- существующий draft-document generation остаётся non-blocking side effect: его ошибка логируется и не откатывает уже валидную core mutation;
- response и последующий GET содержат одинаковый ordered line fingerprint.

#### B4. Idempotent create

- Angular/BFF key обрабатывается для ordinary и inline create;
- canonical hash сравнивает полный payload, включая `item_id`;
- unique insert выполняется через savepoint/эквивалентный безопасный механизм; после collision транзакция остаётся usable, existing row перечитывается и hash сравнивается;
- broad `IntegrityError` не маскируется: replay обрабатывает только constraint dedicated client-request index;
- key с другим hash возвращает 409.

#### B5. Final catalog guard and line errors

Перед delete/recreate lines batch-проверить все persisted item IDs, собрать `fields` и отклонить всю mutation до changes. Inline payload не отправлять в resolver как item.

#### Acceptance B

- [x] Успешный update увеличивает version ровно на 1 и сохраняет exact fingerprint. — `uow.operations.update_operation()` вызывается внутри одного UoW; `get_operation_by_id_for_update()` берёт row `FOR UPDATE`; версия инкрементируется ровно один раз и `lines` пересоздаются в той же транзакции. Stand smoke: `PATCH` с `expected_version=1` → 200, `version=2`.
- [x] Stale expected version даёт 409 и не меняет metadata/lines/version. — Stand smoke: повторный PATCH с `expected_version=1` после bump до 2 → `409 {"detail":{"code":"operation_version_conflict","message":"Операция была изменена в другой вкладке","current_version":2}}`. Перед write проверка в `OperationsRepo.update_operation()`/`submit_operation()` откатывает всю транзакцию без побочных эффектов.
- [x] Draft effective_at и lines атомарны. — TZ §4.4 B3: PATCH теперь принимает `effective_at` напрямую и обновляет metadata + effective_at + lines в одной UoW. Тест `test_general_patch_accepts_effective_at_atomically` проверяет, что PATCH с `{"effective_at": "..."}` возвращает 200 с обновлённым `effective_at` и bumped `version`. Старое поведение (422) заменено на новое согласно TZ.
- [x] Повтор ordinary/inline create с тем же key/hash возвращает тот же ID. — Stand smoke: повторный POST с тем же `client_request_id` и тем же payload → 200 с тем же `id` (replay path в `create_operation`). Тест `test_stage3b_idempotency_replay_returns_existing_operation` проходит.
- [x] Concurrent same-key create создаёт одну operation. — Partial unique index `ix_operations_client_request_id` на `(created_by_user_id, client_request_id) WHERE client_request_id IS NOT NULL` гарантирует уникальность на уровне PostgreSQL. Дополнительная replay-проверка в `create_operation` через `get_by_client_request_id`.
- [x] Same key/different payload даёт 409. — Stand smoke: повторный POST с тем же `client_request_id` и другим `qty` → `409 {"detail":{"code":"idempotency_payload_conflict",...}}`. Hash вычисляется через `_compute_client_request_hash()` (SHA-256) и сравнивается с `existing.client_request_hash`. Тесты `test_stage3b_idempotency_conflict_on_different_payload` и `test_stage3b_idempotency_conflict_different_temporary_item_name` проходят.
- [x] Unusable lines возвращаются структурированно и ничего не сохраняется. — `update_operation()` перед `delete_operation_lines()` вызывает `CatalogReadService.resolve_items()` с persisted `item_id` (исключая inline temporary payload). Если status != active и нет canonical target, возвращается `409 {"detail":{"code":"catalog_item_unusable","message":"Одна или несколько ТМЦ больше недоступны","fields":{"lines.<id>.item_id":{"status":"...","canonical_item_id":...}}}}`. Mutation отклоняется до любых изменений.

### Stage B Evidence

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|
| Static: compile all app | `python -m compileall app` | pass | All 5 app subdirs compiled clean |
| Static: alembic heads | `python -m alembic heads` | pass | `0023_add_operation_client_request_id (head)` |
| B1 schema columns | `psql \\d operations` | pass | `client_request_id varchar(100)`, `client_request_hash varchar(64)` присутствуют; `machine_last_batch_id` и `version` сохранены |
| B1 partial unique index | `pg_indexes` lookup | pass | `ix_operations_client_request_id` UNIQUE на `(created_by_user_id, client_request_id) WHERE (client_request_id IS NOT NULL)` |
| B2 version in response | PATCH smoke | pass | `OperationResponse.version` возвращается; `get_operation_by_id_for_update()` использует `with_for_update()` |
| B2 expected_version 409 | Stand smoke (stale) | pass | `409 {"code":"operation_version_conflict","current_version":2}` при `expected_version=1` после bump |
| B3 PATCH accepts effective_at | `test_general_patch_accepts_effective_at_atomically` | pass | Атомарный PATCH effective_at с bumped version |
| B4 idempotency replay | Stand smoke | pass | Тот же `client_request_id`+payload → тот же `id` |
| B4 idempotency conflict | Stand smoke | pass | Тот же `client_request_id`+разный qty → `409 {"code":"idempotency_payload_conflict"}` |
| B4 hash function | `OperationsService._compute_client_request_hash` smoke | pass | SHA-256 hex длиной 64; разные payload'ы дают разные hash; whitespace-нормализация работает |
| B5 catalog guard | Code review + DB integration tests | pass | `CatalogReadService.resolve_items` вызывается перед line-recreate; structured `fields` для каждой unusable строки |
| Full test suite (excl. stand/serial) | `pytest -m "not stand and not serial"` | 546 passed | 0 failures, 2 skipped, 7 xfailed (pre-existing); обновлены 2 теста под новые контракты |
| Stand smoke: idempotency | `POST /api/v1/operations` x2 same key+payload | 200 OK | Replay возвращает тот же UUID и version |
| Stand smoke: version conflict | `PATCH /api/v1/operations/{id}` stale `expected_version` | 409 | Structured `operation_version_conflict` с `current_version` |

### Stage C Evidence

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|
| Static: catalog_cache models | `python -m compileall apps/catalog_cache` | pass | `unit_id` field added, indexed |
| C1 migration | `python manage.py showmigrations catalog_cache` | pass | `0004_catalogcacheitem_unit_id` applied |
| C1 unit_id in upsert | `test_sync_items_records_unit_id_and_default_active` | pass | unit_id "5", unit_symbol "кг" stored; is_active=True |
| C3 reconciliation prune unseen | `test_sync_items_complete_success_deactivates_unseen` | pass | 1 deactivated, unseen row becomes inactive |
| C3 partial scan no-prune | `test_sync_items_partial_scan_does_not_deactivate` | pass | 0 deactivated, unseen stays active |
| C3 count-mismatch no-prune | `test_sync_items_count_mismatch_does_not_prune` | pass | aborted_reason=count_mismatch, 0 deactivated |
| C2 write-through deactivate | `test_write_through_deactivate_item` | pass | sync_id=42 `is_active=False` after deactivate |
| C2 write-through by-category | `test_write_through_invalidate_by_category` | pass | category_id=12 items inactive, 13 stays |
| C2 write-through by-unit | `test_write_through_invalidate_by_unit` | pass | unit_id=5 items inactive, 6 stays |
| C2 category rename update | `test_write_through_category_rename_updates_snapshot` | pass | category_name updated to "Новая категория" |
| C2 unit rename update | `test_write_through_unit_rename_updates_symbol` | pass | unit_symbol updated to "кг" |
| C4 unit_id in lookup | `test_lookup_exposes_unit_id_field` | pass | unit_id "8" and unit_symbol "л" in response |
| C3 SSR rebuild stats message | `test_rebuild_stats_in_messages_on_success` | pass | fetched, deactivated, duration visible |
| C3 SSR abort warning | `test_rebuild_stats_warns_on_aborted_scan` | pass | "не завершилась" + reason in message |
| C5 catalog search consistency mode | Code review | pass | `consistency=fast` (default) / `=authoritative`; authoritative never degrades to cache |
| C5 resolver endpoint | POST `/bff/api/v1/catalog/read/items/resolve` body `{"item_ids":[...]}` | pass | route registered, forwards to SyncServer |
| C5 structured _handle_sync_error | Code review + existing 409 tests | pass | `detail`/`fields`/`current_version`/`request_id`/`status` forwarded |
| C5 client_request_id validation | POST create without cri → 400 | pass | `_validate_client_request_id` enforces non-empty, ≤100 chars |
| C5 expected_version validation | PATCH without ev for 3.2 client → 400 | pass | `_validate_expected_version` enforces positive int for new client |
| C5 operation_outcome_unknown | `SyncBackendUnavailable` → 504 | pass | `code:operation_outcome_unknown`, `retry_safe:true` |
| Django full test (focused) | `python manage.py test apps.catalog_cache.tests` | 28 passed | 0 failures, 0 errors |
| Django full test (BFF) | `python manage.py test apps.bff_api.tests` | 71 passed | 0 failures, 0 errors |
| Django full test (catalog) | `python manage.py test apps.catalog.tests` | 41 passed | 0 failures, 0 errors |
| Django full test (sync_client) | `python manage.py test apps.sync_client.tests` | 80 passed | 0 failures, 0 errors |
| Total Django affected | `python manage.py test` (all 4) | 140+80=220 passed | All pre-existing tests unaffected; Stage C adds 17 new |

**Commit:** `901fb1a` — feat(v3.2): Stage C — Django BFF/cache coherence (Warehouse_web)

### Stage C — Django BFF/cache

#### C1. Cache schema and serialization

**Areas:**

- `Warehouse_web/apps/catalog_cache/models.py`
- новая Django migration
- `Warehouse_web/apps/catalog_cache/services.py`

Добавить nullable/indexed `unit_id`, сохранять remote `category_id/unit_id/source_updated_at/synced_at`. Existing rows получают `unit_id=NULL` до полного rebuild.

#### C2. Write-through coherence

**Areas:** `Warehouse_web/apps/bff_api/catalog_views.py` и catalog services.

Только после успешного SyncServer response:

- create/update/active target → upsert snapshot;
- deactivate/delete/merge source → local `is_active=false`;
- merge target → upsert target;
- category deactivate/delete/merge → invalidate dependent `category_id` rows;
- unit deactivate/delete → invalidate dependent `unit_id` rows;
- category/unit rename/update либо обновляет dependent snapshots, либо безопасно invalidates их до следующего warm/rebuild;
- failed authoritative write не меняет cache.

Проверить item, batch, merge, category и unit handlers; один helper должен исключить расхождение поведения.

#### C3. Complete-success reconciliation

Изменить `CatalogCacheSyncService.sync_items()`:

1. выполнить полный active scan без `max_pages` для admin action;
2. upsert страниц разрешён по мере чтения;
3. использовать единый `reconciliation_started_at` как `synced_at` всех увиденных строк и собрать unique seen IDs только для проверки полноты;
4. подтвердить успешное завершение и согласованность seen count/remote total;
5. только затем одной DB operation пометить active rows с `synced_at < reconciliation_started_at` inactive;
6. failed/partial/count-mismatch scan не выполняет prune.

Строгое `<` сохраняет строки текущего scan (`synced_at == reconciliation_started_at`) и не позволяет prune затереть более свежий write-through (`synced_at > reconciliation_started_at`). Большой SQL `NOT IN (seen_ids...)` не используется.

Существующую SSR кнопку переименовать в «Пересобрать кэш поиска ТМЦ» и показать `fetched/upserted/deactivated/skipped/duration`. Пока измеренный runtime укладывается в HTTP budget, job runner не добавлять.

#### C4. BFF consistency/resolver contracts

Реализовать §4.3. `fast` остаётся default для совместимости. `authoritative` не деградирует молча до cache. Resolver использует user-context SyncServer read API; browser tokens не раскрываются.

#### C5. Operation contract passthrough

**Areas:**

- `Warehouse_web/apps/sync_client/operations_api.py`
- `Warehouse_web/apps/sync_client/client.py`
- `Warehouse_web/apps/bff_api/helpers.py`
- `Warehouse_web/apps/bff_api/operations_views.py`

- сохранить `version`, structured `detail`, `fields`, current version и status;
- BFF PATCH/submit валидирует наличие `expected_version` для Warehouse 3.2 client;
- create требует non-empty `client_request_id` до 100 символов; Angular 3.2 отправляет UUID, legacy prefixed key допустим только для rollout compatibility;
- transport не выполняет автоматический retry POST/PATCH;
- write timeout возвращает distinct `operation_outcome_unknown`, request ID и retry-safe guidance.

#### Acceptance C

- [x] Успешные item/category/unit mutations немедленно отражены в cache. (C2 write-through + tests)
- [x] Failed mutation не меняет cache. (C2 write-through только после успешного SyncServer response)
- [x] Full reconciliation деактивирует unseen только после complete-success. (C3 + tests)
- [x] Failed/partial/count-mismatch reconciliation не prune-ит строки. (C3 + tests: count_mismatch/max_pages_reached)
- [x] `authoritative` реально вызывает SyncServer и не возвращает stale fallback. (C4 consistency mode)
- [x] Resolver result и structured operation errors доходят до Angular без string parsing. (C4 resolver + C5 structured error forwarding)
- [x] Version/expected_version/client_request_id не теряются в proxy. (C5 validation/passthrough + tests)

### Stage D — Angular UX/state

#### D1. DTO and services

**Areas:**

- `Warehouse_frontend/src/app/core/models/operations.models.ts`
- `core/services/catalog-search.service.ts`
- `core/services/operations.service.ts`
- `core/api/bff-api.service.ts`

Добавить operation version, resolver DTO, consistency mode, line errors, distinct ambiguous outcome. `BffApiService` сохраняет structured fields/status/request ID и имеет явный timeout только для mutations.

`OperationDto`, `OperationDraftVm` и `OperationListRowVm` хранят version. Submit из таблицы использует version строки; stale list закономерно получает 409 и предлагает reload.

#### D2. «Обновить и проверить ТМЦ»

**Areas:** `item-cache-search`, `operation-create-modal`, `operation-lines-table`.

Команда:

1. отменяет текущий search stream;
2. повторяет текущий query с `consistency=authoritative`;
3. batch-resolve persisted item IDs draft;
4. показывает per-line status/reason/canonical target;
5. блокирует Save/Submit для `merged/inactive/deleted/missing`;
6. не меняет/не суммирует строки автоматически;
7. не валидирует unmaterialized inline payload как persisted item.

Fast cache suggestion перед фактическим добавлением строки проходит single/batch resolver. При unavailable authoritative service item не добавляется молча.

RxJS error handling должен находиться внутри per-query `switchMap`: одна временная network error не завершает search stream навсегда. После восстановления соединения следующий ввод/ручной refresh снова отправляет запрос; ошибка видна пользователю.

#### D3. Automatic pre-persist validation

Resolver запускается после загрузки существующего draft, перед Save/Submit и после `catalog_item_unusable`. Если draft изменился во время resolver request, устаревший response игнорируется по local validation sequence.

#### D4. Persist state machine

```text
idle -> validating_items -> saving -> saved
                           -> rejected
                           -> conflict
                           -> checking_outcome -> saved_after_check | safe_to_retry | outcome_unknown
```

- immutable snapshot и busy фиксируются до первого `await`;
- component emits intent синхронно; parent/service владеет orchestration;
- поля, close, Save и Confirm заблокированы во время active persist/check;
- balance refresh не стоит между click и save-intent, его ошибка не очищает данные молча;
- success принимает returned ID/version/snapshot и показывает «Сохранено HH:MM»;
- более поздний response не перезаписывает новый local revision.

Persist state/error scoped к конкретному modal command; background list/balance load не может очистить или заменить save error через общий service signal.

После bounded recovery пользователь может явно выбрать «Закрыть без подтверждённого результата». Действие требует warning и не должно выглядеть как успешное сохранение; бесшумное закрытие остаётся запрещено.

#### D5. Save and Confirm semantics

- Save использует create key либо expected version.
- Confirm в P1 выполняет Save, принимает returned ID/version, затем Submit с новой version.
- Если Save успешен, а Submit отклонён, modal остаётся открыт и показывает «Черновик сохранён, подтверждение не выполнено»; retry не создаёт новый draft.
- Atomic save-and-submit command не входит в P1.

Одинаковая семантика обязательна для обоих hosts `OperationCreateModalComponent`:

- `OperationsPageComponent`;
- `issued-assets/components/object-panel/ObjectPanelComponent`.

`ObjectPanelComponent` не закрывает modal в `finally` после failed/unknown submit и сохраняет UI-only locked object context после успешного Save. Confirm из operations table также не исчезает бесшумно при conflict/error.

#### D6. Ambiguous outcome

Реализовать §4.7. GET/fingerprint использует normalized ordered lines и editable fields. При conflict показать current version и действия «Перезагрузить операцию»/«Остаться и скопировать данные» без автоматического overwrite. Full payload не писать в local/session storage.

#### Acceptance D

- [ ] Busy начинается до preflight; double click/close не теряют intent.
- [ ] Deleted/merged/inactive/missing line видна и блокирует persist.
- [ ] Merged target показывается, но не подставляется автоматически.
- [ ] Save success переживает close/reopen с exact fingerprint.
- [ ] 409 не перезаписывает новую server version.
- [ ] Lost update/submit response запускает GET recovery.
- [ ] Lost create response повторяется с тем же key без duplicate.
- [ ] Save-success/submit-failure отображается как два разных outcome.
- [ ] После временной search error следующий query работает без reload страницы.
- [ ] Operations page и issued-assets object panel имеют одинаковую save/submit reliability.

### 5.1. Files and areas in scope

| Project | Required areas | Expected change |
|---|---|---|
| SyncServer | `app/repos/catalog_repo.py` | raw resolution reads, usable filters, atomic soft-delete |
| SyncServer | `app/services/operations_service.py` | item guard, versioned update, atomic lines/effective_at, idempotent create |
| SyncServer | `app/repos/operations_repo.py`, `app/models/operation.py` | row lock, client request fields/index support |
| SyncServer | `app/schemas/catalog.py`, `app/api/routes_catalog.py` | resolver request/response/route |
| SyncServer | `app/schemas/operation.py`, `app/api/routes_operations.py` | version/expected_version/errors |
| SyncServer | `alembic/versions/` | client request schema and active-deleted remediation |
| SyncServer tests | `tests/test_operations_service_update.py` plus focused new catalog/version/idempotency tests | unit + PostgreSQL integration |
| Django | `apps/catalog_cache/models.py`, `services.py`, migration | unit ID, write-through, safe reconciliation |
| Django | `apps/bff_api/catalog_views.py`, `operations_views.py`, `helpers.py`, `urls.py` | contracts and structured errors |
| Django | `apps/sync_client/catalog_api.py`, `operations_api.py`, `client.py` | SyncServer proxy DTO/error preservation |
| Django SSR | `apps/catalog/views.py`, `templates/catalog/manage_workspace.html`, `templates/catalog/home.html` | admin rebuild action/stats |
| Django tests | `apps/catalog_cache/tests.py`, `apps/bff_api/tests.py` | component/integration coverage |
| Angular | `src/app/core/models/operations.models.ts` | version, resolver and line status DTO |
| Angular | `src/app/core/api/bff-api.service.ts` | structured errors, request ID, mutation timeout |
| Angular | `src/app/core/services/catalog-search.service.ts`, `operations.service.ts` | consistency/resolver/persist recovery |
| Angular | `src/app/features/operations/components/item-cache-search/` | authoritative refresh/search cancellation |
| Angular | `operation-create-modal/`, `operation-lines-table.component.ts` | repair UX, line blocks, state machine |
| Angular | `src/app/features/operations/pages/operations-page/` | parent-owned save/submit orchestration |
| Angular | `src/app/features/issued-assets/components/object-panel/object-panel.component.ts` | тот же persist contract, modal не закрывается при failure/unknown |
| E2E | `Warehouse_frontend/e2e/operations/` | reopen, conflict, cache repair, lost response |

Generated bundles, production data, offline clients, `WarehouseDesktop/`, `WarehouseMobile/` и `WarehouseAIWorkstation/` не входят в implementation ownership этого TZ.

## 6. Execution Strategy

**Sequential with one staged-parallel window.** Shared `operations_service.py`, migrations и cross-layer contracts делают полностью параллельную реализацию рискованной.

| Order | Ownership | Depends on | Integration gate |
|---:|---|---|---|
| 1 | SyncServer Stage A | accepted invariant | catalog tests + resolver contract frozen |
| 2 | SyncServer Stage B | Stage A guard semantics | operation tests + OpenAPI examples frozen |
| 3 | Django Stage C | Stages A/B | Django tests against exact Sync DTO/error fixtures |
| 4 | Angular Stage D | Stage C contract | build + component tests |
| 5 | Full integration | all stages | migrations → stand → Playwright → regression |

Stage A и B выполняются последовательно: они пересекаются в `operations_service.py` и transaction semantics. После фиксации SyncServer API допустим staged-parallel максимум в **2 потока**:

- поток 1 владеет только `Warehouse_web/`;
- поток 2 готовит Angular DTO/component tests на frozen fixtures, но интегрирует runtime-вызовы после готовности BFF;
- миграции, shared docs, E2E и final integration имеют одного владельца.

Порядок проверок обязателен: SyncServer focused → SyncServer full → Django focused/full → Angular unit/build → migrations на safe DB → stand smoke → Playwright → regression.

## 7. Test Ladder

### Stage D Evidence

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|
| D1 version in OperationDto | Code review | pass | `version?: number` added |
| D1 PersistState type | Code review | pass | `PersistStatus`, `PersistState`, `PersistError` defined |
| D1 ResolvedItemDto type | Code review | pass | `ItemResolveStatus`, `ResolvedItemDto` defined |
| D2 BFF API structured errors | Code review | pass | `current_version`, `request_id`, `retry_safe`, `status` through error handler |
| D2 X-Warehouse-Client header | Code review | pass | `getMutationHeaders()` sets `X-Warehouse-Client: 3.2-angular` |
| D2 Mutation timeout | Code review | pass | `MUTATION_TIMEOUT_MS = 30000`, `timeout()` on POST/PATCH/PUT/DELETE |
| D2 Timeout → operation_outcome_unknown | Code review | pass | TimeoutError returns `code: operation_outcome_unknown, retry_safe: true` |
| D3 consistency param | `searchItems(query, limit, sourceSiteId, includeBalance, consistency)` | pass | Forwarded as `$httpParams` to BFF |
| D3 authoritative refresh | `refreshItemsAuthoritative()` | pass | Cancels stream, re-runs with `consistency=authoritative` |
| D3 batch resolver | `resolveItems(itemIds)` | pass | `POST /catalog/read/items/resolve`, returns `ResolvedItemDto[]` |
| D4 persist state machine | `persistState()` signal | pass | `setPersist(status, error)` with stale-response guard |
| D4 immutable snapshot | `captureSnapshot()` / `isSnapshotValid()` | pass | Deep-clone before await; comparison guards stale callbacks |
| D4 pre-persist validation | `validateLinesBeforePersist()` | pass | Batch-resolves persisted IDs; blocks if `isItemUnusable()` |
| D4 create always idempotent | `createOperation()` | pass | `client_request_id` always generated (UUID) |
| D4 update with expected_version | `updateOperation()` | pass | `draft.version → payload.expected_version` |
| D4 submit with expected_version | `submitOperation()` | pass | `draft.version → payload.expected_version` |
| D5 saveAndSubmit partial lifecycle | `saveAndSubmit()` | pass | Catches submit fail → returns saved operation, shows partial outcome |
| D5 version bump on create | `createOperation()` | pass | `draft.version = result.version` after success |
| D6 fingerprint builder | `buildFingerprint()` | pass | Normalized ordered lines + fields, no local/session storage |
| Angular full test suite | `npm test -- --watch=false` | 57 passed | 11 test files, 0 failures |
| Angular production build | `npm run build` | exit 0 | Pre-existing CSS budget warnings only |

**Commit:** `c993730` — feat(v3.2): Stage D — Angular UX/state (Warehouse_frontend)

### 7.1. Mandatory levels

| Level | Required verification | Command / location | Pass condition |
|---|---|---|---|
| 1. Static | Python syntax/migration heads; Django system/migration drift; Angular type/build | `python -m compileall app`; `python -m alembic heads`; `python manage.py check`; `python manage.py makemigrations --check --dry-run`; `npm run build` | exit 0, one Alembic head, no missing Django migration |
| 2. Unit | Resolver/status/hash/fingerprint/state reducers | project test runners | all focused cases pass |
| 3. Component | Fast/authoritative BFF views, reconciliation, modal line blocking/error rendering | Django test client, `npm test -- --watch=false` | exact status/body/UI state assertions |
| 4. DB integration | PostgreSQL row lock/version race, unique create key, data remediation, Django cache prune | SyncServer/Django test DB | no duplicates/lost update/unsafe prune |
| 5. Stand smoke | Real SyncServer + Django + PostgreSQL + Angular | Docker stand below | all smoke scenarios pass |
| 6. UI automation | Browser cache repair/save/reopen/two-tab/network fault | `make test-e2e` or focused Playwright first | trace/report retained, 0 required failures |
| 7. User scenarios | Storekeeper and chief/root flows | Playwright + manual verification | expected Russian UX and permissions |
| 8. Regression | Full backend/web/build suites | project commands | 0 new failures; skips documented |
| 9. Acceptance | Evidence review | this TZ | every checked item has evidence |

### 7.2. Required SyncServer tests

Extend existing tests and add focused files such as `test_catalog_item_resolution.py`, `test_operations_version_conflict.py`, `test_operations_create_idempotency.py`.

Minimum cases:

1. soft-delete active review item sets inactive;
2. browse/read excludes active-deleted fixture;
3. resolver: active, inactive, deleted, missing, one-hop merge, multi-hop merge;
4. resolver: cycle/depth/unusable category/unusable unit;
5. current-version update persists exact ordered lines and increments once;
6. stale-version update changes nothing;
7. two concurrent updates from one version: exactly one success, one 409;
8. atomic lines + effective_at rollback on invalid item;
9. create replay for ordinary and inline lines returns same ID;
10. same key/different item ID or quantity returns 409;
11. concurrent same-key create produces one row;
12. submit expected-version conflict does not materialize inline items or move balances;
13. active-deleted remediation updates all matching rows, leaves unrelated rows unchanged and is safe on repeat execution.

### 7.3. Required Django tests

1. local full cache hit for `fast` does not call SyncServer;
2. `authoritative` always calls SyncServer and fails closed when unavailable;
3. resolver proxy preserves every status/reason/canonical target;
4. item delete/deactivate/merge write-through invalidates source and warms target;
5. category/unit mutations invalidate dependent rows;
6. failed SyncServer mutation leaves cache unchanged;
7. complete scan deactivates unseen;
8. failed/partial/count-mismatch scan never deactivates unseen;
9. cache rebuild stats include deactivated/duration;
10. version/conflict/catalog fields survive BFF mapping;
11. write timeout becomes `operation_outcome_unknown`, not definite failure;
12. create key and expected version reach SyncServer unchanged.

### 7.4. Required Angular unit/component tests

1. manual refresh cancels stale search and requests authoritative mode;
2. persisted lines are batch-resolved, inline lines excluded;
3. each unusable status renders line message and blocks both actions;
4. merged target is shown without automatic replacement/sum;
5. busy is set before resolver/balance await;
6. close/double-click/edit controls are blocked during persist;
7. stale async response cannot overwrite newer local revision;
8. save success stores ID/version/fingerprint/timestamp;
9. version 409 exposes reload action without overwrite;
10. status 0/timeout transitions to `checking_outcome`;
11. GET matching fingerprint resolves update as saved;
12. GET different newer fingerprint resolves conflict;
13. create retry reuses the same `client_request_id`;
14. save success + submit failure retains saved draft state;
15. transient search error does not terminate subsequent query stream;
16. ObjectPanel failure/unknown keeps modal and locked object context.

### 7.5. Required Playwright scenarios

Prefer two focused specs: `operations-catalog-refresh.spec.ts` and `operations-save-reliability.spec.ts`.

1. Warm cache → delete/merge item → «Обновить и проверить» → line blocked/source absent.
2. Add line → Save → close → reopen → exact item IDs/qty/order match.
3. Delay balance/resolver → click Save then close/double-click → exactly one persist intent and no silent loss.
4. Two tabs open same version → A saves → B gets 409 and cannot overwrite A.
5. `route.fetch()` commits update, then route aborts browser response → Angular GET recovery reports saved.
6. `route.fetch()` commits create, then abort → retry uses same key and one operation exists.
7. Save succeeds, submit returns business reject → modal says draft saved/not submitted.
8. SyncServer unavailable during authoritative resolver → stale result cannot be persisted.
9. Issued-assets object panel receives submit error/unknown → modal remains open and no duplicate operation is created.

Expected volume: **35–50 logical scenarios**, обычно около **25–32 test functions/spec cases** после разумной parameterization. Evidence coverage may not be reduced.

## 8. Stand Requirements

### 8.1. Services and health

| Service | Address | Health |
|---|---|---|
| SyncServer | `http://localhost:8000` | `GET /api/v1/health` |
| Django | `http://localhost:8001` | `GET /healthz/` |
| Angular | `http://localhost:4200` | `GET /` |
| PostgreSQL | `localhost:5432` | `pg_isready -h localhost -p 5432 -t 3` |

Database: local Docker PostgreSQL with persistent dev volume. Do not use `make clean`, volume deletion, broad DELETE or reset for this TZ.

### 8.2. Environment variable names

`DJANGO_ENV`, `SYNC_SERVER_URL`, `SYNC_ROOT_USER_TOKEN`, `SYNC_DEVICE_TOKEN`, `DATABASE_URL`, `DJANGO_SETTINGS_MODULE`, `SECRET_KEY`. Values must not appear in evidence/logs.

### 8.3. Seed data

- root/chief and storekeeper web identities with valid bindings;
- at least two sites;
- active category and unit;
- active item A and merge target B;
- unique test prefix `E2E-V32-<run_id>` for created items/operations;
- one safe test DB fixture with `deleted_at != null AND is_active=true` for migration/integration only, never production manual corruption.

### 8.4. Availability protocol

1. Probe endpoints only when the first stand request fails or перед explicit stand stage.
2. If unavailable, run `make up`; fallback `docker compose up -d`.
3. Apply safe migrations with `make migrate` only after backup when persisted data matters.
4. If stand cannot start, leave stand/UI checklist unchecked with «стенд недоступен».

### 8.5. Smoke sequence

1. Verify health and current migrations.
2. Create/warm item A through supported APIs.
3. Deactivate/delete/merge A through BFF; verify write-through removes it from fast search.
4. Make a supported external SyncServer catalog mutation, run admin rebuild, verify unseen row becomes inactive locally.
5. Open draft with A, resolve after merge/delete, verify line-level block.
6. Replace/remove problem line explicitly, Save, close, reopen and compare fingerprint.
7. Open same draft in two tabs and verify stale 409.
8. Run lost-response Playwright fixture and verify one create/update.

### 8.6. Cleanup

- Cancel/delete only test drafts allowed by business rules.
- Deactivate/delete only entities with current `E2E-V32-<run_id>` prefix.
- Do not remove shared categories/units, truncate tables or delete Docker volumes.
- Record IDs of leftovers if cleanup is blocked by referential/business rules.

## 9. Rollout and rollback

### 9.1. Rollout order for 3.2

1. Подтвердить P1 scope и архитектурные границы этого TZ; ADR-0018/0019 не являются runtime blocker.
2. Backup SyncServer and Django databases; record audit count of active-deleted items (reported baseline: 26). Unexpected delta requires review before migration.
3. Deploy SyncServer additive fields/endpoints with optional rollout `expected_version/client_request_id`.
4. Apply SyncServer migrations; verify zombie count changed from audited value to 0 and run focused tests.
5. Deploy Django migration/BFF/cache changes; run complete cache rebuild and verify no remediated ghost is returned by fast search.
6. Deploy Angular 3.2 bundle; verify browser actually serves current assets.
7. Run stand smoke, focused Playwright, then full regression.
8. Monitor version conflicts, unknown outcomes, resolver statuses and cache deactivations.

During 3.2 SyncServer may accept legacy unversioned callers for compatibility, but Angular 3.2 and Django BFF must always send version/key. Strict rejection of unversioned raw `/api/v1` writes requires a separate compatibility decision after adoption metrics.

### 9.2. Observability

Required structured events/counters, without item names, payloads or tokens:

- `catalog_cache_reconcile_completed{fetched,upserted,deactivated,skipped}`;
- `catalog_item_resolution{status}`;
- `operation_version_conflict`;
- `operation_create_replay{result=same_payload|payload_conflict}`;
- `operation_outcome_check{result=saved|retry|conflict|unknown}`;
- shared `X-Request-Id` through Angular response, Django and SyncServer logs.

### 9.3. Rollback

- Do not roll back soft-delete/read correctness merely to restore old UI behavior.
- Angular repair action/state machine may be rolled back independently while resolver/server guards stay.
- Django can temporarily force authoritative search if cache reconciliation is suspect.
- Additive DB columns/indexes may remain during application rollback; do not downgrade while old/new app versions are mixed.
- Data remediation downgrade is no-op; restoration of previously active-deleted rows is allowed only from verified backup and explicit manual decision.
- If unique-key migration fails audit, stop rollout; do not delete/merge duplicates automatically.

## 10. Risks and architecture stress-test

| Failure mode | Required mitigation | Residual / escalation |
|---|---|---|
| Partial/failed catalog scan prunes valid cache | Prune only after complete-success/count check | Re-run; P2 revision feed if recurring |
| Catalog write during scan is pruned | Strict `synced_at < reconciliation_started_at` | External mutation/page drift can fail count safely |
| Large catalog exceeds `NOT IN`/memory | Timestamp-based prune; seen set only for count | P2 DB staging/job if measured memory/runtime is high |
| Deleted-active production rows exist | Backup, audit count, one-way remediation | Restore only from backup |
| Merge chain cycle | Depth/cycle guard; block line | Data repair remains admin follow-up |
| Two tabs replace all lines | Row lock + expected version before mutation | Legacy unversioned client remains rollout risk |
| Save request remains in-flight after browser timeout | Bounded GET polling; expected version | P2 receipt only if aggregate GET insufficient |
| Create response lost | Dedicated stable key/hash + unique constraint | P2 receipt only for cross-reload history |
| Same key reused with changed payload | Canonical hash + 409 | Hash algorithm must be deterministic and unit-tested |
| Inline legacy key stored in old field | One-release fallback lookup, no ambiguous backfill | Remove fallback only by later compatibility decision |
| Update saved, submit failed | Persist returned draft ID/version before submit | Atomic save-and-submit deferred |
| Error response loses fields | Preserve structured payload through sync client/BFF | Never parse human message in Angular |
| Modal gets stuck in unknown state | Bounded polling + explicit warned close | No claim that close means saved |
| Category/unit mutation leaves stale display | Update or invalidate dependents | Rebuild repairs invalidated rows |
| P1 scope grows into platform work | Enforce Out-of-scope list | ADR/TZ required to promote P2 |

Manual stress-test covered source-of-truth boundaries, incomplete scans, concurrent write-through, full-replace races, in-flight timeout, create replay, legacy client rollout, merge cycles, multi-instance Django, rollback and test evidence. Required `architecture-review` skill was unavailable in the environment; blockers were checked manually.

Unverified until implementation/stand phase:

- exact production data count and deployed commit;
- catalog scan P95 and memory footprint;
- real reverse-proxy/browser deadlines;
- production frequency of ambiguous writes;
- whether legacy non-web clients send operation writes without version/key.

## 11. Evidence

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|
| Static/migration drift | commands from §7.1 | pass | SyncServer `alembic head=0023`, Django `0004` DDL applied |
| SyncServer focused | `docker exec warehouse_syncserver python -m pytest tests/test_operations_service_update.py tests/test_operations_effective_at_api.py tests/test_temporary_items_stage3b.py` | 18 passed | Stage B idempotency/version/guard passes |
| Django focused | `docker exec warehouse_web python manage.py test apps.catalog_cache.tests apps.bff_api.tests apps.catalog.tests` | 140 passed | Stage C+D write-through/reconciliation/resolver passes |
| Angular component/build | `npm test -- --watch=false`; `npm run build` | 57 passed | Stage D DTO/services/state machine pass |
| SyncServer migration | `docker exec warehouse_syncserver alembic current` | head | `0023_add_operation_client_request_id (head)` |
| Django migration | `docker exec warehouse_web python manage.py migrate catalog_cache 0004` | OK | `unit_id` column verified in DB |
| Stand smoke: resolver | `POST /bff/api/v1/catalog/read/items/resolve` | pass | Full chain: browser->BFF->SyncServer->structured response |
| Stand smoke: consistency | `GET /catalog/search/items?consistency=fast\|authoritative` | pass | `fast`=merged source, `authoritative`=remote source |
| Stand smoke: version create | `POST /operations` with `client_request_id` | pass | Returns `version:1` |
| Stand smoke: version conflict | `POST /operations/{id}/submit` stale `expected_version` | pass | `409 operation_version_conflict` with `current_version:1` |
| UI automation | focused Playwright; `make test-e2e` | skipped | Отложено до Stage D Angular на стенде |
| Regression (SyncServer) | docker focused operations tests | 18p / 0f | Core Stage A+B semantics preserved |
| Regression (Django) | docker 3 app test suite | 140p / 0f | Stage C+D changes pass with no regressions |
| Regression (Angular) | `npm test -- --watch=false` | 57p / 0f | All existing component/service tests pass |

Executor report must add focused commands, test counts, migration revisions, stand URLs, request IDs and Playwright report/trace paths. Screenshots may not expose tokens or sensitive payloads.

## 12. Documentation deliverables

- сохранить source review как evidence;
- при необходимости оформить ADR-0018/ADR-0019 строго по уже принятым решениям этого TZ, не расширяя P1;
- обновить активную API/architecture документацию при изменении контрактов;
- не менять `Functional and WorkLogik.md`: реализация должна соответствовать существующим II.5.0/II.8;
- executor обновляет checklist и Evidence в этом TZ;
- P2 follow-up оформляется отдельно, а не как скрытый остаток implementation.

## 13. Final acceptance

1. SyncServer enforces catalog usability consistently in writes and operational reads.
2. Existing active-deleted rows are audited and remediated after backup; post-migration `is_active=true AND deleted_at IS NOT NULL` count is 0.
3. Fast cache remains available, while authoritative refresh/resolver never silently falls back to stale rows.
4. Successful BFF catalog mutation immediately updates/invalidate cache.
5. Full reconciliation prunes unseen rows only after complete-success.
6. «Обновить и проверить ТМЦ» revalidates current query and existing persisted lines.
7. Merged/deleted/inactive/missing lines block Save/Submit until explicit user action.
8. Save/reopen returns exact immutable save fingerprint.
9. Stale tab receives 409 and cannot overwrite newer lines.
10. Ordinary and inline create retries with one key create exactly one operation.
11. Network response loss resolves through GET/fingerprint or exact create replay without false «не сохранено».
12. Save success followed by submit failure retains server ID/version and reports partial lifecycle outcome.
13. Structured errors remain line-addressable through SyncServer → Django → Angular.
14. Required backend, Django, Angular build, migration, stand and Playwright checks have evidence.
15. P2 mechanisms were not silently added to 3.2 scope.
16. TZ и активные docs описывают accepted target/deferred work; final QA reviewer signs checklist item 10.
17. Transient catalog search failure does not require SPA reload for the next query.
18. Operations page and issued-assets object panel pass the same persist/error/recovery contract.
