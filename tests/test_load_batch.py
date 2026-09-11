"""Phase 11.3 DoD — a small, fast version of `scripts/load_test.py`'s
scenario as a real pytest check: batch throughput + correctness through
`process_batch`, the same orchestrator the real batch-upload view calls.
The full class-scale run (60 sheets/5 versions/100 questions) lives in
`scripts/load_test.py` since it's a multi-minute timed benchmark, not a fast
CI gate.
"""

from __future__ import annotations

import time

import pytest

from app.core.models import Question, Submission
from app.core.scan_pipeline import process_batch
from app.core.versioning_service import generate_versions_for_quiz, recover_correct_letters
from tests.conftest import render_filled_submission_image

pytestmark = pytest.mark.django_db

NUM_QUESTIONS = 20
N_OPTIONS = 4
NUM_VERSIONS = 2
SHEETS_PER_VERSION = 5
TIME_BOUND_SECONDS_PER_SHEET = 5.0


def test_small_batch_finalizes_correctly_within_time_bound(professor, make_quiz, make_xlsx, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    quiz = make_quiz(professor, options_per_question=N_OPTIONS)
    rows = [["question_text", "option_1", "option_2", "option_3", "option_4", "correct_options", "points"]]
    for i in range(1, NUM_QUESTIONS + 1):
        rows.append([f"Q{i}", "alpha", "beta", "gamma", "delta", "A", ""])
    from app.core.ingest import ingest_quiz

    result = ingest_quiz(quiz, make_xlsx(rows))
    assert result.ok

    versions = generate_versions_for_quiz(quiz, NUM_VERSIONS, seed=3)
    questions = list(Question.objects.filter(quiz=quiz).order_by("order_index"))

    all_submissions: list[Submission] = []
    start = time.perf_counter()
    for version in versions:
        fill_pattern = {}
        for q in questions:
            pos = version.question_order.index(q.id) + 1
            letters = recover_correct_letters(version, q)
            fill_pattern[pos] = {ord(letter) - ord("A") for letter in letters}
        image_bytes = render_filled_submission_image(version, fill_pattern)
        pages = [(image_bytes, n) for n in range(1, SHEETS_PER_VERSION + 1)]
        all_submissions.extend(
            process_batch(version=version, pages=pages, source=Submission.Source.BATCH_PDF)
        )
    elapsed = time.perf_counter() - start

    n_sheets = NUM_VERSIONS * SHEETS_PER_VERSION
    assert len(all_submissions) == n_sheets
    assert all(s.status == Submission.Status.FINALIZED for s in all_submissions)
    assert all(s.total_score == NUM_QUESTIONS for s in all_submissions)

    per_sheet = elapsed / n_sheets
    assert per_sheet <= TIME_BOUND_SECONDS_PER_SHEET, (
        f"per-sheet average {per_sheet:.3f}s exceeds the {TIME_BOUND_SECONDS_PER_SHEET}s bound"
    )
