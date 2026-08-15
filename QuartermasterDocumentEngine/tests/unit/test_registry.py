"""Unit tests for the template registry (SPEC v2 §9, ADR-0001 D6)."""

from __future__ import annotations

from pathlib import Path

import pytest
from qm_engine.errors import (
    TemplateContractMismatchError,
    TemplateNotInstalledError,
    TemplateVersionNotInstalledError,
)
from qm_engine.registry import Registry

REPO = Path(__file__).resolve().parents[2]
TEMPLATES = REPO / "templates"


def registry() -> Registry:
    return Registry(TEMPLATES)


def test_lookup_existing_template() -> None:
    package = registry().lookup("warehouse-waybill-ru", "0.1.0")
    assert package.template_id == "warehouse-waybill-ru"
    assert package.version == "0.1.0"
    assert package.document_contract == "warehouse.operation-document/v2"
    assert package.backend == "weasyprint"
    assert package.entrypoint.is_file()
    assert "pdf" in package.output_formats


def test_lookup_missing_template_id() -> None:
    with pytest.raises(TemplateNotInstalledError):
        registry().lookup("nonexistent-template", "0.1.0")


def test_lookup_missing_version() -> None:
    with pytest.raises(TemplateVersionNotInstalledError):
        registry().lookup("warehouse-waybill-ru", "9.9.9")


def test_check_contract_mismatch() -> None:
    package = registry().lookup("warehouse-waybill-ru", "0.1.0")
    with pytest.raises(TemplateContractMismatchError):
        registry().check_contract(package, "warehouse.other-document/v1")


def test_check_contract_match() -> None:
    package = registry().lookup("warehouse-waybill-ru", "0.1.0")
    # Should not raise.
    registry().check_contract(package, "warehouse.operation-document/v2")


def test_list_installed() -> None:
    packages = registry().list_installed()
    ids = {(p.template_id, p.version) for p in packages}
    assert ("warehouse-waybill-ru", "0.1.0") in ids
    assert ("warehouse-waybill-ru", "1.0") in ids


def test_lookup_prod_version() -> None:
    package = registry().lookup("warehouse-waybill-ru", "1.0")
    assert package.version == "1.0"
    assert package.entrypoint.is_file()


def test_registry_missing_root() -> None:
    r = Registry(REPO / "does-not-exist")
    assert r.list_installed() == []
    with pytest.raises(TemplateNotInstalledError):
        r.lookup("anything", "1.0.0")
