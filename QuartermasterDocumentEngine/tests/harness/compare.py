"""Visual comparison CLI (TZ §13 / T9).

Entry point:
``python -m tests.harness.compare --fixture <name> --templates <id@ver>,<id@ver> --out <dir>``.

The CLI renders both backends via the qm-render subprocess
(black-box observer), then runs the structural, semantic and visual
checkers and writes the report plus raw JSON artefacts under
``--out``. The :func:`run_comparison` function is the same code path
the tests use — the click decorator is only a thin wrapper.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

import click

from tests.harness import (
    raster,
    report,
    semantic,
    structural,
    visual,
)
from tests.harness._internals import (
    fixture_paths,
    render_pdf,
    resolve_templates_dir,
    safe_load_json,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------

CALIBRATION_DIRNAME = "calibration"
NOISE_FLOOR_FILENAME = "noise_floor.json"
CALIBRATION_FIXTURE = "waybill-20"
CALIBRATION_RENDERS = 5


def _calibration_paths(repo_root: Path) -> tuple[Path, Path]:
    """Return ``(calibration_dir, noise_floor.json)`` under spike-out/."""
    spike_out = repo_root / "spike-out"
    calibration_dir = spike_out / CALIBRATION_DIRNAME
    return calibration_dir, calibration_dir / NOISE_FLOOR_FILENAME


def ensure_calibration(
    repo_root: Path,
    templates_dir: Path,
    *,
    fixture_name: str = CALIBRATION_FIXTURE,
    n_renders: int = CALIBRATION_RENDERS,
) -> dict[str, Any]:
    """Compute the noise floor once and write ``noise_floor.json``.

    Returns the JSON content as a dict. The first call renders the
    waybill fixture five times per backend and stores the SSIM and
    changed-pixels distributions; subsequent calls load the cached
    file instead of re-rendering.

    The calibration deliberately uses a small fixture (waybill-20)
    because the noise floor is a property of the rendering pipeline,
    not of the document size.
    """
    calibration_dir, noise_floor_path = _calibration_paths(repo_root)
    if noise_floor_path.exists():
        try:
            cached: dict[str, Any] = json.loads(noise_floor_path.read_text(encoding="utf-8"))
            return cached
        except (json.JSONDecodeError, OSError):
            # Bad cache: recompute.
            logger.warning("recomputing noise floor: cache file is unreadable")

    calibration_dir.mkdir(parents=True, exist_ok=True)
    weasy_fixture, typst_fixture = fixture_paths(fixture_name, repo_root)
    pairs: list[tuple[str, Path]] = [
        ("weasy", weasy_fixture),
        ("typst", typst_fixture),
    ]

    ssim_samples: list[float] = []
    changed_samples: list[float] = []
    for backend, fixture_path in pairs:
        outputs: list[Path] = []
        for i in range(n_renders):
            output_path = calibration_dir / f"calib-{backend}-{i}.pdf"
            outcome = render_pdf(fixture_path, output_path, templates_dir)
            if not outcome.success:
                logger.warning(
                    "calibration render failed for %s (%s): %s",
                    backend,
                    i,
                    outcome.stderr,
                )
                continue
            outputs.append(output_path)
        if len(outputs) < 2:
            logger.warning("not enough %s renders for calibration", backend)
            continue
        # SSIM/CHANGED between all pairs of the same backend.
        for i in range(len(outputs)):
            for j in range(i + 1, len(outputs)):
                result = visual.compare_pages(outputs[i], outputs[j], page_index=0)
                ssim_samples.append(result["ssim"])
                changed_samples.append(result["changed_pixels"])

    if not ssim_samples:
        raise RuntimeError("calibration produced no samples — renders failed")

    observed_floor_ssim = min(ssim_samples)
    observed_floor_changed = max(changed_samples)
    ssim_threshold = max(min(0.995, observed_floor_ssim), 0.97)
    changed_threshold = max(min(0.005, observed_floor_changed), 0.001)

    noise_floor = {
        "fixture": fixture_name,
        "n_renders": n_renders,
        "ssim_observed_floor": observed_floor_ssim,
        "changed_pixels_observed_floor": observed_floor_changed,
        "ssim_threshold": ssim_threshold,
        "changed_pixels_threshold": changed_threshold,
        "samples": {
            "ssim": ssim_samples,
            "changed_pixels": changed_samples,
        },
    }
    noise_floor_path.write_text(
        json.dumps(noise_floor, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return noise_floor


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


def _backend_label_for_template(template: str, templates_dir: Path | None = None) -> str:
    """Return the backend label implied by a template id@version.

    The authoritative source is the template's manifest
    (``backend: typst | weasyprint``) resolved through the registry;
    the id-suffix heuristics below are the fallback for template
    dirs where the manifest is unavailable. Manifest-based resolution
    is required for the canonical pair (``warehouse-waybill-ru@1.0``
    is weasyprint while ``warehouse-waybill-ru@2.0.0`` is typst).
    """
    template_id, _, version = template.partition("@")
    if templates_dir is not None:
        try:
            from qm_engine.registry import Registry

            package = Registry(templates_dir).lookup(template_id, version)
            backend = str(package.manifest.get("backend", ""))
            if backend == "typst":
                return "typst"
            if backend == "weasyprint":
                return "weasy"
        except Exception:  # noqa: BLE001 - fall back to heuristics
            pass
    if template_id.endswith("-typst"):
        return "typst"
    if template_id.endswith("-weasy") or template_id == "warehouse-waybill-ru":
        return "weasy"
    # Last-resort default: the template id suffixes the backend name.
    return "unknown"


def _template_to_fixture(
    template: str,
    available_paths: dict[str, Path],
    default: Path,
) -> Path:
    """Pick the right fixture file for a given template.

    The fixture's ``template_id``/``template_version`` fields are the
    authoritative source of truth: the envelope that pins
    ``template`` is the one to render. When no fixture pins the
    template, fall back to the legacy suffix-based mapping (weasy/typst
    pair sharing the logical stem).
    """
    template_id, _, version = template.partition("@")
    for candidate in available_paths.values():
        if not candidate.exists():
            continue
        try:
            envelope = safe_load_json(candidate)
        except Exception:  # noqa: BLE001 - skip unreadable fixtures
            continue
        if (
            str(envelope.get("template_id", "")) == template_id
            and str(envelope.get("template_version", "")) == version
        ):
            return candidate
    backend = _backend_label_for_template(template)
    candidate = available_paths.get(backend)
    if candidate is not None:
        return candidate
    return default


def run_comparison(
    fixture_name: str,
    templates: list[str],
    out_dir: Path,
    *,
    templates_dir: Path | None = None,
    repo_root: Path | None = None,
    include_visual: bool = True,
) -> dict[str, Any]:
    """Run the full comparison pipeline for one fixture.

    Used by both the CLI and the test suite. The function returns
    the summary dict; it also writes JSON artefacts and the markdown
    report under ``out_dir``.

    Parameters
    ----------
    fixture_name:
        Logical name (e.g. ``waybill-20``); the function resolves
        the actual fixture paths under ``tests/fixtures/<family>/``.
    templates:
        List of ``template_id@version`` strings (one per backend).
    out_dir:
        Where the artefacts are written. Always created.
    templates_dir:
        Optional override for the templates directory. Defaults to
        the env/bundle default.
    repo_root:
        Optional override for the repository root. Defaults to the
        current working directory.
    include_visual:
        When False, skip rasterization and SSIM (used by tests that
        only need structural/semantic checks).
    """
    if len(templates) < 2:
        raise ValueError("comparison requires at least two templates")

    repo_root = (repo_root or Path.cwd()).resolve()
    templates_dir = (templates_dir or resolve_templates_dir(None)).resolve()
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # Map template → fixture file.
    weasy_fixture, typst_fixture = fixture_paths(fixture_name, repo_root)
    available = {"weasy": weasy_fixture, "typst": typst_fixture}
    default_fixture = weasy_fixture if weasy_fixture.exists() else typst_fixture
    template_to_fixture: dict[str, Path] = {}
    for template in templates:
        template_to_fixture[template] = _template_to_fixture(
            template, available, default_fixture
        )

    # Render both backends.
    render_history: list[report.RenderHistory] = []
    pdf_paths: dict[str, Path] = {}
    envelope_paths: dict[str, Path] = {}
    for template in templates:
        fixture_path = template_to_fixture[template]
        backend = _backend_label_for_template(template, templates_dir)
        output_pdf = out_dir / f"{backend}.pdf"
        outcome = render_pdf(fixture_path, output_pdf, templates_dir)
        render_history.append(
            report.RenderHistory(
                backend=backend,
                success=outcome.success,
                stderr=outcome.stderr,
            )
        )
        if outcome.success:
            pdf_paths[backend] = output_pdf
            envelope_paths[backend] = fixture_path

    # Ensure calibration before any visual step.
    if include_visual:
        try:
            calibration = ensure_calibration(repo_root, templates_dir)
        except RuntimeError as exc:
            logger.warning("calibration failed: %s", exc)
            calibration = None
    else:
        calibration = None

    # --- Structural + semantic -------------------------------------------
    structural_results: dict[str, dict[str, Any]] = {}
    semantic_results: dict[str, dict[str, Any]] = {}
    for backend, pdf_path in pdf_paths.items():
        envelope = safe_load_json(envelope_paths[backend])
        try:
            s_result = structural.check_structural(pdf_path, envelope, fixture_name)
        except Exception as exc:  # noqa: BLE001 - never abort the harness
            render_history.append(
                report.RenderHistory(
                    backend=f"{backend}:structural",
                    success=False,
                    stderr=f"structural check failed: {exc}",
                )
            )
        else:
            structural_results[backend] = s_result.to_dict()

        try:
            sem_result = semantic.check_semantic(
                [_page_text(pdf_path, i) for i in range(_page_count(pdf_path))],
                envelope,
                fixture_name,
                backend,
            )
        except Exception as exc:  # noqa: BLE001
            render_history.append(
                report.RenderHistory(
                    backend=f"{backend}:semantic",
                    success=False,
                    stderr=f"semantic check failed: {exc}",
                )
            )
        else:
            semantic_results[backend] = sem_result.to_dict()

    # --- Visual ----------------------------------------------------------
    visual_summary: dict[str, Any] = {}
    if include_visual and len(pdf_paths) == 2:
        be_a, be_b = sorted(pdf_paths.keys())
        thresholds = visual.VisualThresholds.from_noise_floor(_calibration_paths(repo_root)[1])
        # Rasterize first.
        for backend, pdf_path in pdf_paths.items():
            raster_dir = out_dir / "raster" / backend
            raster.rasterize_pdf(pdf_path, raster_dir)
        try:
            visual_summary = visual.compare_pdfs(pdf_paths[be_a], pdf_paths[be_b], thresholds)
        except Exception as exc:  # noqa: BLE001
            render_history.append(
                report.RenderHistory(
                    backend="visual",
                    success=False,
                    stderr=f"visual comparison failed: {exc}",
                )
            )
        # Per-page diff PNGs.
        if visual_summary.get("pages"):
            for page_key in sorted(visual_summary["pages"].keys()):
                page_idx = int(page_key.split("-")[1]) - 1
                diff_path = out_dir / "visual" / f"{page_key}.diff.png"
                try:
                    visual.write_diff_png(pdf_paths[be_a], pdf_paths[be_b], page_idx, diff_path)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("diff PNG for %s failed: %s", page_key, exc)

    # --- Raw JSON artefacts ---------------------------------------------
    (out_dir / "structural.json").write_text(
        json.dumps(structural_results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (out_dir / "semantic.json").write_text(
        json.dumps(semantic_results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (out_dir / "visual.json").write_text(
        json.dumps(visual_summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # --- Report -----------------------------------------------------------
    report.write_report(
        out_dir,
        fixture_name,
        templates,
        structural=structural_results,
        semantic=semantic_results,
        visual=visual_summary,
        calibration=calibration,
        render_history=render_history,
    )

    any_veto = any(s.get("veto") for s in semantic_results.values())
    return {
        "out_dir": str(out_dir),
        "structural": structural_results,
        "semantic": semantic_results,
        "visual": visual_summary,
        "calibration": calibration,
        "render_history": [r.to_dict() for r in render_history],
        "veto": any_veto,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _page_count(pdf_path: Path) -> int:
    """Return the number of pages in ``pdf_path`` (lazy pymupdf)."""
    import pymupdf  # spike extra, lazy

    doc = pymupdf.open(pdf_path)  # type: ignore[no-untyped-call]
    try:
        return len(doc)
    finally:
        doc.close()  # type: ignore[no-untyped-call]


def _page_text(pdf_path: Path, page_index: int) -> str:
    """Return the text of a single page (lazy pymupdf)."""
    import pymupdf  # spike extra, lazy

    doc = pymupdf.open(pdf_path)  # type: ignore[no-untyped-call]
    try:
        text: str = doc[page_index].get_text()  # type: ignore[no-untyped-call]
        return text
    finally:
        doc.close()  # type: ignore[no-untyped-call]


# ---------------------------------------------------------------------------
# Click CLI
# ---------------------------------------------------------------------------


@click.command("compare")
@click.option(
    "--fixture",
    "fixture_name",
    required=True,
    help="Logical fixture name (e.g. waybill-20, vehicle-route-sheet-1, fuel-report-100).",
)
@click.option(
    "--templates",
    "templates",
    required=True,
    help='Comma-separated template ids, e.g. "warehouse-waybill-ru@1.0,spike-waybill-typst@0.1.0".',
)
@click.option(
    "--out",
    "out_dir",
    required=True,
    type=click.Path(path_type=Path),
    help="Output directory (will be created).",
)
@click.option(
    "--templates-dir",
    "templates_dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=None,
    help="Override the templates directory (env QM_TEMPLATES_DIR also honoured).",
)
@click.option(
    "--repo-root",
    "repo_root",
    type=click.Path(path_type=Path, file_okay=False),
    default=None,
    help="Override the repository root (default: cwd).",
)
@click.option(
    "--skip-visual",
    is_flag=True,
    default=False,
    help="Skip rasterization and SSIM (structural + semantic only).",
)
def main(
    fixture_name: str,
    templates: str,
    out_dir: Path,
    templates_dir: Path | None,
    repo_root: Path | None,
    skip_visual: bool,
) -> None:
    """Compare two backends' renders for one fixture."""
    template_list = [t.strip() for t in templates.split(",") if t.strip()]
    repo_root_resolved = (repo_root or Path.cwd()).resolve()
    td_resolved = (
        resolve_templates_dir(str(templates_dir) if templates_dir else None)
        if templates_dir
        else None
    )
    summary = run_comparison(
        fixture_name,
        template_list,
        out_dir,
        templates_dir=td_resolved,
        repo_root=repo_root_resolved,
        include_visual=not skip_visual,
    )
    click.echo(
        json.dumps(
            {
                "out_dir": summary["out_dir"],
                "veto": summary["veto"],
                "render_history": summary["render_history"],
            },
            ensure_ascii=False,
        )
    )
    if summary["veto"]:
        sys.exit(2)


if __name__ == "__main__":
    main()
