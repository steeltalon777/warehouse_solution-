# Quartermaster Document Engine — Specification v2

**Status:** Draft / architecture baseline  
**Component:** QuartermasterDocumentEngine  
**Repository model:** standalone repository  
**Primary integration:** universal CLI  
**Date:** 2026-08-10

## 1. Назначение

Quartermaster Document Engine — автономный модуль рендеринга документов.

Он принимает самодостаточный версионированный JSON и создаёт печатный артефакт независимо от Django, SyncServer, БД, UI и сети.

Базовый контракт:

```text
self-contained versioned JSON
            ↓
universal CLI
            ↓
PDF / preview artifact
```

Допустимые потребители:

- SyncServer;
- Django / Warehouse_web;
- WPF;
- Android;
- CI;
- batch jobs;
- shell/PowerShell scripts;
- человек напрямую из терминала.

## 2. Главный архитектурный принцип

SyncServer остаётся владельцем доменной логики и producer'ом document payload.

Renderer является stateless consumer.

```text
Domain entities / revisions
          ↓
SyncServer Payload Builder
          ↓
Immutable Document Payload
          ↓
Quartermaster Document Engine
          ↓
PDF / PNG / SVG / HTML*
```

`HTML*` зависит от backend и не является обязательным каноническим форматом.

### SyncServer отвечает за

- бизнес-правила;
- lifecycle документа;
- snapshots;
- `document_type`;
- `document_contract`;
- `template_id`;
- `template_version`;
- построение immutable payload;
- сохранение payload и его hash.

### Renderer отвечает за

- валидацию схемы;
- registry шаблонов;
- compatibility checks;
- локализацию;
- пагинацию;
- физическую геометрию страниц;
- таблицы;
- типографику;
- шрифты/assets;
- layout подписей;
- QR/barcode как возможности представления;
- выбор backend;
- формирование artifact.

### Renderer не отвечает за

- Operation / OperationLine / revisions;
- остатки;
- пользователей и роли;
- авторизацию;
- ORM;
- PostgreSQL;
- HTTP к SyncServer;
- бизнес-аудит;
- persistent cache;
- retention policy.

## 3. Универсальный CLI

CLI — основной integration contract.

Renderer обязан работать без Quartermaster-сервисов.

```bash
qm-render validate --input payload.json

qm-render render   --input payload.json   --output waybill.pdf

cat payload.json | qm-render render   --stdin   --stdout   --format pdf > waybill.pdf
```

Сценарий «человек в терминале → JSON → PDF» является обязательным.

Renderer не принимает `document_id` как ключ для сетевого lookup.

`document_id` может находиться внутри payload только как metadata.

## 4. Репозиторий

Отдельный репозиторий:

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

Компонент не является частью SyncServer, Warehouse_web, Warehouse_core или WPF.

Git submodule не является основным способом распространения.

## 5. Поставка

Целевая единица поставки:

```text
quartermaster-document-engine-X.Y.Z-linux-x64.tar.gz
quartermaster-document-engine-X.Y.Z-windows-x64.zip
```

Bundle может включать:

```text
engine executable/runtime
contracts/
templates/
fonts/
manifests/
checksums.json
```

Клиенты не должны зависеть от языка реализации.

## 6. Версионирование

Раздельно версионируются:

- `engine_version`;
- `backend_version`;
- `document_contract`;
- `template_version`;
- release/distribution bundle.

Опубликованный template package immutable.

Любое намеренное изменение внешнего вида требует нового `template_version`.

## 7. Document envelope

```json
{
  "engine_contract_version": "1.0.0",
  "document_contract": "warehouse.operation-document/v2",
  "document_type": "waybill",
  "template_id": "warehouse-waybill-ru",
  "template_version": "2.0.0",
  "locale": "ru-RU",
  "render_profile": "print",
  "document_id": "optional-uuid",
  "document_number": "210726/1430/1",
  "document": {},
  "assets": {}
}
```

Правила:

1. Payload содержит все бизнес-данные для рендера.
2. Renderer не дополняет их из сети/БД.
3. `template_id`/`template_version` выбирает producer и хранит как opaque identifiers.
4. Render-host проверяет наличие package.
5. Отсутствующая версия шаблона = ошибка.
6. Подмена на latest запрещена.
7. Базовый offline render не использует сетевые assets.
8. Даты и числа имеют однозначный machine format.

## 8. Семейства контрактов

Один гигантский payload запрещён.

Примеры:

```text
warehouse.operation-document/v2
transport.vehicle-route-sheet/v1
transport.equipment-route-sheet/v1
fuel.monthly-report/v1
inventory.balance-report/v1
```

Общие reusable blocks допустимы для организации, площадки, человека, автомобиля, техники, подписей, количеств, денег, единиц, периодов и QR/barcode data.

## 9. Template package

Каждый шаблон — отдельный versioned package.

```text
templates/warehouse-waybill-ru/2.0.0/
├── manifest.yaml
├── main.typ
├── partials/
└── assets/
```

Manifest задаёт:

- template id/version;
- document contract;
- backend;
- entrypoint;
- output formats;
- locales;
- page settings;
- capabilities;
- required fonts/assets.

Registry выполняет lookup, compatibility validation, backend selection и resource checks.

## 10. Backend abstraction

Логический интерфейс:

```text
render(
    normalized_document,
    template_package,
    output_format,
    render_options
) -> RenderResult
```

Кандидаты spike:

1. WeasyPrint 66 — текущий baseline.
2. Typst — основной новый кандидат.
3. Chromium/Paged Media — только если результаты spike оправдают дополнительную сложность.

Typst не объявляется победителем заранее.

Direct PDF APIs не являются предпочтительным общим backend без доказанной необходимости.

## 11. Migration harness

Автоматический Jinja/Django-template → Typst converter вне scope.

Для одного fixture:

```text
payload
 ├── current renderer → old pages
 └── candidate renderer → new pages
```

Сравниваются:

- page count;
- размеры;
- semantic text;
- critical values;
- rasterized pages;
- SSIM;
- diff regions.

Перенос шаблонов выполняется вручную.

## 12. Lifecycle backend

WeasyPrint — baseline/migration backend, а не гарантированно постоянный второй backend.

Если Typst достигает функционального, deployment и performance parity:

- активные формы мигрируют;
- новые формы используют выбранный основной backend;
- WeasyPrint остаётся только там, где нужен для исторической воспроизводимости.

Если parity нет, mixed-backend architecture допускается.

## 13. Artifact boundary

Core не хранит persistent artifacts.

На Phase 1–3:

```text
SyncServer
  immutable payload

Django BFF
  temporary server-side render-host
  RenderedDocumentArtifact
  cache/audit/retry/storage

Quartermaster Document Engine
  stateless renderer
```

Отдельный artifact service не создаётся без реальной необходимости.

Триггеры пересмотра:

- второй server-side consumer;
- scheduled/night batch;
- >100 документов в batch workflow;
- общая очередь;
- object storage;
- централизованные retries;
- необходимость server-side render без Django;
- заметная деградация web latency;
- starvation Django workers.

## 14. Историческая воспроизводимость

- уже сохранённый PDF предпочтительнее re-render;
- template update не меняет старый artifact;
- metadata artifact содержит payload hash, contract, template id/version, engine/backend versions и PDF SHA-256;
- published template packages immutable;
- отсутствие старого template package = archive/deployment error;
- silent fallback на latest запрещён;
- старые payload поддерживаются explicit adapters, если это практично;
- архив должен сохранять templates, manifests, fonts и checksums.

## 15. Шрифты и assets

Renderer не зависит от случайных системных шрифтов.

До spike обследуются реальные fonts текущих Django и SyncServer templates.

Цель:

- fonts bundled;
- версии pinned;
- Cyrillic mandatory;
- fallback explicit;
- missing font = render error;
- Windows/Linux используют одинаковые версии ресурсов.

## 16. Spike: 3 класса документов

### MOVE waybill

Fixtures:

```text
1 / 20 / 75 / 200 / 500 строк
```

Проверяются длинные кириллические названия, переносы, многостраничность, повтор header, footer/signatures и финальные signature blocks.

### Vehicle route sheet

Fixture:

```text
1 vehicle
1 driver
50 route records
10 refueling records
odometer
fuel balances
dates/times
signature fields
partially blank handwritten fields
```

### Monthly fuel report

Fixtures:

```text
100 / 500 / 1500 строк
```

Проверяются grouping, subtotals, totals, decimals, landscape и worst-case 20–50 страниц.

## 17. Общие возможности spike

- QR;
- barcode;
- embedded image;
- signature image;
- seal/stamp image;
- watermark;
- several copies;
- copy labels;
- portrait/landscape;
- Cyrillic;
- long multi-page tables.

Регуляторные интеграции вне scope.

## 18. Performance

Benchmark:

- cold render;
- 10 sequential;
- 10 parallel;
- 50 через pool=4;
- 20-row waybill;
- 500-row waybill;
- 1500-row fuel report.

Измеряются cold/warm, p50/p95, CPU, peak RAM, output size, startup overhead.

Предварительные пределы на 4 vCPU / 8 GB:

| Scenario | Target | Hard limit |
|---|---:|---:|
| Cold 20-row CLI | <=1.5s | 2.5s |
| Warm 20-row | <=0.7s | 1.2s |
| 500-row waybill | <=4s | 7s |
| 1500-row report | <=8s | 15s |
| 50 docs pool=4 | <=30s | 60s |
| Peak worker RAM | <=400MB | 700MB |

Пороги калибруются относительно текущего WeasyPrint.

## 19. Test ladder

1. Static.
2. Unit.
3. Backend component.
4. SyncServer contract.
5. CLI integration.
6. Windows/Linux smoke.
7. Django host integration.
8. Performance/concurrency.
9. Visual regression/acceptance.

## 20. Golden policy

В обычном Git:

- JSON fixtures;
- metadata expectations;
- text expectations;
- page/layout assertions.

В Git LFS при необходимости:

- representative golden PNG;
- ограниченный acceptance-набор PDF.

Initial unchanged-template thresholds:

```text
SSIM >= 0.995
changed pixels <= 0.5%
```

Unexpected diff → `REVIEW_REQUIRED`.

Golden update требует template version bump, visual diff, semantic checks и review approval.

## 21. Ошибки CLI

Минимум:

```text
INVALID_PAYLOAD
UNSUPPORTED_ENGINE_CONTRACT
UNSUPPORTED_DOCUMENT_CONTRACT
TEMPLATE_NOT_INSTALLED
TEMPLATE_VERSION_NOT_INSTALLED
TEMPLATE_CONTRACT_MISMATCH
BACKEND_NOT_AVAILABLE
FONT_NOT_AVAILABLE
ASSET_NOT_AVAILABLE
UNSUPPORTED_OUTPUT_FORMAT
RENDER_FAILED
```

## 22. Начальные команды

```bash
qm-render version
qm-render capabilities
qm-render validate --input payload.json
qm-render inspect-template --template ID --version VERSION
qm-render render --input payload.json --output result.pdf
qm-render render --stdin --stdout --format pdf
```

## 23. Definition of Done архитектурного spike

- standalone repo существует;
- CLI работает offline;
- envelope schema определена;
- минимум два backend реально сравнены;
- три family prototype готовы;
- Windows/Linux smoke пройден;
- bundled fonts проверены;
- deployment size/performance измерены;
- visual migration harness работает;
- comparative matrix заполнена;
- primary backend выбран доказательно;
- migration recommendation оформлена;
- решение закреплено ADR.

## 24. Центральное свойство

Quartermaster Document Engine — не генератор одной складской накладной.

Это универсальный offline-capable renderer:

```text
self-contained versioned JSON
            ↓
universal CLI
            ↓
deterministic printable artifact
```

Если есть валидный payload и совместимая поставка engine, документ должен рендериться без сети, БД, Django, SyncServer и WPF.
