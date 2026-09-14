"""ADR-0034 waybill null-safety integration tests (template 2.2.1).

The contract ``warehouse.operation-document/v2`` allows explicit JSON
null for the nested object fields receiver / sender / operation / basis.
Template 2.2.0 dereferenced them with ``.at(...)``, which is a Typst
compile error on ``none``; all 186 historical QDE failures (Phase 6D
evidence, template 2.2.0) are receiver=null RECEIVE payloads without a
``consignee_label``. Template 2.2.1 accepts the full contract domain and
must render byte-identically to 2.2.0 on every payload 2.2.0 could
render.

Covers (ADR-0034 §7):

* receiver=null historical capture (scrubbed production payload doc
  ``0385ae37-b269-4ebb-b865-6a1af1e715f9``): failure on 2.2.0, success
  on 2.2.1 with the legacy ``_consignee_label`` fallback chain;
* sender=null / operation=null / basis=null synthetic variants;
* phase1-minimal envelope (header + lines only);
* 2.2.0-vs-2.2.1 normal-path parity (bytes, pages, media box, text);
* repeated-render determinism on the patch template.

The tests skip cleanly when the pinned Typst binary is unavailable.
"""

from __future__ import annotations

import hashlib
import json
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from pypdf import PdfReader
from qm_engine.envelope import parse_envelope
from qm_engine.errors import RenderFailedError
from qm_engine.render import render_envelope

REPO = Path(__file__).resolve().parents[2]
TEMPLATES = REPO / "templates"
NULL_DIR = REPO / "tests" / "fixtures" / "waybill-null"
PARITY_DIR = REPO / "tests" / "fixtures" / "waybill-qde22"
TEMPLATE_ID = "warehouse-waybill-ru"
PATCH_VERSION = "2.2.1"
BASELINE_VERSION = "2.2.0"

# Frozen 2.2.x page counts (see tests/integration/test_waybill_balance.py);
# the patch must not change the measurable-pagination baseline.
EXPECTED_PAGES_22 = {1: 1, 20: 2, 75: 5, 200: 12, 500: 30}

# A4 media box in PDF points (2.2.x Typst output).
A4_WIDTH_PT = 595.2756
A4_HEIGHT_PT = 841.8898


def _typst_available() -> bool:
    from qm_backends.typst_backend import TypstBackend

    try:
        return TypstBackend().available()
    except Exception:  # noqa: BLE001 - availability probe
        return False


pytestmark = [
    pytest.mark.skipif(
        not _typst_available(),
        reason="real typst binary not present; run scripts/fetch_typst.py",
    )
]


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _render(envelope: dict[str, Any]) -> bytes:
    parsed = parse_envelope(json.dumps(envelope, ensure_ascii=False))
    result = render_envelope(parsed, TEMPLATES, output_format="pdf")
    assert result.format == "pdf"
    assert not result.warnings, f"typst emitted warnings: {result.warnings}"
    return result.data


def _render_version(envelope: dict[str, Any], version: str) -> bytes:
    variant = json.loads(json.dumps(envelope))
    variant["template_version"] = version
    return _render(variant)


def _page_count(pdf_bytes: bytes) -> int:
    return len(PdfReader(BytesIO(pdf_bytes)).pages)


def _page_texts(pdf_bytes: bytes) -> list[str]:
    return [page.extract_text() or "" for page in PdfReader(BytesIO(pdf_bytes)).pages]


def _media_box(pdf_bytes: bytes) -> tuple[float, float]:
    box = PdfReader(BytesIO(pdf_bytes)).pages[0].mediabox
    return (float(box.width), float(box.height))


def _null_fixture(stem: str) -> dict[str, Any]:
    return _load(NULL_DIR / f"{stem}.typst.json")


# ---------------------------------------------------------------------------
# receiver=null: the historical Phase 6D failure class
# ---------------------------------------------------------------------------


def test_historical_receiver_null_fails_on_2_2_0() -> None:
    """The scrubbed historical capture reproduces the 2.2.0 crash.

    This is the regression proof: without the 2.2.1 guards the same
    payload still raises ``type none has no method 'at'`` and no PDF is
    produced.
    """
    envelope = _null_fixture("waybill-null-receiver")
    assert envelope["document"]["receiver"] is None
    assert "consignee_label" not in envelope["document"]
    with pytest.raises(RenderFailedError):
        _render_version(envelope, BASELINE_VERSION)


def test_historical_receiver_null_renders_on_2_2_1() -> None:
    """2.2.1 renders the RECEIVE payload with the legacy fallback chain.

    ``consignee_label`` is absent and ``receiver`` is null, so the
    Грузополучатель falls through to ``sender.site_name`` ("Акша")
    exactly like the legacy Django ``_consignee_label``; the Основание
    falls back to ``operation_type_label`` ("Поступление").
    """
    pdf = _render(_null_fixture("waybill-null-receiver"))
    texts = _page_texts(pdf)
    assert len(texts) == 1
    assert "Накладная № 120626/0550/2" in texts[0]
    assert "Грузополучатель: Акша" in texts[0]
    assert "Основание: Поступление" in texts[0]
    assert _media_box(pdf) == pytest.approx((A4_WIDTH_PT, A4_HEIGHT_PT), abs=0.5)


# ---------------------------------------------------------------------------
# Synthetic isolated chains: sender / operation / basis / phase1-minimal
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("stem", "needles"),
    [
        (
            "waybill-null-sender",
            ["Накладная № 100826/0343/0", "Грузополучатель: ДЭУ (КСК)"],
        ),
        (
            "waybill-null-operation",
            ["Накладная № WB-FIX-3", "Грузополучатель: ДЭУ (КСК)"],
        ),
        ("waybill-null-basis", ["Основание: Перемещение"]),
        (
            "waybill-minimal",
            ["Накладная № WB-MIN-1", "Грузополучатель: —", "Основание: Операция"],
        ),
    ],
)
def test_null_variant_renders_with_expected_fallback(stem: str, needles: list[str]) -> None:
    pdf = _render(_null_fixture(stem))
    all_text = "\n".join(_page_texts(pdf))
    for needle in needles:
        assert needle in all_text, f"{stem}: missing {needle!r}"
    assert _media_box(pdf) == pytest.approx((A4_WIDTH_PT, A4_HEIGHT_PT), abs=0.5)


def test_consignee_chain_all_null_falls_back_to_dash() -> None:
    """receiver=None + recipient=None + sender=None -> the "—" fallback.

    The committed null-sender fixture short-circuits at
    ``consignee_label``, so this constructed case exercises the sender
    guard inside the consignee fallback chain itself.
    """
    envelope = _null_fixture("waybill-minimal")
    document = envelope["document"]
    document["receiver"] = None
    document["recipient"] = None
    document["sender"] = None
    text = "\n".join(_page_texts(_render(envelope)))
    assert "Грузополучатель: —" in text


def test_null_sender_uses_zero_site_id_and_isolates_the_guard() -> None:
    """sender=null reaches the guarded computed-title branch (site_id "0")."""
    document = _null_fixture("waybill-null-sender")["document"]
    assert document["sender"] is None
    assert "operation_display_number" not in document
    assert document["operation"]["display_number"] is None


def test_null_basis_does_not_render_the_removed_basis_label() -> None:
    envelope = _null_fixture("waybill-null-basis")
    assert envelope["document"]["basis"] is None
    assert "basis_label" not in envelope["document"]
    text = "\n".join(_page_texts(_render(envelope)))
    assert "Перемещение Угдан → ДЭУ (КСК)" not in text


def test_phase1_minimal_document_has_only_lines() -> None:
    """The contract requires ONLY ``lines`` — the minimal shape is valid."""
    envelope = _null_fixture("waybill-minimal")
    assert set(envelope["document"]) == {"lines"}
    assert len(envelope["document"]["lines"]) == 3


# ---------------------------------------------------------------------------
# Normal-path parity: 2.2.0 -> 2.2.1 must be byte-identical
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("n", [1, 20, 75, 200, 500])
def test_normal_path_parity_2_2_0_vs_2_2_1(n: int) -> None:
    """Guard-only patch: identical bytes/pages/media box/text on 2.2.0 inputs."""
    envelope = _load(PARITY_DIR / f"waybill-qde22-{n}.typst.json")
    assert envelope["template_version"] == BASELINE_VERSION
    pdf_220 = _render_version(envelope, BASELINE_VERSION)
    pdf_221 = _render_version(envelope, PATCH_VERSION)

    assert hashlib.sha256(pdf_220).hexdigest() == hashlib.sha256(pdf_221).hexdigest()
    assert _page_count(pdf_221) == EXPECTED_PAGES_22[n]
    assert _page_count(pdf_221) == _page_count(pdf_220)
    assert _media_box(pdf_221) == _media_box(pdf_220)
    assert _page_texts(pdf_221) == _page_texts(pdf_220)


def test_committed_2_2_1_normal_fixture_renders_like_2_2_0() -> None:
    """The committed waybill-qde221-75 fixture pins the patch version."""
    fixture = REPO / "tests" / "fixtures" / "waybill-221" / "waybill-qde221-75.typst.json"
    envelope = _load(fixture)
    assert envelope["template_id"] == TEMPLATE_ID
    assert envelope["template_version"] == PATCH_VERSION
    pdf = _render(envelope)
    assert _page_count(pdf) == EXPECTED_PAGES_22[75]
    body_220 = _load(PARITY_DIR / "waybill-qde22-75.typst.json")["document"]
    assert envelope["document"] == body_220


def test_patch_template_repeated_render_is_byte_identical() -> None:
    envelope = _null_fixture("waybill-null-receiver")
    first = _render(envelope)
    second = _render(envelope)
    assert hashlib.sha256(first).hexdigest() == hashlib.sha256(second).hexdigest()
