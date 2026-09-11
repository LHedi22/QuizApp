"""Phase 0.3 DoD: prove scripts/check_corpus.py's logic on good + bad corpora.

Corpora are built in tmp_path (tiny PNGs + JSON labels) so there are no binary
fixtures to maintain.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from scripts.check_corpus import Thresholds, validate_corpus, validate_label

SOURCE_META = {
    "sheet_token": "tok-test",
    "generator_version": "test",
    "page_size": "A4",
    "page_w_mm": 210.0,
    "page_h_mm": 297.0,
    "questions": 5,
    "options": 4,
    "fiducial_centres_mm": [[15, 15], [195, 15], [15, 282], [195, 282]],
    "bubble_centres_mm": {},
}

FULL_LABEL = {
    "image": "x.png",
    "capture_type": "phone_photo",
    "photocopy_generations": 0,
    "orientation": "upright",
    "sheet_token": "tok-test",
    "lighting": "even indoor",
    "marked_options": {"1": ["B"], "2": ["A", "C"], "3": []},
    "notes": "",
}


def _img(path: Path, size=(40, 60)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, "white").save(path)


def _write(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2))


def _corpus(root: Path) -> Path:
    _write(root / "_source" / "tok-test.meta.json", SOURCE_META)
    return root


# --- validate_label unit checks ------------------------------------------------

@pytest.fixture
def sources():
    return {"tok-test": SOURCE_META}


def test_full_label_is_valid(sources):
    assert validate_label(FULL_LABEL, label_name="x.json", sources=sources) == []


@pytest.mark.parametrize(
    ("mutate", "needle"),
    [
        (lambda d: d.update(capture_type="webcam"), "capture_type must be one of"),
        (lambda d: d.update(orientation="sideways"), "orientation must be one of"),
        (lambda d: d.update(photocopy_generations=9), "photocopy_generations must be an int 0..3"),
        (lambda d: d.update(photocopy_generations=True), "photocopy_generations must be an int 0..3"),
        (lambda d: d.update(sheet_token="nope"), "does not resolve to a source sheet"),
        (lambda d: d.update(marked_options={"1": ["E"]}), "outside A..D"),
        (lambda d: d.update(marked_options={"9": ["A"]}), "out of range 1..5"),
        (lambda d: d.update(marked_options={"1": ["A", "A"]}), "duplicate letters"),
        (lambda d: d.update(lighting=5), "lighting must be a string"),
        (lambda d: d.pop("notes"), "missing keys"),
        (lambda d: d.update(surprise=1), "unknown keys"),
    ],
)
def test_label_defect_is_reported(sources, mutate, needle):
    label = json.loads(json.dumps(FULL_LABEL))
    mutate(label)
    errors = validate_label(label, label_name="x.json", sources=sources)
    assert any(needle in e for e in errors), errors


def test_fiducial_px_out_of_bounds(sources):
    label = json.loads(json.dumps(FULL_LABEL))
    label["fiducial_px"] = [[5, 5], [35, 5], [5, 55], [9999, 9999]]
    errors = validate_label(label, label_name="x.json", sources=sources, image_size=(40, 60))
    assert any("outside image bounds" in e for e in errors), errors


def test_fiducial_px_wrong_count(sources):
    label = json.loads(json.dumps(FULL_LABEL))
    label["fiducial_px"] = [[5, 5], [35, 5]]
    errors = validate_label(label, label_name="x.json", sources=sources)
    assert any("list of 4" in e for e in errors), errors


# --- validate_corpus integration checks --------------------------------------

def test_good_corpus_passes_relaxed_thresholds(tmp_path):
    root = _corpus(tmp_path / "corpus")
    for name, cap, gens, orient in [
        ("phone_a", "phone_photo", 1, "upright"),
        ("phone_b", "phone_photo", 0, "upside_down"),
        ("copier_a", "copier_scan", 2, "reversed"),
    ]:
        _img(root / "images" / f"{name}.png")
        label = json.loads(json.dumps(FULL_LABEL))
        label.update(image=f"{name}.png", capture_type=cap, photocopy_generations=gens, orientation=orient)
        _write(root / "labels" / f"{name}.json", label)

    report = validate_corpus(
        root, thresholds=Thresholds(min_phone_photo=2, min_copier_scan=1, min_photocopied=1, min_reversed=1)
    )
    assert report.ok, report.errors
    assert report.counts["phone_photo"] == 2
    assert report.counts["reversed"] == 2


def test_default_thresholds_flag_a_small_corpus(tmp_path):
    root = _corpus(tmp_path / "corpus")
    _img(root / "images" / "phone_a.png")
    _write(root / "labels" / "phone_a.json", {**FULL_LABEL, "image": "phone_a.png"})

    report = validate_corpus(root)  # default 20/0/0/0
    assert not report.ok
    assert any("phone_photo has 1, need >= 20" in e for e in report.errors)


def test_orphan_image_and_orphan_label_are_reported(tmp_path):
    root = _corpus(tmp_path / "corpus")
    _img(root / "images" / "has_no_label.png")
    _img(root / "images" / "real.png")
    _write(root / "labels" / "points_nowhere.json", {**FULL_LABEL, "image": "ghost.png"})
    _write(root / "labels" / "real.json", {**FULL_LABEL, "image": "real.png"})

    report = validate_corpus(root)
    assert any("has_no_label" in e and "no label" in e for e in report.errors)
    assert any("ghost.png" in e and "not found" in e for e in report.errors)


def test_missing_source_metas_is_an_error(tmp_path):
    root = tmp_path / "corpus"
    (root / "images").mkdir(parents=True)
    (root / "labels").mkdir(parents=True)
    report = validate_corpus(root)
    assert any("no source sheet metas" in e for e in report.errors)


def test_invalid_json_label_is_reported(tmp_path):
    root = _corpus(tmp_path / "corpus")
    _img(root / "images" / "real.png")
    (root / "labels").mkdir(parents=True, exist_ok=True)
    (root / "labels" / "broken.json").write_text("{ not json")
    report = validate_corpus(root)
    assert any("broken.json" in e and "invalid JSON" in e for e in report.errors)
