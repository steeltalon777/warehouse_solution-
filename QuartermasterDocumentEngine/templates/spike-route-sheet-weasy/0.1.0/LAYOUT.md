# spike-route-sheet-weasy@0.1.0 — Transport vehicle route sheet (Jinja2 + WeasyPrint).

Same-form implementation of the route sheet used for the Phase 2 backend
spike (TZ-PHASE2-BACKEND-SPIKE §T7). Uses the engine's bundled DejaVu
Sans fonts.

The template supports the engine-level copies banner (TZ §T8): the
engine injects `copy_number` and `copies_total` into the document
context and the template prints "Экземпляр N из M" when copies_total > 1.
With `copies_total <= 1` (or the field absent) no banner is rendered,
keeping the copies=1 path byte-identical to Phase 1.

## Layout (T7 spec)

- A4 portrait, margins 16/14/14 mm.
- Header: "ПУТЕВОЙ ЛИСТ" centered, document number and period below.
- Header block: vehicle (make / model / plate / garage number) and
  driver (full name / employee id / class).
- Trips table: 50 rows, columns: № / departure_at / return_at / origin
  / destination / purpose / distance_km / duration_min. `thead` repeats
  on page break; `tr` uses `page-break-inside: avoid`.
- Footer: "Лист N из M" at bottom-center.
- Signatures: 3 columns (водитель / механик / диспетчер).

## Capabilities

- qr, barcode, image, watermark, copies, landscape, multi-page-table,
  fixed-form.

## Fonts

Uses `qm_engine.fonts` bundled DejaVu Sans (Regular / Bold / Oblique /
BoldOblique). Manifest declares the four files; missing files trigger
`FONT_NOT_AVAILABLE` (exit 4) before render.
