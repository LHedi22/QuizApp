"""Phase 11.1 — happy path end-to-end through the real Django views + real
backend: quiz creation through a graded, reviewed result. No service-layer
shortcuts, no mocked OMR — the scanned "photo" is a genuine rendered and
rasterized answer sheet (see `tests/conftest.py::render_filled_submission_image`).
"""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from app.core.models import Question, Quiz, Submission, Version
from app.core.versioning_service import recover_correct_letters
from tests.conftest import render_filled_submission_image

pytestmark = pytest.mark.django_db


@pytest.fixture
def client_a(client, professor):
    client.force_login(professor)
    return client


def test_full_workflow_quiz_creation_to_graded_reviewed_result(
    client_a, professor, make_xlsx, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path

    # 1. create quiz
    resp = client_a.post(
        reverse("quiz_create"),
        {
            "title": "E2E Happy Path Quiz",
            "options_per_question": 4,
            "marking_mode": "partial",
            "default_points": 1.0,
        },
    )
    assert resp.status_code == 302
    quiz = Quiz.objects.get(title="E2E Happy Path Quiz", professor=professor)

    # 2. upload questions (.xlsx) — R1.2
    rows = [["question_text", "option_1", "option_2", "option_3", "option_4", "correct_options", "points"]]
    for i in range(1, 9):
        rows.append([f"Question {i}", "opt A", "opt B", "opt C", "opt D", "A", ""])
    upload = SimpleUploadedFile(
        "questions.xlsx",
        make_xlsx(rows),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp = client_a.post(reverse("quiz_upload", args=[quiz.pk]), {"file": upload})
    assert resp.status_code == 302
    assert Question.objects.filter(quiz=quiz).count() == 8

    # 3. generate versions (R2.1)
    resp = client_a.post(reverse("version_generate", args=[quiz.pk]), {"m": 2})
    assert resp.status_code == 302
    versions = list(Version.objects.filter(quiz=quiz).order_by("version_number"))
    assert len(versions) == 2

    # 4. download both PDFs for every version (R3.1/R3.4)
    for v in versions:
        for kind in ("answer_sheet", "question_paper"):
            resp = client_a.get(reverse("version_pdf", args=[v.pk, kind]))
            assert resp.status_code == 200
            assert resp["Content-Type"] == "application/pdf"

    # 5. mark a version printed (R3.5)
    version = versions[0]
    resp = client_a.post(reverse("version_mark_printed", args=[version.pk]))
    assert resp.status_code == 302
    version.refresh_from_db()
    assert version.printed_at is not None

    # 6. scan an all-correct submission through the real upload view
    fill_pattern: dict[int, set[int]] = {}
    for q in Question.objects.filter(quiz=quiz).order_by("order_index"):
        sheet_position = version.question_order.index(q.id) + 1
        letters = recover_correct_letters(version, q)
        fill_pattern[sheet_position] = {ord(letter) - ord("A") for letter in letters}
    image_bytes = render_filled_submission_image(version, fill_pattern)
    upload = SimpleUploadedFile("scan.jpg", image_bytes, content_type="image/jpeg")
    resp = client_a.post(reverse("submission_upload", args=[version.pk]), {"photo-image": upload})
    assert resp.status_code == 302
    submission = Submission.objects.get(version=version)
    assert resp.url == reverse("submission_detail", args=[submission.pk])
    assert submission.status == Submission.Status.FINALIZED
    assert submission.total_score == pytest.approx(8.0)

    # 7. the review UI shows it, unflagged, all correct
    body = client_a.get(reverse("submission_detail", args=[submission.pk])).content.decode()
    assert "Finalized" in body or "finalized" in body

    # 8. assign a student label
    resp = client_a.post(reverse("submission_assign", args=[submission.pk]), {"student_label": "e2e-student"})
    assert resp.status_code == 302
    submission.refresh_from_db()
    assert submission.student_label == "e2e-student"

    # 9. results list + CSV export both show it
    results_body = client_a.get(reverse("quiz_results", args=[quiz.pk])).content.decode()
    assert "e2e-student" in results_body
    csv_body = client_a.get(reverse("quiz_results_csv", args=[quiz.pk])).content.decode()
    assert "e2e-student" in csv_body
    assert "8" in csv_body
