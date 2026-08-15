# Fonts — Phase 2 (T4) status

Bundled pinned fonts for the Quartermaster Document Engine.

## What is here

- 4 DejaVu Sans TTF files (Regular, Bold, Oblique, BoldOblique).
- `manifest.json` — machine-readable manifest with SHA-256 of each file.
- `LICENSE` — verbatim DejaVu license (Bitstream Vera + Arev + DejaVu
  public-domain additions).

## Source

System package `fonts-dejavu-core` (Debian/Ubuntu) installed at
`/usr/share/fonts/truetype/dejavu/`. Files were copied into this bundle
and their SHA-256 hashes recorded in `manifest.json`. Upstream project:
https://dejavu-fonts.github.io/ (DejaVu fonts 2.37).

## Why Cyrillic

DejaVu Sans is the only family that is already used by all three
Quartermaster pipelines (SyncServer, Warehouse_web/Django, Engine Phase 1).
A bundled DejaVu that guarantees Cyrillic glyphs removes the silent
fallback hazard and makes PDF renders reproducible across machines
(ADR-0001 D9).

## Phase 2 spike usage

- The engine loads `manifest.json` via `qm_engine.fonts.load_manifest()`.
- `qm_engine.fonts.verify_manifest()` checks that every file is present
  and matches its SHA-256. Any mismatch raises `FontNotAvailableError`
  (exit code 4, code `FONT_NOT_AVAILABLE`).
- The WeasyPrint backend calls `qm_engine.fonts.ensure_bundled_fonts()`
  at the very start of `render()`. It then builds a `FontConfiguration`
  and passes an inline `@font-face` stylesheet to `write_pdf()` so the
  engine does not pick up system fonts.
- The Typst backend (T6) will reuse the same manifest via
  `typst compile --font-path <bundle>/fonts`.

## Reference

- TZ: `doc/TZ-PHASE2-BACKEND-SPIKE.md` §12 (fonts/assets policy).
- TZ: `doc/TZ-PHASE2-BACKEND-SPIKE.md` §8 T4 (bundled pinned fonts).
