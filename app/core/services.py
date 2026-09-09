"""Quiz-lifecycle operations that views (Phase 8) call. Validation lives here so it
can't be skipped by a route.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError

from app.core.models import Quiz


def create_quiz(
    *,
    professor,
    title: str,
    options_per_question,
    marking_mode: str = Quiz.MarkingMode.PARTIAL,
    negative_marking: bool = False,
    default_points=1.0,
) -> Quiz:
    """Create a `draft` quiz with its options count and grading config (R1.1, R7).

    Raises `django.core.exceptions.ValidationError` (field-keyed) on any invalid
    input; nothing is written.
    """
    errors: dict[str, str] = {}

    title = (title or "").strip()
    if not title:
        errors["title"] = "Title is required."

    n: int | None
    try:
        n = int(options_per_question)
    except (TypeError, ValueError):
        n = None
        errors["options_per_question"] = "Options per question must be a whole number."
    if n is not None and not 2 <= n <= 6:
        errors["options_per_question"] = "Options per question must be between 2 and 6."

    if marking_mode not in Quiz.MarkingMode.values:
        errors["marking_mode"] = f"Marking mode must be one of {list(Quiz.MarkingMode.values)}."

    dp: float | None
    try:
        dp = float(default_points)
    except (TypeError, ValueError):
        dp = None
        errors["default_points"] = "Default points must be a number."
    if dp is not None and dp < 0:
        errors["default_points"] = "Default points must be non-negative."

    if errors:
        raise ValidationError(errors)

    return Quiz.objects.create(
        professor=professor,
        title=title,
        options_per_question=n,
        marking_mode=marking_mode,
        negative_marking=bool(negative_marking),
        default_points=dp,
    )
