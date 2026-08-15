// spike-fuel-report-typst@0.1.0 — monthly fuel report in Typst.
// Landscape A4 with vehicle grouping, per-vehicle subtotals, grand total.
// Reads the **full normalized envelope** from `document.json`
// (TZ-PHASE2-BACKEND-SPIKE §T5 / §11.2).
//
// Phase 2.1: envelope-level fields (``document_number``, ``template_id``,
// ``locale``, ``render_profile``) are accessible directly via
// ``doc.<field>`` — no warehouse-specific proxy is used. Inner
// document fields are read via ``doc.document.<field>``.

#set page(
  paper: "a4",
  // Landscape: swap dimensions.
  width: 297mm,
  height: 210mm,
  margin: 12mm,
  footer: context [
    #set text(size: 7pt, fill: luma(120))
    Лист #counter(page).display() из #counter(page).final().first()
  ],
)
#set text(font: "DejaVu Sans", lang: "ru", size: 9pt)

#let doc = json("document.json")
#let inner = doc.document

// Helper: format a number to a fixed N decimals.
#let fnum(value, n: 1) = {
  if value == none { return "" }
  let factor = calc.pow(10, n)
  let rounded = calc.round(value * factor) / factor
  let s = str(rounded)
  let dot = s.position(".")
  if dot == none {
    s + "," + "0" * n
  } else {
    let int-part = s.slice(0, dot)
    let dec-part = s.slice(dot + 1)
    let padded = if dec-part.len() >= n {
      dec-part.slice(0, n)
    } else {
      dec-part + "0" * (n - dec-part.len())
    }
    int-part + "," + padded
  }
}

// Helper: zero-padded month.
#let m2(m) = if m < 10 { "0" + str(m) } else { str(m) }

// --- Header -------------------------------------------------------------

#align(center)[
  #text(size: 14pt, weight: "bold")[ОТЧЁТ ПО РАСХОДУ ТОПЛИВА] \
  #text(size: 10pt)[за #m2(inner.period.month).#inner.period.year] \
  #text(size: 8pt, fill: luma(120))[№ #doc.at("document_number", default: "—")]
]

#align(center)[
  #text(size: 8pt, fill: luma(120))[
    Всего записей: #inner.rows.len(); Техника: #inner.vehicles.len() ед.
  ]
]

#v(0.4em)

// --- Summary grid -------------------------------------------------------

#let summary-cell(title, value) = block(
  stroke: 0.3pt + black,
  inset: 4pt,
  width: 100%,
)[
  #text(size: 7pt, fill: luma(120))[#title] \
  #text(size: 12pt, weight: "bold")[#value]
]

#grid(
  columns: (1fr, 1fr, 1fr),
  column-gutter: 6pt,
  summary-cell(
    [Общий объём топлива],
    [#fnum(inner.grand_total.total_volume_l, n: 2) л],
  ),
  summary-cell(
    [Общий пробег],
    [#fnum(inner.grand_total.total_distance_km, n: 1) км],
  ),
  summary-cell(
    [Общая стоимость],
    [#fnum(inner.grand_total.total_cost, n: 2) руб.],
  ),
)

#v(0.4em)

// --- Vehicle list -------------------------------------------------------

#text(size: 10pt, weight: "bold")[Список техники]

#set text(size: 8pt)
#table(
  columns: (auto, 1fr, auto, auto, auto),
  stroke: 0.3pt + black,
  fill: (col, row) => if row == 0 { luma(230) },
  inset: 2pt,
  align: (left, left, left, left, right),
  table.header(
    repeat: true,
    [*ID*], [*Наименование*], [*Гос. номер*], [*Ед. изм.*], [*Норма л/100км*],
  ),
  ..inner.vehicles.map(v => (
    [#v.id], [#v.name], [#v.plate], [#v.unit], [#fnum(v.norm_l_per_100km, n: 2)],
  )).flatten(),
)

#v(0.3em)

// --- Main data table ---------------------------------------------------

#text(size: 10pt, weight: "bold")[Записи]

#table(
  columns: (auto, auto, auto, 1fr, auto, auto, auto),
  stroke: 0.3pt + black,
  fill: (col, row) => if row == 0 { luma(230) },
  inset: 2pt,
  align: (left, left, left, left, right, right, right),
  table.header(
    repeat: true,
    [*№*], [*Дата*], [*Техника (ID)*], [*Вид топлива*],
    [*Объём, л*], [*Пробег, км*], [*Стоимость, руб*],
  ),
  ..inner.rows.enumerate().map(((idx, row)) => (
    [#idx + 1],
    [#row.date],
    [#row.vehicle_id],
    [#row.fuel_type],
    [#fnum(row.volume_l, n: 2)],
    [#fnum(row.distance_km, n: 1)],
    [#fnum(row.cost, n: 2)],
  )).flatten(),
)

#v(0.3em)

// --- Subtotals + grand total --------------------------------------------

#text(size: 10pt, weight: "bold")[Итоги по технике]

#table(
  columns: (1fr, auto, auto, auto),
  stroke: 0.3pt + black,
  inset: 3pt,
  align: (left, right, right, right),
  fill: (col, row) => {
    if row == 0 { luma(230) }
    else if row == inner.subtotals.len() + 1 { luma(200) }
    else { luma(245) }
  },
  table.header(
    repeat: true,
    [*Техника (ID)*], [*Объём, л*], [*Пробег, км*], [*Стоимость, руб*],
  ),
  ..inner.subtotals.map(s => (
    [#s.vehicle_id],
    [#fnum(s.total_volume_l, n: 2)],
    [#fnum(s.total_distance_km, n: 1)],
    [#fnum(s.total_cost, n: 2)],
  )).flatten(),
  [*ВСЕГО:*],
  [*#fnum(inner.grand_total.total_volume_l, n: 2)*],
  [*#fnum(inner.grand_total.total_distance_km, n: 1)*],
  [*#fnum(inner.grand_total.total_cost, n: 2)*],
)