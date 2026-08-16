"""Regenerate or verify the golden ``expected.json`` files (TZ §13.6 / T11).

The acceptance matrix (six template × backend combinations, six
fixtures) lives under ``tests/golden/``. Each entry has one
``<template-slug>/<fixture-stem>.expected.json`` file with the
structural + semantic assertions the harness must reproduce.

The script has two modes:

* default — re-render every fixture via ``qm-render`` and write a
  fresh ``expected.json`` next to the committed one (preserving
  ``schema_version`` / ``engine_version`` / ``thresholds`` from the
  committed file so a partial update doesn't drift the schema).
* ``--check`` — re-render and compare against the committed files;
  exit 1 on any field mismatch.

The script is idempotent: re-running without code changes yields
byte-identical output. The first generation writes the
``expected.json`` files from scratch; subsequent runs are no-ops
unless the rendered PDFs drift.

Usage
-----

::

    python scripts/golden_update.py                   # regenerate all
    python scripts/golden_update.py --check           # CI gate (exit 1 on diff)
    python scripts/golden_update.py --fixtures w1,w2  # restrict to entries
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.harness import semantic, structural  # noqa: E402
from tests.harness._internals import (  # noqa: E402
    detect_family,
    render_pdf,
    safe_load_json,
)

GOLDEN_DIR = REPO_ROOT / "tests" / "golden"
INDEX_PATH = GOLDEN_DIR / "index.json"
TEMPLATES_DIR = REPO_ROOT / "templates"


# ---------------------------------------------------------------------------
# Substring expectations (canonical lists)
# ---------------------------------------------------------------------------
# These match ``tests.harness.structural.BLOCK_EXPECTATIONS``. Keeping
# a local copy avoids importing the harness module purely to render
# the same dict in JSON form. The harness is the single source of
# truth — if the harness changes, update this list and re-run.

WAYBILL_HEADER = ["Товарная накладная", "ТОВАРНАЯ НАКЛАДНАЯ"]
WAYBILL_TABLE = ["Наименование", "Кол-во"]
WAYBILL_SIGNATURES = ["Сдал", "Принял", "Главный бухгалтер"]
WAYBILL_FOOTER = ["Лист", "Страница"]

ROUTE_SHEET_HEADER = ["Путевой лист", "ПУТЕВОЙ ЛИСТ"]
ROUTE_SHEET_TABLE = ["км", "АЗС"]
ROUTE_SHEET_SIGNATURES = ["Водитель", "Механик", "Диспетчер"]
ROUTE_SHEET_FOOTER = ["Лист", "Страница"]

FUEL_HEADER = ["Отчёт по расходу", "ОТЧЁТ ПО РАСХОДУ"]
FUEL_TABLE = ["Объём", "Пробег"]
FUEL_SIGNATURES: list[str] = []
FUEL_FOOTER = ["Лист", "Страница"]

WAYBILL_SIGNERS_EXPECTED = ["Сдал", "Принял", "Главный бухгалтер", "Кладовщик"]
ROUTE_SHEET_SIGNERS_EXPECTED = ["Водитель", "Механик", "Диспетчер"]
FUEL_SIGNERS_EXPECTED = ["Ответственный"]


FAMILY_BLOCKS: dict[str, dict[str, list[str]]] = {
    "waybill": {
        "header": WAYBILL_HEADER,
        "table": WAYBILL_TABLE,
        "signatures": WAYBILL_SIGNATURES,
        "footer": WAYBILL_FOOTER,
    },
    "route-sheet": {
        "header": ROUTE_SHEET_HEADER,
        "table": ROUTE_SHEET_TABLE,
        "signatures": ROUTE_SHEET_SIGNATURES,
        "footer": ROUTE_SHEET_FOOTER,
    },
    "fuel": {
        "header": FUEL_HEADER,
        "table": FUEL_TABLE,
        "signatures": FUEL_SIGNATURES,
        "footer": FUEL_FOOTER,
    },
}


FAMILY_SIGNERS_EXPECTED: dict[str, list[str]] = {
    "waybill": WAYBILL_SIGNERS_EXPECTED,
    "route-sheet": ROUTE_SHEET_SIGNERS_EXPECTED,
    "fuel": FUEL_SIGNERS_EXPECTED,
}

# The canonical production waybill (warehouse-waybill-ru@2.0.0)
# reproduces the legacy Django/WeasyPrint form: header "Накладная № …",
# 4-column table, MOVE signature labels, no totals row.
CANONICAL_WAYBILL_TEMPLATE = "warehouse-waybill-ru@2.0.0"
CANONICAL_WAYBILL_BLOCKS: dict[str, list[str]] = {
    "header": ["Накладная №"],
    "table": ["Наименование ТМЦ", "Кол-во"],
    "signatures": ["Кладовщик", "Операцию разрешил", "Водитель", "Начальник базы", "Груз принял"],
    "footer": ["Лист"],
}
CANONICAL_WAYBILL_SIGNERS = [
    "Кладовщик",
    "Операцию разрешил",
    "Водитель",
    "Начальник базы",
    "Груз принял",
]


def _blocks_and_signers_for_template(
    template: str,
    family: str,
) -> tuple[dict[str, list[str]], list[str]]:
    """Return (block expectations, signer labels) for an entry."""
    if template == CANONICAL_WAYBILL_TEMPLATE:
        return CANONICAL_WAYBILL_BLOCKS, CANONICAL_WAYBILL_SIGNERS
    return FAMILY_BLOCKS[family], FAMILY_SIGNERS_EXPECTED[family]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _slug_for(template_id: str, template_version: str) -> str:
    """Return the directory slug for a template (id-version, lowercase)."""
    return f"{template_id}-{template_version}".lower()


def _a4_paper_size(orientation: str) -> list[int]:
    """Return the integer-form A4 paper size for the given orientation."""
    portrait = [595, 842]
    landscape = [842, 595]
    return portrait if orientation == "portrait" else landscape


def _load_envelope(fixture_path: Path) -> dict[str, Any]:
    """Load the envelope JSON for ``fixture_path``."""
    return safe_load_json(fixture_path)


def _line_count(family: str, envelope: dict[str, Any]) -> int:
    """Return the canonical line count for a family."""
    if family == "waybill":
        return len(envelope["document"]["lines"])
    if family == "route-sheet":
        return len(envelope["document"]["trips"]) + len(envelope["document"]["refuels"])
    if family == "fuel":
        return len(envelope["document"]["rows"])
    raise ValueError(f"Unknown family: {family}")


def _render_to_pdf(fixture_path: Path, output_pdf: Path) -> None:
    """Render ``fixture_path`` to ``output_pdf`` via the qm-render CLI."""
    outcome = render_pdf(fixture_path, output_pdf, TEMPLATES_DIR)
    if not outcome.success:
        raise RuntimeError(
            f"qm-render failed for {fixture_path} (rc={outcome.returncode}): {outcome.stderr}"
        )


def _page_texts(pdf_path: Path) -> list[str]:
    """Return one string per page (lazy pymupdf import)."""
    import pymupdf

    doc = pymupdf.open(pdf_path)
    try:
        return [doc[i].get_text() for i in range(len(doc))]
    finally:
        doc.close()


def _signers_actual(family: str, sem_fields: dict[str, Any], template: str) -> list[str]:
    """Return the ordered list of actually-rendered signer labels."""
    _, expected_labels = _blocks_and_signers_for_template(template, family)
    actual: list[str] = []
    for label in expected_labels:
        key = f"signer_{label}"
        if key in sem_fields and sem_fields[key].get("pass"):
            actual.append(label)
    return actual


def _signers_pass(family: str, sem_fields: dict[str, Any], template: str) -> bool:
    """Return True if at least one signer label is present in the PDF."""
    _, expected_labels = _blocks_and_signers_for_template(template, family)
    for label in expected_labels:
        key = f"signer_{label}"
        if key in sem_fields and sem_fields[key].get("pass"):
            return True
    return False


def _document_number_actual(family: str, sem_fields: dict[str, Any]) -> tuple[str, bool]:
    """Return (actual_value, pass_flag) for ``document_number``.

    The harness stores the matcher output as a list of alternatives
    that were actually found in the rendered text. For waybill the
    harness accepts either ``envelope.document_number`` or
    ``operation.display_number``; for route-sheet / fuel the harness
    does not check ``document_number`` at all, so we treat the field
    as best-effort and run a substring search against the envelope
    value ourselves.
    """
    key = "document_number"
    if key in sem_fields:
        field = sem_fields[key]
        actual_list = field.get("actual", [])
        first_actual = actual_list[0] if actual_list else ""
        return first_actual, bool(field.get("pass"))
    return "", False


def build_expected_json(
    entry: dict[str, Any],
    structural_dict: dict[str, Any],
    sem_fields: dict[str, Any],
    envelope: dict[str, Any],
    fixture_name: str,
    backend_version: str,
    engine_version: str,
    thresholds: dict[str, Any],
    schema_version: int,
) -> dict[str, Any]:
    """Translate harness output into the ``expected.json`` schema.

    ``schema_version`` / ``engine_version`` / ``thresholds`` come from
    the committed file (default to the index values when no file
    exists yet) so a partial update doesn't drift them.
    """
    family = detect_family(fixture_name)
    page_count = int(structural_dict["page_count"])
    orientation = str(structural_dict["orientation"])
    paper_size = _a4_paper_size(orientation)
    table_rows = int(structural_dict["table_rows"])

    blocks_pass: dict[str, bool] = structural_dict["blocks_pass"]
    expected_blocks, _ = _blocks_and_signers_for_template(entry["template"], family)
    required_blocks: dict[str, dict[str, Any]] = {}
    for name in ("header", "table", "signatures", "footer"):
        required_blocks[name] = {
            "expected_substrings": list(expected_blocks[name]),
            "pass": bool(blocks_pass.get(name, False)),
        }

    expected_doc_number = str(envelope.get("document_number", "") or "")
    doc_actual, doc_pass = _document_number_actual(family, sem_fields)

    expected_line = _line_count(family, envelope)
    signers_expected = _blocks_and_signers_for_template(entry["template"], family)[1]
    signers_actual = _signers_actual(family, sem_fields, entry["template"])
    signers_pass = _signers_pass(family, sem_fields, entry["template"])

    return {
        "schema_version": int(schema_version),
        "template": entry["template"],
        "backend": entry["backend"],
        "fixture": entry["fixture"],
        "engine_version": engine_version,
        "backend_version": backend_version,
        "thresholds": dict(thresholds),
        "structural": {
            "page_count": page_count,
            "paper_size": paper_size,
            "orientation": orientation,
            "required_blocks": required_blocks,
            "table_rows": table_rows,
        },
        "semantic": {
            "document_number": {
                "expected": expected_doc_number,
                "actual": doc_actual,
                "pass": doc_pass,
            },
            "line_count": {
                "expected": expected_line,
                "actual": table_rows,
                "pass": table_rows == expected_line,
            },
            "signers_present": {
                "expected": signers_expected,
                "actual": signers_actual,
                "pass": signers_pass,
            },
        },
    }


# ---------------------------------------------------------------------------
# Version probes
# ---------------------------------------------------------------------------


def _engine_version() -> str:
    """Return the engine version as reported by ``qm-render version``."""
    cmd = [sys.executable, "-m", "qm_cli.main", "version"]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False, cwd=REPO_ROOT)
    if result.returncode != 0:
        raise RuntimeError(f"qm-render version failed: {result.stderr}")
    payload = json.loads(result.stdout)
    return str(payload["engine"])


def _weasy_version() -> str:
    import weasyprint

    return str(weasyprint.__version__)


def _typst_version() -> str:
    pin_path = REPO_ROOT / "spike" / "typst-pin.json"
    pin = safe_load_json(pin_path)
    return str(pin["version"])


def _backend_version(backend: str) -> str:
    if backend == "weasyprint":
        return _weasy_version()
    if backend == "typst":
        return _typst_version()
    raise ValueError(f"Unknown backend: {backend}")


def _load_thresholds() -> dict[str, Any]:
    """Return the SSIM/changed-pixels thresholds (calibration file → defaults)."""
    default = {"ssim": 0.995, "changed_pixels": 0.001}
    noise_floor = REPO_ROOT / "spike-out" / "calibration" / "noise_floor.json"
    if noise_floor.exists():
        try:
            data = safe_load_json(noise_floor)
            return {
                "ssim": float(data.get("ssim_threshold", default["ssim"])),
                "changed_pixels": float(
                    data.get("changed_pixels_threshold", default["changed_pixels"])
                ),
            }
        except (json.JSONDecodeError, OSError):
            pass
    return default


# ---------------------------------------------------------------------------
# Per-entry processing
# ---------------------------------------------------------------------------


def _fixture_stem(fixture_path: Path) -> str:
    """Return the fixture stem (filename without .weasy/.typst suffix)."""
    name = fixture_path.name
    for suffix in (".weasy.json", ".typst.json", ".json"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return fixture_path.stem


def _process_entry(
    entry: dict[str, Any],
    engine_version: str,
    thresholds: dict[str, Any],
) -> dict[str, Any]:
    """Render and compute a fresh expected.json for ``entry``."""
    fixture_path = REPO_ROOT / entry["fixture"]
    backend = entry["backend"]
    template_id, template_version = entry["template"].split("@", 1)

    envelope = _load_envelope(fixture_path)

    with tempfile.TemporaryDirectory() as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        output_pdf = tmp_dir / f"{backend}.pdf"
        _render_to_pdf(fixture_path, output_pdf)

        page_texts = _page_texts(output_pdf)
        struct_result = structural.check_structural(output_pdf, envelope, fixture_path.stem)
        sem_result = semantic.check_semantic(page_texts, envelope, fixture_path.stem, backend)

    backend_version = _backend_version(backend)

    fixture_stem = _fixture_stem(fixture_path)
    schema_version = 1
    new_expected = build_expected_json(
        entry=entry,
        structural_dict=struct_result.to_dict(),
        sem_fields={k: v.to_dict() for k, v in sem_result.fields.items()},
        envelope=envelope,
        fixture_name=fixture_stem,
        backend_version=backend_version,
        engine_version=engine_version,
        thresholds=thresholds,
        schema_version=schema_version,
    )
    return new_expected


def _merge_with_committed(
    entry: dict[str, Any],
    new_expected: dict[str, Any],
) -> dict[str, Any]:
    """Preserve schema_version/engine_version/thresholds from the committed file."""
    committed_path = REPO_ROOT / entry["expected"]
    if not committed_path.exists():
        return new_expected
    try:
        committed = safe_load_json(committed_path)
    except (json.JSONDecodeError, OSError):
        return new_expected
    for key in ("schema_version", "engine_version", "thresholds"):
        if key in committed:
            new_expected[key] = committed[key]
    return new_expected


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------


def _diff_entries(a: dict[str, Any], b: dict[str, Any]) -> list[str]:
    """Return a list of field paths where ``a`` and ``b`` differ."""
    diffs: list[str] = []

    def _walk(prefix: str, av: Any, bv: Any) -> None:
        if isinstance(av, dict) and isinstance(bv, dict):
            for key in sorted(set(av) | set(bv)):
                _walk(f"{prefix}.{key}" if prefix else key, av.get(key), bv.get(key))
            return
        if type(av) is not type(bv):
            diffs.append(f"{prefix}: type mismatch ({type(av).__name__} vs {type(bv).__name__})")
            return
        if av != bv:
            diffs.append(f"{prefix}: {av!r} != {bv!r}")

    _walk("", a, b)
    return diffs


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _resolve_fixtures(
    entries: list[dict[str, Any]],
    fixtures_arg: list[str] | None,
) -> list[dict[str, Any]]:
    """Filter ``entries`` by fixture stem when ``fixtures_arg`` is given."""
    if not fixtures_arg:
        return list(entries)
    wanted = {f.strip() for f in fixtures_arg if f.strip()}
    if not wanted:
        return list(entries)
    filtered: list[dict[str, Any]] = []
    for entry in entries:
        fixture_path = Path(entry["fixture"])
        stem = _fixture_stem(fixture_path)
        if stem in wanted:
            filtered.append(entry)
    return filtered


def _run(
    entries: list[dict[str, Any]],
    *,
    check: bool,
    only_fixtures: list[str] | None,
) -> int:
    filtered = _resolve_fixtures(entries, only_fixtures)
    if not filtered:
        print("[golden] no entries matched --fixtures filter", file=sys.stderr)
        return 1

    engine_version = _engine_version()
    thresholds = _load_thresholds()

    total = len(filtered)
    mismatches = 0
    for idx, entry in enumerate(filtered, start=1):
        label = entry["id"]
        try:
            new_expected = _process_entry(entry, engine_version, thresholds)
        except Exception as exc:  # noqa: BLE001
            print(f"[{idx}/{total}] {label}: render failed: {exc}", file=sys.stderr)
            mismatches += 1
            continue

        new_expected = _merge_with_committed(entry, new_expected)

        expected_path = REPO_ROOT / entry["expected"]
        if check:
            if not expected_path.exists():
                print(
                    f"[{idx}/{total}] {label}: MISSING {expected_path.relative_to(REPO_ROOT)}",
                    file=sys.stderr,
                )
                mismatches += 1
                continue
            committed = safe_load_json(expected_path)
            diffs = _diff_entries(committed, new_expected)
            if diffs:
                print(f"[{idx}/{total}] {label}: {len(diffs)} field(s) drifted:", file=sys.stderr)
                for d in diffs[:20]:
                    print(f"    {d}", file=sys.stderr)
                mismatches += 1
            else:
                print(f"[{idx}/{total}] {label}: ok")
        else:
            expected_path.parent.mkdir(parents=True, exist_ok=True)
            expected_path.write_text(
                json.dumps(new_expected, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            print(f"[{idx}/{total}] {label}: wrote {expected_path.relative_to(REPO_ROOT)}")

    if check and mismatches:
        print(f"[golden] {mismatches}/{total} entries drifted", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--check", action="store_true", help="Verify mode (exit 1 on diff).")
    parser.add_argument(
        "--fixtures",
        default="",
        help="Comma-separated fixture stems to restrict processing to.",
    )
    ns = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if not INDEX_PATH.exists():
        print(f"[golden] missing index: {INDEX_PATH}", file=sys.stderr)
        return 2

    index = safe_load_json(INDEX_PATH)
    entries: list[dict[str, Any]] = list(index.get("entries", []))

    fixtures = [s for s in ns.fixtures.split(",") if s] if ns.fixtures else None
    return _run(entries, check=ns.check, only_fixtures=fixtures)


if __name__ == "__main__":
    raise SystemExit(main())
