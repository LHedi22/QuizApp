"""Persist generated version plans as `Version` rows (R2.1, R2.6, R2.7).

Generation is a one-shot append-only operation: there is deliberately no
`regenerate` / `reshuffle` / `update_*_order` function anywhere (R2.7). The shuffle
maps are written once here and then immutable (Phase 1 `save()` guard + DB triggers).
"""

from __future__ import annotations

from django.db import transaction

from app.core.models import Question, Quiz, Version
from app.grading.versioning import generate_versions
from app.sheet_template import load_template

_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


class VersionGenerationBlocked(Exception):
    """Raised when a quiz isn't in a state where versions can be generated."""


def _letter_set_to_indices(letters: list[str], n_options: int) -> frozenset[int]:
    return frozenset(_LETTERS.index(letter) for letter in letters if _LETTERS.index(letter) < n_options)


def generate_versions_for_quiz(quiz: Quiz, m: int, *, seed: int | None = None) -> list[Version]:
    """Generate `m` versions for `quiz`, atomically, and flip it to `versioned`.

    Raises `VersionGenerationBlocked` if the quiz isn't `draft` or has no questions.
    Propagates `ValueError` / `InfeasibleVersionCount` from the generator (R2.6) —
    nothing is written and `quiz.status` stays `draft`.
    """
    if quiz.status != Quiz.Status.DRAFT:
        raise VersionGenerationBlocked(f"cannot generate versions: quiz is '{quiz.status}', not 'draft'")

    rows = list(quiz.questions.order_by("order_index").values_list("id", "correct_options"))
    if not rows:
        raise VersionGenerationBlocked("quiz has no questions")

    n_options = quiz.options_per_question
    questions = [(qid, _letter_set_to_indices(correct, n_options)) for qid, correct in rows]

    plans = generate_versions(questions, n_options=n_options, m=m, seed=seed)

    template_version = load_template().template_version
    with transaction.atomic():
        versions = Version.objects.bulk_create(
            Version(
                quiz=quiz,
                version_number=number,
                question_order=plan.question_order,
                option_order={str(qid): order for qid, order in plan.option_order.items()},
                template_version=template_version,
                anticluster_fallback=plan.anticluster_fallback,
            )
            for number, plan in enumerate(plans, start=1)
        )
        quiz.status = Quiz.Status.VERSIONED
        quiz.save(update_fields=["status"])
    return versions


def recover_correct_letters(version: Version, question: Question) -> set[str]:
    """The sheet letters `question`'s correct options land on in `version`, from the
    stored maps alone (R2.4). Helper for review / tests / grading translation."""
    n_options = question.quiz.options_per_question
    correct_indices = _letter_set_to_indices(question.correct_options, n_options)
    option_order = version.option_order[str(question.id)]
    position_of = {canonical: pos for pos, canonical in enumerate(option_order)}
    return {_LETTERS[position_of[i]] for i in correct_indices}
