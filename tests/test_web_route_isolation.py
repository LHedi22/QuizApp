"""Phase 8.6 — route-level R0.2 / R0.3 sweep over every Phase 8 data view.

R0.3: an unauthenticated request is redirected to login before any data.
R0.2: professor B hitting professor A's object id gets a 404 (never a 403).

This closes the route-level R0.2 verification deferred from Phase 1.2.
"""

from __future__ import annotations

import pytest
from django.test import override_settings
from django.urls import reverse

from app.core.models import Question
from app.core.versioning_service import generate_versions_for_quiz

pytestmark = pytest.mark.django_db


@pytest.fixture
def owned(professor, make_quiz):
    """A quiz (with questions) + a generated version, all owned by `professor`."""
    quiz = make_quiz(professor, options_per_question=4, title="A's quiz")
    for i in range(1, 9):
        Question.objects.create(
            quiz=quiz, order_index=i, text=f"Q{i}",
            options=["a", "b", "c", "d"], correct_options=["A"],
        )
    version = generate_versions_for_quiz(quiz, 1)[0]
    return quiz, version


def _routes(quiz, version):
    return [
        ("get", reverse("dashboard")),
        ("get", reverse("quiz_create")),
        ("get", reverse("quiz_detail", args=[quiz.pk])),
        ("get", reverse("quiz_edit", args=[quiz.pk])),
        ("get", reverse("quiz_delete", args=[quiz.pk])),
        ("get", reverse("quiz_upload", args=[quiz.pk])),
        ("get", reverse("quiz_results", args=[quiz.pk])),
        ("get", reverse("version_pdf", args=[version.pk, "answer_sheet"])),
        ("post", reverse("quiz_delete", args=[quiz.pk])),
        ("post", reverse("quiz_upload", args=[quiz.pk])),
        ("post", reverse("version_generate", args=[quiz.pk])),
        ("post", reverse("quiz_edit", args=[quiz.pk])),
    ]


@override_settings(MEDIA_ROOT=None)
def test_unauthenticated_is_redirected_to_login(client, owned, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    quiz, version = owned
    client.logout()
    for method, url in _routes(quiz, version):
        resp = getattr(client, method)(url)
        assert resp.status_code == 302, f"{method} {url} → {resp.status_code}"
        assert "/accounts/login/" in resp.url, f"{method} {url} → {resp.url}"


def test_foreign_object_ids_404_for_other_professor(client, owned, other_professor, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    quiz, version = owned
    client.force_login(other_professor)
    # routes that carry someone else's id (skip the id-less dashboard/create)
    for method, url in _routes(quiz, version):
        if url in (reverse("dashboard"), reverse("quiz_create")):
            continue
        resp = getattr(client, method)(url)
        assert resp.status_code == 404, f"{method} {url} → {resp.status_code} (expected 404)"
