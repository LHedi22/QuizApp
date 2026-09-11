"""Phase 7.1 DoD — scan intake orchestrator, integration-tested against the real
Phase 0.7 corpus end-to-end (CLAUDE.md rule 9: the pipeline this exercises is
built entirely from the already-corpus-validated Phase 5/6 functions, so this
suite validates DB *persistence/scoring wiring*, not a new OMR-accuracy claim).

Fixture note (see docs/phases/phase-7.md): the corpus sheets were rendered
directly by scripts/make_corpus_sheets.py with sequential, unshuffled
question_order/option_order (no real quiz/versioning pipeline behind them). Test
fixtures reproduce that exactly (`Version.qr_id` = the real corpus sheet_token,
identity ordering) so `align_page`'s QR decode resolves to a real DB `Version`.
`correct_options` assigned to the fixture questions are **arbitrary** (there is
no real exam behind these practice sheets) — used only to exercise scoring
mechanics, not as a grading-accuracy claim.
"""
from __future__ import annotations

import uuid

import pytest

from app.core.models import Answer, AuditEvent, Question, Submission, Version
from app.core.scan_pipeline import find_probable_duplicate, process_batch, process_submission_image
from app.grading.scoring import score_question
from tests.conftest import load_corpus_cases

_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

CORPUS_CASES = load_corpus_cases()


@pytest.fixture
def make_corpus_version(db, make_quiz, professor):
    """Build a real Quiz/Question(xN)/Version whose geometry + qr_id exactly
    match one corpus source sheet (see module docstring). Arbitrary but valid
    `correct_options`, cycling through the available letters."""

    def _make(meta: dict) -> Version:
        n_options = meta["options"]
        quiz = make_quiz(professor, options_per_question=n_options)
        questions = []
        for i in range(1, meta["questions"] + 1):
            correct_letter = _LETTERS[(i - 1) % n_options]
            q = Question.objects.create(
                quiz=quiz,
                order_index=i,
                text=f"Q{i}",
                options=[f"opt {_LETTERS[j]}" for j in range(n_options)],
                correct_options=[correct_letter],
            )
            questions.append(q)
        return Version.objects.create(
            quiz=quiz,
            version_number=1,
            qr_id=uuid.UUID(meta["sheet_token"]),
            question_order=[q.id for q in questions],
            option_order={str(q.id): list(range(n_options)) for q in questions},
            template_version=meta["template_version"],
        )

    return _make


@pytest.fixture
def corpus_versions_by_token(make_corpus_version):
    """One fixture Version per distinct corpus source sheet (created lazily,
    cached across the whole test run)."""
    cache: dict[str, Version] = {}

    def _get(sheet_token: str, meta: dict) -> Version:
        if sheet_token not in cache:
            cache[sheet_token] = make_corpus_version(meta)
        return cache[sheet_token]

    return _get


# --- structural / synthetic-input tests (no real image needed) --------------


@pytest.mark.django_db
def test_process_submission_image_on_unreadable_bytes_fails_cleanly(make_quiz, professor, make_version):
    quiz = make_quiz(professor)
    version = make_version(quiz)
    submission = process_submission_image(
        version=version, image_bytes=b"not an image", source=Submission.Source.PHOTO
    )
    assert submission.status == Submission.Status.FAILED
    assert submission.failure_reason == Submission.FailureReason.ALIGNMENT_FAILED
    assert submission.answers.count() == 0
    assert submission.total_score is None


@pytest.mark.django_db
def test_process_submission_image_on_blank_image_fails_cleanly_no_answers(make_quiz, professor, make_version):
    import cv2
    import numpy as np

    quiz = make_quiz(professor)
    version = make_version(quiz)
    blank = np.full((800, 600, 3), 255, dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", blank)
    assert ok
    submission = process_submission_image(version=version, image_bytes=buf.tobytes(), source=Submission.Source.PHOTO)
    assert submission.status == Submission.Status.FAILED
    assert submission.failure_reason == Submission.FailureReason.ALIGNMENT_FAILED
    assert Answer.objects.filter(submission=submission).count() == 0


@pytest.mark.django_db
def test_process_batch_continues_past_a_failed_page(make_quiz, professor, make_version):
    quiz = make_quiz(professor)
    version = make_version(quiz)
    results = process_batch(
        version=version,
        pages=[(b"garbage-1", 1), (b"garbage-2", 2)],
        source=Submission.Source.BATCH_PDF,
    )
    assert len(results) == 2
    assert all(s.status == Submission.Status.FAILED for s in results)
    assert results[0].batch_id == results[1].batch_id
    assert [s.page_number for s in results] == [1, 2]


# --- real corpus DoD (rule 9) -------------------------------------------------


@pytest.mark.skipif(not CORPUS_CASES, reason="corpus/images has no labeled real captures")
@pytest.mark.django_db
@pytest.mark.parametrize("image_path,label,meta", CORPUS_CASES, ids=[c[0].stem for c in CORPUS_CASES])
def test_process_submission_image_on_real_corpus_capture(image_path, label, meta, corpus_versions_by_token):
    version = corpus_versions_by_token(label["sheet_token"], meta)
    image_bytes = image_path.read_bytes()

    submission = process_submission_image(version=version, image_bytes=image_bytes, source=Submission.Source.PHOTO)

    assert submission.status in (Submission.Status.FINALIZED, Submission.Status.NEEDS_REVIEW)
    assert submission.failure_reason == ""
    answers = list(Answer.objects.filter(submission=submission).order_by("question_no"))
    assert len(answers) == meta["questions"]
    assert submission.answer_hash != ""

    # cross-check detected_options against the (corrected) real-corpus label —
    # the same accuracy signal Phase 6 already established, now verified through
    # the full persisted DB path rather than the in-memory app.omr call directly
    mismatches = 0
    for a in answers:
        expected = set(label["marked_options"].get(str(a.question_no), []))
        if set(a.detected_options) != expected:
            mismatches += 1
    assert mismatches <= 2, f"{mismatches}/{len(answers)} answers mismatched the label on {image_path.name}"

    # a finalized submission's total must equal the sum of its (all non-flagged,
    # by definition) answer scores; a needs_review one withholds it (R7.4)
    if submission.status == Submission.Status.FINALIZED:
        assert all(not a.flagged and a.score is not None for a in answers)
        assert submission.total_score == pytest.approx(sum(a.score for a in answers))
    else:
        assert submission.total_score is None
        assert any(a.flagged for a in answers)

    # R7.5 parity: the pipeline's score for a non-flagged answer must equal an
    # independent score_question call for the same inputs
    quiz = version.quiz
    for a in answers:
        if a.flagged:
            continue
        question = Question.objects.get(quiz=quiz, order_index=a.question_no)
        from app.core.versioning_service import recover_correct_letters

        key = recover_correct_letters(version, question)
        points = question.points if question.points is not None else quiz.default_points
        expected_score = score_question(
            a.detected_options, key, points, quiz.marking_mode, quiz.negative_marking
        )
        assert a.score == pytest.approx(expected_score)

    audit = AuditEvent.objects.filter(submission=submission, action=AuditEvent.Action.SCORED).first()
    assert audit is not None
    assert audit.actor_professor_id is None  # system action


@pytest.mark.django_db
def test_find_probable_duplicate_detects_a_resubmitted_real_capture(corpus_versions_by_token):
    if not CORPUS_CASES:
        pytest.skip("corpus/images has no labeled real captures")
    image_path, label, meta = CORPUS_CASES[0]
    version = corpus_versions_by_token(label["sheet_token"], meta)
    image_bytes = image_path.read_bytes()

    first = process_submission_image(version=version, image_bytes=image_bytes, source=Submission.Source.PHOTO)
    second = process_submission_image(version=version, image_bytes=image_bytes, source=Submission.Source.PHOTO)

    assert first.answer_hash == second.answer_hash
    dup = find_probable_duplicate(second)
    assert dup is not None and dup.pk == first.pk
    # never auto-set — professor-confirmed only (Appendix A)
    assert second.duplicate_of_id is None
