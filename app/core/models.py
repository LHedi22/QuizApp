"""Domain model — finalizes REBUILD_SPEC Appendix A (Phase 1, decisions D1-D5).

Enforcement notes:
- `Version.question_order` / `option_order` / `qr_id` are immutable after creation
  (R2.7). Guarded here in `save()` and again by a DB trigger (migration 0002).
- `AuditEvent` is append-only (R6.5): `save()` on an existing row and `delete()`
  raise; a DB trigger blocks `UPDATE` too.
- All money-like values are `FloatField` (D3) — R7's `(c-w)/k` is real-valued.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from app.core.exceptions import ImmutableFieldError
from app.core.managers import OwnedManager, ProfessorManager


class Professor(AbstractBaseUser, PermissionsMixin):
    """The only user role (R0.1). Keyed on email; no username, no reset token."""

    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = ProfessorManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        db_table = "core_professor"

    def __str__(self) -> str:
        return self.email

    def save(self, *args, **kwargs):
        self.email = self.email.lower()
        super().save(*args, **kwargs)


class Quiz(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft"
        VERSIONED = "versioned"
        PRINTED = "printed"

    class MarkingMode(models.TextChoices):
        PARTIAL = "partial"
        ALL_OR_NOTHING = "all_or_nothing"

    professor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="quizzes"
    )
    title = models.CharField(max_length=200)
    options_per_question = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(2), MaxValueValidator(6)]
    )
    marking_mode = models.CharField(
        max_length=16, choices=MarkingMode.choices, default=MarkingMode.PARTIAL
    )
    negative_marking = models.BooleanField(default=False)
    default_points = models.FloatField(default=1.0)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = OwnedManager()

    class Meta:
        verbose_name_plural = "quizzes"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(options_per_question__gte=2, options_per_question__lte=6),
                name="quiz_options_per_question_2_to_6",
            ),
            models.CheckConstraint(
                condition=models.Q(default_points__gte=0),
                name="quiz_default_points_non_negative",
            ),
        ]

    def __str__(self) -> str:
        return self.title


class Question(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="questions")
    order_index = models.PositiveIntegerField()
    text = models.TextField()
    options = models.JSONField()  # ["A text", "B text", ...] length == quiz.N
    correct_options = models.JSONField()  # ["A", "C"] canonical letters, length >= 1
    points = models.FloatField(null=True, blank=True)  # None -> quiz.default_points

    objects = OwnedManager()

    class Meta:
        ordering = ["order_index"]
        constraints = [
            models.UniqueConstraint(fields=["quiz", "order_index"], name="question_unique_order"),
        ]

    def __str__(self) -> str:
        return f"{self.quiz_id}:Q{self.order_index}"


class Version(models.Model):
    IMMUTABLE_FIELDS = ("question_order", "option_order", "qr_id")

    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="versions")
    version_number = models.PositiveIntegerField()
    qr_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    question_order = models.JSONField()  # [canonical_question_id, ...] shuffled
    option_order = models.JSONField()  # {"<canonical_question_id>": [canonical_option_index, ...]}
    template_version = models.PositiveIntegerField()
    printed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = OwnedManager()

    class Meta:
        ordering = ["version_number"]
        constraints = [
            models.UniqueConstraint(fields=["quiz", "version_number"], name="version_unique_number"),
        ]

    def __str__(self) -> str:
        return f"{self.quiz_id}:v{self.version_number}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            current = (
                type(self)
                ._base_manager.filter(pk=self.pk)
                .values(*self.IMMUTABLE_FIELDS)
                .first()
            )
            if current is not None:
                for field in self.IMMUTABLE_FIELDS:
                    if getattr(self, field) != current[field]:
                        raise ImmutableFieldError(
                            f"Version.{field} is immutable after creation (R2.7)"
                        )
        super().save(*args, **kwargs)


class RosterEntry(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="roster_entries")
    label = models.CharField(max_length=200)  # name / free text
    external_id = models.CharField(max_length=100, blank=True, default="")

    objects = OwnedManager()

    class Meta:
        verbose_name_plural = "roster entries"

    def __str__(self) -> str:
        return self.label


class Submission(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending"
        NEEDS_REVIEW = "needs_review"
        FINALIZED = "finalized"
        FAILED = "failed"

    class FailureReason(models.TextChoices):
        QR_UNREADABLE = "qr_unreadable"
        ALIGNMENT_FAILED = "alignment_failed"

    class Source(models.TextChoices):
        PHOTO = "photo"
        BATCH_PDF = "batch_pdf"

    version = models.ForeignKey(Version, on_delete=models.PROTECT, related_name="submissions")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    failure_reason = models.CharField(
        max_length=32, choices=FailureReason.choices, blank=True, default=""
    )
    roster_entry = models.ForeignKey(
        RosterEntry, on_delete=models.SET_NULL, null=True, blank=True, related_name="submissions"
    )
    student_label = models.CharField(max_length=200, blank=True, default="")
    total_score = models.FloatField(null=True, blank=True)
    raw_image_path = models.CharField(max_length=500)
    rectified_image_path = models.CharField(max_length=500, blank=True, default="")
    answer_hash = models.CharField(max_length=64, blank=True, default="")
    duplicate_of = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="duplicates"
    )
    source = models.CharField(max_length=16, choices=Source.choices)
    batch_id = models.UUIDField(null=True, blank=True)
    page_number = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = OwnedManager()

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"submission#{self.pk} ({self.status})"


class Answer(models.Model):
    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name="answers")
    question_no = models.PositiveIntegerField()  # canonical Question.order_index
    detected_options = models.JSONField()  # ["B"] / ["A", "C"] / []
    confidence = models.FloatField()
    flagged = models.BooleanField(default=False)
    flag_reason = models.CharField(max_length=50, blank=True, default="")
    correct = models.BooleanField(null=True, blank=True)
    score = models.FloatField(null=True, blank=True)
    manually_edited = models.BooleanField(default=False)
    edited_at = models.DateTimeField(null=True, blank=True)

    objects = OwnedManager()

    class Meta:
        ordering = ["question_no"]
        constraints = [
            models.UniqueConstraint(
                fields=["submission", "question_no"], name="answer_unique_question"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.submission_id}:Q{self.question_no}"


class AuditEvent(models.Model):
    """Append-only (R6.5). Passive reads are intentionally NOT audited (§6 Q13a)."""

    class Action(models.TextChoices):
        SCORED = "scored"
        OVERRIDDEN = "overridden"
        ASSIGNED = "assigned"
        RESCORED = "rescored"
        DUPLICATE_CONFIRMED = "duplicate_confirmed"
        SUGGESTED = "suggested"
        PRINTED = "printed"

    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="audit_events")
    submission = models.ForeignKey(
        Submission,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    actor_professor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="null = system action",
    )
    action = models.CharField(max_length=40, choices=Action.choices)
    detail = models.JSONField(default=dict)  # before/after
    created_at = models.DateTimeField(auto_now_add=True)

    objects = OwnedManager()

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        who = "system" if self.actor_professor_id is None else str(self.actor_professor_id)
        return f"audit[{self.action}] by {who}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ImmutableFieldError("AuditEvent is append-only (R6.5)")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableFieldError("AuditEvent is append-only (R6.5)")

    @property
    def is_system(self) -> bool:
        return self.actor_professor_id is None
