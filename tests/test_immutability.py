"""Phase 1.1 DoD (CLAUDE.md rule 8): version shuffle maps and the audit log are
immutable — enforced at BOTH the app layer and the database (migration 0002)."""
from __future__ import annotations

import pytest
from django.db import Error as DBError
from django.utils import timezone

from app.core.exceptions import ImmutableFieldError
from app.core.models import AuditEvent, Version

pytestmark = pytest.mark.django_db(transaction=True)


def test_app_layer_blocks_reassigning_version_maps(professor, make_quiz, make_version):
    v = make_version(make_quiz(professor))

    v.question_order = [999]
    with pytest.raises(ImmutableFieldError):
        v.save()

    v.refresh_from_db()
    v.option_order = {"999": [0]}
    with pytest.raises(ImmutableFieldError):
        v.save()


def test_db_trigger_blocks_bulk_update_of_version_maps(professor, make_quiz, make_version):
    v = make_version(make_quiz(professor))
    with pytest.raises(DBError):
        Version.objects.filter(pk=v.pk).update(question_order=[1, 2, 3])
    with pytest.raises(DBError):
        Version.objects.filter(pk=v.pk).update(option_order={"1": [3, 2, 1, 0]})


def test_printed_at_is_still_mutable(professor, make_quiz, make_version):
    v = make_version(make_quiz(professor))
    v.printed_at = timezone.now()
    v.save()  # must not raise
    v.refresh_from_db()
    assert v.printed_at is not None


def test_app_layer_blocks_audit_event_edit_and_delete(professor, make_quiz):
    quiz = make_quiz(professor)
    ev = AuditEvent.objects.create(quiz=quiz, action=AuditEvent.Action.PRINTED, detail={"a": 1})

    ev.action = AuditEvent.Action.SCORED
    with pytest.raises(ImmutableFieldError):
        ev.save()
    with pytest.raises(ImmutableFieldError):
        ev.delete()


def test_db_trigger_blocks_audit_event_update(professor, make_quiz):
    quiz = make_quiz(professor)
    ev = AuditEvent.objects.create(quiz=quiz, action=AuditEvent.Action.PRINTED)
    with pytest.raises(DBError):
        AuditEvent.objects.filter(pk=ev.pk).update(action=AuditEvent.Action.SCORED)
