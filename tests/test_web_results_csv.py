"""Phase 9.5 — CSV export (R6.6)."""

from __future__ import annotations

import csv
import io

import pytest
from django.urls import reverse

from app.core.models import Answer, Question, RosterEntry, Version

pytestmark = pytest.mark.django_db


@pytest.fixture
def client_a(client, professor):
    client.force_login(professor)
    return client


@pytest.fixture
def csv_quiz(professor, make_quiz, make_submission):
    quiz = make_quiz(professor, options_per_question=4)
    qs = [
        Question.objects.create(quiz=quiz, order_index=i, text=f"Q{i}",
                                options=["a", "b", "c", "d"], correct_options=["A"])
        for i in range(1, 4)
    ]
    version = Version.objects.create(
        quiz=quiz, version_number=2, question_order=[q.id for q in qs],
        option_order={str(q.id): [0, 1, 2, 3] for q in qs}, template_version=2,
    )
    roster = RosterEntry.objects.create(quiz=quiz, label="Ada")

    s1 = make_submission(version, total_score=2.0, roster_entry=roster)
    for i, sc in enumerate([1.0, 1.0, 0.0], start=1):
        Answer.objects.create(submission=s1, question_no=i, detected_options=["A"],
                              confidence=0.9, score=sc)
    s2 = make_submission(version, total_score=1.0, student_label="walk-in")
    # s2 only has answers for q1 and q3 (q2 missing → blank cell)
    Answer.objects.create(submission=s2, question_no=1, detected_options=["A"], confidence=0.9, score=1.0)
    Answer.objects.create(submission=s2, question_no=3, detected_options=["B"], confidence=0.9, score=0.0)
    s3 = make_submission(version, total_score=None)
    return quiz, s1, s2, s3


def _rows(resp):
    return list(csv.reader(io.StringIO(resp.content.decode())))


def test_csv_headers_and_shape(client_a, csv_quiz):
    quiz, *_ = csv_quiz
    resp = client_a.get(reverse("quiz_results_csv", args=[quiz.pk]))
    assert resp["Content-Type"] == "text/csv"
    assert "attachment" in resp["Content-Disposition"]
    rows = _rows(resp)
    assert rows[0] == ["student", "version", "total", "q1", "q2", "q3"]
    assert len(rows) == 1 + 3  # header + 3 submissions


def test_csv_values(client_a, csv_quiz):
    quiz, s1, s2, s3 = csv_quiz
    rows = _rows(client_a.get(reverse("quiz_results_csv", args=[quiz.pk])))
    body = {r[0] or "(none)": r for r in rows[1:]}
    assert body["Ada"] == ["Ada", "2", "2.0", "1.0", "1.0", "0.0"]
    assert body["walk-in"] == ["walk-in", "2", "1.0", "1.0", "", "0.0"]  # q2 blank
    assert body["(none)"][2] == ""  # total None → blank


def test_foreign_quiz_404_and_unauth_redirect(client, professor, other_professor, csv_quiz):
    quiz, *_ = csv_quiz
    client.force_login(other_professor)
    assert client.get(reverse("quiz_results_csv", args=[quiz.pk])).status_code == 404
    client.logout()
    resp = client.get(reverse("quiz_results_csv", args=[quiz.pk]))
    assert resp.status_code == 302 and "/accounts/login/" in resp.url
