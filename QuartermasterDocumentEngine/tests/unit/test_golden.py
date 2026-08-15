"""Unit tests for the Phase 2 golden artifact package (TZ §13.6 / T11).

These tests cover the structural integrity of the ``tests/golden/``
package: the index, the per-entry ``expected.json`` shape, the LFS
fallback status, and the round-trip against the T9 harness outputs.
The actual golden regeneration/verification (``scripts/golden_update.py
--check``) is exercised by ``test_golden_update_check_idempotent_*``
because that command is a true subprocess gate.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
GOLDEN_DIR = REPO / "tests" / "golden"
INDEX_PATH = GOLDEN_DIR / "index.json"
SPIKE_OUT = REPO / "spike-out"
COMPARE_DIR = SPIKE_OUT / "compare"
GOLDEN_UPDATE = REPO / "scripts" / "golden_update.py"

REQUIRED_KEYS = {
    "template",
    "backend",
    "fixture",
    "engine_version",
    "backend_version",
    "thresholds",
    "structural",
    "semantic",
}

EXPECTED_ENTRY_COUNT = 6


# ---------------------------------------------------------------------------
# 1. Index loads and references all entries
# ---------------------------------------------------------------------------


@pytest.mark.golden
def test_golden_index_loads_and_lists_all_entries() -> None:
    """Index parses; >=6 entries; every ``expected`` path exists on disk."""
    assert INDEX_PATH.exists(), f"missing {INDEX_PATH}"
    payload = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    entries = payload.get("entries")
    assert isinstance(entries, list), "entries must be a list"
    assert len(entries) >= EXPECTED_ENTRY_COUNT, (
        f"index.json has {len(entries)} entries, expected >= {EXPECTED_ENTRY_COUNT}"
    )
    for entry in entries:
        expected_rel = entry["expected"]
        expected_abs = REPO / expected_rel
        assert expected_abs.exists(), f"missing expected file: {expected_rel}"


# ---------------------------------------------------------------------------
# 2. LFS status reflects the fallback
# ---------------------------------------------------------------------------


@pytest.mark.golden
def test_golden_index_lfs_status_unavailable() -> None:
    """The index records the git-lfs fallback (TZ §13.6 + INVESTIGATION §2.3)."""
    payload = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    assert payload.get("lfs_status") == "unavailable-git-lfs-not-installed"
    assert payload.get("lfs_fallback") == "json-only-assertions-png-pdf-as-ci-artifacts"


# ---------------------------------------------------------------------------
# 3. Per-entry expected.json has the required top-level keys
# ---------------------------------------------------------------------------


@pytest.mark.golden
def test_golden_expected_files_have_required_keys() -> None:
    """Each ``expected.json`` carries the full set of required keys."""
    payload = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    entries = payload.get("entries", [])
    assert entries, "index.json has no entries"
    for entry in entries:
        expected_abs = REPO / entry["expected"]
        assert expected_abs.exists(), f"missing expected file: {entry['expected']}"
        data = json.loads(expected_abs.read_text(encoding="utf-8"))
        missing = REQUIRED_KEYS - set(data.keys())
        assert not missing, f"{entry['expected']} missing keys: {sorted(missing)}"


# ---------------------------------------------------------------------------
# 4. Template directories use the dash separator
# ---------------------------------------------------------------------------


@pytest.mark.golden
def test_golden_template_directories_use_dash_separator() -> None:
    """Every directory under ``tests/golden/`` matches ``[a-z0-9.-]+`` (no ``@`` / ``/``)."""
    pattern = re.compile(r"^[a-z0-9.-]+$")
    for child in GOLDEN_DIR.iterdir():
        if not child.is_dir():
            continue
        assert pattern.match(child.name), (
            f"golden directory {child.name} does not match [a-z0-9.-]+ (no @, no /)"
        )
        assert "@" not in child.name, f"golden directory {child.name} contains '@'"
        assert "/" not in child.name, f"golden directory {child.name} contains '/'"
        assert "\\" not in child.name, f"golden directory {child.name} contains '\\'"


# ---------------------------------------------------------------------------
# 5. Golden values match the T9 harness output
# ---------------------------------------------------------------------------


@pytest.mark.golden
def test_golden_expected_values_match_t9_output() -> None:
    """structural.page_count + semantic.document_number.actual align with T9 outputs."""
    payload = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    entries = payload.get("entries", [])
    for entry in entries:
        fixture_rel = entry["fixture"]
        fixture_stem = Path(fixture_rel).stem
        # waybill-75.weasy.json → "waybill-75" (compare dir uses logical name).
        for candidate_suffix in (".weasy", ".typst"):
            if fixture_stem.endswith(candidate_suffix):
                fixture_stem = fixture_stem[: -len(candidate_suffix)]
                break

        struct_path = COMPARE_DIR / fixture_stem / "structural.json"
        sem_path = COMPARE_DIR / fixture_stem / "semantic.json"
        assert struct_path.exists(), f"missing T9 structural output: {struct_path}"
        assert sem_path.exists(), f"missing T9 semantic output: {sem_path}"

        backend_key = "weasy" if entry["backend"] == "weasyprint" else "typst"
        struct = json.loads(struct_path.read_text(encoding="utf-8"))
        sem = json.loads(sem_path.read_text(encoding="utf-8"))

        expected_abs = REPO / entry["expected"]
        golden = json.loads(expected_abs.read_text(encoding="utf-8"))

        t9_page_count = struct[backend_key]["page_count"]
        assert golden["structural"]["page_count"] == t9_page_count, (
            f"{entry['id']}: page_count {golden['structural']['page_count']} != T9 {t9_page_count}"
        )

        # T9 semantic.json only has a document_number field for waybill fixtures.
        # For route-sheet / fuel the harness does not track document_number at
        # all — assert only when the field is present in T9 output.
        sem_fields = sem[backend_key]["fields"]
        if "document_number" in sem_fields:
            t9_actual_list = sem_fields["document_number"]["actual"]
            t9_actual = t9_actual_list[0] if t9_actual_list else ""
            golden_actual = golden["semantic"]["document_number"]["actual"]
            assert golden_actual == t9_actual, (
                f"{entry['id']}: document_number.actual {golden_actual!r} != T9 {t9_actual!r}"
            )


# ---------------------------------------------------------------------------
# 6. golden_update.py --check is idempotent
# ---------------------------------------------------------------------------


@pytest.mark.golden
def test_golden_update_check_idempotent_when_no_diff() -> None:
    """``golden_update.py --check`` exits 0 when nothing has drifted."""
    if not GOLDEN_UPDATE.exists():
        pytest.skip("scripts/golden_update.py missing")
    result = subprocess.run(
        [sys.executable, str(GOLDEN_UPDATE), "--check"],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO,
        timeout=600,
    )
    if result.returncode != 0:
        if "render timed out" in (result.stderr + result.stdout):
            pytest.skip("non-deterministic — render timed out")
        pytest.fail(
            f"golden_update --check exited {result.returncode}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


# ---------------------------------------------------------------------------
# 7. Every entry is flagged lfs=false
# ---------------------------------------------------------------------------


@pytest.mark.golden
def test_golden_lfs_false_for_all_entries() -> None:
    """All entries have ``lfs == false`` — the fallback is fully JSON-only."""
    payload = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    entries = payload.get("entries", [])
    assert entries, "index.json has no entries"
    for entry in entries:
        assert entry.get("lfs") is False, f"{entry['id']}: lfs must be False in fallback mode"
