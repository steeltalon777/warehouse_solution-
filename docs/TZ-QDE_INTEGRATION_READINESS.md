# TZ: QuartermasterDocumentEngine — Integration Readiness

**Status:** Proposed
**Date:** 2026-08-15
**Author:** Architect Agent
**Companion ADRs:**
- `docs/adr/0030-qde-primary-rendering-backend-typst.md`
- `docs/adr/0031-qde-ownership-and-versioning.md`
- `docs/adr/0032-qde-warehouse-integration-contract.md`

**Sources:** ADR-0029, ADR-0001 (QDE), Phase 2 evidence package, AUDIT-2026-08-10 SEC-10/ARC-08/INT-02, TZ-PHASE2-BACKEND-SPIKE.md, ADR-0011.

---

## Execution Strategy

- **Sequential phases (6A → 6F)**, внутри фаз — частичный parallel.
- **Причина sequential**: каждый следующий этап зависит от предыдущего (6A адаптер → 6B модель → 6C template → 6D shadow → 6E acceptance → 6F cutover). Cutover нельзя выполнить без acceptance; acceptance нельзя — без shadow data.
- **Допустимый staged-parallel внутри 6A** (sequential внутри):
  - Поток 1: envelope builder (`apps/documents/services.py:build_qde_envelope`).
  - Поток 2: QDE subprocess client (`apps/documents/services.py:render_via_qde` + error mapping + timeout).
  - Точка интеграции: `DocumentPdfView` (Phase 6A.3) — единственный файл, оба потока сходятся.
  - **Максимум 2 потока** внутри 6A.
- **6C** (production Typst template) живёт в `QuartermasterDocumentEngine/templates/warehouse-waybill-ru@2.0.0/`. Может идти параллельно с 6A/6B при условии, что envelope schema финализирована (D1 ADR-0032).

```text
6A envelope adapter ──┐
                      ├── sequential: 6B artifact v2 ── sequential: 6D shadow ── sequential: 6E acceptance ── sequential: 6F cutover
6C production template┘                                                                     ↑
                                                                              зависит от 6A+6B+6C
```

---

## Execution Checklist

Архитектор создаёт checklist; executor проверяет только после реализации и верификации. Не путать со статус-чекбоксами ADRs.

- [x] 0. Context verified (ADR-0030/0031/0032 прочитаны, ADR-0029 §5/§6/§7/§8/§11 пройдены, AUDIT-2026-08-10 SEC-10 закрыт)
- [x] 1. Phase 6A complete — envelope adapter
- [x] 2. Phase 6A tests (unit + integration + stand smoke)
- [x] 3. Phase 6B complete — RenderedDocumentArtifact v2 + cache key
- [x] 4. Phase 6B tests (unit + integration + migration roundtrip + stand smoke)
- [ ] 5. Phase 6C complete — production Typst waybill template `warehouse-waybill-ru@2.0.0`
- [ ] 6. Phase 6C tests (golden + QDE unit/component + harness)
- [ ] 7. Phase 6D complete — SHADOW integration (legacy primary, QDE shadow)
- [ ] 8. Phase 6D tests (visual diff collected, hash comparison, stand smoke)
- [ ] 9. Phase 6E complete — acceptance / visual verification
- [ ] 10. Phase 6E tests (golden regression + manual sign-off + Playwright E2E)
- [ ] 11. Phase 6F complete — QDE primary cutover
- [ ] 12. Phase 6F tests (production smoke + rollback dry-run + latency comparison)
- [ ] 13. Regression checks: SyncServer pytest + Django manage.py test + QDE pytest зелёные
- [ ] 14. Documentation updated (README.md, ARCHITECTURE.md, INDEX.md, AI_ENTRY_POINTS.md)
- [ ] 15. Final acceptance review с evidence table

---

## 1. Context

Аудит 2026-08-15 показал:

1. QDE автономно реализован (Phase 0–2.1.2 закрыты), 215 тестов passed, Typst = provisional preferred backend (462 vs WeasyPrint 376, без veto).
2. QDE **никак не интегрирован** в production — `SyncServer/app/services/document_renderer.py` (Jinja2 + WeasyPrint) и `Warehouse_web/apps/documents/services.py` (Django templates + WeasyPrint) работают независимо.
3. `RenderedDocumentArtifact` model (`Warehouse_web/apps/documents/models.py`) хранит PDF bytes + cache keys, но **не имеет осей engine/backend/contract** — несовместимо с ADR-0029 §9.3.
4. **SEC-10** (template path traversal в SyncServer renderer) частично смягчён через QDE registry (ADR-0029 §7), но BFF-сторона QDE-вызова ещё не enforce'ит allowlist.
5. **ARC-08** (QDE untracked из root CI) — системный долг, закрывается ADR-0031.
6. **Windows verification** Typst binary не выполнен, но **не блокирует Phase 6** (Linux render-host) — ADR-0030 D5.

Настоящий TZ закрывает архитектурный фундамент для Phase 6: формализует модель данных, cutover-стратегию, разбивку реализации.

---

## 2. Goals

1. **Закрыть RenderedDocumentArtifact v2** под ADR-0029 §9.3 + ADR-0030 D3 (immutable revisions по осям engine/backend/contract/template).
2. **Спроектировать cutover LEGACY → SHADOW → QDE** без silent fallback (явные режимы, явные rollback paths).
3. **Разбить Phase 6 на исполнимые этапы 6A–6F** с понятными зависимостями и acceptance gates.
4. **Зафиксировать test ladder** для каждого этапа.
5. **Зафиксировать stand requirements** для Phase 6 (Docker, реальный QDE binary, Django test DB, integration tests).
6. **Зафиксировать evidence requirements** для executor'а (команды, логи, скриншоты).

---

## 3. Non-Goals (явно НЕ делается в этом TZ)

- Реализация Phase 6A–6F (это делают executor'ы).
- Сама миграция `QuartermasterDocumentEngine/` в monorepo (ADR-0031 migration plan; операционная задача).
- Миграция остальных типов документов (acceptance_certificate, act, invoice — Phase 7+).
- SyncServer renderer changes (ADR-0032 D4: SyncServer остаётся legacy path).
- WPF integration (Phase 8).
- Rust host (Phase 12).
- Auto-converter Django templates → Typst (запрещён ADR-0029 §10).
- Новые document families (route sheet / fuel report — Phase 9-10).
- Visual harness policy changes для legacy Django waybill (Phase 6E TZ содержит dispute policy, но это operational guideline, не код).

---

## 4. Architecture Decisions (cross-references)

Все архитектурные решения уже зафиксированы в companion ADRs. Настоящий TZ **ссылается** на них и не дублирует текст.

| Решение | ADR | Section |
|---|---|---|
| Primary backend = Typst | ADR-0030 | D1 |
| WeasyPrint = legacy | ADR-0030 | D2 |
| Backend по manifest, не клиентом | ADR-0030 | D3 |
| Migration policy per-template | ADR-0030 | D4 |
| Windows verification deferred | ADR-0030 | D5 |
| Monorepo, не independent repo | ADR-0031 | D1 |
| Generic envelope, typed payload внутри | ADR-0032 | D1 |
| Envelope builder в Warehouse_web BFF | ADR-0032 | D2 |
| Subprocess CLI invocation | ADR-0032 | D3 |
| SyncServer direct-render = legacy | ADR-0032 | D4 |
| Allowlist defense-in-depth (BFF + QDE) | ADR-0032 | D5 |
| Django BFF = render-host | ADR-0032 | D6 (ADR-0029 §8) |
| QDE как Python package в Docker image | ADR-0032 | D7 |
| Subprocess security (argv, temp dir, timeout) | ADR-0032 | D8 |

---

## 5. RenderedDocumentArtifact v2 Design

### 5.1. Целевая модель

```python
# Warehouse_web/apps/documents/models.py

class RenderedDocumentArtifact(models.Model):
    """Technical cache of PDFs derived from SyncServer document payloads.

    ADR-0030 D3 + ADR-0032 D1: artifact identity is immutable per render-revision.
    Re-render with different engine/backend/contract/template creates a NEW row,
    not an in-place update of existing row.

    Это cache technical state (PDF bytes + cache key fields), не warehouse domain data.
    Хранилище допустимо в Django ORM согласно Warehouse_web AGENTS.md
    («local storage for technical web state: ... cache»).
    """

    class Status(models.TextChoices):
        RENDERING = "rendering", "Rendering"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    # --- Identity: business document (из SyncServer documents.payload) ---
    document_id = models.CharField(max_length=64, db_index=True)
    revision = models.PositiveIntegerField(default=0)
    document_type = models.CharField(max_length=64)

    # --- Identity: render-revision (QDE axes; ADR-0029 §9.3) ---
    # Все обязательные identity axes заполняются для QDE-rendered строк.
    # Legacy-строки (Phase 6D backward compat) получают значения из DEFAULT_LEGACY_AXES.
    payload_hash = models.CharField(max_length=64)
    document_contract = models.CharField(max_length=64)              # e.g. "warehouse.operation-document/v2"
    template_id = models.CharField(max_length=128)                   # e.g. "warehouse-waybill-ru" (renamed from template_name)
    template_version = models.CharField(max_length=32, blank=True)   # e.g. "2.0.0"
    engine = models.CharField(max_length=32)                         # "qde" или "django-legacy"
    engine_version = models.CharField(max_length=32)                 # "0.1.0" / "waybill-pdf-v3"
    backend = models.CharField(max_length=32)                        # "typst" / "weasyprint"
    backend_version = models.CharField(max_length=32)                # "0.15.1" / "66.0"

    # --- Status + content ---
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RENDERING)
    render_role = models.CharField(
        max_length=32,
        choices=[
            ("primary", "Primary"),
            ("shadow", "Shadow"),
            ("emergency_fallback", "Emergency Fallback"),
            ("legacy", "Legacy"),
        ],
        default="primary",
    )
    pdf_file = models.FileField(upload_to="documents/pdf/", blank=True, null=True)
    pdf_sha256 = models.CharField(max_length=64, blank=True)
    size_bytes = models.PositiveIntegerField(default=0)
    rendered_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    # Optional diagnostic metadata only. Layout changes that affect output MUST bump template_version.
    # Therefore layout_version is intentionally NOT part of artifact identity/cache key.
    layout_version = models.CharField(max_length=32, blank=True)     # legacy/diagnostic label, e.g. "layout-v7.1"

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "document_id", "revision", "payload_hash",
                    "document_contract",
                    "template_id", "template_version",
                    "engine", "engine_version", "backend", "backend_version",
                ],
                name="uniq_rendered_document_artifact_v2",
            ),
        ]
        indexes = [
            models.Index(fields=["document_id", "status"]),
            models.Index(fields=["engine", "backend", "status"]),
            models.Index(fields=["template_id", "template_version"]),
        ]

    @property
    def is_ready(self) -> bool:
        return self.status == self.Status.READY and bool(self.pdf_file)

    def __str__(self) -> str:
        return (
            f"RenderedDocumentArtifact(document_id={self.document_id}, "
            f"engine={self.engine}, backend={self.backend}, status={self.status})"
        )
```

### 5.2. Константы и defaults

```python
DEFAULT_LEGACY_AXES = {
    "engine": "django-legacy",
    "engine_version": "waybill-pdf-v3",   # fallback if row.renderer_version is empty; data migration copies row.renderer_version otherwise
    "backend": "weasyprint",
    "backend_version": "66.0",           # actual legacy Warehouse_web WeasyPrint baseline (requirements: weasyprint>=66,<67)
    "document_contract": "warehouse.operation-document/v2",
    "template_id": "waybill_v1",         # бывший template_name "waybill_v1"
    "template_version": "1.0",           # бывший template_version
    "layout_version": "layout-v7.1",     # бывший WAYBILL_LAYOUT_CACHE_VERSION
    "render_role": "legacy",
}
```

### 5.3. Identity документа vs identity render-revision

**Identity документа** (доменная): `(document_id, revision)` — из SyncServer `documents` table.

**Identity render-revision** (DB uniqueness + cache identity): `(document_id, revision, payload_hash, document_contract, template_id, template_version, engine, engine_version, backend, backend_version)`.

Любое изменение любой оси → новая revision cache row, **не in-place update**.

### 5.4. Cache key (Django locmem cache)

Старый key:
```python
"waybill_pdf:{document_id}:{payload_hash}:{renderer_version}:{template_version}:layout-v7.1"
```

Новые keys (один namespace per engine):
```python
"qde_pdf:{document_id}:{revision}:{payload_hash}:{document_contract}:"
"{template_id}@{template_version}:{engine}@{engine_version}:{backend}@{backend_version}"

# Legacy namespace сохраняется для Phase 6D SHADOW и rollback:
"waybill_pdf:{document_id}:{payload_hash}:{renderer_version}:{template_version}:layout-v7.1"
```

Два namespace не пересекаются. Legacy rows изолированы.

### 5.5. Revision semantics — подробно

| Событие | Поведение |
|---|---|
| SyncServer обновил payload (новый `payload_hash`) | Новая cache row |
| Bump `template_version` (новый layout) | Новая cache row; старая row остаётся (исторический artifact) |
| Bump `engine_version` (например, QDE 0.2.0) | Новая cache row |
| Bump `backend_version` (например, Typst 0.16.0) | Новая cache row |
| Смена `document_contract` (например, `warehouse.operation-document/v2` → `/v3`) | Новая cache row |
| Retry после `FAILED` с теми же осями | Допустимы status/error transitions в той же row (`FAILED → RENDERING → READY`) до получения успешного artifact |
| Повторный render уже `READY` с теми же осями | Возвращается существующий artifact/cache hit; PDF bytes успешной row не перезаписываются |
| Django docstring говорит: «revisions per ADR-0029 §9.3 immutable» | Identity и успешный PDF immutable; технические status/error transitions до `READY` разрешены. |

### 5.6. Migration strategy (Phase 6B)

**Django migration `0002_rendered_document_artifact_v2`**:

1. **ADD columns** (nullable=True initially, default через data migration):
   - `document_contract VARCHAR(64) NULL`
   - `engine VARCHAR(32) NULL`
   - `engine_version VARCHAR(32) NULL`
   - `backend VARCHAR(32) NULL`
   - `backend_version VARCHAR(32) NULL`
   - `layout_version VARCHAR(32) NULL`
   - `render_role VARCHAR(32) NULL`

2. **RENAME columns** (одна операция, Django state_operations + SQL):
   - `template_name` → `template_id` (DB-level rename, не data loss).

3. **DATA migration** (RunPython):
   ```python
   DEFAULT_LEGACY_AXES = {...}
   for row in RenderedDocumentArtifact.objects.all():
       for field, value in DEFAULT_LEGACY_AXES.items():
           setattr(row, field, value)
       # engine_version берётся из row.renderer_version, если уже есть.
       if not row.engine_version and row.renderer_version:
           row.engine_version = row.renderer_version
       row.save(update_fields=list(DEFAULT_LEGACY_AXES.keys()) + ['engine_version'])
   ```

4. **ALTER columns** (nullable=False после backfill):
   - Все новые поля получают `null=False` через `ALTER COLUMN ... SET NOT NULL`.

5. **DROP legacy unique constraint**, ADD new one:
   ```sql
   ALTER TABLE documents_rendereddocumentartifact
     DROP CONSTRAINT uniq_rendered_document_artifact;
   ALTER TABLE documents_rendereddocumentartifact
     ADD CONSTRAINT uniq_rendered_document_artifact_v2
     UNIQUE (document_id, revision, payload_hash, document_contract,
             template_id, template_version, engine, engine_version, backend, backend_version);
   ```

6. **DEPRECATE** (не удалять) `renderer_version` — legacy alias. Сохраняется в DB для будущего forensic. Можно убрать в Phase 11+ после полного cutover.

7. **Reverse migration** (если нужно откатить): добавление `null=True` обратно, rename обратно, восстановление `renderer_version` из `engine_version`. Документируется в migration.

**Проверка feasibility**: migration должна быть выполнена на dev-стенде до production deploy.

---

## 6. Cutover Strategy: LEGACY → SHADOW → QDE

ADR-0032 D6 фиксирует render-host = Django BFF. Настоящий TZ конкретизирует **как** Django BFF переключается с Django-renderer на QDE-renderer.

### 6.1. Режимы

| Режим | Primary render | Shadow render | Где живёт shadow |
|---|---|---|---|
| **LEGACY** | Django-renderer (`render_document_pdf` legacy) | — | — |
| **SHADOW** | Django-renderer (legacy) | QDE (`render_via_qde`) | `RenderedDocumentArtifact` rows с `engine="qde"`, `status="ready"`, `render_role="shadow"` |
| **QDE** | QDE (`render_via_qde`) | Только explicit emergency fallback при включённом operator flag | fallback artifact: `engine="django-legacy"`, `status="ready"`, `render_role="emergency_fallback"` |

**Запрещено**: silent fallback без явной метки. Любой код, который при ошибке QDE молча выдаёт legacy PDF, **нарушает контракт**.

### 6.2. Режим LEGACY (текущее состояние до Phase 6)

- Поведение существующего кода `apps/documents/services.py:render_document_pdf`.
- Включается всегда по умолчанию до cutover.
- В Phase 6A не меняется; используется как baseline для Phase 6D сравнения.

### 6.3. Режим SHADOW (Phase 6D)

**Цель**: legacy renderer остаётся primary, QDE выполняет verification render для сравнения. QDE failure никогда не меняет содержимое primary PDF.

**Реализация**:

1. Новый service `render_via_qde(document, *, force=False) -> RenderedDocumentResult` в `apps/documents/services.py`. Возвращает QDE-rendered artifact.

2. `DocumentPdfView.get()` оборачивается в SHADOW-controller:
   ```python
   def get(self, request, document_id):
       document = api.get_document(document_id)

       # PRIMARY: legacy (как раньше)
       primary_result = render_document_pdf(document)

       # SHADOW verification: QDE не меняет содержимое primary response,
       # но синхронный вызов добавляет latency; включать только в controlled/sampled mode
       try:
           shadow_result = render_via_qde(document)
           log_shadow_comparison(
               document_id=document_id,
               legacy_sha256=primary_result.artifact.pdf_sha256,
               qde_sha256=shadow_result.artifact.pdf_sha256,
               legacy_pages=count_pages(primary_result.pdf_bytes),
               qde_pages=count_pages(shadow_result.pdf_bytes),
               # bytes-diff allowed if expected (layout version mismatch),
               # но pages и text должны совпадать в идеале.
           )
       except QdeRenderError as exc:
           log_shadow_failure(document_id=document_id, error=exc)

       # Возвращаем primary (legacy) PDF пользователю
       return response_with(primary_result)
   ```

3. **Shadow artifact storage**:
   - `RenderedDocumentArtifact` создаётся с `engine="qde"`, `status="ready"`, `render_role="shadow"`.
   - `pdf_file` сохраняется в `documents/pdf/shadow/{document_id}-{uuid}.pdf` (отдельный каталог, чтобы не смешивать с primary).
   - Shadow artifacts подчиняются той же immutable identity: новая комбинация payload/contract/template/engine/backend создаёт **новую row**, существующая `READY` row не затирается.
   - Retention policy shadow artifacts: 30 дней (настраивается); очистка выполняется отдельным retention job/management command и удаляет только истёкшие shadow rows/files.

4. **Hash & structural comparison**:
   - `legacy_sha256 != qde_sha256` ожидаемо (WeasyPrint vs Typst byte-determinism различается).
   - **Сравниваются**:
     - `pdf_pages_count`: ожидается точное совпадение для canonical waybill; любое расхождение → REVIEW_REQUIRED. Явно принятые layout differences допускаются только через Phase 6E manual sign-off.
     - `extracted_text` (через `pypdf.PdfReader.extract_text()`): должно содержать все ключевые значения (item names, quantities, document number, operation_display_number).
     - `media_box` (paper size): должно совпадать (A4 portrait).
   - Любое расхождение по text → REVIEW_REQUIRED; legacy остаётся primary, shadow логируется как anomaly.

5. **Latency / execution semantics**:
   - Приведённый Phase 6D wrapper выполняет QDE render синхронно до отправки response, поэтому SHADOW **может увеличить latency**, хотя не влияет на выбор/содержимое primary PDF.
   - SHADOW включается только в controlled verification window или для sampling; включать его на 100% production traffic без измерения p95 запрещено.
   - Отдельная queue/background worker инфраструктура не вводится в Phase 6D. Если синхронный shadow неприемлем по latency, evidence собирается management command по реальным сохранённым/полученным payloads; это не является триггером для нового artifact service само по себе.

6. **Operator visibility**:
   - Django admin command `compare_shadow_artifacts --limit 50` показывает последние SHADOW сравнения.
   - Prometheus metric `qde_shadow_match_ratio` (через `/metrics` endpoint): доля shadow-runs с pages/text-match.

7. **Acceptance gate SHADOW → QDE**:
   - ≥100 реальных production-shaped/production документов прошли shadow verification (request sampling или management command; способ фиксируется в evidence).
   - Page-count exact-match ratio ≥ 95% (legacy vs QDE); оставшиеся ≤5% обязательно разобраны и явно подписаны как допустимые layout differences.
   - Text match 100% по обязательным ключевым значениям.
   - 0 **неразрешённых** REVIEW_REQUIRED за последние 7 дней.
   - Manual sign-off пользователя.

### 6.4. Режим QDE (Phase 6F)

**Цель**: QDE primary, legacy = emergency fallback с явной меткой.

**Реализация**:

1. `DocumentPdfView.get()` переключается:
   ```python
   def get(self, request, document_id):
       document = api.get_document(document_id)
       try:
           result = render_via_qde(document)
           return response_with(result)
       except QdeRenderError as exc:
           # EMERGENCY FALLBACK — явная метка
           if settings.QDE_EMERGENCY_FALLBACK_ENABLED:
               fallback_result = render_document_pdf_legacy(document)
               log_emergency_fallback(document_id=document_id, error=exc)
               return response_with(fallback_result, header="X-QDE-Fallback: emergency")
           else:
               raise Http503("QDE render failed", exc)
   ```

2. `settings.QDE_EMERGENCY_FALLBACK_ENABLED = False` по умолчанию в Phase 6F (NO silent fallback). Operator может включить через env в emergency.

3. **Emergency fallback artifact** сохраняется с `engine="django-legacy"`, `status="ready"`, `render_role="emergency_fallback"`.

4. **Rollback path** (если QDE cutover показывает регрессию):
   - Один config flag flip обратно: `DOCUMENTS_RENDER_MODE=qde → legacy`.
   - Legacy path немедленно возвращается primary; QDE перестаёт быть primary.
   - SHADOW mode остаётся доступным через `DOCUMENTS_RENDER_MODE=shadow` для диагностики.

5. **Acceptance gate QDE → production**:
   - Все acceptance из §6.3 выполнены.
   - 7 дней production с QDE primary без emergency fallback (т.е. QDE не падал).
   - Latency p95 ≤ 2× legacy (cold-start budget + cache hit ratio).
   - Manual sign-off пользователя.

### 6.5. Mode configuration

```python
# Warehouse_web/config/settings/base.py

# Режим рендера: legacy | shadow | qde
DOCUMENTS_RENDER_MODE = os.environ.get("DOCUMENTS_RENDER_MODE", "legacy")

# QDE emergency fallback (только для QDE mode)
QDE_EMERGENCY_FALLBACK_ENABLED = os.environ.get(
    "QDE_EMERGENCY_FALLBACK_ENABLED", "false"
).lower() == "true"

# QDE subprocess timeout (seconds)
QDE_SUBPROCESS_TIMEOUT_SECONDS = int(
    os.environ.get("QDE_SUBPROCESS_TIMEOUT_SECONDS", "15")
)

# Canonical mapping document_type → (template_id, template_version)
DOCUMENT_TEMPLATE_MAP = {
    "waybill": ("warehouse-waybill-ru", "2.0.0"),  # Phase 6C: 2.0.0
    # Phase 7+:
    # "acceptance_certificate": ("acceptance-certificate-ru", "1.0.0"),
    # "act": ("write-off-act-ru", "1.0.0"),
    # "invoice": ("...", "..."),
}

# QDE install location (auto-detected from pip install -e ./QuartermasterDocumentEngine)
QM_TEMPLATES_DIR = os.environ.get(
    "QM_TEMPLATES_DIR",
    str(Path(sys.prefix) / "share" / "quartermaster_document_engine" / "templates"),
)

# Typst binary (Docker image default: /usr/local/bin/typst)
# Production: default `/usr/local/bin/typst` (Docker image после build-stage
# `scripts/fetch_typst.py --verify-sha256`, см. ADR-0032 D7).
# Dev / editable install: `QM_TYPST_BINARY` должен быть задан явно через
# `.env`, docker-compose override, или shell environment; типичное значение —
# `<repo>/QuartermasterDocumentEngine/.spike/typst-0.15.1/typst-x86_64-unknown-linux-musl/typst`.
# Runtime download Typst запрещён (ADR-0030 D1, ADR-0032 D7).
QM_TYPST_BINARY = os.environ.get("QM_TYPST_BINARY", "/usr/local/bin/typst")

TYPST_TIMESTAMP = "1700000000"  # pinned for determinism
```

---

## 6.6. Status taxonomy и render role

`status` описывает **техническое состояние** артефакта и не смешивается с его ролью:

```python
class Status(models.TextChoices):
    RENDERING = "rendering", "Rendering"
    READY = "ready", "Ready"
    FAILED = "failed", "Failed"
```

Контекст создания хранится отдельно:

```python
render_role = "primary" | "shadow" | "emergency_fallback" | "legacy"
```

`render_role` — **audit metadata о контексте, в котором row была создана**, а не часть render identity и не текущее состояние файла. Поле после создания row не меняется: shadow artifact может позднее быть использован как cache hit, но исторически остаётся созданным в shadow-контексте.

Это сохраняет семантику `is_ready`: любой успешно созданный PDF имеет `status="ready"` независимо от контекста создания. Legacy rows при Phase 6B backfill получают `render_role="legacy"`. Новых status-значений для Phase 6D/6F не требуется.

---

## 7. Security Boundary (cross-ref ADR-0032 D5/D8)

Настоящий TZ конкретизирует security boundary для Phase 6:

### 7.1. Allowlist enforcement (BFF-сторона)

- `apps/documents/services.py:build_qde_envelope` использует **только** `settings.DOCUMENT_TEMPLATE_MAP`.
- Прямой `template_id` от request body или query param **отклоняется** на уровне view (validation error).
- Unit test: `test_envelope_builder_rejects_arbitrary_template_id` — pytest fixture с произвольным `template_id="../../../etc/passwd"`.

### 7.2. Subprocess invocation

- Args только argv: `["python", "-m", "qm_cli.main", "render", "--input", envelope_path, "--output", output_path, "--format", "pdf"]`.
- Без shell=True.
- Без `os.system()`.
- Temp dir создаётся через `tempfile.mkdtemp(prefix="qde-", dir="/tmp")`. Permissions 0700. Cleanup в `finally`.
- Env vars: минимальный whitelist: только `PATH`, `LANG`, `LC_ALL`, `QM_TEMPLATES_DIR`, `QM_TYPST_BINARY`, `QM_FONTS_DIR`, `TYPST_TIMESTAMP`. Не передаются `DATABASE_URL`, `SECRET_KEY`, `SYNC_*_TOKEN`, Django session secrets. `QM_FONTS_DIR` — явная configuration axis для bundled/pinned fonts (ADR-0032 D3, D7); QDE engine (после Phase 6A implementation) читает её и передаёт Typst через `--font-path` (`backends/qm_backends/typst_backend.py`).

### 7.3. Envelope validation

- Envelope JSON валидируется через `jsonschema.validate(envelope, ENVELOPE_SCHEMA)` (QDE schema bundled as data file).
- Validation failure → `QdeValidationError` (HTTP 400 Bad Request, не 500).

### 7.4. Error codes

- QDE Phase 1 уже определяет 11 кодов (`engine/qm_engine/errors.py`).
- Django wrapper maps:
  - `INVALID_PAYLOAD` → 400
  - `UNSUPPORTED_ENGINE_CONTRACT` → 400
  - `UNSUPPORTED_DOCUMENT_CONTRACT` → 400
  - `TEMPLATE_NOT_INSTALLED` → 503
  - `TEMPLATE_VERSION_NOT_INSTALLED` → 503
  - `TEMPLATE_CONTRACT_MISMATCH` → 422
  - `BACKEND_NOT_AVAILABLE` → 503
  - `FONT_NOT_AVAILABLE` → 503
  - `ASSET_NOT_AVAILABLE` → 422
  - `UNSUPPORTED_OUTPUT_FORMAT` → 400
  - `RENDER_FAILED` → 500
- Subprocess timeout → `QdeTimeoutError` → 503 + `retry_after` header.

---

## 8. SyncServer Position (cross-ref ADR-0032 D4)

Подтверждается решение ADR-0032 D4:

- **SyncServer НЕ вызывает QDE в Phase 6.**
- `SyncServer/app/services/document_renderer.py` остаётся без изменений.
- `GET /documents/{id}/render` в SyncServer работает через старый Jinja2+WeasyPrint path.
- Это **legacy path** для клиентов, обходящих Django BFF.

Триггер для пересмотра: появление нового server-side consumer (например, прямой API для mobile/CLI). Это отдельный ADR.

---

## 9. Deployment Boundary (cross-ref ADR-0032 D7)

### 9.1. Docker image structure (Phase 6A.6)

```dockerfile
# Warehouse_web/Dockerfile (multi-stage)

# Stage 1: builder
FROM python:3.12-slim AS builder
WORKDIR /build
COPY Warehouse_web/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY Warehouse_web/ /build/Warehouse_web
COPY QuartermasterDocumentEngine/ /build/QuartermasterDocumentEngine
RUN pip install --no-cache-dir /build/QuartermasterDocumentEngine
RUN pip install --no-cache-dir /build/Warehouse_web

# Stage 1.5: typst-fetch (build-time only; runtime download forbidden)
FROM python:3.12-slim AS typst-fetch
WORKDIR /fetch
COPY QuartermasterDocumentEngine/scripts/fetch_typst.py /fetch/fetch_typst.py
COPY QuartermasterDocumentEngine/spike/typst-pin.json /fetch/typst-pin.json
RUN python /fetch/fetch_typst.py --verify-sha256 \
 && test -x /usr/local/bin/typst

# Stage 2: runtime
FROM python:3.12-slim
WORKDIR /app

# WeasyPrint native deps (Phase 6D SHADOW нужен)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcairo2 libpango-1.0-0 libgdk-pixbuf-2.0-0 libpangoft2-1.0-0 libffi8 libxml2 \
    fonts-dejavu-core fonts-liberation fontconfig \
    && rm -rf /var/lib/apt/lists/*

# Typst binary (pinned, sha256 verified at build-time)
COPY --from=typst-fetch /usr/local/bin/typst /usr/local/bin/typst
RUN chmod +x /usr/local/bin/typst && /usr/local/bin/typst --version

# QDE fonts (bundled/pinned; placed at QM_FONTS_DIR for the render environment).
# Note: as of the current pyproject.toml, fonts/ is NOT shipped via `pip install`
# data files. Fonts are copied explicitly from the QDE source tree in the
# build-stage. Phase 6A implementation requirement: extend QDE pyproject.toml
# `package-data` (or `data-files`) so future `pip install` invocations also
# place fonts at the resolved `paths.fonts_dir()` location.
COPY QuartermasterDocumentEngine/fonts/ /opt/qde/fonts/
ENV QM_FONTS_DIR=/opt/qde/fonts

# QDE templates (Phase 6A implementation requirement: same packaging gap as
# fonts; explicit COPY used here pending pyproject.toml update).
COPY QuartermasterDocumentEngine/templates/ /opt/qde/templates/
ENV QM_TEMPLATES_DIR=/opt/qde/templates

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages

# Warehouse_web code
COPY --from=builder /build/Warehouse_web /app

ENV DJANGO_SETTINGS_MODULE=config.settings.production
ENV DOCUMENTS_RENDER_MODE=legacy  # Phase 6A default
ENV QDE_EMERGENCY_FALLBACK_ENABLED=false
ENV TYPST_TIMESTAMP=1700000000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
```

`typst-fetch` stage выполняется **только во время build**: `scripts/fetch_typst.py --verify-sha256` получает pinned binary и проверяет digest. Runtime image не скачивает binary и не требует сети для старта/рендера. `QM_FONTS_DIR=/opt/qde/fonts` объявлен как явная configuration axis; QDE backend (после Phase 6A implementation) читает эту env var первой и передаёт Typst через свой стандартный `--font-path` mechanism (см. ADR-0032 D7 и TZ §7.2).

### 9.2. Deterministic environment

- `TYPST_TIMESTAMP=1700000000` (pinned).
- `LC_ALL=C.UTF-8`, `LANG=C.UTF-8` для consistency.
- `PATH=/usr/local/bin:/usr/bin:/bin` (no random host PATH).
- `HOME=/tmp` (no ~/.cache/ pollution).
- `XDG_CACHE_HOME=/tmp/xdg` (no ~/.cache pollution).

### 9.3. Resource limits

- `QDE_SUBPROCESS_TIMEOUT_SECONDS=15` (default; tunable).
- Memory: не является частью CLI protocol. При необходимости ограничивается container/cgroup либо проверенным Linux child-process wrapper; конкретный механизм выбирается по stand evidence.
- Disk: temp dir cleaned in `finally`; bounded size of 10 MB per envelope.

### 9.4. Stand (раздел 11 ниже) описывает локальный dev-стенд.

---

## 10. Phase 6 Decomposition (6A → 6F)

### 10.1. Phase 6A — Envelope adapter

**Файлы:**
- `Warehouse_web/apps/documents/services.py` — add `build_qde_envelope`, `render_via_qde`, error mapping.
- `Warehouse_web/apps/documents/tests/test_envelope_builder.py` — new.
- `Warehouse_web/apps/documents/tests/test_qde_subprocess.py` — new.
- `Warehouse_web/config/settings/base.py` — add `DOCUMENTS_RENDER_MODE`, `QDE_EMERGENCY_FALLBACK_ENABLED`, etc.
- `Warehouse_web/Dockerfile` — multi-stage QDE install.
- `QuartermasterDocumentEngine/pyproject.toml` — verify Python 3.12 compatible.

**Definition of done:**
- `build_qde_envelope(document) -> dict` builds valid QDE envelope per QDE schema.
- `render_via_qde(document, force=False) -> RenderedDocumentResult` calls `qm-render render` subprocess, returns result, errors mapped to QdeRenderError.
- Settings documented and exposed via env vars.
- Stand smoke: Django test runs with QDE subprocess mock → 200 OK.

**Acceptance gates:**
- Unit tests (envelope builder, error mapping).
- Integration tests с mocked QDE subprocess (return controlled PDF bytes, error codes).
- Stand smoke: реальный QDE binary в Docker, реальный envelope → реальный PDF.
- Static: `ruff check`, `mypy Warehouse_web/apps/documents`.

**Не входит**: подключение к `DocumentPdfView`. Phase 6A только service layer.

### 10.2. Phase 6B — RenderedDocumentArtifact v2 + cache key

**Файлы:**
- `Warehouse_web/apps/documents/models.py` — new fields, renamed field, new unique constraint.
- `Warehouse_web/apps/documents/migrations/0002_rendered_document_artifact_v2.py` — Django migration.
- `Warehouse_web/apps/documents/services.py` — cache key update, axis-based identity.
- `Warehouse_web/apps/documents/tests/test_artifact_model.py` — new.
- `Warehouse_web/apps/documents/tests/test_artifact_migration.py` — roundtrip test on migrated data.

**Definition of done:**
- Migration runs forward + backward без data loss.
- Legacy rows backfilled with `DEFAULT_LEGACY_AXES`.
- New QDE rows have all required identity axes populated.
- Unique constraint enforces immutable revisions.

**Acceptance gates:**
- Unit: `RenderedDocumentArtifact._meta.constraints` test.
- Integration: migration test на копии production-like DB.
- Stand smoke: `python manage.py showmigrations documents` показывает 0002 applied.
- Existing pytest не сломаны.

**Не входит**: новые status-значения не требуются; `render_role` уже введён в Phase 6B.

### 10.3. Phase 6C — Production Typst waybill template `warehouse-waybill-ru@2.0.0`

**Файлы (только в QDE):**
- `QuartermasterDocumentEngine/templates/warehouse-waybill-ru/2.0.0/manifest.yaml`
- `QuartermasterDocumentEngine/templates/warehouse-waybill-ru/2.0.0/main.typ`
- `QuartermasterDocumentEngine/templates/warehouse-waybill-ru/2.0.0/LAYOUT.md`
- `QuartermasterDocumentEngine/tests/unit/test_template_capabilities.py` — capability test для `@2.0.0`.
- `QuartermasterDocumentEngine/tests/golden/warehouse-waybill-ru/2.0.0/...` — golden.
- `QuartermasterDocumentEngine/tests/integration/test_canonical_waybill.py` — production-shape envelope.

**Definition of done:**
- Template package follows Phase 1 manifest schema.
- Layout соответствует существующей Django waybill layout (visual reference): 4-block MOVE signatures, 22/28/19 page capacities, full first-page header, short middle headers, full last-page form.
- Typst 0.15.1 renders без warnings.
- Golden: 1/20/75/200/500 line waybills → known page counts.
- 0 rendering errors.

**Acceptance gates:**
- Golden regression: `pytest -m golden` зелёный.
- Visual diff vs Django waybill reference (`warehouse-web/spike-out/waybill-django-reference.pdf`): SSIM report, manual sign-off.
- Unit: `inspect-template warehouse-waybill-ru --version 2.0.0` exit 0.
- Integration: render waybill-500 production-shape envelope → page count соответствует зафиксированному Phase 6C golden/baseline; любое отклонение требует REVIEW_REQUIRED.

**Не входит**: migration Django layout в QDE — это Phase 6D shadow validation.

### 10.4. Phase 6D — SHADOW integration

**Файлы:**
- `Warehouse_web/apps/documents/services.py` — `render_via_qde`, `log_shadow_comparison`.
- `Warehouse_web/apps/documents/views.py` — `DocumentPdfView` SHADOW wrapper.
- `Warehouse_web/apps/documents/management/commands/compare_shadow_artifacts.py` — operator command.
- `Warehouse_web/apps/documents/tests/test_shadow_integration.py` — new.

**Definition of done:**
- Django BFF в режиме `DOCUMENTS_RENDER_MODE=shadow`:
  - Возвращает legacy PDF пользователю.
  - Выполняет QDE shadow verification render; синхронный режим может добавлять latency и используется контролируемо/сэмплированно.
  - Сравнивает pages + text + sha256, логирует результат.
- Operator command показывает последние 50 сравн.
- Prometheus metric `qde_shadow_match_ratio` экспортируется (если уже есть `/metrics` endpoint; иначе — Django logging).

**Acceptance gates:**
- Integration: shadow render 1 waybill → 2 artifacts (legacy + qde shadow), оба ready.
- Stand smoke: реальный документ через SHADOW path → 2 artifact rows в БД.
- Visual diff collected для ≥50 реальных production-shaped/production documents перед Phase 6E; способ сбора (request sampling или management command) фиксируется в evidence.

**Не входит**: Prometheus metric setup, если нет существующего `/metrics`. Django logging достаточно.

### 10.5. Phase 6E — Acceptance & visual verification

**Файлы:**
- `Warehouse_web/apps/documents/tests/test_qde_visual_match.py` — new.
- `Warehouse_web/apps/spike-out/waybill-qde-vs-django/` — visual diff artifacts.
- `docs/TZ-QDE_VISUAL_VERIFICATION_REPORT.md` — sign-off report.

**Definition of done:**
- 7-дневное verification window с ≥100 реальными production-shaped/production documents; не требуется держать SHADOW на 100% пользовательского traffic.
- Page-count exact-match ratio ≥ 95% (legacy vs QDE); оставшиеся ≤5% обязательно разобраны и явно подписаны как допустимые layout differences.
- Text match 100% по обязательным значениям (item names, quantities, document_number).
- 0 неразрешённых REVIEW_REQUIRED.
- Manual sign-off пользователя на docs/TZ-QDE_VISUAL_VERIFICATION_REPORT.md.

**Acceptance gates:**
- Все acceptance из §6.3.
- Visual diff report в `docs/TZ-QDE_VISUAL_VERIFICATION_REPORT.md`.
- User sign-off.

**Не входит**: обширные UX изменения, A/B test design — Phase 7+.

### 10.6. Phase 6F — QDE primary cutover

**Файлы:**
- `Warehouse_web/apps/documents/views.py` — `DocumentPdfView` QDE primary + emergency fallback path.
- `Warehouse_web/config/settings/base.py` — `DOCUMENTS_RENDER_MODE=qde` (operator sets).
- `Warehouse_web/apps/documents/tests/test_qde_primary.py` — new.

**Definition of done:**
- `DOCUMENTS_RENDER_MODE=qde` в production.
- QDE primary, legacy = emergency fallback path с явной меткой.
- Rollback procedure проверена: переключение `DOCUMENTS_RENDER_MODE=legacy` + restart/redeploy возвращает legacy primary. Management command может выполнять preflight/diagnostics, но не считается магическим способом изменить environment запущенного контейнера.
- 7 дней production без emergency fallback.

**Acceptance gates:**
- Все acceptance из §6.4.
- Latency p95 ≤ 2× legacy.
- Manual sign-off пользователя на cutover.

**Не входит**: удаление legacy Django renderer. ADR-0032 D2 + ADR-0029 §8 — legacy остаётся в bundle.

---

## 11. Test Ladder

Стандартные уровни из `docs/AGENT_TZ_WORKFLOW.md`.

### Level 1: Static

| Что | Команда | Где |
|---|---|---|
| ruff | `ruff check Warehouse_web/ QuartermasterDocumentEngine/` | root |
| mypy | `mypy Warehouse_web/apps/documents/ QuartermasterDocumentEngine/{engine,backends,cli}` | root |
| Django check | `python Warehouse_web/manage.py check` | Warehouse_web |
| Migration check | `python Warehouse_web/manage.py makemigrations --check --dry-run` | Warehouse_web |

### Level 2: Unit

| Что | Файл |
|---|---|
| `build_qde_envelope` happy path + edge cases | `apps/documents/tests/test_envelope_builder.py` |
| `render_via_qde` error mapping | `apps/documents/tests/test_qde_subprocess.py` |
| `RenderedDocumentArtifact` model fields + unique constraint | `apps/documents/tests/test_artifact_model.py` |
| Cache key derivation per axes | `apps/documents/tests/test_cache_key.py` |
| `DOCUMENT_TEMPLATE_MAP` allowlist (SEC-10) | `apps/documents/tests/test_template_allowlist.py` |
| QDE Phase 1 unit (regression) | `QuartermasterDocumentEngine/tests/unit/` |

### Level 3: Component

| Что | Файл |
|---|---|
| `DocumentPdfView` QDE mode (mocked subprocess) | `apps/documents/tests/test_view_qde.py` |
| `DocumentPdfView` SHADOW mode | `apps/documents/tests/test_view_shadow.py` |
| `DocumentPdfView` legacy mode (regression) | `apps/documents/tests/test_view_legacy.py` |

### Level 4: Integration

| Что | Файл |
|---|---|
| Migration 0002 roundtrip | `apps/documents/tests/test_artifact_migration.py` |
| End-to-end: реальный envelope → реальный qm-render subprocess → PDF bytes | `apps/documents/tests/test_qde_e2e.py` |
| QDE Phase 1+2 regression | `QuartermasterDocumentEngine/tests/integration/` |

### Level 5: Stand smoke

- `make up` запускает весь стенд.
- `http://localhost:8001/admin/` — Django admin работает (admin/admin123).
- `http://localhost:8000/api/v1/health` — SyncServer health OK.
- `python Warehouse_web/manage.py shell` — проверить, что `DOCUMENTS_RENDER_MODE` настройка читается.
- Реальный документ через Django shell → SHADOW render → проверить 2 artifact rows.

### Level 6: UI automation

- Playwright E2E: открыть операцию, нажать «Сформировать накладную», дождаться PDF, скачать, проверить sha256 в БД.
- `Warehouse_web/e2e/` — существующие specs обновляются.

### Level 7: User scenarios

- Сценарий 1: пользователь-кладовщик формирует waybill через Django web → получает PDF за <3 сек.
- Сценарий 2: 100 waybill-операций подряд (batch stress) — pages match ≥95%.
- Сценарий 3: emergency fallback при выключенном Typst binary — Django BFF возвращает legacy PDF с заголовком `X-QDE-Fallback: emergency`.

### Level 8: Regression

- SyncServer pytest: `python -m pytest` в `SyncServer/`.
- Django: `python Warehouse_web/manage.py test`.
- QDE: `pytest` в `QuartermasterDocumentEngine/`.
- Warehouse_frontend: `npm run build` + `npm run test:unit`.

### Level 9: Acceptance review

- Evidence table с командами, результатами, логами, скриншотами.
- User sign-off в `docs/TZ-QDE_VISUAL_VERIFICATION_REPORT.md`.

---

## 12. Stand Description

### 12.1. Database

- PostgreSQL 15 (Docker container `warehouse_postgres`).
- Alembic migrations applied: `make migrate`.
- Seed data: dev fixtures через `Warehouse_web/manage.py loaddata` если нужно.

### 12.2. Services

| Service | Address | Container |
|---|---|---|
| PostgreSQL | `localhost:5432` | `warehouse_postgres` |
| SyncServer | `localhost:8000` | `warehouse_syncserver` |
| Django BFF | `localhost:8001` | `warehouse_web` |
| QDE CLI | subprocess внутри `warehouse_web` | не отдельный контейнер |

### 12.3. Environment variables (имена, не значения)

- `DJANGO_ENV=development`
- `SYNC_SERVER_URL=http://warehouse_syncserver:8000`
- `SYNC_ROOT_USER_TOKEN`
- `SYNC_DEVICE_TOKEN`
- `DATABASE_URL`
- `DJANGO_SETTINGS_MODULE=config.settings.development`
- `SECRET_KEY`
- `DOCUMENTS_RENDER_MODE=legacy|shadow|qde` (Phase 6A default: `legacy`)
- `QDE_EMERGENCY_FALLBACK_ENABLED=false`
- `QDE_SUBPROCESS_TIMEOUT_SECONDS=15`
- `QM_TEMPLATES_DIR`
- `QM_TYPST_BINARY`
- `QM_FONTS_DIR` (explicit render environment axis; ADR-0032 D3, D7)
- `TYPST_TIMESTAMP=1700000000`
- `LC_ALL=C.UTF-8`
- `LANG=C.UTF-8`

### 12.4. Health checks

- `curl -s http://localhost:8000/api/v1/health`
- `curl -s http://localhost:8001/healthz/`
- `pg_isready -h localhost -p 5432 -t 3`

### 12.5. Smoke commands

```bash
# Phase 6A: QDE subprocess работает
docker exec warehouse_web python -c "from apps.documents.services import build_qde_envelope, render_via_qde; ..."

# Phase 6B: migration applied
docker exec warehouse_web python manage.py showmigrations documents

# Phase 6D: SHADOW mode активен
docker exec warehouse_web python manage.py shell -c "from django.conf import settings; print(settings.DOCUMENTS_RENDER_MODE)"

# Phase 6F: QDE primary mode работает
docker exec warehouse_web python manage.py shell -c "from django.conf import settings; print(settings.DOCUMENTS_RENDER_MODE)"
```

### 12.6. Reset/cleanup

```bash
# Применяется между фазами
cd /home/makc/AI_sandbox/warehouse_solution
make down
make up
make migrate

# Если нужен full reset (P3 hardening):
make restart
```

---

## 13. Risks

| Риск | Severity | Митигация |
|---|---|---|
| Visual diff на edge cases (длинные имена, кириллица) при SHADOW | 🟡 Medium | Dispute policy в Phase 6E TZ; specific edge cases регрессируются в golden |
| Cold-start latency в 15 s timeout budget | 🟡 Medium | Cache key + `RenderedDocumentArtifact`; first hit cold, second hit warm |
| Migration 0002 data loss | 🔴 High (если miswritten) | Roundtrip test на dev; backup production DB перед migration |
| SyncServer начинает вызывать QDE случайно | 🟡 Medium | ADR-0032 D4 явно запрещает; review gate на любые SyncServer changes |
| Typst 0.15.x upstream maintenance | 🔵 Note | Pin зафиксирован; апгрейд требует spike + ADR |
| Subprocess attack surface | 🟡 Medium | ADR-0032 D8 (argv-only, temp dir, env whitelist, timeout) |
| QDE phase отстаёт от production reality | 🟡 Medium | 7-дневный SHADOW period перед cutover |

---

## 14. Out of Scope

Явно вне scope:

- Phase 7+ миграция остальных типов документов (acceptance_certificate, act, invoice).
- WPF / Windows integration.
- Rust host.
- Multi-page Django waybill content-aware migration в QDE (Phase 6C создаёт `warehouse-waybill-ru@2.0.0` через visual reference, не через auto-conversion).
- New document families (route sheet, fuel report).
- Auto-converter Django → Typst.
- HTML preview (PNG preview в QDE есть; HTML — Phase 7+).
- Artifact service extraction (Phase 11 trigger conditions).

---

## 15. Acceptance Criteria

TZ-QDE_INTEGRATION_READINESS принимается когда:

1. Все 4 документа (ADR-0030, ADR-0031, ADR-0032, настоящий TZ) зафиксированы в `dev` ветке.
2. ADR-0032 §Decision Boundary не противоречит ADR-0029 §8.
3. ADR-0030 §Cross-references явно указывают на исправление «ADR-0002» → «ADR-0030» в существующих документах.
4. ADR-0031 явно отменяет ADR-0029 §1 (отдельный репозиторий) и ссылается на ARC-08.
5. Phase 6A–6F разложены с понятными зависимостями, файлами в scope, и acceptance gates.
6. Test ladder присутствует для всех уровней (1–9) с конкретными командами.
7. Stand description соответствует AGENT_TZ_WORKFLOW.md §Stand.
8. Risks + mitigations зафиксированы.

Phase 6 (любая фаза 6A–6F) начинается только после принятия настоящего TZ и всех трёх ADR.

---

## 16. Evidence Requirements

Executor'ы (Phase 6A–6F) включают в отчёт evidence table (см. `docs/AGENT_TZ_WORKFLOW.md`).

Минимум для каждой фазы:

```markdown
## Evidence

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|
| Static (ruff + mypy) | `ruff check . && mypy ...` | pass/fail | log path |
| Unit | `pytest apps/documents/tests/unit/` | pass/fail | log path |
| Integration | `pytest apps/documents/tests/integration/` | pass/fail | log path |
| Stand smoke | `curl /documents/{id}/pdf` (или Django shell) | pass/fail | URL/log/screenshot |
| UI automation | Playwright | pass/fail | report path |
| Migration roundtrip | `manage.py migrate forward/backward` | pass/fail | DB snapshot |
```

---

## 17. Cross-references

### Связанные ADRs (companion)

- ADR-0030 (QDE Primary Rendering Backend Typst) — primary backend решение.
- ADR-0031 (QDE Ownership and Versioning) — monorepo.
- ADR-0032 (Warehouse → QDE Integration Contract) — canonical seam.

### Связанные существующие ADRs

- ADR-0029 (Quartermaster Document Engine architecture) — фиксирует границы producer/consumer и envelope.
- ADR-0011 (Django → SyncServer Transport Hardening) — **отдельный** transport level; не путать с Django → QDE.
- ADR-0001 (QDE engine-internal) — internal decisions внутри QDE.

### Связанные TZ

- `QuartermasterDocumentEngine/doc/TZ-PHASE2-BACKEND-SPIKE.md` — closed evidence package.
- `QuartermasterDocumentEngine/doc/TZ-PHASE1-CLI-SKELETON.md` — closed.
- `docs/TZ-V3.1I_WAYBILL_PAGINATION_AND_SYNC_HARDENING.md` — closed; Phase 6C reference для pagination semantics.
- `docs/TZ-QUARTERMASTER_3_1.md` — branding/offline readiness (closed); **не QDE integration**.

### Audit references

- `docs/AUDIT_ARCHITECTURE_SECURITY_2026-08-10.md`:
  - **ARC-08** (QDE untracked) — закрывается ADR-0031.
  - **SEC-10** (template path traversal) — закрывается ADR-0032 D5 + настоящим TZ §7.
  - **INT-02** (submit swallows render error) — не решается Phase 6; остаётся как observation.

---

## 18. Confidence

- **High** для Phase 6A–6F как реализуемых этапов без дополнительных архитектурных решений.
- **High** для того, что ADR-0030 + ADR-0031 + ADR-0032 + настоящий TZ закрывают architectural фундамент для Phase 6.
- **Medium** для конкретных timing budget'ов (cold-start 15 s timeout; latency p95 ≤ 2× legacy) — измеримы в Phase 6D stand smoke.
- **Medium** для визуальной dispute policy на SHADOW → QDE cutover — закрывается в Phase 6E TZ после наблюдения 50+ shadow-runs.
- **High** для того, что Phase 6 не требует дополнительных ADRs (если визуальный diff и latency budgets укладываются).