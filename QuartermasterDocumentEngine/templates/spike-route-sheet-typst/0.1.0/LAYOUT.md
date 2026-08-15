# Layout — spike-route-sheet-typst@0.1.0

## Goal
Typst variant of the vehicle route sheet. Same logical layout as
`spike-route-sheet-weasy@0.1.0`, expressed natively in Typst.

## Page
- size: A4 portrait
- margin: 12mm on all sides

## Header
Centered title «ПУТЕВОЙ ЛИСТ», followed by vehicle plate and period range.

## Body
1. **Vehicle + Driver side-by-side boxes**: make/model/plate/garage + driver
   name/employee_id/class
2. **Summary grid** (2 rows × 3 cols):
   - odometer start/end (km)
   - fuel balance start/end (л)
   - fuel received total (л)
   - consumption norm / actual / deviation (л)
3. **Trips table** (50 rows): № / Выезд / Возврат / Откуда / Куда / Цель /
   км / мин. `table.header(repeat: true)`.
4. **Refuels table** (10 rows): № / Дата / АЗС / Топливо / Объём / Сумма.
5. **Signers block**: 3 columns (Водитель / Механик / Диспетчер), each with
   label, name (or «_____________________________» placeholder), signed_at
   timestamp (or blank line).

## Footer
«Лист N из M» using `counter(page)` and final page count.

## Notes
- Reads `let doc = json("document.json")` — Typst backend writes the inner
  document mapping (not the envelope) to disk.
- thead repeats via `#table.header(repeat: true, ...)`.
- The page-count is captured via a `context` block at top-level so the
  footer can reference the final count without a runtime error.
