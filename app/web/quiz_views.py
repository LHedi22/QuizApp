"""Quiz CRUD views (Phase 8.1). Every view is `@login_required` and funnels object
access through `get_owned_or_404` so a foreign id 404s, never 403 (R0.2/R0.3).
"""

from __future__ import annotations

from io import BytesIO

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from app.core.access import get_owned_or_404
from app.core.ingest import IngestBlocked, ingest_quiz
from app.core.models import Quiz
from app.core.versioning_service import VersionGenerationBlocked, generate_versions_for_quiz
from app.grading.versioning import InfeasibleVersionCount
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
