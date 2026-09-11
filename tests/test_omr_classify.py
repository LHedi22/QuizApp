"""Phase 6 DoD — bubble classifier + confidence gate.

Three kinds of evidence, per docs/phases/phase-6.md:
1. Pure/structural tests of the R5.7 gate rules (synthetic BubbleFill rows).
2. A synthetic "clean scan" (no camera noise/perspective) for R5.5's held-out
   >=99% accuracy figure -- design principle 2: synthetic is a supplement, but
   the right tool for this specific idealized-conditions metric.
3. The real Phase 0.7 corpus (CLAUDE.md rule 9) for real-photo bubble accuracy
   and the R5.5 per-submission finalize-rate metric.
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.omr.alignment import VersionGeometry, align_page
from app.omr.classify import (
    BubbleFill,
    BubbleState,
    SubmissionStatus,
    classify_bubble_score,
    classify_page,
    evaluate_question_gate,
    evaluate_submission,
)
from app.omr.geometry import AlignmentError, homography_dlt
from app.sheet_template import bubble_centres, load_template

TEMPLATE = load_template()
CORPUS_ROOT = Path(__file__).resolve().parent.parent / "corpus"
_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


# --- R5.7 gate rules — pure, structural --------------------------------------


def _row(question: int, states: list[BubbleState]) -> list[BubbleFill]:
    return [
        BubbleFill(question=question, option_index=i, fill_score=0.0, state=s)
        for i, s in enumerate(states)
    ]


def test_gate_flags_zero_marks_regardless_of_key_size():
    row = _row(1, [BubbleState.EMPTY, BubbleState.EMPTY, BubbleState.EMPTY, BubbleState.EMPTY])
    for key_size in (1, 2, 3):
        result = evaluate_question_gate(row, key_size=key_size)
        assert result.flagged and result.reason == "no_marks"


def test_gate_flags_multiple_marks_on_single_answer_question():
    row = _row(1, [BubbleState.FILLED, BubbleState.FILLED, BubbleState.EMPTY, BubbleState.EMPTY])
    result = evaluate_question_gate(row, key_size=1)
    assert result.flagged and result.reason == "multiple_marks_single_answer"


def test_gate_does_not_flag_multiple_marks_on_multi_answer_question():
    row = _row(1, [BubbleState.FILLED, BubbleState.FILLED, BubbleState.EMPTY, BubbleState.EMPTY])
    result = evaluate_question_gate(row, key_size=2)
    assert not result.flagged and result.marked_indices == (0, 1)


def test_gate_flags_any_ambiguous_bubble_regardless_of_marks():
    row = _row(1, [BubbleState.FILLED, BubbleState.AMBIGUOUS, BubbleState.EMPTY, BubbleState.EMPTY])
    result = evaluate_question_gate(row, key_size=1)
    assert result.flagged and result.reason == "ambiguous_bubble"


def test_gate_does_not_flag_a_clean_single_mark():
    row = _row(1, [BubbleState.EMPTY, BubbleState.FILLED, BubbleState.EMPTY, BubbleState.EMPTY])
    result = evaluate_question_gate(row, key_size=1)
    assert not result.flagged and result.reason is None and result.marked_indices == (1,)


def test_gate_rejects_invalid_key_size():
    row = _row(1, [BubbleState.EMPTY])
    with pytest.raises(ValueError):
        evaluate_question_gate(row, key_size=0)


def test_classify_bubble_score_none_is_ambiguous():
    assert classify_bubble_score(None) == BubbleState.AMBIGUOUS


def test_evaluate_submission_maps_alignment_error_to_alignment_failed():
    status, results = evaluate_submission(
        AlignmentError("marks_not_found"), None, TEMPLATE, key_sizes={}
    )
    assert status == SubmissionStatus.ALIGNMENT_FAILED
    assert results is None


# --- synthetic clean-scan accuracy (R5.5 held-out metric) --------------------


def _render_clean_synthetic(num_questions: int, n_options: int, fill_pattern: dict, *, scale: float = 8.0):
    """A no-perspective, no-camera-noise synthetic 'scan': hollow circles for
    every bubble, solid filled discs for `fill_pattern` (question -> option_index
    marked). Returns (gray, H)."""
    w_px = int(TEMPLATE.page_width_mm * scale)
    h_px = int(TEMPLATE.page_height_mm * scale)
    img = np.full((h_px, w_px), 255, dtype=np.uint8)

    w_mm, h_mm = TEMPLATE.page_width_mm, TEMPLATE.page_height_mm
    corners_mm = np.array([[0, 0], [w_mm, 0], [w_mm, h_mm], [0, h_mm]])
    corners_px = corners_mm * scale
    H = homography_dlt(corners_mm, corners_px)

    centres = bubble_centres(TEMPLATE, num_questions, n_options)
    radius_px = int(TEMPLATE.geometry.grid.bubble_diameter_mm / 2 * scale)
    for q, opts in centres.items():
        marked = fill_pattern.get(q, set())
        for opt_idx, (cx_mm, cy_mm) in enumerate(opts):
            cx, cy = int(cx_mm * scale), int(cy_mm * scale)
            cv2.circle(img, (cx, cy), radius_px, 0, thickness=max(1, int(scale * 0.12)))
            if opt_idx in marked:
                cv2.circle(img, (cx, cy), int(radius_px * 0.8), 0, thickness=-1)
    return img, H


def test_synthetic_clean_scan_classification_is_at_least_99_percent_accurate():
    num_questions, n_options = 40, 4
    rng = np.random.default_rng(42)
    fill_pattern = {q: {int(rng.integers(0, n_options))} for q in range(1, num_questions + 1)}
    gray, H = _render_clean_synthetic(num_questions, n_options, fill_pattern)

    page = classify_page(gray, H, TEMPLATE, num_questions, n_options)
    total = correct = ambiguous = 0
    for q, row in page.items():
        marked = fill_pattern.get(q, set())
        for bubble in row:
            total += 1
            expected = BubbleState.FILLED if bubble.option_index in marked else BubbleState.EMPTY
            if bubble.state == BubbleState.AMBIGUOUS:
                ambiguous += 1
            elif bubble.state == expected:
                correct += 1
    accuracy = correct / total
    assert ambiguous == 0, f"{ambiguous}/{total} bubbles ambiguous on a clean synthetic scan"
    assert accuracy >= 0.99, f"clean-scan accuracy {accuracy:.4f} below the R5.5 held-out bar"


def test_synthetic_clean_scan_multiple_random_patterns():
    """Several sheets/patterns, not just one lucky draw."""
    total = correct = 0
    for seed in range(5):
        num_questions, n_options = 30, 5
        rng = np.random.default_rng(seed)
        fill_pattern = {q: {int(rng.integers(0, n_options))} for q in range(1, num_questions + 1)}
        gray, H = _render_clean_synthetic(num_questions, n_options, fill_pattern)
        page = classify_page(gray, H, TEMPLATE, num_questions, n_options)
        for q, row in page.items():
            marked = fill_pattern.get(q, set())
            for bubble in row:
                total += 1
                expected = BubbleState.FILLED if bubble.option_index in marked else BubbleState.EMPTY
                if bubble.state == expected:
                    correct += 1
    assert correct / total >= 0.99


# --- real corpus DoD (rule 9) -------------------------------------------------


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


def test_real_corpus_bubble_classification_accuracy_and_finalize_rate():
    """The Phase 6 headline numbers (R5.5), measured honestly against the real
    20-photo corpus -- reported here, not asserted to be perfect. See
    docs/PROGRESS.md phase-6 entry for the numbers and their narrow-corpus
    caveat (same pattern as Phase 5.5).
    """
    if not CORPUS_CASES:
        pytest.skip("corpus/images has no labeled real captures")

    total_bubbles = correct_bubbles = ambiguous_bubbles = 0
    n_finalized = 0
    n_submissions = 0

    for image_path, label, _meta in CORPUS_CASES:
        image = cv2.imread(str(image_path))
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        alignment = align_page(image, TEMPLATE, version_lookup=_corpus_version_lookup)
        page = classify_page(gray, alignment.H, TEMPLATE, alignment.num_questions, alignment.n_options)

        # bubble-level accuracy against the (corrected) real-corpus labels
        for q_str, marked_letters in label["marked_options"].items():
            q = int(q_str)
            marked_idx = {_LETTERS.index(letter) for letter in marked_letters}
            for bubble in page[q]:
                total_bubbles += 1
                if bubble.state == BubbleState.AMBIGUOUS:
                    ambiguous_bubbles += 1
                    continue
                expected = BubbleState.FILLED if bubble.option_index in marked_idx else BubbleState.EMPTY
                if bubble.state == expected:
                    correct_bubbles += 1

        # submission-level finalize rate (R5.5) -- key_size=1 assumed for every
        # question (documented in phase-6.md: these are Phase-0 technical test
        # sheets with no real ingested question bank / |K| behind them)
        n_submissions += 1
        status, _results = evaluate_submission(
            alignment, gray, TEMPLATE, key_sizes={},
        )
        if status == SubmissionStatus.FINALIZED:
            n_finalized += 1

    accuracy = correct_bubbles / total_bubbles
    finalize_rate = n_finalized / n_submissions
    print(
        f"\nPhase 6 real-corpus metrics: bubble accuracy={accuracy:.4f} "
        f"({correct_bubbles}/{total_bubbles}, {ambiguous_bubbles} ambiguous), "
        f"finalize_rate={finalize_rate:.2f} ({n_finalized}/{n_submissions})"
    )
    # generous bar -- this is a real measurement, not a target being gamed; see
    # docs/PROGRESS.md for the actual observed numbers and their discussion
    assert accuracy >= 0.98, f"real-corpus bubble accuracy {accuracy:.4f} unexpectedly low"
