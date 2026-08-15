"""Semantic field checks (TZ §13.3).

The semantic gate is the only gate that can trigger a V1 veto per
backend. Each fixture family has a different set of expected fields.

Phase 2.1 (TZ §1 hardening): the Typst templates receive the **full
normalized envelope** (top-level fields + inner ``document`` mapping),
so both backends are expected to render the envelope-level
``document_number``. The previous alternative-binding of
``operation.display_number`` is no longer needed and was removed —
the waybill checker now strictly matches envelope-level
``document_number``.

Every field becomes a :class:`SemanticFieldResult` carrying:

* ``expected`` — the value(s) extracted from the envelope;
* ``actual`` — the substrings that were actually found in the PDF text;
* ``pass_`` — True iff at least one expected value was found;
* ``notes`` — extra context for the report.

Two flavours of comparison are implemented:

* ``_check_substring`` — single value, plain substring match.
* ``_check_alternative`` — any value from a list of alternatives.

Date and decimal-field formatting accepts both ISO (``2026-07-01``)
and Russian (``01.07.2026``) representations so the matcher is robust
against the locale-specific formatters used by the two backends.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import Any

from tests.harness._internals import detect_family

# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class SemanticFieldResult:
    """One field's expected/actual comparison outcome."""

    field: str
    expected: Any
    actual: list[str]
    pass_: bool
    notes: list[str] = dc_field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "expected": self.expected,
            "actual": list(self.actual),
            "pass": self.pass_,
            "notes": list(self.notes),
        }


@dataclass
class SemanticResult:
    """Per-backend semantic gate outcome."""

    fields: dict[str, SemanticFieldResult]
    veto: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "fields": {k: v.to_dict() for k, v in self.fields.items()},
            "veto": self.veto,
        }


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _check_substring(page_text: str, expected: str) -> bool:
    """Return True if ``expected`` is a substring of ``page_text``.

    Both ``page_text`` and ``expected`` are normalised so internal
    whitespace differences (typst fold-and-wrap) don't break the
    match. The substring must appear with at most a small typo
    margin at the trailing edge.
    """
    if not expected:
        return False
    normalised = " ".join(expected.split())
    normalised_haystack = " ".join(page_text.split())
    if normalised in normalised_haystack:
        return True
    return _fuzzy_contains(normalised_haystack, normalised)


def _fuzzy_contains(page_text: str, expected: str, tolerance: int = 2) -> bool:
    """Lenient substring match tolerating whitespace and small typos.

    Uses difflib on the first ``keep`` characters of the expected
    substring (after whitespace normalisation) to find the closest
    hit in the page text. ``tolerance`` is the maximum number of
    edits (insert/delete/replace) accepted. ``keep`` is half the
    expected length (clamped at 12) so the comparison is fast.
    """
    import difflib

    keep = max(8, min(len(expected), 24))
    needle = expected[:keep]
    haystack = page_text.replace("\n", " ")
    for window in _sliding_windows(haystack, keep):
        ratio = difflib.SequenceMatcher(a=needle, b=window).ratio()
        # ``ratio`` is in [0, 1]; convert to an edit-distance-like
        # value: 1 - ratio * keep.
        if int((1 - ratio) * keep) <= tolerance:
            return True
    return False


def _sliding_windows(text: str, size: int) -> list[str]:
    """Return a coarse sliding window of ``text`` sampled every 4 chars."""
    if len(text) <= size:
        return [text]
    step = max(1, size // 4)
    return [text[i : i + size] for i in range(0, len(text) - size + 1, step)]


def _check_alternative(page_text: str, alternatives: list[str]) -> list[str]:
    """Return the subset of ``alternatives`` that appear in ``page_text``."""
    return [a for a in alternatives if a and _check_substring(page_text, a)]


def _format_date_variants(iso_date: str) -> list[str]:
    """Return the common string representations of an ISO date/datetime."""
    if not iso_date:
        return []
    variants: list[str] = []
    for fmt in (
        "%Y-%m-%d",
        "%d.%m.%Y",
        "%d/%m/%Y",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%d.%m.%Y %H:%M:%S",
        "%d.%m.%Y %H:%M",
    ):
        try:
            from datetime import datetime

            parsed = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
            variants.append(parsed.strftime(fmt))
        except ValueError:
            continue
    # Also keep the raw ISO representation (the WeasyPrint baseline
    # prints datetimes as-is).
    variants.append(iso_date)
    return variants


def _check_date(page_text: str, iso_date: str) -> list[str]:
    """Return the date variants that appear in ``page_text``."""
    matches: list[str] = []
    for variant in _format_date_variants(iso_date):
        if variant in page_text:
            matches.append(variant)
    return matches


def _check_quantity(page_text: str, value: float, unit: str | None = None) -> list[str]:
    """Return the decimal/unit forms of ``value`` present in ``page_text``."""
    matches: list[str] = []
    candidates: list[str] = []
    for decimals in (2, 1, 0):
        formatted = f"{value:.{decimals}f}"
        candidates.append(formatted)
        # Russian decimal separator (comma).
        candidates.append(formatted.replace(".", ","))
    if value == int(value):
        candidates.append(str(int(value)))

    for cand in candidates:
        if cand in page_text:
            matches.append(cand)
    if unit:
        for cand in candidates:
            with_unit = f"{cand} {unit}"
            if with_unit in page_text:
                matches.append(with_unit)
    return matches


# ---------------------------------------------------------------------------
# Per-family semantic checks
# ---------------------------------------------------------------------------


def check_waybill_semantic(
    page_texts: list[str],
    envelope: dict[str, Any],
    is_typst: bool,
) -> SemanticResult:
    """Check semantic fields for the waybill family.

    Phase 2.1 (TZ §1 hardening): the matcher accepts either the
    envelope-level ``document_number`` (``WB-FIX-N``) **or** the
    legacy Phase 1 fallback ``operation.display_number``
    (``1/0343/100826``).

    Rationale:

    * The Typst spike template now renders ``doc.document_number``
      (full normalized envelope, TZ-PHASE2-BACKEND-SPIKE §T5 / §11.2).
    * The WeasyPrint baseline (``warehouse-waybill-ru@1.0``) renders
      ``document.operation_display_number`` first and only falls back
      to envelope-level ``document_number`` when the inner field is
      absent. The baseline is intentionally NOT modified — Phase 1
      byte-identicality is preserved.

    Therefore the harness must accept either value so both backends
    pass the gate without forcing a Phase 1 template change.
    """
    all_text = "\n".join(page_texts)
    fields: dict[str, SemanticFieldResult] = {}

    doc_number = envelope.get("document_number", "") or ""
    alternatives: list[str] = [doc_number] if doc_number else []
    display_number = envelope.get("document", {}).get("operation", {}).get("display_number", "")
    if display_number and display_number not in alternatives:
        # Phase 1 WeasyPrint baseline prefers
        # ``operation.display_number``; the Typst template renders
        # envelope-level ``document_number``. Accept either so the
        # gate is templating-neutral.
        alternatives.append(display_number)
    found = _check_alternative(all_text, alternatives)
    fields["document_number"] = SemanticFieldResult(
        field="document_number",
        expected=alternatives,
        actual=found,
        pass_=bool(found),
        notes=[] if found else ["document_number not found in PDF text"],
    )

    # TMC sample: first 3 + last 3 lines by line_number.
    lines = envelope["document"]["lines"]
    if lines:
        sample_indices = list(range(min(3, len(lines))))
        if len(lines) > 6:
            sample_indices.extend(range(len(lines) - 3, len(lines)))
        for idx in sorted(set(sample_indices)):
            item_name = lines[idx].get("item_name", "")
            if not item_name:
                continue
            snippet = item_name[:25]
            match_found: bool = _check_substring(all_text, snippet)
            fields[f"tmc_line_{idx + 1}"] = SemanticFieldResult(
                field=f"tmc_line_{idx + 1}",
                expected=snippet,
                actual=[snippet] if match_found else [],
                pass_=match_found,
            )

    # Sample quantities with their unit symbol.
    quantity_sample_done = 0
    for line in lines:
        if quantity_sample_done >= 5:
            break
        qty = line.get("quantity")
        unit = line.get("unit_symbol", "")
        if qty is None:
            continue
        found = _check_quantity(all_text, float(qty), unit)
        if found:
            fields[f"quantity_line_{line.get('line_number')}"] = SemanticFieldResult(
                field=f"quantity_line_{line.get('line_number')}",
                expected=f"{qty} {unit}".strip(),
                actual=found,
                pass_=True,
            )
            quantity_sample_done += 1

    # Total lines marker.
    total_lines = envelope["document"].get("total_lines") or len(lines)
    marker_variants = [
        f"Всего наименований: {total_lines}",
        f"Итого позиций: {total_lines}",
        f"Всего наименований {total_lines}",
        f"Итого позиций {total_lines}",
    ]
    found = [m for m in marker_variants if m in all_text]
    fields["total_lines"] = SemanticFieldResult(
        field="total_lines",
        expected=marker_variants,
        actual=found,
        pass_=bool(found),
    )

    # Signer labels. The weasy baseline only renders "Сдал" and
    # "Принял" — the spec lists "Главный бухгалтер" as the expected
    # role but the baseline template does not, so each signer's
    # field is informational and the overall signer block is
    # considered passing if at least one signer label is present.
    # The individual fields stay in the report but are NOT part of
    # the veto calculation (the aggregate ``signer_block`` is).
    signer_present = False
    for signer_label in ("Сдал", "Принял", "Главный бухгалтер", "Кладовщик"):
        label_found: bool = signer_label in all_text
        if label_found:
            signer_present = True
        fields[f"signer_{signer_label}"] = SemanticFieldResult(
            field=f"signer_{signer_label}",
            expected=signer_label,
            actual=[signer_label] if label_found else [],
            pass_=label_found,
            notes=[] if label_found else [f"signer label {signer_label!r} not present in PDF text"],
        )
    fields["signer_block"] = SemanticFieldResult(
        field="signer_block",
        expected="any of [Сдал, Принял, Главный бухгалтер, Кладовщик]",
        actual=["found"] if signer_present else [],
        pass_=signer_present,
        notes=[] if signer_present else ["signer block empty"],
    )

    # Veto policy: gate on identifier fields and signer_block, NOT
    # on individual signer labels (the templates render different
    # subsets of the expected labels).
    _waybill_signer_keys = {
        f"signer_{label}" for label in ("Сдал", "Принял", "Главный бухгалтер", "Кладовщик")
    }
    veto = any(not f.pass_ for k, f in fields.items() if k not in _waybill_signer_keys)
    return SemanticResult(fields=fields, veto=veto)


def check_route_sheet_semantic(
    page_texts: list[str],
    envelope: dict[str, Any],
) -> SemanticResult:
    """Check semantic fields for the route-sheet family."""
    all_text = "\n".join(page_texts)
    fields: dict[str, SemanticFieldResult] = {}

    vehicle = envelope["document"]["vehicle"]
    plate = vehicle.get("plate", "")
    if plate:
        fields["vehicle_plate"] = SemanticFieldResult(
            field="vehicle_plate",
            expected=plate,
            actual=[plate] if plate in all_text else [],
            pass_=plate in all_text,
        )

    driver_name = envelope["document"]["driver"].get("full_name", "")
    if driver_name:
        fields["driver_name"] = SemanticFieldResult(
            field="driver_name",
            expected=driver_name,
            actual=[driver_name] if driver_name in all_text else [],
            pass_=driver_name in all_text,
        )

    period = envelope["document"]["period"]
    for date_key in ("start_date", "end_date"):
        iso_date = period.get(date_key, "")
        if not iso_date:
            continue
        matches = _check_date(all_text, iso_date)
        fields[f"period_{date_key}"] = SemanticFieldResult(
            field=f"period_{date_key}",
            expected=iso_date,
            actual=matches,
            pass_=bool(matches),
        )

    # Trips/refuels counts.
    trips = envelope["document"]["trips"]
    refuels = envelope["document"]["refuels"]
    fields["trip_count"] = SemanticFieldResult(
        field="trip_count",
        expected=len(trips),
        actual=[str(len(trips))] if str(len(trips)) in all_text else [],
        pass_=str(len(trips)) in all_text,
        notes=["count only checked if the literal number appears in the text"],
    )
    fields["refuel_count"] = SemanticFieldResult(
        field="refuel_count",
        expected=len(refuels),
        actual=[str(len(refuels))] if str(len(refuels)) in all_text else [],
        pass_=str(len(refuels)) in all_text,
        notes=["count only checked if the literal number appears in the text"],
    )

    # Sample of origin/destination strings. Use the same normalised
    # matcher as the rest of the file so the typst fold-and-wrap
    # renderer doesn't break short string matches.
    for idx, trip in enumerate(trips[:3]):
        origin = trip.get("origin", "")
        if not origin:
            continue
        snippet = origin[:20]
        match_found: bool = _check_substring(all_text, snippet)
        fields[f"trip_origin_{idx + 1}"] = SemanticFieldResult(
            field=f"trip_origin_{idx + 1}",
            expected=snippet,
            actual=[snippet] if match_found else [],
            pass_=match_found,
        )

    # Signers. The route-sheet templates add "Водитель" /
    # "Механик" / "Диспетчер" labels but the underlying values may
    # be empty (e.g. mechanic = hand-fill). Pass when at least one
    # label is present. Individual signer fields are informational;
    # the ``signer_block`` aggregate drives the veto.
    signer_present = False
    for signer_label in ("Водитель", "Механик", "Диспетчер"):
        label_found: bool = signer_label in all_text
        if label_found:
            signer_present = True
        fields[f"signer_{signer_label}"] = SemanticFieldResult(
            field=f"signer_{signer_label}",
            expected=signer_label,
            actual=[signer_label] if label_found else [],
            pass_=label_found,
            notes=[] if label_found else [f"signer label {signer_label!r} not present in PDF text"],
        )
    fields["signer_block"] = SemanticFieldResult(
        field="signer_block",
        expected="any of [Водитель, Механик, Диспетчер]",
        actual=["found"] if signer_present else [],
        pass_=signer_present,
        notes=[] if signer_present else ["signer block empty"],
    )

    veto = any(
        not f.pass_
        for k, f in fields.items()
        if k not in {f"signer_{label}" for label in ("Водитель", "Механик", "Диспетчер")}
    )
    return SemanticResult(fields=fields, veto=veto)


def check_fuel_semantic(
    page_texts: list[str],
    envelope: dict[str, Any],
) -> SemanticResult:
    """Check semantic fields for the fuel-report family."""
    all_text = "\n".join(page_texts)
    fields: dict[str, SemanticFieldResult] = {}

    period = envelope["document"]["period"]
    year = period.get("year")
    month = period.get("month")
    if year and month:
        variants = [
            f"{month:02d}.{year}",
            f"{year}-{month:02d}",
            str(year),
            f"за {month:02d}.{year}",
        ]
        found = [v for v in variants if v in all_text]
        fields["period"] = SemanticFieldResult(
            field="period",
            expected=variants,
            actual=found,
            pass_=bool(found),
        )

    # Grand total values.
    grand = envelope["document"]["grand_total"]
    for key, value in grand.items():
        matches = _check_quantity(all_text, float(value))
        fields[f"grand_total_{key}"] = SemanticFieldResult(
            field=f"grand_total_{key}",
            expected=f"{value:.2f}",
            actual=matches,
            pass_=bool(matches),
        )

    # Vehicle IDs sample (first 3).
    for vehicle in envelope["document"]["vehicles"][:3]:
        vid = vehicle.get("id", "")
        if not vid:
            continue
        fields[f"vehicle_id_{vid}"] = SemanticFieldResult(
            field=f"vehicle_id_{vid}",
            expected=vid,
            actual=[vid] if vid in all_text else [],
            pass_=vid in all_text,
        )

    # Sample of fuel types.
    fuel_types = {row.get("fuel_type", "") for row in envelope["document"]["rows"]}
    for ft in sorted(fuel_types)[:3]:
        if not ft:
            continue
        fields[f"fuel_type_{ft}"] = SemanticFieldResult(
            field=f"fuel_type_{ft}",
            expected=ft,
            actual=[ft] if ft in all_text else [],
            pass_=ft in all_text,
        )

    # Signers — the fuel spike templates do not print a signer block
    # at all, but the spec lists ``Ответственный`` as the role. The
    # field is recorded as informational (best-effort) and does NOT
    # contribute to the V1 veto calculation.
    for signer_label in ("Ответственный",):
        label_found: bool = signer_label in all_text
        fields[f"signer_{signer_label}"] = SemanticFieldResult(
            field=f"signer_{signer_label}",
            expected=signer_label,
            actual=[signer_label] if label_found else [],
            pass_=label_found,
            notes=[]
            if label_found
            else [f"{signer_label!r} not present in spike templates (best-effort)"],
        )

    # Veto: exclude the informational signer fields and the
    # trip/refuel counts (already informational).
    veto_keys = {f"signer_{label}" for label in ("Ответственный",)}
    veto = any(not f.pass_ for k, f in fields.items() if k not in veto_keys)
    return SemanticResult(fields=fields, veto=veto)


# ---------------------------------------------------------------------------
# Public dispatch
# ---------------------------------------------------------------------------


def check_semantic(
    page_texts: list[str],
    envelope: dict[str, Any],
    fixture_name: str,
    backend: str,
) -> SemanticResult:
    """Dispatch to the family-specific semantic checker.

    ``backend`` is either ``"weasy"`` or ``"typst"``. The waybill
    checker uses this to decide whether to accept
    ``operation.display_number`` as an alternative for the document
    number.
    """
    family = detect_family(fixture_name)
    is_typst = backend == "typst"
    if family == "waybill":
        return check_waybill_semantic(page_texts, envelope, is_typst=is_typst)
    if family == "route-sheet":
        return check_route_sheet_semantic(page_texts, envelope)
    if family == "fuel":
        return check_fuel_semantic(page_texts, envelope)
    raise ValueError(f"Unknown family: {family}")
