"""Persist a parsed `.xlsx` into a quiz's canonical questions (R1.2, R1.3, R1.5).

Wraps the pure `xlsx_ingest.parse_workbook` with the sheet-geometry numbers and the
`draft`-only guard, then bulk-creates `Question` rows atomically.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from django.db import transaction

from app.core.models import Question, Quiz
from app.core.xlsx_ingest import ParseResult, parse_workbook
from app.sheet_template import load_template


class IngestBlocked(Exception):
    """Raised when questions can't change because a version already exists (R1.5)."""


def _require_draft(quiz: Quiz, action: str) -> None:
    if quiz.status != Quiz.Status.DRAFT:
        raise IngestBlocked(
            f"cannot {action}: quiz is '{quiz.status}', not 'draft' — "
            f"questions are frozen once a version has been generated (R1.5)"
        )


def discard_questions(quiz: Quiz) -> int:
    """Delete all of a quiz's questions. Allowed only while the quiz is `draft`."""
    _require_draft(quiz, "discard questions")
    deleted, _ = quiz.questions.all().delete()
    return deleted


def ingest_quiz(quiz: Quiz, source: str | Path | bytes | BytesIO) -> ParseResult:
    """Parse `source` for `quiz` and, if valid, replace the quiz's questions.

    Returns the `ParseResult`. On any error nothing is written (`result.ok` is
    False and `quiz.questions` is unchanged). Raises `IngestBlocked` if the quiz is
    no longer `draft`.
    """
    _require_draft(quiz, "ingest questions")

    template = load_template()
    result = parse_workbook(
        source,
        n_options=quiz.options_per_question,
        max_chars_per_option=template.max_chars_per_option,
        max_questions=template.capacity_for(quiz.options_per_question),
    )
    if not result.ok:
        return result

    with transaction.atomic():
        quiz.questions.all().delete()
        Question.objects.bulk_create(
            [
                Question(
                    quiz=quiz,
                    order_index=q.order_index,
                    text=q.text,
                    options=q.options,
                    correct_options=q.correct_options,
                    points=q.points,
                )
                for q in result.questions
            ]
        )
    return result
