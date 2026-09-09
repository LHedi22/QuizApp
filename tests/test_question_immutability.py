"""Phase 2.4 DoD: questions are frozen once a version exists (R1.5). Needs Postgres."""
from __future__ import annotations

import pytest

from app.core.ingest import IngestBlocked, discard_questions, ingest_quiz
from app.core.models import Quiz
from tests.conftest import QUESTION_HEADER

pytestmark = pytest.mark.django_db

ROWS = [
    QUESTION_HEADER,
    ["q1", "a", "b", "c", "d", "A", None],
    ["q2", "a", "b", "c", "d", "B", None],
]


def test_reingest_allowed_while_draft(professor, make_quiz, make_xlsx):
    quiz = make_quiz(professor, options_per_question=4)
    assert quiz.status == Quiz.Status.DRAFT
    ingest_quiz(quiz, make_xlsx(ROWS))
    ingest_quiz(quiz, make_xlsx(ROWS[:2]))  # replace with 1
    assert quiz.questions.count() == 1


@pytest.mark.parametrize("status", [Quiz.Status.VERSIONED, Quiz.Status.PRINTED])
def test_frozen_once_versioned_or_printed(professor, make_quiz, make_xlsx, status):
    quiz = make_quiz(professor, options_per_question=4)
    ingest_quiz(quiz, make_xlsx(ROWS))
    quiz.status = status
    quiz.save(update_fields=["status"])

    with pytest.raises(IngestBlocked):
        ingest_quiz(quiz, make_xlsx(ROWS[:2]))
    with pytest.raises(IngestBlocked):
        discard_questions(quiz)
    assert quiz.questions.count() == 2  # unchanged
