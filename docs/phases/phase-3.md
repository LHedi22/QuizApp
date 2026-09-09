# Phase 3 — Version generation

> Source: `docs/REBUILD_SPEC.md` §5 (Phases table, row 3), §2 R2.1–R2.7, §6 Q9, Q11,
> Q12. Governing rules: `docs/CLAUDE.md` (esp. rules 5 and 8).

## Phase goal

Generate `M` exam versions from a quiz's canonical questions: an independently
shuffled question order per version and an independently shuffled option order per
question, with the exact multi-correct-aware anti-clustering of R2.5, a hard
feasibility guard, provable termination, and shuffle maps that are written **once**
and never touched again.

## ⚠ One data-model addition needs sign-off (CLAUDE.md rule 5)

R2.5's fallback path ("falls back to the least-skewed candidate seen and **records
that in the version row**") implies a `version` column that Appendix A doesn't list.
See "Decision for sign-off" below — nothing is built until it's approved.

## What Phase 3 does NOT do

- No PDF (Phase 4). Phase 3 produces `Version` rows (`question_order`,
  `option_order`, `qr_id`, `template_version`) — the paper comes later.
- No re-generation / re-shuffle path — by design (R2.7). Generating is a one-shot,
  append-only operation.
- `template_version` on new versions = whatever `sheet_template.json` currently
  says (`load_template().template_version`, = 1 today).

---

## Subtask 3.1 — Pure generator core (R2.1, R2.3, R2.4)

**Goal.** A pure function in `app/grading` that produces `M` version plans (question
order + per-question option order) with genuine permutations and recoverable keys.

**Deliverables.**
- `app/grading/versioning.py`:
  - `@dataclass VersionPlan(question_order: list[int], option_order: dict[int, list[int]],
    anticluster_fallback: bool)`
  - `generate_versions(questions, *, n_options, m, seed=None) -> list[VersionPlan]`
    where `questions` is an ordered list of `(question_id, correct_indices: frozenset[int])`
    (canonical 0-based option indices).
  - Deterministic given `seed` (a `random.Random(seed)` internally) — so tests and
    re-runs are reproducible; production passes `seed=None` for OS randomness.
  - `question_order` = the `question_id`s permuted; `option_order[qid]` = a
    permutation of `range(n_options)` (canonical index at each sheet position).
  - `correct_sheet_letters(plan, qid, correct_indices, n_options) -> set[str]` helper:
    canonical index `i` sits at sheet position `plan.option_order[qid].index(i)` →
    letter. Used by the anti-cluster pass and by the recovery test.
- `tests/test_versioning_core.py`.

**Definition of Done (runnable).**
1. `pytest tests/test_versioning_core.py -q`:
   - `M` plans returned; each `question_order` is a permutation of the input ids;
   - each `option_order[qid]` is a permutation of `range(n_options)` — **every
     question of every version** (R2.3);
   - **key recovery (R2.4):** for a fixed input, reconstruct each question's correct
     **sheet letters** purely from `question_order` + `option_order`, map back to
     canonical indices, and assert equality with the input `correct_indices` — for
     ≥ 3 versions, ≥ 3 questions each, including ≥ 1 where both the question order
     and that question's option order are non-identity, and ≥ 1 multi-correct
     question;
   - same `seed` → identical plans; different `seed` → different (with overwhelming
     probability at realistic sizes).
2. `pytest tests/test_purity.py` green (`app.grading` stays web-framework-free).

---

## Subtask 3.2 — Feasibility guard + `M`/empty guards (R2.2, R2.6)

**Goal.** Reject an impossible request before anything is generated or written.

**Deliverables.**
- In `versioning.py`: `class InfeasibleVersionCount(ValueError)`.
- `distinct_orderings_at_least(num_questions, m) -> bool` — `num_questions!` vs `m`
  with a **saturating** compare (never actually computes a 5000! ; stop multiplying
  once the running product exceeds `m`).
- `generate_versions` raises:
  - `ValueError` if `m < 1` or `questions` is empty (R2.6);
  - `InfeasibleVersionCount` if `m` exceeds the number of distinct question orderings
    (R2.2) — message: `"cannot generate M versions with distinct question orders for
    a Q-question quiz — maximum is Q!"`.
- No two returned `question_order`s are identical (R2.2) — enforced by
  rejection-resampling, which terminates because the feasibility guard passed.

**Definition of Done (runnable).**
1. `pytest tests/test_versioning_feasibility.py -q`:
   - `m=0`, `m=-1`, empty questions → `ValueError`, no plans;
   - `Q=3, m=7` → `InfeasibleVersionCount` (3! = 6); `Q=3, m=6` → OK, all 6
     `question_order`s distinct and together they are exactly the 6 permutations;
   - `Q=3, m=5` → OK, 5 distinct;
   - `Q=50, m=20` → OK, fast (saturating compare doesn't touch `50!`);
   - `distinct_orderings_at_least(50, 20)` returns quickly (< 1 ms).

---

## Subtask 3.3 — Anti-clustering (R2.5, exact + multi-correct-aware)

**Goal.** Every version satisfies both R2.5 constraints; offending questions are
re-rolled up to a bound; provable termination with a recorded fallback.

**Deliverables.**
- Module-level named constants in `versioning.py`:
  - `MAX_CONSECUTIVE_SAME_LETTER = 2` (no run of 3+ — constraint 1);
  - `LETTER_COUNT_SLACK = 0.20` → `max_letter_count(num_questions, n_options) =
    ceil(num_questions * (1/n_options + LETTER_COUNT_SLACK))` (constraint 2);
  - `MAX_RESHUFFLE_ATTEMPTS = <value — see sign-off>`.
- The anti-cluster pass, per version:
  - build each **letter's** occurrence list over the shuffled question order: a
    question contributes letter `L` if `L ∈ correct_sheet_letters(...)` — **every**
    letter of a multi-correct `K` counts once (Q11);
  - constraint 1: for each letter independently, no `MAX_CONSECUTIVE_SAME_LETTER + 1`
    consecutive questions all contain that letter;
  - constraint 2: for each letter, its total ≤ `max_letter_count(...)`;
  - also: this version's per-letter histogram tuple must not equal any
    already-accepted version's in the batch;
  - while any of the above fails and attempts remain: re-roll the `option_order` of
    the questions contributing to the failure, recompute;
  - if attempts exhausted: keep the **least-skewed** candidate seen (skew =
    max letter count − ideal, tie-broken by run-length excess), set
    `anticluster_fallback = True`.
- The whole thing terminates unconditionally (bounded loop).
- `tests/test_versioning_anticluster.py`.

**Definition of Done (runnable).**
1. `pytest tests/test_versioning_anticluster.py -q`:
   - for a realistic quiz (Q=40, N=4, mixed single/multi correct, `m=10`, several
     seeds): **every** version satisfies constraint 1 and constraint 2, and all
     `m` per-letter histograms are pairwise distinct; `anticluster_fallback` is
     `False` for all;
   - a constructed multi-correct case where letters B,C are both correct on
     questions that would otherwise form a run — assert the per-letter run check
     catches it (Q11 semantics);
   - **termination (pathological):** `Q=3, N=2, m=1` (constraints unsatisfiable) →
     returns within `MAX_RESHUFFLE_ATTEMPTS`, `anticluster_fallback = True`, does
     not hang (wrap in a timeout / attempt-counter assertion);
   - `max_letter_count(40, 4) == ceil(40*0.45) == 18`; `max_letter_count(100, 5)
     == 40`; `max_letter_count(80, 6) == ceil(80*(1/6+0.2)) == ceil(29.33) == 30`.

---

## Subtask 3.4 — Persist versions + one-shot immutability (R2.1, R2.7, R2.6)

**Goal.** Turn version plans into `Version` rows atomically; flip the quiz to
`versioned`; prove there is no re-shuffle path.

**Deliverables.**
- `app/core/versioning_service.py`:
  - `generate_versions_for_quiz(quiz, m, *, seed=None) -> list[Version]`:
    - requires `quiz.status == "draft"` and `quiz.questions.exists()` else raises;
    - calls the pure `generate_versions` with the quiz's questions + `N`;
    - on any guard failure (`ValueError` / `InfeasibleVersionCount`) → **nothing
      written**, exception propagates;
    - inside `transaction.atomic()`: `bulk_create` `Version` rows
      (`version_number` 1..m, `qr_id` auto uuid4, `question_order`, `option_order`
      keyed by str(qid), `template_version = load_template().template_version`,
      `anticluster_fallback`); set `quiz.status = "versioned"`.
  - No `regenerate` / `reshuffle` / `update_version_maps` function anywhere.
- `tests/test_versioning_service.py` + extend `tests/test_immutability.py`.

**Definition of Done (runnable).**
1. `pytest tests/test_versioning_service.py -q` (Postgres):
   - draft quiz with N questions → `m` `Version` rows, `version_number` 1..m,
     distinct `qr_id`s, `quiz.status == "versioned"`, questions now frozen
     (`ingest_quiz` raises — ties to 2.4);
   - `InfeasibleVersionCount` / `m=0` / no questions → `Version.objects.count()`
     unchanged, `quiz.status` still `draft`;
   - round-trip: load a `Version` row, reconstruct a sampled question's correct
     sheet letters from the **DB** `question_order` / `option_order`, match the
     source question (R2.4 end-to-end).
2. Introspection (R2.7): a test asserts `app.core` exposes **no** callable whose
   name matches `re.compile(r"(reshuffle|regenerate).*version|update.*(question|option)_order")`
   and that `Version` has no serializer/form; plus the live DB-trigger test from
   Phase 1 still passes.
3. `bash scripts/ci.sh` green.

---

## Decision for sign-off

### E1 — `version.anticluster_fallback` column
R2.5 says the generator "records [the fallback] in the version row". Appendix A's
`version` has no such field.
**Proposal:** add `anticluster_fallback = models.BooleanField(default=False)` to
`Version` (a new migration `0003`). `True` only when `MAX_RESHUFFLE_ATTEMPTS` was
exhausted and a least-skewed candidate was used — i.e. a pathologically small quiz.
Surfaced read-only in the Django admin and (Phase 8) the version list so the
professor knows that version's answer distribution is more skewed than target.
**Alternative:** don't store it; log a warning only. Rejected — R2.5 explicitly says
"records that in the version row", and a professor auditing a skewed version needs
to see *why*.
**Also confirm:** `MAX_RESHUFFLE_ATTEMPTS` value. **Proposal: 200** (per version;
generous headroom for realistic quizzes where 0–2 re-rolls is typical, still a
fraction of a second, and small enough that the pathological case fails fast).

---

## Phase 3 exit checklist

- [x] E1 signed off 2026-09-09 (`version.anticluster_fallback`, `MAX_RESHUFFLE_ATTEMPTS=200`)
- [x] 3.1 generator core — permutations + key recovery (multi-correct, non-identity)
      tests green; pure  (commit c269d77)
- [x] 3.2 feasibility — `m<1`/empty/`InfeasibleVersionCount` + saturating compare  (c269d77)
- [x] 3.3 anti-clustering — both R2.5 constraints hold every version, histograms
      distinct, `max_letter_count` matches spec, pathological case → fallback in <3s  (c269d77)
- [x] 3.4 persist — atomic `Version` creation, `status→versioned`, no re-shuffle
      path (regex introspection), DB round-trip key recovery  (commit 3b25c22, verified)
- [x] `scripts/ci.sh` green — `189 passed`, clean-DB migrate `0001`+`0002`+`0003`,
      `makemigrations --check` 0  (verified via podman Postgres; re-run on `docker`
      runtime once Docker Desktop is healthy)

**Phase 3 complete.**
