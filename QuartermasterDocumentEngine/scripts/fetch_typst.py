#!/usr/bin/env python3
"""Fetch pinned Typst binary for Phase 2 spike (TZ §11.1).

Idempotent: if the binary is already extracted at the target path with the
pinned SHA-256, the script exits 0 without re-downloading.

Exit codes:
    0 — success (already extracted or freshly downloaded and verified).
    1 — network error (download failed).
    2 — SHA-256 mismatch (binary or archive).
    3 — unsupported platform (Windows in this script).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tarfile
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PIN_PATH = REPO / "spike" / "typst-pin.json"

EXIT_OK = 0
EXIT_NETWORK = 1
EXIT_HASH_MISMATCH = 2
EXIT_UNSUPPORTED = 3


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest().lower()


def _load_pin() -> dict[str, object]:
    with PIN_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def _download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "qm-fetch-typst/1.0"})
    with urllib.request.urlopen(req, timeout=60) as response, dest.open("wb") as out:
        shutil.copyfileobj(response, out)


def _extract_tar_xz(archive: Path, target_dir: Path) -> None:
    with tarfile.open(archive, "r:xz") as tar:
        # Filter to plain files only — no path components escape the target
        # because we trust the upstream tar archive but defend against
        # `../` entries regardless.
        members: list[tarfile.TarInfo] = []
        for member in tar.getmembers():
            member_path = (target_dir / member.name).resolve()
            if not str(member_path).startswith(str(target_dir.resolve())):
                raise ValueError(f"Refusing to extract path outside target: {member.name}")
            members.append(member)
        tar.extractall(target_dir, members=members, filter="data")


def _linux_target(pin_version: str, target_dir: Path) -> Path:
    return target_dir / f"typst-{pin_version}"


def _linux_subdir(pin_version: str) -> str:
    return "typst-x86_64-unknown-linux-musl"


def fetch(target_dir: Path, version: str | None = None) -> int:
    pin = _load_pin()
    pin_version = str(pin["version"])
    if version and version != pin_version:
        print(
            f"Requested version {version} does not match pin {pin_version}; aborting.",
            file=sys.stderr,
        )
        return EXIT_UNSUPPORTED

    if os.name == "nt":
        target = target_dir / f"typst-{pin_version}"
        print(
            "Windows: not supported by this script; "
            f"copy typst.exe manually to {target / 'typst-x86_64-pc-windows-msvc' / 'typst.exe'} "
            "and set QM_TYPST_BINARY.",
            file=sys.stderr,
        )
        return EXIT_UNSUPPORTED

    if os.name != "posix":
        print(f"Unsupported platform: {os.name}", file=sys.stderr)
        return EXIT_UNSUPPORTED

    binaries = pin["binaries"]
    if not isinstance(binaries, dict):
        print("Invalid pin file: 'binaries' must be a mapping", file=sys.stderr)
        return EXIT_UNSUPPORTED
    linux_entry = binaries.get("linux-x64")
    if not isinstance(linux_entry, dict):
        print("Invalid pin file: 'linux-x64' entry missing", file=sys.stderr)
        return EXIT_UNSUPPORTED

    url = str(linux_entry["url"])
    archive_sha = str(linux_entry["archive_sha256"]).lower()
    binary_path_in_archive = str(linux_entry["binary_path_in_archive"])
    binary_sha = str(linux_entry["binary_sha256"]).lower()

    final_dir = _linux_target(pin_version, target_dir)
    final_binary = final_dir / binary_path_in_archive
    final_binary = final_binary.resolve()

    if final_binary.is_file() and _sha256_of(final_binary) == binary_sha:
        print(f"Already extracted: {final_binary}")
        return EXIT_OK

    target_dir.mkdir(parents=True, exist_ok=True)
    archive_path = target_dir / f"typst-{pin_version}.tar.xz"
    if not archive_path.is_file() or _sha256_of(archive_path) != archive_sha:
        print(f"Downloading {url} -> {archive_path}")
        try:
            _download(url, archive_path)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(f"Network error: {exc}", file=sys.stderr)
            return EXIT_NETWORK
        if _sha256_of(archive_path) != archive_sha:
            print(
                f"Archive SHA-256 mismatch: expected {archive_sha}, got {_sha256_of(archive_path)}",
                file=sys.stderr,
            )
            return EXIT_HASH_MISMATCH

    print(f"Extracting {archive_path} -> {final_dir}")
    final_dir.mkdir(parents=True, exist_ok=True)
    _extract_tar_xz(archive_path, final_dir)

    if not final_binary.is_file():
        print(f"Expected binary not found at {final_binary}", file=sys.stderr)
        return EXIT_HASH_MISMATCH
    if _sha256_of(final_binary) != binary_sha:
        print(
            f"Binary SHA-256 mismatch: expected {binary_sha}, got {_sha256_of(final_binary)}",
            file=sys.stderr,
        )
        return EXIT_HASH_MISMATCH

    print(f"Verified: {final_binary}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--version",
        default=None,
        help="Typst version to fetch (default: read from spike/typst-pin.json).",
    )
    parser.add_argument(
        "--target-dir",
        type=Path,
        default=REPO / ".spike",
        help="Directory where typst-<version>/ will be created (default: <repo>/.spike).",
    )
    args = parser.parse_args(argv)
    return fetch(args.target_dir, args.version)


if __name__ == "__main__":
    sys.exit(main())
