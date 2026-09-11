"""Bubble classifier + confidence gate (REBUILD_SPEC §5 Phase 6, §2 R5.5–R5.7).

Filled/empty/ambiguous classification per bubble via local-background-normalized
fill scoring (R5.6), plus the R5.7 confidence-gate rules applied per question and
per submission. **Pure**: `numpy` + `app.omr.geometry` + `app.sheet_template`
only, no Django (rule 7). No scoring (Phase 2's `score_question` is reused as-is
in Phase 7), no persistence, no duplicate detection (R5.8) — see
`docs/phases/phase-6.md` "What Phase 6 does NOT do".
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from app.omr.alignment import PageAlignment
from app.omr.geometry import AlignmentError, apply_homography
from app.sheet_template import SheetTemplate, bubble_centres


class BubbleState(StrEnum):
    FILLED = "filled"
    EMPTY = "empty"
    AMBIGUOUS = "ambiguous"


# Provisional thresholds, calibrated against the real 20-photo corpus (not
# re-derived from first principles — same pattern as Phase 5's gates). See
# docs/PROGRESS.md phase-6.1 entry: marked bubbles p5=0.538 (min 0.38), unmarked
# bubbles p99=0.008 (max 0.34) — wide headroom either side of this band.
DEFAULT_EMPTY_MAX = 0.15
DEFAULT_FILLED_MIN = 0.35


@dataclass(frozen=True)
class BubbleFill:
    question: int
    option_index: int
    fill_score: float  # NaN if the sample region fell outside the image
    state: BubbleState


def bubble_fill_score(
    gray: np.ndarray,
    H: np.ndarray,
    center_mm: tuple[float, float],
    bubble_diameter_mm: float,
    *,
    fill_frac: float = 0.55,
    bg_margin_mm: float = 2.0,
) -> float | None:
    """Local-background-normalized fill score for one bubble:
    `(background_mean - fill_mean) / background_mean`. ~0 for an empty bubble
    (the ink-sample region reads the same as its own local background), growing
    toward ~1 for a solid fill. `None` if the required sample region falls
    outside the image (never guessed — the caller must treat this as ambiguous).

    R5.6: the *local* background ring sampled right next to each bubble (not a
    page-wide fixed threshold) is what makes this robust to an illumination
    gradient across the page — a darker region shifts a bubble's raw brightness
    and its own local background together, and the ratio cancels the shift out.

    Local px-per-mm is derived from `H` right at this bubble (project two points
    1mm apart), not a single page-wide scale estimate, so it's correct under
    perspective — same approach as Phase 5.3's Stage-B tick search and 5.4's
    crop boxes.
    """
    p0 = apply_homography(H, np.array([center_mm]))[0]
    p1 = apply_homography(H, np.array([[center_mm[0] + 1, center_mm[1]]]))[0]
    px_per_mm = float(np.linalg.norm(p1 - p0))
    cx, cy = p0

    r_fill = 0.5 * bubble_diameter_mm * fill_frac * px_per_mm
    r_bg_inner = 0.5 * bubble_diameter_mm * 1.15 * px_per_mm  # clears the printed circle stroke
    r_bg_outer = (0.5 * bubble_diameter_mm + bg_margin_mm) * px_per_mm

    half = int(np.ceil(r_bg_outer)) + 2
    x0, y0 = int(round(cx - half)), int(round(cy - half))
    x1, y1 = int(round(cx + half)), int(round(cy + half))
    h, w = gray.shape[:2]
    if x0 < 0 or y0 < 0 or x1 > w or y1 > h:
        return None

    region = gray[y0:y1, x0:x1].astype(np.float64)
    yy, xx = np.ogrid[0 : region.shape[0], 0 : region.shape[1]]
    local_cx, local_cy = cx - x0, cy - y0
    dist = np.hypot(xx - local_cx, yy - local_cy)
    fill_mask = dist <= r_fill
    bg_mask = (dist > r_bg_inner) & (dist <= r_bg_outer)
    if fill_mask.sum() == 0 or bg_mask.sum() == 0:
        return None

    fill_mean = float(region[fill_mask].mean())
    bg_mean = float(region[bg_mask].mean())
    return (bg_mean - fill_mean) / max(bg_mean, 1e-6)


def classify_bubble_score(
    score: float | None,
    *,
    empty_max: float = DEFAULT_EMPTY_MAX,
    filled_min: float = DEFAULT_FILLED_MIN,
) -> BubbleState:
    if score is None:
        return BubbleState.AMBIGUOUS  # unreadable region: never a confident guess (R5.3 spirit)
    if score >= filled_min:
        return BubbleState.FILLED
    if score <= empty_max:
        return BubbleState.EMPTY
    return BubbleState.AMBIGUOUS


def classify_page(
    gray: np.ndarray,
    H: np.ndarray,
    template: SheetTemplate,
    num_questions: int,
    n_options: int,
    *,
    empty_max: float = DEFAULT_EMPTY_MAX,
    filled_min: float = DEFAULT_FILLED_MIN,
) -> dict[int, list[BubbleFill]]:
    """1-based question -> list of per-option `BubbleFill` (index = option)."""
    centres = bubble_centres(template, num_questions, n_options)
    diameter = template.geometry.grid.bubble_diameter_mm

    result: dict[int, list[BubbleFill]] = {}
    for question, options in centres.items():
        row = []
        for option_index, center in enumerate(options):
            score = bubble_fill_score(gray, H, center, diameter)
            state = classify_bubble_score(score, empty_max=empty_max, filled_min=filled_min)
            row.append(
                BubbleFill(
                    question=question,
                    option_index=option_index,
                    fill_score=score if score is not None else float("nan"),
                    state=state,
                )
            )
        result[question] = row
    return result


# --- R5.7 confidence gate ----------------------------------------------------


@dataclass(frozen=True)
class QuestionGateResult:
    question: int
    marked_indices: tuple[int, ...]  # 0-based option indices classified FILLED
    flagged: bool
    reason: str | None  # "ambiguous_bubble" | "no_marks" | "multiple_marks_single_answer" | None


def evaluate_question_gate(row: list[BubbleFill], *, key_size: int) -> QuestionGateResult:
    """R5.7's per-question flag rule. `key_size` = `|K|`, the number of correct
    options for this question (1 = single-answer, >1 = multi-answer). For a
    multi-answer question, any 1..N marks is gradeable (R7.2) and not itself a
    flag — only low classifier confidence (an ambiguous bubble) flags it.
    """
    if key_size < 1:
        raise ValueError(f"key_size must be >= 1, got {key_size}")
    question = row[0].question
    marked = tuple(b.option_index for b in row if b.state == BubbleState.FILLED)

    if any(b.state == BubbleState.AMBIGUOUS for b in row):
        return QuestionGateResult(question, marked, True, "ambiguous_bubble")
    if len(marked) == 0:
        return QuestionGateResult(question, marked, True, "no_marks")
    if key_size == 1 and len(marked) > 1:
        return QuestionGateResult(question, marked, True, "multiple_marks_single_answer")
    return QuestionGateResult(question, marked, False, None)


# --- Submission-level status --------------------------------------------------


class SubmissionStatus(StrEnum):
    ALIGNMENT_FAILED = "alignment_failed"
    NEEDS_REVIEW = "needs_review"
    FINALIZED = "finalized"


def evaluate_submission(
    alignment_or_error: PageAlignment | AlignmentError,
    gray: np.ndarray | None,
    template: SheetTemplate,
    key_sizes: dict[int, int],
    *,
    empty_max: float = DEFAULT_EMPTY_MAX,
    filled_min: float = DEFAULT_FILLED_MIN,
) -> tuple[SubmissionStatus, dict[int, QuestionGateResult] | None]:
    """Ties `align_page`'s result (5.3) to the per-question gate (R5.7) for a
    whole submission. `alignment_or_error` is a `PageAlignment` (5.3) on success;
    pass the caught `AlignmentError` on failure.

    Note: R5.7 names `qr_unreadable` as a status distinct from
    `alignment_failed` — not implemented here (see phase-6.md "What Phase 6
    does NOT do"): `app.omr.detect`/`alignment` don't currently distinguish
    "QR not decoded" from other `marks_not_found` causes at the exception level,
    and there is no real-corpus evidence to calibrate a split (QR decode was
    100% across the whole Phase 5 corpus). Every `AlignmentError` maps to
    `ALIGNMENT_FAILED` for now.
    """
    if isinstance(alignment_or_error, AlignmentError):
        return SubmissionStatus.ALIGNMENT_FAILED, None
    alignment = alignment_or_error

    page = classify_page(
        gray,
        alignment.H,
        template,
        alignment.num_questions,
        alignment.n_options,
        empty_max=empty_max,
        filled_min=filled_min,
    )
    results = {
        q: evaluate_question_gate(row, key_size=key_sizes.get(q, 1)) for q, row in page.items()
    }
    status = SubmissionStatus.NEEDS_REVIEW if any(r.flagged for r in results.values()) else SubmissionStatus.FINALIZED
    return status, results
