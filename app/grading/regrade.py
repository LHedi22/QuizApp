"""Pure regrade helpers for the Phase 9 manual-override path (REBUILD_SPEC R6.3).

No Django, no I/O. The override service in `app/core/review_service.py` composes
these with `score_question` (R7.5) and the ORM.
"""

from __future__ import annotations

from collections.abc import Iterable

NEEDS_REVIEW = "needs_review"
FINALIZED = "finalized"


def submission_total(scores: Iterable[float | None]) -> float:
    """Sum of per-answer scores; an ungraded answer (`None`) contributes 0."""
    return float(sum(s for s in scores if s is not None))


def status_after_override(current: str, any_flagged: bool) -> str:
    """R6.3 local rule: a `needs_review` submission with nothing still flagged
    finalizes; a `finalized` submission stays finalized; anything else is
    unchanged. (The full R5.7 confidence gate is Phase 6/7, never run here.)
    """
    if current == NEEDS_REVIEW and not any_flagged:
        return FINALIZED
    return current
