"""Bundle path resolution.

The engine is delivered as a language-agnostic bundle (ADR-0001 D11) that
contains ``contracts/``, ``templates/`` and ``fonts/`` next to the runnable
engine. In the source tree those directories live at the repository root.
Locating the bundle root lets the CLI read the shipped schemas and find the
default template directory without any network or database access.
"""

from __future__ import annotations

import os
from pathlib import Path

# The package lives at <bundle>/engine/qm_engine/, so the bundle root is three
# levels up from this module.
_BUNDLE_ROOT = Path(__file__).resolve().parents[2]

ENGINE_VERSION = "0.1.0"

# Engine contract versions supported by this engine. A list (not a single
# string) because the engine may understand several engine_contract_version
# values at once (SPEC v2 §6; TZ-PHASE1-CLI-SKELETON section "CLI contract").
ENGINE_CONTRACT_VERSIONS = ["1.0.0"]

# The default engine contract version used when a payload does not pin one.
ENGINE_CONTRACT_VERSION = ENGINE_CONTRACT_VERSIONS[0]

# Default template directory inside the bundle (TZ: `<bundle>/templates`).
DEFAULT_TEMPLATES_DIR = _BUNDLE_ROOT / "templates"

# Envelope schema shipped in the bundle.
ENVELOPE_RESOURCE = "envelope/v1/envelope.schema.json"


def bundle_root() -> Path:
    """Return the bundle root directory containing contracts/, templates/."""
    return _BUNDLE_ROOT


def contracts_dir() -> Path:
    return _BUNDLE_ROOT / "contracts"


def envelope_schema_path() -> Path:
    return contracts_dir() / ENVELOPE_RESOURCE


def fonts_dir() -> Path:
    """Return the bundled ``fonts/`` directory under the bundle root.

    Phase 2 (T4) ships DejaVu Sans Regular/Bold/Oblique/BoldOblique plus a
    ``manifest.json`` and a ``LICENSE`` here. The directory is read-only
    data, distributed with the engine so the renderer is not dependent on
    the host system fonts (ADR-0001 D9).
    """
    return _BUNDLE_ROOT / "fonts"


def templates_dir_from_env() -> Path | None:
    """Resolve ``QM_TEMPLATES_DIR`` if set, else ``None``."""
    raw = os.environ.get("QM_TEMPLATES_DIR")
    if raw:
        return Path(raw).resolve()
    return None


def default_templates_dir() -> Path:
    """Resolve the effective default templates dir (env override wins)."""
    return templates_dir_from_env() or DEFAULT_TEMPLATES_DIR
