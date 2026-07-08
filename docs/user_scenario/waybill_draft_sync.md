# User Scenario: Waybill Draft Sync (TZ V3.1I)

**Date:** 2026-07-08
**Status:** validated
**Source TZ:** `docs/TZ-V3.1I_WAYBILL_PAGINATION_AND_SYNC_HARDENING.md` (rev. 2)
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

**Поведение:** После 40+ строк накладная занимает 2-3 страницы. Проверяется визуально:
- Страница 1: h1 «Накладная №...», header-lines, thead, ~18-20 строк таблицы, **подпись «Кладовщик:» в самом низу** (flex layout).
- Страница 2: thead повторяется, остаток строк, подпись «Кладовщик:» внизу.
- Страница 3 (если есть): thead, остаток, подпись внизу + extra-подписи (MOVE: «Операцию разрешил:», «Водитель:») на **последней** странице.

**Критерий приёмки:** На странице с 1 строкой блок «Кладовщик:» **прижат к нижнему краю листа**, не висит под таблицей.

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

### N1. EXPENSE draft → нет накладной

Создать `EXPENSE` черновик (2 строки).
- До: `GET /api/v1/documents/operations/<op_id>/documents` → 0 docs.
- UI «Накладная» → сообщение «для этой операции накладная будет сформирована при подтверждении».
- При submit → генерируется `act` (рендерится в следующих TZ, пока out of scope).

### N2. WRITE_OFF draft → нет накладной

Аналогично N1, но `WRITE_OFF`.

### N3. RECEIVE draft → нет накладной

Аналогично, но `RECEIVE`. При submit → `acceptance_certificate`.

### N4. DB-ошибка в генерации waybill → operation не падает

Симулировать DB-ошибку (мок `DocumentService.generate_from_operation`):
- Operation создаётся/обновляется нормально.
- В логах `waybill_auto_create_failed` / `waybill_auto_update_failed` warning.
- Транзакция коммитится (savepoint откатил только генерацию, не всю операцию).

## Что проверяется

- ✅ **A1 → I1+I2+I4:** заголовок сверху, подпись внизу, многостраничная накладная без разрывов, hard-cap.
- ✅ **A2 → I1:** `<h1>` и `.header-lines` не отрываются от таблицы.
- ✅ **A3 → I1:** подпись прижата к низу flex-layout'ом.
- ✅ **A4 → I3:** накладная появляется сразу при create черновика для MOVE/ISSUE/ISSUE_RETURN.
- ✅ **Сохранение количества:** payload строится из `operation.lines` → `payload.lines[i].quantity` соответствует черновику.
- ✅ **Update sync:** H1 (rev. 2 helper) обновляет накладную при каждом изменении.
- ✅ **Blocker #1 закрыт:** EXPENSE/WRITE_OFF не получают draft-документ → submit создаёт act с актуальным payload.

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
