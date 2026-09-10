"""Phase 9 mutations: manual override, student assignment, roster paste, and the
per-version "mark printed" control. Every one writes an append-only `AuditEvent`
(R6.5); every score change goes through the shared `score_question` (R7.5).
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from app.core.models import AuditEvent, Question, Quiz, RosterEntry, Submission, Version
from app.core.versioning_service import recover_correct_letters
from app.grading.regrade import status_after_override, submission_total
from app.grading.scoring import score_question


def _question_for(answer) -> Question:
    version = answer.submission.version
    return Question.objects.get(quiz_id=version.quiz_id, order_index=answer.question_no)


def _points_for(question: Question, quiz: Quiz) -> float:
    return question.points if question.points is not None else quiz.default_points


@transaction.atomic
def override_answer(*, answer, professor, marked_options: list[str]):
    """Re-score one answer from a professor-supplied marked-option set (R6.3).

    Re-scores via `score_question`, clears the flag, stamps `manually_edited` +
    `edited_at`, recomputes the submission total, and finalizes the submission if
    nothing on it is still flagged. Writes an `overridden` audit event.
    """
    submission: Submission = answer.submission
    version: Version = submission.version
    quiz: Quiz = version.quiz
    question = _question_for(answer)
    key = recover_correct_letters(version, question)
    points = _points_for(question, quiz)
    marked = sorted({m.strip().upper() for m in marked_options if m and m.strip()})

    before = {
        "detected_options": list(answer.detected_options),
        "score": answer.score,
        "flagged": answer.flagged,
    }
    new_score = score_question(marked, key, points, quiz.marking_mode, quiz.negative_marking)

    answer.detected_options = marked
    answer.score = new_score
    answer.correct = set(marked) == set(key)
    answer.flagged = False
    answer.flag_reason = ""
    answer.manually_edited = True
    answer.edited_at = timezone.now()
    answer.save()

    answers = list(submission.answers.all())
    submission.total_score = submission_total(a.score for a in answers)
    submission.status = status_after_override(
        submission.status, any_flagged=any(a.flagged for a in answers)
    )
    submission.save(update_fields=["total_score", "status"])

    AuditEvent.objects.create(
        quiz=quiz,
        submission=submission,
        actor_professor=professor,
        action=AuditEvent.Action.OVERRIDDEN,
        detail={
            "question_no": answer.question_no,
            "before": before,
            "after": {"detected_options": marked, "score": new_score},
        },
    )
    return answer


@transaction.atomic
def assign_student(*, submission: Submission, professor, roster_entry=None, label: str = ""):
    """Assign a student to a submission (R6.4) — a roster entry OR free text, never
    both. Editable and logged (`assigned` audit event)."""
    before = {
        "roster_entry": submission.roster_entry_id,
        "student_label": submission.student_label,
    }
    if roster_entry is not None:
        submission.roster_entry = roster_entry
        submission.student_label = ""
    else:
        submission.roster_entry = None
        submission.student_label = (label or "").strip()
    submission.save(update_fields=["roster_entry", "student_label"])

    AuditEvent.objects.create(
        quiz=submission.version.quiz,
        submission=submission,
        actor_professor=professor,
        action=AuditEvent.Action.ASSIGNED,
        detail={
            "before": before,
            "after": {
                "roster_entry": submission.roster_entry_id,
                "student_label": submission.student_label,
            },
        },
    )
    return submission


def parse_roster(text: str) -> list[tuple[str, str]]:
    """One `(label, external_id)` per non-blank line. Line format: `label` or
    `label, external_id` (first comma splits). Raises `ValueError` on a line whose
    label is empty."""
    entries: list[tuple[str, str]] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        label, _, external_id = line.partition(",")
        label = label.strip()
        if not label:
            raise ValueError(f"roster line has no name: {raw!r}")
        entries.append((label, external_id.strip()))
    return entries


@transaction.atomic
def replace_roster(*, quiz: Quiz, professor, text: str) -> list[RosterEntry]:
    """Replace (not append) a quiz's roster from pasted text (R6.4). Existing
    submission assignments to removed entries become unset (FK `SET_NULL`)."""
    parsed = parse_roster(text)
    quiz.roster_entries.all().delete()
    created = RosterEntry.objects.bulk_create(
        [RosterEntry(quiz=quiz, label=label, external_id=external_id) for label, external_id in parsed]
    )
    AuditEvent.objects.create(
        quiz=quiz,
        submission=None,
        actor_professor=professor,
        action=AuditEvent.Action.ASSIGNED,
        detail={"roster_size": len(created)},
    )
    return created


@transaction.atomic
def mark_version_printed(*, version: Version, professor) -> Version:
    """Set `version.printed_at` (R3.5). The first printed version of a quiz flips
    `quiz.status → printed` (which blocks question re-upload, R1.5). Idempotent:
    an already-printed version is returned unchanged with no new audit event.
    This is the only code path that sets `printed_at` / flips to `printed`."""
    if version.printed_at is not None:
        return version

    version.printed_at = timezone.now()
    version.save(update_fields=["printed_at"])

    quiz = version.quiz
    if quiz.status != Quiz.Status.PRINTED:
        quiz.status = Quiz.Status.PRINTED
        quiz.save(update_fields=["status"])

    AuditEvent.objects.create(
        quiz=quiz,
        submission=None,
        actor_professor=professor,
        action=AuditEvent.Action.PRINTED,
        detail={"version_id": version.id, "version_number": version.version_number},
    )
    return version
