"""Quiz CRUD views (Phase 8.1). Every view is `@login_required` and funnels object
access through `get_owned_or_404` so a foreign id 404s, never 403 (R0.2/R0.3).
"""

from __future__ import annotations

import csv
from io import BytesIO

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, F
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from app.core.access import get_owned_or_404
from app.core.blob_storage import get_blob_storage
from app.core.ingest import IngestBlocked, ingest_quiz
from app.core.models import Quiz, Submission, Version
from app.core.versioning_service import VersionGenerationBlocked, generate_versions_for_quiz
from app.grading.versioning import InfeasibleVersionCount
from app.pdf.artifacts import render_and_store_version_pdfs
from app.web.forms import (
    QuestionUploadForm,
    QuizConfigForm,
    QuizCreateForm,
    VersionGenerateForm,
)


@login_required
def quiz_list(request: HttpRequest) -> HttpResponse:
    quizzes = (
        Quiz.objects.owned_by(request.user)
        .annotate(num_questions=Count("questions", distinct=True))
        .annotate(num_versions=Count("versions", distinct=True))
        .order_by("-created_at")
    )
    return render(request, "web/quiz_list.html", {"quizzes": quizzes})


@login_required
def quiz_create(request: HttpRequest) -> HttpResponse:
    form = QuizCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        quiz = form.save(request.user)
        messages.success(request, f"Quiz “{quiz.title}” created.")
        return redirect("quiz_detail", pk=quiz.pk)
    return render(request, "web/quiz_form.html", {"form": form, "mode": "create"})


@login_required
def quiz_detail(request: HttpRequest, pk: int) -> HttpResponse:
    quiz = get_owned_or_404(Quiz, pk, request.user)
    can_edit = quiz.status == Quiz.Status.DRAFT
    return render(
        request,
        "web/quiz_detail.html",
        {
            "quiz": quiz,
            "questions": quiz.questions.all(),
            "versions": quiz.versions.all(),
            "can_edit": can_edit,
            "can_generate": can_edit and quiz.questions.exists(),
            "version_form": VersionGenerateForm(),
        },
    )


@login_required
def version_generate(request: HttpRequest, pk: int) -> HttpResponse:
    """Generate `M` shuffled versions (R2.1). Feasibility / blocked failures
    (R2.2/R2.6) are surfaced as a message; nothing is written on failure.
    """
    quiz = get_owned_or_404(Quiz, pk, request.user)
    if request.method != "POST":
        return redirect("quiz_detail", pk=quiz.pk)

    form = VersionGenerateForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Enter a whole number of versions (1 or more).")
        return redirect("quiz_detail", pk=quiz.pk)

    try:
        versions = generate_versions_for_quiz(quiz, form.cleaned_data["m"])
    except (VersionGenerationBlocked, InfeasibleVersionCount, ValueError) as exc:
        messages.error(request, str(exc))
        return redirect("quiz_detail", pk=quiz.pk)

    messages.success(request, f"{len(versions)} version(s) generated.")
    return redirect("quiz_detail", pk=quiz.pk)


_RESULTS_SORTS = {
    "captured": [F("created_at").asc()],
    "-captured": [F("created_at").desc()],
    "score": [F("total_score").asc(nulls_last=True)],
    "-score": [F("total_score").desc(nulls_last=True)],
}


@login_required
def quiz_results(request: HttpRequest, pk: int) -> HttpResponse:
    """Per-quiz submission list (R6.1): status / score / capture time / assigned
    student / flag reasons, filterable by status, sortable by score and capture
    time.
    """
    quiz = get_owned_or_404(Quiz, pk, request.user)

    submissions = (
        Submission.objects.owned_by(request.user)
        .filter(version__quiz=quiz)
        .select_related("roster_entry", "version")
        .prefetch_related("answers")
    )

    status = request.GET.get("status", "")
    if status in Submission.Status.values:
        submissions = submissions.filter(status=status)

    sort = request.GET.get("sort", "-captured")
    order = _RESULTS_SORTS.get(sort, _RESULTS_SORTS["-captured"])
    submissions = submissions.order_by(*order, "id")

    rows = []
    for sub in submissions:
        if sub.status == Submission.Status.FAILED:
            flags = [sub.get_failure_reason_display()] if sub.failure_reason else []
        else:
            flags = sorted({a.flag_reason for a in sub.answers.all() if a.flagged and a.flag_reason})
        student = (sub.roster_entry.label if sub.roster_entry_id else sub.student_label) or "—"
        rows.append({"sub": sub, "student": student, "flags": flags})

    return render(
        request,
        "web/quiz_results.html",
        {
            "quiz": quiz,
            "rows": rows,
            "statuses": Submission.Status.choices,
            "active_status": status,
            "active_sort": sort,
        },
    )


@login_required
def quiz_results_csv(request: HttpRequest, pk: int) -> HttpResponse:
    """CSV export of a quiz's results (R6.6): student, version, total, per-question
    scores in canonical question order."""
    quiz = get_owned_or_404(Quiz, pk, request.user)
    n_questions = quiz.questions.count()
    submissions = (
        Submission.objects.owned_by(request.user)
        .filter(version__quiz=quiz)
        .select_related("roster_entry", "version")
        .prefetch_related("answers")
        .order_by("id")
    )

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="quiz{quiz.pk}_results.csv"'
    writer = csv.writer(response)
    writer.writerow(
        ["student", "version", "total", *(f"q{i}" for i in range(1, n_questions + 1))]
    )
    for sub in submissions:
        student = (sub.roster_entry.label if sub.roster_entry_id else sub.student_label) or ""
        scores = {a.question_no: a.score for a in sub.answers.all()}
        row = [
            student,
            sub.version.version_number,
            "" if sub.total_score is None else sub.total_score,
        ]
        for i in range(1, n_questions + 1):
            s = scores.get(i)
            row.append("" if s is None else s)
        writer.writerow(row)
    return response


_PDF_KINDS = ("answer_sheet", "question_paper")


@login_required
def version_pdf(request: HttpRequest, pk: int, kind: str) -> HttpResponse:
    """Stream a version's answer sheet / question paper from the deterministic
    blob cache (R3.1, R3.4)."""
    if kind not in _PDF_KINDS:
        raise Http404("unknown PDF kind")
    version = get_owned_or_404(Version, pk, request.user)
    paths = render_and_store_version_pdfs(version)
    data = get_blob_storage().read(paths[kind])
    response = HttpResponse(data, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="quiz{version.quiz_id}_v{version.version_number}_{kind}.pdf"'
    )
    return response


@login_required
def quiz_upload(request: HttpRequest, pk: int) -> HttpResponse:
    """Ingest a `.xlsx` of questions (R1.2/R1.3). Renders every header + row error;
    never a 500. Blocked once the quiz has left `draft` (R1.5).
    """
    quiz = get_owned_or_404(Quiz, pk, request.user)
    form = QuestionUploadForm(request.POST or None, request.FILES or None)
    result = None
    if request.method == "POST" and form.is_valid():
        upload = form.cleaned_data["file"]
        try:
            result = ingest_quiz(quiz, BytesIO(upload.read()))
        except IngestBlocked as exc:
            messages.error(request, str(exc))
            return redirect("quiz_detail", pk=quiz.pk)
        if result.ok:
            messages.success(
                request,
                f"{len(result.questions)} question(s) ingested — the previous set "
                "was replaced.",
            )
            return redirect("quiz_detail", pk=quiz.pk)
    return render(
        request,
        "web/quiz_upload.html",
        {"quiz": quiz, "form": form, "result": result},
    )


@login_required
def quiz_edit(request: HttpRequest, pk: int) -> HttpResponse:
    quiz = get_owned_or_404(Quiz, pk, request.user)
    if quiz.status != Quiz.Status.DRAFT:
        messages.error(
            request,
            f"Cannot edit a “{quiz.get_status_display()}” quiz — configuration is "
            "frozen once versions exist.",
        )
        return redirect("quiz_detail", pk=quiz.pk)

    form = QuizConfigForm(request.POST or None, instance=quiz)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Quiz configuration updated.")
        return redirect("quiz_detail", pk=quiz.pk)
    return render(request, "web/quiz_form.html", {"form": form, "mode": "edit", "quiz": quiz})


@login_required
def quiz_delete(request: HttpRequest, pk: int) -> HttpResponse:
    quiz = get_owned_or_404(Quiz, pk, request.user)
    if quiz.status != Quiz.Status.DRAFT:
        messages.error(
            request,
            f"Cannot delete a “{quiz.get_status_display()}” quiz — its versions are "
            "irreplaceable and may already be graded.",
        )
        return redirect("quiz_detail", pk=quiz.pk)

    if request.method == "POST":
        title = quiz.title
        quiz.delete()
        messages.success(request, f"Quiz “{title}” deleted.")
        return redirect("dashboard")
    return render(request, "web/quiz_confirm_delete.html", {"quiz": quiz})
