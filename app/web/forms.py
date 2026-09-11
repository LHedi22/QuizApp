from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import ValidationError as DjangoValidationError

from app.core.models import Quiz, Submission
from app.core.review_service import parse_roster
from app.core.services import create_quiz

_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

Professor = get_user_model()


class RegisterForm(forms.ModelForm):
    password1 = forms.CharField(label="Password", strip=False, widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirm password", strip=False, widget=forms.PasswordInput)

    class Meta:
        model = Professor
        fields = ["email"]

    def clean_email(self) -> str:
        email = self.cleaned_data["email"].lower()
        if Professor.objects.filter(email=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "The two password fields didn't match.")
        if p1:
            password_validation.validate_password(p1, self.instance)
        return cleaned

    def save(self, commit: bool = True) -> Professor:
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


_MARKING_MODE_CHOICES = Quiz.MarkingMode.choices


class QuizCreateForm(forms.Form):
    """Create a quiz (R1.1). Delegates to `services.create_quiz` so the same
    field-keyed validation runs whether the caller is this form or a script.
    """

    title = forms.CharField(max_length=200)
    options_per_question = forms.TypedChoiceField(
        choices=[(n, str(n)) for n in range(2, 7)],
        coerce=int,
        label="Options per question",
        help_text="2–6, uniform for the whole quiz. Fixed once set.",
    )
    marking_mode = forms.ChoiceField(choices=_MARKING_MODE_CHOICES)
    negative_marking = forms.BooleanField(required=False)
    default_points = forms.FloatField(min_value=0, initial=1.0)

    def save(self, professor) -> Quiz:
        """Create and return the quiz. Call only after `is_valid()`."""
        c = self.cleaned_data
        try:
            return create_quiz(
                professor=professor,
                title=c["title"],
                options_per_question=c["options_per_question"],
                marking_mode=c["marking_mode"],
                negative_marking=c["negative_marking"],
                default_points=c["default_points"],
            )
        except DjangoValidationError as exc:  # pragma: no cover - form fields catch these first
            for field, messages in exc.message_dict.items():
                for message in messages:
                    self.add_error(field if field in self.fields else None, message)
            raise


class VersionGenerateForm(forms.Form):
    """Request `M` shuffled versions (R2.1). Feasibility (R2.2) is enforced by the
    generator, not here — the view surfaces its error.
    """

    m = forms.IntegerField(min_value=1, label="Number of versions")


class AnswerOverrideForm(forms.Form):
    """Professor-supplied marked-option set for one answer (R6.3). `A..` up to the
    question's option count."""

    def __init__(self, *args, n_options: int, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["marked_options"] = forms.MultipleChoiceField(
            required=False,
            widget=forms.CheckboxSelectMultiple,
            choices=[(_LETTERS[i], _LETTERS[i]) for i in range(n_options)],
        )


class StudentAssignForm(forms.Form):
    """Assign a submission to a student (R6.4): pick a roster entry OR type free
    text — exactly one."""

    student_label = forms.CharField(required=False, max_length=200)

    def __init__(self, *args, quiz, instance: Submission | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["roster_entry"] = forms.ModelChoiceField(
            required=False,
            queryset=quiz.roster_entries.all(),
            empty_label="— free text —",
        )
        if instance is not None and not self.is_bound:
            self.fields["roster_entry"].initial = instance.roster_entry_id
            self.fields["student_label"].initial = instance.student_label

    def clean(self):
        cleaned = super().clean()
        roster_entry = cleaned.get("roster_entry")
        label = (cleaned.get("student_label") or "").strip()
        if roster_entry and label:
            raise forms.ValidationError("Pick a roster entry or type a name — not both.")
        if not roster_entry and not label:
            raise forms.ValidationError("Pick a roster entry or type a name.")
        return cleaned


class RosterPasteForm(forms.Form):
    """Paste a per-quiz roster (R6.4): one `name` or `name, external_id` per line."""

    text = forms.CharField(widget=forms.Textarea, required=False, label="Roster (one per line)")

    def clean_text(self) -> str:
        text = self.cleaned_data["text"]
        try:
            parse_roster(text)
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from exc
        return text


class QuestionUploadForm(forms.Form):
    """Upload a `.xlsx` question spreadsheet (R1.2). The heavy validation is the
    Phase 2 `ingest_quiz` parser; this only rejects the obviously-wrong file type.
    """

    file = forms.FileField(label="Question spreadsheet (.xlsx)")

    def clean_file(self):
        f = self.cleaned_data["file"]
        if not f.name.lower().endswith(".xlsx"):
            raise forms.ValidationError("Upload an .xlsx file (xlsx only, no CSV).")
        return f


class SubmissionPhotoUploadForm(forms.Form):
    """Upload one handheld-phone photo of a filled answer sheet (R4.1a), scanned
    against a single pre-selected `Version` (Phase 7, 2026-09-11 decision)."""

    image = forms.ImageField(label="Answer sheet photo")


class SubmissionBatchUploadForm(forms.Form):
    """Upload a multi-page PDF scan (R4.1b/R5.4) — each page becomes an
    independent submission against the pre-selected `Version`."""

    file = forms.FileField(label="Batch PDF (one page per sheet)")

    def clean_file(self):
        f = self.cleaned_data["file"]
        if not f.name.lower().endswith(".pdf"):
            raise forms.ValidationError("Upload a .pdf file.")
        return f


class QuizConfigForm(forms.ModelForm):
    """Edit a quiz's title + grading config. `options_per_question` is deliberately
    not editable — changing N would invalidate already-ingested option counts.
    """

    class Meta:
        model = Quiz
        fields = ["title", "marking_mode", "negative_marking", "default_points"]

    def clean_default_points(self) -> float:
        value = self.cleaned_data["default_points"]
        if value is not None and value < 0:
            raise forms.ValidationError("Default points must be non-negative.")
        return value
