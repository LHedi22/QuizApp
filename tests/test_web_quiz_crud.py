"""Phase 8.1 — quiz CRUD views, end-to-end via the Django test client.

Covers: create (valid + each invalid field), owner-scoped list, foreign/missing
pk → 404 on detail/edit/delete, config edit (cannot touch N), draft-only edit,
draft-only delete.
"""

from __future__ import annotations

import pytest
from django.urls import reverse

from app.core.models import Quiz

pytestmark = pytest.mark.django_db


@pytest.fixture
def client_a(client, professor):
    client.force_login(professor)
    return client


def _create(client, **overrides):
    data = {
        "title": "Midterm",
        "options_per_question": "4",
        "marking_mode": Quiz.MarkingMode.PARTIAL,
        "default_points": "1.0",
    }
    data.update(overrides)
    return client.post(reverse("quiz_create"), data)


def test_create_valid_writes_draft_and_redirects(client_a, professor):
    resp = _create(client_a, title="Midterm", negative_marking="on")
    quiz = Quiz.objects.get()
    assert quiz.professor == professor
    assert quiz.status == Quiz.Status.DRAFT
    assert quiz.options_per_question == 4
    assert quiz.negative_marking is True
    assert resp.status_code == 302
    assert resp.url == reverse("quiz_detail", args=[quiz.pk])


@pytest.mark.parametrize(
    "overrides",
    [
        {"title": ""},
        {"options_per_question": "7"},
        {"options_per_question": "1"},
        {"default_points": "-2"},
        {"marking_mode": "bogus"},
    ],
)
def test_create_invalid_writes_nothing(client_a, overrides):
    resp = _create(client_a, **overrides)
    assert resp.status_code == 200  # form re-rendered
    assert Quiz.objects.count() == 0


def test_list_is_owner_scoped(client, professor, other_professor, make_quiz):
    make_quiz(professor, title="Mine")
    make_quiz(other_professor, title="Theirs")
    client.force_login(professor)
    body = client.get(reverse("dashboard")).content.decode()
    assert "Mine" in body
    assert "Theirs" not in body


@pytest.mark.parametrize("name", ["quiz_detail", "quiz_edit", "quiz_delete"])
def test_foreign_and_missing_pk_404(client, professor, other_professor, make_quiz, name):
    foreign = make_quiz(other_professor)
    client.force_login(professor)
    assert client.get(reverse(name, args=[foreign.pk])).status_code == 404
    assert client.get(reverse(name, args=[999999])).status_code == 404


def test_config_edit_persists_and_cannot_change_n(client_a, professor, make_quiz):
    quiz = make_quiz(professor, title="Old", options_per_question=4)
    resp = client_a.post(
        reverse("quiz_edit", args=[quiz.pk]),
        {
            "title": "New",
            "marking_mode": Quiz.MarkingMode.ALL_OR_NOTHING,
            "default_points": "2.5",
            "options_per_question": "6",  # ignored — not a form field
        },
    )
    assert resp.status_code == 302
    quiz.refresh_from_db()
    assert quiz.title == "New"
    assert quiz.marking_mode == Quiz.MarkingMode.ALL_OR_NOTHING
    assert quiz.default_points == 2.5
    assert quiz.options_per_question == 4  # unchanged


def test_edit_blocked_once_versioned(client_a, professor, make_quiz):
    quiz = make_quiz(professor, title="Frozen", status=Quiz.Status.VERSIONED)
    resp = client_a.post(
        reverse("quiz_edit", args=[quiz.pk]),
        {"title": "Changed", "marking_mode": Quiz.MarkingMode.PARTIAL, "default_points": "1"},
    )
    assert resp.status_code == 302
    quiz.refresh_from_db()
    assert quiz.title == "Frozen"


def test_delete_draft_then_blocked_when_versioned(client_a, professor, make_quiz):
    draft = make_quiz(professor, title="Draft")
    resp = client_a.post(reverse("quiz_delete", args=[draft.pk]))
    assert resp.status_code == 302
    assert not Quiz.objects.filter(pk=draft.pk).exists()

    locked = make_quiz(professor, title="Locked", status=Quiz.Status.PRINTED)
    resp = client_a.post(reverse("quiz_delete", args=[locked.pk]))
    assert resp.status_code == 302
    assert Quiz.objects.filter(pk=locked.pk).exists()
