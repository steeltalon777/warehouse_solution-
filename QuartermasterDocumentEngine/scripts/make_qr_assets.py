#!/usr/bin/env python3
"""Produce a JSON snippet of base64-encoded assets (TZ §8 T5).

Producer-side helper. Generates QR and Code 128 barcode PNGs with
``segno`` and ``python-barcode`` and writes a JSON file shaped like the
``envelope.assets`` field:

    {
      "qr":      {"mime": "image/png", "data_base64": "..."},
      "barcode": {"mime": "image/png", "data_base64": "..."}
    }

The script is intentionally offline at runtime once dependencies are
installed. Run:

    python scripts/make_qr_assets.py \\
        --qr "WB-001" \\
        --code128 "1234567890123" \\
        --out assets.json
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path

from qm_engine.assets import make_code128_png, make_qr_png
from qm_engine.errors import AssetNotAvailableError


def _png_asset(png: bytes) -> dict[str, str]:
    return {"mime": "image/png", "data_base64": base64.b64encode(png).decode("ascii")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--qr", default=None, help="Text payload for the QR code (optional).")
    parser.add_argument(
        "--code128", default=None, help="Text payload for the Code 128 barcode (optional)."
    )
    parser.add_argument("--out", type=Path, default=Path("assets.json"), help="Output JSON path.")
    args = parser.parse_args(argv)

    if args.qr is None and args.code128 is None:
        print("Provide at least one of --qr or --code128.", file=sys.stderr)
        return 2

    assets: dict[str, dict[str, str]] = {}

    if args.qr is not None:
        try:
            png = make_qr_png(args.qr)
        except AssetNotAvailableError as exc:
            print(f"QR generation failed: {exc}", file=sys.stderr)
            return 1
        assets["qr"] = _png_asset(png)

    if args.code128 is not None:
        try:
            png = make_code128_png(args.code128)
        except AssetNotAvailableError as exc:
            print(f"Barcode generation failed: {exc}", file=sys.stderr)
            return 1
        assets["barcode"] = _png_asset(png)

    args.out.write_text(json.dumps(assets, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
