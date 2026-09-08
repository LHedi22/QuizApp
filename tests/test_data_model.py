"""Phase 1.1 DoD: the finalized data model matches REBUILD_SPEC Appendix A."""
from __future__ import annotations

from django.apps import apps
from django.conf import settings

from app.core.managers import _OWNER_LOOKUP

CORE_MODELS = {
    "Professor",
    "Quiz",
    "Question",
    "Version",
    "RosterEntry",
    "Submission",
    "Answer",
    "AuditEvent",
}


def test_all_appendix_a_models_exist():
    got = {m.__name__ for m in apps.get_app_config("core").get_models()}
    assert CORE_MODELS <= got, CORE_MODELS - got


def test_custom_user_model():
    assert settings.AUTH_USER_MODEL == "core.Professor"
    Professor = apps.get_model("core", "Professor")
    assert Professor.USERNAME_FIELD == "email"
    assert Professor.REQUIRED_FIELDS == []
    assert Professor._meta.get_field("email").unique


def _field(model_name, field_name):
    return apps.get_model("core", model_name)._meta.get_field(field_name)


def test_version_columns_and_immutability_surface():
    Version = apps.get_model("core", "Version")
    assert _field("Version", "printed_at").null is True
    assert _field("Version", "qr_id").unique is True
    assert _field("Version", "qr_id").editable is False
    for name in ("question_order", "option_order"):
        assert _field("Version", name).get_internal_type() == "JSONField"
    assert Version.IMMUTABLE_FIELDS == ("question_order", "option_order", "qr_id")
    assert _field("Version", "template_version").get_internal_type() in {
        "PositiveIntegerField",
        "IntegerField",
    }


def test_json_columns_per_d2():
    for model, field in [
        ("Question", "options"),
        ("Question", "correct_options"),
        ("Version", "question_order"),
        ("Version", "option_order"),
        ("Answer", "detected_options"),
        ("AuditEvent", "detail"),
    ]:
        assert _field(model, field).get_internal_type() == "JSONField", (model, field)


def test_score_fields_are_float_per_d3():
    for model, field in [
        ("Quiz", "default_points"),
        ("Question", "points"),
        ("Answer", "score"),
        ("Submission", "total_score"),
    ]:
        assert _field(model, field).get_internal_type() == "FloatField", (model, field)


def test_quiz_status_choices_exact():
    Quiz = apps.get_model("core", "Quiz")
    assert {v for v, _ in Quiz._meta.get_field("status").choices} == {
        "draft",
        "versioned",
        "printed",
    }
    assert {v for v, _ in Quiz._meta.get_field("marking_mode").choices} == {
        "partial",
        "all_or_nothing",
    }


def test_submission_status_choices_exact():
    Submission = apps.get_model("core", "Submission")
    assert {v for v, _ in Submission._meta.get_field("status").choices} == {
        "pending",
        "needs_review",
        "finalized",
        "failed",
    }


def test_unique_constraints_present():
    def names(model):
        return {c.name for c in apps.get_model("core", model)._meta.constraints}

    assert "question_unique_order" in names("Question")
    assert "version_unique_number" in names("Version")
    assert "answer_unique_question" in names("Answer")
    assert "quiz_options_per_question_2_to_6" in names("Quiz")


def test_owner_lookup_covers_every_owned_model():
    # Professor is the owner itself; every other core model must be reachable.
    assert set(_OWNER_LOOKUP) == CORE_MODELS - {"Professor"}
