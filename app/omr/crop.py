"""Bubble-grid rectification (REBUILD_SPEC §5 Phase 5.4).

`PageAlignment` (5.3) + version geometry -> per-(question, option) crop boxes in
the **source image** — no page warp is ever materialized (see `app.omr.alignment`).
Pure: `numpy` + `app.omr.geometry` + `app.sheet_template`, no Django (rule 7).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.omr.geometry import apply_homography
from app.sheet_template import SheetTemplate, bubble_centres

_DEFAULT_MARGIN_MM = 0.5


@dataclass(frozen=True)
class BubbleCropBox:
    """An axis-aligned crop box in source-image px for one (question, option)."""

    question: int
    option_index: int  # 0-based: 0=A, 1=B, ...
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    def center(self) -> tuple[float, float]:
        return ((self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2)

    def as_int_bounds(self) -> tuple[int, int, int, int]:
        """`(x0, y0, x1, y1)` rounded to int px, suitable for array slicing."""
        return (round(self.x0), round(self.y0), round(self.x1), round(self.y1))


def bubble_crop_boxes(
    H: np.ndarray,
    template: SheetTemplate,
    num_questions: int,
    n_options: int,
    *,
    margin_mm: float = _DEFAULT_MARGIN_MM,
) -> dict[int, list[BubbleCropBox]]:
    """1-based question -> list of per-option `BubbleCropBox` (index = option),
    in source-image px.

    Each box is the axis-aligned bounding box, in image space, of the bubble's mm
    -space footprint (`bubble_diameter_mm + 2*margin_mm`, centred on the bubble)
    projected through `H`. Projecting the footprint's corners (rather than
    assuming one global px-per-mm scale) means each box's size correctly reflects
    the *local* perspective scale/rotation at that point on the page — bubbles
    near the camera don't get an undersized box just because the far edge of the
    page is smaller in the photo.
    """
    centres = bubble_centres(template, num_questions, n_options)
    half = template.geometry.grid.bubble_diameter_mm / 2 + margin_mm

    boxes: dict[int, list[BubbleCropBox]] = {}
    for question, options in centres.items():
        q_boxes = []
        for option_index, (cx, cy) in enumerate(options):
            corners_mm = np.array(
                [
                    [cx - half, cy - half],
                    [cx + half, cy - half],
                    [cx + half, cy + half],
                    [cx - half, cy + half],
                ]
            )
            corners_px = apply_homography(H, corners_mm)
            x0, y0 = corners_px.min(axis=0)
            x1, y1 = corners_px.max(axis=0)
            q_boxes.append(
                BubbleCropBox(
                    question=question,
                    option_index=option_index,
                    x0=float(x0),
                    y0=float(y0),
                    x1=float(x1),
                    y1=float(y1),
                )
            )
        boxes[question] = q_boxes
    return boxes


def crop_mean_intensity(gray: np.ndarray, box: BubbleCropBox) -> float | None:
    """Mean grayscale intensity within a crop box (0=black, 255=white,
    `gray.dtype` any numeric), or `None` if the box falls even partially outside
    the image bounds. A thin, deliberately dumb summary — Phase 6's actual bubble
    classifier does the real filled/empty/ambiguous work; this only exists so
    5.4's DoD can check crop-box *placement* against real corpus ink."""
    h, w = gray.shape[:2]
    x0, y0, x1, y1 = box.as_int_bounds()
    if x0 < 0 or y0 < 0 or x1 > w or y1 > h or x1 <= x0 or y1 <= y0:
        return None
    region = gray[y0:y1, x0:x1]
    if region.size == 0:
        return None
    return float(region.mean())
