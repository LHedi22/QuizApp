from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model, password_validation

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
