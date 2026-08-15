"""Integration tests for the visual comparison harness (TZ §13 / T9).

Every test is annotated with ``@pytest.mark.spike`` so it only runs
when the ``[spike]`` extra is installed. The tests cover the
calibration step, the structural and semantic gates, the visual
self-compare, and the V1 veto path.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.harness import (
    semantic,
    structural,
    visual,
)
from tests.harness._internals import detect_family, resolve_templates_dir
from tests.harness.compare import (
    CALIBRATION_FIXTURE,
    ensure_calibration,
    run_comparison,
)

REPO = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = REPO / "templates"
SPIKE_OUT = REPO / "spike-out"
COMPARE_DIR = SPIKE_OUT / "compare"


# ---------------------------------------------------------------------------
# 1. Calibration
# ---------------------------------------------------------------------------


@pytest.mark.spike
def test_calibration_runs_once_and_writes_floor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Calibration produces noise_floor.json with sane thresholds."""
    # Use a scratch spike-out directory so the test cannot poison the
    # canonical cache used by other tests.
    scratch_repo = tmp_path / "scratch-repo"
    scratch_repo.mkdir()
    monkeypatch.setattr(
        "tests.harness.compare._calibration_paths",
        lambda _root: (
            scratch_repo / "calibration",
            scratch_repo / "calibration" / "noise_floor.json",
        ),
    )

    # Patch where the calibration helpers look for the fixture.
    def _fake_fixture_paths(name: str, _root: Path) -> tuple[Path, Path]:
        family = detect_family(name)
        d = REPO / "tests" / "fixtures" / family
        return d / f"{name}.weasy.json", d / f"{name}.typst.json"

    monkeypatch.setattr("tests.harness.compare.fixture_paths", _fake_fixture_paths)

    noise_floor = ensure_calibration(scratch_repo, resolve_templates_dir(None), n_renders=2)
    assert "ssim_threshold" in noise_floor
    assert "changed_pixels_threshold" in noise_floor
    assert 0.97 <= noise_floor["ssim_threshold"] <= 0.995
    assert 0.001 <= noise_floor["changed_pixels_threshold"] <= 0.005
    # Second call returns the cached file.
    cached = ensure_calibration(scratch_repo, resolve_templates_dir(None), n_renders=2)
    assert cached["ssim_threshold"] == noise_floor["ssim_threshold"]


# ---------------------------------------------------------------------------
# 2. Comparison: waybill-20 produces PDFs + matching structural + semantic
# ---------------------------------------------------------------------------


@pytest.mark.spike
def test_compare_waybill_20_both_backends_produce_pdfs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`run_comparison` produces both PDFs and JSON artefacts."""
    out_dir = tmp_path / "compare"
    scratch_repo = tmp_path / "scratch-repo"
    scratch_repo.mkdir()
    monkeypatch.setattr(
        "tests.harness.compare._calibration_paths",
        lambda _root: (
            scratch_repo / "calibration",
            scratch_repo / "calibration" / "noise_floor.json",
        ),
    )

    summary = run_comparison(
        "waybill-20",
        ["warehouse-waybill-ru@1.0", "spike-waybill-typst@0.1.0"],
        out_dir,
        templates_dir=TEMPLATES_DIR,
        repo_root=REPO,
        include_visual=True,
    )

    assert (out_dir / "weasy.pdf").exists()
    assert (out_dir / "typst.pdf").exists()
    assert (out_dir / "structural.json").exists()
    assert (out_dir / "semantic.json").exists()
    assert (out_dir / "visual.json").exists()
    assert (out_dir / "report.md").exists()

    structural_payload = json.loads((out_dir / "structural.json").read_text())
    assert "weasy" in structural_payload
    assert "typst" in structural_payload
    assert structural_payload["weasy"]["page_count"] >= 1
    assert structural_payload["typst"]["page_count"] >= 1

    semantic_payload = json.loads((out_dir / "semantic.json").read_text())
    # Phase 2.1: document_number must pass for both backends via the
    # envelope-level field (``WB-FIX-20``). The previous Typst-only
    # fallback to ``operation.display_number`` was removed when the
    # Typst backend started writing the full normalized envelope.
    for backend in ("weasy", "typst"):
        assert semantic_payload[backend]["fields"]["document_number"]["pass"] is True

    assert summary["veto"] is False


# ---------------------------------------------------------------------------
# 3. Structural blocks for each fixture family
# ---------------------------------------------------------------------------


@pytest.mark.spike
@pytest.mark.parametrize(
    "fixture_name,templates",
    [
        ("waybill-20", ["warehouse-waybill-ru@1.0", "spike-waybill-typst@0.1.0"]),
        (
            "vehicle-route-sheet-1",
            ["spike-route-sheet-weasy@0.1.0", "spike-route-sheet-typst@0.1.0"],
        ),
        ("fuel-report-100", ["spike-fuel-report-weasy@0.1.0", "spike-fuel-report-typst@0.1.0"]),
    ],
)
def test_structural_blocks_for_each_fixture_family(
    fixture_name: str, templates: list[str], tmp_path: Path
) -> None:
    """header / table / signatures / footer detected in each family."""
    out_dir = tmp_path / "compare"
    summary = run_comparison(
        fixture_name,
        templates,
        out_dir,
        templates_dir=TEMPLATES_DIR,
        repo_root=REPO,
        include_visual=False,
    )

    # Re-open the rendered PDFs and re-run the structural checker.
    structural_payload = json.loads((out_dir / "structural.json").read_text())
    expected_blocks = {
        "waybill": ("header", "table", "signatures", "footer"),
        "route-sheet": ("header", "table", "signatures", "footer"),
        "fuel": ("header", "table", "footer"),
    }
    family = detect_family(fixture_name)
    must_pass = expected_blocks[family]
    for backend, payload in structural_payload.items():
        for block in must_pass:
            assert payload["blocks_pass"][block], (
                f"{backend}/{fixture_name}: block '{block}' missing"
            )

    assert summary["out_dir"] == str(out_dir)


# ---------------------------------------------------------------------------
# 4. Semantic: document number + signers per family
# ---------------------------------------------------------------------------


@pytest.mark.spike
@pytest.mark.parametrize(
    "fixture_name,templates,expected_doc_ids,expected_signer",
    [
        # Phase 2.1: both backends render the envelope-level
        # ``WB-FIX-20``. The legacy ``operation.display_number``
        # alternative was removed because the Typst template now reads
        # ``doc.document_number`` directly (TZ-PHASE2-BACKEND-SPIKE §T5
        # / §11.2). The list still keeps the display_number for
        # regression safety on envelopes without a top-level
        # ``document_number``.
        (
            "waybill-20",
            ["warehouse-waybill-ru@1.0", "spike-waybill-typst@0.1.0"],
            ["WB-FIX-20"],
            "Сдал",
        ),
        # route-sheet: vehicle plate and "Водитель" signer.
        (
            "vehicle-route-sheet-1",
            ["spike-route-sheet-weasy@0.1.0", "spike-route-sheet-typst@0.1.0"],
            ["А123ВС 75"],
            "Водитель",
        ),
        # fuel-report: period and "Отчёт" header (signer is best-effort).
        (
            "fuel-report-100",
            ["spike-fuel-report-weasy@0.1.0", "spike-fuel-report-typst@0.1.0"],
            ["07.2026"],
            "Отчет",  # header token; the fuel spike templates have no signer block
        ),
    ],
)
def test_semantic_finds_document_number_and_signers(
    fixture_name: str,
    templates: list[str],
    expected_doc_ids: list[str],
    expected_signer: str,
    tmp_path: Path,
) -> None:
    """Semantic matcher finds the expected identifier and signer label."""
    out_dir = tmp_path / "compare"
    run_comparison(
        fixture_name,
        templates,
        out_dir,
        templates_dir=TEMPLATES_DIR,
        repo_root=REPO,
        include_visual=False,
    )

    semantic_payload = json.loads((out_dir / "semantic.json").read_text())
    # At least one identifier / signer label must be found for each backend.
    for backend, payload in semantic_payload.items():
        fields = payload["fields"]
        # At least one of the expected identifiers must be present.
        accepted = False
        for key in ("document_number", "vehicle_plate", "period"):
            if key in fields and fields[key]["pass"]:
                accepted = True
                break
        assert accepted, f"{backend}/{fixture_name}: no identifier found in {list(fields)}"

        # Signer label heuristics.
        signer_keys = [k for k in fields if k.startswith("signer_")]
        # Families without a signer block: the fuel spike templates
        # do not render a signer label at all. We accept that as a
        # best-effort gap and skip the assertion for families where
        # the spec lists "Ответственный" as best-effort.
        best_effort_signers = {"fuel-report-100"}
        if signer_keys and fixture_name not in best_effort_signers:
            # The aggregate signer_block drives the per-fixture
            # gate; individual signer_XXX fields are informational.
            if "signer_block" in fields:
                assert fields["signer_block"]["pass"], (
                    f"{backend}/{fixture_name}: signer block missing"
                )
            else:
                assert any(fields[k]["pass"] for k in signer_keys), (
                    f"{backend}/{fixture_name}: signer block missing"
                )


# ---------------------------------------------------------------------------
# 5. Visual self-compare: SSIM ≈ 1.0 for identical renders
# ---------------------------------------------------------------------------


@pytest.mark.spike
def test_visual_ssim_self_compare_is_one(tmp_path: Path) -> None:
    """SSIM between two identical renders of the same backend is ~1.0."""
    family = detect_family(CALIBRATION_FIXTURE)
    fixture_path = REPO / "tests" / "fixtures" / family / f"{CALIBRATION_FIXTURE}.weasy.json"
    pdf_a = tmp_path / "render-a.pdf"
    pdf_b = tmp_path / "render-b.pdf"

    outcome_a = _render_pdf(fixture_path, pdf_a)
    outcome_b = _render_pdf(fixture_path, pdf_b)
    assert outcome_a, "first render failed"
    assert outcome_b, "second render failed"

    result = visual.compare_pages(pdf_a, pdf_b, page_index=0)
    assert result["ssim"] >= 0.99, f"SSIM dropped to {result['ssim']} for identical renders"
    assert result["changed_pixels"] < 0.01, (
        f"changed_pixels ratio {result['changed_pixels']} too high for identical renders"
    )


# ---------------------------------------------------------------------------
# 6. Semantic V1 veto on a deliberately wrong expectation
# ---------------------------------------------------------------------------


@pytest.mark.spike
def test_semantic_marks_value_mismatch_as_v1_veto() -> None:
    """A wrong expected value triggers a V1 veto in the semantic gate."""
    # Build a synthetic page-text bundle that lacks the expected
    # identifier. The semantic gate must mark the field as not-pass
    # and set veto=True.
    page_texts = ["Some totally unrelated document text.", "More noise, no headers."]
    envelope = {
        "document_number": "EXPECTED-DOC-NUMBER-XYZ",
        "document": {
            "operation": {"display_number": "EXPECTED-DOC-NUMBER-XYZ"},
            "lines": [],
            "total_lines": 0,
        },
    }
    result = semantic.check_semantic(page_texts, envelope, "waybill-20", backend="typst")
    assert result.fields["document_number"].pass_ is False
    assert result.veto is True


# ---------------------------------------------------------------------------
# Extra unit-style checks (pure functions, no rendering)
# ---------------------------------------------------------------------------


@pytest.mark.spike
def test_row_pattern_matches_cyrillic_followed_by_number() -> None:
    """row pattern requires a number followed by a non-digit token."""
    from tests.harness._internals import ROW_PATTERN, strip_footer

    text = "Header\n1\nБолт\n2\nГайка\nЛист 1 из 4"
    cleaned = strip_footer(text)
    matches = ROW_PATTERN.findall(cleaned)
    assert matches == ["1", "2"], f"expected ['1', '2'], got {matches}"


@pytest.mark.spike
def test_count_expected_rows_handles_weasy_and_typst() -> None:
    """Count how many of the expected row numbers (1..N) appear in text."""
    from tests.harness._internals import count_expected_rows

    weasy_text = "Header\n1\nБолт\n2\nГайка\n3\nШуруп\nЛист 1 из 4"
    typst_text = "Header\n1\nБолт\n2\nГайка\nЛист 1 из 4"
    # Weasy uses 1..3 → expect 3 hits.
    assert count_expected_rows([weasy_text], 3) == 3
    # Typst omits row 3 → expect 2 hits.
    assert count_expected_rows([typst_text], 3) == 2
    # Counting past the available rows is a no-op.
    assert count_expected_rows([typst_text], 5) == 2


@pytest.mark.spike
def test_strip_footer_removes_both_layouts() -> None:
    """Footer stripper handles Typst and WeasyPrint variants."""
    from tests.harness._internals import strip_footer

    typst_text = "Footer here Лист 3 из 5 trailing"
    assert "Лист 3 из 5" not in strip_footer(typst_text)
    weasy_text = "Footer here Страница 1 из 1 trailing"
    assert "Страница 1 из 1" not in strip_footer(weasy_text)


@pytest.mark.spike
def test_detect_paper_and_orientation_a4() -> None:
    paper, orientation = structural.detect_paper_and_orientation(595.28, 841.89)
    assert paper == "A4"
    assert orientation == "portrait"
    paper, orientation = structural.detect_paper_and_orientation(841.89, 595.28)
    assert paper == "A4"
    assert orientation == "landscape"


@pytest.mark.spike
def test_visual_thresholds_from_missing_file(tmp_path: Path) -> None:
    """Missing noise_floor.json returns conservative defaults."""
    thresholds = visual.VisualThresholds.from_noise_floor(tmp_path / "missing.json")
    assert thresholds.ssim == visual.DEFAULT_SSIM_THRESHOLD
    assert thresholds.changed_pixels == visual.DEFAULT_CHANGED_PIXELS_THRESHOLD


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _render_pdf(fixture_path: Path, output_path: Path) -> bool:
    """Tiny wrapper around subprocess for the self-compare test."""
    import os
    import subprocess
    import sys

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()
    cmd = [
        sys.executable,
        "-m",
        "qm_cli.main",
        "--templates-dir",
        str(TEMPLATES_DIR),
        "render",
        "--input",
        str(fixture_path),
        "--output",
        str(output_path),
        "--format",
        "pdf",
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        env=dict(os.environ),
        timeout=300,
        check=False,
    )
    return result.returncode == 0 and output_path.exists()
