"""Phase 2.1 DoD: score_question implements §2 R7 exactly.

Every expected value below is hand-computed from R7.1 / R7.2 / R7.3. `points` is
varied away from 1.0 in places to prove the multiplication.
"""
from __future__ import annotations

import pytest

from app.grading.scoring import ALL_OR_NOTHING, PARTIAL, score_question

TOGGLES = [(PARTIAL, False), (PARTIAL, True), (ALL_OR_NOTHING, False), (ALL_OR_NOTHING, True)]


# --- R7.1: unanswered scores 0 under every toggle combination -----------------

@pytest.mark.parametrize(("mode", "negative"), TOGGLES)
@pytest.mark.parametrize("key", [{"A"}, {"A", "C"}, {"A", "B", "D"}])
def test_r7_1_unanswered_is_zero(mode, negative, key):
    assert score_question(set(), key, 3.0, mode, negative) == 0.0


# --- R7.2: partial mode ------------------------------------------------------

@pytest.mark.parametrize(
    ("marked", "key", "points", "negative", "expected"),
    [
        # single-correct k=1
        ({"A"}, {"A"}, 1.0, False, 1.0),          # right → (1-0)/1 = 1.0
        ({"A"}, {"A"}, 2.5, True, 2.5),           # right, points scale
        ({"B"}, {"A"}, 1.0, False, 0.0),          # one wrong → (0-1)/1 = -1 → max(0,-1)=0
        ({"B"}, {"A"}, 1.0, True, -1.0),          # one wrong, negative on → -points
        ({"B"}, {"A"}, 4.0, True, -4.0),
        # multi-correct k=2
        ({"A", "B"}, {"A", "C"}, 1.0, False, 0.0),  # one right + one wrong → (1-1)/2 = 0
        ({"A", "B"}, {"A", "C"}, 1.0, True, 0.0),
        ({"A", "C"}, {"A", "C"}, 1.0, False, 1.0),  # both right → (2-0)/2 = 1.0
        ({"A", "C"}, {"A", "C"}, 3.0, True, 3.0),
        ({"A"}, {"A", "C"}, 1.0, False, 0.5),       # one right only → (1-0)/2 = 0.5
        ({"A"}, {"A", "C"}, 1.0, True, 0.5),
        ({"A"}, {"A", "C"}, 2.0, False, 1.0),
        # lower-bound example from R7.2: k=3, c=0, w=3 → (0-3)/3 = -1
        ({"B", "D", "E"}, {"A", "C", "F"}, 1.0, True, -1.0),
        ({"B", "D", "E"}, {"A", "C", "F"}, 5.0, True, -5.0),
        ({"B", "D", "E"}, {"A", "C", "F"}, 1.0, False, 0.0),
        # confirmed: no per-question floor for negative-on multi-correct.
        # k=2, c=0, w=4 → (0-4)/2 = -2 → -2·points
        ({"B", "C", "D", "E"}, {"A", "F"}, 1.0, True, -2.0),
        ({"B", "C", "D", "E"}, {"A", "F"}, 3.0, True, -6.0),
        ({"B", "C", "D", "E"}, {"A", "F"}, 1.0, False, 0.0),  # floored at 0 when off
        # partial-overlap on multi: c=2, w=1, k=3 → (2-1)/3
        ({"A", "C", "E"}, {"A", "C", "F"}, 3.0, False, 1.0),
        ({"A", "C", "E"}, {"A", "C", "F"}, 3.0, True, 1.0),
    ],
)
def test_r7_2_partial(marked, key, points, negative, expected):
    got = score_question(marked, key, points, PARTIAL, negative)
    assert got == pytest.approx(expected)


# --- R7.3: all-or-nothing mode --------------------------------------------------

@pytest.mark.parametrize(
    ("marked", "key", "points", "negative", "expected"),
    [
        ({"A", "C"}, {"A", "C"}, 2.0, False, 2.0),   # exact match → points
        ({"A", "C"}, {"A", "C"}, 2.0, True, 2.0),
        ({"A"}, {"A", "C"}, 2.0, False, 0.0),        # subset → 0 / -points
        ({"A"}, {"A", "C"}, 2.0, True, -2.0),
        ({"A", "C", "D"}, {"A", "C"}, 2.0, False, 0.0),  # superset → 0 / -points
        ({"A", "C", "D"}, {"A", "C"}, 2.0, True, -2.0),
        ({"B"}, {"A"}, 1.0, False, 0.0),             # wrong single → 0 / -points
        ({"B"}, {"A"}, 1.0, True, -1.0),
        ({"A"}, {"A"}, 1.0, True, 1.0),              # right single → points
    ],
)
def test_r7_3_all_or_nothing(marked, key, points, negative, expected):
    got = score_question(marked, key, points, ALL_OR_NOTHING, negative)
    assert got == pytest.approx(expected)


# --- guards & purity ---------------------------------------------------------

def test_empty_key_raises():
    with pytest.raises(ValueError):
        score_question({"A"}, set(), 1.0, PARTIAL, False)


def test_bad_mode_raises():
    with pytest.raises(ValueError):
        score_question({"A"}, {"A"}, 1.0, "weighted", False)


@pytest.mark.parametrize(("mode", "negative"), TOGGLES)
def test_deterministic_and_never_raises_for_valid_input(mode, negative):
    letters = ["A", "B", "C", "D", "E", "F"]
    for k in range(1, 7):
        key = set(letters[:k])
        for size in range(0, 7):
            marked = set(letters[:size])
            a = score_question(marked, key, 1.0, mode, negative)
            b = score_question(marked, key, 1.0, mode, negative)
            assert a == b
            assert isinstance(a, float)


def test_accepts_any_iterable_not_just_sets():
    assert score_question(["A", "A"], ("A",), 1.0, PARTIAL, False) == 1.0
