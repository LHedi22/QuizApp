"""Phase 9.4 — roster paste (R6.4)."""

from __future__ import annotations

import pytest
from django.urls import reverse

from app.core.models import RosterEntry

pytestmark = pytest.mark.django_db


@pytest.fixture
def client_a(client, professor):
    client.force_login(professor)
    return client


def test_paste_creates_then_replaces(client_a, professor, make_quiz):
    quiz = make_quiz(professor)
    client_a.post(reverse("quiz_roster", args=[quiz.pk]),
                  {"text": "Ada\nBabbage, 42\nHopper"})
    assert quiz.roster_entries.count() == 3
    assert quiz.roster_entries.get(label="Babbage").external_id == "42"

    client_a.post(reverse("quiz_roster", args=[quiz.pk]), {"text": "X\nY"})
    labels = sorted(quiz.roster_entries.values_list("label", flat=True))
    assert labels == ["X", "Y"]


def test_bad_line_is_a_form_error_and_leaves_roster_unchanged(client_a, professor, make_quiz):
    quiz = make_quiz(professor)
    RosterEntry.objects.create(quiz=quiz, label="Keep")
    resp = client_a.post(reverse("quiz_roster", args=[quiz.pk]), {"text": "Ada\n, 99"})
    assert resp.status_code == 200
    assert b"no name" in resp.content
    assert list(quiz.roster_entries.values_list("label", flat=True)) == ["Keep"]


def test_roster_entries_appear_in_assignment_form(client_a, professor, make_quiz, make_version, make_submission):
    quiz = make_quiz(professor, options_per_question=4)
    client_a.post(reverse("quiz_roster", args=[quiz.pk]), {"text": "Ada Lovelace"})
    version = make_version(quiz)
    sub = make_submission(version)
    body = client_a.get(reverse("submission_detail", args=[sub.pk])).content.decode()
    assert "Ada Lovelace" in body


def test_get_prefills_current_roster(client_a, professor, make_quiz):
    quiz = make_quiz(professor)
    RosterEntry.objects.create(quiz=quiz, label="Ada", external_id="1")
    RosterEntry.objects.create(quiz=quiz, label="Bob")
    body = client_a.get(reverse("quiz_roster", args=[quiz.pk])).content.decode()
    assert "Ada, 1" in body
    assert "Bob" in body


def test_foreign_quiz_404(client, professor, other_professor, make_quiz):
    foreign = make_quiz(other_professor)
    client.force_login(professor)
    assert client.get(reverse("quiz_roster", args=[foreign.pk])).status_code == 404
