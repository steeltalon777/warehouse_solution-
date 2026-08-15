"""Markdown report writer (TZ §13 deliverable).

The report is a self-contained Markdown summary intended for human
review. It is one of the artefacts the harness must produce under
``spike-out/compare/<fixture>/`` and is the entry point a
reviewer reads when triaging backend regressions.

The renderer is delegated to a small dataclass-driven helper rather
than a third-party templating engine: the report is small enough to
keep formatting decisions in plain Python, and the strings are
deterministic so two identical runs produce byte-identical reports.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class RenderHistory:
    """Render outcome for one backend.

    Captures the success flag and the (truncated) stderr that the
    qm-render subprocess produced. The harness treats any failed
    render as a REVIEW_REQUIRED marker, not as a gate failure.
    """

    backend: str
    success: bool
    stderr: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "success": self.success,
            "stderr": self.stderr,
        }


def _format_pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def _format_ssim(value: float) -> str:
    return f"{value:.4f}"


def _truncate(text: str, max_len: int = 500) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + f"\n… (truncated, {len(text)} chars total)"


def write_report(
    out_dir: Path,
    fixture_name: str,
    templates: list[str],
    *,
    structural: dict[str, dict[str, Any]],
    semantic: dict[str, dict[str, Any]],
    visual: dict[str, Any],
    calibration: dict[str, Any] | None,
    render_history: list[RenderHistory],
) -> None:
    """Write ``report.md`` and a sidecar ``summary.json`` to ``out_dir``.

    Parameters mirror the JSON artefacts produced by the harness.
    ``render_history`` is rendered as a "Render History" section at
    the top of the report so failures are visible without reading
    the JSON.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []

    # The structural/semantic dictionaries are keyed by backend
    # label (``weasy`` / ``typst``); the templates list is rendered
    # only in the header. Use the union of those keys as the iteration
    # order for the per-backend sections so we never render a section
    # for a backend that has no data.
    backend_names: list[str] = []
    seen: set[str] = set()
    for key in list(structural.keys()) + list(semantic.keys()):
        if key not in seen:
            backend_names.append(key)
            seen.add(key)

    lines.append("# Quartermaster Visual Comparison Report")
    lines.append("")
    lines.append(f"- **Fixture:** `{fixture_name}`")
    lines.append(f"- **Templates:** {', '.join(f'`{t}`' for t in templates)}")
    lines.append("")

    # --- Render history ----------------------------------------------------
    if render_history:
        lines.append("## Render History")
        lines.append("")
        for entry in render_history:
            status = "✓" if entry.success else "**REVIEW_REQUIRED**"
            lines.append(f"- {entry.backend}: {status}")
            if not entry.success and entry.stderr:
                lines.append("")
                lines.append("    ```")
                lines.append(_truncate(entry.stderr, 400))
                lines.append("    ```")
        lines.append("")

    # --- Calibration -------------------------------------------------------
    lines.append("## Calibration")
    lines.append("")
    if calibration:
        lines.append(f"- SSIM threshold: `{calibration.get('ssim_threshold', 'N/A')}`")
        lines.append(
            f"- Changed-pixels threshold: `{calibration.get('changed_pixels_threshold', 'N/A')}`"
        )
        lines.append(f"- noise-floor SSIM (min): `{calibration.get('ssim_observed_floor', 'N/A')}`")
        lines.append(
            f"- noise-floor changed-pixels (max): "
            f"`{calibration.get('changed_pixels_observed_floor', 'N/A')}`"
        )
        lines.append(f"- calibration samples: {calibration.get('n_renders', 'N/A')}")
    else:
        lines.append("- No calibration data; thresholds use conservative defaults.")
    lines.append("")

    # --- Structural -------------------------------------------------------
    lines.append("## Structural (per backend)")
    lines.append("")
    if not structural:
        lines.append("_No structural data (no backend rendered successfully)._")
        lines.append("")
    for backend in backend_names:
        s = structural.get(backend)
        if s is None:
            lines.append(f"### {backend}")
            lines.append("")
            lines.append("_Not rendered._")
            lines.append("")
            continue
        lines.append(f"### {backend}")
        lines.append("")
        lines.append(f"- page_count: `{s.get('page_count')}`")
        lines.append(f"- paper: `{s.get('paper')}`")
        lines.append(f"- orientation: `{s.get('orientation')}`")
        blocks_pass = s.get("blocks_pass", {})
        all_blocks = "✓" if s.get("all_blocks_pass") else "**REVIEW_REQUIRED**"
        lines.append(f"- blocks_pass: {all_blocks}")
        for block_name, ok in blocks_pass.items():
            mark = "✓" if ok else "✗"
            lines.append(f"  - {block_name}: {mark}")
        lines.append(
            f"- table_rows: `{s.get('table_rows')}` / `{s.get('expected_table_rows')}` expected"
        )
        for note in s.get("notes", []):
            lines.append(f"- note: {note}")
        lines.append("")

    # --- Semantic ----------------------------------------------------------
    lines.append("## Semantic (per backend)")
    lines.append("")
    any_veto = False
    if not semantic:
        lines.append("_No semantic data (no backend rendered successfully)._")
        lines.append("")
    for backend in backend_names:
        s = semantic.get(backend)
        if s is None:
            lines.append(f"### {backend}")
            lines.append("")
            lines.append("_Not rendered._")
            lines.append("")
            continue
        lines.append(f"### {backend}")
        lines.append("")
        fields = s.get("fields", {})
        if not fields:
            lines.append("_No fields checked._")
            lines.append("")
            continue
        # Compact field table.
        lines.append("| field | expected | actual | pass |")
        lines.append("|---|---|---|---|")
        for field_name, result in fields.items():
            expected = result.get("expected")
            if isinstance(expected, list):
                expected_str = " / ".join(str(e) for e in expected)
            else:
                expected_str = str(expected)
            actual = result.get("actual", [])
            actual_str = ", ".join(str(a) for a in actual) if actual else "—"
            pass_str = "✓" if result.get("pass") else "✗"
            lines.append(f"| {field_name} | `{expected_str}` | `{actual_str}` | {pass_str} |")
        if s.get("veto"):
            any_veto = True
            lines.append("")
            lines.append("**V1 VETO: semantic mismatch detected — backend must NOT be primary.**")
        lines.append("")

    # --- Visual -----------------------------------------------------------
    lines.append("## Visual (cross-backend, informational)")
    lines.append("")
    if not visual:
        lines.append("_No visual comparison data._")
        lines.append("")
    else:
        lines.append(
            f"- page_count A: `{visual.get('page_count_a')}` "
            f"page_count B: `{visual.get('page_count_b')}` "
            f"match: `{visual.get('page_count_match')}`"
        )
        thresholds = visual.get("thresholds", {})
        lines.append(
            f"- thresholds: SSIM ≥ `{thresholds.get('ssim')}`, "
            f"changed-pixels ≤ `{thresholds.get('changed_pixels')}`"
        )
        pages = visual.get("pages", {})
        if not pages:
            lines.append("- no overlapping pages")
        else:
            lines.append("")
            lines.append("| page | SSIM | changed-pixels | review |")
            lines.append("|---|---|---|---|")
            for page_key in sorted(pages.keys()):
                p = pages[page_key]
                marker = "**REVIEW_REQUIRED**" if p.get("review_required") else "ok"
                lines.append(
                    f"| {page_key} | {_format_ssim(p['ssim'])} | "
                    f"{_format_pct(p['changed_pixels'])} | {marker} |"
                )
        if visual.get("review_required"):
            lines.append("")
            lines.append("**REVIEW_REQUIRED**: visual mismatch — investigate diff artefacts.")
        lines.append("")

    # --- Summary ----------------------------------------------------------
    lines.append("## Summary")
    lines.append("")
    summary_bits: list[str] = []
    if not any_veto:
        summary_bits.append("semantic: ok (no V1 veto)")
    else:
        summary_bits.append("semantic: **V1 veto**")
    if visual.get("review_required"):
        summary_bits.append("visual: REVIEW_REQUIRED")
    else:
        summary_bits.append("visual: ok")
    render_failures = [r for r in render_history if not r.success]
    if render_failures:
        fail_list = ", ".join(r.backend for r in render_failures)
        summary_bits.append(f"render: REVIEW_REQUIRED ({fail_list})")
    else:
        summary_bits.append("render: ok")
    lines.append("- " + "; ".join(summary_bits))
    lines.append("")

    # --- Write the markdown -----------------------------------------------
    report_path = out_dir / "report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")

    # --- Sidecar JSON summary --------------------------------------------
    summary = {
        "fixture": fixture_name,
        "templates": templates,
        "structural": structural,
        "semantic": semantic,
        "visual": visual,
        "calibration": calibration,
        "render_history": [r.to_dict() for r in render_history],
        "veto": any_veto,
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
