"""Scaffold a corpus label file for an image, ready for the user to fill in.

Usage:
    python scripts/new_label.py corpus/images/phone_0001.jpg

Guesses `capture_type` from the filename ("scan"/"copier" -> copier_scan, else
phone_photo), pre-fills `sheet_token` when exactly one source sheet exists, and seeds
`marked_options` with every question mapped to [] (blank). The user edits the rest.
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


def build_template(image_path: Path, corpus_root: Path) -> dict:
    sources = load_sources(corpus_root / "_source")
    name = image_path.name.lower()
    capture_type = "copier_scan" if ("scan" in name or "copier" in name) else "phone_photo"

    token = ""
    marked: dict[str, list[str]] = {}
    if len(sources) == 1:
        meta = next(iter(sources.values()))
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

    label_path.parent.mkdir(parents=True, exist_ok=True)
    label_path.write_text(json.dumps(build_template(image_path, corpus_root), indent=2))
    print(f"wrote {label_path} - now fill in orientation, lighting, and marked_options")


if __name__ == "__main__":
    main()
