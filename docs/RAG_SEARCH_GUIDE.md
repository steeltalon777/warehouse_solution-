# RAG Search Guide: Kalm + Qdrant

Документ описывает, как агентам искать информацию в коде через
семантический поиск на базе Kalm-эмбеддингов в Qdrant.

Скрипт: `/home/makc/AI_sandbox/code-search/code_search_cli.py`.

---

## 1. Когда использовать RAG

**Использовать RAG** для быстрого поиска:

- места формирования / обработки конкретной ошибки,
- цепочки вызовов в одном сервисе или слое,
- класса / метода, отвечающего за поведение X,
- фикстур и тестов на конкретный сценарий,
- схем / DTO / serializer'ов для сущности.

**Не использовать, идти в grep / Read напрямую**, когда:

- известно точное имя символа или точная строка,
  `grep -n "name" path` быстрее и точнее;
- нужно увидеть **весь файл** целиком (контекст класса, не один метод);
- вопрос про абстрактные архитектурные термины
  («dual-response contract», «BFF boundary», «ownership split») —
  dense-поиск Kalm их не ловит, нужен ручной просмотр и обсуждение;
- нужен UI HTTP-вызов из Angular по смысловому описанию
  («отправляет в Django») — Kalm тащит state-методы,
  лучше `grep -n "httpClient\.\|\.post\|submit" src/app/core/services/`.

---

## 2. CLI

```bash
~/AI_sandbox/code-search/code_search_cli.py \
  "поисковый запрос" \
  --collection NAME \
  --limit N \
  [--show-code]
```

| Флаг | Назначение |
|---|---|
| `query` (позиционный) | Запрос на русском или английском |
| `--collection` | **Всегда указывать явно.** Дефолт = `syncserver_code_v1`, это частая причина промахов |
| `--limit` | Сколько чанков вернуть. 8–10 обычно достаточно, больше — шум |
| `--show-code` | Печатать тело чанка. Полезно для верификации top-3 |

---

## 3. Коллекции

| Репа | Коллекция | Что внутри |
|---|---|---|
| `SyncServer/` | `syncserver_code_v1` | FastAPI сервисы, схемы, репо, доменные ошибки, тесты |
| `Warehouse_web/` | `warehouse_web_code_v1` | Django views, BFF (`apps/sync_client/`), admin, шаблоны |
| `Warehouse_frontend/` | `warehouse_frontend_code_v1` | Angular: services, components, features, e2e |

Проверка состояния коллекции:

```bash
curl -s http://127.0.0.1:6333/collections/warehouse_frontend_code_v1 |
  jq '.result | {status, points_count, indexed_vectors_count}'
```

`indexed_vectors_count: 0` означает, что HNSW-индекс не построен и поиск
идёт linear scan. На ~1000 точках это не блокер, но запуск
`update_collection` или рестарт Qdrant ускоряет поиск.

---

## 4. Стратегии по типу вопроса

### 4.1. Точный поиск (где формируется X)

1. Указать коллекцию **явно**.
2. Использовать **русский + технические термины**
   («где формируется сообщение для 409 от SyncServer»).
3. Проверить top-3 через `--show-code`: если это тест или e2e-хелпер —
   переформулировать («функция обработки», «error handler»).
4. **Верифицировать** путь: `apps/` = Warehouse_web,
   `app/` = SyncServer, `src/app/` = Angular.
   Путь в чанке должен соответствовать ожидаемой репе.

### 4.2. Причинный (почему X теряется / ломается)

Хорошо работает в одной коллекции.
Формулировка с причинно-следственным языком:
«почему теряет», «откуда берётся», «что вызывает».
Score 0.50–0.60 обычно даёт правильный класс ошибки / исключения.

### 4.3. Сквозной поток (SyncServer → Django → Angular)

Делать **3 вызова CLI** (по одному на коллекцию), склеивать руками.

Альтернатива: искать «точку склейки» —
BFF error handler (`apps/common/api_error_handler.py:48-108`)
или Angular `normalizeError`
(`src/app/core/services/operations.service.ts:971-982`),
потом прыгать по call-sites.

Без merged retrieval — дорого по токенам, но работает.

### 4.4. Архитектурный (где нарушается контракт)

⚠️ **Слабое место Kalm.** Абстрактные имена контрактов не ловятся.

Алгоритм:

1. Сначала уточнить у пользователя определение термина.
2. Если нужно всё-таки искать — формулировать через **конкретные паттерны**:
   «где возвращается и JSON, и HTML», «где есть два response объекта»,
   «где один endpoint отвечает по-разному».
3. Допускать fallback на ручной просмотр каталогов сервисов.

### 4.5. Изменение (какие файлы менять для X)

Хорошо работает в одной репе.

Искать в порядке:

1. Существующие аналоги (класс / схема похожего домена).
2. Точку `raise` в сервисе.
3. Envelope / DTO в schemas.
4. Маппинг в BFF — отдельный запрос с `--collection warehouse_web_code_v1`.
5. UI-модель в Angular — отдельный запрос с `--collection warehouse_frontend_code_v1`.

Kalm не умеет перечислять «все места, которые придётся тронуть» —
он ищет по семантике. Поэтому 2–3 прохода по разным коллекциям.

### 4.6. Негативный тест (опровержение ложной гипотезы)

Работает как **молчаливое опровержение**:
если в top-K нет подтверждений гипотезе — её нет в коде.

Проверить, что искали **в правильной коллекции**.
Гипотеза «в Warehouse_web есть локальный ORM каталог» проверяется
в `warehouse_web_code_v1`, не в `syncserver_code_v1`.

Не интерпретировать «не нашлось» как «не существует» без проверки:
возможно, термин в коде назван иначе.

---

## 5. Подводные камни — обязательно фильтровать

| Шум | Где | Что делать |
|---|---|---|
| `module tests/test_x.py:1-1` (1 токен) | Python | Бесполезный чанк-призрак. Игнорировать или просить индексатор объединить с docstring модуля |
| `module_manifest ... envelope.fixtures.ts` | Angular | То же. Часто самый длинный чанк в файле, забивает top-K |
| `inline_template ComponentName.inline_template` (500–900 токенов) | Angular | HTML-шаблоны попадают в выдачу наравне с сервисами. Если ищем логику — пропускать |
| `e2e/... openCreateModal`, `makeEnvelope` | Angular e2e | Тестовые хелперы. Понизить приоритет, если ищем продакшен-код |
| `indexed_vectors_count: 0` в Qdrant | Все коллекции | HNSW не построен → linear scan. Не баг, но триггернуть `update_collection` для ускорения |

---

## 6. Проверка результата перед использованием

1. **Путь соответствует репе**: `apps/` ≠ `app/` ≠ `src/app/`.
2. **Score в диапазоне 0.50–0.70** для русского mix — норм.
   Ниже 0.40 — скорее мимо.
3. **Top-1 — не тест и не e2e-хелпер**. Если да — переформулировать.
4. **Размер чанка разумный** (50–900 токенов). 1-токенный или
   2000-токенный — подозрительно.
5. **Прочитать 2–3 чанка через `Read`** с указанным `file_path:offset`,
   чтобы убедиться, что это именно то, что нужно.
6. **Если ничего не нашлось** — попробовать:
   (а) сменить коллекцию,
   (б) английскую формулировку,
   (в) более узкий / широкий запрос.
   Если всё равно пусто — идти в `grep` / `Read`.

---

## 7. Чего НЕ ждать от RAG

- Одним запросом не нарисовать сквозной поток через 3 репы — будет 3 прохода.
- Не получится спросить «почему архитектурное решение такое» —
  dense-поиск не работает на обоснованиях.
- Не получится «найди все места, где нужно поменять X» —
  это требует статического анализа зависимостей, не эмбеддингов.
- Не получится доверять score > 0.65 как «точно правильный ответ» —
  Kalm иногда даёт высокий score семантически близким, но нерелевантным
  чанкам (например, тестам с говорящим именем).

---

## 8. Шаблон использования в агенте

```bash
# 1. Точечный поиск с явной коллекцией
~/AI_sandbox/code-search/code_search_cli.py \
  "где Django BFF маппит 409 ConflictError в пользовательское сообщение" \
  --collection warehouse_web_code_v1 --limit 8

# 2. Верифицировать top-1 через Read
# (по file:line из выдачи)

# 3. Если нужен сквозной — повторить для других коллекций
~/AI_sandbox/code-search/code_search_cli.py \
  "ConflictError response" \
  --collection syncserver_code_v1 --limit 5

~/AI_sandbox/code-search/code_search_cli.py \
  "Angular normalizeError для 409 от Django" \
  --collection warehouse_frontend_code_v1 --limit 5

# 4. Склеить цепочку в ответе пользователю
```

---

## 9. Известные точки склейки (якоря)

Эти чанки часто возникают в выдаче по смежным темам
и могут служить опорными точками для сквозного поиска:

| Слой | Якорь | Коллекция |
|---|---|---|
| SyncServer: доменные ошибки | `app/api/exceptions.py` (классы `ConflictError`, `ValidationError`, `NotFoundError`) | `syncserver_code_v1` |
| SyncServer: envelope доменных ошибок | `app/schemas/operation_submit_error.py:98-106 ProblemEnvelope` | `syncserver_code_v1` |
| SyncServer: детали ошибки остатка | `app/services/operation_submit_errors.py` (`InsufficientStockError._detail`, `InsufficientIssuedBalanceError._detail`) | `syncserver_code_v1` |
| SyncServer: cancel-flow rollback дефицит | `app/services/operations_service.py:2511-2775` (`OperationsService.cancel_operation`) + `_check_cancel_balance_sufficiency` (новый) — см. ADR-0027 | `syncserver_code_v1` |
| Django BFF: OperationCancelView mapping | `apps/bff_api/operations_views.py:393-417` (`OperationCancelView.post`) → `api_error_response` (ADR-0027 §7.1) | `warehouse_web_code_v1` |
| Django BFF: маппинг исключений | `apps/sync_client/exceptions.py` (`SyncConflictError`, `SyncValidationError`, `SyncBackendUnavailable`) | `warehouse_web_code_v1` |
| Django BFF: error handler | `apps/common/api_error_handler.py:48-108 APIErrorHandler.handle_api_error` | `warehouse_web_code_v1` |
| Angular: нормализация ошибки | `src/app/core/services/operations.service.ts:971-982 OperationsService.normalizeError` | `warehouse_frontend_code_v1` |
| Angular: отображение ошибки | `src/app/features/operations/components/operation-create-modal/submit-error-toasts.ts` (`GENERIC_SUBMIT_ERROR_TOAST`, `lineGroupToast`, `formatSubmitStockHint`) | `warehouse_frontend_code_v1` |

---

## 10. Дальнейшие улучшения (TODO для индексатора)

1. **Merged retrieval**: флаг `--repos syncserver+warehouse_web+warehouse_frontend`
   с автоматическим merge и de-dup top-K.
2. **Коллекция по умолчанию**: убрать или сделать обязательным аргументом.
3. **Фильтр мусора**: чанки `module tests/test_x.py:1-1` и
   `module_manifest` либо объединять с docstring, либо выкидывать.
4. **Алиасы архитектурных терминов** в индексаторе
   («dual-response contract», «BFF boundary», «ownership split»).
5. **Понижение веса inline_template** в Angular-индексации,
   разбиение HTML-чанков по структурным блокам.
6. **Отдельный namespace для `e2e/`** с пониженным весом.
7. **Алиасы HTTP-абстракций** в Angular: «отправляет в Django» →
   `*.service.ts:*.submit*` или `httpClient.post`.