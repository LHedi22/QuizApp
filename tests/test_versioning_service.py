"""Phase 3.4 DoD: persist versions atomically, flip status, no re-shuffle path
(R2.1, R2.6, R2.7). Needs Postgres."""
from __future__ import annotations

import importlib
import inspect
import pkgutil
import re

import pytest

from app.core import versioning_service
from app.core.ingest import IngestBlocked, ingest_quiz
from app.core.models import Question, Quiz, Version
from app.core.versioning_service import (
    VersionGenerationBlocked,
    generate_versions_for_quiz,
    recover_correct_letters,
)
from app.grading.versioning import InfeasibleVersionCount
from tests.conftest import QUESTION_HEADER

pytestmark = pytest.mark.django_db


def _quiz_with_questions(professor, make_quiz, make_xlsx, *, count=10, n=4):
    quiz = make_quiz(professor, options_per_question=n)
    header = ["question_text", *[f"option_{i}" for i in range(1, n + 1)], "correct_options"]
    letters = "ABCDEF"[:n]
    rows = [header] + [
        [f"q{i}", *[f"opt{j}" for j in range(n)], letters[i % n]] for i in range(count)
    ]
    result = ingest_quiz(quiz, make_xlsx(rows))
    assert result.ok, (result.header_errors, result.file_errors, result.row_errors)
    return quiz


def test_generates_m_versions_flips_status_and_freezes_questions(professor, make_quiz, make_xlsx):
    quiz = _quiz_with_questions(professor, make_quiz, make_xlsx, count=12)
    versions = generate_versions_for_quiz(quiz, 5, seed=1)

    assert [v.version_number for v in versions] == [1, 2, 3, 4, 5]
    assert len({v.qr_id for v in versions}) == 5
    assert all(v.template_version == 1 for v in versions)
    assert {tuple(v.question_order) for v in versions}.__len__() == 5  # distinct (R2.2)

    quiz.refresh_from_db()
    assert quiz.status == Quiz.Status.VERSIONED
    with pytest.raises(IngestBlocked):  # ties to R1.5 / subtask 2.4
        ingest_quiz(quiz, make_xlsx([QUESTION_HEADER, ["x", "a", "b", "c", "d", "A", None]]))


def test_infeasible_request_writes_nothing_and_leaves_status_draft(professor, make_quiz, make_xlsx):
    quiz = _quiz_with_questions(professor, make_quiz, make_xlsx, count=3)  # 3! = 6
    before = Version.objects.count()
    with pytest.raises(InfeasibleVersionCount):
        generate_versions_for_quiz(quiz, 7, seed=1)
    assert Version.objects.count() == before
    quiz.refresh_from_db()
    assert quiz.status == Quiz.Status.DRAFT


@pytest.mark.parametrize("bad_m", [0, -1])
def test_bad_m_raises_without_writing(professor, make_quiz, make_xlsx, bad_m):
    quiz = _quiz_with_questions(professor, make_quiz, make_xlsx, count=8)
    with pytest.raises(ValueError):
        generate_versions_for_quiz(quiz, bad_m)
    assert Version.objects.filter(quiz=quiz).count() == 0
    quiz.refresh_from_db()
    assert quiz.status == Quiz.Status.DRAFT


def test_generation_blocked_when_not_draft_or_no_questions(professor, make_quiz, make_xlsx):
    empty = make_quiz(professor, options_per_question=4)
    with pytest.raises(VersionGenerationBlocked):
        generate_versions_for_quiz(empty, 3)

    quiz = _quiz_with_questions(professor, make_quiz, make_xlsx, count=8)
    generate_versions_for_quiz(quiz, 2, seed=1)
    quiz.refresh_from_db()
    with pytest.raises(VersionGenerationBlocked):  # already 'versioned'
        generate_versions_for_quiz(quiz, 2)


def test_db_roundtrip_key_recovery(professor, make_quiz, make_xlsx):
    quiz = _quiz_with_questions(professor, make_quiz, make_xlsx, count=15, n=4)
    generate_versions_for_quiz(quiz, 3, seed=7)

    for version in Version.objects.filter(quiz=quiz):
        for qid in version.question_order[:4]:
            question = Question.objects.get(pk=qid)
            option_order = version.option_order[str(qid)]  # keys are str (JSON)
            sheet_letters = recover_correct_letters(version, question)
            recovered = {option_order["ABCDEF".index(letter)] for letter in sheet_letters}
            canonical = {"ABCDEF".index(letter) for letter in question.correct_options}
            assert recovered == canonical


def test_no_reshuffle_or_regenerate_callable_exists():
    """R2.7 — no code path re-shuffles or re-maps a version after creation."""
    banned = re.compile(r"(reshuffle|regenerate)|update.*(question_order|option_order)", re.IGNORECASE)
    import app.core
    import app.grading

    offenders = []
    for package in (app.core, app.grading):
        for _, modname, _ in pkgutil.iter_modules(package.__path__, package.__name__ + "."):
            module = importlib.import_module(modname)
            for name, obj in inspect.getmembers(module, callable):
                if getattr(obj, "__module__", "").startswith(package.__name__) and banned.search(name):
                    offenders.append(f"{modname}.{name}")
    assert not offenders, offenders


def test_service_generated_version_maps_are_immutable(professor, make_quiz, make_xlsx):
    from django.db import Error as DBError

    from app.core.exceptions import ImmutableFieldError

    quiz = _quiz_with_questions(professor, make_quiz, make_xlsx, count=10)
    version = generate_versions_for_quiz(quiz, 2, seed=1)[0]

    version.question_order = [1, 2, 3]
    with pytest.raises(ImmutableFieldError):
        version.save()
    with pytest.raises(DBError):
        Version.objects.filter(pk=version.pk).update(option_order={"1": [0]})


def test_versioning_service_module_has_no_mutation_helpers():
    names = [n for n, _ in inspect.getmembers(versioning_service, callable)]
    assert "generate_versions_for_quiz" in names
    assert not any("regenerate" in n or "reshuffle" in n for n in names)
