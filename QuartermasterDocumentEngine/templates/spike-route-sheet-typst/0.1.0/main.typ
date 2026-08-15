// spike-route-sheet-typst@0.1.0 — vehicle route sheet in Typst.
// Honest same-form implementation of `spike-route-sheet-weasy@0.1.0`,
// expressed natively in Typst. Reads the **full normalized envelope**
// from `document.json` (TZ-PHASE2-BACKEND-SPIKE §T5 / §11.2).
//
// Phase 2.1: envelope-level fields (``document_number``, ``template_id``,
// ``locale``, ``render_profile``) are accessible directly via
// ``doc.<field>`` — no warehouse-specific proxy is used. Inner
// document fields are read via ``doc.document.<field>``.

#set page(
  paper: "a4",
  margin: 12mm,
  footer: context [
    #set text(size: 7pt, fill: luma(120))
    Лист #counter(page).display() из #counter(page).final().first()
  ],
)
#set text(font: "DejaVu Sans", lang: "ru", size: 9pt)

// Helper: format a number to a fixed N decimals (1 decimal by default).
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
    let padded = if dec-part.len() >= n { dec-part.slice(0, n) } else { dec-part + "0" * (n - dec-part.len()) }
    int-part + "," + padded
  }
}

#let doc = json("document.json")
#let inner = doc.document

#align(center)[
  #text(size: 13pt, weight: "bold")[ПУТЕВОЙ ЛИСТ] \
  #text(size: 9pt)[№ #doc.at("document_number", default: "—")] \
  Транспортное средство: #inner.vehicle.plate \
  Период: #inner.period.start_date — #inner.period.end_date
]

#v(0.4em)

// --- Vehicle + Driver boxes ---------------------------------------------

#grid(
  columns: (1fr, 1fr),
  column-gutter: 6pt,
  [
    #set text(size: 8pt)
    *Транспортное средство* \
    #line(length: 100%, stroke: 0.3pt + black) \
    #v(0.2em)
    #grid(
      columns: (auto, 1fr),
      column-gutter: 4pt,
      [Марка, модель:], [#inner.vehicle.make #inner.vehicle.model],
      [Гос. номер:], [#inner.vehicle.plate],
      [Гаражный №:], [#inner.vehicle.garage_number],
    )
  ],
  [
    #set text(size: 8pt)
    *Водитель* \
    #line(length: 100%, stroke: 0.3pt + black) \
    #v(0.2em)
    #grid(
      columns: (auto, 1fr),
      column-gutter: 4pt,
      [ФИО:], [#inner.driver.full_name],
      [Табельный №:], [#inner.driver.employee_id],
      [Класс:], [#inner.driver.class],
    )
  ],
)

#v(0.4em)

// --- Summary grid (odometer / fuel balance / fuel consumption) ----------

#let summary-cell(title, value) = block(
  stroke: 0.3pt + black,
  inset: 4pt,
  width: 100%,
)[
  #text(size: 7pt, fill: luma(120))[#title] \
  #text(size: 10pt, weight: "bold")[#value]
]

#let consumption-delta = inner.fuel_consumption.actual - inner.fuel_consumption.norm

#grid(
  columns: (1fr, 1fr, 1fr),
  column-gutter: 6pt,
  summary-cell(
    [Одометр (начало / конец)],
    [#fnum(inner.odometer.start, n: 1) / #fnum(inner.odometer.end, n: 1) км],
  ),
  summary-cell(
    [Остаток топлива (начало / конец)],
    [#fnum(inner.fuel_balance.start_l, n: 1) / #fnum(inner.fuel_balance.end_l, n: 1) л],
  ),
  summary-cell(
    [Получено топлива],
    [#fnum(inner.fuel_balance.received_total_l, n: 1) л],
  ),
)

#v(0.3em)

#grid(
  columns: (1fr, 1fr, 1fr),
  column-gutter: 6pt,
  summary-cell(
    [Расход по норме],
    [#fnum(inner.fuel_consumption.norm, n: 2) л],
  ),
  summary-cell(
    [Расход фактический],
    [#fnum(inner.fuel_consumption.actual, n: 2) л],
  ),
  summary-cell(
    [Отклонение],
    [#calc.abs(consumption-delta) л],
  ),
)

#v(0.4em)

// --- Trips table --------------------------------------------------------

#text(size: 10pt, weight: "bold")[Маршрутные записи]

#set text(size: 8pt)
#table(
  columns: (auto, auto, auto, 1fr, 1fr, 1fr, auto, auto),
  stroke: 0.3pt + black,
  fill: (col, row) => if row == 0 { luma(230) },
  inset: 2pt,
  align: (left, left, left, left, left, left, right, right),
  table.header(
    repeat: true,
    [*№*], [*Выезд*], [*Возврат*], [*Откуда*], [*Куда*], [*Цель*], [*км*], [*мин*],
  ),
  ..inner.trips.enumerate().map(((idx, trip)) => (
    [#idx + 1],
    [#trip.departure_at],
    [#trip.return_at],
    [#trip.origin],
    [#trip.destination],
    [#trip.purpose],
    [#fnum(trip.distance_km, n: 1)],
    [#trip.duration_min],
  )).flatten(),
)

#v(0.3em)

// --- Refuels table ------------------------------------------------------

#text(size: 10pt, weight: "bold")[Заправки]

#table(
  columns: (auto, auto, 1fr, 1fr, auto, auto),
  stroke: 0.3pt + black,
  fill: (col, row) => if row == 0 { luma(230) },
  inset: 2pt,
  align: (left, left, left, left, right, right),
  table.header(
    repeat: true,
    [*№*], [*Дата*], [*АЗС*], [*Топливо*], [*Объём, л*], [*Сумма*],
  ),
  ..inner.refuels.enumerate().map(((idx, r)) => (
    [#idx + 1],
    [#r.refueled_at],
    [#r.station],
    [#r.fuel_type],
    [#fnum(r.volume_l, n: 1)],
    [#fnum(r.cost, n: 2)],
  )).flatten(),
)

#v(0.3em)

// --- Signers ------------------------------------------------------------

#text(size: 10pt, weight: "bold")[Подписи]

#let placeholder = "_____________________________"
#let placeholder-meta = "_____________________"
#grid(
  columns: (1fr, 1fr, 1fr),
  column-gutter: 6pt,
  ..(("driver", "mechanic", "dispatcher",)).map(role => {
    let s = inner.signers.at(role)
    block(
      stroke: 0.3pt + black,
      inset: 4pt,
      width: 100%,
    )[
      #set text(size: 8pt)
      #text(weight: "bold")[#s.label] \
      #v(0.6em)
      #line(length: 100%, stroke: 0.3pt + black) \
      #v(-0.2em)
      #if s.name == "" or s.name == none [
        #text(size: 7pt, fill: luma(150))[#placeholder]
      ] else [
        #text(size: 8pt)[#s.name]
      ] \
      #v(0.2em)
      #if s.signed_at == "" or s.signed_at == none [
        #text(size: 7pt, fill: luma(150))[#placeholder-meta]
      ] else [
        #text(size: 7pt)[#s.signed_at]
      ]
    ]
  })
)