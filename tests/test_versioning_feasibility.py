"""Phase 3.2 DoD: feasibility + M/empty guards reject before generating (R2.2/R2.6)."""
from __future__ import annotations

import itertools
import time

import pytest

from app.grading.versioning import (
    InfeasibleVersionCount,
    distinct_orderings_at_least,
    generate_versions,
)
from tests.test_versioning_core import make_questions


@pytest.mark.parametrize("bad_m", [0, -1, -5])
def test_m_below_one_raises(bad_m):
    with pytest.raises(ValueError):
        generate_versions(make_questions(5, 4), n_options=4, m=bad_m)


def test_empty_questions_raises():
    with pytest.raises(ValueError):
        generate_versions([], n_options=4, m=1)


def test_infeasible_m_raises():
    with pytest.raises(InfeasibleVersionCount):
        generate_versions(make_questions(3, 4), n_options=4, m=7, seed=1)  # 3! = 6


def test_m_equal_to_factorial_yields_all_permutations():
    qs = make_questions(3, 4)
    plans = generate_versions(qs, n_options=4, m=6, seed=1)
    orders = {tuple(p.question_order) for p in plans}
    assert orders == set(itertools.permutations([q for q, _ in qs]))


def test_m_just_below_factorial_all_distinct():
    plans = generate_versions(make_questions(3, 4), n_options=4, m=5, seed=2)
    assert len({tuple(p.question_order) for p in plans}) == 5


def test_large_quiz_is_feasible_and_fast():
    start = time.perf_counter()
    plans = generate_versions(make_questions(50, 4), n_options=4, m=20, seed=1)
    assert len(plans) == 20
    assert len({tuple(p.question_order) for p in plans}) == 20
    assert time.perf_counter() - start < 5.0


def test_saturating_compare():
    start = time.perf_counter()
    assert distinct_orderings_at_least(50, 20) is True
    assert distinct_orderings_at_least(1, 1) is True
    assert distinct_orderings_at_least(1, 2) is False
    assert distinct_orderings_at_least(3, 6) is True
    assert distinct_orderings_at_least(3, 7) is False
    assert distinct_orderings_at_least(4, 24) is True
    assert distinct_orderings_at_least(4, 25) is False
    assert time.perf_counter() - start < 0.05
