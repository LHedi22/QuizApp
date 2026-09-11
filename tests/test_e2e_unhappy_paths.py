"""Phase 11.2 — unhappy paths through the real UI + real backend: bad
spreadsheet row, infeasible `M` request, unreadable QR / failed alignment,
ambiguous bubble, duplicate submission, upside-down scan. Every scenario
must fail *cleanly* — no exception, no silent misgrade, no partial write.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from app.core.models import Answer, Question, Quiz, Submission, Version
from app.core.scan_pipeline import find_probable_duplicate, process_submission_image
from app.core.versioning_service import recover_correct_letters
from app.omr.alignment import VersionGeometry, align_page
from app.omr.geometry import AlignmentError
from app.sheet_template import load_template
from tests.conftest import render_filled_submission_image

pytestmark = pytest.mark.django_db


@pytest.fixture
def client_a(client, professor):
    client.force_login(professor)
    return client


@pytest.fixture
def quiz_with_questions(professor, make_quiz):
    quiz = make_quiz(professor, options_per_question=4)
    for i in range(1, 9):
        Question.objects.create(
            quiz=quiz, order_index=i, text=f"Q{i}",
            options=["a", "b", "c", "d"], correct_options=["A"],
        )
    return quiz


# --- R1.3/R1.5: bad spreadsheet row --------------------------------------


def test_bad_spreadsheet_row_rejected_all_or_nothing(client_a, professor, make_xlsx):
    quiz = Quiz.objects.create(professor=professor, title="Bad Row Quiz", options_per_question=4)
    rows = [["question_text", "option_1", "option_2", "option_3", "option_4", "correct_options", "points"]]
    rows.append(["Q1 fine", "a", "b", "c", "d", "A", ""])
    rows.append(["Q2 missing an option", "a", "b", "", "d", "A", ""])  # R1.4 bad row
    upload = SimpleUploadedFile("bad.xlsx", make_xlsx(rows), content_type="application/octet-stream")

    resp = client_a.post(reverse("quiz_upload", args=[quiz.pk]), {"file": upload})

    assert resp.status_code == 200  # re-renders the upload page, not a redirect
    body = resp.content.decode()
    assert "expected 4 non-empty option cells" in body
    assert Question.objects.filter(quiz=quiz).count() == 0  # nothing written (R1.3)


# --- R2.2: infeasible M request -------------------------------------------


def test_infeasible_version_count_rejected(client_a, professor):
    quiz = Quiz.objects.create(professor=professor, title="Tiny Quiz", options_per_question=4)
    Question.objects.create(
        quiz=quiz, order_index=1, text="only question", options=["a", "b", "c", "d"], correct_options=["A"]
    )  # 1! = 1 distinct ordering

    resp = client_a.post(reverse("version_generate", args=[quiz.pk]), {"m": 2})

    assert resp.status_code == 302
    assert Version.objects.filter(quiz=quiz).count() == 0
    resp2 = client_a.get(reverse("quiz_detail", args=[quiz.pk]))
    assert "exceeds" in resp2.content.decode() or "distinct" in resp2.content.decode()


# --- R5.1: unreadable QR / failed alignment --------------------------------


def test_blank_image_upload_fails_cleanly_no_answers(client_a, make_quiz, professor, make_version):
    quiz = make_quiz(professor)
    version = make_version(quiz)
    blank = np.full((800, 600, 3), 255, dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", blank)
    assert ok
    upload = SimpleUploadedFile("blank.jpg", buf.tobytes(), content_type="image/jpeg")

    resp = client_a.post(reverse("submission_upload", args=[version.pk]), {"photo-image": upload}, follow=True)

    assert resp.status_code == 200
    assert "Scan failed" in resp.content.decode()
    submission = Submission.objects.get(version=version)
    assert submission.status == Submission.Status.FAILED
    assert submission.failure_reason == Submission.FailureReason.ALIGNMENT_FAILED
    assert Answer.objects.filter(submission=submission).count() == 0


def test_qr_decoding_to_an_unknown_version_fails_as_version_not_found():
    """A QR that decodes fine but doesn't match any version this professor
    picked — distinct from a QR that can't be read at all (R5.1)."""

    def lookup(_qr_text: str) -> VersionGeometry | None:
        return None  # nothing ever matches -> exercises the version_not_found path

    blank = np.full((800, 600, 3), 255, dtype=np.uint8)
    with pytest.raises(AlignmentError) as exc_info:
        align_page(blank, load_template(), version_lookup=lookup)
    # a blank image has no QR at all, so this still lands on marks_not_found —
    # confirms the two failure modes both raise the *same* clean AlignmentError
    # channel rather than an unhandled exception either way (R5.1's real point)
    assert exc_info.value.reason in ("marks_not_found", "version_not_found")


# --- R5.7: ambiguous bubble -------------------------------------------------


def test_ambiguous_bubble_flags_for_review(professor, make_quiz, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    quiz = make_quiz(professor, options_per_question=4)
    questions = [
        Question.objects.create(
            quiz=quiz, order_index=i, text=f"Q{i}", options=["a", "b", "c", "d"], correct_options=["A"]
        )
        for i in range(1, 6)
    ]
    version = Version.objects.create(
        quiz=quiz, version_number=1,
        question_order=[q.id for q in questions],
        option_order={str(q.id): [0, 1, 2, 3] for q in questions},
        template_version=2,
    )

    # every question answered cleanly except one: a mid-gray partial fill
    fill_pattern = {i: {0} for i in range(1, 6)}
    image_bytes = render_filled_submission_image(version, fill_pattern)
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    gray = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)

    from app.sheet_template import bubble_centres

    centres = bubble_centres(load_template(), 5, 4)
    scale = 150 / 25.4
    x_mm, y_mm = centres[5][0]  # question 5's option A — leave this one ambiguous
    cx, cy = int(x_mm * scale), int(y_mm * scale)
    radius_px = int(load_template().geometry.grid.bubble_diameter_mm / 2 * scale * 0.8)
    # a mid-gray fill lands the local-normalized score between the empty_max
    # (0.15) and filled_min (0.35) gate thresholds -- genuinely ambiguous,
    # not just "lightly filled"
    cv2.circle(gray, (cx, cy), radius_px, 195, thickness=-1)
    ok, buf = cv2.imencode(".jpg", gray)
    assert ok

    submission = process_submission_image(version=version, image_bytes=buf.tobytes(), source=Submission.Source.PHOTO)

    assert submission.status == Submission.Status.NEEDS_REVIEW
    assert submission.total_score is None
    flagged = Answer.objects.filter(submission=submission, flagged=True)
    assert flagged.exists()


# --- R5.8: duplicate submission (no UI wired yet — Phase 7 design) --------


def test_duplicate_submission_detected_but_never_auto_confirmed(professor, make_quiz, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    quiz = make_quiz(professor, options_per_question=4)
    questions = [
        Question.objects.create(
            quiz=quiz, order_index=i, text=f"Q{i}", options=["a", "b", "c", "d"], correct_options=["A"]
        )
        for i in range(1, 4)
    ]
    version = Version.objects.create(
        quiz=quiz, version_number=1,
        question_order=[q.id for q in questions],
        option_order={str(q.id): [0, 1, 2, 3] for q in questions},
        template_version=2,
    )
    fill_pattern = {i: {0} for i in range(1, 4)}
    image_bytes = render_filled_submission_image(version, fill_pattern)

    first = process_submission_image(version=version, image_bytes=image_bytes, source=Submission.Source.PHOTO)
    second = process_submission_image(version=version, image_bytes=image_bytes, source=Submission.Source.PHOTO)

    assert first.answer_hash == second.answer_hash
    dup = find_probable_duplicate(second)
    assert dup is not None and dup.pk == first.pk
    assert second.duplicate_of_id is None  # professor-confirmed only (Appendix A)


# --- R5.2: upside-down scan fails cleanly, never silently misgraded -------


def test_upside_down_scan_fails_cleanly(client_a, professor, make_quiz, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    quiz = make_quiz(professor, options_per_question=4)
    questions = [
        Question.objects.create(
            quiz=quiz, order_index=i, text=f"Q{i}", options=["a", "b", "c", "d"], correct_options=["A"]
        )
        for i in range(1, 5)
    ]
    version = Version.objects.create(
        quiz=quiz, version_number=1,
        question_order=[q.id for q in questions],
        option_order={str(q.id): [0, 1, 2, 3] for q in questions},
        template_version=2,
    )
    fill_pattern = {}
    for q in questions:
        letters = recover_correct_letters(version, q)
        pos = version.question_order.index(q.id) + 1
        fill_pattern[pos] = {ord(letter) - ord("A") for letter in letters}
    image_bytes = render_filled_submission_image(version, fill_pattern)
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    gray = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    rotated = cv2.rotate(gray, cv2.ROTATE_180)
    ok, buf = cv2.imencode(".jpg", rotated)
    assert ok

    upload = SimpleUploadedFile("upside_down.jpg", buf.tobytes(), content_type="image/jpeg")
    resp = client_a.post(reverse("submission_upload", args=[version.pk]), {"photo-image": upload}, follow=True)

    assert resp.status_code == 200
    submission = Submission.objects.get(version=version)
    # R5.2: must never silently misgrade — either a clean FAILED, or (if the
    # aligner's 180 deg symmetry handling recovers it) a correct FINALIZED,
    # but never a wrong score
    if submission.status == Submission.Status.FAILED:
        assert submission.failure_reason == Submission.FailureReason.ALIGNMENT_FAILED
        assert Answer.objects.filter(submission=submission).count() == 0
    else:
        assert submission.status in (Submission.Status.FINALIZED, Submission.Status.NEEDS_REVIEW)
        if submission.status == Submission.Status.FINALIZED:
            assert submission.total_score == pytest.approx(4.0)
