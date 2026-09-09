"""Phase 3.1 DoD: pure generator core — permutations + key recovery (R2.1/R2.3/R2.4)."""
from __future__ import annotations

from app.grading.versioning import correct_sheet_letters, generate_versions

_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def make_questions(n_q: int, n_opt: int, *, multi_every: int = 0):
    out = []
    for i in range(n_q):
        qid = 100 + i
        if multi_every and i % multi_every == 0:
            correct = frozenset({0, min(2, n_opt - 1)})
        else:
            correct = frozenset({i % n_opt})
        out.append((qid, correct))
    return out


def test_returns_m_plans_over_the_same_question_set():
    qs = make_questions(20, 4)
    plans = generate_versions(qs, n_options=4, m=10, seed=1)
    assert len(plans) == 10
    qids = {q for q, _ in qs}
    for p in plans:
        assert set(p.question_order) == qids
        assert len(p.question_order) == len(qids)  # no dupes


def test_option_order_is_a_permutation_every_question_every_version():
    qs = make_questions(15, 5)
    for p in generate_versions(qs, n_options=5, m=8, seed=2):
        for qid in p.question_order:
            assert sorted(p.option_order[qid]) == [0, 1, 2, 3, 4]


def test_key_recovery_roundtrip_incl_multi_and_non_identity():
    qs = make_questions(12, 4, multi_every=4)
    correct_by_qid = dict(qs)
    plans = generate_versions(qs, n_options=4, m=5, seed=3)

    non_identity_option_orders = 0
    multi_checked = 0
    for p in plans:
        for qid in p.question_order:
            key = correct_by_qid[qid]
            sheet_letters = correct_sheet_letters(p.option_order[qid], key)
            recovered = {p.option_order[qid][_LETTERS.index(letter)] for letter in sheet_letters}
            assert recovered == set(key)
            if p.option_order[qid] != [0, 1, 2, 3]:
                non_identity_option_orders += 1
            if len(key) > 1:
                multi_checked += 1
    assert non_identity_option_orders >= 1
    assert multi_checked >= 1
    assert any(p.question_order != [q for q, _ in qs] for p in plans)  # non-identity q-order


def test_deterministic_with_seed():
    qs = make_questions(20, 4)
    a = generate_versions(qs, n_options=4, m=6, seed=42)
    b = generate_versions(qs, n_options=4, m=6, seed=42)
    assert [(p.question_order, p.option_order) for p in a] == [
        (p.question_order, p.option_order) for p in b
    ]
    c = generate_versions(qs, n_options=4, m=6, seed=43)
    assert [p.question_order for p in a] != [p.question_order for p in c]
