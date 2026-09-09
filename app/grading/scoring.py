"""The single scoring implementation (REBUILD_SPEC §2 R7, §6 Q1).

`score_question` is the *only* place a question's score is computed. The scan
pipeline (Phase 7) and every manual professor correction (Phase 9) call this exact
function — they can never diverge (R7.5). Pure: no I/O, no Django.

Formulae, verbatim from R7:

  c = |M ∩ K|   (correct options selected)
  w = |M \\ K|   (incorrect options selected)
  k = |K|       (size of the correct set, k ≥ 1)

  R7.1  M = ∅                        → 0, under every toggle combination
  R7.2  mode = partial
          fraction = (c − w) / k
          negative off → points · max(0, fraction)     (floored at 0 per question)
          negative on  → points · fraction              (NOT floored — R7.4;
                                                          may be < −points for
                                                          multi-correct, confirmed)
  R7.3  mode = all_or_nothing
          M = K exactly → points
          M ≠ K, M ≠ ∅  → 0 (negative off) or −points (negative on)
"""

from __future__ import annotations

from collections.abc import Iterable

PARTIAL = "partial"
ALL_OR_NOTHING = "all_or_nothing"
_MODES = frozenset({PARTIAL, ALL_OR_NOTHING})


def score_question(
    marked_set: Iterable[str],
    key_set: Iterable[str],
    points: float,
    mode: str,
    negative: bool,
) -> float:
    """Score one question. See module docstring for the formulae (R7)."""
    if mode not in _MODES:
        raise ValueError(f"mode must be one of {sorted(_MODES)}, got {mode!r}")

    key = frozenset(key_set)
    if not key:
        raise ValueError("key_set must contain at least one correct option (k >= 1)")
    marked = frozenset(marked_set)
    points = float(points)

    # R7.1 — an unanswered question scores 0 regardless of mode / negative marking.
    if not marked:
        return 0.0

    if mode == ALL_OR_NOTHING:
        # R7.3
        if marked == key:
            return points
        return -points if negative else 0.0

    # R7.2 — partial credit
    k = len(key)
    c = len(marked & key)
    w = len(marked - key)
    fraction = (c - w) / k
    if negative:
        return points * fraction
    return points * max(0.0, fraction)
