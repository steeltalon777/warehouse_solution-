"""Unit tests for the error model (SPEC v2 §21, TZ-PHASE1-CLI-SKELETON)."""

from __future__ import annotations

from qm_engine.errors import (
    EXIT_RENDER,
    EXIT_RESOURCE,
    EXIT_TEMPLATE,
    EXIT_VALIDATION,
    EngineError,
    InvalidPayloadError,
    RenderFailedError,
    TemplateNotInstalledError,
)


def test_error_to_dict_shape() -> None:
    err = InvalidPayloadError("boom", {"path": "document"})
    assert err.to_dict() == {
        "error": {"code": "INVALID_PAYLOAD", "message": "boom", "details": {"path": "document"}}
    }


def test_error_exit_code_mapping() -> None:
    assert InvalidPayloadError("x").exit_code == EXIT_VALIDATION
    assert TemplateNotInstalledError("x").exit_code == EXIT_TEMPLATE
    assert RenderFailedError("x").exit_code == EXIT_RENDER


def test_error_is_engine_error() -> None:
    assert isinstance(InvalidPayloadError("x"), EngineError)


def test_error_message_is_set() -> None:
    err = RenderFailedError("render died")
    assert str(err) == "render died"
    assert err.message == "render died"


def test_exit_resources_constant() -> None:
    # Sanity: resource class constant exists and is 4.
    assert EXIT_RESOURCE == 4


def test_default_details_empty() -> None:
    err = TemplateNotInstalledError("no template")
    assert err.details == {}
