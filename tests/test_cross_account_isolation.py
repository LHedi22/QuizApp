"""Phase 1.2 DoD: per-professor ownership isolation (REBUILD_SPEC §2 R0.2).

Route-level coverage ("every request path") is completed as data views are added
(Phases 8-9), each adding its own cross-account test. This proves the enforcement
primitives — `Model.objects.owned_by()` and `get_owned_or_404` — that every such
view must funnel through.
"""
from __future__ import annotations

import pytest
from django.http import Http404

from app.core.access import get_owned_or_404
from app.core.models import Answer, AuditEvent, Question, Quiz, RosterEntry, Submission, Version

pytestmark = pytest.mark.django_db


@pytest.fixture
def owned_graph(professor, make_quiz, make_version, make_submission):
    quiz = make_quiz(professor)
    version = make_version(quiz)
    question = quiz.questions.first()
    roster = RosterEntry.objects.create(quiz=quiz, label="Ada")
    submission = make_submission(version)
    answer = Answer.objects.create(
        submission=submission, question_no=1, detected_options=["A"], confidence=1.0
    )
    audit = AuditEvent.objects.create(quiz=quiz, action=AuditEvent.Action.SCORED)
    return {
        Quiz: quiz,
        Question: question,
        Version: version,
        RosterEntry: roster,
        Submission: submission,
        Answer: answer,
        AuditEvent: audit,
    }


def test_owned_by_hides_other_professors_rows(professor, other_professor, owned_graph):
    for model, obj in owned_graph.items():
        assert model.objects.owned_by(professor).filter(pk=obj.pk).exists()
        assert not model.objects.owned_by(other_professor).filter(pk=obj.pk).exists()
        with pytest.raises(model.DoesNotExist):
            model.objects.owned_by(other_professor).get(pk=obj.pk)


def test_get_owned_or_404_returns_own_and_404s_foreign(professor, other_professor, owned_graph):
    for model, obj in owned_graph.items():
        assert get_owned_or_404(model, obj.pk, professor) == obj
        with pytest.raises(Http404):
            get_owned_or_404(model, obj.pk, other_professor)


def test_get_owned_or_404_on_missing_pk(professor):
    with pytest.raises(Http404):
        get_owned_or_404(Quiz, 999_999, professor)
