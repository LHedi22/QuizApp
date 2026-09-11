"""Phase 5.2 DoD — perimeter detection front-end, measured against the real Phase
0.7 corpus (CLAUDE.md rule 9: no OMR front-end DoD may be signed off on synthetic
images alone). See docs/phases/phase-5.md.
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.omr.detect import (
    canonical_fiducial_corners_mm,
    canonical_qr_corners_mm,
    detect_fiducials,
    detect_qr,
    detect_stage_a,
)
from app.omr.geometry import AlignmentError, fit_homography_robust
from app.sheet_template import load_template

TEMPLATE = load_template()
CORPUS_ROOT = Path(__file__).resolve().parent.parent / "corpus"

# Provisional Stage-A gate, calibrated against the actual corpus (see
# docs/PROGRESS.md): observed rms 1.3-3.0px / max 1.9-5.4px on 3024x4032 photos
# with all 8/8 points inlying. Generous headroom over that, not a re-derivation
# from first principles — 5.5 owns the formal reliability-budget writeup.
STAGE_A_GATE = {"gate_rms_px": 12.0, "gate_max_px": 25.0, "min_inliers": 6}


def _corpus_cases() -> list[tuple[Path, dict]]:
    images_dir, labels_dir = CORPUS_ROOT / "images", CORPUS_ROOT / "labels"
    if not images_dir.is_dir():
        return []
    cases = []
    for image_path in sorted(images_dir.glob("*.jpg")):
        label_path = labels_dir / f"{image_path.stem}.json"
        if label_path.is_file():
            cases.append((image_path, json.loads(label_path.read_text())))
    return cases


CORPUS_CASES = _corpus_cases()


# --- canonical (mm-space) geometry — pure, deterministic -------------------


def test_canonical_fiducial_corners_match_geometry_helper():
    expected = TEMPLATE.geometry.fiducial_centres_mm(TEMPLATE.page_width_mm, TEMPLATE.page_height_mm)
    got = canonical_fiducial_corners_mm(TEMPLATE)
    assert got.shape == (4, 2)
    np.testing.assert_allclose(got, expected)


def test_canonical_qr_corners_sit_strictly_inside_the_qr_box():
    q = TEMPLATE.geometry.qr
    corners = canonical_qr_corners_mm(TEMPLATE)
    assert corners.shape == (4, 2)
    # inset from the box on every side (excludes the qrcode library's quiet zone),
    # but by less than one module width's worth of slack
    assert (corners[:, 0] > q.x_mm).all() and (corners[:, 0] < q.x_mm + q.size_mm).all()
    assert (corners[:, 1] > q.y_mm).all() and (corners[:, 1] < q.y_mm + q.size_mm).all()
    inset = corners[0, 0] - q.x_mm
    assert 0 < inset < q.size_mm * 0.1  # a couple of quiet-zone modules, not a big fraction
    # TL/TR/BR/BL order
    x0, y0 = corners[0]
    x1, y1 = corners[1]
    x2, y2 = corners[2]
    x3, y3 = corners[3]
    assert x1 > x0 and y1 == pytest.approx(y0)  # TR is right of TL, same y
    assert x2 == pytest.approx(x1) and y2 > y1  # BR is below TR, same x
    assert x3 == pytest.approx(x0) and y3 == pytest.approx(y2)  # BL closes the box


# --- structural / failure-path behaviour — synthetic inputs are fine here,
# these assert *behaviour*, not corpus accuracy (rule 9 governs accuracy claims) --


def test_detect_fiducials_returns_none_on_a_blank_image():
    blank = np.full((800, 600), 255, dtype=np.uint8)
    assert detect_fiducials(blank) is None


def test_detect_qr_returns_none_on_a_blank_image():
    blank = np.full((800, 600), 255, dtype=np.uint8)
    text, pts = detect_qr(blank, top_left_fiducial_px=np.array([0.0, 0.0]))
    assert text is None and pts is None


def test_detect_stage_a_raises_marks_not_found_on_a_blank_image():
    blank = np.full((800, 600, 3), 255, dtype=np.uint8)
    with pytest.raises(AlignmentError) as exc_info:
        detect_stage_a(blank, TEMPLATE)
    assert exc_info.value.reason == "marks_not_found"


# --- real corpus DoD (rule 9) ------------------------------------------------


@pytest.mark.skipif(not CORPUS_CASES, reason="corpus/images has no labeled real captures")
@pytest.mark.parametrize("image_path,label", CORPUS_CASES, ids=[c[0].stem for c in CORPUS_CASES])
def test_stage_a_detection_on_real_corpus_capture(image_path, label):
    image = cv2.imread(str(image_path))
    assert image is not None, f"failed to read {image_path}"

    corr = detect_stage_a(image, TEMPLATE)  # raises AlignmentError -> a real test failure
    assert corr.mm.shape == (8, 2)
    assert corr.px.shape == (8, 2)

    # the decoded QR payload must be the sheet this photo actually is (an
    # unambiguous, label-independent correctness signal — not a guess)
    assert corr.qr_text == label["sheet_token"]

    fit = fit_homography_robust(corr.mm, corr.px, **STAGE_A_GATE, ransac_iters=300)
    assert fit.n_inliers == 8, "a real capture should not need to drop any Stage-A point"


def test_corpus_has_labeled_real_captures():
    # guards against the corpus-driven tests above silently skipping to green
    # because corpus/images was empty or unlabeled
    assert len(CORPUS_CASES) >= 20, (
        f"expected the Phase 0.7 corpus (>=20 labeled captures), found {len(CORPUS_CASES)} — "
        "Phase 5.2's DoD must be measured against real captures (CLAUDE.md rule 9)"
    )
