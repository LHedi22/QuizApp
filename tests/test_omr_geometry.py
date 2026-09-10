"""Phase 5.1 DoD — projective solver core, verified against analytic ground truth
(no corpus, no DB, no cv2). See docs/phases/phase-5.md.
"""
from __future__ import annotations

import numpy as np
import pytest

from app.omr.geometry import (
    AlignmentError,
    apply_homography,
    fit_homography_robust,
    homography_dlt,
    invert_homography,
    reprojection_error,
    resolve_page_orientation,
)
from app.sheet_template import bubble_centres, load_template

TEMPLATE = load_template()
W, H = TEMPLATE.page_width_mm, TEMPLATE.page_height_mm
PAGE_CORNERS = np.array([[0.0, 0.0], [W, 0.0], [W, H], [0.0, H]])  # TL, TR, BR, BL

# generous provisional gate — 5.1 tests behaviour *relative* to it, not its value
GATE = {"gate_rms_px": 6.0, "gate_max_px": 15.0, "min_inliers": 6}


def make_homography(rng, *, rot_deg=0.0, keystone_px=0.0, scale=6.0, tx=40.0, ty=40.0):
    """A plausible canonical-mm → image-px capture transform."""
    theta = np.radians(rot_deg)
    c, s = np.cos(theta), np.sin(theta)
    centre = np.array([W / 2, H / 2])
    rot = (PAGE_CORNERS - centre) @ np.array([[c, -s], [s, c]]).T + centre
    img = rot * scale + np.array([tx, ty])
    img = img + rng.uniform(-keystone_px, keystone_px, img.shape)
    return homography_dlt(PAGE_CORNERS, img)


def stage_a_points():
    """4 fiducials + 3 QR-box corners — version-independent (7 points)."""
    fid = np.array(TEMPLATE.geometry.fiducial_centres_mm(W, H))
    q = TEMPLATE.geometry.qr
    qr = np.array([[q.x_mm, q.y_mm], [q.x_mm + q.size_mm, q.y_mm], [q.x_mm, q.y_mm + q.size_mm]])
    return np.vstack([fid, qr])


def stage_b_points(num_questions=40, n_options=4):
    """4 fiducials + one tick per bubble row (both edges) + one per option column."""
    fid = list(TEMPLATE.geometry.fiducial_centres_mm(W, H))
    centres = bubble_centres(TEMPLATE, num_questions, n_options)
    row_ys = sorted({round(y, 4) for opts in centres.values() for _, y in opts})
    col_xs = sorted({round(x, 4) for opts in centres.values() for x, _ in opts})
    m = TEMPLATE.margin_mm
    ticks = (
        [(m - 3, y) for y in row_ys]
        + [(W - m + 3, y) for y in row_ys]
        + [(x, m - 3) for x in col_xs]
    )
    return np.array(fid + ticks)


def grid_mm():
    centres = bubble_centres(TEMPLATE, 40, 4)
    return np.array([p for opts in centres.values() for p in opts])


# --- 1. exactness ---------------------------------------------------------


def test_dlt_is_exact_for_a_true_projective_map():
    rng = np.random.default_rng(1)
    h_true = make_homography(rng, rot_deg=12.0, keystone_px=25.0)
    src = stage_a_points()
    dst = apply_homography(h_true, src)

    fit = fit_homography_robust(src, dst, **GATE)
    assert fit.rms_px < 1e-6
    grid_true = apply_homography(h_true, grid_mm())
    grid_est = apply_homography(fit.H, grid_mm())
    assert np.abs(grid_true - grid_est).max() < 1e-6


def test_apply_and_invert_round_trip():
    rng = np.random.default_rng(2)
    h = make_homography(rng, rot_deg=-8.0, keystone_px=15.0)
    pts = grid_mm()
    back = apply_homography(invert_homography(h), apply_homography(h, pts))
    assert np.abs(back - pts).max() < 1e-9


# --- 2. noise -----------------------------------------------------------


@pytest.mark.parametrize("rot_deg", [-20.0, -7.0, 0.0, 11.0, 20.0])
def test_recovers_grid_under_detection_noise(rot_deg):
    rng = np.random.default_rng(hash(rot_deg) % 2**32)
    h_true = make_homography(rng, rot_deg=rot_deg, keystone_px=30.0, scale=5.0)
    src = stage_b_points()
    dst = apply_homography(h_true, src) + rng.normal(0.0, 1.5, (len(src), 2))

    fit = fit_homography_robust(src, dst, **GATE)
    grid_true = apply_homography(h_true, grid_mm())
    grid_est = apply_homography(fit.H, grid_mm())
    assert np.abs(grid_true - grid_est).max() < 3.0
    assert 0.0 < fit.rms_px < GATE["gate_rms_px"]
    assert fit.n_inliers >= len(src) - 2


# --- 3. robustness to gross outliers ----------------------------------


def test_ransac_rejects_a_few_mis_detected_marks():
    rng = np.random.default_rng(4)
    h_true = make_homography(rng, rot_deg=6.0, keystone_px=20.0)
    src = stage_b_points()
    dst = apply_homography(h_true, src) + rng.normal(0.0, 0.8, (len(src), 2))
    bad = [3, 17]
    dst[bad] += np.array([40.0, -45.0])

    fit = fit_homography_robust(src, dst, **GATE)
    assert not fit.inlier_mask[bad].any()
    grid_err = np.abs(apply_homography(fit.H, grid_mm()) - apply_homography(h_true, grid_mm())).max()
    assert grid_err < 2.0


def test_too_many_outliers_is_a_clean_failure():
    rng = np.random.default_rng(5)
    h_true = make_homography(rng, rot_deg=3.0)
    src = stage_b_points()
    dst = apply_homography(h_true, src)
    # corrupt 30 of 40 points with random large offsets (no consistent wrong plane)
    corrupt = rng.choice(len(src), size=30, replace=False)
    dst[corrupt] += rng.uniform(-60, 60, (30, 2))

    with pytest.raises(AlignmentError) as exc:
        fit_homography_robust(src, dst, gate_rms_px=2.0, gate_max_px=4.0, min_inliers=20)
    assert exc.value.reason == "fit_quality"


# --- 4. occlusion ------------------------------------------------------


def test_partial_occlusion_still_fits_then_fails_cleanly():
    rng = np.random.default_rng(6)
    h_true = make_homography(rng, rot_deg=-10.0, keystone_px=18.0)
    src = stage_a_points()
    dst = apply_homography(h_true, src) + rng.normal(0, 1.0, (7, 2))

    fit = fit_homography_robust(src[:5], dst[:5], **{**GATE, "min_inliers": 4})
    assert fit.n_inliers >= 4

    with pytest.raises(AlignmentError) as exc:
        fit_homography_robust(src[:3], dst[:3], **GATE)
    assert exc.value.reason == "marks_not_found"


# --- 5. orientation (R5.2) ------------------------------------------


def _quad_and_asym(h_true, asym_canonical):
    return apply_homography(h_true, PAGE_CORNERS), apply_homography(h_true, [asym_canonical])[0]


def test_upright_capture_resolves_to_zero():
    rng = np.random.default_rng(7)
    h_true = make_homography(rng, rot_deg=9.0, keystone_px=20.0)
    q = TEMPLATE.geometry.qr
    asym_canonical = np.array([q.x_mm + q.size_mm / 2, q.y_mm + q.size_mm / 2])  # near TL
    detected, asym_detected = _quad_and_asym(h_true, asym_canonical)

    deg = resolve_page_orientation(
        detected, PAGE_CORNERS, asym_canonical=asym_canonical, asym_detected=asym_detected, margin_px=20.0
    )
    assert deg == 0


def test_upside_down_capture_resolves_to_180():
    rng = np.random.default_rng(8)
    h_true = make_homography(rng, rot_deg=-5.0, keystone_px=15.0)
    q = TEMPLATE.geometry.qr
    asym_canonical = np.array([q.x_mm + q.size_mm / 2, q.y_mm + q.size_mm / 2])
    # detector saw the sheet rotated 180°: its corner i is really canonical corner i+2
    upright, asym_detected = _quad_and_asym(h_true, asym_canonical)
    detected = np.roll(upright, -2, axis=0)

    deg = resolve_page_orientation(
        detected, PAGE_CORNERS, asym_canonical=asym_canonical, asym_detected=asym_detected, margin_px=20.0
    )
    assert deg == 180


def test_symmetric_landmark_is_ambiguous():
    rng = np.random.default_rng(9)
    h_true = make_homography(rng, rot_deg=2.0)
    centre = np.array([W / 2, H / 2])  # a landmark on the symmetry centre carries no signal
    detected, asym_detected = _quad_and_asym(h_true, centre)

    with pytest.raises(AlignmentError) as exc:
        resolve_page_orientation(
            detected, PAGE_CORNERS, asym_canonical=centre, asym_detected=asym_detected, margin_px=20.0
        )
    assert exc.value.reason == "ambiguous_orientation"


# --- 6. gate direction: over-determination makes residual a real signal ---


def test_inconsistent_correspondences_never_return_a_bad_fit():
    rng = np.random.default_rng(10)
    src = rng.uniform(0, 200, (8, 2))
    dst = rng.uniform(0, 1200, (8, 2))  # no projective relationship
    with pytest.raises(AlignmentError) as exc:
        fit_homography_robust(src, dst, gate_rms_px=1.0, gate_max_px=2.0, min_inliers=6)
    assert exc.value.reason == "fit_quality"


def test_reprojection_error_matches_manual():
    rng = np.random.default_rng(11)
    h = make_homography(rng, rot_deg=4.0)
    src = grid_mm()[:5]
    dst = apply_homography(h, src)
    dst[2] += [3.0, 4.0]
    err = reprojection_error(h, src, dst)
    assert err[0] < 1e-9 and abs(err[2] - 5.0) < 1e-9
