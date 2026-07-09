# User Scenario: Waybill Draft Sync (TZ V3.1I)

**Date:** 2026-07-08
**Status:** validated
**Source TZ:** `docs/TZ-V3.1I_WAYBILL_PAGINATION_AND_SYNC_HARDENING.md` (rev. 4 — plan B activated)
**Pre-fix reality:** V3.1H had H1 (auto-regen on update) but **no waybill on create**, which meant the storekeeper could not see any draft document for a freshly created operation. The first "Накладная" click returned 404 until they edited something.

## Pre-conditions

- dev-стенд: SyncServer 8000, Django 8001, Angular 4200, Postgres 5432 — все health.
- Авторизация: Django admin `admin`/`admin123`.
- В каталоге: ≥5 ТМЦ с разными названиями (короткие, средние, длинные 100+ символов).
- В каталоге: ≥2 site (для MOVE нужно source ≠ destination).
- 1 сотрудник с правами `storekeeper` (используется как `actor_user_id` в операциях).

## Сценарий

### Шаг 1. Кладовщик логинится

```
URL: http://localhost:8001/admin/login/
Логин: admin
Пароль: admin123
```

После логина виден Django shell с topbar и левым навигационным меню.

### Шаг 2. Создаёт новый черновик операции MOVE

Через UI «Операции → Новая операция» (или через BFF `POST /bff/api/v1/operations/`):

- Тип: `MOVE`
- Сайт: Склад-1 (source = Склад-1)
- Назначение: Склад-2
- Строки: 0 (пусто)

**Проверка до (V3.1H, без I3):** `GET /api/v1/documents/operations/<op_id>/documents` → 404 / пусто.

**Проверка после (V3.1I, с I3):**
```bash
# Внутри SyncServer (или через BFF)
GET /api/v1/documents/operations/<op_id>/documents
→ {"items": [{..., "document_type": "waybill", "status": "draft", "payload": {"lines": []}}]}
```

Документ сразу есть. UI «Накладная» → сразу открывает пустую накладную с «Нет строк для печати» (это уже было в шаблоне `waybill_pdf.html:155-160`).

### Шаг 3. Добавляет 5 строк ТМЦ

Кладовщик добавляет 5 строк через форму операции:
1. «Дрель ударная» — 3 шт
2. «Молоток слесарный 500г» — 5 шт
3. «Набор свёрл по металлу 1-10мм 19 шт» — 2 шт
4. «Строительный уровень 600мм» — 1 шт
5. «Очень длинное наименование ТМЦ с множеством слов для проверки переноса строк в колонке» — 1 шт

**Поведение:** Каждое сохранение строк → `update_operation` → H1+rev.2 helper → `generate_from_operation(document_type="waybill", auto_finalize=False)` → void старого draft, создание нового с актуальным `payload.lines`.

**Проверка через BFF:**
```bash
POST /bff/api/v1/documents/operations/<op_id>/waybill/open
→ {"data": {"document": {"id": "<new_doc_id>", ...}, "pdf_url": "..."}}
```

Скачать PDF → `pdftotext` → найти 5 строк, актуальные количества (3, 5, 2, 1, 1).

### Шаг 4. Добавляет ещё 35 строк (всего 40)

Кладовщик продолжает собирать операцию. Добавляет ещё 35 ТМЦ, из них 5 с названиями >100 символов.

**Поведение (rev. 5):** С 40 строками MOVE — 1-я страница: 22 строки max (полный заголовок 60mm + thead 10mm + sig 6mm), средние: 28 строк max (короткий заголовок 12mm + thead 10mm + sig 6mm), последняя MOVE: 22 строки max. Точные значения зависят от типа операции:
- MOVE (4 подписи): first=22, middle=28, last=22.
- ISSUE/ISSUE_RETURN/EXPENSE (1 подпись): first=22, middle=28, last=26.
- WRITE_OFF (1 подпись): first=22, middle=28, last=26.
- RECEIVE/ADJUSTMENT (нет extra): first=22, middle=28, last=28.

**Проверяется визуально:**
- Страница 1: полный заголовок (Накладная + Грузоотправитель + Грузополучатель + Основание) + 22 строки + «Кладовщик:» внизу.
- Страница 2 (если есть): короткий заголовок (только «Накладная № X») + N строк + «Кладовщик:» внизу.
- Последняя страница: короткий заголовок + N строк + полная форма подписей.
- Для MOVE: «Операцию разрешил» + «Водитель» + «Начальник базы» + «Груз принял».
- Для ISSUE/ISSUE_RETURN/EXPENSE: «Получил».
- Для WRITE_OFF: «Операцию разрешил».
- Подпись «Кладовщик:» присутствует на КАЖДОЙ странице (на последней — в составе полной формы).

### Шаг 5. Submit операции

Кладовщик подтверждает операцию.

**Поведение:**
- `submit_operation` для MOVE → `submit_document_type_for_operation("MOVE")` → `"waybill"`.
- `generate_from_operation(document_type="waybill", auto_finalize=True)` → находит осиротевший draft (MOVE = waybill), finalizes его in-place (это легитимно, т.к. для waybill-типов draft и final одного типа).
- Документ получает `status="finalized"`, `finalized_at=now`, `document_number` обновляется.

### Шаг 6. Финальная накладная

Кладовщик ещё раз нажимает «Накладная» → PDF скачивается:
- 1 документ `finalized` (тот же, что был draft'ом).
- `document_number` в формате `WB-<site_id>-<YYYYMMDD>-<suffix>`.
- Контент полностью соответствует 40 строкам.

## Негативные сценарии

### N1. ADJUSTMENT draft → нет накладной (служебная операция)

Создать `ADJUSTMENT` черновик (2 строки).
- `GET /api/v1/documents/operations/<op_id>/documents` → 0 docs.
- UI «Накладная» → сообщение «для этой операции накладная не предусмотрена (корректировка)».
- При submit → создаётся финальный `act` (только root/chief).

### N2. RECEIVE/EXPENSE/WRITE_OFF draft → есть накладная (rev. 3)

- `GET /api/v1/documents/operations/<id>/documents?document_type=waybill` → 1 draft.
- При submit → draft waybill войдируется, финальный `acceptance_certificate` (RECEIVE) или `act` (EXPENSE/WRITE_OFF) создаётся с актуальным payload.

### N4. DB-ошибка в генерации waybill → operation не падает

Симулировать DB-ошибку (мок `DocumentService.generate_from_operation`):
- Operation создаётся/обновляется нормально.
- В логах `waybill_auto_create_failed` / `waybill_auto_update_failed` warning.
- Транзакция коммитится (savepoint откатил только генерацию, не всю операцию).

## Что проверяется

- ✅ **A1 → I1+I2+I4:** заголовок сверху, подпись внизу, многостраничная накладная без разрывов, hard-cap.
- ✅ **A2 → I1:** `<h1>` и `.header-lines` не отрываются от таблицы.
- ✅ **A3 → I1 (rev. 4 plan B):** подпись прижата к низу **не flex'ом, а exact-rows с 3 layout** (first/middle/last). Без flexbox. Проверяется на 1-страничной и многостраничной накладной.
- ✅ **A4 → I3 (rev. 3):** накладная появляется сразу при create черновика для всех операций движения ТМЦ (MOVE/ISSUE/ISSUE_RETURN/RECEIVE/EXPENSE/WRITE_OFF). ADJUSTMENT (служебная) — без накладной.
- ✅ **Сохранение количества:** payload строится из `operation.lines` → `payload.lines[i].quantity` соответствует черновику.
- ✅ **Update sync:** H1 (rev. 2 helper) обновляет накладную при каждом изменении.
- ✅ **rev. 3:** Все операции движения ТМЦ (MOVE/ISSUE/ISSUE_RETURN/RECEIVE/EXPENSE/WRITE_OFF) получают draft waybill при create/update. ADJUSTMENT (служебная) — без draft. При submit draft waybills войдируются для не-waybill финалов.
- ✅ **rev. 5:** MOVE-операция с 40 строками → 2 страницы: page 1 (22 строки, full title) + page 2 (18 строк, short title, 4-блочные подписи MOVE). middle-страницы всегда полные 28 строк; first_max=22 (после FULL_TITLE 50→60mm).

## Ожидаемые результаты (evidence)

| # | Проверка | Команда / URL | Ожидание |
|---|---|---|---|
| 1 | `make status` | curl health-checks | все 3 OK |
| 2 | `pytest SyncServer` | `cd SyncServer && python -m pytest` | 469 passed |
| 3 | `manage.py test` | `cd Warehouse_web && python manage.py test` | 388 passed |
| 4 | `apps.documents` tests | `python manage.py test apps.documents -v 2` | 17 passed |
| 5 | `test_draft_document_type.py` | `cd SyncServer && python -m pytest tests/test_draft_document_type.py -v` | 4 passed |
| 6 | Playwright E2E | `npx playwright test e2e/operations-waybill-pagination.spec.ts` | 1 passed |
| 7 | PDF на 1 странице | визуально в браузере | подпись внизу, h1 сверху |
| 8 | PDF на 3 страницах | визуально | заголовок thead повторяется, подпись на каждой стр |
| 9 | pdftotext на 3-страничной | `pdftotext -layout nakladnaya.pdf -` | «Лист 1 из 3», «Лист 2 из 3», «Лист 3 из 3» |
| 10 | EXPENSE draft no-doc | SyncServer logs | нет вызова `generate_from_operation` для EXPENSE draft |
