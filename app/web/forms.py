from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import ValidationError as DjangoValidationError

from app.core.models import Quiz
from app.core.services import create_quiz

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
