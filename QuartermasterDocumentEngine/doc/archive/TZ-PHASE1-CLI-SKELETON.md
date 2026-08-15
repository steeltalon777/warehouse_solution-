# TZ: Quartermaster Document Engine — Phase 1: CLI skeleton

**Status:** Completed — Phase 1 (CLI skeleton) accepted by QA (2026-08-10); archived. Все пункты чек-листа закрыты, кроме п.9 Windows smoke (пользовательский гейт при наличии runner). Реализация: commits b305eb3, 9008fee.
**Date:** 2026-08-10
**Основание:** `doc/ADR-0001-QUARTERMASTER-DOCUMENT-ENGINE.md`, ROADMAP v1 Phase 1, SPEC v2 §3, §7, §9, §21, §22
**Репозиторий:** `warehouse_solution/QuartermasterDocumentEngine` (nested standalone repo, ветка `dev`)

## Execution Strategy

- **Sequential.** Новый пустой репозиторий: пакетный каркас, схемы, registry, backend-интерфейс и CLI жёстко связаны между собой, общий объём мал.
- Один исполнитель. Параллельные шарды нецелесообразны (max useful threads: 1).
- Зависимостей от других репозиториев нет; Docker-стенд warehouse_solution не используется.
- Порядок внутри: каркас → ошибки → envelope → registry → backend → CLI → fixture/шаблон → smoke.

## Execution Checklist

- [x] 0. Context verified: SPEC v2 §3/§7/§9/§21/§22, ADR-0001, ROADMAP Phase 1 прочитаны
- [x] 1. Architecture boundaries confirmed: engine stateless, без сети/БД, без доменной логики
- [x] 2. Каркас проекта: `pyproject.toml`, пакеты `qm_engine`/`qm_backends`/`qm_cli`, console script `qm-render` устанавливается и работает offline
- [x] 3. Envelope JSON Schema + модель ошибок (unit tests)
- [x] 4. Template registry + manifest (unit tests)
- [x] 5. Backend interface + WeasyPrint baseline backend (component tests)
- [x] 6. CLI-команды `version`/`capabilities`/`validate`/`inspect-template`/`render`, режимы file→artifact, stdin→file, stdin→stdout (integration tests)
- [x] 7. Fixture `waybill-20.json` + dev-шаблон `warehouse-waybill-ru@0.1.0`
- [x] 8. Linux offline smoke: acceptance-команда ROADMAP пройдена
- [ ] 9. Windows smoke — при наличии runner (нет Windows runner у агентов; требует пользователя)
- [x] 10. Документация: README отражает команды и статус
- [x] 11. Final acceptance review: evidence table заполнена (QA-приёмка пройдена; пункт 9 Windows smoke остаётся пользовательским гейтом — runner у агентов отсутствует)

### Критерии приёмки по пунктам

| Пункт | Критерий |
|---|---|
| 2 | `pip install -e ".[dev]"` в чистом venv проходит; `qm-render version` печатает JSON и exit 0 |
| 3 | `pytest tests/unit` зелёный: валидный envelope принимается; каждый invalid-fixture класса 2 даёт свой код ошибки |
| 4 | `pytest tests/unit` зелёный: lookup находит `warehouse-waybill-ru@0.1.0`; отсутствующий id → `TEMPLATE_NOT_INSTALLED`, отсутствующая версия → `TEMPLATE_VERSION_NOT_INSTALLED`, чужой contract → `TEMPLATE_CONTRACT_MISMATCH`; fallback на latest отсутствует |
| 5 | `pytest tests/component` зелёный: backend рендерит валидный PDF (`%PDF`, ≥1 страница); при недоступном WeasyPrint `available()` → False и код `BACKEND_NOT_AVAILABLE` |
| 6 | `pytest tests/integration` зелёный: все 3 режима IO, exit codes и JSON-ошибки на stderr по таблице |
| 7 | fixture проходит `validate`; шаблон отображается в `capabilities` |
| 8 | acceptance-команда (ниже) даёт exit 0 и валидный PDF, без сети |
| 9 | та же команда на Windows; при отсутствии runner — unchecked + blocker note |
| 10 | README: команды, режимы, статус Phase 1 |

## Check Rules

- Architect создал чек-лист и критерии (этот файл).
- Executor отмечает пункты 2–10 только после запуска соответствующей верификации.
- QA/верификатор отмечает пункт 11 только после проверки evidence.
- Пропущенная проверка остаётся unchecked с причиной в отчёте.
- Коммиты только в ветку `dev`; stage только целевых файлов явным pathspec; push запрещён агентам.

## In scope (файлы)

```text
QuartermasterDocumentEngine/
├── pyproject.toml                     # один дистрибутив quartermaster-document-engine
├── engine/qm_engine/                  # envelope, errors, registry, render orchestration
│   ├── envelope.py                    # парсинг/валидация envelope
│   ├── errors.py                      # коды ошибок, exit codes, JSON на stderr
│   ├── registry.py                    # lookup template package, compatibility checks
│   └── render.py                      # оркестрация: envelope → registry → backend
├── backends/qm_backends/
│   ├── base.py                        # Backend protocol + RenderResult
│   └── weasyprint_backend.py          # baseline backend (HTML→PDF)
├── cli/qm_cli/
│   └── main.py                        # qm-render entrypoint
├── contracts/
│   ├── envelope/v1/envelope.schema.json
│   └── warehouse.operation-document/v2/schema.json   # phase1-minimal subset
├── templates/warehouse-waybill-ru/0.1.0/
│   ├── manifest.yaml
│   └── main.html                      # entrypoint (Jinja2) для WeasyPrint
├── fonts/README.md                    # аудит шрифтов — Phase 2; пока placeholder
└── tests/
    ├── fixtures/waybill-20.json
    ├── fixtures/invalid/*.json        # сломанные payload для негативных тестов
    ├── unit/
    ├── component/
    └── integration/
```

## Out of scope

- Typst и любые backend'ы кроме WeasyPrint baseline.
- Visual migration harness (Phase 3), performance benchmark (Phase 4).
- Production-шаблоны и canonical waybill (Phase 6): шаблон 0.1.0 — минимальный dev-шаблон.
- Django/SyncServer интеграция, RenderedDocumentArtifact.
- Вывод PNG/SVG/HTML (Phase 1: только `--format pdf`).
- Bundled fonts enforcement (коды ошибок существуют, принуждение — с Phase 2).
- Адаптеры старых payload, автоконвертер шаблонов.

## Решение: host language Phase 1 — Python 3.11+

Обоснование: baseline backend WeasyPrint — Python-стек; Typst доступен из Python (CLI/bindings) для Phase 2; публичный CLI contract language-agnostic (ADR-0001 D11/D13), поэтому будущая смена runtime не ломает потребителей. Отклонение от этого решения исполнитель фиксирует в отчёте.

## Расширение scope (утверждено исполнителем)

По запросу пользователя реализован полный рендер боевых envelope операций с прода:

- `doc/test_templates/*.json` — боевые payload'ы (MOVE/RECEIVE/WRITE_OFF/ADJUSTMENT) по которым проверяется рендер.
- Envelope schema `template_version` принимает `X.Y` и `X.Y.Z` (боевые используют `"1.0"`).
- `contracts/warehouse.operation-document/v2/schema.json` расширена под боевую структуру `document` (operation, sender, receiver, lines с `item_*`/`quantity`/`unit_*`, signatures, localization, basis); `header` стал опциональным (dev-fixture).
- Добавлен dev-шаблон `warehouse-waybill-ru@1.0` (`templates/warehouse-waybill-ru/1.0/`), рендерящий боевую структуру; `warehouse-waybill-ru@0.1.0` сохранён для dev-fixture.
- 2 файла старого формата (`template_waybill_MOVE_5l.json`, `template_act_ADJUSTMENT_1l.json`) распакованы вручную в прямой envelope (`*.envelope.json`); движок ожидает envelope.

## Phase 1.1 — CLI contract hardening (fixes по ревью)

По итогам ревью (#1) устранены три замечания:

1. **Единый `--templates-dir` во всех командах.** `validate`, `inspect-template`, `capabilities`, `render` теперь резолвят корень шаблонов через один `_resolve_templates_dir(ctx)` (CLI-флаг > env `QM_TEMPLATES_DIR` > bundle default). Ранее `validate` и `inspect-template` игнорировали глобальный флаг. Добавлены regression-тесты: пустая кастомная директория → `validate`/`render`/`inspect-template` = exit 3 `TEMPLATE_NOT_INSTALLED`, `capabilities` = `[]`.
2. **`version` возвращён к публичному TZ-контракту:** `{"engine": "0.1.0", "engine_contract_versions": ["1.0.0"]}` — поле `engine_contract_versions` — массив (engine может понимать несколько контрактов одновременно). Введён `paths.ENGINE_CONTRACT_VERSIONS`.
3. **`inspect-template` `backend_available` исправлен:** теперь выводится `backend` (имя) и `backend_available` (bool через реальную проверку `get_backend(...).available()`).

Regression-тесты добавлены в `tests/integration/test_cli.py`; итог: 65 тестов (23 unit + 8 component + 34 integration).

### Окружение исполнителя

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
```

Зависимости (пиннить точно): runtime — `weasyprint==66.*` (baseline по ROADMAP), `jsonschema`, `Jinja2`, `PyYAML`; dev — `pytest`, `ruff`, `mypy`, `pypdf` (проверка PDF в тестах).

**Предпроверка WeasyPrint:** перед пунктом 5 выполнить `python -c "import weasyprint"` — нужны системные библиотеки pango/cairo. В warehouse_solution их уже использует Django-контур; если импорт падает — зафиксировать blocker и согласовать установку системных пакетов с пользователем, не ставить молча.

## CLI contract

| Команда | Назначение |
|---|---|
| `qm-render version` | версия engine + поддерживаемые `engine_contract_version` (JSON) |
| `qm-render capabilities` | backends, output formats, установленные шаблоны (JSON) |
| `qm-render validate --input F` / `--stdin` | валидация envelope + contract + наличие шаблона |
| `qm-render inspect-template --template ID --version V` | manifest + статус compatibility |
| `qm-render render --input F --output O` | file → artifact |
| `qm-render render --input F --stdout --format pdf` | file → stdout |
| `qm-render render --stdin --stdout --format pdf` | stdin → stdout |

Флаги: `--templates-dir` (override корня шаблонов; дефолт `<bundle>/templates`, env `QM_TEMPLATES_DIR`). Phase 1: `--format` принимает только `pdf`; `render_profile` поддерживается только `print`; `locale` — `ru-RU`.

Форматы JSON-вывода:

```jsonc
// qm-render version
{"engine": "0.1.0", "engine_contract_versions": ["1.0.0"]}
// qm-render capabilities
{"backends": [{"name": "weasyprint", "available": true}],
 "output_formats": ["pdf"],
 "templates": [{"id": "warehouse-waybill-ru", "version": "0.1.0",
                 "document_contract": "warehouse.operation-document/v2"}]}
```

### Exit codes

| Code | Класс | Коды ошибок |
|---:|---|---|
| 0 | успех | — |
| 2 | валидация payload/контракта | `INVALID_PAYLOAD`, `UNSUPPORTED_ENGINE_CONTRACT`, `UNSUPPORTED_DOCUMENT_CONTRACT`, `UNSUPPORTED_OUTPUT_FORMAT` |
| 3 | ошибки шаблона | `TEMPLATE_NOT_INSTALLED`, `TEMPLATE_VERSION_NOT_INSTALLED`, `TEMPLATE_CONTRACT_MISMATCH` |
| 4 | ресурсы/backend | `BACKEND_NOT_AVAILABLE`, `FONT_NOT_AVAILABLE`, `ASSET_NOT_AVAILABLE` |
| 5 | рендер/internal | `RENDER_FAILED` |

Формат ошибки (stderr, JSON, одна строка): `{"error": {"code": "...", "message": "...", "details": {...}}}`. На stdout при `--stdout` пишутся только байты артефакта (бинарный режим, UTF-8 text туда не примешивать).

## Envelope schema (`contracts/envelope/v1/envelope.schema.json`)

JSON Schema draft 2020-12. Required: `engine_contract_version`, `document_contract`, `document_type`, `template_id`, `template_version`, `locale`, `render_profile`, `document`. Optional: `document_id`, `document_number`, `assets`. Semver-формат версий. Engine Phase 1 принимает `engine_contract_version == "1.0.0"`, иначе `UNSUPPORTED_ENGINE_CONTRACT`.

Document contract Phase 1: минимальный schema `warehouse.operation-document/v2` под fixture (заголовок документа + массив строк); помечен `phase1-minimal`, полный canonical contract — Phase 6.

## Template package и registry

`templates/<id>/<version>/manifest.yaml` задаёт: `id`, `version`, `document_contract`, `backend`, `entrypoint`, `output_formats`, `locales`, page settings, `capabilities`, `fonts`, `assets`. Пример dev-шаблона:

```yaml
id: warehouse-waybill-ru
version: 0.1.0
document_contract: warehouse.operation-document/v2
backend: weasyprint
entrypoint: main.html
output_formats: [pdf]
locales: [ru-RU]
page: {size: A4, orientation: portrait}
capabilities: {}
fonts: []
assets: []
```

Registry выполняет: lookup по `template_id`+`template_version`; проверки `TEMPLATE_NOT_INSTALLED` / `TEMPLATE_VERSION_NOT_INSTALLED` / `TEMPLATE_CONTRACT_MISMATCH`; возврат package path + manifest. Подмена версии на latest запрещена (ADR-0001 D6).

## Backend interface

```python
class Backend(Protocol):
    name: str

    def available(self) -> bool: ...
    def render(
        self, normalized_document, template_package, output_format, render_options
    ) -> RenderResult: ...
```

`RenderResult`: байты артефакта + metadata (page_count если известен, warnings). `WeasyPrintBackend`: Jinja2-рендер entrypoint шаблона payload'ом → WeasyPrint HTML→PDF, полностью offline, без сетевых assets. Все текстовые ресурсы — UTF-8.

## Fixture

`tests/fixtures/waybill-20.json`: валидный envelope `warehouse.operation-document/v2`, `template_id=warehouse-waybill-ru`, `template_version=0.1.0`, 20 строк с кириллицей и длинными наименованиями. Скелет:

```jsonc
{"engine_contract_version": "1.0.0",
 "document_contract": "warehouse.operation-document/v2",
 "document_type": "waybill",
 "template_id": "warehouse-waybill-ru",
 "template_version": "0.1.0",
 "locale": "ru-RU",
 "render_profile": "print",
 "document_id": "doc-test-0001",
 "document_number": "НК-000001",
 "document": {"header": {"organization": "…", "document_date": "2026-08-10", "…": "…"},
               "lines": [ {"position": 1, "name": "…", "quantity": "10.000", "unit": "шт", "…": "…"} ]}}
```

`tests/fixtures/invalid/`: минимум по одному fixture на каждый код ошибки класса 2 (сломанный JSON, неверный `engine_contract_version`, неизвестный `document_contract`, неверный формат версии и т.п.).

## Test ladder

| # | Уровень | Применимо | Что проверяется | Команда |
|---|---|---|---|---|
| 1 | Static | да | lint/types | `ruff check .` + `mypy engine backends cli` |
| 2 | Unit | да | envelope, errors, registry | `pytest tests/unit` |
| 3 | Component | да | WeasyPrint backend → валидный PDF (`%PDF` header, ≥1 страница) | `pytest tests/component` |
| 4 | DB integration | N/A | engine не имеет БД | — |
| 5 | CLI integration | да | subprocess: 3 режима IO, exit codes, JSON на stderr | `pytest tests/integration` |
| 6 | Linux offline smoke | да | acceptance-команда ниже, без сети | shell |
| 7 | UI automation | N/A | CLI без UI | — |
| 8 | Windows smoke | условно | тот же smoke на Windows; blocker при отсутствии runner | — |
| 9 | Regression | N/A | новый репозиторий | — |
| 10 | Acceptance | да | evidence table | — |

Проверка offline: smoke прогоняется в изоляции сети, если доступно (`unshare -n` или аналог); иначе — code review на отсутствие сетевых вызовов + пометка в evidence.

## Acceptance criteria (exit из Phase 1)

```bash
cat tests/fixtures/waybill-20.json | qm-render render --stdin --stdout --format pdf > /tmp/waybill.pdf
```

- exit code 0; `/tmp/waybill.pdf` начинается с `%PDF`, размер > 0, ≥ 1 страница;
- `qm-render validate --input tests/fixtures/waybill-20.json` → exit 0;
- каждый invalid-fixture даёт корректный код ошибки и exit code из таблицы;
- `qm-render capabilities` показывает backend `weasyprint` и шаблон `warehouse-waybill-ru@0.1.0`;
- весь рендер offline: сетевые вызовы в коде отсутствуют (проверяется review + запуском без сети).

## Stand

Docker-стенд не требуется: offline CLI на dev-машине Linux. Переменные окружения: только `QM_TEMPLATES_DIR` (опционально). Health checks: неприменимы.

## Evidence table (заполняет исполнитель)

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|
| Static | `ruff check . && mypy engine backends cli` | pass | ruff: All checks passed; mypy: Success (11 source files) |
| Unit | `pytest tests/unit` | pass | 23 passed |
| Component | `pytest tests/component` | pass | 8 passed (WeasyPrint → `%PDF-1.7`, page_count=1, кириллица в text layer) |
| CLI integration | `pytest tests/integration` | pass | 34 passed (3 режима IO, exit codes 0/1/2/3, JSON на stderr, 6 боевых envelope, 4 regression `--templates-dir`) |
| Linux smoke | acceptance-команда | pass | `/tmp/waybill.pdf` — `%PDF-1.7`, 22007 байта, 1 страница |
| Prod smoke | боевые envelope через шаблон 1.0 | pass | 6/6 `doc/test_templates/*.json` → валидный PDF с кириллицей |
| Phase 1.1 fixes | `--templates-dir` 4 команды, `version`, `inspect-template` | pass | эмпирически + regression-тесты (см. «Phase 1.1») |
| Windows smoke | acceptance-команда на Windows | skipped | нет Windows runner у агентов (ADR-0001 §5); требуется пользователь |
