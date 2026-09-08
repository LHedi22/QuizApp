"""Owner-scoped access. Every domain object belongs to exactly one professor via a
FK chain rooted at `Quiz.professor` (REBUILD_SPEC §2 R0.2). These helpers are the
single funnel views use so ownership can never be forgotten on a route.
"""

from __future__ import annotations

from django.contrib.auth.base_user import BaseUserManager
from django.db import models


class ProfessorManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email: str, password: str | None = None, **extra):
        if not email:
            raise ValueError("email is required")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, password: str | None = None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        if extra.get("is_staff") is not True or extra.get("is_superuser") is not True:
            raise ValueError("superuser must have is_staff=True and is_superuser=True")
        return self.create_user(email, password, **extra)


# Path from each model back to the owning professor, for `owned_by()`.
_OWNER_LOOKUP = {
    "Quiz": "professor",
    "Question": "quiz__professor",
    "Version": "quiz__professor",
    "RosterEntry": "quiz__professor",
    "Submission": "version__quiz__professor",
    "Answer": "submission__version__quiz__professor",
    "AuditEvent": "quiz__professor",
}


class OwnedQuerySet(models.QuerySet):
    def owned_by(self, user) -> OwnedQuerySet:
        lookup = _OWNER_LOOKUP[self.model.__name__]
        return self.filter(**{lookup: user})


OwnedManager = models.Manager.from_queryset(OwnedQuerySet)
