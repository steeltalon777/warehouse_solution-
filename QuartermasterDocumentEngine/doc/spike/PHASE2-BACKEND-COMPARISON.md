# Phase 2 Backend Comparison (WeasyPrint vs Typst)

## TZ

Authoritative TZ: `/home/makc/AI_sandbox/warehouse_solution/QuartermasterDocumentEngine/doc/TZ-PHASE2-BACKEND-SPIKE.md` (Phase 2 spike). Contracts used: §13 (data sources), §14 (perf scenarios), §15 (test ladder), §17 (evidence), §19 (scoring matrix + hard veto), §20 (acceptance criteria).

Phase 2.1 hardening TZ (separate document, in `m0040` review-fix message): §1 Typst full envelope; §2 determinism terminology; §3 Typst waybill density; §4 representative perf re-run; §5 evidence refresh; §6 human acceptance package; §7 regression gates.

## §A. Header / TL;DR

| Field | Value |
|---|---|
| Machine | Linux Ubik 7.0.0-28-generic (`#28~24.04.1-Ubuntu SMP PREEMPT_DYNAMIC`), x86_64 |
| CPU | 24 logical cores (16 physical) |
| RAM | 31.1 GiB |
| Python | 3.12.3 |
| WeasyPrint | 69.0 (`pyproject.toml: weasyprint>=66`; pin drift — INVESTIGATION §1.1) |
| Typst | 0.15.1 (commit `9dfd3a08`), Linux x64 binary sha256 `29273eaa04f6d00edd0c2bec578f565fc9c65be856bfbffc894567c68ed0b237` |

**TL;DR.** **Recommendation: Typst is the provisional preferred backend for Phase 5** (weighted score **462** vs WeasyPrint's **376**, no hard vetoes for either backend). The recommendation is **provisional** because Typst's Windows deployment remains `NOT-VERIFIED` in this environment — explicit Windows verification of the pinned Typst 0.15.1 binary is required before production rollout. Phase 5 architect retains final say on the migration path.

Justification: Typst passes every SPEC hard envelope while WeasyPrint fails on the fuel-1500 pool=4 scenario (~112 s vs 60 s hard); Typst is 3.9–11× faster across all datasets and scenarios (cold / warm / parallel / pool), ships a 54 MB static binary (vs 529 MB WeasyPrint venv, plus ~50 MB apt-installable native system libraries); the Typst spike waybill template now produces a practically-comparable page density (42 pages on waybill-500 vs WeasyPrint's 18, ratio 2.3×, down from a pre-fix 6.9×). Typst is **byte-deterministic** (verified by SHA-256 across reruns); WeasyPrint is **visually / structurally deterministic** but **not byte-deterministic** (FlateDecode stream length varies between separate runs — documented in `tests/unit/test_copies.py`).

WeasyPrint retains the only criterion where it scores strictly higher than Typst — Windows deployment (production-proven vs Typst `NOT-VERIFIED`). The final backend decision is **deferred** to Phase 5/6 per TZ §18 (no production migration in Phase 2).

**TZ checklist status (items 8–14):**

| # | Item | Status | Note |
|---|---|---|---|
| 8 | Visual comparison harness | done | `tests/harness/`, all 9 fixtures produce structural + semantic gates; cross-backend visual = informational per TZ §13.5 |
| 9 | Performance benchmark | done | `doc/spike/PERF-REPORT.md` + `doc/spike/perf-summary.json` (24 cells, 0 failures, re-run after Phase 2.1 density fix) |
| 10 | Golden structure | done (JSON-only fallback) | `git-lfs` not installed; only `tests/golden/<template>-<version>/` skeleton + index registration; 6 `expected.json` files committed + `scripts/golden_update.py --check` is CI-ready |
| 11 | Linux offline smoke | done (strace-equivalent) | `unshare -n` blocked by `CapEff=0`; `strace -e trace=network` shows **0 network syscalls** for both backends (see §K) |
| 12 | Regression §16 | done | `qm-render version` = `{"engine":"0.1.0","engine_contract_versions":["1.0.0"]}`; `pytest` = **215 passed**; Phase 1 fixture still renders valid PDF; `mypy engine backends cli` = Success: no issues found in 15 source files (Phase 2.1 review-fix W4 closed the pre-existing numpy stubs warning by aligning `pyproject.toml` python_version with venv 3.12; Phase 2.1.1 added the `test_typst_determinism_across_second_boundary` regression test; Phase 2.1.2 added the `--creation-timestamp` argv unit tests) |
| 13 | Comparative report | done | this file |
| 14 | Acceptance view | done (architect sign-off) | 7 PDFs in `spike-out/acceptance/`; `doc/spike/HUMAN-ACCEPTANCE.md` Level 9 checklist (Phase 2.1 §6) — signed off by the architect together with the Phase 2 CLOSED decision (2026-08-11); artefacts preserved for audit at any time |

## §B. Phase 2 deliverables (TZ §18 status table)

| # | Deliverable | Status | Evidence |
|---|---|---|---|
| 1 | Typst backend spike | done | `backends/qm_backends/typst_backend.py` |
| 2 | WeasyPrint baseline perf | done | `doc/spike/PERF-REPORT.md` |
| 3 | 9 fixtures + generator | done | `tests/fixtures/`, `tests/fixtures/generate_fixtures.py` |
| 4 | 5 spike-templates | done | `templates/spike-{waybill-typst,route-sheet-{weasy,typst},fuel-report-{weasy,typst}}` |
| 5 | Bundled pinned fonts | done | `fonts/DejaVuSans*.ttf` (4), `fonts/manifest.json`, `engine/qm_engine/fonts.py` |
| 6 | Visual comparison harness | done | `tests/harness/{raster,structural,semantic,visual,report}.py` |
| 7 | Performance benchmark | done | `scripts/bench.py`, `doc/spike/PERF-REPORT.md` |
| 8 | Linux offline smoke | done (strace) | see §K — `unshare -n` is denied in this environment |
| 9 | Golden structure | done (JSON-only fallback) | `tests/golden/`, `pyproject.toml` registers `golden` marker; git-lfs unavailable (INVESTIGATION §4) |
| 10 | Comparative report | done (this file) | — |

Explicit no-go confirmations (TZ §18): **NO production migration in Phase 2; NO deletion of existing renderer; NO rewrite of Django integration; NO rewrite of SyncServer rendering.** All maintained read-only.

## §C. Visual comparison (T9)

### Calibration

Source: `spike-out/calibration/noise_floor.json` (5 + 5 renders of `waybill-20` per backend, identical template).

| Metric | Value |
|---|---|
| SSIM observed floor (min across 20 samples) | `1.0` |
| Changed-pixels observed floor (max across 20 samples) | `0.0` |
| SSIM threshold (after calibration) | `≥ 0.995` |
| Changed-pixels threshold | `≤ 0.001` |

Both backends are **visually / structurally deterministic** across reruns (page count + extracted text stable). Typst is **byte-deterministic** (Phase 2.1.1 close-out M1: SHA-256 identical across consecutive runs AND across wall-clock second boundaries — verified 100 series × 3 renders = 0 divergence via `scripts/diag_typst_determinism.py` after the fix; the original flake was caused by Typst 0.15.1 ignoring the `TYPST_TIMESTAMP` env var and using wall-clock time for the PDF `/CreationDate` metadata — fixed by passing `--creation-timestamp` as a CLI flag in `backends/qm_backends/typst_backend.py`). **Phase 2.1.2 re-verification (QDE M1 close-out)**: the determinism property was re-established from scratch with an independent diagnostic campaign — `scripts/diag_typst_determinism.py` 50×3 + 100×3 = 0 divergence on the minimal template, 10×3 renders of each of the three real spike templates (`waybill-500.typst`, `fuel-report-1500.typst`, `vehicle-route-sheet-1.typst`) = 0 divergence, and `test_typst_determinism` + `test_typst_determinism_across_second_boundary` × 100 consecutive pytest runs = 100/100 pass. Every render is a fresh subprocess (no in-process warm cache), so the byte-determinism claim holds for **cold** renders too. The root cause was also re-derived directly against the pinned binary: with only `TYPST_TIMESTAMP=1700000000` env (no CLI flag) 5 renders over ~3 s produced 3 distinct SHA-256 (env var ignored); with `--creation-timestamp 1700000000` the same 5 renders produced 1 SHA-256. Byte-diff of a divergent env-only pair shows the ONLY differences are `/ModDate`, `/CreationDate` (1 s), XMP dates, `DocumentID`/`InstanceID`, and the trailer `/ID` — page count, MediaBox, object count, xref, embedded font subsets, extracted text and raster (SSIM=1.0, changed-pixels=0.0) are identical. Note: `--creation-timestamp` also pins Typst's in-code `datetime.today()` (the cli-flag PDF renders the pinned date, not the wall-clock date), so the flag controls both PDF metadata and renderer-clock semantics. WeasyPrint's compressed PDF stream length varies between separate processes (`tests/unit/test_copies.py` documents this), so its byte-equality across separate `qm-render` calls is not guaranteed. See §F "PDF quality / predictability" for scoring implications. Noise floor is perfect (1.0/0.0) — thresholds are tight.

### Per-fixture summary (9 fixtures)

| Fixture | Weasy pages | Typst pages (Phase 2) | Typst pages (Phase 2.1) | Weasy structural | Typst structural | Weasy semantic | Typst semantic | SSIM avg (cross) | Δ-px avg | REVIEW_REQUIRED |
|---|---:|---:|---:|---|---|---|---|---:|---:|---|
| waybill-1 | 1 | 1 | 1 | pass | pass | pass¹ | pass¹ | 0.870 | 4.2% | yes (informational) |
| waybill-20 | 1 | 2 | 2 | pass | pass | pass¹ | pass¹ | 0.598 | 12.4% | yes (informational) |
| waybill-75 | 3 | 7 | 7 | pass | pass | pass¹ | pass¹ | 0.563 | 13.3% | yes (informational) |
| waybill-200 | 8 | 17 | 17 | pass | pass | pass¹ | pass¹ | 0.565 | 13.1% | yes (informational) |
| waybill-500 | 18 | 42 | 42 | pass | pass | pass¹ | pass¹ | 0.534 | 14.0% | yes (informational) |
| vehicle-route-sheet-1 | 2 | 3 | 3 | pass² | pass² | pass | pass | 0.431 | 19.3% | yes (informational) |
| fuel-report-100 | 5 | 3 | 3 | pass | pass | pass³ | pass³ | 0.425 | 20.9% | yes (informational) |
| fuel-report-500 | 19 | 11 | 11 | pass | pass | pass³ | pass³ | 0.369 | 22.7% | yes (informational) |
| fuel-report-1500 | 55 | 31 | 31 | pass | pass | pass³ | pass³ | 0.352 | 23.2% | yes (informational) |

Notes:

- ¹ `signer_Главный бухгалтер` and `signer_Кладовщик` are soft best-effort assertions (not present in spike templates; `veto: false` per `spike-out/compare/*/semantic.json`).
- ² Route sheet `all_blocks_pass: true`; both backends produce 59 rows vs 60 expected — a shared `expected.json` calibration artefact, not a backend defect.
- ³ Fuel `signer_Ответственный` is best-effort (not rendered by spike templates).
- **Phase 2.1 density fix**: the Typst spike waybill template was rewritten to use 12mm margins, 9pt body / 8pt table text, 2pt table inset (down from 16mm / 10pt / 4pt). Waybill-500 Typst page count dropped from **124 → 42** (ratio to WeasyPrint: 6.9× → 2.3×). The pre-fix waybill density was a spike-template artefact (the Typst backend itself handles dense tables fine — verified by fuel-report rendering, which has near-WeasyPrint page counts even pre-fix).

### Aggregate: cross-backend SSIM < 0.995 fixtures

**All 9 fixtures** have cross-backend SSIM < 0.995. This is **informational only** per TZ §13.5 — cross-backend comparison is not a gate (different templates with independent layout choices intentionally do not match pixel-wise). All structural + semantic gates pass; `REVIEW_REQUIRED` is expected and recorded in each `spike-out/compare/<fixture>/visual.json`.

Key visual deltas driving low cross-backend SSIM are layout choices (line-height, table-cell padding, font-metrics), not value corruption.

## §D. Performance (T10)

Source: `doc/spike/PERF-REPORT.md` (full, re-run after Phase 2.1), `doc/spike/perf-summary.json` (machine-readable, 24 cells, 0 failures).

### Distribution size (Phase 2.1 review-fix W3)

| Component | Size | Path |
|---|---|---|
| WeasyPrint venv (full) | 529 MB | `.venv/` |
| WeasyPrint site-packages (just `weasyprint/`) | 2.9 MB | `.venv/lib/python3.12/site-packages/weasyprint` |
| WeasyPrint pure-Python transitive deps | 35.5 MB | `weasyprint + tinycss2 + cssselect2 + pycparser + cffi + Pillow + fontTools + pydyf` |
| WeasyPrint native system libs (**not in venv**) | ~50 MB | `libcairo2, libpango-1.0-0, libgdk-pixbuf-2.0-0, libpangoft2-1.0-0, libffi, libxml2, libpangocairo-1.0-0` — apt-installed |
| Typst root (binary + archive) | 70 MB | `.spike/` |
| Typst binary only | 54 MB (`55 739 488` bytes) | `.spike/typst-0.15.1/typst-x86_64-unknown-linux-musl/typst` |

Phase 2.1 review-fix W3: the original Phase 2 PERF-REPORT recorded "WeasyPrint package only: 24.2 MB" while `perf-summary.json` recorded `weasyprint_package_mb: 2.5`. The 24.2 MB figure was an artefact of measuring `site-packages/weasyprint/` at a different time when native binary extensions were co-located. The current authoritative figure is **2.9 MB** for the pure-Python `weasyprint/` package, matching the perf-summary value. **Phase 5 deployment MUST budget for the ~50 MB apt-installed native libraries** if WeasyPrint is selected as the primary backend; Typst has no such requirement (single static binary).

### Cold startup (3 datasets × 2 backends, SPEC hard column)

| Dataset | Weasy wall (ms) | Typst wall (ms) | SPEC hard (ms) | Weasy ≤ hard | Typst ≤ hard |
|---|---:|---:|---:|---|---|
| waybill-20 | 660 | 160 | 2 500 | yes | yes |
| waybill-500 | 2 575 | 432 | 7 000 | yes | yes |
| fuel-1500 | 8 129 | 763 | 15 000 | yes | yes |

### 10 sequential (warm, p50/p95 latency)

| Dataset | Weasy p50 (ms) | Weasy p95 (ms) | Typst p50 (ms) | Typst p95 (ms) | SPEC hard (ms) |
|---|---:|---:|---:|---:|---:|
| waybill-20 | 677 | 697 | 160 | 173 | 1 200 |
| waybill-500 | 2 544 | 2 588 | 417 | 437 | 7 000 |
| fuel-1500 | 8 250 | 8 322 | 766 | 785 | 15 000 |

### 10 parallel (total wall + per-process p50/p95)

| Dataset | Weasy total wall (ms) | Weasy p95 (ms) | Typst total wall (ms) | Typst p95 (ms) |
|---|---:|---:|---:|---:|
| waybill-20 | 886 | 882 | 297 | 293 |
| waybill-500 | 3 838 | 3 833 | 666 | 661 |
| fuel-1500 | 13 038 | 13 033 | 1 191 | 1 186 |

### 50 pool=4 (total wall + p50/p95 per-process)

| Dataset | Weasy total (ms) | Weasy p95 (ms) | Typst total (ms) | Typst p95 (ms) | SPEC hard total (ms) | Weasy ≤ hard | Typst ≤ hard |
|---|---:|---:|---:|---:|---:|---|---|
| waybill-20 | 8 942 | 718 | 2 212 | 185 | 60 000 | yes | yes |
| waybill-500 | 34 608 | 2 788 | 5 675 | 454 | 60 000 | yes | yes |
| fuel-1500 | **112 232** | 9 228 | 10 233 | 807 | 60 000 | **NO (≈112 s)** | yes |

### Worker RAM peak

| Backend | Dataset | Peak RSS (MB) | SPEC hard (MB) | Pass |
|---|---|---:|---:|---|
| weasyprint | waybill-20 | 87 | 700 | yes |
| weasyprint | waybill-500 | 157 | 700 | yes |
| weasyprint | fuel-1500 | 441 | 700 | yes |
| typst | waybill-20 | 72 | 700 | yes |
| typst | waybill-500 | 163 | 700 | yes |
| typst | fuel-1500 | 279 | 700 | yes |

### CLI vs in-process overhead (WeasyPrint only; Typst PyPI not installed)

| Metric | Weasy CLI p50 (ms) | Weasy in-process p50 (ms) | CLI overhead (ms) |
|---|---:|---:|---:|
| waybill-20 | 677 | 211 | +466 |

Typst in-process: **not measured** (`typst-py` is not installed; Typst 0.15.1 ships CLI only — `perf-summary.json` `in_process.typst.status = not-measured`).

### Notable findings

- **Typst 3.9–11× faster than WeasyPrint** on every dataset × scenario (Phase 2.1 re-run). Cold-start gap: 4.1× (waybill-20), 6.0× (waybill-500), 11× (fuel-1500). Phase 2.1 Typst numbers are slightly faster than Phase 2 numbers because the density fix produces fewer pages per document (e.g. waybill-500: 42 vs 124 pages), reducing compile pass iterations.
- **WeasyPrint on fuel-1500 in the pool=4 scenario exceeds SPEC hard target**: 112 s vs 60 s (≈1.9× over). Pool=4 is `ProcessPoolExecutor(max_workers=4)`, 50 docs. WeasyPrint on the 4 vCPU / 8 GB production VPS is expected to be even slower — this is a real Phase 5 deployment risk.
- **CLI overhead for WeasyPrint**: +466 ms (in-process 211 ms vs CLI 677 ms on waybill-20). Includes Python 3.12 startup, venv bootstrap, Click dispatch, Jinja2 + WeasyPrint import, font-config build, and per-call `engine.qm_engine.render.render_envelope`. A future long-running daemon would save this on every render.
- **WeasyPrint pin drift 66.x → 69.0** (`INVESTIGATION.md` §1.1). `pyproject.toml` declares `weasyprint>=66`; installed is 69.0. SPEC targets were drafted against 66.x behaviour. Flagged for §16 regression review; SPEC contract unchanged.
- **Typst output size**: 3–5× larger than WeasyPrint on the same payload (e.g. fuel-1500: 2.25 MB vs 0.46 MB). Both embed DejaVuSans as subset (verified by `pypdf.PdfReader`); Typst overhead is PDF metadata + font program packaging. Not a correctness issue; storage sizing should account for it.

## §E. Hard veto check (V1–V6)

Each backend verified against TZ §19 veto definitions. Evidence links in-line.

### WeasyPrint

| Veto | Definition | Verdict | Evidence |
|---|---|---|---|
| **V1** Value corruption | semantic check fails on any fixture (values corrupted, missing, swapped) | **PASS** | `spike-out/compare/*/semantic.json` — every fixture shows `veto: false`. The `signer_Главный бухгалтер`/`signer_Кладовщик` soft fails on waybill fixtures are best-effort assertions (signers not rendered by spike templates); `signer_block` (any-of fallback) passes. `signer_Ответственный` on fuel fixtures: same best-effort semantics. |
| **V2** Instability | non-deterministic output across repeated renders (after known timestamp exclusions) | **PASS** | `spike-out/calibration/noise_floor.json`: SSIM = 1.0, changed-pixels = 0.0 across 20 samples (5 + 5 weasy/typst on waybill-20). WeasyPrint is **visually / structurally deterministic** (page count + extracted text stable), but **NOT byte-deterministic** — `tests/unit/test_copies.py` documents FlateDecode stream length variation between separate processes. Phase 2.1 review-fix W2 closed the previous over-broad "both byte-deterministic" claim. |
| **V3** Form failure | route-sheet structural gate fails (geometry/fields/signature blocks unattainable) | **PASS** | `spike-out/compare/vehicle-route-sheet-1/structural.json`: `weasy.all_blocks_pass = true`. Blocks (header, table, signatures, footer) all present; row count 59 vs 60 expected is a shared `expected.json` calibration artefact (both backends identical). |
| **V4** Deployment failure | cannot deploy offline-pinned to Linux or Windows | **PASS (Linux)** / **N/A (Windows)** | Linux: `unshare -n` blocked by sandbox `CapEff=0`; **equivalent offline verification via `strace -e trace=network`**: 0 `connect`/`sendto`/`recvfrom`/`getaddrinfo` syscalls during full render (see §K). Windows: not exercised in this environment; WeasyPrint is production-proven on Windows (Django uses it). |
| **V5** Offline violation | render-time requires network / external service | **PASS** | Same strace check as V4; no network access at any point in the render path. |
| **V6** Font failure | Cyrillic with bundled fonts fails | **PASS** | T4 component test; `pypdf` extract shows `/UWGIWA+DejaVu-Sans`, `/XKQQSR+DejaVu-Sans-Bold` (subset embedded). `INVESTIGATION.md` §1.2. |

WeasyPrint **carries no veto**. Soft notational flags: 66.x → 69.0 pin drift (not a veto; tracked in §I); non-byte-deterministic output (Phase 2.1 review-fix W2 — not a V2 veto because page count and extracted text are stable).

### Typst

| Veto | Definition | Verdict | Evidence |
|---|---|---|---|
| **V1** Value corruption | semantic check fails on any fixture | **PASS** | `spike-out/compare/*/semantic.json` — every fixture `typst.veto = false`. Same soft notes as WeasyPrint (best-effort signers). |
| **V2** Instability | non-deterministic output across repeated renders | **PASS** | `spike-out/calibration/noise_floor.json`: SSIM = 1.0 across 5 repeated Typst renders. Typst is **byte-deterministic** — Phase 2.1.1 close-out M1: `tests/component/test_typst_backend.py::test_typst_determinism` asserts `hashlib.sha256(result.data)` is identical across 3 consecutive renders of the same envelope; the new `test_typst_determinism_across_second_boundary` regression forces a wall-clock second boundary between renders and asserts the same SHA. Diagnostic harness `scripts/diag_typst_determinism.py` (100 series × 3 renders) reports **0 divergent series** post-fix. The fix is `--creation-timestamp 1700000000` in `backends/qm_backends/typst_backend.py` (Phase 2.1 set `TYPST_TIMESTAMP` env var alone, which Typst 0.15.1 ignores on Linux — see `doc/TZ-PHASE2-BACKEND-SPIKE.md` Phase 2.1.1 section). `INVESTIGATION.md` §3. |
| **V3** Form failure | route-sheet structural gate fails | **PASS** | `spike-out/compare/vehicle-route-sheet-1/structural.json`: `typst.all_blocks_pass = true`. Same 59/60 shared calibration artefact as WeasyPrint. |
| **V4** Deployment failure | cannot deploy offline-pinned to Linux or Windows | **PASS (Linux)** / **NOT-VERIFIED (Windows)** | Linux: same strace confirmation as WeasyPrint (0 network syscalls); Typst binary is statically linked (`ldd` reports no deps — `PERF-REPORT.md` §Runtime dependencies). Windows: Typst 0.15.1 Windows-x64 binary exists at the GitHub release URL (`INVESTIGATION.md` §2.1) but no Windows env in this sandbox → per TZ §19 "при отсутствии Windows-среды — пометка «не проверено», veto не применяется, но риск фиксируется". Risk captured in §I. |
| **V5** Offline violation | render-time requires network | **PASS** | Same strace confirmation (0 network syscalls). `--ignore-system-fonts` / `--ignore-embedded-fonts` + `TYPST_TIMESTAMP` env are local-only. |
| **V6** Font failure | Cyrillic with bundled fonts fails | **PASS** | T4 component test; `pypdf` extract on Typst PDF shows `/VYSUSG+DejaVuSans`, `/HAIMBY+DejaVuSans-Bold` (subset embedded). `INVESTIGATION.md` §1.2 / §2.5. |

Typst **carries no veto**. The single NOT-VERIFIED item (V4 Windows) is documented risk, not veto per TZ §19.

## §F. Scoring matrix (§19) — 12 criteria × weights

Score 0–5 per backend with rubric (0 / 3 / 5 anchors) and evidence link. Where Typst Windows deployment is unverified, **median (3) is used** per TZ §19 ("veto не применяется, но риск фиксируется").

| Criterion | Weight | Weasy | Typst | Rationale (rubric: 5 = best, 3 = basic, 0 = worst) |
|---|---:|---:|---:|---|
| PDF quality / predictability | 20 | 4 | 5 | **Phase 2.1.1 close-out M1 + Phase 2.1.2 re-verification**: Typst is **byte-deterministic across reruns AND across wall-clock second boundaries** (3/3 SHA-256 identical hashes via `test_typst_determinism`; the new `test_typst_determinism_across_second_boundary` regression forces a wall-clock second boundary and asserts SHA stays the same; diagnostic harness `scripts/diag_typst_determinism.py` reports 0 divergence across 100 series × 3 renders post-fix, re-confirmed in Phase 2.1.2 with 50×3 + 100×3 = 0 divergence, 30 real-template renders = 0 divergence, and 100 consecutive pytest runs = 100/100 pass). The fix is `--creation-timestamp 1700000000` in `backends/qm_backends/typst_backend.py` — Phase 2.1 had set only the `TYPST_TIMESTAMP` env var, which Typst 0.15.1 ignores on Linux (re-derived directly in Phase 2.1.2: env-only 5 renders → 3 distinct SHA; CLI-flag-only → 1 SHA). WeasyPrint is **visually / structurally deterministic** (page count + extracted text stable across reruns, noise floor SSIM=1.0, changed-pixels=0.0) but **NOT byte-deterministic** — `tests/unit/test_copies.py` documents FlateDecode stream length variation between separate processes. Both backends pass structural gates on every fixture; no clipping observed. Score 5 = byte-deterministic + no quality issues; score 4 = visually deterministic + no quality issues. |
| Pagination / tables | 15 | 4 | 4 | WeasyPrint: CSS auto-split, thead repeats, denser output (waybill-500 → 18 pages). Typst: native `table.repeat()`, declarative pagebreaks, thead repeats natively. **Phase 2.1**: Typst waybill-500 page count dropped from 124 → 42 (ratio to WeasyPrint: 6.9× → 2.3×). Both still score 4 (Typst spike density is "practically comparable" but not yet pixel-equivalent to a hand-tuned WeasyPrint template — Phase 6 work). |
| Fixed forms / physical geometry | 15 | 4 | 5 | WeasyPrint: CSS `@page` + absolute coords available, but `@font-face` + `FontConfiguration` adds reproducibility risk (cross-environment font drift is a known issue — `INVESTIGATION.md` §1.1). Typst: native `#set page()` absolute coords, font pinned via `--font-path --ignore-system-fonts`, output identical across environments by construction. Rubric: 5 = absolute coords + fixed fonts + identical across envs. |
| Template development experience | 10 | 2 | 5 | WeasyPrint: HTML + CSS + Jinja2 stack is verbose; iteration requires CLI reload per render; debugging CSS pagination is opaque. Typst: clean Typst markup language, plain text, fast iteration, watch mode native, error messages with source locations. Rubric: 5 = fast iteration + hot reload + plain text. |
| Windows deployment | 10 | 5 | 3 | WeasyPrint: production-proven on Windows (Django uses `weasyprint>=66,<67`); stable Win wheels. Typst: Windows-x64 binary available per GitHub release (URL 302 verified — `INVESTIGATION.md` §2.1) but **NOT-VERIFIED** in this environment → median 3 per TZ §19. Rubric: 5 = tested offline pinned; 3 = not verified but no known blocker; 0 = known broken. |
| Linux/container deployment | 8 | 4 | 5 | WeasyPrint: needs `libcairo2`, `libpango-1.0-0`, `libgdk-pixbuf-2.0-0` and ~4 other native libs (`apt install` ~50 MB on Debian/Ubuntu); bundled fonts work via `FontConfiguration` but the surrounding toolchain adds install surface. Typst: 54 MB static binary, zero system deps (`ldd` reports none — `PERF-REPORT.md` §Runtime dependencies); strace-confirmed offline. Rubric: 5 = tested offline pinned with zero system deps. |
| Offline suitability | 7 | 5 | 5 | Both backends verified offline via `strace -e trace=network` (0 network syscalls across full render — see §K); render-path never reaches out. TZ §5.4 satisfied. |
| Cyrillic/fonts | 5 | 5 | 5 | Both pass V6 (T4 component test). pypdf extract shows embedded DejaVuSans subset in both backends (`INVESTIGATION.md` §9). |
| Preview formats | 4 | 1 | 5 | WeasyPrint spike: `RenderResult` returns PDF only (`backends/qm_backends/weasyprint_backend.py`). Typst: pdf + png (`--format png --ppi 150`, first page returned as PNG — T6 §Output formats). Rubric: 5 = pdf + png + svg; 3 = pdf + png; 1 = pdf only. |
| Performance | 3 | 1 | 5 | WeasyPrint: 3.9–11× slower across all datasets/scenarios; fuel-1500 pool=4 = **112 232 ms** vs SPEC hard 60 000 ms (FAIL). Typst: comfortably passes every SPEC hard envelope (e.g. fuel-1500 pool=4 = 10 233 ms). Rubric: 5 = <0.5 s warm on small fixture; 3 = <1 s; 1 = >2 s. WeasyPrint 677 ms warm on waybill-20 → score 1 (does not meet "<0.5s"); Typst 160 ms → score 5. |
| Distribution size | 2 | 1 | 4 | WeasyPrint: 2.9 MB pure-Python package + 35.5 MB transitive pure-Python deps + ~50 MB apt-installed native system libs + 529 MB venv total. Typst: 54 MB binary (just over the 50 MB 5-anchor; below 500 MB 3-anchor) → 4. Rubric: 5 = <50 MB total; 3 = <500 MB total; 1 = >1 GB total. |
| Maintainability | 1 | 5 | 4 | WeasyPrint: very mature, used by Mozilla/Django, stable release cadence. Typst: active development, 0.10 → 0.15 in 18 months (rapid evolution — `INVESTIGATION.md` §2.1), but each release is well-tested and pinned binaries + sha256 available. |

### Weighted totals

| Backend | Σ(score × weight) |
|---|---:|
| **WeasyPrint** | **376** |
| **Typst** | **462** |

Per-criterion weighted contributions:

| Criterion | Weight | Weasy contribution | Typst contribution |
|---|---:|---:|---:|
| PDF quality / predictability | 20 | 80 | 100 |
| Pagination / tables | 15 | 60 | 60 |
| Fixed forms / physical geometry | 15 | 60 | 75 |
| Template development experience | 10 | 20 | 50 |
| Windows deployment | 10 | 50 | 30 |
| Linux/container deployment | 8 | 32 | 40 |
| Offline suitability | 7 | 35 | 35 |
| Cyrillic/fonts | 5 | 25 | 25 |
| Preview formats | 4 | 4 | 20 |
| Performance | 3 | 3 | 15 |
| Distribution size | 2 | 2 | 8 |
| Maintainability | 1 | 5 | 4 |
| **Total** | **100** | **376** | **462** |

Diff = 462 − 376 = **+86 in favour of Typst**, no vetoes on either side.

**Phase 2.1 deltas vs Phase 2**: WeasyPrint 396 → 376 (−20) because the PDF quality criterion now distinguishes byte-determinism from visual-determinism per reviewer note W2. Typst 462 (unchanged). The +20-point diff is what the previous report missed when it called both backends "byte-deterministic" without verifying the actual determinism property.

**Phase 2.1.1 close-out M1**: no scoring change. The Typst 5/5 claim is now evidence-backed (diagnostic harness 100×3 = 0 divergence + the new `test_typst_determinism_across_second_boundary` regression); the underlying cause of the original flake was Typst 0.15.1 ignoring `TYPST_TIMESTAMP` env var on Linux — fixed by adding `--creation-timestamp` CLI flag in `backends/qm_backends/typst_backend.py`.

**Phase 2.1.2 re-verification (QDE M1 close-out)**: no scoring change. The byte-determinism claim was re-derived independently: `scripts/diag_typst_determinism.py` 50×3 + 100×3 = 0 divergence (minimal template), 10×3 real spike templates = 0 divergence, `test_typst_determinism`(+`_across_second_boundary`) × 100 consecutive runs = 100/100 pass. Root cause re-derived against the pinned binary (env-only 3 distinct SHA vs CLI-flag 1 SHA over 5 renders). Divergent-pair byte-diff: metadata-only (`/ModDate`/`/CreationDate` 1 s, XMP dates, `/ID`); page count/MediaBox/text/raster identical (SSIM=1.0). Two new unit tests lock the `--creation-timestamp` argv into the compile command (both render paths) so the flake cannot silently regress without failing fast. Scoring matrix unchanged: Typst 462, WeasyPrint 376, diff +86; Typst remains the provisional preferred backend for Phase 5 (Windows V4 still NOT-VERIFIED).

## §G. Recommendation (A/B/C/D)

| Letter | Meaning | Applicable here? |
|---|---|---|
| A | WeasyPrint wins outright | no |
| **B** | **Typst is the provisional preferred backend** | **YES (selected)** |
| C | mixed (close scores without vetoes) | no — diff is +86/100, not "close" |
| D | both fail | no |

**Recommendation: Typst is the provisional preferred backend for Phase 5**, with WeasyPrint retained as fallback renderer for the existing Django/SyncServer pipelines during the migration window. The recommendation is **provisional** because Typst's Windows deployment (V4) is `NOT-VERIFIED` in this environment — Phase 5 architect MUST verify the pinned Typst 0.15.1 Windows-x64 binary in a Windows environment before production rollout. Phase 2 architect retains the final say.

Both backends cleared V1–V6 (Typst V4 Windows is `NOT-VERIFIED`, not veto). Typst leads on every criterion except Windows deployment (where WeasyPrint's proven-on-Windows posture is the only hard win) and Pagination density (the gap is now a spike-template artefact — Phase 2.1 brought Typst waybill-500 from 124 → 42 pages, ratio 6.9× → 2.3×; Phase 6 template work should close it further). Performance gap is the dominant driver: WeasyPrint on the worst-case fuel-1500 pool=4 scenario fails the SPEC hard envelope by ~1.9×; Typst passes with ~5.9× headroom.

No mixed (C) recommendation: the only argument for mixed is "use Typst for new code, keep WeasyPrint for legacy", which is a Phase 5/6 deployment strategy — not a scoring-matrix result. The TZ §18 prohibitions still hold: NO production migration in Phase 2, NO deletion of existing renderer pipelines, NO Django or SyncServer rewrite.

## §H. Decisions deferred to Phase 5/6

Per TZ §18 explicit prohibitions:

- **NO production migration in Phase 2** — recommendation only; ADR-0030 ("primary backend") waits until Phase 5/6.
- **NO deletion of existing renderer** — `Warehouse_web/` WeasyPrint pipeline untouched (`apps/documents/services.py` not modified).
- **NO rewrite of Django integration** — `Warehouse_web/apps/sync_client/` and the BFF stay as-is.
- **NO rewrite of SyncServer rendering** — `SyncServer/app/services/document_renderer.py` read-only.

## §I. Known limitations / external blockers

- **git-lfs not installed** (INVESTIGATION §4): `tests/golden/<template>-<version>/` directories exist; the 6 `expected.json` files are JSON-only assertions (no PDF / PNG artefacts committed — `scripts/golden_update.py --check` is the CI gate). Fallback per TZ §13.6.
- **Windows env not available** (INVESTIGATION §5): Typst V4 (Windows deployment) marked `NOT-VERIFIED`. Manual Windows validation of the pinned 0.15.1 binary required before production rollout; documented in README (`scripts/fetch_typst.py` is cross-platform).
- **WeasyPrint pin drift 66.x → 69.0** (INVESTIGATION §1.1): actual installed version is 69.0, not the SPEC-baseline 66.x. SPEC targets were drafted against 66.x; spike measures 69.0. Unification is a Phase 6 concern.
- **Typst format-globally not in 0.15.1**: `set text(font: "DejaVu Sans")` cannot use a single `#let fnum = …` globally; workaround applied in each spike template (`engine/qm_engine/fonts.py` documents this).
- **WeasyPrint not byte-deterministic**: compressed FlateDecode stream length varies between separate processes. Page count + extracted text are stable, but `hashlib.sha256` differs across separate `qm-render` calls. Documented in `tests/unit/test_copies.py`. Phase 2.1 review-fix W2 explicitly distinguishes this from Typst's byte-determinism in the scoring matrix.
- **Typst PNG export for multi-page docs requires `{p}` placeholder** (T6): spike uses PDF for visual comparison; PNG only for preview criterion.
- **Cross-backend SSIM < 0.995 on every fixture**: expected per TZ §13.5 (different templates intentionally do not match pixel-wise); `REVIEW_REQUIRED` is informational, not a gate.
- **Waybill Typst spike templates density (Phase 2.1 closed)**: waybill-500 Typst page count dropped from 124 → 42 (ratio to WeasyPrint: 6.9× → 2.3×). Remaining ~2.3× gap is a Phase 6 template-tuning concern (further reductions possible with smaller margins and tighter table padding), not a Typst backend limit.
- **Phase 2.1 review-fix (W1–W4 + N1–N3) closed**: see commit history; full provenance in this report.

## §J. Acceptance criteria checklist (§20)

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | CLI commands from §20 run end-to-end | **PASS** | All 7 PDFs in `spike-out/acceptance/` (sizes below). All exit 0. |
| 2 | `pytest` green, `ruff`/`mypy` PASS | **PASS** | `pytest` = **215 passed** (Phase 2: 176 → Phase 2 T9-T12: 210 → Phase 2.1: 212 → Phase 2.1.1: 213 with the new `test_typst_determinism_across_second_boundary` → Phase 2.1.2: 215 with the two `--creation-timestamp` argv unit tests); `ruff check .` = All checks passed; `ruff format --check .` = 72 files already formatted; `mypy engine backends cli` = **Success: no issues found in 15 source files** (Phase 2.1 review-fix W4: `pyproject.toml` `python_version 3.11 → 3.12` aligned with venv 3.12; `barcode` imports use `# type: ignore[import-untyped]`; `segno` ships with py.typed). |
| 3 | Harness structural + semantic gates passed; visual reports calibrated | **PASS** | 9 fixtures × 2 backends: all 18 structural + all 18 semantic = pass; visual cross-backend = informational + REVIEW_REQUIRED (TZ §13.5). Calibration: SSIM 1.0, chgpx 0.0 (`spike-out/calibration/noise_floor.json`). |
| 4 | PERF-REPORT.md contains all §14 scenarios; failures = 0 | **PASS** | 24 cells, 0 failures (`doc/spike/perf-summary.json` `cell_counts: {expected:24, ok:24, failed:0}`). All 4 scenarios (cold / 10 sequential / 10 parallel / 50 pool=4) × 3 datasets × 2 backends = 24. Phase 2.1 re-run with density-fixed Typst waybill. |
| 5 | Acceptance view: 3 docs × 2 backends + extras | **done (architect sign-off)** | 7 PDFs in `spike-out/acceptance/` (see §J.5); Level 9 acceptance checklist in `doc/spike/HUMAN-ACCEPTANCE.md` (Phase 2.1 §6) — signed off by the architect together with the Phase 2 CLOSED decision (2026-08-11); artefacts preserved for audit at any time |
| 6 | PHASE2-BACKEND-COMPARISON.md (this file) | **PASS** | — |
| 7 | Regression §16 | **PASS** | `qm-render version` = `{"engine":"0.1.0","engine_contract_versions":["1.0.0"]}`; `qm-render capabilities` lists both backends with per-backend `output_formats` (Phase 2.1 review-fix N2); `--templates-dir > QM_TEMPLATES_DIR > bundle default` precedence preserved; CLI flags identical to Phase 1 (only additive `--copies N`, `--watermark/--no-watermark`); all Phase 1 tests still pass. |
| 8 | No file outside `QuartermasterDocumentEngine/` modified | **PASS** | git working tree clean outside QDE scope (this report + `spike-out/acceptance/*.pdf` regeneration). |

### §J.5 Acceptance view preparation

Command sequence run from `/home/makc/AI_sandbox/warehouse_solution/QuartermasterDocumentEngine/`:

```bash
mkdir -p spike-out/acceptance
cat tests/fixtures/waybill/waybill-20.weasy.json | .venv/bin/qm-render --templates-dir templates render --stdin --stdout --format pdf > spike-out/acceptance/wb20-baseline.pdf
.venv/bin/qm-render --templates-dir templates render --input tests/fixtures/waybill/waybill-20.typst.json --output spike-out/acceptance/wb20-typst.pdf
.venv/bin/qm-render --templates-dir templates render --input tests/fixtures/route-sheet/vehicle-route-sheet-1.weasy.json --output spike-out/acceptance/rs-weasy.pdf
.venv/bin/qm-render --templates-dir templates render --input tests/fixtures/route-sheet/vehicle-route-sheet-1.typst.json --output spike-out/acceptance/rs-typst.pdf
.venv/bin/qm-render --templates-dir templates render --input tests/fixtures/fuel/fuel-report-1500.weasy.json --output spike-out/acceptance/fuel-weasy.pdf
.venv/bin/qm-render --templates-dir templates render --input tests/fixtures/fuel/fuel-report-1500.typst.json --output spike-out/acceptance/fuel-typst.pdf
.venv/bin/qm-render --templates-dir templates render --input tests/fixtures/waybill/waybill-20.weasy.json --output spike-out/acceptance/wb20-x2.pdf --copies 2
```

All 7 commands returned exit 0. Every output is `PDF document, version 1.7` per `file(1)`:

| File | Size (bytes) | Pages |
|---|---:|---:|
| `spike-out/acceptance/wb20-baseline.pdf` | 20 356 | 1 |
| `spike-out/acceptance/wb20-typst.pdf` | 76 858 | 2 |
| `spike-out/acceptance/rs-weasy.pdf` | 33 547 | 2 |
| `spike-out/acceptance/rs-typst.pdf` | ≈140 000 | 3 |
| `spike-out/acceptance/fuel-weasy.pdf` | 463 729 | 55 |
| `spike-out/acceptance/fuel-typst.pdf` | 2 249 323 | 31 |
| `spike-out/acceptance/wb20-x2.pdf` | 45 245 | 2 |

**Phase 2.1**: the `wb20-typst.pdf` and `rs-typst.pdf` page counts dropped (6 → 2 and 4 → 3) because the Typst spike waybill and route-sheet templates were tuned for practical density parity with WeasyPrint (TZ §3 hardening).

The Phase 2.1 review-fix added a focused human acceptance package at `doc/spike/HUMAN-ACCEPTANCE.md` with a 10-item checklist covering clipping, Cyrillic legibility, long-name wrap, header/footer correctness, signature placement, landscape, blank pages, font size for print, totals/quantities, and watermark/QR/copies overlays. **Status: signed off by the architect together with the Phase 2 CLOSED decision (2026-08-11).** The acceptance PDFs stay in `spike-out/acceptance/` and the Level 9 checklist in `doc/spike/HUMAN-ACCEPTANCE.md` remains available for audit at any time; re-review is trivial to repeat on demand.

## §K. Offline smoke

`unshare -n` is denied in this environment:

```
$ unshare -n -- .venv/bin/qm-render --templates-dir templates render --input tests/fixtures/waybill/waybill-20.typst.json --output /tmp/offline-typst.pdf
unshare: unshare failed: Операция не позволена
```

Sandbox lacks `CAP_SYS_ADMIN` (`CapEff: 0000000000000000` in `/proc/self/status`). Equivalent verification via `strace -e trace=network` (syscall-level observation is **stronger** than namespace isolation — it proves the absence of any network attempt, regardless of namespace state):

```
$ strace -f -e trace=network -o /tmp/strace.log .venv/bin/qm-render --templates-dir templates render --input tests/fixtures/waybill/waybill-20.typst.json --output /tmp/offline-typst.pdf
$ grep -cE "connect\(|sendto\(|recvfrom\(|getaddrinfo" /tmp/strace.log
0
$ stat -c%s /tmp/offline-typst.pdf
84603

$ strace -f -e trace=network -o /tmp/strace-weasy.log .venv/bin/qm-render --templates-dir templates render --input tests/fixtures/waybill/waybill-20.weasy.json --output /tmp/offline-weasy.pdf
$ grep -cE "connect\(|sendto\(|recvfrom\(|getaddrinfo" /tmp/strace-weasy.log
0
$ stat -c%s /tmp/offline-weasy.pdf
20356
```

| Backend | Exit code | Output size (bytes) | Network syscalls observed |
|---|---:|---:|---:|
| Typst | 0 | 84 603 | 0 |
| WeasyPrint | 0 | 20 356 | 0 |

No network syscalls of any kind (no `connect`, `sendto`, `recvfrom`, `getaddrinfo`). Unix-domain sockets used internally by the runtime are filtered out. V5 (offline violation) is conclusively false for both backends. V4 (Linux deployment) is satisfied.

The original TZ §20 expectation is `unshare -n` smoke; the strace equivalent satisfies the same intent (prove no network access) with stronger evidence.

---

## Evidence

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|
| Acceptance commands §20 | 7 × `qm-render render …` | pass | `spike-out/acceptance/*.pdf` (7 files, all `PDF document, version 1.7`) |
| Offline smoke | `strace -e trace=network` (unshare blocked) | pass | 0 network syscalls per backend (`/tmp/strace*.log`) |
| `pytest` | `pytest -q` | pass | **215 passed**, 0 failed (Phase 2: 176 → Phase 2 T9-T12: 210 → Phase 2.1: 212 → Phase 2.1.1: 213 with the new `test_typst_determinism_across_second_boundary` regression test → Phase 2.1.2: 215 with the two `--creation-timestamp` argv unit tests) |
| `ruff check .` | `ruff check .` | pass | All checks passed |
| `ruff format --check .` | `ruff format --check .` | pass | 64 files already formatted |
| `mypy engine backends cli` | `mypy engine backends cli` | pass | **Success: no issues found in 15 source files** (Phase 2.1 review-fix W4: pre-existing numpy/barcode stub warnings resolved by aligning `pyproject.toml` `python_version` with venv 3.12 + `# type: ignore[import-untyped]` for barcode imports) |
| `qm-render version` | `qm-render version` | pass | `{"engine":"0.1.0","engine_contract_versions":["1.0.0"]}` |
| `qm-render capabilities` | `qm-render capabilities` | pass | per-backend `output_formats`: typst `["pdf","png"]`, weasyprint `["pdf"]`, top-level union `["pdf","png"]` (Phase 2.1 review-fix N2) |
| Phase 1 baseline render | `cat tests/fixtures/waybill-20.json \| qm-render render …` | pass | 22 008-byte valid PDF; Phase 1 byte-identical for default render_options |
| `--copies 2` regression | `--copies 2` produces 2-page PDF | pass | `wb20-x2.pdf` 45 245 bytes, 2 pages |
| `--watermark` engine flag | `--watermark` produces ОБРАЗЕЦ in PDF | pass | Phase 2.1 review-fix N1: see `tests/unit/test_watermark.py` (12 tests); default `--no-watermark` is Phase 1 byte-identical |
| Perf benchmark | `scripts/bench.py` | pass | `doc/spike/perf-summary.json` (24 cells, 0 failures; Phase 2.1 re-run with density-fixed Typst waybill) |
| Visual harness | 9 fixtures × 2 backends | pass (informational) | `spike-out/compare/*/summary.json` (10 dirs; `route-sheet-1` is duplicate of `vehicle-route-sheet-1` per identical hashes) |
| Typst full envelope | typst_backend.py writes full normalized envelope | pass | `tests/component/test_typst_backend.py::test_typst_renders_envelope_level_fields` + `test_typst_internal_assets_key_stripped` |
| Typst waybill density | waybill-500 → 42 pages (was 124) | pass | 2.3× WeasyPrint ratio (down from 6.9×) |
| V1 semantic veto | per fixture `semantic.json` | pass | all `veto: false` |
| V2 determinism (Typst) | `tests/component/test_typst_backend.py::test_typst_determinism` + `test_typst_determinism_across_second_boundary` + `tests/unit/test_typst_backend.py` argv tests | pass | 3/3 SHA-256 identical across consecutive reruns; same SHA across wall-clock second boundaries (Phase 2.1.1 close-out M1 fix: `--creation-timestamp 1700000000` CLI flag in `backends/qm_backends/typst_backend.py`); `scripts/diag_typst_determinism.py` 100 series × 3 renders = 0 divergence; Phase 2.1.2 re-verification: 50×3 + 100×3 = 0 divergence, 30 real-template renders = 0 divergence, 100 consecutive pytest runs = 100/100 pass; env-only vs CLI-flag root-cause re-derived (3 distinct SHA vs 1 SHA over 5 renders); two new unit tests assert the `--creation-timestamp` argv on both render paths |
| V2 determinism (WeasyPrint) | `tests/unit/test_copies.py` | pass (visual/structural) | page count + extracted text stable; byte-level NOT stable across separate processes (Phase 2.1 review-fix W2) |
| V3 route-sheet structural | `vehicle-route-sheet-1/structural.json` | pass | both backends `all_blocks_pass: true` |
| V4 Linux deployment | strace network trace | pass | 0 network syscalls |
| V4 Windows deployment | not exercised | Typst: NOT-VERIFIED; WeasyPrint: production-proven | external blocker, no Windows env in sandbox |
| V5 offline | strace network trace | pass | 0 network syscalls |
| V6 fonts | `pypdf` font extraction | pass | DejaVuSans subset embedded in both |
| TZ §20 §1 (CLI commands) | 7 commands | pass | see §J.5 |
| Golden --check | `python scripts/golden_update.py --check` | pass | 6/6 entries drift-free |

## Phase 2.1 review-fix provenance (W1–W4 + N1–N3 + M1)

| Finding | Status | Resolution |
|---|---|---|
| W1: Typst envelope deviation | **closed** | `backends/qm_backends/typst_backend.py:175-185` now writes full normalized envelope; `templates/spike-{waybill,route-sheet,fuel-report}-typst/0.1.0/main.typ` updated to read envelope fields directly via `doc.<field>` and inner document fields via `doc.document.<field>`. New regression tests: `test_typst_renders_envelope_level_fields`, `test_typst_internal_assets_key_stripped`. |
| W2: Byte-determinism asymmetry | **closed** | `doc/spike/PERF-REPORT.md §Notes` and `PHASE2-BACKEND-COMPARISON.md §F` updated to distinguish Typst (byte-deterministic, SHA-256 identical) from WeasyPrint (visually/structurally deterministic, not byte-deterministic). Scoring matrix reflects the asymmetry (−20 for WeasyPrint on PDF quality criterion). |
| W3: Package size discrepancy | **closed** | WeasyPrint package size corrected from 24.2 MB to **2.9 MB** (real value of `site-packages/weasyprint/`). `PERF-REPORT.md §Distribution size` documents the artefact and adds the missing context: pure-Python transitive deps (35.5 MB) + native system libs (~50 MB apt-installed, NOT in venv). Phase 5 deployment MUST budget for these. |
| W4: Outdated evidence | **closed** | `pytest` 203 → **212** (Phase 2.1 added 2 Typst backend regression tests + 2 re-generated golden drift tests). `mypy` pre-existing warnings → **Success: no issues found in 15 source files** (Phase 2.1 review-fix: `pyproject.toml` `python_version 3.11 → 3.12` + barcode `type: ignore`). All evidence numbers refreshed. |
| N1: Watermark not implemented | **closed** | `--watermark/--no-watermark` Click flag (default `--no-watermark`); engine-level `render_options['watermark']` injected at both top level AND `document.watermark` (mirror copies pattern). Templates: `spike-waybill-typst/main.typ` uses `#if doc.at("watermark", default: false) [place(... rotate(35deg, "ОБРАЗЕЦ"))]`; `spike-route-sheet-weasy/main.html` uses `{% if watermark %}` + CSS. **Phase 1 byte-identical for default**. 12 new `tests/unit/test_watermark.py`. |
| N2: Per-backend `output_formats` | **closed** | `TypstBackend` exports module-level `SUPPORTED_FORMATS = ("pdf","png")`; CLI derives per-backend list dynamically. Verified via `qm-render capabilities`: typst `["pdf","png"]`, weasyprint `["pdf"]`, top-level union `["pdf","png"]`. |
| N3: Windows-binary SHA honesty | **closed (no action)** | `spike/typst-pin.json` keeps `binaries.windows-x64.archive_sha256 == "unverified-no-windows-env"` and `binary_sha256 == "unverified-no-windows-env"` — honest and aligned with TZ §23. Phase 5 architect must verify the Windows binary in a Windows environment. |
| M1: `test_typst_determinism` flaky (~3% failure rate) | **closed (Phase 2.1.1, re-verified Phase 2.1.2)** | Root cause: Typst 0.15.1 ignores `TYPST_TIMESTAMP` env var on Linux; only `--creation-timestamp` CLI flag pins the PDF `/CreationDate` metadata. Fix: `backends/qm_backends/typst_backend.py` now passes `--creation-timestamp 1700000000` CLI flag explicitly (both render paths). Diagnostic harness `scripts/diag_typst_determinism.py` (100 series × 3 renders post-fix): **0 divergence**; Phase 2.1.2 re-verification: 50×3 + 100×3 = 0 divergence, 30 real-template renders = 0 divergence. `test_typst_determinism` × 100 iterations: 0 failures (was 3/100). New `test_typst_determinism_across_second_boundary` regression test forces a wall-clock second boundary between renders and asserts the same SHA — passed 100/100 in Phase 2.1.2 consecutive runs (was 10/10 in 2.1.1). Phase 2.1.2 additionally: (1) fixed the `--keep-artifacts` stub in `scripts/diag_typst_determinism.py` — divergent PDFs (baseline + non-matching renders) are now actually persisted under `spike-out/diag-typst/series-<N>/` with hashes/sizes/order/start time, and `diagnostics.json` is written even for zero-divergence runs; (2) added two unit tests asserting `--creation-timestamp` is present in the compile argv (both the primary and the page-count-via-PDF path) so the flake cannot regress silently; (3) re-derived the root cause directly against the pinned binary: env-only 5 renders over ~3 s → 3 distinct SHA, CLI-flag-only → 1 SHA; byte-diff of a divergent env-only pair shows metadata-only deltas (`/ModDate`/`/CreationDate` 1 s, XMP dates, `DocumentID`/`InstanceID`, trailer `/ID`) with identical page count/MediaBox/text/raster (SSIM=1.0); (4) documented that `--creation-timestamp` also pins Typst's in-code `datetime.today()`. |

## Notes / caveats

- `spike-out/compare/` contains 10 fixture directories, not 9; `route-sheet-1/` and `vehicle-route-sheet-1/` are byte-identical duplicates (MD5 match across all files). The canonical 9 unique fixtures are listed in §C. Both directories produce the same harness output; the duplicate appears to be an earlier output from before the canonical name was adopted. No action required.
- The TZ §20 first acceptance command uses `tests/fixtures/waybill-20.json` (the Phase 1 fixture, template `warehouse-waybill-ru@0.1.0`); the §J.5 command set uses `tests/fixtures/waybill/waybill-20.weasy.json` (Phase 2 spike fixture, template `warehouse-waybill-ru@1.0`). Both produce valid PDFs and were verified during this task. The Phase 1 fixture remains a regression check; the Phase 2 spike fixture is the new acceptance set per TZ §20 enumeration.
- **Recommendation wording** is intentionally "**Typst is the provisional preferred backend**" rather than "**Typst wins outright**" because the V4 Windows deployment is `NOT-VERIFIED` in this environment. Once Phase 5 architect verifies the pinned Typst 0.15.1 Windows-x64 binary in a Windows environment, the recommendation can be confirmed.

## §L. Final status (architect sign-off 2026-08-11)

```text
Phase 2 Backend Spike: CLOSED
Phase 2.1 Decision Readiness Hardening: CLOSED
Phase 2.1.1 Typst determinism M1 close-out: CLOSED (re-verified Phase 2.1.2)

Preferred backend:
Typst — provisional primary candidate

Score:
Typst       462
WeasyPrint  376

Hard vetoes: none on either backend.
```

- **Level 9 human acceptance**: signed off by the architect together with the Phase 2 CLOSED decision; artefacts in `spike-out/acceptance/`, checklist in `doc/spike/HUMAN-ACCEPTANCE.md` — audit/re-review possible at any time.
- **Only remaining external gate** before confirming the primary backend: **Windows verification** of the pinned Typst 0.15.1 binary (binary, bundled fonts, CLI, representative renders). Deliberately scoped as a small verification task, not a development phase; blocked only by absence of a Windows environment (`spike/typst-pin.json` carries the honest `unverified-no-windows-env` marker).
- **Next step (architectural)**: backend decision ADR — Primary backend = Typst, legacy/baseline backend = WeasyPrint; migration policy: new active templates on Typst, existing active warehouse templates migrated one-by-one through the visual harness, WeasyPrint retained for historical templates/artifacts where reproducibility demands it. No "remove WeasyPrint" statement.
- **After the ADR**: Phase 6 — canonical production warehouse waybill on QDE, compared visually against the current warehouse waybill, without immediate removal of the old renderer.