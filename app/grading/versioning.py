"""Version generation — question + option shuffling with anti-clustering.

Pure: no Django imports. Persistence is `app/core/versioning_service.py`.

REBUILD_SPEC §2 R2.1-R2.7, §6 Q9 / Q11 / Q12.

Terminology
-----------
`questions` is an ordered list of `(question_id, correct_indices)` where
`correct_indices` is a `frozenset` of canonical 0-based option indices (|set| >= 1).

A `VersionPlan` holds:
  - `question_order`: the `question_id`s permuted (R2.1);
  - `option_order`: `{question_id: [canonical_option_index at sheet position 0, 1, ...]}`
    — a genuine permutation of `range(n_options)` per question (R2.3);
  - `anticluster_fallback`: True iff `MAX_RESHUFFLE_ATTEMPTS` was exhausted and the
    least-skewed candidate was kept (R2.5 fallback, only on unsatisfiable tiny quizzes).

The correct answer is always recoverable from `question_order` + `option_order`
alone (R2.4): canonical option `i` sits at sheet position
`option_order[qid].index(i)`, i.e. sheet letter `chr(ord('A') + that position)`.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# --- named constants (R2.5; "module-level, tested for termination") -----------
MAX_CONSECUTIVE_SAME_LETTER = 2  # no run of 3+ questions sharing a correct letter
LETTER_COUNT_SLACK = 0.20  # 1/N + 20 percentage points
MAX_RESHUFFLE_ATTEMPTS = 200  # per version, before falling back (signed off 2026-09-09)


class InfeasibleVersionCount(ValueError):
    """Raised when `m` exceeds the number of distinct question orderings (R2.2)."""


@dataclass
class VersionPlan:
    question_order: list[int]
    option_order: dict[int, list[int]]
    anticluster_fallback: bool = False


def max_letter_count(num_questions: int, n_options: int) -> int:
    """Constraint 2 cap: `ceil(num_questions * (1/N + 0.20))` (R2.5)."""
    return math.ceil(num_questions * (1.0 / n_options + LETTER_COUNT_SLACK))


def distinct_orderings_at_least(num_questions: int, m: int) -> bool:
    """`num_questions! >= m`, without materialising a huge factorial (R2.2 saturating)."""
    product = 1
    for k in range(2, num_questions + 1):
        product *= k
        if product >= m:
            return True
    return product >= m


def correct_sheet_letters(option_order: list[int], correct_indices: frozenset[int]) -> set[str]:
    """Sheet letters the correct options land in for one question."""
    position_of = {canonical: sheet_pos for sheet_pos, canonical in enumerate(option_order)}
    return {_LETTERS[position_of[i]] for i in correct_indices}


def _random_permutation(n: int, rng: random.Random) -> list[int]:
    perm = list(range(n))
    rng.shuffle(perm)
    return perm


def _per_position_letters(
    question_order: list[int],
    option_order: dict[int, list[int]],
    correct_by_qid: dict[int, frozenset[int]],
) -> list[set[str]]:
    return [
        correct_sheet_letters(option_order[qid], correct_by_qid[qid]) for qid in question_order
    ]


def _histogram(per_pos: list[set[str]], n_options: int) -> tuple[int, ...]:
    counts = [0] * n_options
    for letters in per_pos:
        for letter in letters:
            counts[_LETTERS.index(letter)] += 1
    return tuple(counts)


def _offending_positions(per_pos: list[set[str]], n_options: int, cap: int) -> set[int]:
    """Positions (in question_order) that must be re-rolled to satisfy R2.5."""
    offenders: set[int] = set()
    run_window = MAX_CONSECUTIVE_SAME_LETTER + 1
    letters = _LETTERS[:n_options]

    # constraint 1 — per letter, no `run_window` consecutive questions all containing it
    for letter in letters:
        for start in range(len(per_pos) - run_window + 1):
            window = range(start, start + run_window)
            if all(letter in per_pos[p] for p in window):
                offenders.update(window)

    # constraint 2 — per-letter total <= cap
    for letter in letters:
        hits = [p for p, s in enumerate(per_pos) if letter in s]
        if len(hits) > cap:
            offenders.update(hits)

    return offenders


def _skew(per_pos: list[set[str]], n_options: int, cap: int) -> tuple[int, int, int]:
    """Lower is better. Used to pick the least-skewed fallback candidate."""
    hist = _histogram(per_pos, n_options)
    over_cap = sum(max(0, c - cap) for c in hist)
    run_excess = 0
    for letter in _LETTERS[:n_options]:
        streak = 0
        for s in per_pos:
            streak = streak + 1 if letter in s else 0
            if streak > MAX_CONSECUTIVE_SAME_LETTER:
                run_excess += 1
    spread = max(hist) - min(hist)
    return (over_cap, run_excess, spread)


def _build_option_orders(
    question_order: list[int],
    correct_by_qid: dict[int, frozenset[int]],
    n_options: int,
    cap: int,
    seen_histograms: set[tuple[int, ...]],
    rng: random.Random,
) -> tuple[dict[int, list[int]], bool]:
    option_order = {qid: _random_permutation(n_options, rng) for qid in question_order}
    best: tuple[tuple[int, int, int], dict[int, list[int]]] | None = None

    for _ in range(MAX_RESHUFFLE_ATTEMPTS + 1):
        per_pos = _per_position_letters(question_order, option_order, correct_by_qid)
        offenders = _offending_positions(per_pos, n_options, cap)
        hist_clash = _histogram(per_pos, n_options) in seen_histograms

        if not offenders and not hist_clash:
            return option_order, False

        skew = _skew(per_pos, n_options, cap)
        if best is None or skew < best[0]:
            best = (skew, {qid: order[:] for qid, order in option_order.items()})

        if offenders:
            reroll_positions = offenders
        else:  # histogram-only clash: perturb a random slice
            k = max(1, len(question_order) // 4)
            reroll_positions = set(rng.sample(range(len(question_order)), k))
        for pos in reroll_positions:
            qid = question_order[pos]
            option_order[qid] = _random_permutation(n_options, rng)

    assert best is not None
    return best[1], True


def generate_versions(
    questions: list[tuple[int, frozenset[int]]],
    *,
    n_options: int,
    m: int,
    seed: int | None = None,
) -> list[VersionPlan]:
    """Produce `m` version plans. Raises before generating anything on a bad request."""
    if m < 1:
        raise ValueError("m must be >= 1")
    if not questions:
        raise ValueError("quiz has no questions")
    if not 2 <= n_options <= 6:
        raise ValueError("n_options must be between 2 and 6")
    for qid, correct in questions:
        if not correct or any(not 0 <= i < n_options for i in correct):
            raise ValueError(f"question {qid}: correct indices must be a non-empty subset of 0..{n_options - 1}")

    num_questions = len(questions)
    if not distinct_orderings_at_least(num_questions, m):
        raise InfeasibleVersionCount(
            f"cannot generate {m} versions with distinct question orders for a "
            f"{num_questions}-question quiz — maximum is {num_questions}!"
        )

    rng = random.Random(seed)
    qids = [qid for qid, _ in questions]
    correct_by_qid = {qid: correct for qid, correct in questions}
    cap = max_letter_count(num_questions, n_options)

    plans: list[VersionPlan] = []
    seen_question_orders: set[tuple[int, ...]] = set()
    seen_histograms: set[tuple[int, ...]] = set()

    for _ in range(m):
        while True:  # distinct question order (R2.2); terminates — feasibility checked above
            question_order = qids[:]
            rng.shuffle(question_order)
            if tuple(question_order) not in seen_question_orders:
                seen_question_orders.add(tuple(question_order))
                break

        option_order, fallback = _build_option_orders(
            question_order, correct_by_qid, n_options, cap, seen_histograms, rng
        )
        per_pos = _per_position_letters(question_order, option_order, correct_by_qid)
        seen_histograms.add(_histogram(per_pos, n_options))
        plans.append(VersionPlan(question_order, option_order, fallback))

    return plans
