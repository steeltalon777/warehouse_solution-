"""Bundle path resolution.

The engine is delivered as a language-agnostic bundle (ADR-0001 D11) that
contains ``contracts/``, ``templates/`` and ``fonts/`` next to the runnable
engine. In the source tree those directories live at the repository root;
when the engine is installed via ``pip install`` the same resources are
delivered into ``<sys.prefix>/share/quartermaster_document_engine/`` by
``[tool.setuptools.data-files]`` (ADR-0032 D7, TZ-QDE_INTEGRATION_READINESS
§6.5, §9.1). Locating the resolved resource directories lets the CLI read
the shipped schemas, templates and fonts without any network or database
access.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# The package lives at <bundle>/engine/qm_engine/, so the bundle root is three
# levels up from this module.
_BUNDLE_ROOT = Path(__file__).resolve().parents[2]

# Installed share location (TZ §6.5): ``pip install`` delivers templates/,
# fonts/ and contracts/ under ``<sys.prefix>/share/quartermaster_document_engine/``.
_INSTALLED_SHARE_ROOT = Path(sys.prefix) / "share" / "quartermaster_document_engine"

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
    """Resolve the contracts dir (installed share location, then bundle root)."""
    share = _INSTALLED_SHARE_ROOT / "contracts"
    if share.is_dir():
        return share
    return _BUNDLE_ROOT / "contracts"


def envelope_schema_path() -> Path:
    return contracts_dir() / ENVELOPE_RESOURCE


def fonts_dir_from_env() -> Path | None:
    """Resolve ``QM_FONTS_DIR`` if set, else ``None``.

    ``QM_FONTS_DIR`` is the explicit configuration axis for bundled/pinned
    fonts (ADR-0032 D3/D7, TZ §6.5, §7.2): when set it wins over both the
    installed share location and the bundle root.
    """
    raw = os.environ.get("QM_FONTS_DIR")
    if raw:
        return Path(raw).resolve()
    return None


def default_fonts_dir() -> Path:
    """Resolve the effective bundled fonts dir (env override wins).

    Priority: ``QM_FONTS_DIR`` -> installed share location
    (``<sys.prefix>/share/quartermaster_document_engine/fonts``) -> bundle
    root ``fonts/``. A resolved directory that is missing the mandatory
    DejaVu files still fails later in ``ensure_bundled_fonts`` with
    ``FontNotAvailableError`` — there is no silent fallback to system
    fonts (ADR-0001 D9, ADR-0032 D7).
    """
    env = fonts_dir_from_env()
    if env is not None:
        return env
    share = _INSTALLED_SHARE_ROOT / "fonts"
    if share.is_dir():
        return share
    return _BUNDLE_ROOT / "fonts"


def templates_dir_from_env() -> Path | None:
    """Resolve ``QM_TEMPLATES_DIR`` if set, else ``None``."""
    raw = os.environ.get("QM_TEMPLATES_DIR")
    if raw:
        return Path(raw).resolve()
    return None


def default_templates_dir() -> Path:
    """Resolve the effective default templates dir (env override wins).

    Priority: ``QM_TEMPLATES_DIR`` -> installed share location
    (``<sys.prefix>/share/quartermaster_document_engine/templates``) ->
    bundle root ``templates/``.
    """
    env = templates_dir_from_env()
    if env is not None:
        return env
    share = _INSTALLED_SHARE_ROOT / "templates"
    if share.is_dir():
        return share
    return DEFAULT_TEMPLATES_DIR
