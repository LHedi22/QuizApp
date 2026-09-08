class ImmutableFieldError(Exception):
    """Raised when code attempts to mutate a field that is immutable after creation.

    Covers `Version.question_order` / `Version.option_order` / `Version.qr_id`
    (REBUILD_SPEC §2 R2.7) and any update/delete of an `AuditEvent` (R6.5). The
    database enforces the same rules with triggers (migration 0002); this exception
    is the app-layer guard so the failure is a clean, catchable error rather than a
    raw `django.db` exception.
    """
