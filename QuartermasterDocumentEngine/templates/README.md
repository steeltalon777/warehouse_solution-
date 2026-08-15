# Templates

This directory contains installed template packages for the Quartermaster
Document Engine. Each package is a subdirectory named `<template_id>/<version>/`
with three files:

- `manifest.yaml` — engine metadata (contract, backend, entrypoint, …).
- `main.html` / `main.typ` — the entrypoint (Jinja2 + HTML or Typst).
- `LAYOUT.md` — plain-text layout spec shared between paired backends.

## Baseline (Phase 1, immutable)

| Template id | Version | Backend | Contract |
|---|---|---|---|
| `warehouse-waybill-ru` | `0.1.0` | weasyprint | `warehouse.operation-document/v2` |
| `warehouse-waybill-ru` | `1.0`   | weasyprint | `warehouse.operation-document/v2` |

These are the Phase 1 baseline templates — they are **immutable** per
`TZ-PHASE2-BACKEND-SPIKE.md §5`. No edits, no new versions of the same id.

## Spike packages (Phase 2, T7)

| Template id | Version | Backend | Contract | Form |
|---|---|---|---|---|
| `spike-waybill-typst`    | `0.1.0` | typst     | `warehouse.operation-document/v2`  | Multi-page waybill (MOVE-style) |
| `spike-route-sheet-weasy` | `0.1.0` | weasyprint | `transport.vehicle-route-sheet/v1` | Strict 1–2 page route sheet |
| `spike-route-sheet-typst` | `0.1.0` | typst     | `transport.vehicle-route-sheet/v1` | Same form, Typst |
| `spike-fuel-report-weasy` | `0.1.0` | weasyprint | `fuel.monthly-report/v1`           | Landscape A4 monthly report |
| `spike-fuel-report-typst` | `0.1.0` | typst     | `fuel.monthly-report/v1`           | Same report, Typst |

These five packages form the Phase 2 backend spike — the same logical form
implemented independently in each backend so the rendering engines can be
compared on identical inputs (`tests/fixtures/`).

## LAYOUT.md convention

For each pair (weasy+typst), the two packages share a single textual
specification, stored once per package as `LAYOUT.md` (self-contained copy).
The spec describes the form in plain text:

- Goal (one-sentence description)
- Page (size, margin)
- Header (textual description)
- Body (tables, columns, repeat behaviour)
- Footer (counter, etc.)
- Signatures / Signers
- Notes (font, placeholders, layout quirks)

This is the "common spec" both backends implement — even though the
WeasyPrint and Typst versions render via different mechanisms.

## Adding a new template

1. Pick a `template_id` (kebab-case, e.g. `my-template`).
2. Pick a `version` (SemVer: `X.Y` or `X.Y.Z`).
3. Choose a backend (`weasyprint` or `typst`) and pick a document contract
   (or define a new one in `contracts/<name>/<version>/schema.json`).
4. Create `templates/<id>/<version>/manifest.yaml` with all required fields
   (see `INVESTIGATION.md` §7 for the capabilities dictionary).
5. Write the entrypoint (`main.html` for WeasyPrint, `main.typ` for Typst).
6. Optionally write `LAYOUT.md` describing the form.
7. Validate with `qm-render inspect-template --template <id> --version <v>`.
8. Add fixtures under `tests/fixtures/<doctype>/` and tests under
   `tests/component/test_<name>.py`.
