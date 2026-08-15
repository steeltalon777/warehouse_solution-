# Layout — spike-fuel-report-weasy@0.1.0

## Goal
Monthly fuel consumption report — landscape A4 with vehicle grouping,
per-vehicle subtotals, and grand total. Forms the comparison partner to
`spike-fuel-report-typst@0.1.0`.

## Page
- size: A4 landscape
- margin: 12mm on all sides

## Header
Centered title «ОТЧЁТ ПО РАСХОДУ ТОПЛИВА ЗА MM.YYYY», followed by row and
vehicle counts.

## Body
Summary grid (3 cells):
- Total volume (л) from `grand_total.total_volume_l`
- Total distance (км) from `grand_total.total_distance_km`
- Total cost (руб) from `grand_total.total_cost`

One main data table (7 columns):
№ / Дата / Техника (ID) / Вид топлива / Объём, л / Пробег, км / Стоимость, руб

`thead` repeats on each page; rows are flow-broken across pages.

After the row block, a `<tfoot>` with one subtotal row per vehicle
(`document.subtotals`) plus a final grand total row.

## Footer
«Лист N из M» using CSS counter(pages).

## Notes
- No image / QR / barcode requirements for this spike — `assets: []`.
- Designed for 100/500/1500 rows; subtotals + grand total always appear
  on the last page.
