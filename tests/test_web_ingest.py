"""Phase 8.2 — question upload UI (xlsx ingest), end-to-end via the test client."""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from app.core.models import Question, Quiz
from tests.conftest import QUESTION_HEADER

pytestmark = pytest.mark.django_db

GOOD_ROWS = [
    QUESTION_HEADER,
    ["What is 2+2?", "1", "2", "3", "4", "D", ""],
    ["Capital of France?", "Berlin", "Paris", "Rome", "Madrid", "B", "2"],
]


@pytest.fixture
def client_a(client, professor):
    client.force_login(professor)
    return client


def _upload(client, quiz, xlsx_bytes, name="questions.xlsx"):
    return client.post(
        reverse("quiz_upload", args=[quiz.pk]),
        {"file": SimpleUploadedFile(name, xlsx_bytes)},
    )


def test_valid_xlsx_ingests_in_file_order(client_a, professor, make_quiz, make_xlsx):
    quiz = make_quiz(professor, options_per_question=4)
    resp = _upload(client_a, quiz, make_xlsx(GOOD_ROWS))
    assert resp.status_code == 302
    texts = list(Question.objects.filter(quiz=quiz).order_by("order_index").values_list("text", flat=True))
    assert texts == ["What is 2+2?", "Capital of France?"]


def test_bad_rows_all_listed_and_nothing_written(client_a, professor, make_quiz, make_xlsx):
    quiz = make_quiz(professor, options_per_question=4)
    rows = [
        QUESTION_HEADER,
        ["", "a", "b", "", "", "Z", ""],          # empty text + wrong count + bad letter
        ["Dup", "x", "x", "y", "z", "A", ""],      # duplicate option text
        ["Weight", "a", "b", "c", "d", "A", "-1"],  # negative points
    ]
    resp = _upload(client_a, quiz, make_xlsx(rows))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "rejected" in body.lower()
    # every offending row surfaced
    for n in ("2", "3", "4"):
        assert f"<td>{n}</td>" in body
    # multiple reasons for row 2
    assert "question_text is empty" in body
    assert "duplicate option text" in body
    assert Question.objects.filter(quiz=quiz).count() == 0


def test_reupload_while_draft_replaces(client_a, professor, make_quiz, make_xlsx):
    quiz = make_quiz(professor, options_per_question=4)
    _upload(client_a, quiz, make_xlsx(GOOD_ROWS))
    assert Question.objects.filter(quiz=quiz).count() == 2
    _upload(client_a, quiz, make_xlsx(GOOD_ROWS[:2]))  # header + 1 row
    assert Question.objects.filter(quiz=quiz).count() == 1


def test_upload_blocked_once_versioned(client_a, professor, make_quiz, make_xlsx):
    quiz = make_quiz(professor, options_per_question=4, status=Quiz.Status.VERSIONED)
    resp = _upload(client_a, quiz, make_xlsx(GOOD_ROWS))
    assert resp.status_code == 302
    assert Question.objects.filter(quiz=quiz).count() == 0


def test_foreign_quiz_404(client, professor, other_professor, make_quiz, make_xlsx):
    foreign = make_quiz(other_professor)
    client.force_login(professor)
    assert _upload(client, foreign, make_xlsx(GOOD_ROWS)).status_code == 404
