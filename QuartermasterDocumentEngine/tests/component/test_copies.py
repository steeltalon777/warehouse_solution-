"""Component tests for engine-level copies (TZ-PHASE2-BACKEND-SPIKE §T8).

The Typst-backed tests are guarded by ``_real_binary_available()`` and
skipped if the pinned typst binary is absent. The WeasyPrint-backed
tests and the CLI smoke are unconditional (WeasyPrint is a Phase 1
dependency).
"""

from __future__ import annotations

import json
import os
import subprocess
from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfReader
from qm_backends.typst_backend import _pinned_binary_path
from qm_engine.envelope import Envelope
from qm_engine.render import render_envelope

REPO = Path(__file__).resolve().parents[2]
QM = REPO / ".venv" / "bin" / "qm-render"
TEMPLATES = REPO / "templates"
WAYBILL_TYPST = REPO / "tests" / "fixtures" / "waybill" / "waybill-20.typst.json"
ROUTE_SHEET_WEASY = REPO / "tests" / "fixtures" / "route-sheet" / "vehicle-route-sheet-1.weasy.json"
WAYBILL_WEASY = REPO / "tests" / "fixtures" / "waybill-20.json"


def _weasyprint_available() -> bool:
    try:
        import weasyprint  # noqa: F401
    except ImportError:
        return False
    return True


def _typst_binary_available() -> bool:
    path = _pinned_binary_path()
    return path is not None and path.is_file()


_skip_no_weasyprint = pytest.mark.skipif(
    not _weasyprint_available(),
    reason="weasyprint not installed in this environment",
)
_skip_no_typst = pytest.mark.skipif(
    not _typst_binary_available(),
    reason="real typst binary not present; run scripts/fetch_typst.py",
)


def _load_envelope(path: Path) -> Envelope:
    return Envelope(json.loads(path.read_bytes()))


def _all_text(pdf_bytes: bytes) -> str:
    return "".join((p.extract_text() or "") for p in PdfReader(BytesIO(pdf_bytes)).pages)


# --- Typst backend: page-count doubling + banner text ----------------------


@_skip_no_typst
def test_render_with_copies_two_doubles_pages_typst() -> None:
    """``copies=2`` via Typst backend: result.page_count = 2 × single."""
    env = _load_envelope(WAYBILL_TYPST)
    single = render_envelope(env, TEMPLATES, render_options={"copies": 1})
    double = render_envelope(env, TEMPLATES, render_options={"copies": 2})
    assert single.page_count is not None
    assert double.page_count is not None
    assert double.page_count == 2 * single.page_count
    assert double.data[:5] == b"%PDF-"


@_skip_no_typst
def test_render_with_copies_two_includes_banner_typst() -> None:
    """``copies=2`` via Typst: both banners present in extracted text."""
    env = _load_envelope(WAYBILL_TYPST)
    result = render_envelope(env, TEMPLATES, render_options={"copies": 2})
    text = _all_text(result.data)
    assert "Экземпляр 1 из 2" in text
    assert "Экземпляр 2 из 2" in text


@_skip_no_typst
def test_render_with_copies_one_no_banner_typst() -> None:
    """``copies=1`` must not print a banner (TZ §T8 invariant 6)."""
    env = _load_envelope(WAYBILL_TYPST)
    result = render_envelope(env, TEMPLATES, render_options={"copies": 1})
    text = _all_text(result.data)
    assert "Экземпляр" not in text


# --- WeasyPrint backend: banner text + page-count doubling ----------------


@_skip_no_weasyprint
def test_render_with_copies_two_includes_banner_weasyprint() -> None:
    """``copies=2`` via WeasyPrint spike-route-sheet: both banners."""
    env = _load_envelope(ROUTE_SHEET_WEASY)
    result = render_envelope(env, TEMPLATES, render_options={"copies": 2})
    text = _all_text(result.data)
    assert "Экземпляр 1 из 2" in text
    assert "Экземпляр 2 из 2" in text


@_skip_no_weasyprint
def test_render_with_copies_one_no_banner_weasyprint() -> None:
    """``copies=1`` via WeasyPrint spike-route-sheet: no banner."""
    env = _load_envelope(ROUTE_SHEET_WEASY)
    result = render_envelope(env, TEMPLATES, render_options={"copies": 1})
    text = _all_text(result.data)
    assert "Экземпляр" not in text


@_skip_no_weasyprint
def test_render_with_copies_two_doubles_pages_weasyprint() -> None:
    env = _load_envelope(ROUTE_SHEET_WEASY)
    single = render_envelope(env, TEMPLATES, render_options={"copies": 1})
    double = render_envelope(env, TEMPLATES, render_options={"copies": 2})
    assert single.page_count is not None
    assert double.page_count is not None
    assert double.page_count == 2 * single.page_count


@_skip_no_weasyprint
def test_render_with_copies_three_concatenates_pages_weasyprint() -> None:
    """``copies=3`` is supported and page-counts triple."""
    env = _load_envelope(ROUTE_SHEET_WEASY)
    single = render_envelope(env, TEMPLATES, render_options={"copies": 1})
    triple = render_envelope(env, TEMPLATES, render_options={"copies": 3})
    assert single.page_count is not None
    assert triple.page_count == 3 * single.page_count
    text = _all_text(triple.data)
    for n in (1, 2, 3):
        assert f"Экземпляр {n} из 3" in text


# --- CLI smoke -------------------------------------------------------------


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(QM), *args],
        capture_output=True,
        env=dict(os.environ),
        timeout=120,
        check=False,
    )


@_skip_no_typst
def test_render_with_copies_two_via_cli_typst(tmp_path: Path) -> None:
    """End-to-end CLI: ``qm-render render --copies 2`` on the typst waybill."""
    out = tmp_path / "copies-2.pdf"
    r = _run_cli(
        "render",
        "--input",
        str(WAYBILL_TYPST),
        "--output",
        str(out),
        "--copies",
        "2",
    )
    assert r.returncode == 0, r.stderr.decode()
    assert out.read_bytes()[:5] == b"%PDF-"
    text = _all_text(out.read_bytes())
    assert "Экземпляр 1 из 2" in text
    assert "Экземпляр 2 из 2" in text


@_skip_no_weasyprint
def test_render_with_copies_two_via_cli_weasyprint(tmp_path: Path) -> None:
    """End-to-end CLI: ``qm-render render --copies 2`` on the weasy route sheet."""
    out = tmp_path / "copies-2.pdf"
    r = _run_cli(
        "render",
        "--input",
        str(ROUTE_SHEET_WEASY),
        "--output",
        str(out),
        "--copies",
        "2",
    )
    assert r.returncode == 0, r.stderr.decode()
    assert out.read_bytes()[:5] == b"%PDF-"
    text = _all_text(out.read_bytes())
    assert "Экземпляр 1 из 2" in text
    assert "Экземпляр 2 из 2" in text


@_skip_no_weasyprint
def test_render_via_cli_copies_one_matches_no_flag(tmp_path: Path) -> None:
    """CLI: ``--copies 1`` and no flag both succeed and produce valid PDFs.

    Note: WeasyPrint's PDF stream is non-deterministic across separate
    processes (FlateDecode length varies), so byte-identicality is
    only checked in-process (unit tests). Here we verify both
    invocations succeed and emit a valid PDF with the same page count.
    """
    out_a = tmp_path / "with-flag.pdf"
    out_b = tmp_path / "without-flag.pdf"
    r_a = _run_cli(
        "render",
        "--input",
        str(WAYBILL_WEASY),
        "--output",
        str(out_a),
        "--copies",
        "1",
    )
    r_b = _run_cli("render", "--input", str(WAYBILL_WEASY), "--output", str(out_b))
    assert r_a.returncode == 0, r_a.stderr.decode()
    assert r_b.returncode == 0, r_b.stderr.decode()
    assert out_a.read_bytes()[:5] == b"%PDF-"
    assert out_b.read_bytes()[:5] == b"%PDF-"
    pages_a = len(PdfReader(BytesIO(out_a.read_bytes())).pages)
    pages_b = len(PdfReader(BytesIO(out_b.read_bytes())).pages)
    assert pages_a == pages_b


def test_render_via_cli_copies_zero_rejected(tmp_path: Path) -> None:
    """CLI: ``--copies 0`` is rejected by click (IntRange min=1)."""
    r = _run_cli(
        "render",
        "--input",
        str(WAYBILL_WEASY),
        "--output",
        str(tmp_path / "out.pdf"),
        "--copies",
        "0",
    )
    assert r.returncode != 0
