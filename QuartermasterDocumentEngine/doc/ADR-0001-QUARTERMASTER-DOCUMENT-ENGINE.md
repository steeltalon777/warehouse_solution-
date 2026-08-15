# ADR-0001: Quartermaster Document Engine — standalone stateless document renderer

**Status:** Accepted
**Date:** 2026-08-10
**Decision owner:** user
**Источники:** `doc/SPEC-QUARTERMASTER_DOCUMENT_ENGINE-v2.md` (SPEC v2), `doc/ROADMAP-QUARTERMASTER_DOCUMENT_ENGINE-v1.md` (ROADMAP v1)
**Вытесняет:** SPEC v1 от 2026-08-06 (`warehouse_solution/docs/SPEC-QUARTERMASTER_DOCUMENT_ENGINE.md`) — остаётся как исторический контекст

## 1. Контекст

В системе существуют два независимых контура рендеринга PDF (SyncServer, Jinja2, и Django-шаблоны на WeasyPrint-базе). Это даёт:

- дублирование шаблонной логики между контурами;
- невозможность offline-рендера на клиентах (WPF, Android, терминал);
- привязку шаблонов к доменному коду платформ;
- отсутствие версионированной воспроизводимости уже выпущенных документов.

Требуется универсальный рендерер для накладных, путевых листов, топливных отчётов и будущих семейств документов, работающий без сети, БД и Quartermaster-сервисов.

## 2. Решение

### D1. Standalone repository

`QuartermasterDocumentEngine` — отдельный репозиторий (размещён внутри `warehouse_solution/` как nested-проект). Он не является частью SyncServer, Warehouse_web, Warehouse_client_core или WPF. Git submodule — не основной способ распространения; основная единица поставки — bundle (D11).

### D2. Граница producer/consumer

- **SyncServer** — владелец доменной логики и единственный producer document payload: строит immutable самодостаточный versioned payload, выбирает `document_contract`/`template_id`/`template_version`, сохраняет payload и его hash.
- **Engine** — stateless consumer: валидация схемы, registry шаблонов, compatibility checks, локализация, пагинация, геометрия страниц, таблицы, типографика, шрифты/assets, layout подписей, QR/barcode как возможности представления, выбор backend, формирование artifact.
- Engine **не содержит**: ORM, доступ к PostgreSQL, HTTP к SyncServer, бизнес-аудит, persistent cache, retention policy, знания об Operation/OperationLine/revisions/остатках/пользователях.

### D3. Universal CLI — основной integration contract

`qm-render` с командами `version`, `capabilities`, `validate`, `inspect-template`, `render`. Режимы: file→artifact, stdin→file, stdin→stdout. `document_id` — только metadata внутри payload, никогда не ключ для сетевого lookup. Сценарий «человек в терминале → JSON → PDF» обязателен.

### D4. Offline mode обязателен

Главный критерий универсальности: валидный payload + совместимый engine bundle достаточны для рендера без сети, БД, Django, SyncServer, WPF. Базовый offline render не использует сетевые assets.

### D5. Envelope и семейства контрактов

Envelope содержит: `engine_contract_version`, `document_contract`, `document_type`, `template_id`, `template_version`, `locale`, `render_profile`, `document`, опционально `document_id`, `document_number`, `assets`. Один гигантский payload запрещён: контрактные семейства (`warehouse.operation-document/v2`, `transport.vehicle-route-sheet/v1`, `transport.equipment-route-sheet/v1`, `fuel.monthly-report/v1`, `inventory.balance-report/v1`, …) с reusable-блоками для организаций, людей, техники, подписей, количеств, денег, периодов, QR/barcode data. Даты и числа — однозначный machine format.

### D6. Шаблоны — versioned immutable packages

`templates/<id>/<version>/`: `manifest.yaml` + entrypoint + partials + assets. Manifest задаёт id/version, document contract, backend, entrypoint, output formats, locales, page settings, capabilities, required fonts/assets. Опубликованные версии immutable; любое намеренное визуальное изменение = новый `template_version`; silent fallback на latest запрещён; отсутствующая версия = ошибка.

### D7. Backend abstraction; победитель выбирается доказательно

Единый логический интерфейс:

```text
render(normalized_document, template_package, output_format, render_options) -> RenderResult
```

Spike (Phase 2): WeasyPrint 66 (текущий baseline) против Typst. Chromium/Paged Media — только при доказанной необходимости; direct PDF APIs — не предпочтительный общий backend. Победитель не назначен заранее; решение на Phase 5 по weighted matrix из ROADMAP. Исходы: Typst primary / mixed backend с явным выбором backend в manifest / новое исследование backend.

### D8. Artifact boundary

Core engine не хранит persistent artifacts. Phases 1–3: SyncServer хранит immutable payload; Django BFF — временный server-side render-host (`RenderedDocumentArtifact`, cache, audit, retry/storage). Отдельный artifact service не создаётся до появления триггеров:

- второй server-side consumer;
- scheduled/night batch;
- >100 документов в batch workflow;
- общая очередь;
- object storage;
- централизованные retries;
- server-side render без Django;
- заметная деградация web latency;
- starvation Django workers.

### D9. Шрифты и assets — bundled и pinned

Никакой зависимости от случайных системных шрифтов. Cyrillic обязательна; missing font = render error; Windows/Linux используют одинаковые версии ресурсов. Аудит реальных шрифтов текущих шаблонов — перед spike (Phase 2).

### D10. Историческая воспроизводимость

Уже сохранённый PDF предпочтительнее re-render; template update не меняет старый artifact; metadata artifact содержит payload hash, contract, template id/version, engine/backend versions, PDF SHA-256; старые payload поддерживаются explicit adapters, где это практично; архив сохраняет templates, manifests, fonts, checksums.

### D11. Language-agnostic поставка

Bundle `quartermaster-document-engine-X.Y.Z-{linux-x64.tar.gz, windows-x64.zip}`: engine executable/runtime, `contracts/`, `templates/`, `fonts/`, manifests, `checksums.json`. Клиенты не зависят от языка реализации.

### D12. Machine-readable errors

Обязательные коды: `INVALID_PAYLOAD`, `UNSUPPORTED_ENGINE_CONTRACT`, `UNSUPPORTED_DOCUMENT_CONTRACT`, `TEMPLATE_NOT_INSTALLED`, `TEMPLATE_VERSION_NOT_INSTALLED`, `TEMPLATE_CONTRACT_MISMATCH`, `BACKEND_NOT_AVAILABLE`, `FONT_NOT_AVAILABLE`, `ASSET_NOT_AVAILABLE`, `UNSUPPORTED_OUTPUT_FORMAT`, `RENDER_FAILED`.

### D13. Runtime evolution без ломки публичных контрактов

Python host может остаться навсегда, если проходит deployment/performance. Rust host рассматривается только при измеримой пользе (Windows packaging, startup bottleneck, embedded Typst, one-binary deployment). Публичный CLI contract, schemas, manifests и templates при смене runtime не меняются.

## 3. Явно не решено (deferred)

- Победитель среди rendering backends — Phase 5.
- Chromium/Paged Media — только при оправдании spike.
- Rust host — Phase 12, при измеримой пользе.
- Artifact service — Phase 11, по триггерам D8.
- Автоконвертер Jinja/Django-шаблонов в Typst — вне scope; миграция ручная через visual migration harness (Phase 3).

## 4. Последствия

Плюсы:

- offline render у любого потребителя (SyncServer, Django, WPF, Android, CI, scripts, человек);
- воспроизводимость документов и контролируемые visual-изменения;
- чистая граница: домен — в SyncServer, представление — в engine;
- доказательный выбор backend вместо предварительных ставок.

Минусы/обязательства:

- SyncServer обязан строить полный self-contained payload (DB-shortcuts невозможны);
- миграция шаблонов ручная;
- возможен временный mixed backend (два стека поддержки);
- требуется поставка bundle на Windows/WPF.

## 5. Риски

| Риск | Митигация |
|---|---|
| Недостатки Typst для fixed forms/геометрии | D6/D7: backend выбирается per-template в manifest; mixed backend допустим |
| Вес/сложность WeasyPrint-зависимостей на Windows | измерение в Phase 4 (deployment size, startup, RAM) |
| Лицензии шрифтов | аудит до bundling (Phase 2) |
| Неконтролируемые performance-пороги | калибровка относительно текущего WeasyPrint baseline (SPEC §18) |
| Нет Windows runner у агентов | Windows smoke помечается blocker'ом, выполняется пользователем (прецедент TZ Quartermaster 3.1) |

## 6. Триггеры пересмотра ADR

- Срабатывание любого триггера из D8 (extraction artifact service) — отдельный ADR.
- Смена runtime (D13) — отдельный ADR с результатами измерений.
- Изменение политики совместимости `engine_contract_version` или политики immutability шаблонов.
