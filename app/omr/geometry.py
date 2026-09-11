"""Projective-geometry solver core for OMR alignment (REBUILD_SPEC §2 R5.1/R5.3,
§4 design principles 3 & 4).

**Pure** — `numpy` only, no `cv2`, no Django (CLAUDE.md rule 7). This is the linear
algebra: a normalized-DLT homography, an over-determined robust fit with an absolute
quality gate, page-orientation resolution, and grid projection. The image→points
front-end (perimeter detection) is Phase 5.2 and is measured against the real corpus;
none of that lives here.

Convention: a homography `H` maps **canonical answer-sheet millimetres → source-image
pixels** (top-left origin in both spaces). `apply_homography(H, mm)` therefore gives
the pixel location to crop from the captured photo.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

_ORIENTATIONS = (0, 90, 180, 270)


class AlignmentError(Exception):
    """The clean-failure channel (R5.3): a wrong-but-'successful' fit is strictly
    worse than a specific failure, so every give-up path raises this with a reason.
    """

    REASONS = frozenset(
        {"marks_not_found", "fit_quality", "ambiguous_orientation", "version_not_found"}
    )

    def __init__(self, reason: str, detail: str = "") -> None:
        if reason not in self.REASONS:
            raise ValueError(f"unknown AlignmentError reason: {reason!r}")
        self.reason = reason
        super().__init__(f"{reason}: {detail}" if detail else reason)


@dataclass(frozen=True)
class HomographyFit:
    H: np.ndarray  # (3, 3), canonical-mm → image-px
    rms_px: float
    max_px: float
    n_points: int
    n_inliers: int
    inlier_mask: np.ndarray  # (n_points,) bool


# --- core homography ---------------------------------------------------------


def _as_xy(points) -> np.ndarray:
    arr = np.asarray(points, dtype=np.float64)
    if arr.ndim != 2 or arr.shape[1] != 2:
        raise ValueError(f"expected (N, 2) points, got shape {arr.shape}")
    return arr


def _normalizing_transform(pts: np.ndarray) -> np.ndarray:
    """Hartley normalization: centroid → origin, mean distance → sqrt(2)."""
    centroid = pts.mean(axis=0)
    shifted = pts - centroid
    mean_dist = np.sqrt((shifted**2).sum(axis=1)).mean()
    if mean_dist < 1e-12:
        raise np.linalg.LinAlgError("degenerate point set (all coincident)")
    s = np.sqrt(2.0) / mean_dist
    return np.array([[s, 0.0, -s * centroid[0]], [0.0, s, -s * centroid[1]], [0.0, 0.0, 1.0]])


def apply_homography(H: np.ndarray, points) -> np.ndarray:
    pts = _as_xy(points)
    homo = np.hstack([pts, np.ones((len(pts), 1))])
    projected = homo @ np.asarray(H, dtype=np.float64).T
    w = projected[:, 2:3]
    if np.any(np.abs(w) < 1e-12):
        raise np.linalg.LinAlgError("point projected to infinity")
    return projected[:, :2] / w


def invert_homography(H: np.ndarray) -> np.ndarray:
    inv = np.linalg.inv(np.asarray(H, dtype=np.float64))
    return inv / inv[2, 2]


def homography_dlt(src, dst) -> np.ndarray:
    """Normalized Direct Linear Transform. `src`, `dst`: ≥ 4 correspondences.
    Exact (reprojection ≈ 0) when `dst` is a true projective image of `src`.
    """
    src_xy, dst_xy = _as_xy(src), _as_xy(dst)
    if len(src_xy) != len(dst_xy):
        raise ValueError("src and dst must have the same length")
    if len(src_xy) < 4:
        raise ValueError("homography needs at least 4 correspondences")

    t_src, t_dst = _normalizing_transform(src_xy), _normalizing_transform(dst_xy)
    src_n = apply_homography(t_src, src_xy)
    dst_n = apply_homography(t_dst, dst_xy)

    rows = []
    for (x, y), (u, v) in zip(src_n, dst_n, strict=True):
        rows.append([-x, -y, -1, 0, 0, 0, u * x, u * y, u])
        rows.append([0, 0, 0, -x, -y, -1, v * x, v * y, v])
    _, _, vt = np.linalg.svd(np.asarray(rows, dtype=np.float64))
    h_norm = vt[-1].reshape(3, 3)

    H = np.linalg.inv(t_dst) @ h_norm @ t_src
    if abs(H[2, 2]) < 1e-12:
        raise np.linalg.LinAlgError("degenerate homography (H[2,2] ~ 0)")
    return H / H[2, 2]


def reprojection_error(H: np.ndarray, src, dst) -> np.ndarray:
    """Per-correspondence Euclidean error in `dst` (pixel) space."""
    return np.linalg.norm(apply_homography(H, src) - _as_xy(dst), axis=1)


# --- robust over-determined fit + absolute gate -----------------------------


def fit_homography_robust(
    src,
    dst,
    *,
    gate_rms_px: float,
    gate_max_px: float,
    min_inliers: int,
    inlier_thresh_px: float | None = None,
    ransac_iters: int = 200,
    seed: int = 0,
) -> HomographyFit:
    """Seeded-deterministic RANSAC over 4-point minimal samples, refit by DLT on the
    inlier set. Raises `AlignmentError('fit_quality')` if the refit residual exceeds
    the absolute gate or too few inliers survive; `AlignmentError('marks_not_found')`
    if fewer than 4 correspondences are supplied.

    The gate values are **provisional** until Phase 0.7's corpus calibrates them —
    the tests assert behaviour relative to the gate, not the gate's numeric value.
    """
    src_xy, dst_xy = _as_xy(src), _as_xy(dst)
    n = len(src_xy)
    if n != len(dst_xy):
        raise ValueError("src and dst must have the same length")
    if n < 4:
        raise AlignmentError("marks_not_found", f"only {n} correspondences")
    if inlier_thresh_px is None:
        inlier_thresh_px = gate_max_px

    rng = np.random.default_rng(seed)
    best_mask = np.zeros(n, dtype=bool)

    # enough iterations to almost-surely hit a clean 4-subset even with ~40% outliers
    for _ in range(max(ransac_iters, 1)):
        idx = rng.choice(n, size=4, replace=False)
        try:
            H = homography_dlt(src_xy[idx], dst_xy[idx])
            mask = reprojection_error(H, src_xy, dst_xy) <= inlier_thresh_px
        except np.linalg.LinAlgError:
            continue
        if mask.sum() > best_mask.sum():
            best_mask = mask

    if best_mask.sum() < max(4, min_inliers):
        # fall back to an all-points fit once before giving up (helps the low-noise,
        # low-N case where every RANSAC subset is already the whole set)
        try:
            H_all = homography_dlt(src_xy, dst_xy)
            mask_all = reprojection_error(H_all, src_xy, dst_xy) <= inlier_thresh_px
            if mask_all.sum() > best_mask.sum():
                best_mask = mask_all
        except np.linalg.LinAlgError:
            pass

    if best_mask.sum() < 4 or best_mask.sum() < min_inliers:
        raise AlignmentError(
            "fit_quality", f"{int(best_mask.sum())} inliers < min_inliers={min_inliers}"
        )

    H = homography_dlt(src_xy[best_mask], dst_xy[best_mask])
    err = reprojection_error(H, src_xy[best_mask], dst_xy[best_mask])
    rms = float(np.sqrt((err**2).mean()))
    mx = float(err.max())
    if rms > gate_rms_px or mx > gate_max_px:
        raise AlignmentError("fit_quality", f"rms={rms:.2f}px max={mx:.2f}px over gate")

    return HomographyFit(
        H=H,
        rms_px=rms,
        max_px=mx,
        n_points=n,
        n_inliers=int(best_mask.sum()),
        inlier_mask=best_mask,
    )


# --- page orientation (R5.2 near-180°) --------------------------------------


def resolve_page_orientation(
    detected_quad,
    canonical_quad,
    *,
    asym_canonical,
    asym_detected,
    margin_px: float,
) -> int:
    """Which 0/90/180/270 rotation aligns the detected corner quad to canonical.

    The 4 corners alone give an exact (zero-residual) DLT for *every* rotation, so
    the only signal is an asymmetric landmark (the QR corner): the rotation whose
    homography maps `asym_canonical` closest to its detected position `asym_detected`
    wins. If the best two rotations are within `margin_px`, the capture is
    unresolvable → `AlignmentError('ambiguous_orientation')` (R5.2's
    clean-specific-failure branch).

    Returns degrees to rotate the *canonical* frame to match the capture.
    """
    det = _as_xy(detected_quad)
    can = _as_xy(canonical_quad)
    if len(det) != 4 or len(can) != 4:
        raise ValueError("orientation resolution needs exactly 4 corners each")

    scores: list[tuple[float, int]] = []
    for k, degrees in enumerate(_ORIENTATIONS):
        rotated = np.roll(can, -k, axis=0)
        try:
            H = homography_dlt(rotated, det)
            predicted = apply_homography(H, [asym_canonical])[0]
        except np.linalg.LinAlgError:
            continue
        scores.append((float(np.linalg.norm(predicted - np.asarray(asym_detected))), degrees))

    if not scores:
        raise AlignmentError("ambiguous_orientation", "no non-degenerate corner assignment")
    scores.sort()
    if len(scores) > 1 and scores[1][0] - scores[0][0] < margin_px:
        raise AlignmentError(
            "ambiguous_orientation",
            f"best two rotations within {margin_px}px ({scores[0]}, {scores[1]})",
        )
    return scores[0][1]


# --- grid projection -------------------------------------------------------


def project_points_mm(H: np.ndarray, points_mm) -> np.ndarray:
    """Canonical-mm → source-image-px. Thin, named wrapper so call sites read as
    intent (`project_points_mm(fit.H, bubble_centres_mm)`), not raw matrix ops."""
    return apply_homography(H, points_mm)
