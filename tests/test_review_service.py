"""Phase 9.1 — review/grading services + pure regrade helpers."""

from __future__ import annotations

import pytest

from app.core.models import Answer, AuditEvent, Quiz, RosterEntry, Submission, Version
from app.core.review_service import (
    assign_student,
    mark_version_printed,
    override_answer,
    parse_roster,
    replace_roster,
)
from app.grading.regrade import status_after_override, submission_total

# --- pure helpers -----------------------------------------------------------

def test_submission_total_skips_none():
    assert submission_total([1.0, None, 2.5, 0.0]) == 3.5


@pytest.mark.parametrize(
    "current,any_flagged,expected",
    [
        ("needs_review", False, "finalized"),
        ("needs_review", True, "needs_review"),
        ("finalized", False, "finalized"),
        ("finalized", True, "finalized"),
        ("pending", False, "pending"),
    ],
)
def test_status_after_override(current, any_flagged, expected):
    assert status_after_override(current, any_flagged) == expected


# --- DB services ----------------------------------------------------------


@pytest.fixture
def graded(professor, make_quiz, make_version, make_submission):
    """needs_review submission, q1 answered wrong + flagged, plus a 2nd flagged answer."""
    quiz = make_quiz(professor, options_per_question=4)
    version = make_version(quiz)  # 1 question, key "A", identity option order
    sub = make_submission(version, status=Submission.Status.NEEDS_REVIEW, total_score=0.0)
    a1 = Answer.objects.create(
        submission=sub, question_no=1, detected_options=["B"], confidence=0.3,
        flagged=True, flag_reason="ambiguous", correct=False, score=0.0,
    )
    a2 = Answer.objects.create(
        submission=sub, question_no=2, detected_options=[], confidence=0.2,
        flagged=True, flag_reason="empty", correct=False, score=0.0,
    )
    return quiz, version, sub, a1, a2


@pytest.mark.django_db
def test_override_rescored_flag_cleared_status_when_last_flag_gone(graded, professor):
    quiz, version, sub, a1, a2 = graded
    # clear the second flag first so the override finalizes
    a2.flagged = False
    a2.save(update_fields=["flagged"])

    override_answer(answer=a1, professor=professor, marked_options=["a"])
    a1.refresh_from_db()
    sub.refresh_from_db()

    assert a1.detected_options == ["A"]
    assert a1.score == 1.0
    assert a1.correct is True
    assert a1.flagged is False and a1.flag_reason == ""
    assert a1.manually_edited is True and a1.edited_at is not None
    assert sub.total_score == 1.0
    assert sub.status == Submission.Status.FINALIZED

    events = AuditEvent.objects.filter(submission=sub, action="overridden")
    assert events.count() == 1
    assert events.get().detail["before"]["detected_options"] == ["B"]


@pytest.mark.django_db
def test_override_leaves_status_when_another_answer_still_flagged(graded, professor):
    quiz, version, sub, a1, a2 = graded
    override_answer(answer=a1, professor=professor, marked_options=["A"])
    sub.refresh_from_db()
    assert sub.status == Submission.Status.NEEDS_REVIEW  # a2 still flagged


@pytest.mark.django_db
def test_override_on_finalized_stays_finalized(graded, professor):
    quiz, version, sub, a1, a2 = graded
    Submission.objects.filter(pk=sub.pk).update(status=Submission.Status.FINALIZED)
    a2.flagged = False
    a2.save(update_fields=["flagged"])
    override_answer(answer=a1, professor=professor, marked_options=["A"])
    sub.refresh_from_db()
    assert sub.status == Submission.Status.FINALIZED
    assert AuditEvent.objects.filter(submission=sub, action="overridden").count() == 1


@pytest.mark.django_db
def test_assign_student_roster_then_free_text(graded, professor):
    quiz, version, sub, a1, a2 = graded
    entry = RosterEntry.objects.create(quiz=quiz, label="Ada")

    assign_student(submission=sub, professor=professor, roster_entry=entry)
    sub.refresh_from_db()
    assert sub.roster_entry_id == entry.id and sub.student_label == ""

    assign_student(submission=sub, professor=professor, label="  walk-in  ")
    sub.refresh_from_db()
    assert sub.roster_entry_id is None and sub.student_label == "walk-in"

    assert AuditEvent.objects.filter(submission=sub, action="assigned").count() == 2


def test_parse_roster_forms():
    text = "Ada\nBabbage, 42\n\n   \nHopper ,  7 \n"
    assert parse_roster(text) == [("Ada", ""), ("Babbage", "42"), ("Hopper", "7")]


def test_parse_roster_rejects_empty_label():
    with pytest.raises(ValueError, match="no name"):
        parse_roster("Ada\n, 99\n")


@pytest.mark.django_db
def test_replace_roster_replaces(professor, make_quiz):
    quiz = make_quiz(professor)
    replace_roster(quiz=quiz, professor=professor, text="A\nB\nC")
    assert quiz.roster_entries.count() == 3
    replace_roster(quiz=quiz, professor=professor, text="X, 1\nY, 2")
    labels = sorted(quiz.roster_entries.values_list("label", flat=True))
    assert labels == ["X", "Y"]
    assert quiz.roster_entries.get(label="X").external_id == "1"


@pytest.mark.django_db
def test_mark_version_printed_flips_quiz_and_is_idempotent(professor, make_quiz, make_version):
    quiz = make_quiz(professor, status=Quiz.Status.VERSIONED)
    v1 = make_version(quiz, version_number=1)
    v2 = Version.objects.create(
        quiz=quiz, version_number=2, question_order=v1.question_order,
        option_order=v1.option_order, template_version=2,
    )

    mark_version_printed(version=v1, professor=professor)
    v1.refresh_from_db()
    quiz.refresh_from_db()
    assert v1.printed_at is not None
    assert quiz.status == Quiz.Status.PRINTED
    assert AuditEvent.objects.filter(action="printed").count() == 1

    mark_version_printed(version=v1, professor=professor)  # idempotent
    assert AuditEvent.objects.filter(action="printed").count() == 1

    mark_version_printed(version=v2, professor=professor)
    v2.refresh_from_db()
    assert v2.printed_at is not None
    assert AuditEvent.objects.filter(action="printed").count() == 2
