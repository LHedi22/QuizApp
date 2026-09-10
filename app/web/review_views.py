"""Phase 9 review surface: per-submission answer sheet + audit history (R6.2/R6.5),
inline override + student assignment (R6.3/R6.4). Every view is `@login_required`
and funnels object access through `get_owned_or_404`.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from app.core.access import get_owned_or_404
from app.core.models import Answer, Question, Quiz, Submission, Version
from app.core.review_service import (
    assign_student,
    mark_version_printed,
    override_answer,
    replace_roster,
)
from app.core.versioning_service import recover_correct_letters
from app.web.forms import AnswerOverrideForm, RosterPasteForm, StudentAssignForm

_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _answer_rows(submission: Submission):
    version = submission.version
    questions = {q.order_index: q for q in Question.objects.filter(quiz_id=version.quiz_id)}
    rows = []
    for ans in submission.answers.all():
        question = questions.get(ans.question_no)
        rows.append(
            {
                "answer": ans,
                "question": question,
                "correct_letters": (
                    sorted(recover_correct_letters(version, question)) if question else []
                ),
            }
        )
    # flagged rows pinned to the top (R6.2), then canonical question order
    rows.sort(key=lambda r: (not r["answer"].flagged, r["answer"].question_no))
    return rows


@login_required
def submission_detail(request: HttpRequest, pk: int) -> HttpResponse:
    submission = get_owned_or_404(Submission, pk, request.user)
    version = submission.version
    quiz = version.quiz
    return render(
        request,
        "web/submission_detail.html",
        {
            "submission": submission,
            "version": version,
            "quiz": quiz,
            "rows": _answer_rows(submission),
            "events": submission.audit_events.select_related("actor_professor").order_by(
                "-created_at"
            ),
            "option_letters": list(_LETTERS[: quiz.options_per_question]),
            "assign_form": StudentAssignForm(quiz=quiz, instance=submission),
        },
    )


@login_required
def answer_override(request: HttpRequest, pk: int) -> HttpResponse:
    answer = get_owned_or_404(Answer, pk, request.user)
    if request.method != "POST":
        return redirect("submission_detail", pk=answer.submission_id)
    n_options = answer.submission.version.quiz.options_per_question
    form = AnswerOverrideForm(request.POST, n_options=n_options)
    if form.is_valid():
        override_answer(
            answer=answer, professor=request.user, marked_options=form.cleaned_data["marked_options"]
        )
        messages.success(request, f"Q{answer.question_no} updated.")
    else:
        messages.error(request, "Could not apply the override.")
    return redirect("submission_detail", pk=answer.submission_id)


@login_required
def submission_assign(request: HttpRequest, pk: int) -> HttpResponse:
    submission = get_owned_or_404(Submission, pk, request.user)
    if request.method != "POST":
        return redirect("submission_detail", pk=submission.pk)
    form = StudentAssignForm(request.POST, quiz=submission.version.quiz, instance=submission)
    if form.is_valid():
        assign_student(
            submission=submission,
            professor=request.user,
            roster_entry=form.cleaned_data.get("roster_entry"),
            label=form.cleaned_data.get("student_label", ""),
        )
        messages.success(request, "Student assignment updated.")
    else:
        for error in form.non_field_errors():
            messages.error(request, error)
    return redirect("submission_detail", pk=submission.pk)


def _roster_as_text(quiz: Quiz) -> str:
    lines = []
    for entry in quiz.roster_entries.all():
        lines.append(f"{entry.label}, {entry.external_id}" if entry.external_id else entry.label)
    return "\n".join(lines)


@login_required
def quiz_roster(request: HttpRequest, pk: int) -> HttpResponse:
    """Paste / replace a quiz's roster (R6.4)."""
    quiz = get_owned_or_404(Quiz, pk, request.user)
    if request.method == "POST":
        form = RosterPasteForm(request.POST)
        if form.is_valid():
            created = replace_roster(
                quiz=quiz, professor=request.user, text=form.cleaned_data["text"]
            )
            messages.success(request, f"Roster saved — {len(created)} student(s).")
            return redirect("quiz_detail", pk=quiz.pk)
    else:
        form = RosterPasteForm(initial={"text": _roster_as_text(quiz)})
    return render(request, "web/quiz_roster.html", {"quiz": quiz, "form": form})


@login_required
def version_mark_printed(request: HttpRequest, pk: int) -> HttpResponse:
    """Mark a version printed (R3.5). The first printed version of a quiz flips
    `quiz.status → printed`, which blocks question re-upload (R1.5)."""
    version = get_owned_or_404(Version, pk, request.user)
    if request.method == "POST":
        mark_version_printed(version=version, professor=request.user)
        messages.success(request, f"Version {version.version_number} marked printed.")
    return redirect("quiz_detail", pk=version.quiz_id)
