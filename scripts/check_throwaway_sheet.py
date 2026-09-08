"""Verify a throwaway sheet's QR survives rasterization at scan resolution.

Renders the generated PDF to a bitmap (as a scanner/camera would) and decodes the QR
with pyzbar, asserting it matches the token recorded in <stem>.meta.json.

Usage:
    python scripts/check_throwaway_sheet.py corpus/_source/throwaway_v0
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pymupdf
from PIL import Image
from pyzbar.pyzbar import decode as zbar_decode


def decode_qr_from_pdf(pdf_path: Path, dpi: int = 200) -> list[str]:
    doc = pymupdf.open(pdf_path)
    try:
        pix = doc[0].get_pixmap(dpi=dpi)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    finally:
        doc.close()
    return [d.data.decode("utf-8") for d in zbar_decode(img)]


def check(stem: Path, dpi: int = 200) -> str:
    stem = Path(stem)
    meta = json.loads(stem.with_suffix(".meta.json").read_text())
    expected = meta["sheet_token"]
    found = decode_qr_from_pdf(stem.with_suffix(".pdf"), dpi=dpi)
    if expected not in found:
        raise AssertionError(
            f"QR token mismatch: expected {expected!r} in rasterized page, decoded {found!r}"
        )
    return expected


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("stem", help="path stem of a generated sheet (no extension)")
    ap.add_argument("--dpi", type=int, default=200)
    args = ap.parse_args()
    try:
        token = check(Path(args.stem), dpi=args.dpi)
    except (AssertionError, FileNotFoundError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(f"OK: QR decoded from rasterized page, token = {token}")


if __name__ == "__main__":
    main()
