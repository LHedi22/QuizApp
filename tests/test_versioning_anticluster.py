"""Phase 3.3 DoD: R2.5 anti-clustering — exact, multi-correct-aware, terminates."""
from __future__ import annotations

import time

import pytest

from app.grading.versioning import (
    MAX_CONSECUTIVE_SAME_LETTER,
    _histogram,
    _offending_positions,
    _per_position_letters,
    correct_sheet_letters,
    generate_versions,
    max_letter_count,
)
from tests.test_versioning_core import make_questions

_LETTERS = "ABCDEF"


def _per_pos(plan, correct_by_qid):
    return [
        correct_sheet_letters(plan.option_order[qid], correct_by_qid[qid])
        for qid in plan.question_order
    ]


def _assert_constraints_hold(plan, correct_by_qid, n_options):
    per_pos = _per_pos(plan, correct_by_qid)
    cap = max_letter_count(len(per_pos), n_options)
    for letter in _LETTERS[:n_options]:
        total = sum(1 for s in per_pos if letter in s)
        assert total <= cap, f"letter {letter}: {total} > cap {cap}"
        streak = 0
        for s in per_pos:
            streak = streak + 1 if letter in s else 0
            assert streak <= MAX_CONSECUTIVE_SAME_LETTER, f"letter {letter}: run {streak}"


@pytest.mark.parametrize("seed", range(6))
def test_realistic_quiz_all_versions_satisfy_r2_5(seed):
    qs = make_questions(40, 4, multi_every=7)
    correct_by_qid = dict(qs)
    plans = generate_versions(qs, n_options=4, m=10, seed=seed)

    for plan in plans:
        assert plan.anticluster_fallback is False
        _assert_constraints_hold(plan, correct_by_qid, 4)

    histograms = [_histogram(_per_pos(p, correct_by_qid), 4) for p in plans]
    assert len(set(histograms)) == len(histograms), "version histograms must be pairwise distinct"


def test_max_letter_count_matches_spec_examples():
    assert max_letter_count(40, 4) == 18  # ceil(40 * 0.45)
    assert max_letter_count(100, 5) == 40  # ceil(100 * 0.40)
    assert max_letter_count(80, 6) == 30  # ceil(80 * 0.3666..)
    assert max_letter_count(4, 4) == 2  # ceil(4 * 0.45) = ceil(1.8)


def test_offending_positions_tracks_each_letter_independently_for_multi_correct():
    # letter B is correct on positions 0,1,2 (a run of 3) — regardless of the other
    # letters in those questions' correct sets (Q11 semantics).
    per_pos = [{"B"}, {"B", "A"}, {"B", "C"}, {"D"}]
    offenders = _offending_positions(per_pos, n_options=4, cap=99)
    assert {0, 1, 2} <= offenders


def test_offending_positions_flags_over_cap_letter():
    per_pos = [{"A"}] * 5 + [{"B"}]
    offenders = _offending_positions(per_pos, n_options=4, cap=3)
    assert {0, 1, 2, 3, 4} <= offenders  # the five A positions


def test_pathological_unsatisfiable_quiz_terminates_with_fallback():
    # N=2, every question has BOTH options correct → letter A appears in every
    # question → a run of 3 is unavoidable and un-re-rollable.
    qs = [(1, frozenset({0, 1})), (2, frozenset({0, 1})), (3, frozenset({0, 1}))]
    start = time.perf_counter()
    plans = generate_versions(qs, n_options=2, m=1, seed=1)
    assert time.perf_counter() - start < 3.0
    assert plans[0].anticluster_fallback is True


def test_histogram_helper_counts_multi_correct_letters_once_each():
    per_pos = [{"A", "C"}, {"A"}, {"B"}]
    assert _histogram(per_pos, 4) == (2, 1, 1, 0)


def test_per_position_letters_shape():
    qs = make_questions(6, 4)
    plan = generate_versions(qs, n_options=4, m=1, seed=0)[0]
    per_pos = _per_position_letters(plan.question_order, plan.option_order, dict(qs))
    assert len(per_pos) == 6
    assert all(isinstance(s, set) and s for s in per_pos)
