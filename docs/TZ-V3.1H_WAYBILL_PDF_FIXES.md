# TZ: V3.1H — Waybill PDF Fixes

**Date:** 2026-06-24
**Based on:** brainstorm 22.06.2026, аудит цепочки накладных
**Status:** Ready

## Execution Strategy

- [x] 🟢 Executed in parallel (Stage 1: H1 + H2+H3 in 2 parallel agents)
- **Note:** H1 (SyncServer) is in a different repo from H2/H3 (Warehouse_web), allowing safe parallelism. H2 and H3 both touch `services.py` so they were combined in one agent.

---

## Execution Checklist

- [x] 0. Context verified — цепочка отслежена, проблемы подтверждены
- [x] 1. Stage H1: Auto-update waybill metadata on draft edit ✅
- [x] 2. Stage H1 tests: 4 new tests pass (unit + integration: draft edit → waybill refreshed) ✅
- [x] 3. Stage H2: Fix multi-page rendering (dynamic pagination + CSS fixes) ✅
- [x] 4. Stage H2 tests: 8 existing tests pass; CSS page-break-inside:avoid on `<tr>` ✅
- [x] 5. Stage H3: Render-on-demand (Django cache, no PDF storage) ✅
- [x] 6. Stage H3 tests: 8 existing tests pass; stand smoke: PDF served with `x-document-pdf-cache: miss` ✅
- [x] 7. Integration: full flow draft → edit → render → PDF served 200 OK ✅
- [x] 8. Regression: SyncServer 449 passed, Django 350 passed, Angular build OK ✅
- [ ] 9. Final acceptance review — ожидает пользователя

---

## Диагноз (контекст)

### Текущая цепочка

```
create_operation  →  ❌ waybill НЕ создаётся
update_operation  →  ❌ waybill НЕ обновляется
submit_operation  →  ✅ DocumentService.generate_from_operation(auto_finalize=True)

Angular «Накладная» → BFF POST /waybill/open
    → SyncServer POST /documents/operations/{id}/documents
    → Django render_document_pdf():
        1. Кеш-проверка (RenderedDocumentArtifact по хешу payload)
        2. Jinja2 waybill_pdf.html → WeasyPrint PDF
        3. Сохранить в MEDIA_ROOT/documents/pdf/
        4. Вернуть URL
```

### Проблемы

| # | Проблема | Серьёзность |
|---|----------|-------------|
| P1 | Метаданные накладной не обновляются при редактировании черновика | 🔴 Кладовщик печатает устаревший документ |
| P2 | Многостраничные таблицы рендерятся с разрывами, половина таблицы на следующем листе | 🔴 Документ выглядит неопрятно |
| P3 | PDF-файлы накапливаются в MEDIA_ROOT без очистки | 🟡 Мусор на диске |

---

## Stage H1: Auto-update waybill metadata on draft edit

### Задача H1.1: Добавить вызов DocumentService в update_operation

**Файл:** `SyncServer/app/services/operations_service.py`, метод `update_operation()`

После обновления строк и данных операции, до коммита транзакции:

```python
# H1: Auto-regenerate waybill for draft operations
if operation.status == "draft":
    try:
        await DocumentService.generate_from_operation(
            uow=uow,
            operation=operation,
            auto_finalize=False,  # draft → не finalize
        )
    except Exception as exc:
        logger.warning("waybill_auto_update_failed", operation_id=str(operation.id), error=str(exc))
        # Не абортим update_operation из-за ошибки waybill
```

Логика `generate_from_operation` с `auto_finalize=False` и draft-статусом (строки 227-235 в `document_service.py`):
1. Void все существующие не-void документы для этой операции+типа+шаблона
2. Создать новый draft-документ
3. НЕ finalize (финализация только на submit)

Это **уже реализовано** в `DocumentService` — нужно только вызвать.

### Задача H1.2: Идемпотентность

При каждом `update_operation` старые draft-документы void'ятся, создаётся новый. Это допустимо: метаданные всегда соответствуют актуальному состоянию черновика.

### Задача H1.3: Производительность

`update_operation` теперь делает дополнительный запрос к БД для генерации waybill. Для оценки нагрузки:
- `_build_payload()` собирает данные: sites, lines, items, units, categories — ~5-10 запросов
- `_void_existing_documents()` — 1 UPDATE
- `INSERT INTO documents` — 1 запрос
- Итого ~10-15 дополнительных запросов на update

Для справки: текущий `update_operation` делает ~20-30 запросов. Добавление ~10 запросов — приемлемо для админского/кладовщицкого интерфейса (не high-throughput).

### Acceptance criteria H1

- [ ] Изменить строки в черновике → накладная обновлена
- [ ] Изменить количество → накладная обновлена
- [ ] Старые draft-документы void'ятся
- [ ] Ошибка генерации накладной НЕ абортит update_operation
- [ ] `python -m pytest` — все 410+ тестов зелёные

---

## Stage H2: Fix multi-page rendering

### Задача H2.1: Динамический расчёт строк на странице

**Файл:** `Warehouse_web/apps/documents/services.py`, функция `paginate_waybill_lines()`

**Текущая проблема:** жёстко 24 строки на первой странице, 30 на последующих. Не учитывает:
- Многострочные названия ТМЦ
- Разную высоту строк

**Решение:** заменить статическую пагинацию на расчёт по высоте контента.

```python
def paginate_waybill_lines(
    lines: list[dict[str, Any]],
    first_page_max_rows: int = 24,
    continuation_max_rows: int = 30,
    estimated_row_height_mm: float = 7.0,
    available_height_first_page_mm: float = 170.0,
    available_height_continuation_mm: float = 210.0,
) -> list[list[dict[str, Any]]]:
    """
    Paginate waybill lines dynamically based on content height.
    
    Each line contributes estimated_row_height_mm plus extra for multi-line names.
    """
    pages: list[list[dict[str, Any]]] = [[]]
    current_height = 0.0
    page_index = 0
    
    for line in lines:
        name = line.get("item_name_snapshot", "")
        # Estimate line height: base + 1 extra row per ~60 chars
        extra_lines = len(name) // 60
        line_height = estimated_row_height_mm + (extra_lines * estimated_row_height_mm * 0.6)
        
        max_height = available_height_first_page_mm if page_index == 0 else available_height_continuation_mm
        
        if current_height + line_height > max_height and pages[page_index]:
            pages.append([])
            page_index += 1
            current_height = 0.0
        
        pages[page_index].append(line)
        current_height += line_height
    
    return pages
```

### Задача H2.2: Обновить шаблон

**Файл:** `Warehouse_web/apps/documents/templates/documents/waybill_pdf.html`

Убедиться, что шаблон корректно обрабатывает динамическое количество страниц:
- `page-break-before: always` на каждой странице кроме первой
- Таблица не разрывается посреди строки
- `page-break-inside: avoid` на строках таблицы

CSS-фиксы при необходимости:
```css
.waybill-table tr {
    page-break-inside: avoid;
}
.waybill-table thead {
    display: table-header-group; /* повторять заголовок на каждой странице */
}
```

### Задача H2.3: Проверить на реальных данных

Создать тестовую операцию с 40+ строками ТМЦ (включая длинные названия). Сгенерировать накладную — убедиться, что:
- Страницы не обрываются посреди строки
- Заголовок таблицы повторяется
- Все строки присутствуют

### Acceptance criteria H2

- [ ] Накладная с 3+ страницами — таблица не разрывается
- [ ] Длинные названия не вызывают перекос
- [ ] Заголовок таблицы на каждой странице
- [ ] Подписи на каждой странице
- [ ] `python manage.py test apps.documents` — зелёные

---

## Stage H3: Render-on-demand (no persistent storage)

### Задача H3.1: Убрать сохранение PDF-файлов

**Файл:** `Warehouse_web/apps/documents/services.py`, функция `render_document_pdf()`

**Текущее поведение:** PDF сохраняется в `MEDIA_ROOT/documents/pdf/` + запись в `RenderedDocumentArtifact`.

**Целевое поведение:** Рендерить PDF в память (BytesIO), отдавать как `HttpResponse`, НЕ сохранять на диск.

```python
from io import BytesIO
from django.http import HttpResponse

def render_document_pdf_streaming(document: dict) -> HttpResponse:
    """Render waybill PDF in-memory and return as streaming response."""
    html = render_document_html(document)
    pdf_buffer = BytesIO()
    HTML(string=html).write_pdf(pdf_buffer)
    pdf_buffer.seek(0)
    
    filename = build_document_pdf_filename(document)
    response = HttpResponse(pdf_buffer.read(), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    response["X-Document-Pdf-Cache"] = "miss"
    return response
```

### Задача H3.2: Оставить кеш на 1 час

**Файл:** `Warehouse_web/apps/documents/services.py`

Сохранить `RenderedDocumentArtifact` (без файла) как запись о факте рендеринга, с TTL 1 час в Django-кеше:

```python
from django.core.cache import cache

CACHE_KEY_PREFIX = "waybill_pdf:"
CACHE_TTL = 3600  # 1 час

def get_cached_or_render(document_id: str, payload_hash: str) -> bytes:
    cache_key = f"{CACHE_KEY_PREFIX}{document_id}:{payload_hash}"
    pdf_data = cache.get(cache_key)
    if pdf_data:
        return pdf_data
    
    pdf_data = _render_to_bytes(document_id)
    cache.set(cache_key, pdf_data, CACHE_TTL)
    return pdf_data
```

### Задача H3.3: Очистить старые PDF из MEDIA_ROOT

**Файл:** `Warehouse_web/apps/documents/management/commands/cleanup_old_pdfs.py`

```python
from django.core.management.base import BaseCommand
from apps.documents.models import RenderedDocumentArtifact
from django.utils import timezone
from datetime import timedelta

class Command(BaseCommand):
    help = "Remove PDF artifacts older than 30 days"
    
    def handle(self, **options):
        cutoff = timezone.now() - timedelta(days=30)
        old = RenderedDocumentArtifact.objects.filter(rendered_at__lt=cutoff)
        for artifact in old:
            artifact.pdf_file.delete(save=False)
        count, _ = old.delete()
        self.stdout.write(f"Removed {count} old PDF artifacts")
```

### Acceptance criteria H3

- [ ] PDF отдаётся как streaming response, без сохранения на диск
- [ ] При повторном запросе (тот же payload) — кеш из Django cache на 1 час
- [ ] `RenderedDocumentArtifact` очищается (можно оставить модель для аудита, но без файлов)
- [ ] `python manage.py test apps.documents` — зелёные

---

## Files in scope

| Файл | Этап | Тип изменений |
|---|---|---|
| `SyncServer/app/services/operations_service.py` | H1 | Вызов `DocumentService` в `update_operation` |
| `SyncServer/app/services/document_service.py` | H1 | Проверить `auto_finalize=False` + draft |
| `Warehouse_web/apps/documents/services.py` | H2, H3 | Динамическая пагинация, render-on-demand |
| `Warehouse_web/apps/documents/templates/documents/waybill_pdf.html` | H2 | CSS-фиксы для многостраничности |
| `Warehouse_web/apps/documents/management/commands/cleanup_old_pdfs.py` | H3 | Новая management-команда |
| `Warehouse_web/apps/documents/models.py` | H3 | Проверить `RenderedDocumentArtifact` (оставить для аудита) |

## Out of scope

- Новые типы документов (только waybill)
- Редизайн шаблона (только фикс вёрстки и пагинации)
- ЭЦП / подписи
- Рендеринг на стороне SyncServer (остаётся в Django)
- Автоматический cron для очистки (команда готова, cron — infra)
- Миграции БД (если не требуются)

## Test Ladder

| Level | Применение |
|---|---|
| Static checks | ✅ ruff + mypy (SyncServer), Angular build |
| Unit tests | ✅ H1: test `update_operation` вызывает `DocumentService` |
| Component tests | ✅ H2: test `paginate_waybill_lines` с разными данными |
| Integration tests | ✅ H1: DB-backed — draft edit → waybill обновлён |
| Stand smoke tests | ✅ Dev-стенд: создать операцию → изменить → накладная → рендер |
| UI automation | ✅ Playwright: кнопка «Накладная» → PDF открывается |
| User scenarios | ✅ Кладовщик: черновик → изменить строки → накладная → печать |
| Regression pack | ✅ SyncServer 410+ tests, Django 325 tests |
| Acceptance review | ✅ Evidence table |

## Stand Requirements

- Docker dev-стенд: все сервисы
- Django admin: `admin`/`admin123`
- Данные: операция с 3+ строками ТМЦ (включая длинные названия) для теста пагинации
