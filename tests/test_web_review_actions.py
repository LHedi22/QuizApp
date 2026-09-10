"""Phase 9.3 — override + student-assignment endpoints (R6.3 / R6.4)."""

from __future__ import annotations

import pytest
from django.urls import reverse

from app.core.models import Answer, AuditEvent, Question, RosterEntry, Submission, Version

pytestmark = pytest.mark.django_db


@pytest.fixture
def client_a(client, professor):
    client.force_login(professor)
    return client


@pytest.fixture
def setup(professor, make_quiz, make_submission):
    quiz = make_quiz(professor, options_per_question=4)
    q1 = Question.objects.create(quiz=quiz, order_index=1, text="Q1",
                                 options=["a", "b", "c", "d"], correct_options=["A"])
    version = Version.objects.create(
        quiz=quiz, version_number=1, question_order=[q1.id],
        option_order={str(q1.id): [0, 1, 2, 3]}, template_version=2,
    )
    sub = make_submission(version, status=Submission.Status.NEEDS_REVIEW, total_score=0.0)
    ans = Answer.objects.create(
        submission=sub, question_no=1, detected_options=["C"], confidence=0.3,
        flagged=True, flag_reason="ambiguous", correct=False, score=0.0,
    )
    return quiz, version, sub, ans


def test_override_corrects_answer_and_finalizes(client_a, setup):
    quiz, version, sub, ans = setup
    resp = client_a.post(reverse("answer_override", args=[ans.pk]), {"marked_options": ["A"]})
    assert resp.status_code == 302
    ans.refresh_from_db()
    sub.refresh_from_db()
    assert ans.detected_options == ["A"] and ans.score == 1.0 and ans.flagged is False
    assert sub.total_score == 1.0 and sub.status == Submission.Status.FINALIZED

    body = client_a.get(reverse("submission_detail", args=[sub.pk])).content.decode()
    assert "Overridden" in body


def test_override_on_finalized_stays_finalized(client_a, setup):
    quiz, version, sub, ans = setup
    Submission.objects.filter(pk=sub.pk).update(status=Submission.Status.FINALIZED)
    client_a.post(reverse("answer_override", args=[ans.pk]), {"marked_options": ["A"]})
    sub.refresh_from_db()
    assert sub.status == Submission.Status.FINALIZED


def test_assignment_roster_then_free_text_shows_in_results(client_a, setup, professor):
    quiz, version, sub, ans = setup
    entry = RosterEntry.objects.create(quiz=quiz, label="Ada Lovelace")

    client_a.post(reverse("submission_assign", args=[sub.pk]), {"roster_entry": entry.pk})
    sub.refresh_from_db()
    assert sub.roster_entry_id == entry.pk

    client_a.post(reverse("submission_assign", args=[sub.pk]), {"student_label": "walk-in"})
    sub.refresh_from_db()
    assert sub.roster_entry_id is None and sub.student_label == "walk-in"

    results = client_a.get(reverse("quiz_results", args=[quiz.pk])).content.decode()
    assert "walk-in" in results
    assert AuditEvent.objects.filter(submission=sub, action="assigned").count() == 2


def test_assignment_both_or_neither_is_rejected(client_a, setup):
    quiz, version, sub, ans = setup
    entry = RosterEntry.objects.create(quiz=quiz, label="Ada")

    client_a.post(reverse("submission_assign", args=[sub.pk]),
                  {"roster_entry": entry.pk, "student_label": "x"})
    sub.refresh_from_db()
    assert sub.roster_entry_id is None and sub.student_label == ""

    client_a.post(reverse("submission_assign", args=[sub.pk]), {})
    sub.refresh_from_db()
    assert sub.roster_entry_id is None and sub.student_label == ""
    assert not AuditEvent.objects.filter(submission=sub, action="assigned").exists()


def test_foreign_answer_and_submission_404(client, professor, other_professor, setup):
    quiz, version, sub, ans = setup
    client.force_login(other_professor)
    assert client.post(reverse("answer_override", args=[ans.pk]), {"marked_options": ["A"]}).status_code == 404
    assert client.post(reverse("submission_assign", args=[sub.pk]), {"student_label": "x"}).status_code == 404
