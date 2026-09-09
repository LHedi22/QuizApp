"""Phase 2.3b DoD: ingest_quiz persists a valid file atomically, writes nothing on
error (R1.2, R1.3). Needs Postgres."""
from __future__ import annotations

import pytest

from app.core.ingest import ingest_quiz
from app.core.models import Question
from tests.conftest import QUESTION_HEADER

pytestmark = pytest.mark.django_db

GOOD_ROWS = [
    QUESTION_HEADER,
    ["Capital of France?", "Paris", "Lyon", "Berlin", "Rome", "A", None],
    ["Select the primes", "2", "3", "4", "9", "A,B", 2.0],
    ["Empty points uses default", "w", "x", "y", "z", "C", None],
]


def test_valid_file_creates_ordered_questions(professor, make_quiz, make_xlsx):
    quiz = make_quiz(professor, options_per_question=4)
    result = ingest_quiz(quiz, make_xlsx(GOOD_ROWS))
    assert result.ok, (result.header_errors, result.file_errors, result.row_errors)
    qs = list(quiz.questions.all())
    assert [q.order_index for q in qs] == [1, 2, 3]
    assert qs[0].text == "Capital of France?"
    assert qs[0].options == ["Paris", "Lyon", "Berlin", "Rome"]
    assert qs[0].correct_options == ["A"]
    assert qs[1].correct_options == ["A", "B"] and qs[1].points == 2.0
    assert qs[2].points is None


def test_reingest_replaces_questions(professor, make_quiz, make_xlsx):
    quiz = make_quiz(professor, options_per_question=4)
    ingest_quiz(quiz, make_xlsx(GOOD_ROWS))
    assert quiz.questions.count() == 3
    smaller = [QUESTION_HEADER, ["only one", "a", "b", "c", "d", "D", None]]
    ingest_quiz(quiz, make_xlsx(smaller))
    assert quiz.questions.count() == 1
    assert quiz.questions.get().correct_options == ["D"]


def test_invalid_file_writes_nothing(professor, make_quiz, make_xlsx):
    quiz = make_quiz(professor, options_per_question=4)
    ingest_quiz(quiz, make_xlsx(GOOD_ROWS))  # 3 good questions first
    bad = [
        QUESTION_HEADER,
        ["ok", "a", "b", "c", "d", "A", None],
        ["bad row", "a", "b", "c", "d", "Z", "-4"],
    ]
    result = ingest_quiz(quiz, make_xlsx(bad))
    assert not result.ok
    assert len(result.row_errors) == 1
    # atomic: the pre-existing 3 questions are untouched, the bad batch is not written
    assert quiz.questions.count() == 3


def test_n_option_count_is_enforced_from_the_quiz(professor, make_quiz, make_xlsx):
    quiz = make_quiz(professor, options_per_question=3)
    header3 = ["question_text", "option_1", "option_2", "option_3", "correct_options", "points"]
    result = ingest_quiz(quiz, make_xlsx([header3, ["q", "a", "b", "c", "A", None]]))
    assert result.ok
    assert quiz.questions.get().options == ["a", "b", "c"]
    # a 4-option header against an N=3 quiz is a header error
    bad = ingest_quiz(quiz, make_xlsx([QUESTION_HEADER, ["q", "a", "b", "c", "d", "A", None]]))
    assert any("option_4" in e for e in bad.header_errors)
    assert Question.objects.filter(quiz=quiz).count() == 1  # unchanged


def test_capacity_enforced_against_sheet_template(professor, make_quiz, make_xlsx):
    quiz = make_quiz(professor, options_per_question=6)  # capacity_for(6) == 80
    header6 = ["question_text", *[f"option_{i}" for i in range(1, 7)], "correct_options"]
    rows = [header6] + [[f"q{i}", "a", "b", "c", "d", "e", "f", "A"] for i in range(81)]
    result = ingest_quiz(quiz, make_xlsx(rows))
    assert result.file_errors and "maximum for N=6 is 80" in result.file_errors[0]
    assert quiz.questions.count() == 0
