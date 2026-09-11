"""Validate the Phase 0 real-capture corpus (REBUILD_SPEC §5 Phase 0, §6 Q10/Q18).

Checks, for `corpus/` (or a given root):
  * every image has a parseable label and every label points at a real image;
  * each label's fields, enums, `sheet_token`, and `marked_options` are valid for the
    referenced source sheet;
  * optional `fiducial_px` (Phase 5 alignment gold data) is 4 in-bounds points;
  * aggregate threshold: >=30 phone photos.

Note (2026-09-11, user decision): the copier_scan / photocopied / upside_down
thresholds from REBUILD_SPEC §6 Q10/Q18 are relaxed to 0 here — the user's
deployment never uses a copier/scanner or photocopied/upside-down sheets, so
those capture modes aren't required in the corpus. REBUILD_SPEC.md itself is
left unchanged (by explicit user choice) — this script is the actual gate.
R5.2's "reliably return a clean failure on near-180° orientation" behavior is
still in scope for the Phase 5 aligner; only the corpus *testing* requirement
for it was dropped. See docs/PROGRESS.md 2026-09-11 entry for the full decision.

Exit 0 = corpus complete. Non-zero = something missing (each reason is printed).
This is the standing gate for subtask 0.7.

Usage:
    python scripts/check_corpus.py                # validates ./corpus
    python scripts/check_corpus.py path/to/corpus
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}
CAPTURE_TYPES = {"phone_photo", "copier_scan"}
ORIENTATIONS = {"upright", "upside_down", "reversed"}
REVERSED_ORIENTATIONS = {"upside_down", "reversed"}
REQUIRED_KEYS = {
    "image",
    "capture_type",
    "photocopy_generations",
    "orientation",
    "sheet_token",
    "lighting",
    "marked_options",
    "notes",
}
OPTIONAL_KEYS = {"fiducial_px"}


@dataclass(frozen=True)
class Thresholds:
    min_phone_photo: int = 30
    min_copier_scan: int = 0
    min_photocopied: int = 0
    min_reversed: int = 0


DEFAULT_THRESHOLDS = Thresholds()


@dataclass
class CorpusReport:
    errors: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors


def load_sources(source_dir: Path) -> dict[str, dict]:
    sources: dict[str, dict] = {}
    for meta_path in sorted(source_dir.glob("*.meta.json")):
        meta = json.loads(meta_path.read_text())
        sources[meta["sheet_token"]] = meta
    return sources


def _letters(n: int) -> set[str]:
    return {chr(ord("A") + i) for i in range(n)}


def validate_label(
    label: object,
    *,
    label_name: str,
    sources: dict[str, dict],
    image_size: tuple[int, int] | None = None,
) -> list[str]:
    """Return a list of human-readable problems with one label (empty = valid)."""
    p = f"{label_name}:"
    if not isinstance(label, dict):
        return [f"{p} label is not a JSON object"]

    errors: list[str] = []
    missing = REQUIRED_KEYS - label.keys()
    if missing:
        errors.append(f"{p} missing keys {sorted(missing)}")
    unknown = label.keys() - REQUIRED_KEYS - OPTIONAL_KEYS
    if unknown:
        errors.append(f"{p} unknown keys {sorted(unknown)}")

    if label.get("capture_type") not in CAPTURE_TYPES:
        errors.append(f"{p} capture_type must be one of {sorted(CAPTURE_TYPES)}")
    if label.get("orientation") not in ORIENTATIONS:
        errors.append(f"{p} orientation must be one of {sorted(ORIENTATIONS)}")

    gens = label.get("photocopy_generations")
    if not isinstance(gens, int) or isinstance(gens, bool) or not 0 <= gens <= 3:
        errors.append(f"{p} photocopy_generations must be an int 0..3")

    for str_key in ("lighting", "notes"):
        if not isinstance(label.get(str_key), str):
            errors.append(f"{p} {str_key} must be a string")

    token = label.get("sheet_token")
    meta = sources.get(token) if isinstance(token, str) else None
    if meta is None:
        errors.append(f"{p} sheet_token {token!r} does not resolve to a source sheet")

    marked = label.get("marked_options")
    if not isinstance(marked, dict):
        errors.append(f"{p} marked_options must be an object mapping question -> [letters]")
    elif meta is not None:
        n_q, n_o = meta["questions"], meta["options"]
        allowed = _letters(n_o)
        for q_key, opts in marked.items():
            try:
                q_num = int(q_key)
            except (TypeError, ValueError):
                errors.append(f"{p} marked_options key {q_key!r} is not an integer")
                continue
            if not 1 <= q_num <= n_q:
                errors.append(f"{p} marked_options question {q_num} out of range 1..{n_q}")
            if not isinstance(opts, list):
                errors.append(f"{p} marked_options[{q_key}] must be a list")
                continue
            if len(opts) != len(set(opts)):
                errors.append(f"{p} marked_options[{q_key}] has duplicate letters")
            bad = [o for o in opts if o not in allowed]
            if bad:
                errors.append(f"{p} marked_options[{q_key}] letters {bad} outside A..{chr(ord('A') + n_o - 1)}")

    fid = label.get("fiducial_px")
    if fid is not None:
        if not isinstance(fid, list) or len(fid) != 4:
            errors.append(f"{p} fiducial_px must be a list of 4 [x, y] points")
        else:
            for i, pt in enumerate(fid):
                if not (isinstance(pt, list) and len(pt) == 2 and all(isinstance(v, (int, float)) for v in pt)):
                    errors.append(f"{p} fiducial_px[{i}] must be [x, y] numbers")
                elif image_size is not None:
                    w, h = image_size
                    x, y = pt
                    if not (0 <= x <= w and 0 <= y <= h):
                        errors.append(f"{p} fiducial_px[{i}] = {pt} outside image bounds {w}x{h}")

    return errors


def validate_corpus(root: Path, *, thresholds: Thresholds = DEFAULT_THRESHOLDS) -> CorpusReport:
    root = Path(root)
    images_dir, labels_dir, source_dir = root / "images", root / "labels", root / "_source"
    report = CorpusReport()

    sources = load_sources(source_dir) if source_dir.is_dir() else {}
    if not sources:
        report.errors.append(f"no source sheet metas found in {source_dir}")

    images = {
        p.name: p
        for p in (images_dir.iterdir() if images_dir.is_dir() else [])
        if p.suffix.lower() in IMAGE_EXTS
    }
    label_paths = {p.stem: p for p in (labels_dir.glob("*.json") if labels_dir.is_dir() else [])}

    for stem in sorted({Path(name).stem for name in images} - label_paths.keys()):
        report.errors.append(f"image {stem}.* has no label file labels/{stem}.json")

    counts = {"phone_photo": 0, "copier_scan": 0, "photocopied": 0, "reversed": 0, "labels": 0}

    for _stem, path in sorted(label_paths.items()):
        try:
            label = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            report.errors.append(f"{path.name}: invalid JSON ({exc})")
            continue

        counts["labels"] += 1
        image_name = label.get("image") if isinstance(label, dict) else None
        image_path = images.get(image_name) if isinstance(image_name, str) else None
        if image_path is None:
            report.errors.append(f"{path.name}: image {image_name!r} not found in {images_dir}")

        image_size = None
        if image_path is not None and label.get("fiducial_px") is not None:
            try:
                from PIL import Image

                with Image.open(image_path) as im:
                    image_size = im.size
            except Exception as exc:  # noqa: BLE001 - report, don't crash the whole run
                report.errors.append(f"{path.name}: cannot read image size for fiducial check ({exc})")

        report.errors.extend(
            validate_label(label, label_name=path.name, sources=sources, image_size=image_size)
        )

        if isinstance(label, dict):
            if label.get("capture_type") in counts:
                counts[label["capture_type"]] += 1
            if isinstance(label.get("photocopy_generations"), int) and label["photocopy_generations"] >= 1:
                counts["photocopied"] += 1
            if label.get("orientation") in REVERSED_ORIENTATIONS:
                counts["reversed"] += 1

    report.counts = counts
    checks = [
        ("phone_photo", counts["phone_photo"], thresholds.min_phone_photo),
        ("copier_scan", counts["copier_scan"], thresholds.min_copier_scan),
        ("photocopied (>=1 generation)", counts["photocopied"], thresholds.min_photocopied),
        ("upside_down/reversed", counts["reversed"], thresholds.min_reversed),
    ]
    for name, have, need in checks:
        if have < need:
            report.errors.append(f"threshold not met: {name} has {have}, need >= {need}")

    return report


def _print_report(report: CorpusReport, thresholds: Thresholds) -> None:
    c = report.counts
    print("corpus summary")
    print(f"  labels               {c.get('labels', 0)}")
    print(f"  phone_photo          {c.get('phone_photo', 0):>4}  (need >= {thresholds.min_phone_photo})")
    print(f"  copier_scan          {c.get('copier_scan', 0):>4}  (need >= {thresholds.min_copier_scan})")
    print(f"  photocopied >=1 gen  {c.get('photocopied', 0):>4}  (need >= {thresholds.min_photocopied})")
    print(f"  upside_down/reversed {c.get('reversed', 0):>4}  (need >= {thresholds.min_reversed})")
    if report.errors:
        print(f"\n{len(report.errors)} problem(s):")
        for e in report.errors:
            print(f"  - {e}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("root", nargs="?", default="corpus", help="corpus root (default: ./corpus)")
    args = ap.parse_args()
    thresholds = DEFAULT_THRESHOLDS
    report = validate_corpus(Path(args.root), thresholds=thresholds)
    _print_report(report, thresholds)
    if report.ok:
        print("\nOK: corpus complete.")
        raise SystemExit(0)
    raise SystemExit(1)


if __name__ == "__main__":
    main()
