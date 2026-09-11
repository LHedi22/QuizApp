"""Phase 11.3 — class-scale load test (REBUILD_SPEC §5 Phase 11).

Builds a 100-question, N=4 quiz, generates 5 versions, and runs 60
rendered-and-filled submissions (12 per version, all-correct) through
`process_batch` — the same orchestrator the real batch-upload view calls.
Reports wall time, per-sheet average, and peak Python-level memory
(`tracemalloc` — no `resource`/`psutil` dependency exists in this repo, and
Windows dev lacks `resource`).

Not part of `pytest -q` — this is a timed benchmark, not a correctness gate.
`tests/test_load_batch.py` runs a smaller version of the same scenario as a
real, fast pytest DoD check.

    DATABASE_URL=... SECRET_KEY=... python scripts/load_test.py
"""

from __future__ import annotations

import os
import sys
import time
import tracemalloc
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings")

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402

from app.core.ingest import ingest_quiz  # noqa: E402
from app.core.models import Question, Submission  # noqa: E402
from app.core.scan_pipeline import process_batch  # noqa: E402
from app.core.services import create_quiz  # noqa: E402
from app.core.versioning_service import generate_versions_for_quiz, recover_correct_letters  # noqa: E402
from tests.conftest import render_filled_submission_image  # noqa: E402

LOAD_EMAIL = "load-test@example.com"  # noqa: S105
NUM_QUESTIONS = 100
N_OPTIONS = 4
NUM_VERSIONS = 5
SHEETS_PER_VERSION = 12  # 5 * 12 = 60 total, matching the spec's "60 sheets"
TIME_BOUND_SECONDS_PER_SHEET = 5.0  # written bound (see docs/phases/phase-11.md)


def _build_xlsx(n: int) -> bytes:
    from io import BytesIO

    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["question_text", "option_1", "option_2", "option_3", "option_4", "correct_options", "points"])
    for i in range(1, n + 1):
        ws.append([f"Load-test question {i}", "alpha", "beta", "gamma", "delta", "A", ""])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def main() -> None:
    user_model = get_user_model()
    professor, _ = user_model.objects.get_or_create(email=LOAD_EMAIL)
    professor.set_password("load-test-pass-12345")  # noqa: S106
    professor.save()
    professor.quizzes.all().delete()

    quiz = create_quiz(professor=professor, title="Load Test Quiz", options_per_question=N_OPTIONS)
    result = ingest_quiz(quiz, _build_xlsx(NUM_QUESTIONS))
    if not result.ok:
        raise SystemExit(f"load_test: ingest failed: {result}")

    versions = generate_versions_for_quiz(quiz, NUM_VERSIONS, seed=7)
    questions = list(Question.objects.filter(quiz=quiz).order_by("order_index"))

    print(f"Rendering {NUM_VERSIONS * SHEETS_PER_VERSION} filled submission images...")
    render_start = time.perf_counter()
    pages_by_version = []
    for version in versions:
        fill_pattern = {}
        for q in questions:
            pos = version.question_order.index(q.id) + 1
            letters = recover_correct_letters(version, q)
            fill_pattern[pos] = {ord(letter) - ord("A") for letter in letters}
        image_bytes = render_filled_submission_image(version, fill_pattern)
        pages_by_version.append((version, image_bytes))
    render_elapsed = time.perf_counter() - render_start
    print(f"  render done in {render_elapsed:.1f}s")

    tracemalloc.start()
    total_start = time.perf_counter()
    all_submissions: list[Submission] = []
    for version, image_bytes in pages_by_version:
        pages = [(image_bytes, n) for n in range(1, SHEETS_PER_VERSION + 1)]
        submissions = process_batch(version=version, pages=pages, source=Submission.Source.BATCH_PDF)
        all_submissions.extend(submissions)
    total_elapsed = time.perf_counter() - total_start
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    n_sheets = len(all_submissions)
    per_sheet = total_elapsed / n_sheets
    n_finalized = sum(1 for s in all_submissions if s.status == Submission.Status.FINALIZED)
    n_correct = sum(
        1 for s in all_submissions
        if s.status == Submission.Status.FINALIZED and s.total_score == NUM_QUESTIONS
    )

    print()
    print(f"sheets scanned:      {n_sheets}")
    print(f"finalized:           {n_finalized}/{n_sheets}")
    print(f"correct (all-{NUM_QUESTIONS}):   {n_correct}/{n_sheets}")
    print(f"total wall time:     {total_elapsed:.2f}s")
    print(f"per-sheet average:   {per_sheet:.3f}s (bound: {TIME_BOUND_SECONDS_PER_SHEET}s)")
    print(f"peak traced memory:  {peak_bytes / 1e6:.1f} MB")

    ok = True
    if per_sheet > TIME_BOUND_SECONDS_PER_SHEET:
        print(f"FAIL: per-sheet average {per_sheet:.3f}s exceeds the {TIME_BOUND_SECONDS_PER_SHEET}s bound")
        ok = False
    if n_finalized != n_sheets:
        print(f"FAIL: {n_sheets - n_finalized} submission(s) did not finalize")
        ok = False
    if n_correct != n_sheets:
        print(f"FAIL: {n_sheets - n_correct} submission(s) scored incorrectly")
        ok = False

    if not ok:
        raise SystemExit(1)
    print("PASS")


if __name__ == "__main__":
    main()
