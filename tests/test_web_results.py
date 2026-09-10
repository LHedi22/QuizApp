"""Phase 8.5 — per-quiz results list (R6.1), end-to-end via the test client.

Submissions are hand-built fixtures — the real scan pipeline is Phases 5–7
(user-approved 2026-09-10).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from django.urls import reverse

from app.core.models import Answer, RosterEntry, Submission

pytestmark = pytest.mark.django_db


@pytest.fixture
def client_a(client, professor):
    client.force_login(professor)
    return client


@pytest.fixture
def results_quiz(professor, make_quiz, make_version, make_submission):
    quiz = make_quiz(professor, options_per_question=4)
    version = make_version(quiz)

    def at(sub, y, mo, d):
        Submission.objects.filter(pk=sub.pk).update(created_at=datetime(y, mo, d, tzinfo=UTC))

    roster = RosterEntry.objects.create(quiz=quiz, label="Ada Lovelace")

    s1 = make_submission(version, status=Submission.Status.FINALIZED, total_score=8.0,
                         roster_entry=roster)
    at(s1, 2026, 1, 10)
    s2 = make_submission(version, status=Submission.Status.NEEDS_REVIEW, total_score=3.0,
                         student_label="unmatched sheet")
    at(s2, 2026, 1, 20)
    s3 = make_submission(version, status=Submission.Status.FINALIZED, total_score=10.0)
    at(s3, 2026, 1, 5)
    s4 = make_submission(version, status=Submission.Status.FAILED,
                         failure_reason=Submission.FailureReason.QR_UNREADABLE)
    at(s4, 2026, 1, 25)

    Answer.objects.create(submission=s2, question_no=1, detected_options=["A", "B"],
                          confidence=0.4, flagged=True, flag_reason="ambiguous_multi")
    return quiz


def _get(client, quiz, **params):
    return client.get(reverse("quiz_results", args=[quiz.pk]), params)


def test_lists_all_submissions_newest_capture_first(client_a, results_quiz):
    body = _get(client_a, results_quiz).content.decode()
    assert body.count("2026-01-") == 4
    # default sort -captured → Jan 25 row before Jan 5 row
    assert body.index("2026-01-25") < body.index("2026-01-05")


def test_status_filter(client_a, results_quiz):
    body = _get(client_a, results_quiz, status="needs_review").content.decode()
    assert "2026-01-20" in body
    assert "2026-01-10" not in body
    assert body.count("2026-01-") == 1


def test_sort_by_score(client_a, results_quiz):
    body = _get(client_a, results_quiz, sort="-score").content.decode()
    # highest score (10.0, Jan 5) first; failed (no score) sorts last on desc
    assert body.index("2026-01-05") < body.index("2026-01-10") < body.index("2026-01-20")

    body = _get(client_a, results_quiz, sort="captured").content.decode()
    assert body.index("2026-01-05") < body.index("2026-01-25")


def test_flag_and_student_columns(client_a, results_quiz):
    body = _get(client_a, results_quiz).content.decode()
    assert "Ada Lovelace" in body
    assert "unmatched sheet" in body
    assert "ambiguous_multi" in body          # flagged answer reason
    assert "Qr Unreadable" in body  # failure reason (get_failure_reason_display)


def test_foreign_quiz_404(client, professor, other_professor, make_quiz):
    foreign = make_quiz(other_professor)
    client.force_login(professor)
    assert client.get(reverse("quiz_results", args=[foreign.pk])).status_code == 404


def test_unauthenticated_redirects(client, results_quiz):
    resp = client.get(reverse("quiz_results", args=[results_quiz.pk]))
    assert resp.status_code == 302
    assert "/accounts/login/" in resp.url
