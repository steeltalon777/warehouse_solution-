# Quartermaster Document Engine

Независимый универсальный offline-рендерер документов:

```text
self-contained versioned JSON → qm-render (CLI) → PDF / preview artifact
```

Рендер не требует сети, БД, Django, SyncServer или WPF: валидный payload + совместимый bundle engine достаточны.

## Документы

- `doc/SPEC-QUARTERMASTER_DOCUMENT_ENGINE-v2.md` — спецификация (architecture baseline).
- `doc/ROADMAP-QUARTERMASTER_DOCUMENT_ENGINE-v1.md` — roadmap Phase 0–12.
- `doc/ADR-0001-QUARTERMASTER-DOCUMENT-ENGINE.md` — базовые архитектурные решения.
- `doc/TZ-PHASE1-CLI-SKELETON.md` — исполнимое TZ на Phase 1 (CLI skeleton).
- `doc/TZ-PHASE2-BACKEND-SPIKE.md` — исполнимое TZ на Phase 2 (backend spike: WeasyPrint 66 vs Typst).

## Структура

```text
doc/        контракты и решения (SPEC, ROADMAP, ADR, TZ)
contracts/  JSON Schema envelope и семейств документов
templates/  versioned immutable template packages
fonts/      bundled pinned шрифты (Cyrillic mandatory) — Phase 2 placeholder
engine/     ядро: envelope, registry, errors, оркестрация
backends/   backend abstraction (WeasyPrint baseline, далее spike Typst)
cli/        qm-render
tests/      fixtures, unit, component, integration
```

## Статус

Phase 0 (bootstrap и ADR) завершён. **Phase 1 (CLI skeleton) реализована**:
`qm-render` работает offline на Linux, установлен и проходит acceptance-команду.

**Phase 2 (Backend spike) завершена** — WeasyPrint и Typst 0.15.1 оба рабочие offline, 5 spike-шаблонов
(waybill-typst, route-sheet-{weasy,typst}, fuel-report-{weasy,typst}) рендерят валидные PDF, copies/watermark
поддерживаются. **Рекомендация T12: Typst** (weighted 462 vs WeasyPrint 396, без veto). См. `doc/spike/PHASE2-BACKEND-COMPARISON.md`.
Производственный выбор (ADR-0030, Typst primary, WeasyPrint legacy) — принят, см. `docs/adr/0030-qde-primary-rendering-backend-typst.md`.

## Установка (dev)

Требуется Python 3.11+.

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Команды

```bash
qm-render version
qm-render capabilities
qm-render validate --input payload.json
qm-render validate --stdin
qm-render inspect-template --template warehouse-waybill-ru --version 0.1.0
qm-render render --input payload.json --output result.pdf
cat payload.json | qm-render render --stdin --stdout --format pdf > result.pdf
```

`qm-render version` возвращает `{"engine": "0.1.0", "engine_contract_versions": ["1.0.0"]}` —
`engine_contract_versions` всегда массив (движок может понимать несколько контрактов одновременно).

Flags: `--templates-dir` (override корня шаблонов; дефолт `<bundle>/templates`,
env `QM_TEMPLATES_DIR`). Флаг работает единообразно во всех командах
(`validate`, `capabilities`, `inspect-template`, `render`).
Phase 1: `--format` принимает только `pdf`;
`render_profile` — только `print`; `locale` — `ru-RU`.

Phase 2 (дополнительно): `--format {pdf,png}` (png — Typst only);
`--copies N` (≥1, default 1, конкатенация PDF);
`--watermark/--no-watermark` (default off, шаблон-level «ОБРАЗЕЦ» на spike-waybill-typst и spike-route-sheet-weasy).
Backend'ы и форматы доступны через `qm-render capabilities`:
`backends[i].output_formats` (per-backend) + top-level `output_formats` (union для обратной совместимости).

### Шаблоны

- `warehouse-waybill-ru@0.1.0` — dev-шаблон под простой fixture (`tests/fixtures/waybill-20.json`, структура `header` + `lines`).
- `warehouse-waybill-ru@1.0` — шаблон под боевые envelope операций с прода (`doc/test_templates/*.json`): структура `document` с `operation`, `sender`/`receiver`, `lines` (`item_*`/`quantity`/`unit_*`), `signatures`, `localization`.

`template_version` принимает `X.Y` и `X.Y.Z` (боевые payload'ы используют `"1.0"`).

### Exit codes

| Code | Класс |
|---:|---|
| 0 | успех |
| 2 | валидация payload/контракта |
| 3 | ошибки шаблона |
| 4 | ресурсы/backend |
| 5 | рендер/internal |

Ошибки выводятся в stderr в JSON: `{"error": {"code": ..., "message": ..., "details": {...}}}`.

### Acceptance (Phase 1)

```bash
cat tests/fixtures/waybill-20.json | qm-render render --stdin --stdout --format pdf > /tmp/waybill.pdf
```

### Acceptance (Phase 2 spike)

```bash
# baseline (Phase 1 контракт)
cat tests/fixtures/waybill/waybill-20.weasy.json | qm-render --templates-dir templates render --stdin --stdout --format pdf > /tmp/wb20-weasy.pdf

# Typst-вариант накладной
qm-render --templates-dir templates render --input tests/fixtures/waybill/waybill-20.typst.json --output /tmp/wb20-typst.pdf

# копии (аддитивный флаг; без него вывод идентичен Phase 1)
qm-render --templates-dir templates render --input tests/fixtures/waybill/waybill-20.weasy.json --output /tmp/wb20-x2.pdf --copies 2

# водяной знак (template-level, opt-in)
qm-render --templates-dir templates render --input tests/fixtures/route-sheet/vehicle-route-sheet-1.weasy.json --output /tmp/rs-wm.pdf --watermark
```

## Проверки

```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/mypy engine backends cli
.venv/bin/pytest
.venv/bin/pytest -m golden     # Phase 2 golden regression (JSON-only, LFS-fallback)
.venv/bin/pytest -m spike      # Phase 2 spike-only tests (требуется [spike] extra + typst binary)
.venv/bin/python -m tests.harness.compare --fixture waybill-20 \
  --templates warehouse-waybill-ru@1.0,spike-waybill-typst@0.1.0 \
  --out spike-out/compare/waybill-20/   # визуальный harness
.venv/bin/python scripts/bench.py        # performance benchmark
.venv/bin/python scripts/golden_update.py --check  # golden update gate
```

## Потребители (целевое)

```text
SyncServer --------\
Django ------------ \
WPF ---------------- > self-contained JSON → qm-render → PDF
Android ------------ /
Scripts ----------- /
Human terminal ----/
```
