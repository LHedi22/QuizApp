"""Phase 7.2 — scan intake UI: upload one photo or a batch PDF of filled answer
sheets against a single pre-selected `Version` (2026-09-11 decision, see
docs/phases/phase-7.md — `Submission.version` is a required FK and alignment
failure alone can't identify a version, so the professor picks one before
scanning). Every view is `@login_required` and funnels object access through
`get_owned_or_404`.
"""

from __future__ import annotations

import pymupdf
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from app.core.access import get_owned_or_404
from app.core.models import Submission, Version
from app.core.scan_pipeline import process_batch, process_submission_image
from app.web.forms import SubmissionBatchUploadForm, SubmissionPhotoUploadForm

_BATCH_RASTER_DPI = 200


@login_required
def submission_upload(request: HttpRequest, pk: int) -> HttpResponse:
    """One page for both intake paths (R4.1): a single photo, or a batch PDF."""
    version = get_owned_or_404(Version, pk, request.user)
    photo_form = SubmissionPhotoUploadForm(prefix="photo")
    batch_form = SubmissionBatchUploadForm(prefix="batch")

    if request.method == "POST" and "photo-image" in request.FILES:
        photo_form = SubmissionPhotoUploadForm(request.POST, request.FILES, prefix="photo")
        if photo_form.is_valid():
            image = photo_form.cleaned_data["image"]
            submission = process_submission_image(
                version=version, image_bytes=image.read(), source=Submission.Source.PHOTO
            )
            if submission.status == Submission.Status.FAILED:
                messages.error(
                    request,
                    f"Scan failed ({submission.get_failure_reason_display()}) — "
                    "the photo was saved but couldn't be scored. Check the fiducial "
                    "corners and QR code are visible and try again.",
                )
                return redirect("submission_upload", pk=version.pk)
            return redirect("submission_detail", pk=submission.pk)

    return render(
        request,
        "web/submission_upload.html",
        {"version": version, "photo_form": photo_form, "batch_form": batch_form},
    )


@login_required
def submission_upload_batch(request: HttpRequest, pk: int) -> HttpResponse:
    version = get_owned_or_404(Version, pk, request.user)
    form = SubmissionBatchUploadForm(request.POST or None, request.FILES or None, prefix="batch")
    if request.method == "POST" and form.is_valid():
        pdf_bytes = form.cleaned_data["file"].read()
        pages: list[tuple[bytes, int]] = []
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
            for i, page in enumerate(doc, start=1):
                png_bytes = page.get_pixmap(dpi=_BATCH_RASTER_DPI).tobytes("png")
                pages.append((png_bytes, i))
        submissions = process_batch(version=version, pages=pages, source=Submission.Source.BATCH_PDF)
        n_ok = sum(1 for s in submissions if s.status != Submission.Status.FAILED)
        n_failed = len(submissions) - n_ok
        if n_failed:
            messages.warning(request, f"Batch done: {n_ok} scanned, {n_failed} failed (see quiz results).")
        else:
            messages.success(request, f"Batch done: all {n_ok} pages scanned.")
        return redirect("quiz_results", pk=version.quiz_id)

    return render(
        request,
        "web/submission_upload.html",
        {"version": version, "photo_form": SubmissionPhotoUploadForm(prefix="photo"), "batch_form": form},
    )
