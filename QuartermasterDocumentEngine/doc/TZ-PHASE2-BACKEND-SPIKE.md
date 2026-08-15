# TZ: Quartermaster Document Engine — Phase 2. Backend Spike (WeasyPrint 66 vs Typst)

Статус: **CLOSED** (архитектор, 2026-08-11) — Phase 2 Backend Spike, Phase 2.1 Decision Readiness Hardening и Phase 2.1.1/2.1.2 M1 close-out завершены; см. финальный статус-блок в конце файла.
Источники: `doc/SPEC-QUARTERMASTER_DOCUMENT_ENGINE-v2.md`, `doc/ROADMAP-QUARTERMASTER_DOCUMENT_ENGINE-v1.md` (Phase 2), `doc/ADR-0001-QUARTERMASTER-DOCUMENT-ENGINE.md` (D2, D3, D5–D13), `doc/archive/TZ-PHASE1-CLI-SKELETON.md`, коммиты `b305eb3` (Phase 1), `9008fee` (Phase 1.1).

## Execution Checklist

- [x] 0. Context verified (это TZ, SPEC v2, ROADMAP Phase 2, ADR-0001, Phase 1 код)
- [x] 1. Investigation report зафиксирован (`doc/spike/INVESTIGATION.md`)
- [x] 2. Контракты spike-семейств + fixtures готовы и валидны
- [x] 3. Bundled pinned шрифты + font enforcement (FONT_NOT_AVAILABLE)
- [x] 4. Assets (envelope.assets, base64) + ASSET_NOT_AVAILABLE; QR/barcode fixtures
- [x] 5. Typst backend spike (pinned binary, subprocess) + unit/component tests
- [x] 6. Spike-шаблоны: waybill-typst, route-sheet (weasy+typst), fuel report (weasy+typst)
- [x] 7. Generic capabilities: copies/экземпляры, watermark, portrait/landscape
- [x] 8. Visual comparison harness + калибровка порогов + REVIEW_REQUIRED
- [x] 9. Performance benchmark (все сценарии) + отчёт
- [x] 10. Golden artifacts (структура, LFS-политика, update-процедура)
- [x] 11. Linux offline smoke; Windows smoke ИЛИ документированный внешний blocker
- [x] 12. Regression: 65 тестов Phase 1 зелёные, публичные контракты не изменены
- [x] 13. Comparative report + заполненная scoring matrix + hard veto + recommendation
- [x] 14. Final acceptance review (evidence table)

## Check Rules

- Архитектор создал чек-лист и критерии; executor отмечает пункт только после реализации И верификации.
- Пункты 8–14 не закрываются без фактического просмотра PDF (Level 9 test ladder).
- Пропущенная проверка остаётся unchecked с причиной в отчёте.
- Windows-пункты при отсутствии среды остаются unchecked с пометкой «нет Windows-среды» (внешний blocker, не вина executor'а).

## Execution Strategy

**Sequential, 1 executor.** Общие файлы (`engine/qm_engine/envelope.py`, `render.py`, `pyproject.toml`, `cli/qm_cli/main.py`) и сильная связность fixtures→templates→harness делают параллельную работу конфликтной.

Допустимый staged-parallel на 2 потока, если исполнителей двое:

- Stage A (параллельно): поток 1 — T2 контракты + T3 fixtures; поток 2 — T4 fonts + T5 assets + T6 Typst backend. Владелец `envelope.py`/`render.py` — только поток 2; поток 1 трогает лишь `contracts/` и `tests/fixtures/`.
- Stage B (последовательно): T7 шаблоны → T8 capabilities → T9 harness → T10 bench → T11 golden → T12 report.

Максимальная полезная параллельность: **2 потока**. Больше — конфликты на registry/templates/tests.

---

## 1. Context

`QuartermasterDocumentEngine/` — автономный компонент внутри `/home/makc/AI_sandbox/warehouse_solution/` (nested git repo, ветка `dev`), разрабатываемый прежде всего для Warehouse Solution, но архитектурно от него независимый.

Ключевое свойство:

```text
self-contained versioned JSON → qm-render (CLI) → PDF
```

Рендер не требует SyncServer, Django, PostgreSQL, ORM, API, авторизации, сети. Правильная зависимость: `Warehouse Solution → uses → QuartermasterDocumentEngine`. Обратная зависимость запрещена.

Phase 2 — **сравнительный backend spike**, не миграция. Результат — измеримые данные для решения Phase 5 (weighted matrix). Победитель заранее НЕ назначается; допустимы исходы: Typst-primary / WeasyPrint остаётся / mixed / оба имеют критические ограничения → новое исследование.

## 2. Current state (зафиксировано обследованием 2026-08-10)

### 2.1 Engine (коммиты `b305eb3`, `9008fee`)

- Пакеты `qm_engine` (envelope, errors, paths, registry, render), `qm_backends` (base Protocol + WeasyPrintBackend), `qm_cli` (click). Console script `qm-render`.
- Команды: `version`, `capabilities`, `validate`, `inspect-template`, `render`; режимы file→file, file→stdout, stdin→file, stdin→stdout.
- `version` → `{"engine": "0.1.0", "engine_contract_versions": ["1.0.0"]}` (публичный контракт).
- Exit codes: 0 ok / 2 валидация / 3 шаблон / 4 ресурсы-backend / 5 рендер; ошибки JSON в stderr `{"error":{"code","message","details"}}`. Все 11 кодов ошибок SPEC v2 реализованы в `engine/qm_engine/errors.py`.
- `--templates-dir` > `QM_TEMPLATES_DIR` > bundle default — единообразно во всех командах (`_resolve_templates_dir`).
- Backend Protocol (`backends/qm_backends/base.py`): `name`, `available()`, `render(normalized_document, template_package, output_format, render_options) -> RenderResult(data, format, page_count, warnings)`. Реестр backends: `_BACKENDS` в `engine/qm_engine/render.py` (пока только `weasyprint`).
- WeasyPrintBackend: Jinja2 рендер entrypoint'а, `weasyprint.HTML(string=..., base_url=template_root).write_pdf()`, page count через pypdf. **Шрифты/asset'ы не контролирует**, `render_options` игнорирует, поддерживает только `pdf`.
- Envelope schema (`contracts/envelope/v1/envelope.schema.json`): draft 2020-12, `additionalProperties: false`, обязательные 8 полей; опциональные `document_id`, `document_number`, `assets` (object, пока нигде не используется). `locale` enum `["ru-RU"]`, `render_profile` enum `["print"]`, `template_version` pattern `X.Y` или `X.Y.Z`.
- Контракт документов один: `warehouse.operation-document/v2` (намеренно либеральный: `additionalProperties: true`, required только `lines`; каноническое ужесточение — Phase 6). Регистрация в `_DOCUMENT_CONTRACT_SCHEMAS` (`envelope.py`).
- Шаблоны: `warehouse-waybill-ru@0.1.0` (dev fixture) и `warehouse-waybill-ru@1.0` (боевые envelope). Manifest: id/version/document_contract/backend/entrypoint/output_formats/locales/page/capabilities/fonts/assets; поля `capabilities/fonts/assets` пустые и **не enforce'ятся**.
- 6 боевых envelope в `doc/test_templates/` (MOVE 5/15/30 строк, RECEIVE 15, WRITE_OFF 14, ADJUSTMENT act 1 строка) рендерятся в валидные PDF.
- Тесты: **65** (23 unit / 8 component / 34 integration); ruff check, ruff format --check, mypy strict — PASS.
- `fonts/README.md` — placeholder: bundled fonts объявлены scope'ом Phase 2.

### 2.2 SyncServer renderer (read-only обследование)

- `weasyprint==66.0`, `Jinja2==3.1.6` (`SyncServer/requirements.txt`). QR/barcode-библиотек нет.
- `DocumentType = waybill|acceptance_certificate|act|invoice`, но на диске один шаблон `templates/documents/waybill.html` — все 4 типа рендерятся через него (fallback в `document_renderer.py`).
- Payload строится `DocumentService._build_payload` (JSONB + SHA-256 `payload_hash`, `PAYLOAD_SCHEMA_VERSION="1.1.0"`): плоский документ с `operation`, `sender`/`receiver`, `lines` (line_number, item_id, item_name, item_sku, quantity, unit_name, unit_symbol, category_name, batch, comment, опц. accepted_qty/lost_qty), `signatures`, `localization`, `basis`, `total_lines`, `generated_at`. Снапшоты — `OperationLine.*_snapshot` колонки.
- Шаблон: **нет `@page`**, нет пагинации (класс `.page-break` объявлен, но не применён), 8-колоночная таблица (№/Наименование/Артикул/Кол-во/Ед./Категория/Партия/Примечание), подписи Сдал/Принял/Главный бухгалтер/Дата, служебный footer. A4 и поля 0 — неявные дефолты WeasyPrint, визуально `body margin: 20px`.
- Шрифт: единственная декларация `'DejaVu Sans', 'Arial', sans-serif`. **Bundled шрифтов нет**; Dockerfile SyncServer не ставит fontconfig/pango → PDF-рендер в контейнере, по оценке, неработоспособен (вне scope Phase 2, зафиксировать в INVESTIGATION.md).
- Кеш: in-memory dict, TTL 120 с, ключ без payload hash (известный дефект; вне scope).

### 2.3 Django renderer (read-only обследование)

- `weasyprint>=66,<67` (`Warehouse_web/requirements.txt`); движок шаблонов — Django templates (не Jinja2).
- `render_document_pdf` (`apps/documents/services.py`): cache key `waybill_pdf:{document_id}:{payload_hash}:{renderer_version}:{template_version}:layout-v7.1`, TTL 3600, locmem; `RenderedDocumentArtifact` (unique по document_id/revision/payload_hash/template_name/template_version/renderer_version; статусы rendering/ready/failed; `pdf_sha256`, `size_bytes`; `pdf_file` фактически не сохраняется). Ретраев рендера нет.
- Только `waybill`; `build_waybill_context` нормализует строки к `{line_number, item_name, unit, quantity}` (SKU намеренно не печатается), строит `extra_signatures` по типу операции.
- **Пагинация content-aware, на стороне Python** (`paginate_waybill_lines`), константы (rev. 7, `services.py`):
  - `NAME_CHARS_PER_VISUAL_LINE = 40` (визуальная строка имени ТМЦ);
  - `FIRST_PAGE_UNITS = 22`, `MIDDLE_PAGE_UNITS = 28`;
  - `LAST_PAGE_UNITS`: MOVE 19, ISSUE/ISSUE_RETURN/EXPENSE/WRITE_OFF 25, DEFAULT 26;
  - `SINGLE_PAGE_UNITS`: MOVE 15, ISSUE/ISSUE_RETURN/EXPENSE/WRITE_OFF 19, DEFAULT 21 (включают 1 unit резерва).
- Геометрия (архив `docs/archive/TZ-V3.1I_WAYBILL_PAGINATION_AND_SYNC_HARDENING.md`, Stage I2): A4 210×297 мм, `@page margin: 16mm 14mm 14mm` → полезная высота 267 мм; overhead первой страницы ≈78 мм.
- Шаблон `waybill_pdf.html`: `@page { size: A4 portrait; margin: 16mm 14mm 14mm }`; font 11pt `"DejaVu Sans", "Arial"`; `table-layout: fixed`, колонки № 11mm / Ед. 24mm / Кол-во 28mm, имя гибкое с `overflow-wrap: anywhere`; `thead` повторяется, `tr { page-break-inside: avoid }`; первая страница — полный header (Грузоотправитель/Грузополучатель/Основание), последующие — короткий (только заголовок 14pt); «Кладовщик» на каждой странице; финальный подписной блок только на последней (MOVE: Операцию разрешил / Водитель / Начальник базы / Груз принял; WRITE_OFF: Операцию разрешил; ISSUE/ISSUE_RETURN/EXPENSE: Получил); footer «Лист N из M» при total_pages > 1.
- Шрифты: bundled нет; Dockerfile ставит `fontconfig`, `fonts-dejavu-core`, `fonts-liberation`. QR/barcode/assets нет.

### 2.4 Выводы font-аудита

| Pipeline | font-family | Bundled fonts | Обеспечение в runtime |
|---|---|---|---|
| SyncServer | `'DejaVu Sans','Arial',sans-serif` | нет | ничего (в контейнере, по оценке, рендер падает) |
| Django | `"DejaVu Sans","Arial",sans-serif` | нет | apt: fonts-dejavu-core, fonts-liberation, fontconfig |
| Engine (Phase 1) | `"DejaVu Sans","Liberation Sans",sans-serif` | нет (`fonts/` placeholder) | системные хоста |

Различий в гарнитурах между pipeline'ами нет (везде DejaVu Sans первый), но **нигде шрифт не pinned и не распространяется с кодом** → воспроизводимость PDF машино-зависима. Это главная проблема, которую Phase 2 обязан закрыть (ADR-0001 D9).

## 3. Goal

На одинаковых контрактах, fixtures и шрифтах практически сравнить **WeasyPrint 66 (baseline)** и **Typst (кандидат)** по качеству PDF, пагинации, строгим формам, удобству шаблонизации, деплою Linux/Windows, offline, кириллице, preview, производительности, размеру дистрибуции — и подготовить данные для Phase 5.

## 4. Non-goals

- Миграция production renderer'ов, удаление существующих шаблонов Django/SyncServer, перепись Django-интеграции или SyncServer-рендера.
- Автоматический конвертер Jinja2 → Typst (запрещён как цель).
- Третий backend (Chromium/Paged Media) — только если архитектурный анализ по ходу spike выявит конкретную необходимость; инициатива «для полноты» запрещена. Любая такая инициатива — сначала запись в INVESTIGATION.md + стоп у архитектора.
- Интеграции ЕГАИС/Честный ЗНАК и иные регуляторные системы.
- Разработка транспортной/ГСМ доменной модели Quartermaster (fixtures самодостаточны).
- Изменение публичного CLI-контракта (`version`, exit codes, семантика `validate`, приоритет `--templates-dir`).
- Сетевой доступ в render-time (загрузка бинарников/шрифтов при рендере запрещена).

## 5. Architecture constraints

1. Engine остаётся stateless consumer (ADR-0001 D2): без ORM/DB/HTTP/audit/cache; никаких новых зависимостей от Warehouse Solution.
2. Публичный CLI-контракт неизменен (ADR-0001 D3): те же команды, exit codes, JSON-форматы. Разрешены только аддитивные изменения: расширить `capabilities` перечнем зарегистрированных backends (сейчас захардкожен WeasyPrint — это дефект, устранить); новый опциональный флаг `render --copies N` (default 1, поведение без флага идентично Phase 1).
3. Backend выбирается полем `backend` в manifest.yaml; envelope/validation/registry общие для всех backends.
4. Шаблоны immutable: новые spike-шаблоны — новые id/версии; `warehouse-waybill-ru@0.1.0` и `@1.0` не изменять (baseline as-is).
5. Offline: все зависимости рендера (шрифты, assets, бинарник Typst) присутствуют локально до рендера. Engine в render-time ничего не скачивает.
6. Ошибки — только существующие 11 кодов; новые коды в Phase 2 не добавлять (если очень нужно — стоп у архитектора).
7. Язык host'а остаётся открытым: не тянуть Rust-host из-за Typst; spike живёт в текущем Python-коде.
8. Историческая воспроизводимость: любые golden хранят metadata (engine/backend versions, template id/version, payload hash) — задел под ADR-0001 D10.

## 6. Repository scope

In scope (только `QuartermasterDocumentEngine/`):

```text
engine/qm_engine/      envelope.py (реестр контрактов), render.py (реестр backends, copies),
                       fonts.py (новый), assets.py (новый), paths.py, errors.py (без новых кодов)
backends/qm_backends/  base.py (расширение RenderResult при необходимости),
                       weasyprint_backend.py (fonts/assets), typst_backend.py (новый)
cli/qm_cli/main.py     только обобщение capabilities до реестра backends
contracts/             + transport.vehicle-route-sheet/v1/schema.json,
                       + fuel.monthly-report/v1/schema.json
templates/             + 5 spike-пакетов (§11.4); существующие НЕ трогать
fonts/                 + DejaVu Sans (4 файла) + manifest.json + LICENSE
tests/                 fixtures/, unit/, component/, integration/, harness/, golden/
scripts/               (новый каталог) fetch_typst.py, make_qr_assets.py, bench.py, golden_update.py
doc/spike/             INVESTIGATION.md, PERF-REPORT.md, PHASE2-BACKEND-COMPARISON.md
pyproject.toml         extra [spike]; README.md; .gitignore (.spike/, spike-out/)
```

Дополнение к SPEC v2 layout: `scripts/`, `doc/spike/`, `tests/harness/`, `tests/golden/` — tooling spike'а; фиксируется как допустимое расширение в §1 отчёта.

Out of scope: `Warehouse_web/`, `SyncServer/` (только read-only обследование), корневой репозиторий warehouse_solution.

## 7. Required investigation (задание T1)

Файл: `doc/spike/INVESTIGATION.md`. Результат: подтверждение/уточнение фактов §2 этого TZ своими глазами + ответы на вопросы:

1. WeasyPrint: точная версия в venv engine (ожидается 66.x); поведение `FontConfiguration` + `@font-face` для bundled шрифтов (проверка: PDF содержит embedded подмножество DejaVuSans, а не системный substitute).
2. Typst: актуальный stable (на 2026-08-10: **0.15.1**; исполнитель фиксирует версию, которую реально удалось достать), наличие Linux x64 и Windows x64 бинарников, флаги `compile`, `--format png --ppi`, `--font-path`, `--input`, `--creation-timestamp` (или эквивалент для детерминизма), поведение при отсутствующем шрифте (error vs fallback).
3. Детерминизм: 5 повторных рендеров одного envelope каждым backend'ом → побайтово/визуально идентичны? (WeasyPrint ожид. идентичен; Typst — с фиксированным timestamp.)
4. Доступность git-lfs в окружении (`git lfs version`); если нет — golden-стратегия деградирует до §13.6 fallback.
5. Наличие Windows-среды (runner/ручная машина). Ожидается: нет (прецедент TZ 3.1) → Windows-пункты внешние.
6. Подтвердить факты §2.2–2.4 (шрифты, пагинация, версии) и зафиксировать расхождения, если код изменился.

Evidence: файл с ссылками на файлы/строки и команды проверки.

## 8. Implementation tasks

Зависимости: T1 → {T2,T4} → T3 → {T5,T6} → T7 → T8 → {T9,T10} → T11 → T12.

### T1. Investigation report

- Файлы: `doc/spike/INVESTIGATION.md`.
- Результат: ответы §7, версии, риски.
- Проверка: ревью архитектором до старта T5/T6.
- Evidence: ссылки на код/команды внутри отчёта.

### T2. Контракты spike-семейств

- Файлы: `contracts/transport.vehicle-route-sheet/v1/schema.json`, `contracts/fuel.monthly-report/v1/schema.json`, `engine/qm_engine/envelope.py` (`_DOCUMENT_CONTRACT_SCHEMAS` += 2 записи), `tests/unit/test_envelope.py` (новые кейсы).
- Требования к схемам: draft 2020-12; в отличие от либерального v2 — **строгие** (required-поля, типы, без `additionalProperties: true` на верхнем уровне document). Поля — по §9.2/§9.3.
- Проверка: `pytest tests/unit -k contract`; `qm-render validate` на каждом fixture (после T3).
- Evidence: вывод pytest + validate.

### T3. Fixtures

- Файлы: каждая логическая фикстура — **пара envelope'ов**, различающихся только `template_id`/`template_version`:
  - `tests/fixtures/waybill/waybill-{1,20,75,200,500}.{weasy,typst}.json` — contract `warehouse.operation-document/v2`; `.weasy` → `warehouse-waybill-ru@1.0` (baseline), `.typst` → `spike-waybill-typst@0.1.0`;
  - `tests/fixtures/route-sheet/vehicle-route-sheet-1.{weasy,typst}.json` — contract `transport.vehicle-route-sheet/v1`;
  - `tests/fixtures/fuel/fuel-report-{100,500,1500}.{weasy,typst}.json` — contract `fuel.monthly-report/v1`;
  - генератор `tests/fixtures/generate_fixtures.py` (детерминированный, seeded, запуск вручную, результат в git). Phase 1 fixture `tests/fixtures/waybill-20.json` не трогать (regression).
- Требования к waybill-фикстурам (§9.1): кириллица, реалистичные ТМЦ, длинные имена 2–4 визуальные строки, SKU есть/нет, категория, партия, комментарии, дробные количества, разные единицы.
- Проверка: `qm-render validate --input <каждый из 18>` → exit 0; unit-тест детерминизма генератора (повторный запуск → идентичные байты).
- Evidence: выводы validate (18 envelope'ов = 9 фикстур × 2 backends).

### T4. Bundled pinned шрифты

- Файлы: `fonts/DejaVuSans.ttf`, `fonts/DejaVuSans-Bold.ttf`, `fonts/DejaVuSans-Oblique.ttf`, `fonts/DejaVuSans-BoldOblique.ttf`, `fonts/manifest.json` (имя файла, PostScript/family name, SHA-256, источник), `fonts/LICENSE` (лицензия DejaVu/Bitstream Vera — текст обязателен), `engine/qm_engine/fonts.py`, правки `weasyprint_backend.py`, `tests/unit/test_fonts.py`, `tests/component/test_fonts.py`.
- Источник файлов: системные `fonts-dejavu-core` dev-машины (`/usr/share/fonts/truetype/dejavu/`); происхождение и SHA-256 записать в manifest. Скачивание из сети не требуется; если берётся иной источник — зафиксировать.
- Поведение:
  - `fonts.manifest` в manifest.yaml spike-шаблонов перечисляет обязательные файлы; отсутствие файла в `fonts/` → `FONT_NOT_AVAILABLE` (exit 4) **до** рендера.
  - WeasyPrint: `@font-face` из bundle через `weasyprint.text.fonts.FontConfiguration` (`write_pdf(stylesheets=[...], font_config=...)`); системные шрифты не используются.
  - Typst: `typst compile --font-path <bundle>/fonts`; в шаблоне `#set text(font: "DejaVu Sans")`.
  - Silent fallback запрещён: тест «переименовать файл шрифта → FONT_NOT_AVAILABLE», а не рендер другой гарнитурой.
- Проверка: component-тесты: PDF waybill-20 содержит embedded `DejaVuSans` (проверка pypdf: имена embedded fonts); typst-рендер с `--font-path` использует bundle.
- Evidence: pytest + вывод проверки embedded fonts.

### T5. Assets (envelope.assets) + QR/barcode

- Файлы: `engine/qm_engine/assets.py`, правки `weasyprint_backend.py`, `tests/unit/test_assets.py`, `tests/component/test_assets.py`, `scripts/make_qr_assets.py`.
- Контракт asset'а: `envelope.assets = { "<name>": { "mime": "image/png", "data_base64": "..." } }` (имя — безопасный идентификатор `[a-z0-9_-]+`). Backend материализует assets во временный каталог рендера; шаблоны ссылаются по имени. Declared в шаблоне, но отсутствует/битый base64 → `ASSET_NOT_AVAILABLE` (exit 4).
- QR/barcode: генерируются **на стороне producer'а/скрипта** (`scripts/make_qr_assets.py`: segno для QR, python-barcode для Code128/EAN-13 → PNG, base64 в envelope). Engine-side генерация QR — не Phase 2 (зафиксировать в отчёте как решение: payload остаётся self-contained, engine не знает о стандартах кодирования).
- Проверка: fixture с QR+barcode рендерится обоими backends; изображение присутствует в PDF (проверка наличия XObject image / raster-diff против версии без asset).
- Evidence: pytest + PDF-проверки.

### T6. Typst backend spike

- Файлы: `backends/qm_backends/typst_backend.py`, `engine/qm_engine/render.py` (`_BACKENDS["typst"]`), `spike/typst-pin.json` (version, sha256 linux-x64, sha256 windows-x64, source URL — как документация), `scripts/fetch_typst.py`, `.gitignore` (`.spike/`), `tests/unit/test_typst_backend.py`, `tests/component/test_typst_backend.py`.
- Способ запуска — **subprocess pinned бинарника `typst`** (обоснование §11.1).
- Разрешение бинарника: `QM_TYPST_BINARY` (env) → `<repo>/.spike/typst-<version>/typst` → `PATH`. Нет бинарника → `available() == False`, `BACKEND_NOT_AVAILABLE` (exit 4) при рендере; `capabilities` показывает `available: false` (не падает).
- Механика render: временный каталог → копия файлов шаблона + `document.json` (normalized document = полный envelope.data, как в Phase 1) → `typst compile main.typ out.pdf --font-path <bundle>/fonts` (+ детерминизм-флаг timestamp). Entrypoint шаблона читает `#let doc = json("document.json")`.
- Output formats: `pdf` и `png`. `png` = preview **первой страницы** (`--format png --ppi 150`, возвращается один PNG; `RenderResult.data` остаётся одним blob), `page_count` при этом = полное число страниц документа. Прочие форматы → `UNSUPPORTED_OUTPUT_FORMAT`.
- Ошибки компиляции Typst → `RENDER_FAILED` (exit 5) с stderr Typst в `details.cause` (обрезать до 2 КБ).
- Проверка: unit-тесты на mock-бинарнике (аргументы командной строки, маппинг ошибок, available-логика); component-тесты на реальном бинарнике (pdf/png, шрифты, отсутствие сети).
- Evidence: pytest; `qm-render capabilities` с typst в списке.

### T7. Spike-шаблоны (5 пакетов)

- Каталоги `templates/<id>/<version>/` с `manifest.yaml` + entrypoint:
  | template_id | version | backend | contract | назначение |
  |---|---|---|---|---|
  | `spike-waybill-typst` | 0.1.0 | typst | warehouse.operation-document/v2 | тот же логический layout, что `warehouse-waybill-ru@1.0` |
  | `spike-route-sheet-weasy` | 0.1.0 | weasyprint | transport.vehicle-route-sheet/v1 | строгая печатная форма |
  | `spike-route-sheet-typst` | 0.1.0 | typst | transport.vehicle-route-sheet/v1 | та же форма |
  | `spike-fuel-report-weasy` | 0.1.0 | weasyprint | fuel.monthly-report/v1 | landscape, grouping/subtotals |
  | `spike-fuel-report-typst` | 0.1.0 | typst | fuel.monthly-report/v1 | то же |
- Для каждой пары (route-sheet, fuel) — **единая текстовая спецификация layout'а в manifest-комментарии или `LAYOUT.md` пакета**, чтобы оба backends реализовывали одинаковую форму (честное сравнение).
- `capabilities:` в manifest — токены из словаря: `qr`, `barcode`, `image`, `watermark`, `copies`, `landscape`, `multi-page-table`, `fixed-form`. (Словарь закрепить в INVESTIGATION.md; machine-проверка токенов — вне Phase 2.)
- Проверка: `qm-render inspect-template` для каждого; рендер соответствующих fixtures; structural assertions harness'а (§13).
- Evidence: выводы inspect-template + рендеров.

### T8. Copies / экземпляры / watermark

- Файлы: `engine/qm_engine/render.py` (или `artifacts.py`), `cli/qm_cli/main.py`: `render_options.copies: int ≥ 1` — engine-level: N рендеров с внедрёнными в context `copy_number`/`copies_total`, конкатенация PDF (pypdf). Единое поведение для всех backends. CLI: аддитивный флаг `render --copies N` (default 1; без флага байты вывода идентичны Phase 1 — проверить тестом).
- Маркировка экземпляра («Экземпляр 1 из 2») и watermark — на стороне spike-шаблонов (CSS/Typst background); проверить минимум на waybill-typst и route-sheet-weasy.
- Проверка: integration-тесты: copies=2 → page_count удвоен, маркировка присутствует в тексте страниц (text extraction).
- Evidence: pytest.

### T9. Visual comparison harness

- Файлы: `tests/harness/` (python-пакет: raster, structural, semantic, visual, report), dev-extra зависимости (§11.3), `tests/integration/test_harness.py`.
- Контракт запуска: `python -m tests.harness.compare --fixture <name> --templates <weasy-id@ver>,<typst-id@ver> --out spike-out/compare/<fixture>/`.
- Проверки — по §13. Отчёт `spike-out/compare/<fixture>/report.md` + diff PNG (артефакты, не в git).
- Проверка: harness прогоняется на всех 9 фикстурах; unit-тесты semantic/structural матчеров на синтетических PDF.
- Evidence: report.md по каждому fixture + сводка в PHASE2-BACKEND-COMPARISON.md.

### T10. Performance benchmark

- Файлы: `scripts/bench.py`, отчёт `doc/spike/PERF-REPORT.md`, сырые JSON `spike-out/bench/` (в git — только итоговый JSON-сводка `doc/spike/perf-summary.json`).
- Сценарии/метрики — §14. Прогон на доступной машине; характеристики машины (CPU/RAM/OS) — в шапке отчёта.
- Проверка: все сценарии завершены, failures = 0 (иначе — разбор и запись), числа внесены в матрицу.
- Evidence: PERF-REPORT.md + perf-summary.json.

### T11. Golden artifacts

- Файлы: `tests/golden/index.json`, `tests/golden/<template>-<version>/<fixture>.expected.json`, LFS-трекинг (`*.golden.png`, `*.golden.pdf` в `.gitattributes`), `scripts/golden_update.py`, политика в README.
- Детали — §13.6. Маркер `golden` зарегистрировать в `pyproject.toml` (`[tool.pytest.ini_options].markers`). Если git-lfs недоступен (T1.4) — fallback: golden только как JSON-assertions + CI-артефакты; зафиксировать blocker.
- Проверка: `pytest -m golden` проходит по закоммиченным golden; повторный `golden_update.py` без изменений не даёт diff.
- Evidence: pytest -m golden; git log коммита golden.

### T12. Comparative report + scoring matrix + recommendation

- Файл: `doc/spike/PHASE2-BACKEND-COMPARISON.md`.
- Содержимое: данные T9/T10, заполненная матрица §16 с рубриками и обоснованием каждого балла, проверка hard veto по каждому backend'у, recommendation (A/B/C/D), список решений, отложенных до Phase 5/6.
- Проверка: ревью архитектором; полнота (все критерии матрицы заполнены, все veto проверены).
- Evidence: сам файл + запись в Execution Checklist.

## 9. Fixtures

### 9.1 Warehouse MOVE waybill (`warehouse.operation-document/v2`)

Размеры: **1, 20, 75, 200, 500 строк**. Базовая структура — реальный боевой envelope (`doc/test_templates/template_waybill_MOVE_5l.envelope.json`); генератор расширяет `lines`, сохраняя `operation/sender/receiver/signatures/localization/basis`.

Обязательные свойства набора (распределить по размерам, в 20/75/200/500 — всё сразу):

- кириллица throughout; реалистичные ТМЦ (шиноремонт/автозапчасти/склад — как в prod-примере);
- длинные имена 80–160+ символов → 2–4 визуальные строки при 40 chars/visual line;
- `item_sku` заполнен у части строк, у части пуст/отсутствует;
- `category_name` (несколько разных, включая «Без категории»);
- `batch` у части строк; `comment` у части строк (включая длинный);
- дробные количества (2.5, 0.333, 12.75) и целые;
- единицы: шт, кг, л, м, упак, пара (разные `unit_name`/`unit_symbol`);
- operation_type = MOVE (строжайшая последняя страница по §2.3).

Пагинационные правила склада, которые обязаны проверить fixtures (источники — реальный код, не выдуманы):

| Правило | Значение | Источник |
|---|---|---|
| Страница | A4 portrait | `waybill_pdf.html` `@page` |
| Margins | 16mm top, 14mm left/right, 14mm bottom | там же |
| Полезная высота | 267 мм (297−16−14) | TZ-V3.1I I2 |
| Overhead первой страницы | ≈78 мм (полный header) | TZ-V3.1I I2 |
| Визуальная строка имени | 40 символов | `NAME_CHARS_PER_VISUAL_LINE` |
| Ёмкость первой страницы | 22 units | `FIRST_PAGE_UNITS` |
| Ёмкость средних | 28 units | `MIDDLE_PAGE_UNITS` |
| Ёмкость последней (MOVE) | 19 units (20 уже выталкивает подписи на 3-ю страницу) | `LAST_PAGE_UNITS` |
| Одностраничная (MOVE) | 15 units | `SINGLE_PAGE_UNITS` |
| Header первой страницы | полный: Грузоотправитель/Грузополучатель/Основание | шаблон |
| Header последующих | короткий: только заголовок | шаблон |
| Подпись кладовщика | на каждой странице | шаблон |
| Финальный подписной блок | только на последней; MOVE: Операцию разрешил / Водитель / Начальник базы / Груз принял | `_build_extra_signatures` |
| Footer | «Лист N из M» при total_pages > 1 | шаблон |
| Строка таблицы | `page-break-inside: avoid`; `thead` повторяется | шаблон |
| Колонки | № 11mm, Ед. 24mm, Кол-во 28mm, имя гибкое, wrap anywhere | шаблон |

Baseline-шаблон `warehouse-waybill-ru@1.0` реализует упрощённый layout (CSS auto-split, `@bottom-center` счётчик) и **не переписывается**; правила выше — требования к fixtures и ориентир для новых парных шаблонов (T7), а также метрика «насколько backend позволяет выразить производственную форму» (критерий «Fixed forms» матрицы).

### 9.2 Vehicle route sheet (`transport.vehicle-route-sheet/v1`)

Один fixture `vehicle-route-sheet-1.json`. Минимальный состав document-секции:

- 1 автомобиль (марка, модель, гос.номер, гаражный номер), 1 водитель (ФИО, табельный номер, класс);
- 50 маршрутных записей: дата-время выезда/возврата, адрес откуда/куда, цель, пробег км, время в пути;
- 10 заправок: дата-время, АЗС, топливо (вид), объём л, сумма;
- одометр: начало/конец; остаток топлива: начало/конец; получено топлива всего; расход (норма/факт);
- подписные поля: водитель, механик, диспетчер; часть полей (например «показания при возврате», подпись медика) — пустые строки для ручного заполнения (проверка fixed-form с пустыми ячейками);
- даты/время в машиночитаемом ISO в payload; форматирование — задача шаблона.

Цель fixture: строгая печатная форма + большое число отдельных полей (критерий «Fixed forms / physical geometry»). Доменную модель транспорта не строить.

### 9.3 Monthly fuel report (`fuel.monthly-report/v1`)

Размеры: **100, 500, 1500 строк**; ≥10 единиц техники; landscape; группировка по технике с подытогами; grand total; decimal-значения (л, км, руб); worst case 20–50 страниц (1500 строк).

Опционально (не gate): простая диаграмма (bar: расход по технике) как статический PNG-asset через `scripts/make_qr_assets.py`-подобный скрипт. Если backend не позволяет разместить её внятно — зафиксировать в отчёте как ограничение, не ломая fixture.

## 10. WeasyPrint baseline

- Baseline = **текущий `WeasyPrintBackend` + шаблон `warehouse-waybill-ru@1.0` без переписывания** (контрольная точка Phase 1).
- Для route-sheet и fuel report baseline'ом считается новый парный шаблон `spike-*-weasy@0.1.0` (у обоих backends одинаковая спецификация формы — §T7).
- Production Django/SyncServer рендеры используются только как визуальный референс: harness принимает внешний reference PDF (например, сохранённый из Django) и строит diff без автоматических gate'ов.
- Показатели baseline, которые измеряются и заносятся в отчёт: все метрики §14; embedded fonts; page count/геометрия по fixtures; поведение на длинных таблицах (auto-split + thead repeat).
- Версия WeasyPrint в venv engine — из `pyproject.toml` (`weasyprint>=66`); зафиксировать фактическую установленную версию в PERF-REPORT.md (ожидается 66.x; major выше 66 — стоп у архитектора).

## 11. Typst backend

### 11.1 Способ запуска: subprocess pinned бинарника

Решение для spike (обратимо, без ADR):

- **subprocess `typst`** (pinned версия, SHA-256 в `spike/typst-pin.json`).
- Обоснование: (1) язык host'а engine открыт (ADR-0001 D11/D13) — бинарник переносим в будущий не-Python host без переписывания; (2) честный замер cold-start именно так, как будет вызываться CLI; (3) нет нативных wheel-зависимостей в venv; (4) тривиальная версия-фиксация и offline-перенос (файл можно скопировать вручную).
- Альтернатива (PyPI-пакет `typst`, in-process) — разрешена как дополнительное измерение в T10 (in-process vs subprocess delta), но не заменяет subprocess-путь и не становится контрактом Phase 2.
- Бинарник в `.spike/` (gitignored); доставка: `scripts/fetch_typst.py` (download + SHA-256 verify, одноразово, не в render-time) либо ручное копирование + `QM_TYPST_BINARY`.

### 11.2 Требования к реализации

По §T6. Дополнительно:

- `typst_backend.py` не содержит бизнес-логики и не знает о конкретных шаблонах; только: подготовить временный каталог (копия пакета + `document.json`), вызвать бинарник, забрать артефакт, маппить ошибки.
- Детерминизм: фиксированный timestamp создания PDF (флаг/окружение — по итогам T1.2), иначе golden-сравнения нестабильны.
- `available()` не вызывает сеть; только наличие файла + `typst --version` (таймаут 5 с).

### 11.3 Dev-зависимости spike'а

`pyproject.toml` extra `[spike]`: `scikit-image` (SSIM), `PyMuPDF` (raster/text), `segno` (QR), `python-barcode` (линейные коды), `Pillow` (растры), `psutil` (бенчмарк). Установка: `pip install -e ".[dev,spike]"`. Core-зависимости (`[project].dependencies`) **не менять** — рендер не должен требовать spike-пакетов.

### 11.4 Spike-шаблоны

По §T7. Требования к typst-шаблонам: entrypoint `main.typ`; данные из `json("document.json")`; шрифт `DejaVu Sans` из `--font-path`; page-настройки в шаблоне (A4 portrait для waybill/route-sheet, A4 landscape для fuel report); таблицы с повторяемым header'ом; `LAYOUT.md` с текстовой спецификацией формы (общий для weasy/typst пары).

## 12. Fonts/assets

Политика (ADR-0001 D9, по итогам font-аудита §2.4):

1. Renderer не полагается на случайные системные шрифты; шрифты pinned (файл + SHA-256), распространяются с bundle, одинаковы на Linux и Windows.
2. Фаза 2 выбирает **DejaVu Sans** — единственная гарнитура, фактически используемая всеми тремя текущими pipeline'ами (SyncServer, Django, engine Phase 1); Noto и прочие не рассматриваются, пока нет причины. 4 файла (Regular/Bold/Oblique/BoldOblique) + LICENSE + `fonts/manifest.json`.
3. Обязательная кириллица; проверка: кириллические глифы присутствуют в embedded font'е PDF (или рендер кириллицы не даёт tofu — визуальная проверка Level 9).
4. Missing required font → `FONT_NOT_AVAILABLE` (exit 4), silent fallback запрещён (§T4).
5. Assets: только self-contained (`envelope.assets`, base64) либо файлы пакета шаблона; сетевых URL в шаблонах быть не должно (§T5).
6. До spike (T4 до T6/T7) — шрифты уже обязаны работать в обоих backends.

## 13. Visual migration / comparison harness

Автоматический конвертер Jinja2 → Typst **запрещён**. Harness сравнивает независимые рендеры одного fixture.

### 13.1 Растеризация

Оба PDF → PNG одним инструментом (PyMuPDF), фиксированно **150 DPI**, постранично. Typst-PNG (`--format png`) используется только для preview-критерия матрицы, не для сравнения.

### 13.2 Structural checks (hard gate)

Page count; paper size/orientation (MediaBox); наличие обязательных блоков (header, таблица, подписи, footer «Лист N из M»); число строк таблицы (text extraction, подсчёт паттернов номеров строк). Ожидаемые значения — в `tests/golden/.../expected.json`.

### 13.3 Semantic checks (hard gate)

Document number; даты; имена ТМЦ (выборка); количества; единицы; итоги (total_lines/подытоги/grand total); подписные лейблы («Кладовщик», «Сдал», «Принял», роли route sheet); наличие QR/barcode-изображений (raster-детекция региона; автодекодирование QR — опционально, не gate). Значения берутся из fixture (источник истины), сравниваются с текстом PDF. Любое несовпадение значения → **veto V1** для backend'а в отчёте.

### 13.4 Visual checks

SSIM постранично (scikit-image), changed pixel ratio (порог абсолютной разницы), diff PNG в артефакты.

### 13.5 Калибровка порогов (обязательный первый шаг)

Reference-значения SPEC (SSIM ≥ 0.995, changed pixels ≤ 0.5%) **сначала калибруются**: 5 повторных рендеров одного fixture одним backend'ом одним шаблоном → распределение SSIM/changed pixels (noise floor). Итоговые пороги golden-регрессии = noise floor с запасом (но не выше 0.995/0.5%, если noise floor позволяет). Результат калибровки — в PHASE2-BACKEND-COMPARISON.md.

Кросс-backend сравнение (weasy vs typst) по SSIM **не gate'ится** (разные шаблоны не обязаны совпадать пиксельно): hard gate'ы — structural + semantic; visual — информация + `REVIEW_REQUIRED` для неожиданных регионов diff (артефакты растеризации, обрезанный текст, пропавшие блоки).

### 13.6 Golden artifacts

```text
tests/golden/
  index.json                          # реестр: fixture, template@version, backend,
                                      # engine_version, backend_version,golden-файлы, пороги
  <template-id>-<version>/
    <fixture>.expected.json           # structural + semantic assertions (обычный git)
    <fixture>.page-<N>.golden.png     # Git LFS, только репрезентативные страницы
    <fixture>.golden.pdf              # Git LFS, только acceptance-набор
```

Правила:

- В git (обычном): fixtures, expected.json, index.json, LAYOUT-спецификации.
- В Git LFS: representative golden PNG (≤2 страницы на шаблон) и acceptance PDF: waybill-75 (weasy+typst), route-sheet-1 (weasy+typst), fuel-500 (weasy+typst). **Не** коммитить PDF/PNG всей матрицы размеров.
- Сгенерированные артефакты (benchmark-выводы, diff PNG, промежуточные render'ы) → `spike-out/` (.gitignore), живут как CI/local артефакты.
- Обновление golden: только `scripts/golden_update.py` + коммит с обоснованием; изменение golden без изменения шаблона/backend'а → REVIEW_REQUIRED.
- Fallback при отсутствии git-lfs (T1.4): golden = только expected.json; PNG/PDF — артефакты; blocker в отчёте.

## 14. Performance benchmark

Машина: фактическая dev-машина; характеристики (CPU/RAM/OS/Python/версии backends) — в шапке PERF-REPORT.md. Reference-цели SPEC (4 vCPU/8 GB) — ориентир, не догма; главный компаратор — **измеренный WeasyPrint baseline** на той же машине.

Сценарии (для каждого документа: waybill-20, waybill-500, fuel-1500):

| Сценарий | Определение |
|---|---|
| cold | первый subprocess-вызов `qm-render render` в сессии (включая старт интерпретатора/бинарника) |
| 10 sequential | 10 последовательных subprocess-вызовов |
| 10 parallel | 10 одновременных процессов |
| 50 pool=4 | 50 рендеров, concurrency 4 (subprocess-пул) |

Метрики: startup (cold отдельно), p50/p95 latency, CPU time, peak RSS (`/usr/bin/time -v` или psutil-поллинг), размер вывода (байты PDF), failures (0 допускается; каждый failure разбирается), размер дистрибуции (venv WeasyPrint `du -sh` vs бинарник Typst), runtime-зависимости (список).

Дополнительно: in-process Typst (PyPI) vs subprocess — одно измерение для отчёта (не gate).

Проходные ориентиры (из SPEC, калибруются по baseline): cold 20 строк ≤1.5s target/2.5s hard; warm ≤0.7s/1.2s; 500 строк ≤4s/7s; 1500 строк ≤8s/15s; 50 docs pool=4 ≤30s/60s; worker RAM ≤400MB target/700MB hard. Если baseline WeasyPrint сам не проходит hard-границы — фиксировать как свойство baseline, не подгонять цели.

## 15. Test ladder

| Level | Что | Команды/инструменты |
|---|---|---|
| 1 Static | lint/format/types/валидность manifest+схем | `ruff check .`, `ruff format --check .`, `mypy engine backends cli`, jsonschema-проверка manifest'ов (unit) |
| 2 Unit | typst config/available/маппинг ошибок, registry, contracts, fonts, assets, copies | `pytest tests/unit` |
| 3 Component | реальный WeasyPrint и Typst рендеры: валидный PDF, embedded fonts, text/content | `pytest tests/component` |
| 4 Contract | 6 боевых envelope Phase 1 + новые spike-контракты + backward compatibility | `pytest tests/integration -k contract` + `qm-render validate` на всех fixtures |
| 5 Integration | CLI выбирает backend по manifest; file/stdin/stdout; ошибки; fonts/assets; copies | `pytest tests/integration` |
| 6 Cross-platform | Linux offline smoke (`unshare -n`); Windows smoke при наличии среды; кириллические пути (входной файл и каталог с кириллицей) | скрипт smoke; вручную |
| 7 Performance | все сценарии §14 | `python scripts/bench.py` |
| 8 Visual regression | harness, golden, semantic/structural, diff | `python -m tests.harness.compare ...`, `pytest -m golden` |
| 9 Acceptance | фактический просмотр: многостраничная накладная (200/500), путевой лист, большой ГСМ-отчёт (1500) — оба backends | глаза + пометки в отчёте |

Docker-стенд Warehouse Solution не требуется (engine автономен).

## 16. Regression requirements

- 65 тестов Phase 1 зелёные без изменений ожидаемого поведения; новые тесты — сверх.
- `qm-render version` выдаёт ровно `{"engine": "0.1.0", "engine_contract_versions": ["1.0.0"]}`.
- `validate`: семантика и exit codes без дрейфа (те же INVALID_PAYLOAD/UNSUPPORTED_* сценарии).
- `--templates-dir` > `QM_TEMPLATES_DIR` > bundle default — сохраняется во всех командах.
- `warehouse-waybill-ru@0.1.0` и `@1.0` рендерят все прежние fixtures/envelopes.
- Offline CLI сохраняется: render-path не делает сетевых вызовов (проверка `unshare -n` smoke); БД/ORM/HTTP не появляются.
- Acceptance Phase 1 работает: `cat tests/fixtures/waybill-20.json | qm-render render --stdin --stdout --format pdf > /tmp/waybill.pdf`.

## 17. Evidence requirements

Отчёт исполнителя включает таблицу:

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|
| Static | `ruff check . && ruff format --check . && mypy engine backends cli` | pass/fail | вывод |
| Unit/Component/Integration | `pytest` (кол-во тестов до/после) | pass/fail | вывод |
| Contract validate | `qm-render validate` × 18 spike-envelope'ов + Phase 1 fixture + 6 боевых envelope | pass/fail | вывод |
| Fonts | embedded-font check + FONT_NOT_AVAILABLE тест | pass/fail | pytest id |
| Typst render | component-тесты + acceptance PDF | pass/fail | пути PDF |
| Harness | compare-отчёты по 9 fixtures | pass/REVIEW_REQUIRED | spike-out/…/report.md |
| Perf | bench.py | pass/fail | doc/spike/PERF-REPORT.md |
| Linux offline smoke | `unshare -n` рендер обоих backends | pass/fail | лог |
| Windows smoke | тот же набор | pass / blocked | пометка «нет Windows-среды» |
| Acceptance view | просмотр 3×2 документов | done | пометки в COMPARISON.md |

## 18. Deliverables

1. Typst backend spike (`typst_backend.py`, pin, fetch-скрипт, тесты).
2. Измеренный WeasyPrint baseline (PERF-REPORT.md, structural/semantic данные).
3. 9 fixtures (waybill 1/20/75/200/500; route sheet; fuel 100/500/1500) + генератор.
4. 5 spike-шаблонов с manifest'ами и LAYOUT-спецификациями.
5. Bundled pinned шрифты + enforcement (FONT_NOT_AVAILABLE) в обоих backends.
6. Visual comparison harness + калибровка порогов.
7. Performance benchmark (все сценарии §14).
8. Linux offline smoke; Windows smoke либо документированный внешний blocker.
9. Golden-структура + политика (или fallback-blocker).
10. `doc/spike/PHASE2-BACKEND-COMPARISON.md`: данные, заполненная scoring matrix (§19), hard veto, recommendation.

Явно: **NO production migration in Phase 2; NO deletion of existing renderer; NO rewrite of Django integration; NO rewrite of SyncServer rendering.**

## 19. Backend scoring matrix

Веса — из SPEC v2 / ROADMAP Phase 5. Оценка 0–5 по каждому критерию с обязательной рубрикой (что значит 0/3/5) и ссылкой на измерение из T9/T10; итог = Σ(оценка×вес).

| Criterion | Weight |
|---|---:|
| PDF quality / predictability | 20 |
| Pagination / tables | 15 |
| Fixed forms / physical geometry | 15 |
| Template development experience | 10 |
| Windows deployment | 10 |
| Linux/container deployment | 8 |
| Offline suitability | 7 |
| Cyrillic/fonts | 5 |
| Preview formats | 4 |
| Performance | 3 |
| Distribution size | 2 |
| Maintainability | 1 |

### Hard veto (вне взвешенной суммы)

Backend не может победить при любом счёте, если выполнено любое из:

- **V1 Value corruption**: semantic check не прошёл хотя бы на одном fixture (значения искажены, пропущены, переставлены).
- **V2 Instability**: недетерминированный вывод между повторными рендерами (после исключения известных причин типа timestamp), или плавающие page count/размеры.
- **V3 Form failure: строгая форма невыразима** (route sheet structural gate провален: геометрия/поля/подписные блоки не достижимы).
- **V4 Deployment failure**: не разворачивается offline pinned-артефактом на Linux или Windows (при наличии среды; при отсутствии Windows-среды — пометка «не проверено», veto не применяется, но риск фиксируется).
- **V5 Offline violation**: render-time требует сеть/внешний сервис.
- **V6 Font failure**: кириллица с bundled шрифтами не рендерится корректно.

Veto проверяется по каждому backend'у явно и записывается в отчёт; mixed-исход (C) допустим только если ни один backend не имеет veto.

## 20. Acceptance criteria

1. Все команды выполняются на чистой машине с `pip install -e ".[dev,spike]"` и бинарником Typst по pin'у:

```bash
# baseline (Phase 1 контракт)
cat tests/fixtures/waybill-20.json | qm-render render --stdin --stdout --format pdf > /tmp/wb20-weasy.pdf

# typst-вариант накладной
qm-render render --input tests/fixtures/waybill/waybill-20.typst.json --output /tmp/wb20-typst.pdf

# путевой лист и ГСМ — оба backends
qm-render render --input tests/fixtures/route-sheet/vehicle-route-sheet-1.weasy.json --output /tmp/rs-weasy.pdf
qm-render render --input tests/fixtures/route-sheet/vehicle-route-sheet-1.typst.json --output /tmp/rs-typst.pdf
qm-render render --input tests/fixtures/fuel/fuel-report-1500.weasy.json --output /tmp/fuel-weasy.pdf
qm-render render --input tests/fixtures/fuel/fuel-report-1500.typst.json --output /tmp/fuel-typst.pdf

# копии (аддитивный флаг; без него вывод идентичен Phase 1)
qm-render render --input tests/fixtures/waybill/waybill-20.weasy.json --output /tmp/wb20-x2.pdf --copies 2
```

(`.weasy.json`/`.typst.json` — пары envelope, различающиеся только `template_id`/`template_version`; генератор T3.)

2. `pytest` зелёный (65 Phase 1 + новые), `ruff`/`mypy` PASS.
3. Harness: structural+semantic gates пройдены всеми парами; visual отчёты с калиброванными порогами сохранены.
4. PERF-REPORT.md содержит все сценарии §14 для обоих backends, failures разобраны.
5. Viewing Level 9 выполнен: 3 документа × 2 backends просмотрены, пометки в отчёте.
6. PHASE2-BACKEND-COMPARISON.md: матрица заполнена, veto проверены, recommendation (A/B/C/D) дана.
7. Regression §16 выполнен.
8. Ни один файл вне `QuartermasterDocumentEngine/` не изменён.

## 21. Definition of Done

- Execution Checklist 0–14 закрыт с evidence (допустимы unchecked только Windows-пункты и git-lfs-fallback с пометкой blocker).
- Отчёты T1/T10/T12 закоммичены в `dev`; golden — по политике §13.6.
- Публичные контракты Phase 1 неизменны (§16).
- Архитектор принял comparative report; решение о backend'е **не** принимается в Phase 2 — только рекомендация для Phase 5.

## 22. Out of scope

- Изменения `Warehouse_web/`, `SyncServer/`, корневого репозитория.
- Production-миграция рендеров, Django BFF-интеграция engine (Phase 6), WPF (Phase 8).
- Новые document types вне трёх spike-классов; канонические контракты семейств (Phase 6–10).
- Engine-side генерация QR/barcode, ЕГАИС/Честный ЗНАК.
- Очередь рендеров, артефакт-хранилище, batch (триггеры Phase 11).
- HTML preview, интерактивный preview (вне png-preview).

## 23. Known external blockers

| Blocker | Влияние | Обход |
|---|---|---|
| Нет Windows-среды (прецедент TZ 3.1) | Windows smoke, veto V4 по Windows — внешние | пометка «нет Windows-среды»; manual-инструкция в README |
| git-lfs может быть не установлен | golden PNG/PDF в git | fallback §13.6 (JSON-assertions + CI-артефакты) |
| Сеть для загрузки бинарника Typst может быть недоступна | T6 setup | ручное копирование + `QM_TYPST_BINARY`; SHA-256 сверка обязательна |
| PyPI-доступ для `[spike]` extra (scikit-image/PyMuPDF) | harness/bench setup | только dev-окружение; render-path не затронут |
| В dev-машине нет `fonts-dejavu-core` | источник bundled шрифтов | любой легальный источник с фиксацией SHA-256 и лицензии |

---

# ARCHITECT REVIEW NOTES

## 1. Расхождения SPEC/ROADMAP vs реальный код Phase 1

1. `capabilities` CLI хардкодит единственный WeasyPrint backend (`cli/qm_cli/main.py:88`) вместо перечисления зарегистрированных backends — дрейф от идеи реестра; устраняется в T6 (единственное изменение CLI в Phase 2).
2. Manifest-поля `capabilities`, `fonts`, `assets` присутствуют, но не enforce'ятся и не имеют словаря — SPEC ожидает их рабочими; Phase 2 закрывает fonts/assets, словарь capabilities вводит как декларативный (machine-проверка — позже).
3. `warehouse.operation-document/v2` намеренно либерален (`additionalProperties: true`, required только `lines`) — осознанный компромисс Phase 1 («brazed»); канонизация в Phase 6. Риск: spike-контракты, написанные строгими, создадут разнородность семейства — принято: новые семейства строгие сразу, v2 ужесточается в Phase 6.
4. SPEC v2 §«репозиторий» не содержит `scripts/`, `tests/harness/`, `tests/golden/`, `doc/spike/` — Phase 2 добавляет их как tooling; зафиксировать в SPEC при следующем пересмотре.
5. Envelope `assets` объявлен в схеме, но игнорируется движком — Phase 2 реализует (T5).
6. `RenderResult.warnings` не используется ни одним backend'ом — оставить как есть, при случае заполнить в Typst (предупреждения компилятора).

## 2. Риски, которые стоит закрыть до/в начале Phase 2

1. **Машино-зависимые шрифты** (ни один pipeline не bundle'ит шрифты) → любые golden до T4 бессмысленны. Порядок работ T4 до T6/T9 обязателен.
2. **SyncServer-контейнер, по оценке, не рендерит PDF** (нет pango/fontconfig в Dockerfile) — вне scope Phase 2, но зафиксировать в INVESTIGATION.md как долг производства.
3. **Django `RenderedDocumentArtifact` расходится с ADR-0029 §9.3** (in-place update вместо новых ревизий; нет осей engine/backend/contract) — риск Phase 6, не Phase 2.
4. **Два расходящихся WeasyPrint-пинa** (`==66.0` SyncServer, `>=66,<67` Django, `>=66` engine) — для spike зафиксировать фактическую версию engine; унификация — Phase 6.
5. В репозитории engine есть чужой незакоммиченный staged rename `doc/TZ-PHASE1-CLI-SKELETON.md → doc/archive/` (параллельная сессия) — исполнителю Phase 2 не трогать, коммитить только свои pathspec'ы.

## 3. Решения, которые нельзя принять без spike

- Primary backend (Typst vs WeasyPrint vs mixed) — только после T9/T10 + матрицы.
- Долгосрочный способ интеграции Typst (subprocess vs in-process library vs embedded) — spike даёт только subprocess-данные + одну in-process точку.
- Модель пагинации: CSS auto-split (WeasyPrint) vs content-aware pre-pagination в host'е (как в Django) vs native Typst-поток. Typst не имеет CSS-пагинации; если строгие формы склада потребуют content-aware разбиения, это общий механизм host'а поверх обоих backends — вопрос Phase 6, spike лишь покажет цену native-подхода в Typst.
- Engine-side vs producer-side генерация QR/barcode (Phase 2: producer-side; пересмотр по итогам опыта с assets).
- Пороги visual regression после калибровки noise floor.

## 4. Hard veto criteria

V1 value corruption; V2 instability; V3 строгая форма невыразима; V4 deployment failure (Linux/Windows); V5 offline violation; V6 font/Cyrillic failure. Определения — §19. Дополнение: mixed-вариант допустим только при отсутствии veto у обоих.

## 5. Нужен ли отдельный ADR до реализации Phase 2?

**Нет, ADR до spike не нужен.** Границы уже заданы ADR-0001 (D2 stateless, D3 CLI, D7 backend-абстракция без назначенного победителя, D9 шрифты, D12 ошибки) и SPEC v2; Phase 2 не принимает необратимых решений — он производит данные. Выбор subprocess-Typst обратим и задокументирован в самом TZ (§11.1). ADR-0030 («выбор primary backend») пишется после Phase 2/5 на основе матрицы и veto — вот он обязателен до любой production-интеграции.

## Phase 2.1 — Backend decision readiness hardening

Phase 2.1 closes the review-findings raised by the GLM review of commit `1c3ee5c` (Phase 2 T9-T12). It is the last step before the spike data can be handed off to the Phase 5/6 architect for the backend decision.

### P2.1 Findings

| ID | Finding | Resolution |
|---|---|---|
| W1 | Typst backend не передаёт полный envelope в шаблон | `backends/qm_backends/typst_backend.py` теперь пишет полный `normalized_document` (за исключением внутреннего `__assets__`) в `document.json`. Шаблоны читают envelope-поля как `doc.<field>`, inner document как `doc.document.<field>`. |
| W2 | "Byte-deterministic" в COMPARISON вводит в заблуждение | Typst: byte-deterministic (verified SHA-256 3/3 в `tests/component/test_typst_backend.py::test_typst_determinism`). WeasyPrint: visually/structurally deterministic, NOT byte-deterministic (FlateDecode varies между процессами). Scoring matrix обновлена: WeasyPrint −20 на PDF quality / predictability. |
| W3 | Расхождение в размере пакета WeasyPrint (24.2 MB vs 2.5 MB vs 2.9 MB actual) | Исправлено: 2.9 MB = размер `site-packages/weasyprint/`. Добавлен контекст: pure-Python transitive deps 35.5 MB + native system libs ~50 MB apt-installed (NOT in venv). Phase 5 deployment MUST budget for these. |
| W4 | Отчёт не отражает финального состояния (pytest 203 → 212; mypy warnings → clean) | `pytest -q` = 212 passed; `mypy engine backends cli` = Success: no issues found in 15 source files (после фикса `pyproject.toml python_version` 3.11→3.12 + `type: ignore` для barcode imports). |
| N1 | Watermark не реализован | Добавлен CLI `--watermark/--no-watermark` (default `--no-watermark`); engine injects `render_options['watermark']` на двух уровнях. Шаблоны waybill-typst и route-sheet-weasy рендерят diagonal "ОБРАЗЕЦ" при `--watermark`. Phase 1 byte-identical для default. |
| N2 | `capabilities` per-backend output_formats не точны | `TypstBackend` экспортирует `SUPPORTED_FORMATS = ("pdf", "png")`. CLI деривирует per-backend. Verified: typst `["pdf","png"]`, weasyprint `["pdf"]`, top-level union `["pdf","png"]`. |
| N3 | Windows-binary SHA honesty | `binaries.windows-x64.archive_sha256 == "unverified-no-windows-env"` и `binary_sha256 == "unverified-no-windows-env"` оставлены как есть (honest, TZ §23). Phase 5 architect верифицирует в Windows-среде. |

### P2.1 Sub-tasks

- [x] §1 Typst full envelope (`typst_backend.py` + 3 Typst templates + `tests/component/test_typst_backend.py` + `tests/harness/semantic.py`)
- [x] §3 Typst waybill density fix (margins 16/14 → 12mm; body 10pt → 9pt; table 9pt → 8pt, inset 4pt → 2pt): waybill-500 Typst page count 124 → 42 (ratio to WeasyPrint 6.9× → 2.3×)
- [x] §2 + §5 Determinism terminology + evidence refresh (`PHASE2-BACKEND-COMPARISON.md` и `PERF-REPORT.md` обновлены)
- [x] §4 Representative perf benchmark (24 cells re-run; `perf-summary.json` обновлён)
- [x] §6 Human acceptance package (10 PDFs в `spike-out/acceptance/`; 12-item checklist в `doc/spike/HUMAN-ACCEPTANCE.md`; sign-off ожидается от пользователя)
- [x] §7 Regression gates (pytest 212 passed; ruff/mypy clean; `qm-render version` contract unchanged; offline 0 network syscalls)

### P2.1 Final state

- 212 tests passing (was 65 Phase 1 baseline → 176 Phase 2 → 210 Phase 2 T9-T12 → **212 Phase 2.1**)
- `ruff check` clean, `ruff format` clean, `mypy engine backends cli` clean
- `qm-render version` = `{"engine":"0.1.0","engine_contract_versions":["1.0.0"]}` — contract unchanged
- Recommendation (provisional): **Typst is the provisional preferred backend for Phase 5** (scoring: Typst 462, WeasyPrint 376; diff +86 in favour of Typst; no vetoes). Provision статус из-за V4 Windows NOT-VERIFIED.
- TZ checklist items 0–14 all `[x]`; windows blocker documented under V4.

### P2.1 Out-of-scope (per task contract)

- NO production migration of any pipeline (Warehouse_web/, SyncServer, Django BFF, templates immutable: warehouse-waybill-ru@0.1.0/1.0 unchanged).
- NO deletion of any renderer.
- NO new ADR. ADR-0030 ("primary backend") is the Phase 5 architect's decision; Phase 2.1 only produces the readiness data.
- NO Phase 5 work. The architect receives the data via the reports and the human acceptance sign-off.

Phase 2 spike is officially closed after Phase 2.1 sign-off.

## Phase 2.1.1 — Typst determinism finding M1 (close-out)

Phase 2.1 close-out review flagged that `test_typst_determinism` was flaky (~3% failure rate in 100-iteration runs) — renders that crossed a wall-clock second boundary produced different SHA-256 hashes despite identical input.

### P2.1.1 Findings

| ID | Finding | Status |
|---|---|---|
| M1 | `test_typst_determinism` периодически fails (3% / 100 runs) | **closed** |

### P2.1.1 Root cause

**Typst 0.15.1 ignores `TYPST_TIMESTAMP` env var on Linux.** The production code set this env var to pin the PDF `/CreationDate` metadata, expecting Typst to honour it. Per Typst 0.15.x docs the env var should set the same value as `--creation-timestamp`, but in practice only the explicit CLI flag produces a pinned timestamp on Linux. Without the flag Typst uses wall-clock time → `D:20260811092726+09'00` vs `D:20260811092727+09'00` for renders crossing a second boundary → different `/ID` hash → different SHA-256.

Verified by:
* `TYPST_TIMESTAMP=1700000000 typst compile ...` — 5 renders across 5 seconds, all different SHA.
* `typst compile --creation-timestamp 1700000000 ...` — 5 renders across 5 seconds, all identical SHA.

### P2.1.1 Diagnostic harness

`scripts/diag_typst_determinism.py` runs N series × 3 renders and:
* captures the SHA of every PDF,
* extracts trailer keys, /ID, /CreationDate, /ModDate, page count, MediaBox, font subset names,
* reports divergent series + per-series position histogram.

Pre-fix diagnostic (50 series × 3 renders): 2 divergent series (4%). In both cases render #0 was 1 wall-clock second earlier than renders #1 and #2. The only metadata deltas: `/ID`, `/CreationDate`, `/ModDate` (1 second difference). Page count, MediaBox, fonts, content identical.

### P2.1.1 Fix

`backends/qm_backends/typst_backend.py` — pass `--creation-timestamp <unix>` CLI flag explicitly (in both the main render path and the page-count-via-PDF path). The env var is still set for forward compatibility.

`DEFAULT_TYPST_TIMESTAMP = 1700000000` (Nov 2023) is unchanged; honoured by `os.environ.get("TYPST_TIMESTAMP") or str(DEFAULT_TYPST_TIMESTAMP)`.

### P2.1.1 Verification

* Diagnostic post-fix: **100 series × 3 renders = 0 divergence** (was 2/50 = 4% pre-fix).
* `test_typst_determinism` × 100 iterations: **0 failures** (was 3/100 pre-fix).
* `test_typst_determinism_across_second_boundary` × 10 iterations: **0 failures** (new regression test that sleeps 1.2 s between renders to force a wall-clock second boundary).

### P2.1.1 Updated terminology (verified, not claimed)

| Backend | PDF quality / determinism |
|---|---|
| **Typst** | **byte-deterministic** when `--creation-timestamp` is passed (verified 100×3 = 0 divergence). Plus visually / structurally deterministic (page count, MediaBox, fonts, extracted text stable). |
| WeasyPrint | visually / structurally deterministic (page count + extracted text stable). **NOT byte-deterministic** — FlateDecode stream length varies between separate processes (documented in `tests/unit/test_copies.py`). |

Scoring matrix is unchanged from Phase 2.1: WeasyPrint 376 (4 on PDF quality / predictability), Typst 462 (5). Diff: +86 in favour of Typst. The Typst byte-deterministic claim is now backed by a reproducible test (`test_typst_determinism` 100/100 + `test_typst_determinism_across_second_boundary` 10/10) and a dedicated diagnostic harness.

### P2.1.1 Out-of-scope (per task contract)

- NO production migration.
- NO new ADR.
- NO Phase 5 work.
- The Typst scoring of 5/5 for "PDF quality / predictability" is now evidence-backed (not merely claimed).

## Phase 2.1.2 — QDE M1 re-verification (determinism flake close-out)

The QDE Phase 2.1 review re-opened M1 as the only outstanding MAJOR finding, asking for an independent reproduction campaign, proof that the component test actually exercises the renderer, a byte/structural/semantic/visual comparison of divergent PDFs, an explicit determinism classification, a scoring re-check, doc updates and a full regression. All of it was performed; M1 is confirmed closed.

### P2.1.2 Reproduction (frequency of the flake)

| Run | Renders | Divergent series |
|---|---|---|
| `scripts/diag_typst_determinism.py --series 50 --renders 3` (minimal template) | 150 | **0** |
| `scripts/diag_typst_determinism.py --series 100 --renders 3` (minimal template) | 300 | **0** |
| `qm-render render` × 10 each: `waybill-500.typst`, `fuel-report-1500.typst`, `vehicle-route-sheet-1.typst` | 30 | **0** |
| `test_typst_determinism` + `test_typst_determinism_across_second_boundary` × 100 consecutive pytest runs | 500 | **0** |

Total ≈ 980 renders across separate processes, **0 divergence**. Every render is a fresh `typst compile` subprocess (no in-process warm cache), so the byte-determinism claim holds for cold renders too; no warm-up was introduced.

### P2.1.2 Test really executes the renderer (evidence)

- `strace -f -e trace=execve` on `test_typst_determinism`: exactly **3 `typst compile` execve calls** (+1 `--version` probe), each in a distinct fresh `qm-typst-*/` tempdir with `--creation-timestamp 1700000000` on the command line.
- Test collects as runnable (no skip decorator triggered; binary present), reads the PDF bytes from the actual output file after each compile, hashes the real bytes with `hashlib.sha256`, and never reads a fixture/cache.
- Wall time ≈ 0.10–0.21 s per pytest invocation is explained by 3 subprocess renders (~13–21 ms each) + pypdf page counting + pytest overhead.

### P2.1.2 Divergent-pair comparison (root-cause re-derivation)

Directly against the pinned binary (`TYPST_TIMESTAMP` env only, no CLI flag, 5 renders over ~3 s):

- env-only: **3 distinct SHA-256** — Typst 0.15.1 ignores `TYPST_TIMESTAMP` on Linux (confirms P2.1.1 root cause).
- `--creation-timestamp 1700000000` (CLI flag only): **1 SHA-256** across the same 5 renders.

Byte-diff of a divergent env-only pair (env-1 vs env-3):

| Aspect | Result |
|---|---|
| SHA-256 | differs |
| Size | identical (11 116 B) |
| `/ModDate` + `/CreationDate` | differ by 1 s |
| XMP `ModifyDate`/`CreateDate` | differ by 1 s |
| `DocumentID`/`InstanceID` | differ (derived from timestamp) |
| Trailer `/ID` | differs (derived from metadata) |
| Page count | identical (1) |
| MediaBox | identical |
| Object count / xref / font subsets | identical |
| Extracted text | identical |
| Raster (150 DPI) | SSIM = 1.0, changed-pixels = 0.0 |

So the divergence class is **metadata-only, wall-clock-driven**; semantic and visual output are identical. Note: `--creation-timestamp` also pins Typst's in-code `datetime.today()` (cli-flag PDF shows the pinned date 2023-11-14, not the wall-clock date) — the flag controls both PDF metadata and renderer-clock semantics.

### P2.1.2 Classification

**Case B (per the review taxonomy)**: the divergence has a concrete, reproducible cause — wall-clock `CreationDate`/`ModDate`/`/ID` metadata produced when `--creation-timestamp` is absent. With the flag (production path), output is **byte-deterministic in steady state AND in cold state** (every render is a fresh subprocess). No warm-up was added; none is needed. The existing `test_typst_determinism` + `test_typst_determinism_across_second_boundary` component tests assert the actually-guaranteed property (byte-identical SHA across consecutive renders and across wall-clock second boundaries). Case C (semantic/structural/visual divergence) is **not** present — SSIM = 1.0 and text/page count/geometry are identical across divergent metadata.

### P2.1.2 Fixes and hardening

1. `scripts/diag_typst_determinism.py` — the `--keep-artifacts` block was a `pass` stub; divergent PDFs were never persisted and `diagnostics.json` was not written for zero-divergence runs. Now: divergent series persist `baseline-*.pdf` + `divergent-r<N>-*.pdf` (hashes/sizes/order in filename) plus `started.txt`; `--keep-artifacts` persists the full corpus; `diagnostics.json` (incl. per-render SHA/size/wall_ms and cold/warm state note) is written on every run.
2. `tests/unit/test_typst_backend.py` — two new unit tests (`test_render_passes_creation_timestamp_flag`, `test_render_png_path_also_pins_creation_timestamp`) use an argv-recording mock binary to assert `--creation-timestamp 1700000000` is present on the compile command line for both the primary render and the page-count-via-PDF path. Negative control verified: removing the flag makes the test fail fast (no ~3% flake needed to catch the regression).

### P2.1.2 Scoring impact

None. The byte-determinism claim was confirmed (not weakened): `PDF quality / predictability` stays **Typst 5** / WeasyPrint 4, totals **Typst 462** vs WeasyPrint 376 (+86). **Typst remains the provisional preferred backend for Phase 5** (Windows V4 `NOT-VERIFIED` unchanged). The recommendation is independent of byte-determinism: semantic and visual determinism are confirmed for both backends, and Typst retains the performance/deployment advantage.

### P2.1.2 Regression

- `pytest -q` = **215 passed** (213 + 2 new unit tests), 0 failed.
- `ruff check .` / `ruff format --check .` / `mypy engine backends cli` — PASS (re-run).
- `qm-render version` / `qm-render capabilities` — contract unchanged.
- `python scripts/golden_update.py --check` — PASS (re-run).
- ≥ 10 full determinism regression runs: `test_typst_determinism` + `_across_second_boundary` — 100/100 pass in the Phase 2.1.2 campaign, plus a further ≥10 runs at close-out with 0 failures (no flaky assertions).

### P2.1.2 Out-of-scope (per task contract)

- NO production migration. NO renderer change (`backends/qm_backends/typst_backend.py` untouched by Phase 2.1.2).
- NO warm-up added to any test or render path.
- NO new ADR. NO Phase 5 work.

## Phase 2 Final Status (architect sign-off, 2026-08-11)

```text
Phase 2 Backend Spike: CLOSED
Phase 2.1 Decision Readiness Hardening: CLOSED
Phase 2.1.1 Typst determinism M1 close-out: CLOSED (re-verified Phase 2.1.2)

Preferred backend:
Typst — provisional primary candidate

Score:
Typst       462
WeasyPrint  376

Hard vetoes: none on either backend.
```

- **Level 9 human acceptance**: signed off by the architect together with the Phase 2 CLOSED decision; artefacts in `spike-out/acceptance/`, checklist in `doc/spike/HUMAN-ACCEPTANCE.md` — audit/re-review possible at any time.
- **Only remaining external gate** before confirming the primary backend: **Windows verification** of the pinned Typst 0.15.1 binary (binary, bundled fonts, CLI, representative renders). Deliberately scoped as a small verification task, not a development phase; blocked only by absence of a Windows environment (`spike/typst-pin.json` carries the honest `unverified-no-windows-env` marker).
- **Next step (architectural, not executor)**: backend decision ADR — Primary backend = Typst, legacy/baseline backend = WeasyPrint; migration policy: new active templates on Typst, existing active warehouse templates migrated one-by-one through the visual harness, WeasyPrint retained for historical templates/artifacts where reproducibility demands it. No "remove WeasyPrint" statement.
- **After the ADR**: Phase 6 — canonical production warehouse waybill on QDE, compared visually against the current warehouse waybill, without immediate removal of the old renderer.
