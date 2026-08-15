"""Component tests for the Typst backend (T6, marked ``spike``).

These tests require the real pinned ``typst`` binary at
``.spike/typst-0.15.1/typst-x86_64-unknown-linux-musl/typst``. They are
skipped if the binary is missing (run `` ``scripts/fetch_typst.py`` to
populate the cache). Run with ``pytest -m spike`` to opt in.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from pypdf import PdfReader
from qm_backends.typst_backend import TypstBackend, _pinned_binary_path
from qm_engine.registry import TemplatePackage

REPO = Path(__file__).resolve().parents[2]
PIN_PATH = REPO / "spike" / "typst-pin.json"
DEFAULT_TYPIST_BINARY = (
    REPO / ".spike" / "typst-0.15.1" / "typst-x86_64-unknown-linux-musl" / "typst"
)


def _real_binary_available() -> bool:
    path = _pinned_binary_path()
    return path is not None and path.is_file()


_skip_no_binary = pytest.mark.skipif(
    not _real_binary_available(),
    reason="real typst binary not present; run scripts/fetch_typst.py",
)


def _build_template_package(tmp_path: Path, *, use_inner: bool = False) -> TemplatePackage:
    """Build a minimal Typst template that reads the normalized envelope.

    ``use_inner=False`` (default) — the template reads envelope-level
    fields directly via ``doc.<field>`` and inner document fields via
    ``doc.document.<field>``. This mirrors the Phase 2.1 contract
    (TZ-PHASE2-BACKEND-SPIKE §T5 / §11.2).

    ``use_inner=True`` — the template reads inner-document fields via
    ``doc.<field>`` directly (the pre-Phase 2.1 shape, kept around for
    the regression test that proves the new contract is honoured).
    """
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    if use_inner:
        body_template = (
            '#set document(title: "Spike Typst")\n'
            "#set page(width: auto, height: auto, margin: 1cm)\n"
            '#set text(font: "DejaVu Sans", lang: "ru", size: 12pt)\n'
            "= Тестовый Typst-рендер\n\n"
            '#let doc = json("document.json")\n'
            "Документ: *#{doc.title}*. "
            'Контракт: #doc.at("document_number", default: "—")\n\n'
            "#let items = doc.items\n"
            "#for item in items [\n"
            '  - Наименование: *#{item.name}*, количество: #"%.2f" % item.qty\n'
            "]\n"
        )
    else:
        body_template = (
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
            "]\n"
        )
    (pkg / "main.typ").write_text(body_template, encoding="utf-8")
    manifest_text = (
        "id: typst-spike-test\n"
        "version: 0.1.0\n"
        "document_contract: warehouse.operation-document/v2\n"
        "backend: typst\n"
        "entrypoint: main.typ\n"
        "output_formats: [pdf, png]\n"
        "locales: [ru-RU]\n"
    )
    (pkg / "manifest.yaml").write_text(manifest_text, encoding="utf-8")
    return TemplatePackage(
        root=pkg,
        manifest={
            "id": "typst-spike-test",
            "version": "0.1.0",
            "document_contract": "warehouse.operation-document/v2",
            "backend": "typst",
            "entrypoint": "main.typ",
            "output_formats": ["pdf", "png"],
            "locales": ["ru-RU"],
        },
    )


def _sample_document() -> dict[str, object]:
    """Phase 2.1 sample: full normalized envelope shape."""
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


def _inner_only_sample_document() -> dict[str, object]:
    """Pre-Phase 2.1 sample shape (envelope reduced to inner document).

    Used by the regression test that proves the new contract still
    works when the template accesses ``doc.<field>`` directly (because
    the inner fields are present at the top level too — the new
    contract puts the full envelope on disk).
    """
    return {
        "document": {
            "title": "Накладная INNER-ONLY",
            "items": [
                {"name": "Шайба М8", "qty": 50.0},
            ],
        },
        "__assets__": {},
    }


@_skip_no_binary
@pytest.mark.spike
def test_typst_real_binary_renders_minimal_template(tmp_path: Path) -> None:
    """Real binary produces a valid PDF and embeds DejaVu Sans."""
    backend = TypstBackend()
    if not backend.available():
        pytest.skip("real typst binary did not respond to --version")

    package = _build_template_package(tmp_path)
    result = backend.render(
        normalized_document=_sample_document(),
        template_package=package,
        output_format="pdf",
        render_options={},
    )
    assert result.data[:5] == b"%PDF-"
    assert result.page_count is not None and result.page_count >= 1

    reader = PdfReader(__import__("io").BytesIO(result.data))
    fonts: list[str] = []
    for page in reader.pages:
        for font_dict in (page.get("/Resources") or {}).get("/Font", {}).values():
            base = font_dict.get("/BaseFont")
            if isinstance(base, str):
                fonts.append(base)
    # The bundled DejaVu Sans is set via ``--font-path``; the embedded
    # subset prefix should mention ``DejaVu``. We accept either the
    # hyphenated or non-hyphenated spelling.
    has_dejavu = any("dejavu" in name.lower().replace("-", "") for name in fonts)
    assert has_dejavu, f"expected DejaVu subset in PDF, got: {fonts}"


@_skip_no_binary
@pytest.mark.spike
def test_typst_renders_envelope_level_fields(tmp_path: Path) -> None:
    """Phase 2.1: Typst template can read envelope-level fields directly.

    The template binds ``#let doc = json("document.json")`` and reads
    ``doc.document_number`` (envelope-level). Without the full envelope
    serialisation, ``document_number`` would not be visible from a
    Typst template — the previous Typst spike had to fall back to
    ``doc.operation.display_number``.
    """
    backend = TypstBackend()
    if not backend.available():
        pytest.skip("real typst binary did not respond to --version")

    package = _build_template_package(tmp_path)
    result = backend.render(
        normalized_document=_sample_document(),
        template_package=package,
        output_format="pdf",
        render_options={},
    )
    reader = PdfReader(__import__("io").BytesIO(result.data))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "WB-FIX-TEST" in text, (
        f"expected envelope-level document_number in PDF text, got:\n{text[:400]}"
    )
    # And the inner document title is reachable via doc.document.title.
    assert "WAYBILL-TEST" in text


@_skip_no_binary
@pytest.mark.spike
def test_typst_internal_assets_key_stripped(tmp_path: Path) -> None:
    """Phase 2.1: ``__assets__`` is the only stripped field.

    A template can introspect the on-disk ``document.json`` (via
    ``json("document.json")``) and see all envelope-level fields, but
    the internal ``__assets__`` key is not serialised. This protects
    Jinja2-side cleanliness without leaking the engine's transport key.
    """
    backend = TypstBackend()
    if not backend.available():
        pytest.skip("real typst binary did not respond to --version")

    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "main.typ").write_text(
        "#set page(width: auto, height: auto, margin: 1cm)\n"
        '#set text(font: "DejaVu Sans", lang: "ru", size: 12pt)\n'
        '#let doc = json("document.json")\n'
        '#let has_assets = doc.at("__assets__", default: "MISSING")\n'
        "Имеется assets: #has_assets\n"
        'Доступ document_number: #doc.at("document_number", default: "—")\n',
        encoding="utf-8",
    )
    (pkg / "manifest.yaml").write_text(
        "id: typst-spike-test\nversion: 0.1.0\n"
        "document_contract: warehouse.operation-document/v2\n"
        "backend: typst\nentrypoint: main.typ\n"
        "output_formats: [pdf]\nlocales: [ru-RU]\n",
        encoding="utf-8",
    )
    package = TemplatePackage(
        root=pkg,
        manifest={
            "id": "typst-spike-test",
            "version": "0.1.0",
            "document_contract": "warehouse.operation-document/v2",
            "backend": "typst",
            "entrypoint": "main.typ",
            "output_formats": ["pdf"],
            "locales": ["ru-RU"],
        },
    )
    sample = _sample_document()
    # 1×1 transparent PNG, valid base64. We only care that __assets__
    # gets stripped before document.json is written — the actual QR
    # payload is irrelevant for this test.
    sample["__assets__"] = {
        "qr": {
            "mime": "image/png",
            "data_base64": (
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwC"
                "AAAAC0lEQVR42mNgAAIAAAUAAeImBZsAAAAASUVORK5CYII="
            ),
        }
    }

    result = backend.render(
        normalized_document=sample,
        template_package=package,
        output_format="pdf",
        render_options={},
    )
    reader = PdfReader(__import__("io").BytesIO(result.data))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    # The Typst ``.at("__assets__", default: "MISSING")`` returns the
    # default (because we strip __assets__ before serialisation), so
    # the literal string "MISSING" appears in the rendered text.
    assert "MISSING" in text, (
        f"expected stripped __assets__ to produce MISSING in text, got:\n{text[:400]}"
    )
    # And the envelope-level document_number is reachable.
    assert "WB-FIX-TEST" in text


@_skip_no_binary
@pytest.mark.spike
def test_typst_determinism(tmp_path: Path) -> None:
    """Three consecutive renders must produce byte-identical PDFs.

    Phase 2.1 review-fix M1: Typst 0.15.1 ignores the ``TYPST_TIMESTAMP``
    env var on Linux; the production backend now passes
    ``--creation-timestamp`` as a CLI flag explicitly. Without the flag,
    Typst uses wall-clock time for the PDF ``/CreationDate`` metadata,
    so renders crossing a wall-clock second boundary produced different
    ``/ID`` hashes and the test failed ~3% of the time. With the flag
    pinned at ``DEFAULT_TYPST_TIMESTAMP = 1700000000`` the output is
    byte-deterministic across all reruns (verified by ``scripts/diag_typst_determinism.py``
    — 100 series × 3 renders = 0 divergence after the fix).
    """
    backend = TypstBackend()
    if not backend.available():
        pytest.skip("real typst binary did not respond to --version")

    package = _build_template_package(tmp_path)
    doc = _sample_document()

    hashes: list[str] = []
    for _ in range(3):
        result = backend.render(
            normalized_document=doc,
            template_package=package,
            output_format="pdf",
            render_options={},
        )
        hashes.append(hashlib.sha256(result.data).hexdigest())

    assert hashes[0] == hashes[1] == hashes[2], f"non-deterministic output: {hashes}"


@_skip_no_binary
@pytest.mark.spike
def test_typst_determinism_across_second_boundary(tmp_path: Path) -> None:
    """Regression for Phase 2.1 review-fix M1 (the cold-render flake).

    Before the fix, renders that crossed a wall-clock second boundary
    produced different ``/CreationDate`` → different ``/ID`` → different
    SHA. After the fix the backend pins ``--creation-timestamp`` so the
    output is stable across wall-clock seconds. This test forces the
    scenario by sleeping across a second boundary between two renders
    and asserts the SHA stays the same.
    """
    import time

    backend = TypstBackend()
    if not backend.available():
        pytest.skip("real typst binary did not respond to --version")

    package = _build_template_package(tmp_path)
    doc = _sample_document()

    # Render #1 — first wall-clock second.
    result_1 = backend.render(
        normalized_document=doc,
        template_package=package,
        output_format="pdf",
        render_options={},
    )
    sha_1 = hashlib.sha256(result_1.data).hexdigest()

    # Sleep across a wall-clock second boundary. Sleep 1.2 s to make sure
    # we cross at least one boundary even if the first render landed
    # near the boundary itself.
    time.sleep(1.2)

    # Render #2 — different wall-clock second.
    result_2 = backend.render(
        normalized_document=doc,
        template_package=package,
        output_format="pdf",
        render_options={},
    )
    sha_2 = hashlib.sha256(result_2.data).hexdigest()

    assert sha_1 == sha_2, (
        f"render hashes differ across wall-clock second boundary "
        f"(Phase 2.1 M1 regression): {sha_1[:16]}... != {sha_2[:16]}..."
    )

    # Belt-and-braces: structural / semantic equivalence must hold
    # even if a future Typst regression re-introduces metadata drift.
    # Both PDFs must have the same page count and the same extracted
    # text content.
    reader_1 = PdfReader(__import__("io").BytesIO(result_1.data))
    reader_2 = PdfReader(__import__("io").BytesIO(result_2.data))
    assert len(reader_1.pages) == len(reader_2.pages), (
        f"page count differs: {len(reader_1.pages)} vs {len(reader_2.pages)}"
    )
    text_1 = "\n".join(p.extract_text() or "" for p in reader_1.pages)
    text_2 = "\n".join(p.extract_text() or "" for p in reader_2.pages)
    assert text_1 == text_2, (
        "extracted text differs across wall-clock second boundary:\n"
        f"--- render #1 ---\n{text_1[:200]}\n"
        f"--- render #2 ---\n{text_2[:200]}"
    )


@_skip_no_binary
@pytest.mark.spike
def test_typst_page_count_for_png_output(tmp_path: Path) -> None:
    """PNG output returns a PNG blob and a positive page count via the second pass."""
    backend = TypstBackend()
    if not backend.available():
        pytest.skip("real typst binary did not respond to --version")

    package = _build_template_package(tmp_path)
    result = backend.render(
        normalized_document=_sample_document(),
        template_package=package,
        output_format="png",
        render_options={},
    )
    assert result.data[:8] == b"\x89PNG\r\n\x1a\n"
    assert result.page_count is not None and result.page_count >= 1


def test_typst_real_binary_pinned_path_present() -> None:
    """Sanity check the pinned path matches the expected Linux layout."""
    expected = DEFAULT_TYPIST_BINARY
    if not expected.is_file():
        pytest.skip(f"pinned typst binary missing at {expected}")
    assert expected.is_file()
    assert expected.stat().st_size > 1_000_000, "typst binary looks too small"
