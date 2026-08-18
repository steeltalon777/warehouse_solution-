# API_GAPS — отсутствующие возможности SyncServer API

Зафиксировано по коду SyncServer на 2026-08-03. SyncServer, Django BFF и БД
в рамках задачи НЕ изменялись. Для каждого пробела — локальный fallback
и что потребуется добавить на сервере.

## GAP-1. Загрузка исходного документа (upload файла) — ОТСУТСТВУЕТ

- Факт: grep `UploadFile|File(|multipart|upload` по `SyncServer/app/` — 0.
  `routes_documents.py` умеет только генерацию/рендер документов ИЗ операций;
  в модели `Document` нет колонок вложений (blob/path/storage_key).
- Fallback: исходный файл хранится локально в деле
  (`%LOCALAPPDATA%\WarehouseAgent\cases\<case-id>\source\`), SHA-256
  вычисляется клиентом; связь с операцией — через `source_ref =
  "sha256:<hash>"` и `source_document_type="ocr_scan"` в
  `POST /operations/from-source-document`.
- Команды `document upload` / `document get` в CLI **не реализованы**
  (по ТЗ — только при наличии реального API).
- Нужно на сервере: `POST /api/v1/documents/uploads` (multipart, поля:
  файл, sha256, document kind, привязка case/source_ref) +
  `GET /api/v1/documents/uploads/{id}` + связка с операцией.

## GAP-2. Серверная валидация черновика без проведения — ОТСУТСТВУЕТ

- Факт: endpoint вида `POST /operations/{id}/validate` отсутствует;
  проверки (остатки, состояние, права) выполняются только внутри submit.
- Fallback: команда `draft validate` делает локальную валидацию:
  существование/активность позиций (`catalog get`), qty>0, для
  EXPENSE/WRITE_OFF/ISSUE/MOVE — достаточность остатков
  (`GET /balances?site_id&item_id`). Результат помечен
  `validation_scope: "local"`.
- Нужно на сервере: `POST /api/v1/operations/{id}/validate` —
  «сухой прогон» проверок submit без применения эффектов, ответ в формате
  ProblemEnvelope с доменными кодами.

## GAP-3. PATCH заменяет строки целиком, source_*-снимки теряются

- Факт: `OperationUpdate.lines` — это `list[OperationLineCreate]`
  (без `source_item_name` и т.п.); сервис делает delete+create всех строк,
  `id` строк перевыпускаются.
- Fallback: клиент при add-lines/update-line сначала читает draft,
  сливает строки и шлёт полный список с `expected_version`; raw-имя
  сохраняет в `comment`, если он пуст; добавляет warning `lines_replaced`.
- Нужно на сервере: точечные операции со строками
  (`POST /operations/{id}/lines`, `PATCH /operations/{id}/lines/{line_id}`,
  `DELETE .../lines/{line_id}`) и/или приём `source_*` в
  `OperationLineCreate`.

## GAP-4. Заголовок `Idempotency-Key` — ОТСУТСТВУЕТ

- Факт: идемпотентность только через поля тела (`client_request_id`,
  `source_ref`). Это покрыто клиентом: `client_request_id` генерируется
  автоматически и выводится в warning для безопасного повтора.
- Нужно на сервере (опционально): приём `Idempotency-Key` как алиаса
  `client_request_id` для унификации с отраслевой практикой.

## GAP-5. Acting User Context (имперсонация) — ОТСУТСТВУЕТ

- Факт: заголовка/механизма «действовать от имени другого пользователя»
  нет (проверено grep `acting|impersonat|X-Acting`); действующий субъект —
  владелец `X-User-Token`.
- Следствие: каждому кладовщику выдаётся собственный `X-User-Token`;
  device-токен рабочего места — только для аудита. Никаких «сервисных»
  токенов с имперсонацией конфигурировать не требуется.

## GAP-6. Балансы по позиции без deprecated-параметра

- Факт: `GET /balances` принимает `item_id`, но параметр помечен
  `[deprecated]` (переход на `inventory_subject_id`).
- Fallback: клиент использует `item_id` (работает), пометка в коде.
- Нужно на сервере: публичный параметр фильтра по предмету инвентаря
  (`inventory_subject_id`) в `/balances` до удаления `item_id`.

## GAP-7. `code` единицы измерения не отдаётся публичными схемами

- Факт: модель `units` имеет `code`, но `UnitDto` (`/catalog/units`) и
  `UnitResponse` (admin) его не выводят. Сопоставление единиц идёт по
  `name`/`symbol` — достаточно для MVP.
- Нужно на сервере (опционально): добавить `code` в `UnitDto` для
  машинного сопоставления ОКЕИ.

## GAP-8. Запрос на добавление новой позиции каталога — ОТСУТСТВУЕТ (для роли storekeeper)

- Факт: создание позиций — `/api/v1/catalog/admin/*` (chief_storekeeper/root);
  временные позиции создаются только внутри draft через inline
  `temporary_item` (только RECEIVE, требует `client_request_id`) —
  в MVP скилла отключено.
- Fallback: строка остаётся unresolved; кладовщику предлагается выбрать
  существующую позицию или передать список новых позиций старшему
  кладовщику (вне скилла).
- Нужно на сервере (опционально): эндпоинт «запрос на новую позицию»
  (модерируемый) либо осознанное включение inline `temporary_item`
  в скилле отдельной конфигурационной опцией.
