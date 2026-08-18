# WORKFLOW — сценарий помощника кладовщика

Распознавание выполняется встроенными скиллами Hermes
(`ocr-and-documents`, `pdf`, `xlsx`, vision модели). Собственный OCR
не реализуется. Этот скилл отвечает за: складской диалог, структурирование,
сопоставление каталога, безопасные вызовы `warehouse_api.py`, draft,
обработку доменных ошибок.

## 0. Получение файла

1. Немедленно подтвердить получение («Файл получен, распознаю…»).
2. Не спрашивать «что это?» до попытки распознавания.
3. Создать дело:
   `python ${HERMES_SKILL_DIR}/scripts/warehouse_api.py case init --file <путь>`
   - `duplicate=true` → сообщить: «Этот файл уже обрабатывался. Дело: …,
     Черновик: …. Создать новое дело или открыть существующее?»
     Второй draft автоматически НЕ создавать.
   - `duplicate=false` → запомнить `case_id`, `case_dir`, `sha256`.

## 1. Распознавание (RECOGNIZING)

Обновить состояние: `case set-state --case-id <id> --state RECOGNIZING`.

Распознать встроенными средствами Hermes и сохранить в дело
`extracted_document.json` по схеме `schemas/extracted_document.schema.json`:
тип документа, номер, дата, поставщик/отправитель, получатель, склад,
строки (`raw_name`, `quantity`, `unit_raw`, `price`, `amount`, `confidence`),
warnings. SHA-256 файла — из шага 0.

Показать краткое резюме и спросить назначение **одним сообщением**:

> Распознана накладная №154 от 03.08.2026. Поставщик: ООО «Стройресурс».
> Найдено 27 строк.
> Что подготовить: 1 — приход; 2 — перемещение; 3 — выдачу; 4 — списание;
> 5 — только сохранить распознавание.

Если пользователь сразу написал назначение («Оформить приход на Угдан») —
не спрашивать повторно. Сохранить `intent.json`
(схема `schemas/operation_intent.schema.json`), состояние `MATCHING_CATALOG`.

## 2. Сопоставление каталога (MATCHING_CATALOG)

1. Площадка: `sites list` → выбрать `site_id` (по названию из intent или
   `default_site` из `capabilities`). Неоднозначность — в пакет вопросов.
2. Единицы: `units list` → сопоставление `unit_raw` ↔ `unit_symbol`/`name`.
3. Для каждой строки: `catalog search --query "<raw_name>"`.
   - Ровно 1 результат и высокая уверенность → `item_id`.
   - Несколько похожих (warning `catalog_ambiguous`) → **не считать первую
     точным совпадением** → кандидаты в пакет вопросов.
   - 0 результатов (`catalog_empty`) → строка unresolved.
4. Сохранить `catalog_matches.json`: `raw_name`, `item_id` (отдельно!),
   кандидаты, уверенность.

## 3. Пакет уточнений (NEEDS_CLARIFICATION)

Все вопросы — **одним пакетом**, не по одному на строку:

> Осталось три уточнения:
> 1. «Подшипник 6205»: 1 — открытый; 2 — 6205-2RS.
> 2. В строке 14 количество похоже на 10 или 70.
> 3. «Шланг кислородный» отсутствует в каталоге.
> Ответ: 1=2, 2=10, 3=оставить неразрешённой.

Создание новой позиции каталога в MVP отключено: unresolved-строка либо
сопоставляется существующей, либо остаётся unresolved (в черновик не
включается, перечисляется в финальном резюме).

## 4. Создание/обновление draft (CREATING_DRAFT)

Собрать `draft_request.json` (схема `schemas/draft_request.schema.json`),
включая `source_document.source_ref = "sha256:<hash файла>"` — это даёт
серверную дедупликацию повторной отправки.

```
python ${HERMES_SKILL_DIR}/scripts/warehouse_api.py draft create --input draft_request.json
```

- Используется `POST /api/v1/operations/from-source-document`: строки несут
  `item_id` + **`source_item_name`** (raw-имя из документа) — это
  предпочтительное структурированное поле.
- Для обычного `POST /api/v1/operations` сервер `OperationLineCreate`
  поле `source_item_name` **не принимает** (ограничение API).
  В этом случае raw_name сохраняется в `comment` как запасной путь. При
  add-lines к source-document черновику через PATCH то же ограничение:
  `_response_line_to_request` копирует `source_item_name` в `comment`.
- Строки без `item_id` клиент не отправляет (warning
  `line_unresolved_skipped`). Они **не исчезают**: ответ содержит
  `_unresolved_count`, `_unresolved_lines` (line_number, raw_name),
  `_draft_partial: true`.
- 409 `source_document_idempotency_conflict` → значит, по этому файлу уже
  есть draft с ДРУГИМ составом: показать конфликт пользователю, открыть
  существующий черновик через `draft list-own` / `draft get`, не создавать
  новый молча.
- Добавить строки позже: `draft add-lines --draft-id … --input lines.json`.
- Исправить строку: `draft update-line --draft-id … --line-number 14 --qty 70`.
- Проверить: `draft validate --draft-id …` (локальная валидация: позиции
  активны, qty>0, для расходных типов — достаточность остатков).
- Состояние дела: `case set-state --state DRAFT_READY --draft-id <uuid>`.
  Сохранить `draft_result.json` с полями `draft_id`, `display_number`,
  `draft_partial`, `unresolved_count`, `unresolved_lines`.

Ограничение API: PATCH заменяет строки целиком (id перевыпускаются,
source_*-снимки не пересылаются — raw_name сохраняется в comment).
См. API_GAPS.md.

## 5. Финальное резюме (DRAFT_READY)

Если `draft_partial: true` — **запрещено** говорить «черновик готов
полностью» или «операция готова». Использовать формулировку:

> Черновик D-184 подготовлен (ЧАСТИЧНЫЙ: 2 из 27 строк не сопоставлены).
> Склад: Угдан. Документ: №154 от 03.08.2026.
> Сопоставлено автоматически: 24. Уточнено: 1. Не разрешено: 2
> (шланг кислородный — стр.3, прокладка М20 — стр.18).
> Операция не проведена. Для проведения и дополнения откройте черновик в Warehouse.

Если все строки сопоставлены:

> Черновик D-184 подготовлен. Склад: Угдан. Документ: №154 от 03.08.2026.
> Позиций: 27. Операция не проведена. Для проведения откройте черновик
> в Warehouse.

Скилл НИКОГДА не проводит операцию (submit/accept/cancel запрещены
и в SKILL.md, и в allowlist клиента).

## Маппинг назначения документа → тип операции

| Ответ пользователя | operation_type |
|---|---|
| 1 — приход | `RECEIVE` |
| 2 — перемещение | `MOVE` (нужны source_site_id и destination_site_id) |
| 3 — выдача | `ISSUE` |
| 4 — списание | `WRITE_OFF` |
| 5 — только распознать | draft не создаётся, состояние `DRAFT_READY` не наступает |

## Состояния дела

`RECEIVED → COLLECTING_PAGES → RECOGNIZING → WAITING_FOR_INTENT →
MATCHING_CATALOG → NEEDS_CLARIFICATION → CREATING_DRAFT → DRAFT_READY`
(+ `FAILED`, `CANCELLED`). Хранятся в `case_state.json`, обновляются
командой `case set-state`. В `case.log` (если агент его ведёт) запрещено
писать токены и auth-заголовки.
