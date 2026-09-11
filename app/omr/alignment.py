"""Two-stage alignment orchestration (REBUILD_SPEC §5 Phase 5.3).

Stage A (5.2, version-independent) -> version lookup -> Stage B (version-specific
timing-mark grid, refined via local search, carries the final gate) ->
`PageAlignment`, or a clean `AlignmentError` (R5.3: never a guessed-but-wrong fit).

**Pure** — `cv2` / `numpy` / `app.omr` / `app.sheet_template` only, no Django (rule
7). R5.1 step 3 ("looks up the version") is a DB read in real use, which can't live
here — `align_page` takes an injected `version_lookup` callable instead, so Phase 7
can wire in the real `Version.qr_id` lookup while this module stays pure and
independently testable against the corpus.

Design notes (documented, not silent deviations from the original plan):

- **No separate "rectify then decode" step.** The QR is decoded straight from the
  raw image as part of Stage A (5.2) via `pyzbar`, not from a warped canonical
  crop. This already proved reliable on the full corpus (20/20) in 5.2, and a
  literal image warp before decode would only add interpolation-blur risk with no
  measured benefit — `align_page` reuses Stage A's decode result rather than
  redoing it.
- **Stage B never re-detects the fiducials.** They're already known precisely from
  Stage A's own contour-based detection; Stage B only adds the version-specific
  timing-tick points (one per bubble row on both edges + one per option column) to
  the same 4 fiducials, giving an over-determined fit (design principle 3) without
  duplicate, less-precise fiducial re-detection.
- `AlignmentError` (in `app.omr.geometry`) carries a 4th reason,
  `version_not_found`, for a QR that decodes cleanly but doesn't correspond to a
  known version (`version_lookup` returning nothing) — a real failure mode R5.1
  step 3 introduces that the original 3 reasons (all about the *geometric* fit)
  don't cover. Still the same clean-failure doctrine: never guess a version.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import cv2
import numpy as np

from app.omr.detect import canonical_fiducial_corners_mm, detect_stage_a
from app.omr.geometry import AlignmentError, HomographyFit, apply_homography, fit_homography_robust
from app.sheet_template import SheetTemplate, bubble_centres


@dataclass(frozen=True)
class VersionGeometry:
    """The minimum a `version_lookup` needs to return to let Stage B proceed."""

    num_questions: int
    n_options: int


@dataclass(frozen=True)
class PageAlignment:
    """The Phase 5 deliverable: a version-known homography ready to hand bubble-crop
    coordinates to Phase 6 (`app.omr.geometry.project_points_mm(H, bubble_mm)` on
    the *source* image — no page warp is ever materialized, rule 7-friendly and
    avoids interpolation loss)."""

    H: np.ndarray  # canonical-mm -> image-px, Stage B (final, higher-precision)
    qr_text: str
    num_questions: int
    n_options: int
    stage_a_fit: HomographyFit
    stage_b_fit: HomographyFit


# Provisional gates, calibrated against the actual 20-photo corpus (not re-derived
# from first principles) — see docs/PROGRESS.md. 5.5 owns the formal
# reliability-budget writeup; these tests assert behaviour relative to the gate.
STAGE_A_GATE = {"gate_rms_px": 12.0, "gate_max_px": 25.0, "min_inliers": 6}
STAGE_B_GATE = {"gate_rms_px": 12.0, "gate_max_px": 30.0}
_MIN_TICK_FOUND_FRACTION = 0.5  # of the full expected tick set
_MIN_STAGE_B_INLIER_FRACTION = 0.7  # of the ticks actually found


def canonical_stage_b_ticks_mm(template: SheetTemplate, num_questions: int, n_options: int) -> np.ndarray:
    """Canonical mm timing-tick positions: one per bubble row (both edges) + one
    per option column across the top. Matches `app/pdf/answer_sheet.py`'s
    `_draw_timing_marks` exactly. Excludes the fiducials (see module docstring)."""
    centres = bubble_centres(template, num_questions, n_options)
    row_ys = sorted({round(y, 4) for opts in centres.values() for _, y in opts})
    col_xs = sorted({round(x, 4) for opts in centres.values() for x, _ in opts})
    m = template.margin_mm
    w = template.page_width_mm
    ticks = (
        [(m - 3, y) for y in row_ys]
        + [(w - m + 3, y) for y in row_ys]
        + [(x, m - 3) for x in col_xs]
    )
    return np.array(ticks, dtype=np.float64)


def _detect_tick_near(
    gray: np.ndarray,
    predicted_px: np.ndarray,
    *,
    search_radius_px: float,
    min_area_px: float,
    max_area_px: float,
) -> tuple[float, float] | None:
    """Local-window search for one timing-mark blob near a Stage-A-predicted
    position: Otsu-threshold just that window (marks are locally the darkest
    thing present), take the plausibly-tick-sized contour closest to the
    prediction. Returns the refined px centroid, or `None` if nothing plausible
    was found in the window."""
    x0, y0 = predicted_px
    h, w = gray.shape
    xa, xb = max(0, int(x0 - search_radius_px)), min(w, int(x0 + search_radius_px))
    ya, yb = max(0, int(y0 - search_radius_px)), min(h, int(y0 + search_radius_px))
    if xb - xa < 5 or yb - ya < 5:
        return None
    window = gray[ya:yb, xa:xb]
    _, thresh = cv2.threshold(window, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(thresh, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    best: tuple[float, float] | None = None
    best_dist = None
    cx0, cy0 = x0 - xa, y0 - ya
    for c in contours:
        area = cv2.contourArea(c)
        if not (min_area_px <= area <= max_area_px):
            continue
        m = cv2.moments(c)
        if m["m00"] == 0:
            continue
        cx, cy = m["m10"] / m["m00"], m["m01"] / m["m00"]
        dist = (cx - cx0) ** 2 + (cy - cy0) ** 2
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best = (cx + xa, cy + ya)
    return best


def detect_stage_b(
    gray: np.ndarray,
    template: SheetTemplate,
    *,
    num_questions: int,
    n_options: int,
    fiducial_mm: np.ndarray,
    fiducial_px: np.ndarray,
    stage_a_H: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Refine Stage A's fit with the version-specific timing-tick grid.

    Returns `(mm, px)` of the **matched** point set only: the 4 already-known
    fiducials plus every timing tick actually found near its Stage-A-predicted
    location. Raises `AlignmentError('marks_not_found')` if fewer than half the
    expected ticks are found at all — not enough signal to even attempt a
    meaningful Stage-B fit.
    """
    tick_mm = canonical_stage_b_ticks_mm(template, num_questions, n_options)
    predicted_tick_px = apply_homography(stage_a_H, tick_mm)

    tm = template.geometry.timing_mark
    fid_px_pred = apply_homography(stage_a_H, fiducial_mm)
    px_per_mm = float(
        np.linalg.norm(fid_px_pred[0] - fid_px_pred[1]) / np.linalg.norm(fiducial_mm[0] - fiducial_mm[1])
    )
    search_radius_px = 3.0 * px_per_mm
    tick_area_mm2 = tm.length_mm * tm.thickness_mm
    min_area_px = 0.3 * tick_area_mm2 * px_per_mm**2
    max_area_px = 3.0 * tick_area_mm2 * px_per_mm**2

    matched_mm = [fiducial_mm[i] for i in range(len(fiducial_mm))]
    matched_px = [fiducial_px[i] for i in range(len(fiducial_px))]
    for mm_pt, predicted in zip(tick_mm, predicted_tick_px, strict=True):
        found = _detect_tick_near(
            gray, predicted, search_radius_px=search_radius_px, min_area_px=min_area_px, max_area_px=max_area_px
        )
        if found is not None:
            matched_mm.append(mm_pt)
            matched_px.append(found)

    n_ticks_found = len(matched_mm) - len(fiducial_mm)
    if n_ticks_found < _MIN_TICK_FOUND_FRACTION * len(tick_mm):
        raise AlignmentError(
            "marks_not_found", f"only {n_ticks_found}/{len(tick_mm)} Stage-B ticks found"
        )
    return np.array(matched_mm), np.array(matched_px)


def align_page(
    image_bgr: np.ndarray,
    template: SheetTemplate,
    *,
    version_lookup: Callable[[str], VersionGeometry | None],
) -> PageAlignment:
    """The full Phase 5 pipeline: Stage A -> version lookup -> Stage B ->
    `PageAlignment`. Raises `AlignmentError` (never returns a partial/guessed
    result — R5.3) with `reason`:
    - `marks_not_found` — Stage A's fiducials/QR, or too few Stage-B ticks;
    - `fit_quality` — either stage's homography fit is over the absolute gate;
    - `version_not_found` — the QR decoded cleanly but isn't a known version.
    """
    gray = image_bgr if image_bgr.ndim == 2 else cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

    stage_a_corr = detect_stage_a(image_bgr, template)  # raises AlignmentError
    stage_a_fit = fit_homography_robust(stage_a_corr.mm, stage_a_corr.px, **STAGE_A_GATE, ransac_iters=300)

    if not stage_a_corr.qr_text:
        raise AlignmentError("marks_not_found", "QR detected but did not decode to text")
    version = version_lookup(stage_a_corr.qr_text)
    if version is None:
        raise AlignmentError("version_not_found", f"unrecognized qr_text {stage_a_corr.qr_text!r}")

    fiducial_mm = canonical_fiducial_corners_mm(template)
    fiducial_px = stage_a_corr.px[:4]
    stage_b_mm, stage_b_px = detect_stage_b(
        gray,
        template,
        num_questions=version.num_questions,
        n_options=version.n_options,
        fiducial_mm=fiducial_mm,
        fiducial_px=fiducial_px,
        stage_a_H=stage_a_fit.H,
    )
    min_inliers = max(len(fiducial_mm) + 2, int(_MIN_STAGE_B_INLIER_FRACTION * len(stage_b_mm)))
    stage_b_fit = fit_homography_robust(
        stage_b_mm, stage_b_px, **STAGE_B_GATE, min_inliers=min_inliers, ransac_iters=500
    )

    return PageAlignment(
        H=stage_b_fit.H,
        qr_text=stage_a_corr.qr_text,
        num_questions=version.num_questions,
        n_options=version.n_options,
        stage_a_fit=stage_a_fit,
        stage_b_fit=stage_b_fit,
    )
