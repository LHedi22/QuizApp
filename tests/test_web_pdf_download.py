"""Phase 8.4 — version PDF download, end-to-end via the test client."""

from __future__ import annotations

import pytest
from django.test import override_settings
from django.urls import reverse

from app.core.models import Question
from app.core.versioning_service import generate_versions_for_quiz

pytestmark = pytest.mark.django_db


@pytest.fixture
def version(professor, make_quiz):
    quiz = make_quiz(professor, options_per_question=4)
    for i in range(1, 9):
        Question.objects.create(
            quiz=quiz, order_index=i, text=f"Q{i}",
            options=["a", "b", "c", "d"], correct_options=["A"],
        )
    return generate_versions_for_quiz(quiz, 1)[0]


@pytest.fixture
def client_a(client, professor):
    client.force_login(professor)
    return client


@pytest.mark.parametrize("kind", ["answer_sheet", "question_paper"])
def test_download_is_pdf(client_a, version, kind, tmp_path):
    with override_settings(MEDIA_ROOT=tmp_path):
        resp = client_a.get(reverse("version_pdf", args=[version.pk, kind]))
    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF-")
    assert "attachment" in resp["Content-Disposition"]


def test_redownload_is_byte_identical(client_a, version, tmp_path):
    url = reverse("version_pdf", args=[version.pk, "answer_sheet"])
    with override_settings(MEDIA_ROOT=tmp_path):
        first = client_a.get(url).content
        second = client_a.get(url).content
    assert first == second


def test_unknown_kind_404(client_a, version, tmp_path):
    with override_settings(MEDIA_ROOT=tmp_path):
        resp = client_a.get(f"/versions/{version.pk}/bogus.pdf")
    assert resp.status_code == 404


def test_foreign_and_missing_version_404(client, professor, other_professor, make_quiz, version, tmp_path):
    client.force_login(other_professor)
    with override_settings(MEDIA_ROOT=tmp_path):
        assert client.get(reverse("version_pdf", args=[version.pk, "answer_sheet"])).status_code == 404
        assert client.get(reverse("version_pdf", args=[999999, "answer_sheet"])).status_code == 404


def test_unauthenticated_redirects_to_login(client, version, tmp_path):
    with override_settings(MEDIA_ROOT=tmp_path):
        resp = client.get(reverse("version_pdf", args=[version.pk, "answer_sheet"]))
    assert resp.status_code == 302
    assert "/accounts/login/" in resp.url
