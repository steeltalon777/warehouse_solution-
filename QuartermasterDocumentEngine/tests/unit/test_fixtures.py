"""Unit tests for Phase 2 fixture generation (TZ-PHASE2-BACKEND-SPIKE §T3).

The fixtures are written to disk by ``generate_fixtures.py`` and committed.
These tests exercise the **in-memory** builders to guarantee that a rerun
without source changes produces byte-identical output.

The on-disk fixtures are also pulled in for a structural smoke pass: each
JSON must parse through ``parse_envelope`` (envelope schema + contract
schema), and the pair (weasy/typst) must share the same data section.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from qm_engine.envelope import parse_envelope

from tests.fixtures.generate_fixtures import (
    SPIKE_TEMPLATE_VERSION,
    WAYBILL_TYPST_TEMPLATE_ID,
    WAYBILL_TYPST_TEMPLATE_VERSION,
    WAYBILL_WEASY_TEMPLATE_ID,
    WAYBILL_WEASY_TEMPLATE_VERSION,
    build_fuel_report_envelope,
    build_route_sheet_envelope,
    build_waybill_envelope,
)

REPO = Path(__file__).resolve().parents[2]
WAYBILL_DIR = REPO / "tests" / "fixtures" / "waybill"
ROUTE_DIR = REPO / "tests" / "fixtures" / "route-sheet"
FUEL_DIR = REPO / "tests" / "fixtures" / "fuel"


def _hash(payload: object) -> str:
    """Stable hash: sorted keys, no ASCII escaping of Cyrillic."""

    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _envelope_data(payload: dict[str, object]) -> dict[str, object]:
    """Strip non-data fields to compare only document bodies across pairs."""

    return {"document": payload["document"], "assets": payload.get("assets", {})}


def test_waybill_builder_is_deterministic_for_each_size() -> None:
    for n in (1, 20, 75, 200, 500):
        # Same template_id on both calls so the byte-identical assertion is
        # meaningful (template_id is part of the payload hash).
        first = build_waybill_envelope(
            n,
            template_id=WAYBILL_WEASY_TEMPLATE_ID,
            template_version=WAYBILL_WEASY_TEMPLATE_VERSION,
        )
        second = build_waybill_envelope(
            n,
            template_id=WAYBILL_WEASY_TEMPLATE_ID,
            template_version=WAYBILL_WEASY_TEMPLATE_VERSION,
        )
        assert _hash(first) == _hash(second), f"waybill-{n} builder hash drifted between two calls"
        assert first["document_number"] == f"WB-FIX-{n}"
        assert first["document"]["operation_type"] == "MOVE"
        assert first["document"]["operation_type_label"] == "Перемещение"
        assert len(first["document"]["lines"]) == n
        # Line 50 (if present) always gets a long descriptive comment.
        if n >= 50:
            comment_50 = first["document"]["lines"][49].get("comment")
            assert isinstance(comment_50, str)
            assert len(comment_50) > 100, f"line 50 must carry a long comment in waybill-{n}"


def test_route_sheet_builder_is_deterministic() -> None:
    first = build_route_sheet_envelope(
        template_id="spike-route-sheet-weasy",
        template_version=SPIKE_TEMPLATE_VERSION,
    )
    second = build_route_sheet_envelope(
        template_id="spike-route-sheet-weasy",
        template_version=SPIKE_TEMPLATE_VERSION,
    )
    assert _hash(first) == _hash(second)
    assert first["document_number"] == "RS-FIX-1"
    assert len(first["document"]["trips"]) == 50
    assert len(first["document"]["refuels"]) == 10
    assert first["document"]["vehicle"]["make"] == "КамАЗ"
    assert first["document"]["driver"]["full_name"] == "Иванов Иван Иванович"
    # Mixed signer states (driver+dispatcher signed, mechanic blank for hand-fill).
    assert first["document"]["signers"]["driver"]["name"]
    assert not first["document"]["signers"]["mechanic"]["name"]
    assert first["document"]["signers"]["dispatcher"]["name"]


def test_fuel_report_builder_is_deterministic() -> None:
    for n in (100, 500, 1500):
        first = build_fuel_report_envelope(
            n,
            template_id="spike-fuel-report-weasy",
            template_version=SPIKE_TEMPLATE_VERSION,
        )
        second = build_fuel_report_envelope(
            n,
            template_id="spike-fuel-report-weasy",
            template_version=SPIKE_TEMPLATE_VERSION,
        )
        assert _hash(first) == _hash(second)
        assert first["document_number"] == f"FR-FIX-{n}"
        assert first["document"]["period"] == {"year": 2026, "month": 7}
        assert len(first["document"]["vehicles"]) == 10
        assert len(first["document"]["rows"]) == n
        assert len(first["document"]["subtotals"]) == 10
        # Per Phase 2 plan: chart block is OMITTED (stretch goal).
        assert "chart" not in first["document"]
        # Subtotals must add up to the grand total within rounding tolerance.
        g = first["document"]["grand_total"]
        s_vol = sum(s["total_volume_l"] for s in first["document"]["subtotals"])
        s_cost = sum(s["total_cost"] for s in first["document"]["subtotals"])
        s_dist = sum(s["total_distance_km"] for s in first["document"]["subtotals"])
        assert abs(s_vol - g["total_volume_l"]) <= 0.01
        assert abs(s_cost - g["total_cost"]) <= 0.01
        assert abs(s_dist - g["total_distance_km"]) <= 0.1


# ---------------------------------------------------------------------------
# On-disk fixtures: full envelope schema + contract validation.
# ---------------------------------------------------------------------------


def _all_committed_pairs() -> dict[str, dict[str, Path]]:
    """Return ``{stem: {"weasy": path, "typst": path}}`` for all committed pairs."""
    by_stem: dict[str, dict[str, Path]] = {}
    for root in (WAYBILL_DIR, ROUTE_DIR, FUEL_DIR):
        for path in sorted(root.glob("*.json")):
            stem, backend = path.stem.rsplit(".", 1)
            by_stem.setdefault(stem, {})[backend] = path
    return by_stem


def test_all_committed_fixtures_parse_and_have_template_pair() -> None:
    """Every committed envelope must validate via parse_envelope.

    For each logical fixture the weasy/typst pair must share the same
    ``document`` section and point at the correct backend-specific
    ``template_id``/``template_version``.
    """
    by_stem = _all_committed_pairs()
    assert len(by_stem) == 9, f"expected 9 logical fixtures, got {len(by_stem)}"
    total_files = sum(len(backend_map) for backend_map in by_stem.values())
    assert total_files == 18, f"expected 18 committed files, got {total_files}"

    for stem, files in sorted(by_stem.items()):
        weasy_f = files["weasy"]
        typst_f = files["typst"]

        weasy_env = parse_envelope(weasy_f.read_text(encoding="utf-8"))
        typst_env = parse_envelope(typst_f.read_text(encoding="utf-8"))

        # Document contract and data section MUST match.
        assert weasy_env.document_contract == typst_env.document_contract
        assert _envelope_data(weasy_env.data) == _envelope_data(typst_env.data)

        if stem.startswith("waybill"):
            assert weasy_env.template_id == WAYBILL_WEASY_TEMPLATE_ID
            assert weasy_env.template_version == WAYBILL_WEASY_TEMPLATE_VERSION
            assert typst_env.template_id == WAYBILL_TYPST_TEMPLATE_ID
            assert typst_env.template_version == WAYBILL_TYPST_TEMPLATE_VERSION
        elif stem.startswith("vehicle-route-sheet"):
            assert weasy_env.template_id == "spike-route-sheet-weasy"
            assert typst_env.template_id == "spike-route-sheet-typst"
            assert weasy_env.template_version == SPIKE_TEMPLATE_VERSION
            assert typst_env.template_version == SPIKE_TEMPLATE_VERSION
        elif stem.startswith("fuel-report"):
            assert weasy_env.template_id == "spike-fuel-report-weasy"
            assert typst_env.template_id == "spike-fuel-report-typst"
            assert weasy_env.template_version == SPIKE_TEMPLATE_VERSION
            assert typst_env.template_version == SPIKE_TEMPLATE_VERSION
        else:  # pragma: no cover - structural guard
            raise AssertionError(f"unexpected fixture stem: {stem}")


def test_committed_waybill_lines_satisfy_tz_diversity() -> None:
    """Re-validate the explicit TZ §9.1 diversity properties on the largest waybill."""
    raw = (WAYBILL_DIR / "waybill-500.weasy.json").read_text(encoding="utf-8")
    env = parse_envelope(raw)
    lines = env.document["lines"]
    assert len(lines) == 500
    # Categories: must include "Без категории".
    assert "Без категории" in {line["category_name"] for line in lines}
    # Quantities: at least one decimal.
    assert any(q != int(q) for q in (line["quantity"] for line in lines))
    # Units: all six unit symbols present somewhere in the largest fixture.
    symbols = {line["unit_symbol"] for line in lines}
    assert {"шт", "кг", "л", "м", "упак", "пара"}.issubset(symbols)
    # Long item names (≥80 chars, 2–4 visual lines at 40 chars/visual line).
    long_named = sum(1 for line in lines if len(line["item_name"]) >= 80)
    assert long_named >= 50, f"expected ≥50 long names in 500 lines, got {long_named}"
    # Mix of SKU states (filled + empty) and batch states.
    assert any(line["item_sku"] for line in lines)
    assert any(not line["item_sku"] for line in lines)
    assert any(line["batch"] for line in lines)
    assert any(line["batch"] is None for line in lines)
    # Long comment on line 50.
    comment_50 = lines[49].get("comment")
    assert isinstance(comment_50, str) and len(comment_50) > 100
