"""Phase 2.2 DoD: create_quiz validation, defaults, and ownership (R1.1, R7 config)."""
from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError

from app.core.models import Quiz
from app.core.services import create_quiz

pytestmark = pytest.mark.django_db


def test_valid_quiz_is_created_with_all_config(professor):
    quiz = create_quiz(
        professor=professor,
        title="  Midterm  ",
        options_per_question=5,
        marking_mode=Quiz.MarkingMode.ALL_OR_NOTHING,
        negative_marking=True,
        default_points=2.0,
    )
    assert quiz.pk and quiz.professor == professor
    assert quiz.title == "Midterm"
    assert quiz.options_per_question == 5
    assert quiz.marking_mode == "all_or_nothing"
    assert quiz.negative_marking is True
    assert quiz.default_points == 2.0
    assert quiz.status == Quiz.Status.DRAFT


def test_defaults_applied(professor):
    quiz = create_quiz(professor=professor, title="Q", options_per_question=4)
    assert quiz.marking_mode == "partial"
    assert quiz.negative_marking is False
    assert quiz.default_points == 1.0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"title": "", "options_per_question": 4},
        {"title": "   ", "options_per_question": 4},
        {"title": "Q", "options_per_question": 1},
        {"title": "Q", "options_per_question": 7},
        {"title": "Q", "options_per_question": "four"},
        {"title": "Q", "options_per_question": 4, "default_points": -0.5},
        {"title": "Q", "options_per_question": 4, "default_points": "abc"},
        {"title": "Q", "options_per_question": 4, "marking_mode": "weighted"},
    ],
)
def test_invalid_input_raises_and_writes_nothing(professor, kwargs):
    before = Quiz.objects.count()
    with pytest.raises(ValidationError):
        create_quiz(professor=professor, **kwargs)
    assert Quiz.objects.count() == before


def test_created_quiz_is_owned_by_creator(professor, other_professor):
    quiz = create_quiz(professor=professor, title="Q", options_per_question=4)
    assert Quiz.objects.owned_by(professor).filter(pk=quiz.pk).exists()
    assert not Quiz.objects.owned_by(other_professor).filter(pk=quiz.pk).exists()
