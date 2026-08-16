// warehouse-waybill-ru@2.0.0 — declarative signature renderer.
//
// One generic primitive (render_signature_block) renders ANY
// signature block from the declarative configuration in
// layout-config.typ. The number of blocks, their order, labels and
// grid layout are configuration, not code: changing 4 -> 6 blocks
// requires editing layout-config.typ only.
//
// Block shape (from layout-config.typ operation-signature-sets):
//   (key, label, position-label: str?, signature-label:
//    str?, driver)
//
// * driver: true  -> label line + single placeholder line
//                    (legacy "Водитель" block);
// * otherwise      -> label line + hint/placeholder line
//                    "(position) ____ (signature) ____/____"
//                    (legacy standard blocks).
//
// The storekeeper line (storekeeper-label + placeholder) is rendered
// on EVERY page (short form) and is also the first line of the full
// signature section on the last page.

// ---------------------------------------------------------------------------
// Shared pieces
// ---------------------------------------------------------------------------

#let render_placeholder(config) = [
  #text(tracking: 0.2pt)[#config.signature-placeholder]
]

#let render_storekeeper_line(config) = [
  #text(weight: "bold")[#config.storekeeper-label:]
  #h(3mm)
  #render_placeholder(config)
]

// ---------------------------------------------------------------------------
// Per-block primitives
// ---------------------------------------------------------------------------

#let render_standard_block(sig, config) = [
  #text(weight: "bold")[#sig.label:]
  \
  #h(1.5mm)
  #text(
    size: config.typography.hint-size,
    fill: config.typography.hint-color,
  )[(#sig.at("position-label", default: ""))]
  #h(3mm)
  #text(tracking: 0.2pt, "_________________")
  #h(3mm)
  #text(
    size: config.typography.hint-size,
    fill: config.typography.hint-color,
  )[(#sig.at("signature-label", default: ""))]
  #h(3mm)
  #render_placeholder(config)
]

#let render_driver_block(sig, config) = [
  #text(weight: "bold")[#sig.label:]
  \
  #h(1.5mm)
  #render_placeholder(config)
]

#let render_signature_block(sig, config) = {
  if sig.at("driver", default: false) {
    render_driver_block(sig, config)
  } else {
    render_standard_block(sig, config)
  }
}

// ---------------------------------------------------------------------------
// Section: storekeeper on every page, full form on the last page
// ---------------------------------------------------------------------------

#let render_signature_section(is_last, config, blocks) = {
  if is_last {
    // Full form: storekeeper + declarative blocks in the configured
    // grid (row-major flow, incomplete final row allowed).
    block(breakable: false)[
      #v(8mm)
      #render_storekeeper_line(config)
      #if blocks.len() > 0 [
        #v(4mm)
        #grid(
          columns: config.signature-grid.columns,
          column-gutter: config.signature-grid.gap-x,
          row-gutter: config.signature-grid.gap-y,
          ..blocks.map(b => render_signature_block(b, config)),
        )
      ]
    ]
  } else {
    // Short form on first/middle pages.
    block(breakable: false)[
      #v(8mm)
      #render_storekeeper_line(config)
    ]
  }
}
