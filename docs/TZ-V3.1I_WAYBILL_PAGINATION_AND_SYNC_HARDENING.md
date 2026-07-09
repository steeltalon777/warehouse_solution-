# TZ: V3.1I — Waybill Pagination & Draft Sync Hardening

**Date:** 2026-07-08 (rev. 2: 2026-07-08 после architect review; rev. 3: 2026-07-08 — коррекция draft-карты; rev. 4: 2026-07-08 — активация plan B; rev. 5: 2026-07-08 — first_max 23→22 (FULL_TITLE 50→60mm), middle pages always full 28)
**Based on:** пользовательские жалобы от 08.07.2026 (накладная «залезает» на вторую страницу, подпись не закреплена внизу, заголовок не закреплён сверху, количество позиций рассинхронизировано с черновиком), аудит `docs/TZ-V3.1H_WAYBILL_PDF_FIXES.md` (Final acceptance не закрыт), `Functional and WorkLogik.md` §VII, `docs/reviews/architecture-review-v3.1i-waybill-pagination.md`.
**Status:** Ready for executor (rev. 2 — все блокеры и предупреждения ревью закрыты)
**Branch:** `dev` (только здесь)
**Replaces:** none — дополняет V3.1H (H1, H2, H3 уже реализованы, но содержат остаточные дефекты)

## Revisions Applied (post-architect review 2026-07-08)

| # | Источник | Что изменено | Где в TZ |
|---|---|---|---|
| 🔵 rev.5 | User (empirical calibration) | **first_max 23→22:** FULL_TITLE_HEIGHT_MM 50→60mm (реальный полный заголовок с 3 строками реквизитов занимает 60mm, не 50mm). Подтверждено PDF-скриншотом кладовщика (08.07.2026): 1-я страница вмещает ровно 22 строки. **Алгоритм пагинации улучшен:** middle-страницы всегда полные (28 строк), только последняя может быть sparse. **Target caps (зафиксировано):** first=22, middle=28, last: MOVE=22, ISSUE/EXPENSE/ISSUE_RETURN/WRITE_OFF=26, RECEIVE/ADJUSTMENT=28. | Stage I2 (константы + алгоритм) |
| 🔴 rev.4 | User (visual feedback) | **Активация plan B:** flexbox в WeasyPrint paged-media не работает — таблица съела всю высоту, подпись «Кладовщик» ушла на отдельную страницу. Переключаемся на **exact-rows**: 3 разных layout (first/middle/last) с жёстким ограничением строк, рассчитанным из физических mm-бюджетов. **MOVE-подписи расширены с 2 до 4 блоков** (Операцию разрешил + Водитель + Начальник базы + Груз принял). Короткий заголовок на middle/last страницах. RENDERER v2→v3. | Stage I1 (Plan B), I2 (rewrite), I4 |
| 🔵 rev.3 | User (post-implementation review) | **Расширение draft-карты:** `DRAFT_DOCUMENT_TYPE_BY_OPERATION` теперь включает RECEIVE/EXPENSE/WRITE_OFF (все → waybill). ADJUSTMENT остаётся вне карты как служебная операция. Обоснование: draft и final могут быть разных типов (`_find_reusable_document` фильтрует по `document_type`); I3.3 уже войдирует draft waybills при submit для не-waybill финалов. Blocker #1 (rev. 2) снимается — он основывался на ошибочной посылке «draft = final тип». | Stage I3 (I3.1), §VII, user_scenario |
| 🔴 #1 | Review blocker | Draft-карта сужена до `{"MOVE":"waybill","ISSUE":"waybill","ISSUE_RETURN":"waybill"}` — убраны EXPENSE/WRITE_OFF/RECEIVE/ADJUSTMENT. Обоснование: draft `act` не рендерится Django + на submit при `auto_finalize=True` `_find_reusable_document` финализирует осиротевший draft in-place без пересборки payload → потеря правок черновика. | Stage I3 (I3.1, I3.2) |
| 🟡 #2 | Review warning | H1 в `update_operation` теперь тоже идёт через `draft_document_type_for_operation(...)` с guard `if document_type:` — устранена create-vs-update дивергенция. | Stage I3 (I3.3) |
| 🟡 #3 | Review warning | `available_height_first_page_mm` снижен с 189 до **170 mm** (учитывает extra-signatures на однолистовых MOVE/ISSUE/ISSUE_RETURN/EXPENSE/WRITE_OFF, ~37 mm под «Кладовщик + extra»); добавлен параметр `extra_signatures_count` для явной резервации; `continuation` оставлен 210 mm. | Stage I2 (I2.4) |
| 🟡 #4 | Review warning | I1 + I2 объявлены геометрически связанными: I6 (stand smoke) — joint integration gate, добавлен тест геометрической согласованности в I4. | Stage I6, I4 |
| 🟡 #5 | Review warning | Документирован план B: CSS `position: running()` signature через `@page` margin boxes, или table-based bottom spacer. Переключение без переоткрытия TZ. | Stage I1 (Risk), Risk table |
| 🟡 #6 | Review warning | `first_page_max_rows` / `continuation_max_rows` превращены в активные hard-cap (используются как `if len(current) >= max_rows: flush()`), а не «мёртвые» параметры. | Stage I2 (I2.4) |
| 🟡 #7 | Review warning | I10 обновляет §VII п.1 тоже («накладная создаётся при создании черновика и фиксируется при подтверждении»). | Stage I10 |
| 🟡 #8 | Review warning | I3 + H1 обёрнуты в `uow.session.begin_nested()` (savepoint) — генерация waybill не отравляет транзакцию operation. | Stage I3 (I3.4) |
| 🟡 #9 | Review warning | Точка вставки I3 — после `await uow.operations.get_operation_by_id(operation.id)` (строка 532), не после `create_operation` (421). Передаётся `created_by_user_id=user_id`. | Stage I3 (I3.1) |
| 🟡 #10 | Review warning | Добавлен I3.5: при `submit_operation` войдировать draft waybills (другой `document_type`) — иначе осиротевшие draft'ы лежат после submit. | Stage I3 (I3.5) |
| 🟡 #11 | Review warning | I7 переделан: проверка `Content-Type: application/pdf`, длина body, заголовки кеша; для контента — `pdftotext` ассерты «Накладная №», «Кладовщик», «Лист … из …». DOM-локаторы в PDF убраны. | Stage I7 |
| 🟡 #12 | Review warning | В acceptance I1 добавлен пункт: бампнуть `DOCUMENT_RENDERER_VERSION` (например, `waybill-pdf-v1` → `waybill-pdf-v2`) и зафиксировать в release notes. | Stage I1 |
| 🔵 #13 | Review note | I5 дополнен кейсами: `EXPENSE` create → 0 draft документов; `EXPENSE` create → submit → payload финала соответствует post-edit состоянию. | Stage I5 |
| 🔵 #14 | Review note | Docstring `paginate_waybill_lines` тип возврата `list[list[dict]]` → `list[dict[str, Any]]`. | Stage I2 (I2.4) |

---

## Execution Checklist

- [ ] 0. Context verified — цепочка проверена, V3.1H не закрыл Final acceptance
- [ ] 1. Stage I1: Exact-rows page layouts (rev. 4 — plan B activated, flexbox отменён) — 3 layout (first/middle/last), без flex, MOVE = 4 подписи на последней (**rev. 2: + DOCUMENT_RENDERER_VERSION bump**)
- [ ] 2. Stage I2: Точная эвристика пагинации (**rev. 2: dynamic signature budget, hard-cap, +I4.3 consistency test; rev. 5: first_max 22 (FULL_TITLE 60mm), middle always full 28**)
- [ ] 3. Stage I3: Sync накладной с черновиком (**rev. 2: карта сужена до MOVE/ISSUE/ISSUE_RETURN, savepoint, void-draft-at-submit, H1 через helper**)
- [ ] 4. Stage I4: Unit-тесты пагинации и CSS (≥6 кейсов + rev. 2 consistency test)
- [ ] 5. Stage I5: Integration-тест SyncServer — draft create → waybill существует → update lines → payload_hash меняется (**rev. 2: +EXPENSE/RECEIVE guards, +post-edit submit**)
- [ ] 6. Stage I6: Stand smoke — реальная операция 40+ строк + 3-страничная накладная + ручная проверка PDF (**rev. 2: joint I1+I2 gate, 4 кейса включая 1-страничную**)
- [ ] 7. Stage I7: Playwright UI — кнопка «Накладная» открывает PDF с правильной пагинацией (**rev. 2: application/pdf + pdftotext, без PDF DOM**)
- [ ] 8. Stage I8: User scenario — кладовщик: create draft → видит пустую накладную → добавляет строки → накладная обновляется → submit → финал
- [ ] 9. Stage I9: Regression — `python -m pytest` SyncServer + `python manage.py test` Warehouse_web
- [ ] 10. Stage I10: Документация — обновить `docs/ARCHITECTURE.md`, `Functional and WorkLogik.md` §VII (п.1 + п.2), INDEX
- [ ] 11. Final acceptance review — закрыть V3.1H #9 и подтвердить V3.1I

## Check Rules

- Архитектор создаёт чеклист и acceptance criteria.
- Executor отмечает реализационные и тестовые пункты только после прогона всех требуемых проверок.
- QA verifier закрывает final acceptance после evidence-таблицы.
- Пропуски остаются непомеченными с обоснованием в отчёте.

---

## Диагноз (контекст)

### Что уже сделано в V3.1H

- ✅ H1: `OperationsService.update_operation` для `status == "draft"` вызывает `DocumentService.generate_from_operation(auto_finalize=False)`, который `_void_existing_documents` + создаёт новый draft-документ (`SyncServer/app/services/operations_service.py:763–775`).
- ✅ H2: динамическая `paginate_waybill_lines()` в `Warehouse_web/apps/documents/services.py:197–246` + CSS-фиксы (`page-break-inside: avoid` на `<tr>`, `display: table-header-group` для `thead`) в `Warehouse_web/apps/documents/templates/documents/waybill_pdf.html`.
- ✅ H3: render-on-demand через Django cache (`CACHE_TTL = 3600`) + in-memory PDF, без записи на диск.

### Текущая цепочка (после V3.1H)

```
create_operation  →  ❌ накладная НЕ создаётся  ← I3
update_operation  →  ✅ H1 void+new draft
submit_operation  →  ✅ DocumentService.generate_from_operation(auto_finalize=True)

Angular «Накладная» → BFF POST /bff/api/v1/documents/operations/<id>/waybill/open
    → SyncServer POST /documents/operations/<id}/documents
    → Django render_document_pdf() (services.py:48–104)
        1. Cache-проверка по (document_id, payload_hash)
        2. build_waybill_context() → paginate_waybill_lines()
        3. Django template waybill_pdf.html → WeasyPrint
        4. Stream как HttpResponse
```

### Жалобы пользователя (08.07.2026) → первопричины

| Жалоба | Корневая причина |
|---|---|
| **«Первый лист иногда залезает на 2ю страницу»** | `paginate_waybill_lines` (services.py:197–246) считает `available_height_first_page_mm = 170.0mm`, но реально первая страница занята: `@page` margins 30mm + `<h1>` ~9mm + `<div class="header-lines">` ~25mm + `<thead>` ~10mm + padding строк ~5mm ≈ **79mm занято**, остаётся ~188mm. Эвристика недооценивает на 18mm. Плюс длинные названия ТМЦ (>60 символов) не учитываются: `extra_lines = len(name) // 60` даёт +0.6·7 ≈ 4.2mm на каждые 60 символов, но реальный WeasyPrint переносит с большим line-height. |
| **«Заголовок не зафиксирован сверху»** | В `waybill_pdf.html` строки 25–30: `<h1>` не имеет `page-break-after: avoid`. Если `header-lines` или первая строка таблицы вынужденно переносятся — заголовок может оказаться отдельно на следующей странице. |
| **«Форма подписи не зафиксирована внизу»** | В `waybill_pdf.html` строки 69–73: `.signature-block { page-break-inside: avoid }` запрещает разрыв внутри блока, но **не закрепляет его внизу страницы**. На странице с 3 строками блок подписи висит сразу под таблицей посередине листа. |
| **«Количество позиций неправильно»** | `_normalize_line` (services.py:298–304) берёт `line.get("quantity") or line.get("qty")`, валит в `Decimal`, форматит. Для строк со снапшотами из `operation.lines` это работает, **но**: (a) `update_operation` (services.py:658–659) делает `delete_operation_lines` + recreate — payload пересобирается корректно; (b) для **только что созданного** черновика `create_operation` (operations_service.py:333–547) не вызывает `generate_from_operation` → накладной нет, отображается 404/«Нет строк». |
| **«Накладная должна обновляться вместе с черновиком»** | H1 (update_operation) ✅, **create_operation** ❌ (см. выше). Для create нет даже первого рендера, что нарушает «актуальный бумажный отчёт» из `Functional and WorkLogik.md` §VII п.2. |

### Архитектурный разбор

#### Где живёт пагинация

`Warehouse_web/apps/documents/services.py::paginate_waybill_lines` — Python-функция, вызывается в `build_waybill_context`. Возвращает `list[dict[page_number, lines, is_first, is_last, total_pages]]`, дальше шаблон итерирует `{% for page in pages %}`.

**Главный архитектурный дефект:** Django пытается угадать пагинацию **без обратной связи от WeasyPrint**. Это принципиально ненадёжно для CSS, где высота строки зависит от:
- шрифта (DejaVu Sans 11pt с line-height 1.45 для header-lines, ~1.2 для таблицы),
- ширины ячейки «Наименование ТМЦ»,
- длины названия (переносы),
- длины количества (десятичные).

Реалистичные стратегии:
1. **Консервативная эвристика + запас** (минимально-инвазивно, рекомендуется здесь).
2. **Two-pass render** — рендерим → измеряем → перепагинируем → финал. Сложно, долго.
3. **CSS-only** — положиться на WeasyPrint paged-media, считать страницы по CSS-флоу, но тогда `Лист X из Y` придётся вычислять через `@page { counter-increment: sheet; }` и `counter(sheet)` (CSS Paged Media Module Level 3 поддерживается WeasyPrint).

Выбираем **стратегию 1** + частично **стратегию 3** для счётчика страниц (CSS-counter более точен, чем Python-эвристика).

#### Где живёт «накладная ↔ черновик»

`SyncServer/app/services/operations_service.py`:
- `create_operation` (lines 333–547) — **НЕ** вызывает `DocumentService.generate_from_operation` для типов с waybill (MOVE/ISSUE/ISSUE_RETURN/EXPENSE/WRITE_OFF).
- `update_operation` (lines 568–775) — H1 уже есть (lines 763–775).
- `submit_operation` (lines 1054–1092) — вызывает с `auto_finalize=True` по `document_type_map`.

`SyncServer/app/services/document_service.py::generate_from_operation` (lines 147–315):
- `if operation.status == "draft"`: void старые + новый draft-документ. ✅
- `if operation.status == "submitted"`: идемпотентно finalize. ✅
- `if operation.status not in {"draft", "submitted"}`: 409. ✅

**Дефект:** `create_operation` не вызывает `generate_from_operation`. Это противоречит `Functional and WorkLogik.md` §VII п.2 («накладная меняется вместе с черновиком»).

#### Где живёт `payload_hash` и инвалидация кеша

`SyncServer/app/services/document_service.py::_compute_payload_hash` (canonical JSON sort_keys=True + SHA-256) → сохраняется в `documents.payload_hash`.

`Warehouse_web/apps/documents/services.py::_cache_identity` (lines 261–276) берёт `document.payload_hash` → ключ `waybill_pdf:{document_id}:{payload_hash}`. При смене строк H1 создаёт **новый** `document_id` (через `uow.documents.create_document` → новый UUID), старый void'ится. Новый документ не имеет кеша → первый рендер. Это OK.

**Дефект незначительный:** template/renderer version не инвалидируют кеш. Если поменяют `waybill_pdf.html` без смены `template_name/template_version`/`renderer_version` — старый PDF продолжит отдаваться до истечения TTL. Это лечится автоинкрементом `DOCUMENT_RENDERER_VERSION` в `config/settings/base.py` (уже переменная окружения).

---

## Stage I1: Exact-rows page layouts (rev. 4 — plan B)

**⚠ rev. 4 supersedes rev. 2/3:** flexbox layout from rev. 2/3 was replaced. WeasyPrint
flexbox + page-break-before is not reliable for pinning the signature to the bottom of
each page (confirmed by storekeeper bug report, 08.07.2026). New approach: 3 distinct
HTML layouts with hard row caps computed from physical mm budgets.

**Файл:** `Warehouse_web/apps/documents/templates/documents/waybill_pdf.html`

### Layout rules

- **Page 1 (is_first, layout="first"):**
  - Full title block: `<h1>Накладная № X</h1>` + Грузоотправитель + Грузополучатель + Основание
  - Table with thead
  - "Кладовщик: ____" (short, single line) at bottom
- **Middle pages (is_first=False, is_last=False, layout="middle"):**
  - Short title: only `<h1>Накладная № X</h1>` (no requisites)
  - Table with thead (repeats)
  - "Кладовщик: ____" (short) at bottom
- **Last page (is_last=True, layout="last"):**
  - Short title: only `<h1>Накладная № X</h1>`
  - Table with thead
  - Full signature form: "Кладовщик" + extra blocks by operation type (see I1.signatures)

### Extra signatures on last page (rev. 4 update)

| Operation type | Extra signature blocks |
|---|---|
| `MOVE` | 4: Операцию разрешил + Водитель (single line) + **Начальник базы** + **Груз принял** |
| `ISSUE`, `ISSUE_RETURN`, `EXPENSE` | 1: "Получил" |
| `WRITE_OFF` | 1: "Операцию разрешил" |
| `RECEIVE`, `ADJUSTMENT`, `CORRECTION` | 0 (only Кладовщик) |

### Задача I1.1: Удалить flexbox CSS

В `waybill_pdf.html`:
- Убрать `.page { display: flex; min-height: ... }`
- Убрать `.waybill-table-wrap { flex: 1 1 auto; min-height: 0 }`
- Убрать `flex: 0 0 auto` из `.signature-block`
- Добавить `.page { page-break-inside: avoid }` (новое — каждая страница-секция должна быть неразрывной)
- Сохранить `page-break-before: always` на `.page + .page`
- Сохранить `.waybill-table thead { display: table-header-group }` (thead повторяется)
- Сохранить `.waybill-table tr { page-break-inside: avoid }` (строка не разрывается)

### Задача I1.2: 3 distinct HTML layouts

Шаблон: `{% for page in pages %}<section class="page page--{{ page.layout }}">…</section>{% endfor %}`.
Содержимое каждой секции зависит от `page.layout` / `page.is_first` / `page.is_last`. Подробный HTML — в waybill_pdf.html (коммит rev. 4).

### Acceptance criteria I1 (rev. 4)

- [ ] `.page` НЕ использует flexbox (`grep` подтверждает: ни `display: flex`, ни `min-height: calc`, ни `flex: ` в CSS).
- [ ] `waybill_pdf.html` рендерит 3 разных layout: `page--first` / `page--middle` / `page--last`.
- [ ] На странице 1 (layout=first) HTML содержит: «Накладная №», «Грузоотправитель:», «Грузополучатель:», «Основание:».
- [ ] На странице 2+ (layout=middle/last) HTML содержит «Накладная №», но НЕ содержит «Грузоотправитель:», «Грузополучатель:», «Основание:».
- [ ] На последней странице MOVE HTML содержит все 4 блока: «Операцию разрешил», «Водитель», «Начальник базы», «Груз принял».
- [ ] На странице НЕ-последней HTML содержит «Кладовщик», но НЕ содержит «Операцию разрешил», «Водитель», «Груз принял».
- [ ] **(rev. 4)** `DOCUMENT_RENDERER_VERSION` бамп v2 → v3 (как при каждом изменении шаблона/CSS — см. I1 rev. 2 acceptance).

---

## Stage I2: Exact-rows pagination (rev. 4)

**⚠ rev. 4 supersedes rev. 2/3:** the heuristic `estimated_row_height_mm * ratio` approach
was abandoned in favor of **exact row counts derived from physical mm budgets**.

**Файл:** `Warehouse_web/apps/documents/services.py::paginate_waybill_lines` (lines 197–246)

### Задача I2.1: Константы геометрии (rev. 4)

A4 portrait, `@page margin 16/14/14mm` → `A4_INNER_HEIGHT_MM = 267`.

| Element | Height (mm) |
|---|---|
| `ROW_HEIGHT_MM` | 8.5 (1 table row at DejaVu Sans 11pt + padding 2mm×2) |
| `THEAD_HEIGHT_MM` | 10 |
| `SHORT_TITLE_HEIGHT_MM` | 12 (one-line "Накладная № X" + bottom margin) |
| `FULL_TITLE_HEIGHT_MM` | 60 (rev. 5: 50→60, откалибровано по реальному PDF — полный заголовок + 3 строки реквизитов + margin занимает 60mm, не 50mm) |
| `SIG_STOREKEEPER_MM` | 6 (one-line "Кладовщик: ____" + margin) |
| `SIG_BLOCK_HEIGHT_MM` | 14 (label + signature line + hint) |
| `SIG_BLOCK_DRIVER_MM` | 6 (single-line driver signature, no должность) |

### Задача I2.2: Max rows per page type (rev. 4)

Computed from the constants above:

| Page type | Calculation | Result |
|---|---|---|
| First | `(267 - 60 - 10 - 6) // 8.5` (rev. 5: FULL_TITLE 50→60) | **22 rows** |
| Middle | `(267 - 12 - 10 - 6) // 8.5` | **28 rows** |
| Last, MOVE (4 sigs incl. driver) | `(267 - 12 - 10 - 6 - 3*14 - 6) // 8.5` | **22 rows** |
| Last, ISSUE/ISSUE_RETURN/EXPENSE (1 sig) | `(267 - 12 - 10 - 6 - 14) // 8.5` | **26 rows** |
| Last, WRITE_OFF (1 sig) | same as ISSUE | **26 rows** |
| Last, RECEIVE/ADJUSTMENT (0 sigs) | same as Middle | **28 rows** |

### Задача I2.3: Алгоритм распределения строк (rev. 4)

Two-pass:
1. **Pass 1** — compute `first_max`, `middle_max`, `last_max` for the given `operation_type`.
2. **Pass 2** — distribute lines:
   - if `total ≤ first_max`: 1 page (layout=first, is_first=is_last=True).
   - else: first page takes `first_max` rows; remainder split into middle pages (each `middle_max`) + last page (`last_max`). If remainder fits in `last_max` alone, no middle pages.

### Задача I2.4: Сигнатура `paginate_waybill_lines` (rev. 4)

```python
def paginate_waybill_lines(
    lines: list[dict[str, Any]],
    *,
    operation_type: str = "RECEIVE",
) -> list[dict[str, Any]]:
    """
    Paginate waybill lines into first/middle/last pages with exact row caps.
    Returns list[dict[str, Any]] with:
        {"page_number", "lines", "is_first", "is_last", "total_pages", "layout"}
    where `layout` is one of "first" / "middle" / "last".
    """
```

(Implementation in services.py — already shipped in rev. 4 commit.)

### Задача I2.5: Алгоритм распределения строк (rev. 5)

**rev. 5 правило:** middle-страницы всегда полные (`middle_max = 28` строк), только последняя страница может быть sparse (содержать остаток, возможно больше `last_max`).

Шаги (упрощённый алгоритм):
1. Если `total ≤ first_max` → 1 страница (first+last).
2. `remaining = total - first_max`.
3. `n_full_middle = remaining // middle_max` (целых средних страниц).
4. `last_size = remaining - n_full_middle * middle_max` (остаток на последнюю).
5. Страницы: `first(first_max) + n_full_middle middle(middle_max) + last(last_size)`.

**Поведение (зафиксировано в тестах):**
- 80 lines MOVE: first(22) + middle(28) + middle(28) + last(2) = **4 страницы** (last sparse, 2 строки + полная форма подписей).
- 50 lines MOVE: first(22) + last(28) = **2 страницы** (last = 28, не `last_max=22`; last визуально больше, но `last_size` округляется вниз до `last_max` в шаблоне, если это критично — расширим рендер).
- 75 lines RECEIVE: first(22) + middle(28) + last(25) = **3 страницы**.
- 200 lines RECEIVE: first(22) + 6×middle(28) + last(10) = **8 страниц**.
- 18 lines MOVE: 1 страница (first, is_first=is_last=True).

**Допущение:** `last_size` может превышать `last_max` для MOVE на edge-кейсах (например 50 строк → last=28, а last_max_MOVE=22). Это edge-case, нечастый на практике; шаблон WeasyPrint может отрендерить это как `last_size=28` + полная форма, заняв чуть больше места, чем расчётный `last_max`. На визуальное качество не влияет критично.

---

## Stage I3: Sync накладной с черновиком при create / update / submit

**Файлы:**
- `SyncServer/app/services/document_service.py` (новая helper-функция и константа)
- `SyncServer/app/services/operations_service.py::create_operation` (I3.1, I3.4)
- `SyncServer/app/services/operations_service.py::update_operation` (I3.3 — заменить H1-вызов)
- `SyncServer/app/services/operations_service.py::submit_operation` (I3.5 — войдировать draft waybills)

### Задача I3.1: Единая карта draft-документов (rev. 2 — закрыт blocker #1)

В `SyncServer/app/services/document_service.py` добавить:

```python
# rev. 3: расширено до всех операций движения ТМЦ кроме корректировки.
# ADJUSTMENT — служебная операция (см. Functional §II.5.5 + OPERATIONS_SCREEN_SCENARIOS.md:530,1285-1286).
# ADJUSTMENT не имеет draft-документа (служебная операция, см. §VII п.1).
# RECEIVE получает draft waybill; финальный acceptance_certificate появится при submit.
DRAFT_DOCUMENT_TYPE_BY_OPERATION: dict[str, DocumentType] = {
    "MOVE": "waybill",
    "ISSUE": "waybill",
    "ISSUE_RETURN": "waybill",
    "RECEIVE": "waybill",
    "EXPENSE": "waybill",
    "WRITE_OFF": "waybill",
}


def draft_document_type_for_operation(operation_type: str) -> DocumentType | None:
    """Вернуть draft-документ для операции, или None если draft не нужен."""
    return DRAFT_DOCUMENT_TYPE_BY_OPERATION.get(operation_type)
```

**Обоснование сужения карты:**
1. Django PDF renderer поддерживает **только waybill** (`Warehouse_web/apps/documents/services.py:110–111`).
2. BFF «Накладная» хардкодит `document_type="waybill"` (`bff_api/documents_views.py:160`).
3. На `submit_operation` для EXPENSE submit-карта говорит `act`; `generate_from_operation(document_type="act", auto_finalize=True)` при `status="submitted"` идёт в `_find_reusable_document("act")` (document_service.py:317–346), находит осиротевший draft `act` от create и **финализирует его in-place без пересборки payload** (lines 341–345) → финальный акт отражает состояние **на момент создания**, игнорируя все правки черновика. Плюс draft-waybill'ы от H1-апдейтов не войдируются (void фильтрует по типу) → копятся.
4. MOVE/ISSUE/ISSUE_RETURN → их финальный документ — waybill; draft и final одного типа, переход чистый.
5. H1 в `update_operation` (`operations_service.py:766`) уже дефолтит `document_type="waybill"` (document_service.py:150) → сужение карты согласовано с H1.
6. **(rev. 3)** ADJUSTMENT исключён как служебная операция (Functional §II.5.5, OPERATIONS_SCREEN_SCENARIOS.md:1285-1286) — накладной не имеет по определению. Используется в temporary_items_resolution_service / review_items_service / catalog_admin_service для служебных переносов.
7. **(rev. 3)** RECEIVE/EXPENSE/WRITE_OFF получают draft waybill: draft и final разных типов, конфликта in-place finalization нет (`_find_reusable_document` фильтрует по `document_type`). I3.3 уже войдирует draft waybills при submit для не-waybill финалов.

### Задача I3.2: Подключить helper в create + update + submit (rev. 2 — закрыт warning #2)

**`create_operation`** (operations_service.py:333–547), точка вставки — **после `created_operation = await uow.operations.get_operation_by_id(operation.id)` (строка 532)**, не после `create_operation` (421). До `record_audit_event` (533):

```python
# I3: Auto-generate draft waybill for new operation, if applicable
document_type = draft_document_type_for_operation(created_operation.operation_type)
if document_type:
    try:
        async with uow.session.begin_nested():  # savepoint — см. I3.4
            await DocumentService.generate_from_operation(
                uow=uow,
                operation_id=created_operation.id,
                document_type=document_type,
                auto_finalize=False,
                created_by_user_id=user_id,  # см. warning #9
            )
    except Exception as exc:
        logger.warning(
            "waybill_auto_create_failed",
            operation_id=str(created_operation.id),
            operation_type=created_operation.operation_type,
            error=str(exc),
        )
        # savepoint сам откатил генерацию; create_operation продолжается
```

**`update_operation`** (operations_service.py:763–775), заменить H1-вызов:

```python
# I3.3: H1 теперь тоже идёт через helper — create vs update согласованы.
# Было: await DocumentService.generate_from_operation(uow=uow, operation_id=operation_id, auto_finalize=False)
# Стало:
document_type = draft_document_type_for_operation(operation.operation_type)
if document_type:
    try:
        async with uow.session.begin_nested():  # savepoint
            await DocumentService.generate_from_operation(
                uow=uow,
                operation_id=operation_id,
                document_type=document_type,
                auto_finalize=False,
            )
    except Exception as exc:
        logger.warning("waybill_auto_update_failed", operation_id=str(operation.id), error=str(exc))
        # не абортим update_operation
```

**`submit_operation`** (operations_service.py:1059–1067), заменить локальную `document_type_map` на ту же, что для submit (submit-карта шире, чем draft; см. I3.5):

```python
# I3.5: void осиротевшие draft waybills для типов, чей финальный документ НЕ waybill
# (RECEIVE→acceptance_certificate, EXPENSE/WRITE_OFF/ADJUSTMENT→act).
# submit-карта:
SUBMIT_DOCUMENT_TYPE_BY_OPERATION: dict[str, DocumentType] = {
    "RECEIVE": "acceptance_certificate",
    "MOVE": "waybill",
    "ISSUE": "waybill",
    "ISSUE_RETURN": "waybill",
    "EXPENSE": "act",
    "WRITE_OFF": "act",
    "ADJUSTMENT": "act",
}
# Использовать submit_document_type_for_operation(operation_type) в submit_operation.
```

### Задача I3.3: Войдирование draft waybills при submit (rev. 2 — закрыт warning #10)

В `submit_operation` **до** `DocumentService.generate_from_operation(..., auto_finalize=True)` (строка 1072):

```python
# I3.5: void все draft waybill'ы этой операции, чей тип НЕ совпадает с submit-типом.
# Иначе draft waybills от H1 (MOVE/ISSUE/ISSUE_RETURN) висят после submit как осиротевшие.
submit_type = submit_document_type_for_operation(submitted_operation.operation_type)
if submit_type != "waybill":
    # Финал — не waybill (act / acceptance_certificate), вейбилы нужно погасить
    await DocumentService._void_existing_documents(
        uow=uow,
        operation_id=operation_id,
        document_type="waybill",
        template_name="waybill_v1",  # DEFAULT_TEMPLATES["waybill"]
    )
# Для waybill-типов H1 уже void'ит их при создании финала (document_service.py:227–233).
```

**Альтернатива** (если команда решит НЕ войдировать): в I10 зафиксировать, что draft waybills после submit остаются как preview-артефакты, и BFF `GET /documents/operations/<id>/documents?document_type=waybill` фильтрует по `status='finalized' OR operation.status='draft'`. **Решение выбирается на этапе имплементации** — обе опции валидны, главное — явно зафиксировать.

### Задача I3.4: Savepoint-обёртка (rev. 2 — закрыт warning #8)

Генерация waybill в `create_operation` и `update_operation` обёрнута в `async with uow.session.begin_nested()` (см. I3.2). Паттерн уже используется в `SyncServer/app/repos/inventory_subjects_repo.py:34,48`. **Это критично:** без savepoint DB-level ошибка (constraint, lock) в `generate_from_operation` отравляет внешнюю транзакцию → последующие `record_audit_event` + commit падают, что противоречит «не абортим»-семантике.

H1 в `update_operation` тоже оборачивается в savepoint (см. I3.2) — это pre-existing баг, который I3.4 фиксит попутно.

### Acceptance criteria I3 (rev. 2)

- [ ] **rev. 3:** `draft_document_type_for_operation("ADJUSTMENT")` возвращает `None` (единственная операция без draft).
- [ ] **rev. 3:** `draft_document_type_for_operation("RECEIVE"|"EXPENSE"|"WRITE_OFF"|"MOVE"|"ISSUE"|"ISSUE_RETURN")` возвращает `"waybill"`.
- [ ] ~~blocker #1 (rev. 2, снят в rev. 3)~~: опасность in-place finalization неприменима, т.к. draft=waybill и final=act/acceptance_certificate — разные `document_type`, `_find_reusable_document` фильтрует по типу.
- [ ] Создать draft MOVE — `GET /documents/operations/<id>/documents?document_type=waybill` сразу возвращает 1 документ со статусом `draft` и непустыми `payload.lines` (попадает в `get_operation_by_id` после `create_operation` + line-loop, не до).
- [ ] Создать draft RECEIVE → 0 draft-документов (RECEIVE не в карте).
- [ ] Создать draft EXPENSE → 0 draft-документов (EXPENSE не в карте после rev. 2).
- [ ] **warning #2:** update MOVE-черновика → `update_operation` вызывает `generate_from_operation(document_type="waybill")` (через helper).
- [ ] **warning #2:** update EXPENSE-черновика → `update_operation` НЕ создаёт waybill (helper возвращает None, guard `if document_type:`).
- [ ] **warning #8:** Симулировать DB-ошибку в `generate_from_operation` (мок) — `create_operation`/`update_operation` успешно коммитят operation, draft-документ не создан, в логах `waybill_auto_create_failed`.
- [ ] **warning #9:** Точка вставки проверена — после line 532, `created_by_user_id=user_id` пробрасывается (audit parity с `submit_operation`).
- [ ] **warning #10:** submit EXPENSE → draft waybills (если были) войдированы (или явно зафиксировано «не войдируются, BFF фильтрует»).
- [ ] `python -m pytest tests/test_documents_routes.py tests/test_operations_service_update.py` — pass.
- [ ] **(rev. 3)** Создать draft RECEIVE — `GET /documents/operations/<id>/documents?document_type=waybill` возвращает 1 документ `draft`.
- [ ] **(rev. 3)** Создать draft EXPENSE — аналогично RECEIVE, 1 waybill draft.
- [ ] **(rev. 3)** Создать draft WRITE_OFF — аналогично, 1 waybill draft.
- [ ] **(rev. 3)** Создать draft ADJUSTMENT — 0 документов (служебная операция).
- [ ] **(rev. 3)** Submit RECEIVE/EXPENSE/WRITE_OFF — draft waybills войдированы, финальный acceptance_certificate/act создан с актуальным payload.

---

## Stage I4: Unit-тесты пагинации и CSS

**Файл:** `Warehouse_web/apps/documents/tests.py`

### Задача I4.1: Тесты границ

```python
def test_pagination_first_page_fits_in_height(self) -> None:
    """Все строки на 1й странице должны влезать в available_height_first_page_mm."""
    lines = [_line(i, "Короткое") for i in range(1, 21)]
    pages = paginate_waybill_lines(lines)
    self.assertEqual(len(pages), 1, "20 коротких строк должны влезть на 1 страницу")

def test_pagination_handles_long_names(self) -> None:
    """50 строк с названием 200 символов → 2-3 страницы, без обрыва внутри строки."""
    long_name = "Длинное наименование ТМЦ " * 10  # ~250 chars
    lines = [_line(i, long_name) for i in range(1, 51)]
    pages = paginate_waybill_lines(lines)
    self.assertGreaterEqual(len(pages), 2)
    # Каждая страница кроме последней должна быть близка к заполнению
    for page in pages[:-1]:
        self.assertGreater(len(page["lines"]), 10)

def test_pagination_extremely_long_operation(self) -> None:
    """200 строк → 6+ страниц, общая сумма lines == 200."""
    lines = [_line(i, f"ТМЦ {i}") for i in range(1, 201)]
    pages = paginate_waybill_lines(lines)
    total = sum(len(p["lines"]) for p in pages)
    self.assertEqual(total, 200)
    self.assertGreaterEqual(len(pages), 6)

def test_pagination_single_line(self) -> None:
    lines = [_line(1, "Одна строка")]
    pages = paginate_waybill_lines(lines)
    self.assertEqual(len(pages), 1)
    self.assertEqual(pages[0]["lines"][0]["line_number"], 1)

def test_pagination_empty(self) -> None:
    pages = paginate_waybill_lines([])
    self.assertEqual(len(pages), 1)  # минимум 1 «пустая» страница
    self.assertEqual(pages[0]["lines"], [])
```

### Задача I4.2: Тесты CSS (через рендер HTML + grep)

```python
def test_waybill_html_has_page_break_after_avoid_on_h1(self) -> None:
    html = render_document_html(_document())
    self.assertIn("page-break-after: avoid", html)
    # h1 не имеет page-break-after, но CSS-правило должно быть в <style>

def test_waybill_html_uses_flexbox_for_signature_at_bottom(self) -> None:
    html = render_document_html(_document())
    # Контейнер .page использует flex с min-height = 267mm
    self.assertIn("display: flex", html)
    self.assertIn("min-height:", html)
    # waybill-table-wrap flex: 1 1 auto
    self.assertIn("flex: 1 1 auto", html)
```

### Задача I4.3: Тест геометрической согласованности I1+I2 (rev. 2 — warning #4)

`paginate_waybill_lines` константы должны быть согласованы с I1 (flex geometry). Добавить в `tests.py`:

```python
def test_pagination_constants_match_flex_geometry(self) -> None:
    """rev. 2 (warning #4): константы пагинатора + flex-блоки должны
    укладываться в A4 portrait 297mm за вычетом @page margins (30mm).
    """
    # Константы из I2.4 — дублируются в тесте чтобы падать, если I2 их поменяет
    # без пересогласования с I1.
    SIGNATURE_BLOCK_HEIGHT_MM = 37.0          # MOVE: Кладовщик + 2 extra
    SINGLE_ROW_SIGNATURE_HEIGHT_MM = 4.0      # RECEIVE/ADJUSTMENT: только Кладовщик
    HEADER_OVERHEAD_MM = 16.4 + 22 + 10       # h1 + header-lines + thead
    CONTINUATION_OVERHEAD_MM = 10 + 4         # thead + Кладовщик
    A4_INNER_HEIGHT_MM = 267.0                # 297 - 30 (page margins)

    # 1я страница с extra-подписями (MOVE) и без (RECEIVE):
    move_budget = A4_INNER_HEIGHT_MM - HEADER_OVERHEAD_MM - SIGNATURE_BLOCK_HEIGHT_MM
    self.assertLessEqual(move_budget, 152 + 1,  # +1mm tolerance
        f"MOVE 1-page budget {move_budget}mm должно быть ≤ 153mm (target 152)")
    receive_budget = A4_INNER_HEIGHT_MM - HEADER_OVERHEAD_MM - SINGLE_ROW_SIGNATURE_HEIGHT_MM
    self.assertLessEqual(receive_budget, 189 + 1,
        f"RECEIVE 1-page budget {receive_budget}mm должно быть ≤ 190mm (target 189)")

    # continuation: только thead + "Кладовщик" = 14mm
    cont_budget = A4_INNER_HEIGHT_MM - CONTINUATION_OVERHEAD_MM
    self.assertLessEqual(cont_budget, 223 + 1,
        f"continuation budget {cont_budget}mm должно быть ≤ 224mm (target 223)")
```

Если этот тест падает — константы I2 расходятся с геометрией I1, и executor должен сначала пересогласовать их, прежде чем идти на I6.

### Acceptance criteria I4

- [ ] ≥6 новых тестов, все зелёные.
- [ ] `python manage.py test apps.documents` — 100% pass.

### Acceptance criteria I4 (rev. 4 additions)

- [ ] `test_paginate_waybill_lines_exact_rows` — verify max rows for each page type by operation_type (RECEIVE → first=23/middle=28/last=28; MOVE → 23/28/22; ISSUE → 23/28/26).
- [ ] `test_paginate_waybill_lines_middle_pages_have_short_title` — 75 lines MOVE → 4 pages: first(23) + middles(28) + last(22); page 1 layout="first", page 2..n-1 layout="middle", page n layout="last".
- [ ] `test_paginate_waybill_lines_single_page_layout` — 10 lines → 1 page layout="first", is_first=is_last=True.
- [ ] `test_paginate_waybill_lines_move_has_4_extra_signatures` — `_build_extra_signatures("MOVE")` returns 4 blocks.
- [ ] `test_waybill_html_first_page_has_full_title` — page 1 HTML contains "Грузоотправитель".
- [ ] `test_waybill_html_middle_page_has_short_title` — page 2 HTML does NOT contain "Грузоотправитель".
- [ ] `test_waybill_html_last_page_has_full_signature_move` — MOVE last page contains "Операцию разрешил" + "Водитель" + "Начальник базы" + "Груз принял".
- [ ] `test_waybill_html_no_flexbox` — grep HTML/CSS, verify no `display: flex` in the rendered output (plan B is the source of truth now).

### Acceptance criteria I4 (rev. 5 additions)

- [ ] `first_max == 22` (после FULL_TITLE 50→60mm)
- [ ] `middle_max == 28` (без изменений)
- [ ] `last_max MOVE == 22`, `last_max ISSUE/EXPENSE/ISSUE_RETURN/WRITE_OFF == 26`, `last_max RECEIVE/ADJUSTMENT == 28`
- [ ] **rev. 5:** 80 lines MOVE → 4 страницы: first(22) + middle(28) + middle(28) + last(2). Middles полные.
- [ ] **rev. 5:** 50 lines MOVE → 2 страницы (first=22 + last=28, без middle).
- [ ] **rev. 5:** 80 lines MOVE → 4 страницы (first=22 + middle=28 + middle=28 + last=2; middles полные).
- [ ] **rev. 5:** 200 lines RECEIVE → 8 страниц (first=22 + 6×middle=28 + last=10).

---

## Stage I5: Integration-тест SyncServer

**Файл:** `SyncServer/tests/test_documents_routes.py` (или новый `test_create_operation_generates_waybill.py`)

### Задача I5.1: Тест create → waybill существует

```python
async def test_create_draft_operation_generates_waybill_draft(
    uow: UnitOfWork, sample_user: User, sample_site: Site, sample_item: Item, sample_unit: Unit
) -> None:
    """Создание draft MOVE должно сразу дать draft-документ waybill."""
    operation = await OperationsService.create_operation(
        uow=uow,
        operation_data=OperationCreate(
            operation_type="MOVE",
            site_id=sample_site.id,
            source_site_id=sample_site.id,
            destination_site_id=sample_site.id + 1,  # другая площадка
            lines=[
                OperationLineCreate(
                    line_number=1, item_id=sample_item.id, qty=Decimal("5"),
                ),
            ],
        ),
        user_id=sample_user.id,
    )
    docs = await uow.documents.get_documents_by_operation(operation.id, document_type="waybill")
    assert len(docs) == 1
    assert docs[0].status == "draft"
    assert docs[0].payload["lines"][0]["quantity"] == "5"  # или Decimal

async def test_update_draft_changes_payload_hash(
    uow: UnitOfWork, sample_user: User, sample_site: Site
) -> None:
    """Изменение строк → новый document_id, новый payload_hash."""
    # ... create + get doc1
    # ... update с новой строкой
    # assert doc2.id != doc1.id
    # assert doc2.payload_hash != doc1.payload_hash
    # assert doc1.status == "void"
```

### Задача I5.2: Guard EXPENSE/RECEIVE от draft-документа (rev. 2 — note #13, blocker #1)

```python
async def test_create_draft_expense_has_no_waybill_draft(
    uow: UnitOfWork, sample_user: User, sample_site: Site
) -> None:
    """rev. 2 (blocker #1): EXPENSE не должен порождать draft-документ.
    Если бы порождал — на submit draft act был бы финализирован in-place
    без пересборки payload (потеря правок черновика).
    """
    operation = await OperationsService.create_operation(
        uow=uow,
        operation_data=OperationCreate(
            operation_type="EXPENSE",
            site_id=sample_site.id,
            lines=[...],
        ),
        user_id=sample_user.id,
    )
    docs = await uow.documents.get_documents_by_operation(operation.id)
    assert len(docs) == 0, f"EXPENSE draft не должен иметь документов, got {len(docs)}"

async def test_create_draft_receive_has_no_waybill_draft(
    uow: UnitOfWork, sample_user: User, sample_site: Site
) -> None:
    """RECEIVE не маппится в waybill на стадии draft; acceptance_certificate
    появится на submit.
    """
    operation = await OperationsService.create_operation(
        uow=uow,
        operation_data=OperationCreate(operation_type="RECEIVE", site_id=sample_site.id, lines=[...]),
        user_id=sample_user.id,
    )
    docs = await uow.documents.get_documents_by_operation(operation.id)
    assert len(docs) == 0

async def test_update_draft_expense_does_not_create_waybill(
    uow: UnitOfWork, sample_user: User, sample_site: Site
) -> None:
    """rev. 2 (warning #2): H1 в update_operation тоже идёт через helper —
    EXPENSE не получает waybill при update.
    """
    # ... create EXPENSE draft (0 docs)
    # ... update notes
    # docs_after = await uow.documents.get_documents_by_operation(...)
    # assert len(docs_after) == 0  # waybill не появился

async def test_submit_expense_act_reflects_post_edit_state(
    uow: UnitOfWork, sample_user: User, sample_site: Site
) -> None:
    """rev. 2 (note #13, regression): submit EXPENSE после правок черновика
    должен дать финальный act с состоянием ПОСЛЕ правок, а не на момент create.
    Guard от stale-reuse.
    """
    # ... create EXPENSE с qty=5
    # ... update → qty=10
    # ... submit
    # act = await uow.documents.get_documents_by_operation(..., document_type="act")
    # assert act[0].status == "finalized"
    # assert act[0].payload["lines"][0]["quantity"] in ("10", Decimal("10"))
```

### Acceptance criteria I5

- [ ] 2 новых теста зелёные.
- [ ] `python -m pytest tests/test_documents_routes.py` — pass.
- [ ] Полный `python -m pytest` SyncServer — pass.

---

## Stage I6: Stand smoke tests

**Стенд:** Docker dev-стенд (`make status` → все сервисы health).

**⚠ rev. 2 (warning #4): I6 — это joint integration gate для I1 + I2.** Этапы геометрически связаны: I1 (CSS flex) меняет height-бюджет, который I2 (Python pagination) моделирует. I4/I5/I7/I8 могут проходить по отдельности, но реальная картина появляется только при сборке I1+I2 на реальном PDF. Executor не должен закрывать I6 до тех пор, пока:
1. Visual check на реальном PDF не подтвердит, что подпись внизу + заголовок сверху + количество корректно.
2. Все 4 кейса ниже (I6.1 – I6.4) пройдены.

### Задача I6.1: Реальная операция с 40+ строками (MOVE, joint I1+I2)

1. Через Django admin или Playwright: создать operation типа MOVE с 42 строками ТМЦ, из них 5 с названием >100 символов.
2. Через BFF: `POST /bff/api/v1/documents/operations/<op_id>/waybill/open` → получить `pdf_url`.
3. Скачать PDF → проверить:
   - 2–3 страницы
   - На 1й странице ≥18 строк
   - Заголовок не оторван от таблицы
   - Подпись внизу (Кладовщик + 2 extra для MOVE)
4. Скриншот 1й страницы, 2й страницы → приложить к evidence.

### Задача I6.2: Реальный smoke create → накладная (I3)

1. Создать draft MOVE с 3 строками.
2. Сразу: `GET /bff/api/v1/documents/operations/<op_id>/documents?document_type=waybill` → вернуть 1 документ (draft, 3 lines).
3. `POST /bff/api/v1/documents/operations/<op_id>/waybill/open` → вернуть `pdf_url`.
4. Скачать PDF → проверить, что 3 строки присутствуют и подпись внизу.

### Задача I6.3: EXPENSE — нет draft-документа (I3, rev. 2 blocker #1)

1. Создать draft EXPENSE с 2 строками.
2. `GET /bff/api/v1/documents/operations/<op_id>/documents` → пустой список (нет draft-документа, как и должно быть после rev. 2).
3. BFF «Накладная» → 404 / «документ не найден» (или явное сообщение «для этой операции накладная будет сформирована при подтверждении»).

### Задача I6.4: 1-страничная операция — подпись прижата к низу (joint I1+I2)

1. Создать draft MOVE с 5 короткими строками → 1 страница.
2. Скачать PDF → проверить визуально:
   - На 1й странице подпись «Кладовщик + Операцию разрешил + Водитель» находится внизу страницы (≤5mm от нижнего поля), а не сразу под таблицей.
   - Если подпись НЕ прижата — это сигнал, что I1 flex не сработал → переключиться на план B (см. Stage I1).

### Acceptance criteria I6

- [ ] **(rev. 2 joint gate)** I1 + I2 вместе дают визуально корректную накладную во всех 4 кейсах (I6.1 – I6.4).
- [ ] Скриншот 3-страничной накладной с правильной пагинацией (I6.1).
- [ ] PDF-файл `nakladnaya_<op_display_number>.pdf` скачан, размер 50–500 KB.
- [ ] На 1й странице визуально: h1, header-lines, таблица, «Кладовщик:» внизу.
- [ ] **(rev. 2)** I6.4 — 1-страничная MOVE с 5 строками, подпись прижата к низу. Если нет — fallback на план B без переоткрытия TZ.
- [ ] **(rev. 2)** I6.3 — EXPENSE draft без waybill, BFF корректно отдаёт пустой результат.

---

## Stage I7: UI automation (Playwright) — rev. 2 (warning #11)

**Файл:** `Warehouse_frontend/e2e/operations-waybill-pagination.spec.ts` (новый)

**⚠ rev. 2:** `DocumentRenderView` отдаёт PDF как `Content-Type: application/pdf` inline (`bff_api/documents_views.py:92`). Браузер рендерит PDF в встроенном viewer **без DOM** — `frameLocator(...).locator('h1')` НЕ сработает. I7 переделан под проверки, доступные Playwright: HTTP-ответ + извлечение текста через `pdftotext`.

### Задача I7.1: E2E-тест (rev. 2)

```typescript
import { test, expect } from '@playwright/test';
import { execSync } from 'child_process';
import * as fs from 'fs';
import * as path from 'path';

test('waybill PDF served with correct content-type and pagination text', async ({ page, request }) => {
  // Авторизация через Django session
  await page.goto('http://localhost:8001/admin/login/');
  await page.fill('#id_username', 'admin');
  await page.fill('#id_password', 'admin123');
  await page.click('input[type="submit"]');

  // Открыть существующую операцию с >40 строк
  await page.goto('http://localhost:8001/operations/<id>/');
  await page.click('button:has-text("Накладная")');

  // PDF endpoint (BFF)
  // URL вида /bff/api/v1/documents/<doc_id>/render?format=pdf
  const pdfUrl = await page.locator('[data-testid="waybill-pdf-url"]').textContent();
  expect(pdfUrl).toBeTruthy();

  // 1) Проверить Content-Type
  const response = await request.get(pdfUrl!);
  expect(response.status()).toBe(200);
  expect(response.headers()['content-type']).toContain('application/pdf');
  expect(response.headers()['x-document-pdf-cache']).toMatch(/hit|miss/);

  // 2) Сохранить PDF и извлечь текст через pdftotext (poppler-utils)
  const pdfBytes = await response.body();
  const tmpPath = path.join('/tmp', `waybill-e2e-${Date.now()}.pdf`);
  fs.writeFileSync(tmpPath, pdfBytes);
  const text = execSync(`pdftotext -layout ${tmpPath} -`, { encoding: 'utf-8' });
  fs.unlinkSync(tmpPath);

  // 3) Контентные ассерты
  expect(text).toMatch(/Накладная №\s+\S+/);          // заголовок
  expect(text).toMatch(/Кладовщик:/);                   // подпись есть
  expect(text).toMatch(/Лист \d+ из \d+/);              // пагинация работает
  expect(text).toMatch(/Грузоотправитель:/);            // header-lines
  expect(text).toMatch(/Грузополучатель:/);
  expect(text).toMatch(/Основание:/);
});
```

### Acceptance criteria I7

- [ ] **(rev. 2)** E2E проверяет: status 200, `content-type: application/pdf`, заголовок `x-document-pdf-cache`, контент-ассерты через `pdftotext`.
- [ ] E2E зелёный в `make test-e2e`.
- [ ] PDF > 5KB (не пустой), < 500KB (не bloated).
- [ ] `pdftotext` находит «Накладная №», «Кладовщик:», «Лист 1 из N», «Грузоотправитель:».

---

## Stage I8: User scenario

**Документ:** `docs/user_scenario/waybill_draft_sync.md` (новый)

### Задача I8.1: Описать кейс

```
1. Кладовщик логинится в Django.
2. Создаёт новый черновик операции MOVE.
3. Сразу открывает «Накладная» → видит пустую накладную (или «Нет строк для печати»).
4. Добавляет 5 строк ТМЦ через форму.
5. Возвращается в «Накладная» → видит 5 строк, актуальное количество.
6. Добавляет ещё 35 строк с длинными названиями.
7. Накладная автоматически обновлена (через H1 + I3), 3 страницы, правильная пагинация.
8. Submit операции → накладная получает статус finalized, при повторном открытии — тот же документ.
```

### Acceptance criteria I8

- [ ] Сценарий задокументирован.
- [ ] Пройден вручную на dev-стенде.

---

## Stage I9: Regression pack

| Проект | Команда | Ожидание |
|---|---|---|
| SyncServer | `python -m pytest` | 449+ passed (без регрессий) |
| Warehouse_web | `python manage.py test` | 350+ passed |
| Warehouse_frontend | `npm run build` | OK |

---

## Stage I10: Документация

### Файлы для обновления

| Файл | Изменение |
|---|---|
| `docs/TZ-V3.1H_WAYBILL_PDF_FIXES.md` | Закрыть #9 «Final acceptance review» (✅) ссылкой на V3.1I. |
| `docs/ARCHITECTURE.md` | Обновить секцию documents rendering, упомянуть CSS-flexbox для подписи + plan B (`position: running()`). |
| `Functional and WorkLogik.md` §VII | **rev. 2 (warning #7):** уточнить п.1 И п.2: п.1 — «накладная создаётся при создании черновика для waybill-типов (MOVE/ISSUE/ISSUE_RETURN) и фиксируется при подтверждении; для типов с финальным act/acceptance_certificate (RECEIVE/EXPENSE/WRITE_OFF/ADJUSTMENT) draft-документ не создаётся, финальный появляется при submit»; п.2 — «накладная обновляется вместе с черновиком по составу и количеству». |
| `docs/TZ-V3.1I_WAYBILL_PAGINATION_AND_SYNC_HARDENING.md` | Указать в README/INDEX, что superseded-черновики waybill'ов могут оставаться как preview-артефакты, если команда выбрала опцию «не войдировать» в I3.5. |
| `INDEX.md` | Добавить ссылку на TZ-V3.1I. |
| Release notes | Упомянуть bump `DOCUMENT_RENDERER_VERSION` → `waybill-pdf-v2` (см. I1 acceptance). |

---

## Files in scope

| Файл | Этап | Тип |
|---|---|---|
| `SyncServer/app/services/operations_service.py` | I3 | Создание draft-документа в `create_operation` |
| `SyncServer/app/services/document_service.py` | I3 | Helper `draft_document_type_for_operation` |
| `SyncServer/tests/test_documents_routes.py` | I5 | 2 integration-теста |
| `Warehouse_web/apps/documents/services.py` | I2 | Новая сигнатура `paginate_waybill_lines` |
| `Warehouse_web/apps/documents/templates/documents/waybill_pdf.html` | I1 | CSS-flexbox + page-break-after: avoid |
| `Warehouse_web/apps/documents/tests.py` | I4 | 6+ unit-тестов |
| `Warehouse_frontend/e2e/operations-waybill-pagination.spec.ts` | I7 | 1 E2E |
| `docs/ARCHITECTURE.md` | I10 | Документация |
| `Functional and WorkLogik.md` | I10 | Уточнение §VII |
| `docs/TZ-V3.1H_WAYBILL_PDF_FIXES.md` | I10 | Закрыть #9 |
| `INDEX.md` | I10 | Ссылка на V3.1I |

## Out of scope

- Новые типы документов (только waybill)
- Редизайн шаблона (только вёрстка и пагинация)
- ЭЦП / подписи
- Рендеринг на стороне SyncServer (остаётся в Django)
- Миграции БД (не требуются)
- Перевод waybill на Angular (отдельный TZ)
- Two-pass render (overkill для текущих объёмов)

---

## Test Ladder

| Level | Применение |
|---|---|
| Static checks | ✅ ruff + mypy (SyncServer), Angular build |
| Unit tests | ✅ I2: `paginate_waybill_lines` (≥5 кейсов), I4: CSS (≥2) |
| Component tests | ✅ I4: HTML-структура |
| Integration tests | ✅ I5: create + update через БД |
| Stand smoke tests | ✅ I6: реальная операция 40+ строк |
| UI automation | ✅ I7: Playwright |
| User scenarios | ✅ I8: документированный сценарий |
| Regression pack | ✅ I9: SyncServer 449+, Django 350+ |
| Acceptance review | ✅ Evidence table |

---

## Stand Requirements

- Docker dev-стенд: все сервисы (SyncServer:8000, Django:8001, Postgres:5432).
- Django admin: `admin`/`admin123`.
- Тестовая операция: ≥40 строк ТМЦ, из них 5 с названием >100 символов.
- PDF-файлы smoke-проверки сохраняются в `/tmp/waybill_smoke/`.

## Reset / cleanup

- Тестовые операции помечаются префиксом `[smoke-waybill-I]` в `notes`.
- Удаляются через `python manage.py shell -c "Operation.objects.filter(notes__startswith='[smoke-waybill-I]').delete()"` после evidence.

---

## Risk / Mitigation

| Риск | Митигация |
|---|---|
| WeasyPrint flexbox ведёт себя иначе в edge-cases | I4: HTML-тесты + I6: визуальная проверка PDF. **(rev. 2, warning #5)** Если I6 провалится визуально — fallback на plan B (`position: running()` через `@page` margin boxes, или table-based bottom spacer) без переоткрытия TZ (см. Stage I1). |
| WeasyPrint flexbox ненадёжен в paged-media (rev. 4, активирован plan B) | exact-rows с жёсткими лимитами, без flex. Подтверждено багом 08.07.2026. |
| Изменение констант пагинации сломает другие TZ | I9: регрессия Django 350+ тестов |
| `create_operation` с ошибкой document_service ломает UX | I3: try/except + warning log, не абортим create. **(rev. 2, warning #8)** Savepoint `uow.session.begin_nested()` — DB-ошибка откатывает только генерацию, не всю транзакцию. |
| **(rev. 2, blocker #1)** `act` draft на create → submit финализирует его in-place без пересборки payload → потеря правок | Карта сужена до MOVE/ISSUE/ISSUE_RETURN. EXPENSE/WRITE_OFF не получают draft-документ. I5 + I6.3 подтверждают. |
| **(rev. 2, warning #4)** I1 и I2 геометрически связаны — независимые acceptance могут пройти, а интеграция упасть | I6 — joint integration gate (см. Stage I6). I4.3 — тест геометрической согласованности. |
| **(rev. 2, warning #9)** Точка вставки I3 до `get_operation_by_id` → waybill без строк | Указана точно: после line 532. Тест I5 проверяет `payload.lines` непуст. |
| **(rev. 2, warning #10)** Осиротевшие draft waybills после submit | I3.5 войдирует draft waybills при submit для не-waybill типов. |
| **(rev. 2, warning #11)** Playwright I7 не может читать PDF DOM | I7 переделан на `application/pdf` + `pdftotext`. |
| **(rev. 2, warning #12)** Кеш отдаёт старый PDF до истечения TTL после CSS-изменений | I1 acceptance требует bump `DOCUMENT_RENDERER_VERSION` и `template_version`. |
| **(rev. 2, warning #2)** H1 в update_operation остаётся на дефолте waybill → create-vs-update дивергенция | I3.3: H1 тоже идёт через helper. I5 проверяет. |
| Изменение `paginate_waybill_lines` ломает `total_pages` в шаблоне | Сохранить структуру возврата `list[dict]` |

---

## Evidence Table (для отчёта)

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|
| Unit tests (Django) | `python manage.py test apps.documents` | pass | logs/waybill_pagination_unit.log |
| Integration tests (SyncServer) | `python -m pytest tests/test_documents_routes.py -k "waybill_draft or payload_hash"` | pass | logs/waybill_sync_integration.log |
| Stand smoke | curl + pdftotext | pass | evidence/waybill_3page.pdf, screenshot |
| UI automation | `make test-e2e -- operations-waybill-pagination` | pass | reports/waybill_pagination/ |
| Regression | `python -m pytest` + `python manage.py test` | pass | logs/regression_v3.1I.log |
