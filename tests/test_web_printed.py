"""Phase 9.6 — "mark printed" control (R3.5)."""

from __future__ import annotations

from io import BytesIO

import pytest
from django.urls import reverse

from app.core.ingest import IngestBlocked, ingest_quiz
from app.core.models import AuditEvent, Question, Quiz, Version
from tests.conftest import QUESTION_HEADER

pytestmark = pytest.mark.django_db


@pytest.fixture
def client_a(client, professor):
    client.force_login(professor)
    return client


@pytest.fixture
def versioned_quiz(professor, make_quiz):
    quiz = make_quiz(professor, options_per_question=4, status=Quiz.Status.DRAFT)
    q = Question.objects.create(quiz=quiz, order_index=1, text="Q1",
                                options=["a", "b", "c", "d"], correct_options=["A"])
    version = Version.objects.create(
        quiz=quiz, version_number=1, question_order=[q.id],
        option_order={str(q.id): [0, 1, 2, 3]}, template_version=2,
    )
    return quiz, version


def test_mark_printed_flips_quiz_and_blocks_upload(client_a, versioned_quiz, make_xlsx):
    quiz, version = versioned_quiz
    resp = client_a.post(reverse("version_mark_printed", args=[version.pk]))
    assert resp.status_code == 302
    version.refresh_from_db()
    quiz.refresh_from_db()
    assert version.printed_at is not None
    assert quiz.status == Quiz.Status.PRINTED
    assert AuditEvent.objects.filter(action="printed").count() == 1

    with pytest.raises(IngestBlocked):
        ingest_quiz(quiz, BytesIO(make_xlsx([QUESTION_HEADER,
                    ["Q1", "1", "2", "3", "4", "A", ""]])))


def test_mark_printed_is_idempotent(client_a, versioned_quiz):
    quiz, version = versioned_quiz
    client_a.post(reverse("version_mark_printed", args=[version.pk]))
    client_a.post(reverse("version_mark_printed", args=[version.pk]))
    assert AuditEvent.objects.filter(action="printed").count() == 1


def test_foreign_version_404(client, professor, other_professor, versioned_quiz):
    quiz, version = versioned_quiz
    client.force_login(other_professor)
    assert client.post(reverse("version_mark_printed", args=[version.pk])).status_code == 404
