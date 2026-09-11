"""Phase 5.4 DoD — bubble-grid rectification, measured against the real Phase 0.7
corpus (CLAUDE.md rule 9). See docs/phases/phase-5.md.
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.omr.alignment import VersionGeometry, align_page
from app.omr.crop import bubble_crop_boxes, crop_mean_intensity
from app.sheet_template import bubble_centres, load_template

TEMPLATE = load_template()
CORPUS_ROOT = Path(__file__).resolve().parent.parent / "corpus"
_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _corpus_cases() -> list[tuple[Path, dict, dict]]:
    images_dir, labels_dir, source_dir = CORPUS_ROOT / "images", CORPUS_ROOT / "labels", CORPUS_ROOT / "_source"
    if not images_dir.is_dir():
        return []
    sources = {}
    for meta_path in source_dir.glob("*.meta.json"):
        meta = json.loads(meta_path.read_text())
        sources[meta["sheet_token"]] = meta
    cases = []
    for image_path in sorted(images_dir.glob("*.jpg")):
        label_path = labels_dir / f"{image_path.stem}.json"
        if not label_path.is_file():
            continue
        label = json.loads(label_path.read_text())
        meta = sources.get(label["sheet_token"])
        if meta is not None:
            cases.append((image_path, label, meta))
    return cases


CORPUS_CASES = _corpus_cases()
_VERSION_BY_TOKEN = {
    meta["sheet_token"]: VersionGeometry(num_questions=meta["questions"], n_options=meta["options"])
    for _, _, meta in CORPUS_CASES
}


def _corpus_version_lookup(qr_text: str) -> VersionGeometry | None:
    return _VERSION_BY_TOKEN.get(qr_text)


# --- pure geometry -----------------------------------------------------------


def test_bubble_crop_boxes_cover_every_question_and_option():
    identity_h = np.eye(3)  # canonical-mm -> canonical-mm: boxes should equal the mm footprint
    boxes = bubble_crop_boxes(identity_h, TEMPLATE, num_questions=40, n_options=4)
    assert set(boxes.keys()) == set(range(1, 41))
    for q_boxes in boxes.values():
        assert len(q_boxes) == 4
        assert [b.option_index for b in q_boxes] == [0, 1, 2, 3]
        for b in q_boxes:
            assert b.width > 0 and b.height > 0
            # with H=identity, box size is exactly bubble_diameter + 2*margin (mm == px here)
            expected = TEMPLATE.geometry.grid.bubble_diameter_mm + 2 * 0.5
            assert b.width == pytest.approx(expected, abs=1e-6)
            assert b.height == pytest.approx(expected, abs=1e-6)


def test_bubble_crop_boxes_are_centred_on_bubble_centres():
    identity_h = np.eye(3)
    boxes = bubble_crop_boxes(identity_h, TEMPLATE, num_questions=20, n_options=4)
    centres = bubble_centres(TEMPLATE, 20, 4)
    for q, q_boxes in boxes.items():
        for option_index, box in enumerate(q_boxes):
            expected_cx, expected_cy = centres[q][option_index]
            cx, cy = box.center()
            assert cx == pytest.approx(expected_cx, abs=1e-6)
            assert cy == pytest.approx(expected_cy, abs=1e-6)


def test_crop_mean_intensity_returns_none_outside_image_bounds():
    from app.omr.crop import BubbleCropBox

    gray = np.full((100, 100), 200, dtype=np.uint8)
    inside = BubbleCropBox(question=1, option_index=0, x0=10, y0=10, x1=20, y1=20)
    assert crop_mean_intensity(gray, inside) == pytest.approx(200.0)
    outside = BubbleCropBox(question=1, option_index=0, x0=90, y0=90, x1=110, y1=110)
    assert crop_mean_intensity(gray, outside) is None


# --- real corpus DoD (rule 9): crop boxes actually land on the real ink -----


@pytest.mark.skipif(not CORPUS_CASES, reason="corpus/images has no labeled real captures")
@pytest.mark.parametrize("image_path,label,meta", CORPUS_CASES, ids=[c[0].stem for c in CORPUS_CASES])
def test_crop_boxes_stay_within_image_bounds_on_real_corpus_capture(image_path, label, meta):
    image = cv2.imread(str(image_path))
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    alignment = align_page(image, TEMPLATE, version_lookup=_corpus_version_lookup)
    boxes = bubble_crop_boxes(alignment.H, TEMPLATE, alignment.num_questions, alignment.n_options)

    total = out_of_bounds = 0
    for q_boxes in boxes.values():
        for box in q_boxes:
            total += 1
            if crop_mean_intensity(gray, box) is None:
                out_of_bounds += 1
    assert total == meta["questions"] * meta["options"]
    assert out_of_bounds == 0, f"{out_of_bounds}/{total} bubble crop boxes fell outside the image"


def test_marked_bubbles_are_darker_than_unmarked_bubbles_across_the_corpus():
    """The real accuracy signal for 5.4: if crop boxes are correctly placed, a
    bubble the label says was filled in pen must show up darker than the other
    (unmarked) options in the same question -- ink vs. blank paper is a large,
    unambiguous contrast. This does NOT depend on marked_options being 100%
    correct (it's AI-transcribed, flagged unverified in each label) -- a handful
    of mislabeled bubbles can't move an aggregate over hundreds of real crops
    without the crop boxes themselves being wrong.
    """
    if not CORPUS_CASES:
        pytest.skip("corpus/images has no labeled real captures")

    marked_vals: list[float] = []
    unmarked_vals: list[float] = []
    per_question_pass = per_question_total = 0

    for image_path, label, _meta in CORPUS_CASES:
        image = cv2.imread(str(image_path))
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        alignment = align_page(image, TEMPLATE, version_lookup=_corpus_version_lookup)
        boxes = bubble_crop_boxes(alignment.H, TEMPLATE, alignment.num_questions, alignment.n_options)

        for q_str, marked_letters in label["marked_options"].items():
            q = int(q_str)
            q_boxes = boxes[q]
            intensities = [crop_mean_intensity(gray, b) for b in q_boxes]
            marked_idx = {_LETTERS.index(letter) for letter in marked_letters}
            m_vals = [intensities[i] for i in marked_idx if intensities[i] is not None]
            u_vals = [
                intensities[i] for i in range(len(intensities)) if i not in marked_idx and intensities[i] is not None
            ]
            marked_vals.extend(m_vals)
            unmarked_vals.extend(u_vals)
            if m_vals and u_vals:
                per_question_total += 1
                if np.mean(m_vals) < np.mean(u_vals) - 20:
                    per_question_pass += 1

    assert len(marked_vals) > 100 and len(unmarked_vals) > 100  # sanity: corpus actually exercised
    marked_mean, unmarked_mean = np.mean(marked_vals), np.mean(unmarked_vals)
    assert marked_mean < unmarked_mean - 30, (
        f"marked bubbles ({marked_mean:.1f}) should be noticeably darker than "
        f"unmarked ({unmarked_mean:.1f}) if crop boxes are correctly placed"
    )
    pass_rate = per_question_pass / per_question_total
    assert pass_rate >= 0.90, f"marked<unmarked separation held for only {pass_rate:.0%} of questions"
