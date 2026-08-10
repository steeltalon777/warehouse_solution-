# Scope: Old waybills re-render with current template on demand

**Date:** 2026-07-09
**Decision Makers:** architect + user (storekeeper/PM)
**Status:** Ready for review
**Source TZ:** `docs/TZ-V3.1I_WAYBILL_PAGINATION_AND_SYNC_HARDENING.md` (rev. 5)

## Problem

Кладовщик спросил: «старые накладные не переделаются? как привести их к новому виду?»

Гипотеза кладовщика: «метаданные должны сохраняться в БД, а накладная по ним рендерится. Это позволит печатать старые накладные в новой форме, потому что мы работаем над рендером, и если правила рендера изменятся — старые накладные по запросу отрендерятся в актуальный формат».

## Проверка гипотезы — текущее поведение (Validating)

**Гипотеза верна.** Архитектура уже работает так, как ожидает кладовщик.

Evidence (где это в коде):

| Аспект | Файл / строка | Поведение |
|---|---|---|
| Метаданные хранятся в БД | `SyncServer/app/services/document_service.py:285-298` | `documents.payload` (JSON) сохраняется при создании документа; для `auto_finalize=True` — замораживается навсегда. |
| Payload lines используют snapshot'ы | `document_service.py:512-516` | `line.item_name` = `line.item_name_snapshot` — исторические данные, не live-каталог. |
| BFF рендерит на лету | `Warehouse_web/apps/bff_api/documents_views.py:90` | `DocumentRenderView` вызывает `render_document_pdf(document)`, **не** читает файл с диска. |
| Кэш-bust через renderer_version | `Warehouse_web/apps/documents/services.py:73, 95` | `cache_key = waybill_pdf:{document_id}:{payload_hash}` и `renderer_version` в unique constraint `RenderedDocumentArtifact`. Бамп `DOCUMENT_RENDERER_VERSION` инвалидирует кэш. |
| Бамп уже сделан | `Warehouse_web/config/settings/base.py:46` | v1 → v2 → v3 (3 итерации за один TZ). |
| Audit log рендера | `Warehouse_web/apps/documents/models.py:4-29` | `RenderedDocumentArtifact`: `pdf_sha256`, `size_bytes`, `rendered_at`, `renderer_version`, `template_name`, `template_version`. |

**Вывод:** при следующем открытии старой накладной через BFF после deploy новой версии шаблона PDF автоматически рендерится в актуальном формате. Никаких ручных действий не нужно.

## In Scope

1. **Документировать текущее поведение** в `docs/TZ-V3.1I_WAYBILL_PAGINATION_AND_SYNC_HARDENING.md` (или отдельном `docs/architecture/waybill-rendering-pipeline.md`) как **фичу**, а не баг.
2. **Добавить acceptance criteria** в TZ, подтверждающие что старые накладные рендерятся в актуальном формате:
   - `[ ] При изменении CSS-шаблона + бампе `DOCUMENT_RENDERER_VERSION` следующий запрос PDF для старой накладной отдаёт новый формат (без ручной миграции).`
   - `[ ] `RenderedDocumentArtifact` хранит `renderer_version`, по которому можно отследить, с какой версией шаблона отрендерен PDF.`
   - `[ ] `RenderedDocumentArtifact` имеет unique constraint по `(document_id, revision, payload_hash, template_name, template_version, renderer_version)` — это гарантирует, что каждый рендер фиксируется отдельной записью.`
3. **(Опционально, low priority) Management command `rebuild_documents`** для batch re-render:
   - `python manage.py rebuild_documents --days=30 --batch=100` — перерендерит все накладные за последние 30 дней порциями по 100.
   - Полезно, если деплой делается во время пиковой нагрузки и хочется прогреть кэш заранее.

## Out of Scope

1. **Пересборка `payload` в БД** — payload заморожен по дизайну (audit trail). Изменение payload = пересмотр архитектуры SyncServer, не относится к накладной/wеб-рендерингу.
2. **Пересчёт `document_number`** — фиксируется при submit (`document_service.py:281-282`), не должен меняться задним числом.
3. **Изменение `finalized_at`** — фиксируется при submit, не меняется.
4. **Удаление/архивация старых `RenderedDocumentArtifact`** — отдельная housekeeping-задача, не входит в этот scope.
5. **Полный пересчёт всех накладных через cron** — infra-решение, не входит в этот scope.
6. **Изменение схемы payload** (`PAYLOAD_SCHEMA_VERSION` = "1.1.0") — миграция на новую схему требует Alembic + data migration, отдельный TZ.

## Success Criteria

1. **Документация:** TZ-V3.1I содержит раздел «Old waybills re-render» с явным описанием архитектуры (payload хранится, PDF рендерится на лету, кэш-bust через `renderer_version`).
2. **Audit:** На dev-стенде после deploy можно открыть старую накладную (скажем, finalized неделю назад) и убедиться:
   - PDF в браузере отображается в актуальном формате (с 22 строками на 1-й странице).
   - `RenderedDocumentArtifact` для этого документа имеет `renderer_version = "waybill-pdf-v3"`, `template_name = "waybill_v1"`, `template_version = "1.0"`.
3. **Cache TTL:** кэш автоматически очищается через `CACHE_TTL = 3600` (1 час), но renderer bump очищает кэш мгновенно.
4. **(Опционально)** Management command `rebuild_documents` существует и работает.

## Assumptions

| Assumption | Status | Validation |
|---|---|---|
| `documents.payload` не пересобирается автоматически при изменении каталога | **Validated** | `document_service.py:512-516` — `item_name` берётся из snapshot, не из live Item. |
| BFF рендерит PDF на лету при каждом запросе (не из файла) | **Validated** | `bff_api/documents_views.py:90` — `HttpResponse(result.pdf_bytes, ...)`. |
| `renderer_version` участвует в кэш-ключе | **Validated** | `services.py:73, 95` + `models.py:32-42` unique constraint. |
| Старые накладные доступны через BFF `DocumentRenderView` | **Validated** | `documents_views.py:73-102` принимает `document_id`, не ограничивает по дате/статусу. |
| Кладовщик хочет именно «визуально новый PDF», а не «новые метаданные» | **Validated** | Подтверждено в ответах на Socratic-вопросы. |
| Management command `rebuild_documents` нужен | **Reasonable** | Не критично — auto re-render уже работает. Можно отложить. |
| Полный re-render через cron нужен | **Dangerous** | Потенциально дорогая операция (рендер = CPU). Лучше lazy. Не делать без явной потребности. |

## Alternatives Considered

| Approach | Verdict | Reason |
|---|---|---|
| **Do nothing** (текущее) | ✅ **Принято** | Уже работает корректно. Только документировать. |
| Management command `rebuild_documents` | ⚠ **Опционально** | Полезно для batch-прогрева кэша. Не критично, lazy re-render работает. |
| Cron / scheduled task | ❌ Отклонено | Дорого, без явной пользы. Lazy re-render дешевле. |
| Пересборка payload в БД | ❌ Отклонено | Ломает audit trail, рискованно. Не требуется по требованию. |
| Кнопка «Обновить накладную» в UI | ❌ Отклонено | Overkill — пользователь получает актуальный PDF при каждом открытии автоматически. |
| Data migration для `PAYLOAD_SCHEMA_VERSION` 1.0.0 → 1.1.0 | ❌ Out of scope | Отдельный TZ, требует Alembic. Не нужно для рендера. |

## Selected Approach

**Document current behavior, add acceptance criteria. Optionally add management command.**

Это подтверждает архитектурное решение и защищает от регрессий: если кто-то решит «оптимизировать» рендер, закэшировав PDF в файл, тесты на acceptance поймают это.

## First Slice

**Документация + acceptance** (в этот TZ):
- Добавить в TZ-V3.1I раздел «Old waybills re-render on demand» с evidence.
- Добавить 3 acceptance criteria (см. Success Criteria п. 1-3).
- (Опционально) Создать `docs/architecture/waybill-rendering-pipeline.md` — небольшой architecture doc для cross-project reference.

**Management command** (отдельный follow-up, если потребуется):
- `apps/documents/management/commands/rebuild_documents.py`
- `--days=N` (default 7), `--batch-size=N` (default 100)
- Iterates documents за период, вызывает `render_document_pdf(document, force=True)` для каждого
- Логирует прогресс, обрабатывает ошибки

## Next Step

- [ ] Получить approval от пользователя на scope (особенно: «только документировать, без management command» или «+ management command»).
- [ ] Если approved: реализовать доку + acceptance в этом же TZ-V3.1I (rev. 6) или в отдельном TZ.
- [ ] Если management command: отдельный TZ (low priority, follow-up).
