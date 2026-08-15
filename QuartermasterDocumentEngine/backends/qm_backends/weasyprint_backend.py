"""WeasyPrint baseline backend (HTML→PDF), fully offline.

Renders the template entrypoint (a Jinja2 HTML document) with the document
payload and converts the resulting HTML to PDF with WeasyPrint. No network
assets are fetched: CSS ``@page`` and inline styles keep the run offline.

Phase 2 (T4) adds a hard requirement: the engine's bundled fonts
(``qm_engine.fonts``) must be present and SHA-256 verified before
rendering. WeasyPrint is then configured with a ``FontConfiguration``
and an inline ``@font-face`` stylesheet so the host system fonts are
not used as a silent fallback (TZ-PHASE2-BACKEND-SPIKE §12).

Phase 2 (T5) materialises envelope assets into a per-render temporary
directory and passes that directory as ``base_url`` to WeasyPrint so
``<img src="qr.png">`` style references in the template resolve to the
decoded payload. The ``__assets__`` key in the normalized document is
stripped before the dict is handed to Jinja2.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from qm_engine import assets as engine_assets
from qm_engine import fonts as engine_fonts
from qm_engine.errors import (
    BackendNotAvailableError,
    RenderFailedError,
)
from qm_engine.registry import TemplatePackage

from .base import RenderResult

# Reserved key used by ``engine/qm_engine/render.py`` to thread assets
# into the backend without polluting the Jinja2 context.
_ASSETS_KEY = "__assets__"


def _build_font_face_css(fonts_root: Path) -> str:
    """Build an inline ``@font-face`` stylesheet pinned to the bundled fonts.

    All four variants are declared so the renderer can resolve normal,
    bold, italic and bold-italic faces without consulting system fonts.
    """
    regular = (fonts_root / "DejaVuSans.ttf").as_uri()
    bold = (fonts_root / "DejaVuSans-Bold.ttf").as_uri()
    oblique = (fonts_root / "DejaVuSans-Oblique.ttf").as_uri()
    bold_oblique = (fonts_root / "DejaVuSans-BoldOblique.ttf").as_uri()
    return (
        "@font-face {\n"
        f"  font-family: 'DejaVu Sans'; font-weight: normal; font-style: normal;\n"
        f"  src: url('{regular}');\n"
        "}\n"
        "@font-face {\n"
        f"  font-family: 'DejaVu Sans'; font-weight: bold; font-style: normal;\n"
        f"  src: url('{bold}');\n"
        "}\n"
        "@font-face {\n"
        f"  font-family: 'DejaVu Sans'; font-weight: normal; font-style: italic;\n"
        f"  src: url('{oblique}');\n"
        "}\n"
        "@font-face {\n"
        f"  font-family: 'DejaVu Sans'; font-weight: bold; font-style: italic;\n"
        f"  src: url('{bold_oblique}');\n"
        "}\n"
    )


class WeasyPrintBackend:
    """Baseline backend producing PDF via WeasyPrint."""

    name = "weasyprint"

    def available(self) -> bool:
        try:
            import weasyprint  # noqa: F401
        except ImportError:  # pragma: no cover - environment dependent
            return False
        return True

    def render(
        self,
        normalized_document: dict[str, Any],
        template_package: TemplatePackage,
        output_format: str,
        render_options: dict[str, Any],
    ) -> RenderResult:
        if output_format != "pdf":
            from qm_engine.errors import UnsupportedOutputFormatError

            raise UnsupportedOutputFormatError(
                f"Backend '{self.name}' supports only 'pdf', got '{output_format}'",
                {"backend": self.name, "output_format": output_format},
            )

        if not self.available():
            raise BackendNotAvailableError(
                "WeasyPrint backend is not available: the 'weasyprint' package is not installed",
                {"backend": self.name},
            )

        try:
            import weasyprint
        except ImportError as exc:  # pragma: no cover - available() guards this
            raise BackendNotAvailableError(
                "WeasyPrint backend is not available", {"backend": self.name}
            ) from exc

        # Phase 2 T4: bundled fonts must be present and SHA-256 verified
        # before any render. This raises FontNotAvailableError (exit 4)
        # if the bundle is incomplete or has been corrupted. No system
        # fallback is permitted (TZ-PHASE2-BACKEND-SPIKE §12).
        engine_fonts.ensure_bundled_fonts()

        # Phase 2 T5: materialise envelope assets into a temp directory
        # and pass it as WeasyPrint's ``base_url``. The internal
        # ``__assets__`` key is removed from the Jinja2 context so the
        # template only sees the public envelope fields.
        assets = normalized_document.pop(_ASSETS_KEY, {}) or {}
        template_context = dict(normalized_document)

        warnings: list[str] = []
        try:
            from weasyprint import CSS
            from weasyprint.text.fonts import FontConfiguration
        except ImportError as exc:
            raise BackendNotAvailableError(
                "WeasyPrint backend is missing required WeasyPrint Python API",
                {"backend": self.name, "missing": "weasyprint.CSS or weasyprint.text.fonts"},
            ) from exc

        font_css = _build_font_face_css(engine_fonts.fonts_dir())
        font_config = FontConfiguration()
        try:
            with tempfile.TemporaryDirectory(prefix="qm-assets-") as tmp:
                tmp_path = Path(tmp)
                engine_assets.materialise_assets(assets, tmp_path)
                rendered_html = self._render_html(template_context, template_package)
                html = weasyprint.HTML(
                    string=rendered_html,
                    base_url=str(tmp_path),
                )
                pdf_bytes = html.write_pdf(
                    stylesheets=[CSS(string=font_css, font_config=font_config)],
                    font_config=font_config,
                )
        except Exception as exc:  # noqa: BLE001 - surface any render failure
            raise RenderFailedError(
                "WeasyPrint render failed",
                {"backend": self.name, "cause": str(exc), "template": str(template_package.root)},
            ) from exc

        page_count = self._count_pages(pdf_bytes)
        return RenderResult(
            data=pdf_bytes,
            format="pdf",
            page_count=page_count,
            warnings=warnings,
        )

    def _render_html(self, document: dict[str, Any], template_package: TemplatePackage) -> str:
        loader = FileSystemLoader(str(template_package.root))
        env = Environment(
            loader=loader,
            autoescape=select_autoescape(
                enabled_extensions=("html",),
                default_for_string=True,
            ),
        )
        template = env.get_template(str(template_package.manifest["entrypoint"]))
        return template.render(document)

    @staticmethod
    def _count_pages(pdf_bytes: bytes) -> int | None:
        """Best-effort page count using pypdf when available."""
        try:
            from io import BytesIO

            from pypdf import PdfReader

            with BytesIO(pdf_bytes) as stream:
                return len(PdfReader(stream).pages)
        except Exception:  # noqa: BLE001 - non-fatal metadata
            return None
