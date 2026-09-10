"""Scaffold a corpus label file for an image, ready for the user to fill in.

Usage:
    python scripts/new_label.py corpus/images/phone_sheet_b_0001.jpg
    python scripts/new_label.py corpus/images/x.jpg --sheet sheet_b_40q_n4

Guesses `capture_type` from the filename ("scan"/"copier" -> copier_scan, else
phone_photo). Resolves the source sheet from `--sheet` (a source `name` or
`sheet_token`), else from a source `name` that appears in the image filename, else
(if there is exactly one source) that one. When resolved, pre-fills `sheet_token`
and seeds `marked_options` with every question mapped to [] (blank). The user edits
orientation / lighting / photocopy_generations / the real marked bubbles.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load_sources(source_dir: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for meta_path in sorted(Path(source_dir).glob("*.meta.json")):
        meta = json.loads(meta_path.read_text())
        out[meta["sheet_token"]] = meta
    return out


def _resolve_source(sources: dict[str, dict], image_name: str, sheet_arg: str | None) -> dict | None:
    """Pick the source sheet for an image: explicit --sheet, else a source `name`
    appearing in the filename, else the sole source if there is only one."""
    if sheet_arg:
        for meta in sources.values():
            if sheet_arg in (meta["sheet_token"], meta.get("name"), meta.get("short_name")):
                return meta
        return None
    lname = image_name.lower()
    for meta in sources.values():
        for key in (meta.get("name"), meta.get("short_name")):
            if key and key.lower() in lname:
                return meta
    return next(iter(sources.values())) if len(sources) == 1 else None


def build_template(image_path: Path, corpus_root: Path, sheet_arg: str | None = None) -> dict:
    sources = load_sources(corpus_root / "_source")
    name = image_path.name.lower()
    capture_type = "copier_scan" if ("scan" in name or "copier" in name) else "phone_photo"

    meta = _resolve_source(sources, image_path.name, sheet_arg)
    token = ""
    marked: dict[str, list[str]] = {}
    if meta is not None:
        token = meta["sheet_token"]
        marked = {str(q): [] for q in range(1, meta["questions"] + 1)}

    return {
        "image": image_path.name,
        "capture_type": capture_type,
        "photocopy_generations": 0,
        "orientation": "upright",
        "sheet_token": token,
        "lighting": "",
        "marked_options": marked,
        "notes": "",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("image", help="path to an image under corpus/images/")
    ap.add_argument("--sheet", help="source sheet name or token (else guessed from filename)")
    ap.add_argument("--force", action="store_true", help="overwrite an existing label")
    args = ap.parse_args()

    image_path = Path(args.image)
    corpus_root = image_path.parent.parent
    label_path = corpus_root / "labels" / f"{image_path.stem}.json"

    if not image_path.exists():
        print(f"FAIL: {image_path} does not exist", file=sys.stderr)
        raise SystemExit(1)
    if label_path.exists() and not args.force:
        print(f"FAIL: {label_path} already exists (use --force)", file=sys.stderr)
        raise SystemExit(1)

    template = build_template(image_path, corpus_root, args.sheet)
    if not template["sheet_token"]:
        print(
            "WARN: could not resolve a source sheet — set `sheet_token` and "
            "`marked_options` by hand, or pass --sheet <name>",
            file=sys.stderr,
        )
    label_path.parent.mkdir(parents=True, exist_ok=True)
    label_path.write_text(json.dumps(template, indent=2))
    print(f"wrote {label_path} - now fill in orientation, lighting, and marked_options")


if __name__ == "__main__":
    main()
