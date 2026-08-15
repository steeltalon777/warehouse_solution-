"""Template registry (SPEC v2 §9, ADR-0001 D6, TZ-PHASE1-CLI-SKELETON).

Registry performs lookup of a template package by ``template_id`` +
``template_version``, reads its ``manifest.yaml`` and runs compatibility checks.
Published versions are immutable; silent fallback to latest is forbidden.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .errors import (
    TemplateContractMismatchError,
    TemplateNotInstalledError,
    TemplateVersionNotInstalledError,
)

MANIFEST_FILENAME = "manifest.yaml"


@dataclass(frozen=True)
class TemplatePackage:
    """A resolved, on-disk immutable template package."""

    root: Path
    manifest: dict[str, Any]

    @property
    def template_id(self) -> str:
        return str(self.manifest["id"])

    @property
    def version(self) -> str:
        return str(self.manifest["version"])

    @property
    def document_contract(self) -> str:
        return str(self.manifest["document_contract"])

    @property
    def backend(self) -> str:
        return str(self.manifest["backend"])

    @property
    def entrypoint(self) -> Path:
        return self.root / str(self.manifest["entrypoint"])

    @property
    def output_formats(self) -> list[str]:
        return list(self.manifest.get("output_formats", []))

    @property
    def locales(self) -> list[str]:
        return list(self.manifest.get("locales", []))


class Registry:
    """Lookup and compatibility checks over a templates root directory."""

    def __init__(self, templates_root: Path) -> None:
        self.templates_root = templates_root

    def _id_dir(self, template_id: str) -> Path:
        return self.templates_root / template_id

    def _package_dir(self, template_id: str, version: str) -> Path:
        return self.templates_root / template_id / version

    @staticmethod
    def _load_manifest(manifest_path: Path) -> dict[str, Any]:
        try:
            with manifest_path.open(encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
        except (OSError, yaml.YAMLError) as exc:
            raise TemplateNotInstalledError(
                f"Unable to read template manifest {manifest_path}: {exc}",
                {"path": str(manifest_path)},
            ) from exc
        if not isinstance(data, dict):
            raise TemplateNotInstalledError(
                f"Template manifest {manifest_path} must be a YAML mapping",
                {"path": str(manifest_path)},
            )
        return data

    def lookup(self, template_id: str, version: str) -> TemplatePackage:
        """Resolve a template package by id+version or raise a typed error."""
        if not self._id_dir(template_id).is_dir():
            raise TemplateNotInstalledError(
                f"Template '{template_id}' is not installed",
                {"template_id": template_id},
            )

        package_dir = self._package_dir(template_id, version)
        if not package_dir.is_dir():
            raise TemplateVersionNotInstalledError(
                f"Template '{template_id}' version '{version}' is not installed",
                {"template_id": template_id, "template_version": version},
            )

        manifest_path = package_dir / MANIFEST_FILENAME
        if not manifest_path.is_file():
            raise TemplateNotInstalledError(
                f"Template package '{template_id}@{version}' has no {MANIFEST_FILENAME}",
                {"template_id": template_id, "template_version": version},
            )

        manifest = self._load_manifest(manifest_path)
        return TemplatePackage(root=package_dir, manifest=manifest)

    def check_contract(self, package: TemplatePackage, document_contract: str) -> None:
        """Verify the template manifest declares the requested document contract."""
        if package.document_contract != document_contract:
            raise TemplateContractMismatchError(
                f"Template '{package.template_id}@{package.version}' declares "
                f"document_contract '{package.document_contract}', but the envelope "
                f"requests '{document_contract}'",
                {
                    "template_id": package.template_id,
                    "template_version": package.version,
                    "manifest_document_contract": package.document_contract,
                    "requested_document_contract": document_contract,
                },
            )

    def list_installed(self) -> list[TemplatePackage]:
        """List all installed template packages (id/version pairs)."""
        packages: list[TemplatePackage] = []
        if not self.templates_root.is_dir():
            return packages
        for id_dir in sorted(self.templates_root.iterdir()):
            if not id_dir.is_dir():
                continue
            for ver_dir in sorted(id_dir.iterdir()):
                manifest_path = ver_dir / MANIFEST_FILENAME
                if manifest_path.is_file():
                    packages.append(
                        TemplatePackage(root=ver_dir, manifest=self._load_manifest(manifest_path))
                    )
        return packages
