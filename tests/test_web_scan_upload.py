"""Phase 7.2 — scan intake UI (R0.2 ownership + R4.1 upload flows)."""

from __future__ import annotations

import uuid

import pymupdf
import pytest
from django.urls import reverse

from app.core.models import Question, Submission, Version
from tests.conftest import load_corpus_cases

pytestmark = pytest.mark.django_db

CORPUS_CASES = load_corpus_cases()


@pytest.fixture
def client_a(client, professor):
    client.force_login(professor)
    return client


@pytest.fixture
def corpus_version(make_quiz, professor):
    """A real Quiz/Question/Version matching one corpus source sheet's geometry
    and QR id, so a real corpus photo aligns and scores through the full view."""
    if not CORPUS_CASES:
        pytest.skip("corpus/images has no labeled real captures")
    image_path, label, meta = CORPUS_CASES[0]
    n_options = meta["options"]
    quiz = make_quiz(professor, options_per_question=n_options)
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    questions = []
    for i in range(1, meta["questions"] + 1):
        q = Question.objects.create(
            quiz=quiz,
            order_index=i,
            text=f"Q{i}",
            options=[f"opt {letters[j]}" for j in range(n_options)],
            correct_options=[letters[(i - 1) % n_options]],
        )
        questions.append(q)
    version = Version.objects.create(
        quiz=quiz,
        version_number=1,
        qr_id=uuid.UUID(meta["sheet_token"]),
        question_order=[q.id for q in questions],
        option_order={str(q.id): list(range(n_options)) for q in questions},
        template_version=meta["template_version"],
    )
    return version, image_path.read_bytes()


def test_upload_page_renders_both_forms(client_a, make_quiz, professor, make_version):
    quiz = make_quiz(professor)
    version = make_version(quiz)
    body = client_a.get(reverse("submission_upload", args=[version.pk])).content.decode()
    assert "Upload &amp; scan" in body
    assert "Upload &amp; scan batch" in body


def test_photo_upload_success_redirects_to_submission_detail(client_a, corpus_version):
    version, image_bytes = corpus_version
    from django.core.files.uploadedfile import SimpleUploadedFile

    upload = SimpleUploadedFile("sheet.jpg", image_bytes, content_type="image/jpeg")
    resp = client_a.post(
        reverse("submission_upload", args=[version.pk]),
        {"photo-image": upload},
    )
    assert resp.status_code == 302
    submission = Submission.objects.get(version=version)
    assert resp.url == reverse("submission_detail", args=[submission.pk])
    assert submission.status in (Submission.Status.FINALIZED, Submission.Status.NEEDS_REVIEW)


def test_photo_upload_failed_alignment_stays_on_page_with_error(client_a, make_quiz, professor, make_version):
    import cv2
    import numpy as np
    from django.core.files.uploadedfile import SimpleUploadedFile

    quiz = make_quiz(professor)
    version = make_version(quiz)
    blank = np.full((800, 600, 3), 255, dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", blank)
    assert ok
    upload = SimpleUploadedFile("blank.jpg", buf.tobytes(), content_type="image/jpeg")
    resp = client_a.post(
        reverse("submission_upload", args=[version.pk]),
        {"photo-image": upload},
        follow=True,
    )
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "Scan failed" in body
    submission = Submission.objects.get(version=version)
    assert submission.status == Submission.Status.FAILED


def test_batch_upload_success_redirects_to_quiz_results(client_a, corpus_version):
    from django.core.files.uploadedfile import SimpleUploadedFile

    version, image_bytes = corpus_version
    doc = pymupdf.open()
    page = doc.new_page()
    rect = page.rect
    page.insert_image(rect, stream=image_bytes)
    pdf_bytes = doc.tobytes()
    doc.close()

    upload = SimpleUploadedFile("batch.pdf", pdf_bytes, content_type="application/pdf")
    resp = client_a.post(
        reverse("submission_upload_batch", args=[version.pk]),
        {"batch-file": upload},
    )
    assert resp.status_code == 302
    assert resp.url == reverse("quiz_results", args=[version.quiz_id])
    submissions = list(Submission.objects.filter(version=version))
    assert len(submissions) == 1
    assert submissions[0].page_number == 1
    assert submissions[0].batch_id is not None


def test_batch_upload_rejects_non_pdf(client_a, make_quiz, professor, make_version):
    from django.core.files.uploadedfile import SimpleUploadedFile

    quiz = make_quiz(professor)
    version = make_version(quiz)
    upload = SimpleUploadedFile("notes.txt", b"hello", content_type="text/plain")
    resp = client_a.post(
        reverse("submission_upload_batch", args=[version.pk]),
        {"batch-file": upload},
    )
    assert resp.status_code == 200
    assert Submission.objects.filter(version=version).count() == 0


def test_foreign_version_upload_pages_404(client, professor, other_professor, make_quiz, make_version):
    quiz = make_quiz(professor)
    version = make_version(quiz)
    client.force_login(other_professor)
    assert client.get(reverse("submission_upload", args=[version.pk])).status_code == 404
    assert client.get(reverse("submission_upload_batch", args=[version.pk])).status_code == 404
