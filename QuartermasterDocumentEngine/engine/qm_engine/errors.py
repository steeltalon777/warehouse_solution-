"""Machine-readable error model for the Quartermaster Document Engine.

Error codes are the public contract (ADR-0001 D12, SPEC v2 §21).
Each error maps to a CLI exit code class (see TZ-PHASE1-CLI-SKELETON).
"""

from __future__ import annotations

from typing import Any

# Exit code classes (TZ-PHASE1-CLI-SKELETON, section "Exit codes").
EXIT_SUCCESS = 0
EXIT_VALIDATION = 2
EXIT_TEMPLATE = 3
EXIT_RESOURCE = 4
EXIT_RENDER = 5

# Validation / payload / contract errors (exit 2).
INVALID_PAYLOAD = "INVALID_PAYLOAD"
UNSUPPORTED_ENGINE_CONTRACT = "UNSUPPORTED_ENGINE_CONTRACT"
UNSUPPORTED_DOCUMENT_CONTRACT = "UNSUPPORTED_DOCUMENT_CONTRACT"
UNSUPPORTED_OUTPUT_FORMAT = "UNSUPPORTED_OUTPUT_FORMAT"

# Template errors (exit 3).
TEMPLATE_NOT_INSTALLED = "TEMPLATE_NOT_INSTALLED"
TEMPLATE_VERSION_NOT_INSTALLED = "TEMPLATE_VERSION_NOT_INSTALLED"
TEMPLATE_CONTRACT_MISMATCH = "TEMPLATE_CONTRACT_MISMATCH"

# Resource / backend errors (exit 4).
BACKEND_NOT_AVAILABLE = "BACKEND_NOT_AVAILABLE"
FONT_NOT_AVAILABLE = "FONT_NOT_AVAILABLE"
ASSET_NOT_AVAILABLE = "ASSET_NOT_AVAILABLE"

# Render / internal errors (exit 5).
RENDER_FAILED = "RENDER_FAILED"

_EXIT_CODE_BY_CLASS: dict[str, int] = {
    INVALID_PAYLOAD: EXIT_VALIDATION,
    UNSUPPORTED_ENGINE_CONTRACT: EXIT_VALIDATION,
    UNSUPPORTED_DOCUMENT_CONTRACT: EXIT_VALIDATION,
    UNSUPPORTED_OUTPUT_FORMAT: EXIT_VALIDATION,
    TEMPLATE_NOT_INSTALLED: EXIT_TEMPLATE,
    TEMPLATE_VERSION_NOT_INSTALLED: EXIT_TEMPLATE,
    TEMPLATE_CONTRACT_MISMATCH: EXIT_TEMPLATE,
    BACKEND_NOT_AVAILABLE: EXIT_RESOURCE,
    FONT_NOT_AVAILABLE: EXIT_RESOURCE,
    ASSET_NOT_AVAILABLE: EXIT_RESOURCE,
    RENDER_FAILED: EXIT_RENDER,
}


class EngineError(Exception):
    """Base engine error with a public machine-readable code."""

    code: str = RENDER_FAILED
    exit_code: int = EXIT_RENDER

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Return the public JSON error payload (written to stderr)."""
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


def _make_error_class(code: str, exit_code: int) -> type[EngineError]:
    return type(
        f"{code}Error",
        (EngineError,),
        {"code": code, "exit_code": exit_code},
    )


# Validation class (exit 2).
InvalidPayloadError = _make_error_class(INVALID_PAYLOAD, EXIT_VALIDATION)
UnsupportedEngineContractError = _make_error_class(UNSUPPORTED_ENGINE_CONTRACT, EXIT_VALIDATION)
UnsupportedDocumentContractError = _make_error_class(UNSUPPORTED_DOCUMENT_CONTRACT, EXIT_VALIDATION)
UnsupportedOutputFormatError = _make_error_class(UNSUPPORTED_OUTPUT_FORMAT, EXIT_VALIDATION)

# Template class (exit 3).
TemplateNotInstalledError = _make_error_class(TEMPLATE_NOT_INSTALLED, EXIT_TEMPLATE)
TemplateVersionNotInstalledError = _make_error_class(TEMPLATE_VERSION_NOT_INSTALLED, EXIT_TEMPLATE)
TemplateContractMismatchError = _make_error_class(TEMPLATE_CONTRACT_MISMATCH, EXIT_TEMPLATE)

# Resource class (exit 4).
BackendNotAvailableError = _make_error_class(BACKEND_NOT_AVAILABLE, EXIT_RESOURCE)
FontNotAvailableError = _make_error_class(FONT_NOT_AVAILABLE, EXIT_RESOURCE)
AssetNotAvailableError = _make_error_class(ASSET_NOT_AVAILABLE, EXIT_RESOURCE)

# Render class (exit 5).
RenderFailedError = _make_error_class(RENDER_FAILED, EXIT_RENDER)
