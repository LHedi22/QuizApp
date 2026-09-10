"""Phase 8.3 — version generation UI, end-to-end via the test client."""

from __future__ import annotations

import pytest
from django.urls import reverse

from app.core.models import Question, Quiz, Version

pytestmark = pytest.mark.django_db


@pytest.fixture
def client_a(client, professor):
    client.force_login(professor)
    return client


def _add_questions(quiz, n):
    for i in range(1, n + 1):
        Question.objects.create(
            quiz=quiz,
            order_index=i,
            text=f"Q{i}",
            options=["a", "b", "c", "d"][: quiz.options_per_question],
            correct_options=["A"],
        )


def _generate(client, quiz, m):
    return client.post(reverse("version_generate", args=[quiz.pk]), {"m": m})


def test_generate_creates_versions_and_flips_status(client_a, professor, make_quiz):
    quiz = make_quiz(professor, options_per_question=4)
    _add_questions(quiz, 8)
    resp = _generate(client_a, quiz, 3)
    assert resp.status_code == 302
    quiz.refresh_from_db()
    assert quiz.status == Quiz.Status.VERSIONED
    assert Version.objects.filter(quiz=quiz).count() == 3
    body = client_a.get(reverse("quiz_detail", args=[quiz.pk])).content.decode()
    assert body.count("<td>") >= 3  # version rows rendered


@pytest.mark.parametrize("m", ["0", "-1"])
def test_non_positive_m_rejected_nothing_written(client_a, professor, make_quiz, m):
    quiz = make_quiz(professor, options_per_question=4)
    _add_questions(quiz, 5)
    resp = _generate(client_a, quiz, m)
    assert resp.status_code == 302
    quiz.refresh_from_db()
    assert quiz.status == Quiz.Status.DRAFT
    assert Version.objects.filter(quiz=quiz).count() == 0


def test_infeasible_m_rejected(client_a, professor, make_quiz):
    quiz = make_quiz(professor, options_per_question=4)
    _add_questions(quiz, 3)  # 3! = 6 distinct question orders
    resp = _generate(client_a, quiz, 10)
    assert resp.status_code == 302
    quiz.refresh_from_db()
    assert quiz.status == Quiz.Status.DRAFT
    assert Version.objects.filter(quiz=quiz).count() == 0


def test_generate_twice_is_blocked(client_a, professor, make_quiz):
    quiz = make_quiz(professor, options_per_question=4)
    _add_questions(quiz, 8)
    _generate(client_a, quiz, 2)
    assert Version.objects.filter(quiz=quiz).count() == 2
    _generate(client_a, quiz, 5)
    assert Version.objects.filter(quiz=quiz).count() == 2  # unchanged


def test_generate_no_questions_blocked(client_a, professor, make_quiz):
    quiz = make_quiz(professor, options_per_question=4)
    resp = _generate(client_a, quiz, 3)
    assert resp.status_code == 302
    assert Version.objects.filter(quiz=quiz).count() == 0


def test_foreign_quiz_404(client, professor, other_professor, make_quiz):
    foreign = make_quiz(other_professor)
    client.force_login(professor)
    assert _generate(client, foreign, 3).status_code == 404
