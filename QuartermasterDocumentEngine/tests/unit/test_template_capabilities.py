"""Unit tests for spike template manifests (TZ-PHASE2-BACKEND-SPIKE §8 T7).

For each of the 5 spike packages we verify:

- ``manifest.yaml`` parses via ``Registry.lookup``
- ``capabilities`` is a non-empty list of strings drawn from the
  ``doc/spike/INVESTIGATION.md`` §7 dictionary
- ``fonts`` is a list of mappings; every entry has ``family == "DejaVu Sans"``
  and a ``file`` matching one of the four bundled TTF names
- ``document_contract`` is one of the three known contracts
- ``output_formats`` is a non-empty list
- ``page.orientation`` is one of ``{"portrait", "landscape"}``

Pure-Python; no rendering.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from qm_engine.registry import Registry

REPO = Path(__file__).resolve().parents[2]
TEMPLATES = REPO / "templates"

# Capabilities dictionary (TZ §7 / doc/spike/INVESTIGATION.md §7).
KNOWN_CAPABILITIES: frozenset[str] = frozenset(
    {
        "qr",
        "barcode",
        "image",
        "watermark",
        "copies",
        "landscape",
        "multi-page-table",
        "fixed-form",
    }
)

# Known document contracts.
KNOWN_CONTRACTS: frozenset[str] = frozenset(
    {
        "warehouse.operation-document/v2",
        "transport.vehicle-route-sheet/v1",
        "fuel.monthly-report/v1",
    }
)

# Bundled TTF names declared in fonts/manifest.json.
BUNDLED_FONTS: frozenset[str] = frozenset(
    {
        "DejaVuSans.ttf",
        "DejaVuSans-Bold.ttf",
        "DejaVuSans-Oblique.ttf",
        "DejaVuSans-BoldOblique.ttf",
    }
)

SPIKE_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("spike-waybill-typst", "0.1.0"),
    ("spike-route-sheet-weasy", "0.1.0"),
    ("spike-route-sheet-typst", "0.1.0"),
    ("spike-fuel-report-weasy", "0.1.0"),
    ("spike-fuel-report-typst", "0.1.0"),
)

# Canonical production template (Phase 6C). Runs the same generic
# manifest checks as the spike packages plus production-specific
# assertions below.
PRODUCTION_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("warehouse-waybill-ru", "2.0.0"),
)


def _load(template_id: str, version: str) -> dict[str, Any]:
    pkg = Registry(TEMPLATES).lookup(template_id, version)
    return dict(pkg.manifest)


@pytest.mark.parametrize(("template_id", "version"), SPIKE_TEMPLATES)
def test_manifest_capabilities_are_known_tokens(template_id: str, version: str) -> None:
    """Every entry in ``capabilities`` must come from the §7 dictionary."""
    manifest = _load(template_id, version)
    caps = manifest.get("capabilities")
    assert isinstance(caps, list), f"{template_id}: capabilities must be a list, got {type(caps)}"
    assert caps, f"{template_id}: capabilities list must not be empty"
    for entry in caps:
        assert isinstance(entry, str), f"{template_id}: capability entry must be str, got {entry!r}"
        assert entry in KNOWN_CAPABILITIES, (
            f"{template_id}: unknown capability {entry!r}; known: {sorted(KNOWN_CAPABILITIES)}"
        )


@pytest.mark.parametrize(("template_id", "version"), SPIKE_TEMPLATES)
def test_manifest_fonts_match_bundled_ttf(template_id: str, version: str) -> None:
    """All declared fonts must reference the bundled DejaVu Sans variants."""
    manifest = _load(template_id, version)
    fonts = manifest.get("fonts")
    assert isinstance(fonts, list), f"{template_id}: fonts must be a list"
    assert fonts, f"{template_id}: fonts list must not be empty"
    declared_files: set[str] = set()
    for entry in fonts:
        assert isinstance(entry, dict), f"{template_id}: font entry must be a mapping"
        family = entry.get("family")
        assert family == "DejaVu Sans", (
            f"{template_id}: font family must be 'DejaVu Sans', got {family!r}"
        )
        file_name = entry.get("file")
        assert isinstance(file_name, str), f"{template_id}: font 'file' must be str"
        assert file_name in BUNDLED_FONTS, (
            f"{template_id}: unknown bundled TTF {file_name!r}; bundled: {sorted(BUNDLED_FONTS)}"
        )
        declared_files.add(file_name)
    # The four canonical files should all be declared in every spike template.
    assert declared_files >= BUNDLED_FONTS, (
        f"{template_id}: missing bundled TTFs: {sorted(BUNDLED_FONTS - declared_files)}"
    )


@pytest.mark.parametrize(("template_id", "version"), SPIKE_TEMPLATES)
def test_manifest_document_contract_is_known(template_id: str, version: str) -> None:
    """``document_contract`` must be one of the three known contracts."""
    manifest = _load(template_id, version)
    contract = manifest.get("document_contract")
    assert contract in KNOWN_CONTRACTS, (
        f"{template_id}: unknown document_contract {contract!r}; known: {sorted(KNOWN_CONTRACTS)}"
    )


@pytest.mark.parametrize(("template_id", "version"), SPIKE_TEMPLATES)
def test_manifest_output_formats_is_nonempty(template_id: str, version: str) -> None:
    """``output_formats`` must be a non-empty list of strings."""
    manifest = _load(template_id, version)
    formats = manifest.get("output_formats")
    assert isinstance(formats, list), f"{template_id}: output_formats must be a list"
    assert formats, f"{template_id}: output_formats must not be empty"
    for fmt in formats:
        assert isinstance(fmt, str), f"{template_id}: output_format entry must be str"
        assert fmt in {"pdf", "png", "svg"}, f"{template_id}: unsupported output_format {fmt!r}"


@pytest.mark.parametrize(("template_id", "version"), SPIKE_TEMPLATES)
def test_manifest_page_orientation_is_valid(template_id: str, version: str) -> None:
    """``page.orientation`` must be portrait or landscape."""
    manifest = _load(template_id, version)
    page = manifest.get("page")
    assert isinstance(page, dict), f"{template_id}: page must be a mapping"
    orientation = page.get("orientation")
    assert orientation in {"portrait", "landscape"}, (
        f"{template_id}: orientation must be 'portrait' or 'landscape', got {orientation!r}"
    )
    size = page.get("size")
    assert size == "A4", f"{template_id}: page.size must be 'A4', got {size!r}"
    margin = page.get("margin")
    assert isinstance(margin, str) and margin, (
        f"{template_id}: page.margin must be a non-empty string"
    )


def test_landscape_templates_declare_landscape_capability() -> None:
    """The two fuel-report templates declare ``landscape`` and have landscape pages."""
    for template_id, version in SPIKE_TEMPLATES:
        manifest = _load(template_id, version)
        if template_id.startswith("spike-fuel-report"):
            assert manifest["page"]["orientation"] == "landscape"
            assert "landscape" in manifest["capabilities"]


def test_waybill_typst_uses_warehouse_operation_document_contract() -> None:
    """Sanity: spike-waybill-typst must target the waybill contract."""
    manifest = _load("spike-waybill-typst", "0.1.0")
    assert manifest["document_contract"] == "warehouse.operation-document/v2"


def test_route_sheet_templates_use_route_sheet_contract() -> None:
    """Both route-sheet templates target the transport contract."""
    for tid in ("spike-route-sheet-weasy", "spike-route-sheet-typst"):
        manifest = _load(tid, "0.1.0")
        assert manifest["document_contract"] == "transport.vehicle-route-sheet/v1"


def test_fuel_report_templates_use_fuel_report_contract() -> None:
    """Both fuel-report templates target the fuel contract."""
    for tid in ("spike-fuel-report-weasy", "spike-fuel-report-typst"):
        manifest = _load(tid, "0.1.0")
        assert manifest["document_contract"] == "fuel.monthly-report/v1"


def test_typst_templates_declare_png_in_output_formats() -> None:
    """Typst backends can render PNG preview — every Typst spike lists it."""
    for tid in (
        "spike-waybill-typst",
        "spike-route-sheet-typst",
        "spike-fuel-report-typst",
    ):
        manifest = _load(tid, "0.1.0")
        assert "pdf" in manifest["output_formats"]
        assert "png" in manifest["output_formats"]


def test_weasyprint_templates_only_declare_pdf_in_output_formats() -> None:
    """WeasyPrint backend only supports PDF — no PNG in spike manifest."""
    for tid in ("spike-route-sheet-weasy", "spike-fuel-report-weasy"):
        manifest = _load(tid, "0.1.0")
        assert manifest["output_formats"] == ["pdf"]


# ---------------------------------------------------------------------------
# Canonical production template (warehouse-waybill-ru@2.0.0)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("template_id", "version"), PRODUCTION_TEMPLATES)
def test_production_manifest_capabilities_are_known_tokens(
    template_id: str, version: str
) -> None:
    """The production manifest declares known capabilities (multi-page table)."""
    manifest = _load(template_id, version)
    caps = manifest.get("capabilities")
    assert isinstance(caps, list) and caps
    for entry in caps:
        assert entry in KNOWN_CAPABILITIES
    # The waybill form is a fixed print form with a multi-page item table.
    assert "multi-page-table" in caps
    assert "fixed-form" in caps


@pytest.mark.parametrize(("template_id", "version"), PRODUCTION_TEMPLATES)
def test_production_manifest_fonts_match_bundled_ttf(
    template_id: str, version: str
) -> None:
    """The production template bundles the four DejaVu Sans variants."""
    manifest = _load(template_id, version)
    fonts = manifest.get("fonts")
    assert isinstance(fonts, list) and fonts
    declared_files: set[str] = set()
    for entry in fonts:
        assert isinstance(entry, dict)
        assert entry.get("family") == "DejaVu Sans"
        file_name = entry.get("file")
        assert isinstance(file_name, str) and file_name in BUNDLED_FONTS
        declared_files.add(file_name)
    assert declared_files >= BUNDLED_FONTS


@pytest.mark.parametrize(("template_id", "version"), PRODUCTION_TEMPLATES)
def test_production_manifest_contract_and_formats(
    template_id: str, version: str
) -> None:
    """Canonical waybill targets the warehouse contract, A4 portrait, pdf+png."""
    manifest = _load(template_id, version)
    assert manifest["document_contract"] == "warehouse.operation-document/v2"
    assert manifest["backend"] == "typst"
    page = manifest["page"]
    assert page["size"] == "A4"
    assert page["orientation"] == "portrait"
    assert isinstance(page.get("margin"), str) and page["margin"]
    assert "pdf" in manifest["output_formats"]
    assert "png" in manifest["output_formats"]


def test_production_template_package_has_entrypoint_and_layout_doc() -> None:
    """2.0.0 ships main.typ, layout-config.typ and LAYOUT.md."""
    package_root = TEMPLATES / "warehouse-waybill-ru" / "2.0.0"
    manifest = _load("warehouse-waybill-ru", "2.0.0")
    assert (package_root / manifest["entrypoint"]).is_file()
    assert (package_root / "layout-config.typ").is_file()
    assert (package_root / "LAYOUT.md").is_file()
