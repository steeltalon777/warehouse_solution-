# Layout — spike-fuel-report-typst@0.1.0

## Goal
Typst variant of the monthly fuel report. Same logical layout as
`spike-fuel-report-weasy@0.1.0`, expressed natively in Typst. Landscape A4.

## Page
- size: A4 landscape (width 297mm × height 210mm — Typst swaps dimensions)
- margin: 12mm on all sides

## Header
Centered title «ОТЧЁТ ПО РАСХОДУ ТОПЛИВА ЗА MM.YYYY», followed by row and
vehicle counts.

## Body
1. **Summary grid** (3 cells): total volume, total distance, total cost from
   `grand_total`.
2. **Vehicle list** (10 rows): ID / Наименование / Гос. номер / Ед. изм. /
   Норма л/100км. `table.header(repeat: true)`.
3. **Main rows table** (100/500/1500 rows): № / Дата / Техника (ID) / Вид
   топлива / Объём, л / Пробег, км / Стоимость, руб.
   `table.header(repeat: true)`.
4. **Subtotals + grand total table**: one row per `subtotals` vehicle plus a
   final bold grand-total row.

## Footer
«Лист N из M» using `counter(page)` and final page count.

## Notes
- Reads `let doc = json("document.json")` — Typst backend writes the inner
  document mapping (not the envelope) to disk.
- `fnum(value, n: N)` is a local helper that mimics Python's `%.Nf` formatting
  (Typst 0.15.1 has no built-in printf-style formatter). Outputs Russian
  decimal comma.
- `m2(m)` zero-pads a month integer to 2 digits.
