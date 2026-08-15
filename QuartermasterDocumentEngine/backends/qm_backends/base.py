"""Backend abstraction (SPEC v2 §10, ADR-0001 D7, TZ-PHASE1-CLI-SKELETON).

A backend turns a normalized document + a template package into a render
artifact. Phase 1 ships a single baseline backend: WeasyPrint (HTML→PDF).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from qm_engine.registry import TemplatePackage


@dataclass
class RenderResult:
    """Result of a single render call."""

    data: bytes
    format: str
    page_count: int | None = None
    warnings: list[str] = field(default_factory=list)


@runtime_checkable
class Backend(Protocol):
    """Logical backend interface."""

    name: str

    def available(self) -> bool: ...

    def render(
        self,
        normalized_document: dict[str, Any],
        template_package: TemplatePackage,
        output_format: str,
        render_options: dict[str, Any],
    ) -> RenderResult: ...
