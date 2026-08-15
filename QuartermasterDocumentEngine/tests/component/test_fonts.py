"""Component tests for bundled fonts enforcement in the WeasyPrint backend.

These tests run a real ``render_envelope`` through the WeasyPrint backend
and inspect the resulting PDF with pypdf. There are two coverage areas
required by TZ-PHASE2-BACKEND-SPIKE §8 T4:

1. The decked PDF embeds a DejaVu Sans subset (e.g. ``+DejaVuSans``).
2. ``FontNotAvailableError`` is raised (and the render is short-circuited)
   if the bundled fonts are not usable.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfReader
from qm_engine import fonts as engine_fonts
from qm_engine.envelope import parse_envelope
from qm_engine.errors import FontNotAvailableError
from qm_engine.render import render_envelope

REPO = Path(__file__).resolve().parents[2]
WAYBILL = REPO / "tests" / "fixtures" / "waybill-20.json"
TEMPLATES = REPO / "templates"


def _weasyprint_available() -> bool:
    try:
        import weasyprint  # noqa: F401
    except ImportError:
        return False
    return True


_skip_no_weasyprint = pytest.mark.skipif(
    not _weasyprint_available(),
    reason="weasyprint not installed in this environment",
)


def _embedded_font_base_names(pdf_bytes: bytes) -> list[str]:
    """Return the list of ``/BaseFont`` names under every page ``/Resources /Font`` dict."""
    reader = PdfReader(BytesIO(pdf_bytes))
    names: list[str] = []
    for page in reader.pages:
        resources = page.get("/Resources") or {}
        fonts = resources.get("/Font") or {}
        for font_dict in fonts.values():
            base = font_dict.get("/BaseFont")
            if isinstance(base, str):
                names.append(base)
    return names


def _has_dejavu_sans_subset(embedded_names: list[str]) -> bool:
    """Accept any subset prefix where ``dejavu`` and ``sans`` survive in adjacent words.

    WeasyPrint 69.0 normalises the subset prefix to either ``+DejaVuSans``
    or ``+DejaVu-Sans`` depending on the family name. The check below is
    case-insensitive and tolerant of both spellings.
    """
    for name in embedded_names:
        if "+" not in name:
            continue
        subset = name.split("+", 1)[1]
        norm = subset.lower().replace("-", "")
        if "dejavu" in norm and "sans" in norm:
            return True
    return False


@pytest.fixture(scope="module")
def waybill_envelope():
    return parse_envelope(WAYBILL.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def rendered(waybill_envelope):
    return render_envelope(waybill_envelope, TEMPLATES, output_format="pdf")


@_skip_no_weasyprint
def test_render_with_bundled_fonts_embeds_dejavu(rendered) -> None:  # type: ignore[no-untyped-def]
    """The PDF must contain a DejaVu Sans subset (``+DejaVuSans`` or ``+DejaVu-Sans``)."""
    embedded = _embedded_font_base_names(rendered.data)
    assert embedded, "PDF has no embedded font resources"
    assert _has_dejavu_sans_subset(embedded), (
        f"Expected a DejaVu Sans subset in the embedded fonts, got: {embedded}"
    )


@_skip_no_weasyprint
def test_render_missing_font_raises(monkeypatch, waybill_envelope) -> None:  # type: ignore[no-untyped-def]
    """Force ``ensure_bundled_fonts`` to raise and confirm the render aborts.

    The render is short-circuited: no PDF is produced; the
    ``FontNotAvailableError`` is surfaced unchanged.
    """
    boom = FontNotAvailableError("forced for test", {"test": True})

    def _explode() -> dict[str, object]:
        raise boom

    monkeypatch.setattr(engine_fonts, "ensure_bundled_fonts", _explode)

    with pytest.raises(FontNotAvailableError) as exc:
        render_envelope(waybill_envelope, TEMPLATES, output_format="pdf")
    assert exc.value.code == "FONT_NOT_AVAILABLE"
    assert exc.value.exit_code == 4
    assert exc.value.details == {"test": True}
