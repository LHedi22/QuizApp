"""Phase 5.3 DoD — two-stage alignment orchestration, measured against the real
Phase 0.7 corpus (CLAUDE.md rule 9). See docs/phases/phase-5.md.
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.omr.alignment import (
    STAGE_B_GATE,
    PageAlignment,
    VersionGeometry,
    align_page,
    canonical_stage_b_ticks_mm,
    detect_stage_b,
)
from app.omr.detect import canonical_fiducial_corners_mm, detect_stage_a
from app.omr.geometry import AlignmentError, apply_homography, fit_homography_robust
from app.sheet_template import load_template

TEMPLATE = load_template()
CORPUS_ROOT = Path(__file__).resolve().parent.parent / "corpus"


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


# --- pure canonical-geometry math --------------------------------------------


def test_canonical_stage_b_ticks_match_the_pdf_renderer_layout():
    # sheet_b: 40Q, N=4, 4 columns -> 10 rows/column
    ticks = canonical_stage_b_ticks_mm(TEMPLATE, num_questions=40, n_options=4)
    # 10 row ticks * 2 edges + (4 cols * 4 options) column ticks = 20 + 16 = 36
    assert ticks.shape == (36, 2)


# --- failure paths (structural, synthetic inputs assert behaviour) ----------


def test_align_page_raises_marks_not_found_on_a_blank_image():
    blank = np.full((800, 600, 3), 255, dtype=np.uint8)
    with pytest.raises(AlignmentError) as exc_info:
        align_page(blank, TEMPLATE, version_lookup=_corpus_version_lookup)
    assert exc_info.value.reason == "marks_not_found"


@pytest.mark.skipif(not CORPUS_CASES, reason="corpus/images has no labeled real captures")
def test_align_page_raises_version_not_found_for_an_unknown_qr():
    image_path, _, _ = CORPUS_CASES[0]
    image = cv2.imread(str(image_path))
    with pytest.raises(AlignmentError) as exc_info:
        align_page(image, TEMPLATE, version_lookup=lambda _text: None)
    assert exc_info.value.reason == "version_not_found"


# --- real corpus DoD (rule 9) ------------------------------------------------


@pytest.mark.skipif(not CORPUS_CASES, reason="corpus/images has no labeled real captures")
@pytest.mark.parametrize("image_path,label,meta", CORPUS_CASES, ids=[c[0].stem for c in CORPUS_CASES])
def test_align_page_on_real_corpus_capture(image_path, label, meta):
    image = cv2.imread(str(image_path))
    assert image is not None, f"failed to read {image_path}"

    alignment = align_page(image, TEMPLATE, version_lookup=_corpus_version_lookup)
    assert isinstance(alignment, PageAlignment)
    assert alignment.qr_text == label["sheet_token"]
    assert alignment.num_questions == meta["questions"]
    assert alignment.n_options == meta["options"]

    # Stage B must find (and use) at least the fiducials plus a solid majority of
    # the expected timing ticks -- not just squeak past the raw gate values.
    expected_ticks = len(canonical_stage_b_ticks_mm(TEMPLATE, meta["questions"], meta["options"]))
    n_points = alignment.stage_b_fit.n_points
    assert n_points >= 4 + 0.9 * expected_ticks, (
        f"Stage B only matched {n_points - 4}/{expected_ticks} ticks on a real capture"
    )
    assert alignment.stage_b_fit.rms_px <= STAGE_B_GATE["gate_rms_px"]

    # the final homography should place the bubble-grid centre sensibly inside
    # the actual photo (a coarse sanity check that H isn't degenerate)
    grid = TEMPLATE.geometry.grid
    centre_mm = np.array([[TEMPLATE.page_width_mm / 2, (grid.top_mm + grid.bottom_mm) / 2]])
    centre_px = apply_homography(alignment.H, centre_mm)[0]
    h, w = image.shape[:2]
    assert 0 <= centre_px[0] <= w and 0 <= centre_px[1] <= h


@pytest.mark.skipif(not CORPUS_CASES, reason="corpus/images has no labeled real captures")
@pytest.mark.parametrize("image_path,label,meta", CORPUS_CASES, ids=[c[0].stem for c in CORPUS_CASES])
def test_stage_b_improves_or_holds_on_stage_a_precision(image_path, label, meta):
    """Stage B (over-determined, version-specific) should not be meaningfully
    worse than Stage A (8 points) on a real capture -- otherwise the two-stage
    design (principle 3) isn't earning its complexity."""
    image = cv2.imread(str(image_path))
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    from app.omr.alignment import STAGE_A_GATE

    stage_a_corr = detect_stage_a(image, TEMPLATE)
    stage_a_fit = fit_homography_robust(stage_a_corr.mm, stage_a_corr.px, **STAGE_A_GATE, ransac_iters=300)

    fiducial_mm = canonical_fiducial_corners_mm(TEMPLATE)
    stage_b_mm, stage_b_px = detect_stage_b(
        gray,
        TEMPLATE,
        num_questions=meta["questions"],
        n_options=meta["options"],
        fiducial_mm=fiducial_mm,
        fiducial_px=stage_a_corr.px[:4],
        stage_a_H=stage_a_fit.H,
    )
    stage_b_fit = fit_homography_robust(
        stage_b_mm, stage_b_px, **STAGE_B_GATE, min_inliers=4, ransac_iters=500
    )
    # generous headroom -- this is a sanity/regression guard, not a tight bound
    assert stage_b_fit.rms_px <= stage_a_fit.rms_px + 2.0
