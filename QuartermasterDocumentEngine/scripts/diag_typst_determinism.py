"""Diagnostic harness for the Typst determinism flake (Phase 2.1 §M1).

Runs ``N_SERIES`` series of ``N_RENDERS`` consecutive Typst renders via the
production ``TypstBackend`` against a fixed input. Captures the metadata
of every PDF and persists divergent PDFs (baseline + each non-matching
render) to ``spike-out/diag-typst/``, which is gitignored. With
``--keep-artifacts`` the full render corpus is also persisted.

Outputs:
* ``diagnostics.json`` — full results: per-series hashes, sizes, wall
  time, and the diff report for any series that diverged. Written on
  every run (including zero-divergence runs).
* ``series-<N>/`` — divergent PDFs (always) plus full corpus (with
  ``--keep-artifacts``), named ``<tag>-r<render>-<sha12>-<size>B.pdf``
  with a ``started.txt`` recording the series wall-clock start.
* stdout summary: number of series, number of divergent series, which
  call within the series diverged.

Usage:
    .venv/bin/python scripts/diag_typst_determinism.py
    .venv/bin/python scripts/diag_typst_determinism.py --series 50 --renders 3
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# Make repo root importable so we can use the production TypstBackend.
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from io import BytesIO  # noqa: E402

from pypdf import PdfReader  # noqa: E402
from qm_backends.typst_backend import TypstBackend  # noqa: E402
from qm_engine.registry import TemplatePackage  # noqa: E402

OUT_DIR = REPO / "spike-out" / "diag-typst"
TMP_TEMPLATES = OUT_DIR / "_templates"


@dataclass
class SeriesEntry:
    series: int
    render: int
    sha256: str
    size: int
    pdf_meta: dict[str, object]
    wall_ms: float
    data: bytes = b""


def _build_template_package() -> TemplatePackage:
    """Mimic the production test_typst_determinism template.

    Phase 2.1 contract: ``document.json`` is the **full normalized
    envelope**, so envelope-level fields are read via ``doc.<field>``
    and inner document fields via ``doc.document.<field>``. Matches
    ``tests/component/test_typst_backend.py::_build_template_package``
    with ``use_inner=False``.
    """
    if TMP_TEMPLATES.exists():
        shutil.rmtree(TMP_TEMPLATES)
    TMP_TEMPLATES.mkdir(parents=True)
    (TMP_TEMPLATES / "main.typ").write_text(
        '#set document(title: "Spike Typst")\n'
        "#set page(width: auto, height: auto, margin: 1cm)\n"
        '#set text(font: "DejaVu Sans", lang: "ru", size: 12pt)\n'
        "= Тестовый Typst-рендер\n\n"
        '#let doc = json("document.json")\n'
        "Документ: *#{doc.document.title}*. "
        'Контракт: #doc.at("document_number", default: "—")\n\n'
        "#let items = doc.document.items\n"
        "#for item in items [\n"
        '  - Наименование: *#{item.name}*, количество: #"%.2f" % item.qty\n'
        "]\n",
        encoding="utf-8",
    )
    (TMP_TEMPLATES / "manifest.yaml").write_text(
        "id: typst-spike-determinism-diag\n"
        "version: 0.1.0\n"
        "document_contract: warehouse.operation-document/v2\n"
        "backend: typst\n"
        "entrypoint: main.typ\n"
        "output_formats: [pdf, png]\n"
        "locales: [ru-RU]\n",
        encoding="utf-8",
    )
    return TemplatePackage(
        root=TMP_TEMPLATES,
        manifest={
            "id": "typst-spike-determinism-diag",
            "version": "0.1.0",
            "document_contract": "warehouse.operation-document/v2",
            "backend": "typst",
            "entrypoint": "main.typ",
            "output_formats": ["pdf", "png"],
            "locales": ["ru-RU"],
        },
    )


def _sample_document() -> dict[str, object]:
    """Mimic the production test_typst_determinism sample."""
    return {
        "engine_contract_version": "1.0.0",
        "document_contract": "warehouse.operation-document/v2",
        "document_type": "waybill",
        "template_id": "warehouse-waybill-ru",
        "template_version": "1.0",
        "locale": "ru-RU",
        "render_profile": "print",
        "document_id": "ENV-TEST-001",
        "document_number": "WB-FIX-TEST",
        "document": {
            "title": "Накладная WAYBILL-TEST",
            "items": [
                {"name": "Болт М8", "qty": 12.5},
                {"name": "Гайка М8", "qty": 100.0},
            ],
        },
        "__assets__": {},
    }


def _extract_pdf_metadata(pdf_bytes: bytes) -> dict[str, object]:
    """Pull trailer / metadata / IDs from a PDF for diagnostic comparison."""
    reader = PdfReader(BytesIO(pdf_bytes))
    info = {}
    trailer = reader.trailer
    if trailer:
        info["trailer_keys"] = sorted(str(k) for k in trailer)
    if "/ID" in (trailer or {}):
        ids = trailer["/ID"]
        info["doc_id"] = [str(x) for x in ids] if isinstance(ids, list) else str(ids)
    doc_info = reader.metadata
    if doc_info:
        for k, v in doc_info.items():
            info[f"meta_{k}"] = str(v)
    info["page_count"] = len(reader.pages)
    media_boxes = []
    fonts_seen = set()
    for page in reader.pages:
        try:
            box = page.mediabox
            media_boxes.append((float(box.width), float(box.height)))
        except Exception:  # noqa: BLE001
            media_boxes.append(None)
        for font_dict in (page.get("/Resources") or {}).get("/Font", {}).values():
            base = font_dict.get("/BaseFont")
            if isinstance(base, str):
                fonts_seen.add(base)
    info["media_boxes"] = [str(m) for m in media_boxes]
    info["fonts"] = sorted(fonts_seen)
    # Object count: try to read via the underlying xref via pypdf's
    # internal API; falls back to None when not available (pypdf version
    # dependent).
    try:
        info["object_count_proxy"] = len(reader.pages) + len(reader._root_object)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        info["object_count_proxy"] = None
    return info


def _compare(entries: list[SeriesEntry]) -> list[str]:
    """Return human-readable diff lines for a divergent series."""
    diffs: list[str] = []
    baseline = entries[0]
    for e in entries[1:]:
        if e.sha256 == baseline.sha256:
            continue
        diffs.append(
            f"  series[{baseline.series}] render[{baseline.render}] vs render[{e.render}]:\n"
            f"    SHA:     {baseline.sha256[:16]}... != {e.sha256[:16]}...\n"
            f"    size:    {baseline.size} != {e.size}"
        )
    return diffs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--series", type=int, default=50)
    ap.add_argument("--renders", type=int, default=3)
    ap.add_argument(
        "--keep-artifacts",
        action="store_true",
        help=(
            "Keep per-series render PDFs on disk (baseline + any divergent "
            "renders). Divergent PDFs are always saved; this flag additionally "
            "persists the baseline series artefacts."
        ),
    )
    args = ap.parse_args()

    if not OUT_DIR.exists():
        OUT_DIR.mkdir(parents=True)

    package = _build_template_package()
    sample = _sample_document()
    backend = TypstBackend()
    if not backend.available():
        print("FATAL: Typst backend not available", file=sys.stderr)
        return 2

    print("== Typst determinism diagnostic ==")
    print(f"Series: {args.series}, renders per series: {args.renders}")
    print(f"Total renders: {args.series * args.renders}")
    print(f"Started: {datetime.now().isoformat(timespec='seconds')}")

    series_results: list[list[SeriesEntry]] = []
    divergent_series: list[int] = []

    for s in range(args.series):
        # Re-mutate the same `sample` dict like the production test does
        # (backend.render pops __assets__ on each call).
        doc = json.loads(json.dumps(sample))  # fresh each series
        series_entries: list[SeriesEntry] = []
        series_started = datetime.now()
        for r in range(args.renders):
            t0 = datetime.now()
            result = backend.render(
                normalized_document=doc,
                template_package=package,
                output_format="pdf",
                render_options={},
            )
            wall_ms = (datetime.now() - t0).total_seconds() * 1000
            sha = hashlib.sha256(result.data).hexdigest()
            entry = SeriesEntry(
                series=s,
                render=r,
                sha256=sha,
                size=len(result.data),
                pdf_meta=_extract_pdf_metadata(result.data),
                wall_ms=wall_ms,
                data=result.data,
            )
            series_entries.append(entry)
            print(
                f"  series {s:3d} render {r}: {sha[:16]}... size={entry.size} wall={wall_ms:.0f}ms",
                end="\r",
            )
        print()
        # Check if this series diverged. Every render is a fresh
        # subprocess (the backend spawns a new ``typst compile`` per
        # call), so there is no in-process warm cache: each render is
        # "cold" from the renderer's perspective.
        unique_hashes = {e.sha256 for e in series_entries}
        if len(unique_hashes) > 1:
            divergent_series.append(s)
            # Save divergent PDFs (baseline + every non-matching render)
            # to the diagnostic directory, with hashes/sizes/order/time.
            baseline = series_entries[0]
            series_dir = OUT_DIR / f"series-{s:04d}"
            series_dir.mkdir(parents=True, exist_ok=True)
            for e in series_entries:
                tag = "baseline" if e.sha256 == baseline.sha256 else f"divergent-r{e.render}"
                (series_dir / f"{tag}-r{e.render}-{e.sha256[:12]}-{e.size}B.pdf").write_bytes(
                    e.data
                )
            (series_dir / "started.txt").write_text(
                f"{series_started.isoformat(timespec='seconds')}\n"
                f"wall-clock seconds: "
                f"{min(e.wall_ms for e in series_entries) / 1000:.3f}.."
                f"{max(e.wall_ms for e in series_entries) / 1000:.3f}\n",
                encoding="utf-8",
            )
        elif args.keep_artifacts:
            # Non-divergent series: persist a copy of every render so the
            # audit trail includes the full corpus, not only divergences.
            baseline = series_entries[0]
            series_dir = OUT_DIR / f"series-{s:04d}"
            series_dir.mkdir(parents=True, exist_ok=True)
            for e in series_entries:
                (series_dir / f"r{e.render}-{e.sha256[:12]}-{e.size}B.pdf").write_bytes(e.data)
            (series_dir / "started.txt").write_text(
                f"{series_started.isoformat(timespec='seconds')}\n",
                encoding="utf-8",
            )
        series_results.append(series_entries)

    print("\n== Summary ==")
    print(f"Total series:      {len(series_results)}")
    print(f"Divergent series:  {len(divergent_series)} / {len(series_results)}")
    print(f"Divergent ratio:   {len(divergent_series) / max(1, len(series_results)):.1%}")

    if divergent_series:
        print("\n== Divergent series breakdown ==")
        for s in divergent_series[:20]:
            entries = series_results[s]
            hashes = [e.sha256 for e in entries]
            sizes = [e.size for e in entries]
            print(f"  series {s}: hashes={[h[:12] for h in hashes]} sizes={sizes}")

        # Aggregate: which render position diverges?
        # "Position" = index (0, 1, 2) of the render that has the rare hash.
        render_positions: dict[int, int] = defaultdict(int)
        per_series_detail: list[dict] = []
        for s in divergent_series:
            entries = series_results[s]
            hashes = [e.sha256 for e in entries]
            # Majority hash is the baseline; flag minority positions.
            count: dict[str, int] = defaultdict(int)
            for h in hashes:
                count[h] += 1
            baseline_hash = max(count, key=lambda k: count[k])
            for i, e in enumerate(entries):
                if e.sha256 != baseline_hash:
                    render_positions[i] += 1
                    per_series_detail.append(
                        {
                            "series": s,
                            "divergent_render": i,
                            "baseline_hash": baseline_hash[:16],
                            "divergent_hash": e.sha256[:16],
                            "baseline_size": next(
                                b.size for b in entries if b.sha256 == baseline_hash
                            ),
                            "divergent_size": e.size,
                            "baseline_meta": next(
                                b.pdf_meta for b in entries if b.sha256 == baseline_hash
                            ),
                            "divergent_meta": e.pdf_meta,
                        }
                    )
        print(f"\n  Divergent render-position histogram: {dict(render_positions)}")

        # Show meta deltas for first 3 divergent series
        print("\n== Meta diffs (first 3) ==")
        for d in per_series_detail[:3]:
            print(f"  series {d['series']} (divergent at render {d['divergent_render']}):")
            base_meta = d["baseline_meta"]
            div_meta = d["divergent_meta"]
            for key in sorted(set(base_meta) | set(div_meta)):
                if base_meta.get(key) != div_meta.get(key):
                    print(
                        f"    {key}:\n"
                        f"      base: {base_meta.get(key)!r}\n"
                        f"      div:  {div_meta.get(key)!r}"
                    )

        # Save diagnostics.json
        diag = {
            "args": {"series": args.series, "renders": args.renders},
            "started": datetime.now().isoformat(timespec="seconds"),
            "total_series": len(series_results),
            "divergent_series": divergent_series,
            "divergent_ratio": len(divergent_series) / max(1, len(series_results)),
            "render_position_histogram": dict(render_positions),
            "per_series_detail": per_series_detail[:50],
        }
        (OUT_DIR / "diagnostics.json").write_text(
            json.dumps(diag, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"\nDetailed diagnostics written to {OUT_DIR / 'diagnostics.json'}")
    else:
        # No divergence: still persist machine-readable evidence so the
        # diagnostic run is reproducible and auditable (hashes/sizes/order
        # and per-render wall time per series).
        print("\nNo divergence observed across the run.")
        diag = {
            "args": {"series": args.series, "renders": args.renders},
            "started": datetime.now().isoformat(timespec="seconds"),
            "total_series": len(series_results),
            "divergent_series": [],
            "divergent_ratio": 0.0,
            "render_position_histogram": {},
            "per_series_detail": [],
            "per_render_summary": [
                {
                    "series": e.series,
                    "render": e.render,
                    "sha256": e.sha256,
                    "size": e.size,
                    "wall_ms": round(e.wall_ms, 1),
                }
                for series in series_results
                for e in series
            ],
            "cold_warm_state": (
                "every render spawns a fresh typst subprocess "
                "(no in-process cache) => every render is cold; "
                "no warm-up applied"
            ),
        }
        (OUT_DIR / "diagnostics.json").write_text(
            json.dumps(diag, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"Evidence written to {OUT_DIR / 'diagnostics.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
