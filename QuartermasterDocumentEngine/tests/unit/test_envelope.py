"""Unit tests for envelope parsing/validation (SPEC v2 §7)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from qm_engine.envelope import _DOCUMENT_CONTRACT_SCHEMAS, Envelope, parse_envelope
from qm_engine.errors import (
    InvalidPayloadError,
    UnsupportedDocumentContractError,
    UnsupportedEngineContractError,
)

REPO = Path(__file__).resolve().parents[2]
WAYBILL = REPO / "tests" / "fixtures" / "waybill-20.json"


def _load(name: str) -> str:
    return (REPO / "tests" / "fixtures" / "invalid" / name).read_text(encoding="utf-8")


def test_parse_valid_waybill() -> None:
    raw = WAYBILL.read_text(encoding="utf-8")
    envelope = parse_envelope(raw)
    assert isinstance(envelope, Envelope)
    assert envelope.engine_contract_version == "1.0.0"
    assert envelope.document_contract == "warehouse.operation-document/v2"
    assert envelope.template_id == "warehouse-waybill-ru"
    assert envelope.template_version == "0.1.0"
    assert envelope.document_number == "WAYBILL-000020"
    assert len(envelope.document["lines"]) == 20


def test_parse_invalid_json() -> None:
    with pytest.raises(InvalidPayloadError):
        parse_envelope(_load("invalid-json.json"))


def test_parse_unsupported_engine_contract() -> None:
    with pytest.raises(UnsupportedEngineContractError):
        parse_envelope(_load("unsupported-engine-contract.json"))


def test_parse_missing_document_fields() -> None:
    with pytest.raises(InvalidPayloadError):
        parse_envelope(_load("missing-document-fields.json"))


def test_parse_unsupported_document_contract() -> None:
    with pytest.raises(UnsupportedDocumentContractError):
        parse_envelope(_load("unsupported-document-contract.json"))


def test_parse_non_object_root() -> None:
    with pytest.raises(InvalidPayloadError):
        parse_envelope("[1, 2, 3]")


def test_parse_document_wrong_type() -> None:
    data = json.loads(WAYBILL.read_text(encoding="utf-8"))
    data["document"] = "not-an-object"
    with pytest.raises(InvalidPayloadError):
        parse_envelope(json.dumps(data))


def test_parse_missing_required_field() -> None:
    data = json.loads(WAYBILL.read_text(encoding="utf-8"))
    del data["template_version"]
    with pytest.raises(InvalidPayloadError):
        parse_envelope(json.dumps(data))


def test_parse_accepts_two_part_version() -> None:
    """Prod payloads use template_version '1.0' (X.Y, not full semver X.Y.Z)."""
    data = json.loads(WAYBILL.read_text(encoding="utf-8"))
    data["template_version"] = "1.0"
    envelope = parse_envelope(json.dumps(data))
    assert envelope.template_version == "1.0"


def test_parse_prod_document_shape() -> None:
    """Prod document (operation/sender/lines with item_*) passes the contract."""
    prod = REPO / "doc" / "test_templates" / "template_WRITE_OFF_14l.json"
    raw = prod.read_text(encoding="utf-8")
    envelope = parse_envelope(raw)
    assert envelope.template_version == "1.0"
    assert len(envelope.document["lines"]) == 14


# ---------------------------------------------------------------------------
# TZ-PHASE2-BACKEND-SPIKE T2: strict spike-family contracts.
# Document payloads are built in-test (T3 fixtures are owned by another shard).
# ---------------------------------------------------------------------------


def _envelope_skeleton(document_contract: str, document_type: str) -> dict[str, object]:
    return {
        "engine_contract_version": "1.0.0",
        "document_contract": document_contract,
        "document_type": document_type,
        "template_id": f"spike-{document_type}",
        "template_version": "0.1.0",
        "locale": "ru-RU",
        "render_profile": "print",
        "assets": {},
    }


def _minimal_route_sheet_document() -> dict[str, object]:
    return {
        "vehicle": {
            "make": "КамАЗ",
            "model": "65115",
            "plate": "А123БВ777",
            "garage_number": "Г-042",
        },
        "driver": {
            "full_name": "Иванов Иван Иванович",
            "employee_id": "Т-12345",
            "class": "C",
        },
        "trips": [],
        "refuels": [],
        "odometer": {"start": 100000.0, "end": 100250.0},
        "fuel_balance": {"start_l": 50.0, "end_l": 30.0, "received_total_l": 100.0},
        "fuel_consumption": {"norm": 25.0, "actual": 23.5},
        "signers": {
            "driver": {"label": "Водитель", "name": "", "signed_at": ""},
            "mechanic": {"label": "Механик", "name": "", "signed_at": ""},
            "dispatcher": {"label": "Диспетчер", "name": "", "signed_at": ""},
        },
        "period": {"start_date": "2026-07-01", "end_date": "2026-07-31"},
    }


def _minimal_fuel_report_document() -> dict[str, object]:
    return {
        "period": {"year": 2026, "month": 7},
        "vehicles": [
            {
                "id": "V-001",
                "name": "КамАЗ 65115",
                "plate": "А123БВ777",
                "unit": "л",
                "norm_l_per_100km": 25.0,
            }
        ],
        "rows": [
            {
                "date": "2026-07-01",
                "vehicle_id": "V-001",
                "fuel_type": "ДТ",
                "volume_l": 50.0,
                "distance_km": 200.0,
                "cost": 3500.0,
            }
        ],
        "subtotals": [
            {
                "vehicle_id": "V-001",
                "total_volume_l": 50.0,
                "total_distance_km": 200.0,
                "total_cost": 3500.0,
            }
        ],
        "grand_total": {
            "total_volume_l": 50.0,
            "total_distance_km": 200.0,
            "total_cost": 3500.0,
        },
    }


def test_parse_vehicle_route_sheet_minimal() -> None:
    payload = _envelope_skeleton("transport.vehicle-route-sheet/v1", "vehicle_route_sheet")
    payload["document"] = _minimal_route_sheet_document()
    envelope = parse_envelope(json.dumps(payload))
    assert isinstance(envelope, Envelope)
    assert envelope.document_contract == "transport.vehicle-route-sheet/v1"
    assert envelope.document["vehicle"]["plate"] == "А123БВ777"
    assert envelope.document["trips"] == []
    assert envelope.document["refuels"] == []


def test_parse_fuel_report_minimal() -> None:
    payload = _envelope_skeleton("fuel.monthly-report/v1", "fuel_monthly_report")
    payload["document"] = _minimal_fuel_report_document()
    envelope = parse_envelope(json.dumps(payload))
    assert isinstance(envelope, Envelope)
    assert envelope.document_contract == "fuel.monthly-report/v1"
    assert envelope.document["period"] == {"year": 2026, "month": 7}
    assert len(envelope.document["rows"]) == 1
    assert envelope.document["grand_total"]["total_cost"] == 3500.0


def test_parse_vehicle_route_sheet_rejects_missing_required() -> None:
    payload = _envelope_skeleton("transport.vehicle-route-sheet/v1", "vehicle_route_sheet")
    doc = _minimal_route_sheet_document()
    del doc["vehicle"]
    payload["document"] = doc
    with pytest.raises(InvalidPayloadError):
        parse_envelope(json.dumps(payload))


def test_parse_fuel_report_rejects_wrong_type() -> None:
    payload = _envelope_skeleton("fuel.monthly-report/v1", "fuel_monthly_report")
    doc = _minimal_fuel_report_document()
    doc["rows"][0]["volume_l"] = "not-a-number"
    payload["document"] = doc
    with pytest.raises(InvalidPayloadError):
        parse_envelope(json.dumps(payload))


def test_parse_vehicle_route_sheet_full_structure() -> None:
    """Happy path with non-empty trips and refuels — verifies array item constraints."""
    payload = _envelope_skeleton("transport.vehicle-route-sheet/v1", "vehicle_route_sheet")
    doc = _minimal_route_sheet_document()
    doc["trips"] = [
        {
            "departure_at": "2026-07-01T07:30:00+03:00",
            "return_at": "2026-07-01T11:45:00+03:00",
            "origin": "База «Северный терминал»",
            "destination": "Склад заказчика №14",
            "purpose": "Доставка партии ТМЦ",
            "distance_km": 42.5,
            "duration_min": 255,
        }
    ]
    doc["refuels"] = [
        {
            "refueled_at": "2026-07-01T18:05:00+03:00",
            "station": "АЗС «Лукойл-247»",
            "fuel_type": "ДТ",
            "volume_l": 60.0,
            "cost": 4200.0,
        }
    ]
    doc["signers"]["driver"]["name"] = "Иванов И.И."
    doc["signers"]["driver"]["signed_at"] = "2026-07-31T17:30:00+03:00"
    payload["document"] = doc
    envelope = parse_envelope(json.dumps(payload))
    assert len(envelope.document["trips"]) == 1
    assert envelope.document["trips"][0]["distance_km"] == 42.5
    assert len(envelope.document["refuels"]) == 1
    assert envelope.document["signers"]["driver"]["name"] == "Иванов И.И."


def test_parse_fuel_report_with_optional_chart() -> None:
    """The optional `chart` block must validate when present and stay optional when absent."""
    payload = _envelope_skeleton("fuel.monthly-report/v1", "fuel_monthly_report")
    doc = _minimal_fuel_report_document()
    doc["chart"] = {"title": "Расход по технике", "image_asset_name": "fuel-bars-1500"}
    payload["document"] = doc
    envelope = parse_envelope(json.dumps(payload))
    assert envelope.document["chart"]["image_asset_name"] == "fuel-bars-1500"


def test_document_contract_registry_contains_spike_families() -> None:
    """Guard against accidental reset of the contract registry.

    T2 (TZ-PHASE2-BACKEND-SPIKE) registers both new families; later shards
    depend on these short keys being stable.
    """
    assert "transport.vehicle-route-sheet/v1" in _DOCUMENT_CONTRACT_SCHEMAS
    assert "fuel.monthly-report/v1" in _DOCUMENT_CONTRACT_SCHEMAS
    assert (
        _DOCUMENT_CONTRACT_SCHEMAS["transport.vehicle-route-sheet/v1"]
        == "transport.vehicle-route-sheet/v1/schema.json"
    )
    assert (
        _DOCUMENT_CONTRACT_SCHEMAS["fuel.monthly-report/v1"] == "fuel.monthly-report/v1/schema.json"
    )
