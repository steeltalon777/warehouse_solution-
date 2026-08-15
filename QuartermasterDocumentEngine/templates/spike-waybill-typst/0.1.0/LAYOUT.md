# Layout — spike-waybill-typst@0.1.0

## Goal
Honest Typst implementation of the warehouse operation waybill — the same
logical layout as `warehouse-waybill-ru@1.0`, expressed natively in Typst.

## Page
- size: A4 portrait
- margin: 12mm on all four sides (Phase 2.1: reduced from 16/14/14/14 for density parity with WeasyPrint)

## Header
Centered title «ТОВАРНАЯ НАКЛАДНАЯ», followed by document number (envelope-level
`document_number`, with a fallback to `inner.operation.display_number` only when
the envelope field is missing — TZ-PHASE2-BACKEND-SPIKE §T5 / §11.2) and
effective date (`inner.operation.effective_at`).

A bordered block contains three labelled rows:
- Отправитель: legal_name (or site_name) of `inner.source_site`.
- Получатель: legal_name (or site_name) of `inner.destination_site`.
- Основание: `inner.basis.label`.

## Body
Eight-column table, thead repeats on each page:
№ / Наименование / Артикул / Кол-во / Ед. / Категория / Партия / Примечание.
Empty SKU → «—»; missing batch or comment → «—».

Below the table: «Всего наименований: <total_lines>» (from `inner.total_lines`).

## Footer
«Лист N из M» using `counter(page)` and the final page count.

## Signatures
MOVE-style 4-cell grid:
- Сдал / Принял
- Главный бухгалтер / Дата (M.П.)

Each cell has a label, a name (or hand-fill underscores), and an underline.

## Density (Phase 2.1 hardening)
Body text 9pt, table 8pt, table inset 2pt, leading 0.55em. On
waybill-500 the template now renders ≈42 pages vs WeasyPrint's 18 (ratio
≈2.3×), down from the previous 124-page output (ratio ≈6.9×).

## Notes
- Reads `let doc = json("document.json")` — Typst backend writes the **full
  normalized envelope** (top-level fields + inner `document` mapping) to disk
  (TZ-PHASE2-BACKEND-SPIKE §T5 / §11.2). Envelope-level fields
  (``document_number``, ``template_id``, ``locale``, ``render_profile``)
  are accessed directly via ``doc.<field>``; inner document fields via
  ``doc.document.<field>``.
- Page count uses Typst's `counter(page).final().first()` via context.
- Thead repeats via `#table.header(repeat: true, ...)`.