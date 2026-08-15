"""Component tests for the ``QM_FONTS_DIR`` env axis (Phase 6A, ADR-0032 D3/D7).

These tests run a REAL render through the Typst backend with the pinned
binary (``.spike/typst-0.15.1/...``) and the existing ``spike-waybill-typst``
template package against the ``waybill-1.typst.json`` fixture:

1. With ``QM_FONTS_DIR`` pointing to a copy of the bundled fonts the render
   succeeds and embeds DejaVu Sans.
2. With ``QM_FONTS_DIR`` pointing to an empty dir the render fails explicitly
   with ``FontNotAvailableError`` (exit 4) — no silent fallback to system
   fonts (ADR-0001 D9, TZ §7.2).
"""

from __future__ import annotations

import shutil
from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfReader
from qm_backends.typst_backend import _pinned_binary_path
from qm_engine.envelope import parse_envelope
from qm_engine.errors import FontNotAvailableError
from qm_engine.render import render_envelope

REPO = Path(__file__).resolve().parents[2]
TEMPLATES = REPO / "templates"
BUNDLE_FONTS = REPO / "fonts"
WAYBILL_TYPST = REPO / "tests" / "fixtures" / "waybill" / "waybill-1.typst.json"


def _real_binary_available() -> bool:
    path = _pinned_binary_path()
    return path is not None and path.is_file()


_skip_no_binary = pytest.mark.skipif(
    not _real_binary_available(),
    reason="real typst binary not present; run scripts/fetch_typst.py",
)


@pytest.fixture(scope="module")
def waybill_envelope():
    return parse_envelope(WAYBILL_TYPST.read_text(encoding="utf-8"))


def _render(waybill_envelope) -> bytes:
    """Drive a real render through the registry + typst backend."""
    result = render_envelope(waybill_envelope, TEMPLATES, output_format="pdf")
    assert result.data[:5] == b"%PDF-"
    return result.data


def _embedded_font_names(pdf_bytes: bytes) -> list[str]:
    reader = PdfReader(BytesIO(pdf_bytes))
    names: list[str] = []
    for page in reader.pages:
        for font_dict in (page.get("/Resources") or {}).get("/Font", {}).values():
            base = font_dict.get("/BaseFont")
            if isinstance(base, str):
                names.append(base)
    return names


@_skip_no_binary
def test_render_succeeds_with_qm_fonts_dir_copy(
    monkeypatch, tmp_path: Path, waybill_envelope
) -> None:
    """A full copy of the bundled fonts resolves and renders successfully."""
    fonts_copy = tmp_path / "fonts-copy"
    shutil.copytree(BUNDLE_FONTS, fonts_copy)
    monkeypatch.setenv("QM_FONTS_DIR", str(fonts_copy))

    pdf_bytes = _render(waybill_envelope)

    names = _embedded_font_names(pdf_bytes)
    assert any("dejavu" in name.lower().replace("-", "") for name in names), (
        f"expected DejaVu subset in PDF, got: {names}"
    )


@_skip_no_binary
def test_render_fails_explicitly_with_empty_qm_fonts_dir(
    monkeypatch, tmp_path: Path, waybill_envelope
) -> None:
    """An empty fonts dir must abort the render with FONT_NOT_AVAILABLE / exit 4."""
    empty = tmp_path / "empty-fonts"
    empty.mkdir()
    monkeypatch.setenv("QM_FONTS_DIR", str(empty))

    with pytest.raises(FontNotAvailableError) as exc:
        _render(waybill_envelope)
    assert exc.value.code == "FONT_NOT_AVAILABLE"
    assert exc.value.exit_code == 4


@_skip_no_binary
def test_render_fails_explicitly_with_missing_qm_fonts_dir(
    monkeypatch, tmp_path: Path, waybill_envelope
) -> None:
    """A nonexistent fonts dir must abort the render with FONT_NOT_AVAILABLE."""
    missing = tmp_path / "no-such-fonts"
    monkeypatch.setenv("QM_FONTS_DIR", str(missing))

    with pytest.raises(FontNotAvailableError) as exc:
        _render(waybill_envelope)
    assert exc.value.code == "FONT_NOT_AVAILABLE"
    assert exc.value.exit_code == 4


@_skip_no_binary
def test_render_uses_bundle_fonts_when_env_unset(monkeypatch, waybill_envelope) -> None:
    """Without ``QM_FONTS_DIR`` the render resolves the bundle fonts dir."""
    monkeypatch.delenv("QM_FONTS_DIR", raising=False)

    pdf_bytes = _render(waybill_envelope)

    names = _embedded_font_names(pdf_bytes)
    assert any("dejavu" in name.lower().replace("-", "") for name in names), (
        f"expected DejaVu subset in PDF, got: {names}"
    )
