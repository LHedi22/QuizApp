"""Phase 9.2 — submission detail view (R6.2) + audit history (R6.5)."""

from __future__ import annotations

import pytest
from django.urls import reverse

from app.core.models import Answer, AuditEvent, Question, Submission, Version

pytestmark = pytest.mark.django_db


@pytest.fixture
def client_a(client, professor):
    client.force_login(professor)
    return client


@pytest.fixture
def sub5(professor, make_quiz, make_submission):
    quiz = make_quiz(professor, options_per_question=4)
    qs = [
        Question.objects.create(
            quiz=quiz, order_index=i, text=f"Q{i}",
            options=["a", "b", "c", "d"], correct_options=["A"],
        )
        for i in range(1, 6)
    ]
    version = Version.objects.create(
        quiz=quiz, version_number=1,
        question_order=[q.id for q in qs],
        option_order={str(q.id): [0, 1, 2, 3] for q in qs},
        template_version=2,
    )
    sub = make_submission(version, status=Submission.Status.NEEDS_REVIEW, total_score=2.0)
    for i in range(1, 6):
        Answer.objects.create(
            submission=sub, question_no=i,
            detected_options=["A"] if i % 2 else ["B"],
            confidence=0.9 if i % 2 else 0.35,
            flagged=i in (3, 5), flag_reason="ambiguous" if i in (3, 5) else "",
            correct=bool(i % 2), score=1.0 if i % 2 else 0.0,
            manually_edited=(i == 1),
        )
    # created in order → e2 (Overridden) has the later auto_now_add timestamp
    AuditEvent.objects.create(quiz=quiz, submission=sub, actor_professor=professor,
                              action=AuditEvent.Action.SCORED, detail={"n": 1})
    AuditEvent.objects.create(quiz=quiz, submission=sub, actor_professor=professor,
                              action=AuditEvent.Action.OVERRIDDEN, detail={"n": 2})
    return quiz, sub


def test_answer_sheet_renders_flagged_first_and_edited_marker(client_a, sub5):
    quiz, sub = sub5
    body = client_a.get(reverse("submission_detail", args=[sub.pk])).content.decode()
    # all five question rows, with the question text shown alongside the number
    for i in range(1, 6):
        assert f"Q{i}: Q{i}" in body
    # both flagged rows appear before the first unflagged data row
    first_flag = body.index("flag:")
    # unflagged questions are 1,2,4 — "edited" marker is on q1 which is unflagged
    assert first_flag < body.index("edited")
    assert "ambiguous" in body


def test_history_newest_first_and_no_audit_on_view(client_a, sub5):
    quiz, sub = sub5
    before = AuditEvent.objects.count()
    body = client_a.get(reverse("submission_detail", args=[sub.pk])).content.decode()
    assert AuditEvent.objects.count() == before  # passive view not logged (R6.5)
    assert body.index("Overridden") < body.index("Scored")  # newest first


def test_foreign_and_missing_404(client, professor, other_professor, sub5):
    quiz, sub = sub5
    client.force_login(other_professor)
    assert client.get(reverse("submission_detail", args=[sub.pk])).status_code == 404
    assert client.get(reverse("submission_detail", args=[999999])).status_code == 404


def test_answer_sheet_shows_option_text_for_this_versions_shuffle(client_a, professor, make_quiz, make_submission):
    """R2.1/R2.3: sheet letters mean different options per version. The review
    page must show the actual option text next to the letter, mapped through
    THIS version's option_order — not a bare A/B/C/D a professor would have to
    cross-reference the printed question paper to decode."""
    quiz = make_quiz(professor, options_per_question=4)
    # canonical option 0=Paris (wrong), 1=London (correct_options=["B"])
    question = Question.objects.create(
        quiz=quiz, order_index=1, text="Capital of France?",
        options=["Paris", "London", "Berlin", "Madrid"], correct_options=["B"],
    )
    # sheet position 0(A)->canonical idx1(London), 1(B)->idx3(Madrid),
    # 2(C)->idx0(Paris), 3(D)->idx2(Berlin). So the canonical-correct option
    # (London, idx1) actually sits at sheet letter A, not B.
    version = Version.objects.create(
        quiz=quiz, version_number=1, question_order=[question.id],
        option_order={str(question.id): [1, 3, 0, 2]}, template_version=2,
    )
    sub = make_submission(version, status=Submission.Status.NEEDS_REVIEW, total_score=None)
    Answer.objects.create(
        submission=sub, question_no=1, detected_options=["C"], confidence=1.0,
        flagged=False, correct=False, score=0.0,
    )

    body = client_a.get(reverse("submission_detail", args=[sub.pk])).content.decode()
    assert "C: Paris" in body  # what the student marked (sheet letter C)
    assert "A: London" in body  # the actual correct key (sheet letter A) -- not "B"


def test_unauthenticated_redirects(client, sub5):
    quiz, sub = sub5
    resp = client.get(reverse("submission_detail", args=[sub.pk]))
    assert resp.status_code == 302
    assert "/accounts/login/" in resp.url
