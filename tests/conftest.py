"""Shared fixtures for DB-backed core-model tests."""
from __future__ import annotations

import uuid
from io import BytesIO

import openpyxl
import pytest

QUESTION_HEADER = [
    "question_text",
    "option_1",
    "option_2",
    "option_3",
    "option_4",
    "correct_options",
    "points",
]


@pytest.fixture
def make_xlsx():
    """Build an .xlsx workbook (bytes) from a list of row lists."""

    def _build(rows: list[list]) -> bytes:
        wb = openpyxl.Workbook()
        ws = wb.active
        for row in rows:
            ws.append(row)
        buf = BytesIO()
        wb.save(buf)
        return buf.getvalue()

    return _build


@pytest.fixture
def professor(db):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(email="prof@example.com", password="pw-12345")


@pytest.fixture
def other_professor(db):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(email="other@example.com", password="pw-12345")


@pytest.fixture
def make_quiz(db):
    from app.core.models import Quiz

    def _make(professor, **kw):
        defaults = {"title": "Q", "options_per_question": 4}
        return Quiz.objects.create(professor=professor, **{**defaults, **kw})

    return _make


@pytest.fixture
def make_version(db):
    from app.core.models import Question, Version

    def _make(quiz, **kw):
        q = Question.objects.create(
            quiz=quiz, order_index=1, text="t", options=["a", "b", "c", "d"], correct_options=["A"]
        )
        defaults = {
            "version_number": 1,
            "question_order": [q.id],
            "option_order": {str(q.id): [0, 1, 2, 3]},
            "template_version": 1,
        }
        return Version.objects.create(quiz=quiz, **{**defaults, **kw})

    return _make


@pytest.fixture
def make_submission(db):
    from app.core.models import Submission

    def _make(version, **kw):
        defaults = {"raw_image_path": "/data/blob/x.jpg", "source": Submission.Source.PHOTO}
        return Submission.objects.create(version=version, **{**defaults, **kw})

    return _make


@pytest.fixture
def batch_id():
    return uuid.uuid4()
