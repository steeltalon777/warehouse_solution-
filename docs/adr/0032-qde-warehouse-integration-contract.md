# ADR-0032: Warehouse → QuartermasterDocumentEngine Integration Contract

- **Status:** Proposed
- **Date:** 2026-08-15
- **Deciders:** пользователь, Architect Agent
- **Scope:** канонический seam между `Warehouse_web` BFF и `QuartermasterDocumentEngine` для Phase 6
- **Supersedes:** ничего (комплементарен к ADR-0029 §5/§6/§7/§8/§11)
- **Related decisions:** ADR-0029 §5 (envelope), §6 (per-family contracts), §7 (backend abstraction), §8 (render-host ownership), §11 (fonts/assets); ADR-0030 (Typst primary); ADR-0031 (monorepo); ADR-0011 (Django → SyncServer transport, **не путать с Django → QDE**); AUDIT-2026-08-10 SEC-10 (template path traversal)

---

## Context

1. **QDE Phase 0–2.1.2 закрыты.** Engine готов принимать `envelope` JSON и возвращать PDF/PNG. Контракт envelope уже зафиксирован в `QuartermasterDocumentEngine/contracts/envelope/v1/envelope.schema.json` (ADR-0029 §5).
2. **SyncServer** сегодня:
   - Производит `documents.payload` (включая `payload_hash`, `template_name`, `template_version`, `payload_schema_version`).
   - Рендерит HTML/PDF через `DocumentRenderer` (Jinja2 + WeasyPrint) для прямого API `GET /documents/{id}/render`.
   - Не вызывает QDE.
3. **`Warehouse_web` (Django BFF)** сегодня:
   - Получает документ через SyncServer API (`DocumentsAPI.get_document`).
   - Рендерит PDF через `apps/documents/services.py:render_document_pdf` (Django templates + WeasyPrint).
   - Кэширует PDF в Django cache + `RenderedDocumentArtifact` model.
   - Возвращает PDF через `apps/documents/views.py:DocumentPdfView`.
4. **Phase 6 цель**: Django BFF начинает вызывать QDE для рендера вместо собственного WeasyPrint-пути. SyncServer **не меняется**.
5. **SEC-10**: path traversal в `SyncServer/app/services/document_renderer.py:117-131` (резолв `template_name` через `templates_root / f"{normalized}.html"`). QDE реестр эту проблему не имеет (ADR-0029 §7: «SyncServer фиксирует template_id/template_version как opaque identifiers; QDE registry резолвит»), но **Django-сторона QDE-вызова должна enforce'ить allowlist**, чтобы SEC-10 mitigation распространялась на новый render-path.
6. **ADR-0011** фиксирует, что Django ↔ SyncServer транспорт — HTTP/JSON `/api/v1`. Это **не** относится к Django → QDE: QDE это не SyncServer. Django → QDE — отдельный seam, решается настоящим ADR.

---

## Decision

### D1. **Generic envelope approach**: один envelope на семейство документов, typed payload внутри.

Структура envelope (наследует QDE ADR-0029 §5 + Phase 1 schema):

```json
{
  "engine_contract_version": "1.0.0",
  "document_contract": "warehouse.operation-document/v2",
  "document_type": "waybill",
  "template_id": "warehouse-waybill-ru",
  "template_version": "2.0.0",
  "locale": "ru-RU",
  "render_profile": "print",
  "document_id": "uuid",
  "document_number": "210726/1430/1",
  "document": { ...typed payload... },
  "assets": { ...optional... }
}
```

- `document_contract` идентифицирует семейство (`warehouse.operation-document/v2`, `transport.vehicle-route-sheet/v1`, ...).
- Внутри `document` — типизированный payload, формат которого определён contract-specific schema в `contracts/<contract-id>/<version>/schema.json`.
- QDE registry разрешает `(template_id, template_version) → template package → backend`, валидирует совместимость с `document_contract`.

**Отклонена альтернатива «per-form typed envelopes»** (`WaybillEnvelope`, `AcceptanceCertificateEnvelope`, ...). Причины:
- Каждое новое семейство документов требовало бы новой envelope schema, новой command-line flag в QDE CLI, новой envelope → backend dispatch logic.
- Generic envelope уже enforce'ит валидацию typed payload через contract schema внутри envelope.
- Per-form envelopes ломают CLI-универсальность `qm-render render` (Phase 1 design invariant).

### D2. **Envelope builder живёт в Warehouse_web BFF**

- Django service `apps/documents/services.py` дополняется `build_qde_envelope(document: dict) -> dict`.
- Builder:
  1. Берёт `documents.payload` от SyncServer (через `DocumentsAPI`).
  2. Нормализует поля envelope (document_id, document_number, locale, render_profile).
  3. Оборачивает payload в `envelope.document`.
  4. Резолвит `(template_id, template_version)` через **canonical mapping** в Django settings (см. D5).
  5. Возвращает готовый envelope dict для передачи в QDE.

Builder **не импортирует** QDE Python API напрямую. Builder формирует dict; вызов QDE — отдельный шаг (D3).

### D3. **Django BFF вызывает QDE через subprocess CLI**

- Subprocess invocation: `python -m qm_cli.main render --input <envelope.json> --output <artifact.pdf> --format pdf --templates-dir <qde_templates_dir>`.
- Аргументы argv-only, без shell.
- Timeout: configurable, default **15 s** (cold-start Typst budget + 2× warm budget, см. PERF-REPORT.md).
- Stdin/stdout pipe для крупных envelope (Phase 1 `qm-render render --stdin --stdout` поддерживается).
- Env vars: `QM_TEMPLATES_DIR` (если не через `--templates-dir`), `QM_TYPST_BINARY` (default `<qde_install>/.spike/typst-x86_64-unknown-linux-musl/typst`), `QM_FONTS_DIR` (явная configuration axis для bundled/pinned fonts; QDE engine читает env var первой и fallback'ит на resolved `paths.fonts_dir()` если не задан — parallel к существующему `QM_TEMPLATES_DIR` механизму; поддержка `QM_FONTS_DIR` в QDE engine — **Phase 6A implementation requirement**, см. TZ §6.5, §7.2, §9.1), `TYPST_TIMESTAMP=1700000000` для determinism.
- Рабочая директория subprocess — temp dir, очищается после рендера.
- Парсинг результата: exit code + stderr JSON `{"error": {"code": ..., "message": ...}}` (ADR-0029 §10 / Phase 1 CLI contract).

### D4. **SyncServer остаётся direct-render для legacy paths**

- `GET /documents/{id}/render` в SyncServer продолжает работать через `DocumentRenderer` (Jinja2 + WeasyPrint).
- Это **legacy path** для клиентов, не использующих Django BFF (если такие есть).
- BFF path: Django получает JSON от SyncServer и сам рендерит через QDE (Phase 6).
- SyncServer **не вызывает QDE** в Phase 6. Это явное архитектурное решение (см. §Decision Boundary ниже).

### D5. **Allowlist template_id/version — defense in depth**

- **Уровень 1 (Warehouse_web BFF)**: Django settings содержат canonical mapping `DOCUMENT_TEMPLATE_MAP = {"waybill": ("warehouse-waybill-ru", "2.0.0"), ...}`. Builder использует только этот mapping; произвольный `template_id` от клиента НЕ допускается. Закрывает SEC-10 mitigation на BFF-стороне.
- **Уровень 2 (QDE registry)**: QDE registry резолвит `(template_id, template_version) → template package` против installed templates. Неизвестный → `TEMPLATE_NOT_INSTALLED` (exit 4). Это уже enforce'ится в QDE Phase 1.
- **Belt-and-suspenders**: оба уровня обязательны. Bypass любого — нарушение контракта.
- `template_id` и `template_version` — opaque identifiers, не файловые пути. SyncServer не получает filesystem path-параметров от Django.

### D6. **Render-host = Warehouse_web BFF (ADR-0029 §8 unchanged)**

- Trigger conditions для выделения в отдельный artifact service не появились:
  - Не появился второй server-side consumer.
  - Не появился scheduled/night batch-рендер.
  - Нет batch-операций >100 документов.
  - Нет общей очереди/object storage.
  - Django workers не исчерпываются PDF-задачами.
  - Web latency не деградирует от рендера.
- Решение ADR-0029 §8 **подтверждается** и фиксируется в настоящем ADR (см. §Decision Boundary).
- Phase 6 не создаёт artifact service.

### D7. **Deployment: QDE как Python package внутри Warehouse_web Docker image**

- `Warehouse_web/Dockerfile` дополняется multi-stage COPY:
  ```dockerfile
  COPY QuartermasterDocumentEngine /build/QuartermasterDocumentEngine
  RUN pip install /build/QuartermasterDocumentEngine
  ```
- Typst binary **всегда попадает в immutable image на build-stage**: `scripts/fetch_typst.py --verify-sha256` (или эквивалентный build step) получает pinned binary и проверяет digest, после чего runtime stage делает `COPY ... /usr/local/bin/typst`. **Runtime download запрещён**: production render-host не должен зависеть от сети для старта или рендера.
- Fonts: `QuartermasterDocumentEngine/fonts/DejaVuSans*.ttf` попадают в immutable image на build-stage (explicit `COPY` из source tree; **текущий** `pyproject.toml` не включает `fonts/` в `package-data`, поэтому `pip install` без явного Dockerfile COPY не доставит шрифты). `QM_FONTS_DIR` объявлен как явная configuration axis для render environment; QDE backend читает env var первой и передаёт Typst через свой стандартный `--font-path` mechanism (`backends/qm_backends/typst_backend.py`). Поддержка `QM_FONTS_DIR` в QDE engine — **Phase 6A implementation requirement** (parallel к существующему `QM_TEMPLATES_DIR`); silent fallback на системные шрифты запрещён (ADR-0001 D9, FONT_NOT_AVAILABLE при отсутствии bundled шрифта).
- `QM_TYPST_BINARY` env var указывает на `/usr/local/bin/typst` или путь в venv site-packages.
- Логика subprocess (D3) не меняется между dev и prod; только пути.

### D8. **Subprocess security boundary**

- Args: только argv (no shell). Параметры envelope передаются через stdin или temp file.
- Temp file: создаётся через `tempfile.NamedTemporaryFile(delete=True, dir=<safe_base>)`. `<safe_base>` — `/tmp/qde-<uuid>/`. Cleanup в `finally`.
- Working directory subprocess: `<safe_base>`. Не позволяет template уйти в произвольную FS location.
- Env vars: только `PATH`, `LANG`, `LC_ALL`, `QM_TEMPLATES_DIR`, `QM_TYPST_BINARY`, `QM_FONTS_DIR`, `TYPST_TIMESTAMP`. Никаких passthrough Django settings. `QM_FONTS_DIR` — явная configuration axis для bundled/pinned fonts (D3, D7); QDE engine (после Phase 6A implementation) читает её и передаёт Typst через `--font-path` (`backends/qm_backends/typst_backend.py`).
- Resource limits: timeout обязателен. Memory limiting **не является частью QDE CLI contract**; при необходимости он задаётся на уровне container/cgroup либо проверенным Linux child-process wrapper. Конкретный механизм выбирается в Phase 6A по stand evidence, без добавления фиктивного `--memory-limit` флага.
- Timeout: enforced через `subprocess.run(timeout=...)` + `TimeoutExpired` → `QdeRenderError`.

---

## Consequences

### Pros

- **Канонический envelope** в одном месте (QDE schema) — не дублируется.
- **SEC-10 закрыт** на BFF-стороне через allowlist.
- **SyncServer не меняется в Phase 6** — минимальный blast radius.
- **Render-host остаётся Django BFF** без новых сервисов (ADR-0029 §8 trigger conditions не сработали).
- **Subprocess invocation** даёт fail-stop semantics (exit code + JSON error). Никакого in-process coupling.
- **Deterministic PDF** через `TYPST_TIMESTAMP` + Pinned Typst binary + bundled fonts → archive-friendly.

### Cons / обязательства

- **Cold-start overhead** (~460 ms CLI vs in-process WeasyPrint). См. PERF-REPORT §In-process. Для разовых скачиваний PDF незаметно. Для batch-сценариев может стать trigger'ом для ADR-0029 §8.
- **Subprocess failure modes**: binary missing, fonts missing, template missing, timeout, OOM. Каждый mode → explicit error code из QDE → Django wrapper maps на HTTP 503 / 500.
- **BFF добавляет responsibilities** (envelope builder, QDE subprocess client, error mapping, timeout, cache key update). Это допустимо — Django BFF и так BFF.
- **SEC-10 mitigation частично дублируется** (allowlist в Django + registry в QDE). Принятая цена за defense in depth.

### Risks

| Риск | Митигация |
|---|---|
| Subprocess hang при сбое Typst binary | Timeout + cleanup в `finally` |
| Cold-start budget превышает user-perceived latency на hot-path | Cache key в Django cache + `RenderedDocumentArtifact` (TZ §RenderedDocumentArtifact v2) |
| Drift между фактически установленным QDE и metadata артефакта | `engine_version` читается из установленного QDE и сохраняется в artifact identity; release notes фиксируют bundled version |
| SyncServer начнёт рендерить по другому пути (прямой API), обходя QDE audit | D4 явно сохраняет SyncServer direct-render как legacy; не скрывается |
| Template ID collision между разными doc families | D5 + QDE registry namespace enforcement |

---

## Rejected Alternatives

### Per-form typed envelopes (`WaybillEnvelope`, ...)

См. D1. Отклонено.

### Django in-process вызов QDE Python API

In-process создаёт cross-version coupling: Django прибит к конкретной QDE Python ABI. Подпроцесс позволяет обновлять QDE независимо от Django web stack. ADR-0011 отвергает in-process для Django → SyncServer по той же причине; здесь та же логика. **Отклонено**.

### Django напрямую вызывает Typst binary (минуя QDE CLI)

Минует QDE registry, validation, error model. Нарушает ADR-0029 §3 (CLI как primary integration contract). **Отклонено**.

### QDE как REST service / microservice

Триггеры ADR-0029 §8 не сработали. Over-engineering. **Отклонено**.

### QDE как sidecar container

Django BFF уже sidecar к SyncServer в Docker compose. Ещё один sidecar создаёт network dependency. Subprocess проще. **Отклонено** на текущем этапе; может появиться в Phase 11.

### SyncServer вызывает QDE

Создаёт второй server-side consumer → триггер ADR-0029 §8 («появился второй server-side consumer»). Преждевременно. Phase 6 — только BFF path. **Отклонено в Phase 6**.

### Auto-converter Django templates → Typst

Запрещён ADR-0029 §10. Не выбрано.

---

## Decision Boundary

Настоящий ADR явно фиксирует:

1. **Django BFF остаётся render-host для QDE в Phase 6** (D6, ADR-0029 §8).
2. **SyncServer direct-render остаётся legacy path** (D4). SyncServer не вызывает QDE в Phase 6.
3. **Render-host trigger conditions** (ADR-0029 §8) не изменились:
   - появление второго server-side consumer (например, если SyncServer начнёт вызывать QDE);
   - появление scheduled/night batch-рендера;
   - >100 документов в batch;
   - общая очередь / object storage;
   - рендер без Django;
   - worker starvation;
   - latency degradation.
4. **Subprocess timeout default 15 s** может быть пересмотрен в Phase 6 по результатам stand smoke.
5. **Allowlist mapping** (`DOCUMENT_TEMPLATE_MAP`) — настройка Warehouse_web, не QDE. Смена маппинга не требует ADR.

---

## Out of Scope

- WPF / Windows integration (Phase 8).
- Rust host (Phase 12).
- Артефакт-сервис (Phase 11 trigger).
- Production envelope для route sheet / fuel report (Phase 9-10).
- Multi-page Django waybill migration в QDE (Phase 6C).
- Visual regression harness acceptance criteria (Phase 6E TZ).

---

## Cross-references

- ADR-0029 §5/§6/§7/§8/§11.
- ADR-0030 (Typst primary).
- ADR-0031 (monorepo).
- ADR-0011 (Django → SyncServer transport; **не путать** с настоящим seam).
- ADR-0001 (QDE engine-internal).
- `docs/AUDIT_ARCHITECTURE_SECURITY_2026-08-10.md` SEC-10 (закрывается).
- `docs/TZ-QDE_INTEGRATION_READINESS.md` (companion implementation TZ).

---

## Acceptance Criteria

ADR-0032 принимается когда:

1. Все 8 решений (D1–D8) явно описаны и противоречий внутри ADR нет.
2. Cross-references с ADR-0029 §8 и ADR-0011 подтверждены (разные transport-уровни).
3. Phase 6A может начаться без дополнительных архитектурных решений.
4. SEC-10 mitigation strategy зафиксирована defense-in-depth (BFF + QDE registry).