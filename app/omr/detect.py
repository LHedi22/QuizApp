"""Stage-A perimeter detection front-end (REBUILD_SPEC §5 Phase 5.2).

Turns a captured photo into an ordered Stage-A correspondence set — canonical-mm
points paired with the image-px points they were found at — ready for
`app.omr.geometry.fit_homography_robust`. Uses `cv2` + `pyzbar` (rule 7: no
Django import anywhere in `app/omr`).

Design note (2026-09-11): the original Stage-A plan (phase-5.md) called for "4
corner fiducials + 3 QR finder-pattern centres" (7 points). Built instead as
**4 fiducials + the QR's own 4 corners** (8 points), using `pyzbar`'s QR polygon
directly rather than hand-rolling finder-pattern detection — `pyzbar` already does
finder-pattern-level detection internally (it is a real, battle-tested QR reader,
not a heuristic), and its polygon gives one more usable point than 3 finder-pattern
centres would. See docs/PROGRESS.md for the corpus evidence this was checked
against (all 20 real corpus photos, cv2's own `QRCodeDetector` was unreliable on
these — 1/20 — pyzbar decoded 20/20).

Correspondence ordering: neither `pyzbar`'s polygon order nor the fiducial contours
carry known corner identity on their own. Both are resolved the same way — locate
the physical page's top-left by nearest-image-corner heuristic (fiducials) / nearest-
to-the-TL-fiducial heuristic (QR corners) — which is safe under the ±20°
in-plane rotation the spec targets (R5.2) and was cross-validated against all 20
real corpus photos: in every one, the QR centroid sits ~7-8x closer to the fiducial
identified as top-left than to any other detected fiducial. A grossly rotated (near
90°) capture could break this heuristic; `fit_homography_robust`'s absolute gate
(5.1) catches the resulting bad fit rather than silently producing a wrong one
(R5.3) — this module does not attempt to be correct in that case, only safe.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
import qrcode
from pyzbar import pyzbar

from app.omr.geometry import AlignmentError
from app.sheet_template import SheetTemplate

# Any 36-char UUID gives the same QR module count (fixed-length content, fixed EC
# level) — used only to derive the quiet-zone inset baked in by the PDF renderer.
_SAMPLE_QR_ID = "00000000-0000-0000-0000-000000000000"


@dataclass(frozen=True)
class StageACorrespondences:
    """`mm[i]` (canonical answer-sheet mm) corresponds to `px[i]` (source-image px)."""

    mm: np.ndarray  # (8, 2)
    px: np.ndarray  # (8, 2)
    qr_text: str | None  # decoded QR payload, if pyzbar returned one


def _to_gray(image: np.ndarray) -> np.ndarray:
    return image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def _sort_clockwise(points: np.ndarray) -> np.ndarray:
    """Sort 4 points into a clockwise cycle (TL, TR, BR, BL for a roughly-upright
    quad) by ascending angle around their centroid. Top-left-origin, y-down
    coordinates throughout (image px and canonical mm alike), so this ordering
    convention is consistent between the two spaces."""
    centroid = points.mean(axis=0)
    angles = np.arctan2(points[:, 1] - centroid[1], points[:, 0] - centroid[0])
    return points[np.argsort(angles)]


def _roll_to_nearest(points: np.ndarray, reference: np.ndarray) -> np.ndarray:
    """Cyclically roll `points` so index 0 is whichever point is nearest `reference`."""
    dists = np.linalg.norm(points - reference, axis=1)
    return np.roll(points, -int(np.argmin(dists)), axis=0)


# --- canonical (mm-space) Stage-A points ------------------------------------


def canonical_fiducial_corners_mm(template: SheetTemplate) -> np.ndarray:
    """(4, 2) mm points, TL/TR/BL/BR — matches `SheetGeometry.fiducial_centres_mm`."""
    return np.array(
        template.geometry.fiducial_centres_mm(template.page_width_mm, template.page_height_mm),
        dtype=np.float64,
    )


def canonical_qr_corners_mm(template: SheetTemplate) -> np.ndarray:
    """(4, 2) mm corners of the QR's actual dark-module square, TL/TR/BR/BL —
    **excluding** the `qrcode` library's quiet-zone border. `app/pdf/answer_sheet.py`
    draws the whole QR PNG (quiet zone included) stretched to fill
    `geometry.qr`'s `x_mm`/`y_mm`/`size_mm` box, so a real detector's corners sit
    inset from that box by `border / (modules + 2*border)` of its size — computed
    here from the actual `qrcode` render, not guessed.
    """
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_Q, box_size=12, border=2)
    qr.add_data(_SAMPLE_QR_ID)
    qr.make(fit=True)
    inset_frac = qr.border / (qr.modules_count + 2 * qr.border)

    g = template.geometry.qr
    inset = g.size_mm * inset_frac
    x0, y0 = g.x_mm + inset, g.y_mm + inset
    x1, y1 = g.x_mm + g.size_mm - inset, g.y_mm + g.size_mm - inset
    return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], dtype=np.float64)


# --- image-space (px) detection ---------------------------------------------


def detect_fiducials(image_bgr: np.ndarray) -> np.ndarray | None:
    """(4, 2) px points, ordered to match `canonical_fiducial_corners_mm` (TL/TR/BL/BR),
    or `None` if fewer than 4 plausible fiducial candidates are found.

    Fiducials are solid ~7mm black squares. Detected as: adaptive-threshold →
    contours → filter to convex near-square near-solid blobs in a page-relative
    (not absolute-px) area band, so this works across the "page fills 40-100% of
    the frame" range (R5.1) without per-resolution tuning.
    """
    gray = _to_gray(image_bgr)
    h, w = gray.shape
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    thresh = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 35, 10
    )
    contours, _ = cv2.findContours(thresh, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    page_area = h * w
    candidates: list[tuple[float, float]] = []
    for c in contours:
        area = cv2.contourArea(c)
        if not (0.00015 * page_area < area < 0.02 * page_area):
            continue
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.04 * peri, True)
        if len(approx) != 4 or not cv2.isContourConvex(approx):
            continue
        x, y, cw, ch = cv2.boundingRect(approx)
        if ch == 0 or not (0.7 < cw / ch < 1.4):
            continue
        if area / (cw * ch) < 0.7:  # solidity: filled squares are near 1.0
            continue
        m = cv2.moments(c)
        if m["m00"] == 0:
            continue
        candidates.append((m["m10"] / m["m00"], m["m01"] / m["m00"]))

    if len(candidates) < 4:
        return None

    image_corners = [(0.0, 0.0), (float(w), 0.0), (0.0, float(h)), (float(w), float(h))]
    remaining = list(candidates)
    chosen = []
    for corner in image_corners:
        remaining.sort(key=lambda p: (p[0] - corner[0]) ** 2 + (p[1] - corner[1]) ** 2)
        chosen.append(remaining.pop(0))
    return np.array(chosen, dtype=np.float64)


def detect_qr(image_bgr: np.ndarray, *, top_left_fiducial_px: np.ndarray) -> tuple[str | None, np.ndarray | None]:
    """`(decoded_text_or_None, (4, 2) px corners ordered TL/TR/BR/BL)`, or
    `(None, None)` if no QR is found. `top_left_fiducial_px` disambiguates which of
    the 4 detected QR corners is canonical-TL (see module docstring)."""
    gray = _to_gray(image_bgr)
    results = pyzbar.decode(gray, symbols=[pyzbar.ZBarSymbol.QRCODE])
    if not results:
        return None, None
    result = results[0]
    poly = np.array([[p.x, p.y] for p in result.polygon], dtype=np.float64)
    if len(poly) != 4:
        # a damaged/partial symbol can report a non-quad polygon; treat as not found
        return None, None
    ordered = _roll_to_nearest(_sort_clockwise(poly), top_left_fiducial_px)
    text = result.data.decode("utf-8", errors="replace") if result.data else None
    return text, ordered


def detect_stage_a(image_bgr: np.ndarray, template: SheetTemplate) -> StageACorrespondences:
    """The full Stage-A correspondence set (8 points: 4 fiducials + 4 QR corners).

    Raises `AlignmentError('marks_not_found')` if either the fiducials or the QR
    can't be located — the clean-failure channel (R5.3); this function never
    returns a partial/guessed correspondence set.
    """
    fiducials_px = detect_fiducials(image_bgr)
    if fiducials_px is None:
        raise AlignmentError("marks_not_found", "fewer than 4 fiducial candidates")

    qr_text, qr_px = detect_qr(image_bgr, top_left_fiducial_px=fiducials_px[0])
    if qr_px is None:
        raise AlignmentError("marks_not_found", "QR not detected")

    mm = np.vstack([canonical_fiducial_corners_mm(template), canonical_qr_corners_mm(template)])
    px = np.vstack([fiducials_px, qr_px])
    return StageACorrespondences(mm=mm, px=px, qr_text=qr_text)
