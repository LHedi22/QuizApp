"""Django admin. Deliberately minimal — the admin exists mainly as the password
recovery path (there is no reset flow, §3.1 / §6 Q13a). The version shuffle maps and
the audit log are NOT editable here (R2.7, R6.5).
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from app.core.models import (
    Answer,
    AuditEvent,
    Professor,
    Question,
    Quiz,
    RosterEntry,
    Submission,
    Version,
)


@admin.register(Professor)
class ProfessorAdmin(UserAdmin):
    ordering = ["email"]
    list_display = ["email", "is_staff", "is_active", "date_joined"]
    search_fields = ["email"]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),
    )


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ["title", "professor", "options_per_question", "marking_mode", "status", "created_at"]
    list_filter = ["status", "marking_mode", "negative_marking"]
    search_fields = ["title"]


@admin.register(Version)
class VersionAdmin(admin.ModelAdmin):
    list_display = [
        "__str__",
        "version_number",
        "template_version",
        "anticluster_fallback",
        "printed_at",
        "created_at",
    ]
    list_filter = ["anticluster_fallback"]
    # shuffle maps + qr_id are immutable (R2.7); the fallback flag is set by the
    # generator, not a human: show, never edit.
    readonly_fields = [
        "qr_id",
        "question_order",
        "option_order",
        "anticluster_fallback",
        "created_at",
    ]


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ["__str__", "action", "quiz", "submission", "created_at"]
    list_filter = ["action"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register([Question, RosterEntry, Submission, Answer])
