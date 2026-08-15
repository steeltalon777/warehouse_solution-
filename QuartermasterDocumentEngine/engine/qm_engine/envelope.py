"""Envelope parsing and validation (SPEC v2 §7, TZ-PHASE1-CLI-SKELETON).

The envelope is a self-contained versioned JSON payload built by the producer.
Phase 1 accepts ``engine_contract_version == "1.0.0"`` and validates the
envelope against the shipped JSON Schema, then validates the ``document``
section against the referenced document-contract schema.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator

from . import paths
from .errors import (
    InvalidPayloadError,
    UnsupportedDocumentContractError,
    UnsupportedEngineContractError,
)

# Document-contract id -> schema file resolved relative to the bundle contracts dir.
_DOCUMENT_CONTRACT_SCHEMAS: dict[str, str] = {
    "warehouse.operation-document/v2": "warehouse.operation-document/v2/schema.json",
    "transport.vehicle-route-sheet/v1": "transport.vehicle-route-sheet/v1/schema.json",
    "fuel.monthly-report/v1": "fuel.monthly-report/v1/schema.json",
}

# Supported output formats (Phase 1: PDF only).
SUPPORTED_OUTPUT_FORMATS = ("pdf",)

# Supported render profiles (Phase 1: print only).
SUPPORTED_RENDER_PROFILES = ("print",)


def _load_schema(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as fh:
            return cast(dict[str, Any], json.load(fh))
    except (OSError, json.JSONDecodeError) as exc:  # pragma: no cover - bundle integrity
        raise InvalidPayloadError(
            f"Unable to load bundle schema {path}: {exc}",
            {"schema": str(path)},
        ) from exc


class Envelope:
    """Validated document envelope."""

    def __init__(self, data: Mapping[str, Any]) -> None:
        self.data = dict(data)
        self.engine_contract_version: str = self.data["engine_contract_version"]
        self.document_contract: str = self.data["document_contract"]
        self.document_type: str = self.data["document_type"]
        self.template_id: str = self.data["template_id"]
        self.template_version: str = self.data["template_version"]
        self.locale: str = self.data["locale"]
        self.render_profile: str = self.data["render_profile"]
        self.document: Mapping[str, Any] = self.data["document"]
        self.document_id: str | None = self.data.get("document_id")
        self.document_number: str | None = self.data.get("document_number")
        self.assets: Mapping[str, Any] = self.data.get("assets", {})


def _validate_engine_contract(version: str) -> None:
    if version != paths.ENGINE_CONTRACT_VERSION:
        raise UnsupportedEngineContractError(
            f"Unsupported engine_contract_version '{version}'; "
            f"this engine supports '{paths.ENGINE_CONTRACT_VERSION}'",
            {"engine_contract_version": version, "supported": paths.ENGINE_CONTRACT_VERSION},
        )


def _validate_output_format(output_format: str) -> None:
    if output_format not in SUPPORTED_OUTPUT_FORMATS:
        from .errors import UnsupportedOutputFormatError

        raise UnsupportedOutputFormatError(
            f"Unsupported output format '{output_format}'; "
            f"supported: {', '.join(SUPPORTED_OUTPUT_FORMATS)}",
            {"output_format": output_format, "supported": list(SUPPORTED_OUTPUT_FORMATS)},
        )


def _schema_for_document_contract(document_contract: str) -> Path:
    rel = _DOCUMENT_CONTRACT_SCHEMAS.get(document_contract)
    if rel is None:
        raise UnsupportedDocumentContractError(
            f"Unsupported document_contract '{document_contract}'",
            {"document_contract": document_contract},
        )
    return paths.contracts_dir() / rel


def validate_envelope_structure(data: Mapping[str, Any]) -> None:
    """Validate the envelope against the shipped envelope JSON Schema."""
    schema = _load_schema(paths.envelope_schema_path())
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    if errors:
        first = errors[0]
        raise InvalidPayloadError(
            f"Envelope validation failed: {first.message}",
            {"path": ".".join(str(p) for p in first.path), "cause": first.message},
        )


def validate_document_contract(data: Mapping[str, Any], document_contract: str) -> None:
    """Validate the ``document`` section against the referenced contract schema."""
    schema_path = _schema_for_document_contract(document_contract)
    schema = _load_schema(schema_path)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    if errors:
        first = errors[0]
        raise InvalidPayloadError(
            f"Document contract validation failed: {first.message}",
            {
                "document_contract": document_contract,
                "path": ".".join(str(p) for p in first.path),
                "cause": first.message,
            },
        )


def parse_envelope(raw: str | bytes) -> Envelope:
    """Parse raw JSON text and run the full Phase-1 validation pipeline."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InvalidPayloadError(
            f"Payload is not valid JSON: {exc}",
            {"line": exc.lineno, "column": exc.colno, "cause": exc.msg},
        ) from exc

    if not isinstance(data, Mapping):
        raise InvalidPayloadError(
            f"Payload root must be a JSON object, got {type(data).__name__}",
            {"expected": "object"},
        )

    validate_envelope_structure(data)
    _validate_engine_contract(data["engine_contract_version"])
    validate_document_contract(data["document"], data["document_contract"])
    return Envelope(data)
