# Quartermaster Document Engine — Roadmap v1

**Status:** Initial roadmap  
**Date:** 2026-08-10

## Цель

Создать независимый универсальный CLI-движок документов, принимающий самодостаточный versioned JSON и возвращающий печатный artifact.

## Phase 0 — Bootstrap и ADR

Создать standalone repo:

```text
QuartermasterDocumentEngine/
├── doc/
├── contracts/
├── templates/
├── fonts/
├── engine/
├── backends/
├── cli/
└── tests/
```

В `doc/`:

```text
SPEC-QUARTERMASTER_DOCUMENT_ENGINE.md
ROADMAP-QUARTERMASTER_DOCUMENT_ENGINE.md
ADR-0XXX-QUARTERMASTER-DOCUMENT-ENGINE.md
```

ADR фиксирует границы producer/consumer, universal CLI, offline mode, versioned contracts/templates, backend abstraction, artifact boundary и триггеры будущего service extraction.

**Exit:** архитектура согласована, технологический победитель ещё не назначен.

## Phase 1 — CLI skeleton

Реализовать:

```bash
qm-render version
qm-render capabilities
qm-render validate
qm-render inspect-template
qm-render render
```

Режимы:

```text
file → artifact
stdin → file
stdin → stdout
```

Acceptance:

```bash
cat tests/fixtures/waybill-20.json   | qm-render render --stdin --stdout --format pdf   > /tmp/waybill.pdf
```

Создать envelope JSON Schema, registry, backend interface и machine-readable errors.

**Exit:** тестовый документ рендерится из терминала offline на Linux и Windows.

## Phase 2 — Backend spike

Сравнить минимум:

1. WeasyPrint 66 baseline.
2. Typst.

Chromium/Paged Media добавлять только при доказанной необходимости.

Использовать одни и те же fixtures.

### Waybill

```text
1 / 20 / 75 / 200 / 500 строк
```

### Vehicle route sheet

```text
1 vehicle
1 driver
50 route records
10 refueling records
odometer
fuel balances
signatures
```

### Fuel report

```text
100 / 500 / 1500 строк
>=10 vehicles/equipment
20–50 page worst case
```

Дополнительно проверить QR, barcode, images, signature/stamp images, watermark, copies, portrait/landscape.

## Phase 3 — Visual migration harness

Для одного payload запускать old и candidate renderer.

Сравнивать:

- page count;
- dimensions;
- extracted text;
- critical values;
- rasterized pages;
- SSIM;
- diff regions.

Автоконвертер шаблонов не делать.

**Exit:** reviewer видит точный diff старой и новой формы.

## Phase 4 — Performance/deployment

Среды:

```text
Linux container
Windows 11
offline
Cyrillic paths
4 vCPU / 8 GB reference server
```

Нагрузки:

```text
1 cold
10 sequential
10 parallel
50 pool=4
20-row waybill
500-row waybill
1500-row fuel report
```

Измерять startup, p50/p95, CPU, RAM, output/distribution size и dependencies.

## Phase 5 — Backend decision

Weighted matrix:

| Criterion | Weight |
|---|---:|
| PDF quality/predictability | 20 |
| Pagination/tables | 15 |
| Fixed forms/geometry | 15 |
| Template development | 10 |
| Windows deployment | 10 |
| Linux/container deployment | 8 |
| Offline suitability | 7 |
| Cyrillic/fonts | 5 |
| Preview formats | 4 |
| Performance | 3 |
| Distribution size | 2 |
| Maintainability | 1 |

### Typst wins

- becomes primary;
- new forms use it;
- active legacy forms migrate;
- WeasyPrint remains only where needed for history.

### Typst has gaps

- mixed backend remains;
- manifests explicitly choose backend;
- limitations documented.

### Neither works

- open new backend investigation using spike evidence.

**Exit:** decision recorded in ADR — **выполнено: ADR-0030 (2026-08-15)**. Primary = Typst 0.15.1 (Linux x64 pinned), WeasyPrint = legacy/emergency fallback, backend выбирается по `manifest.backend`. См. `docs/adr/0030-qde-primary-rendering-backend-typst.md`.

## Phase 6 — Canonical waybill

Создать canonical template package.

Перенести текущие pagination/signature rules.

Django становится первым server-side host:

```text
Django
  RenderedDocumentArtifact
  cache
  audit
  retry/storage

Engine
  stateless
```

**Exit:** production-compatible waybill создаётся через новый engine.

## Phase 7 — Existing warehouse forms

Консолидировать:

```text
waybill
acceptance_certificate
act
invoice
```

Удалять старые pipeline только после regression/acceptance.

Если Typst победил, активные формы переводятся на него, WeasyPrint становится legacy-only.

## Phase 8 — WPF offline integration

Поставка Windows engine рядом с WPF.

```text
WPF → complete JSON → qm-render.exe → PDF
```

FFI не использовать изначально.

Рассматривать embedded/Rust FFI только если subprocess реально измеренно мешает.

**Exit:** WPF рендерит offline без Django/SyncServer.

## Phase 9 — Route sheets

Добавить:

```text
transport.vehicle-route-sheet/v1
transport.equipment-route-sheet/v1
```

Production templates для автомобиля/техники, водителя, маршрутов, одометра, ГСМ, заправок и подписей.

## Phase 10 — Reports

Добавить семейства:

```text
fuel.monthly-report/v1
inventory.balance-report/v1
warehouse.operation-register/v1
```

Проверить большие таблицы, landscape, grouping, subtotals, totals и charts.

## Phase 11 — Artifact architecture review

Не создавать новый service заранее.

Пересмотреть архитектуру только при:

- multiple server-side consumers;
- scheduled batch;
- >100 docs/batch workflow;
- shared queue;
- object storage;
- centralized retries;
- render without Django;
- web latency degradation;
- Django worker starvation.

Возможный будущий результат:

```text
Artifact Service
      ↓
worker pool
      ↓
Quartermaster Document Engine
```

Это отдельный ADR.

## Phase 12 — Runtime evolution

Python host можно оставить навсегда, если он проходит deployment/performance.

Rust host рассматривать только при измеримой пользе:

- Windows packaging;
- startup bottleneck;
- embedded Typst;
- one-binary deployment.

Публичный CLI contract, schemas, manifests и templates при этом не меняются.

## Continuous requirements

Каждый production template имеет:

- versioned manifest;
- contract;
- pinned fonts/assets;
- fixture;
- semantic checks;
- page/layout checks;
- golden visual;
- Windows smoke;
- Linux smoke.

Каждое намеренное visual change:

1. bump template version;
2. visual diff;
3. semantic checks;
4. reviewer approval;
5. intentional golden update.

Published template versions immutable.

## Target

```text
SyncServer --------\
Django ------------ \
WPF ---------------- > self-contained JSON → qm-render → PDF
Android ------------ /
Scripts ----------- /
Human terminal ----/
```

Главный критерий универсальности:

> Валидный payload + совместимый engine bundle должны быть достаточны для рендера документа без сети, БД и любых Quartermaster-сервисов.
