# Phase 2 — Quiz ingestion + scoring config

> Source: `docs/REBUILD_SPEC.md` §5 (Phases table, row 2), §2 R1.1–R1.5, §2 R7,
> §6 Q1, §6 Q2, §3.2A. Governing rules: `docs/CLAUDE.md`.

## Phase goal

Build the parts that turn "a professor's spreadsheet" into "canonical questions with a
grading config": the header-validated `.xlsx` parser (all-or-nothing, full error
lists), the per-quiz scoring configuration, and the **single shared `score_question`
pure function** that every later grading path calls (R7.5).

## Scoring formula note (CLAUDE.md rule 5)

§2 R7 + §6 Q1 specify the scoring formula **exactly and completely** ("exact,
resolved"). `score_question` is implemented *verbatim* from R7.1–R7.5 with an
exhaustive test battery covering every worked example in the spec. This is
implementing a locked spec, not making a decision — but if any genuine ambiguity
surfaces mid-implementation, **stop and ask** rather than assume.

## What Phase 2 does NOT do

- No version generation (Phase 3), no PDF (Phase 4), no OMR (Phase 5+).
- **No ingestion UI** — that's Phase 8 ("Dashboard + ingestion UI"). Phase 2 delivers
  the service/parser layer + tests; Phase 8 wires forms/views onto it.
- No second `score_question` call site yet — the pipeline (Phase 7) is where the
  R7.5 *parity* test (two call sites, identical output) is asserted. Phase 2 proves
  the function itself against hand-computed values.

## Environment note

DB-backed subtasks (2.2–2.4) need Postgres (`docker run ... postgres:16`). 2.1 and the
pure parser in 2.3 need no DB.

---

## Subtask 2.1 — `score_question` pure function (R7)

**Goal.** One pure function, in `app/grading`, that computes a single question's score
under every toggle combination — the only scoring implementation in the codebase.

**Deliverables.**
- `app/grading/scoring.py`:
  - `score_question(marked: set[str], key: set[str], points: float, mode: str,
    negative: bool) -> float`
  - `mode` accepts `"partial"` / `"all_or_nothing"` (the `Quiz.MarkingMode` values).
  - Exactly R7.1 (M=∅ → 0, always), R7.2 (partial: `fraction=(c−w)/k`;
    off → `points·max(0,fraction)`, on → `points·fraction`), R7.3 (all_or_nothing:
    `M==K` → points; `M≠K, M≠∅` → 0 / −points).
  - `c = |M ∩ K|`, `w = |M \ K|`, `k = |K|` (`k ≥ 1` assumed; raise on `k == 0`).
- `tests/test_scoring.py` — a battery where every expected value is hand-computed from
  R7 (see DoD).

**Definition of Done (runnable).**
1. `pytest tests/test_scoring.py -q` — passes, and includes **every worked example in
   §2 R7.2/R7.3**:
   - k=1 right → `points`; k=1 one wrong → `0` (off) / `−points` (on);
   - k=2 one-right-one-wrong → `0`; k=2 both right → `points`;
   - k=2 one right only, no wrong → `points·0.5` (off & on);
   - k=3, c=0,w=3, partial on → `−points` (lower bound);
   - `M=∅` → `0` for all four (mode × negative) combinations;
   - all_or_nothing `M==K` → `points`; `M⊊K` → `0` / `−points`; `M` with an extra
     wrong letter → `0` / `−points`.
2. A property check: `score_question` is pure (no I/O, deterministic) and never raises
   for `k ≥ 1`, any `M ⊆ {A..F}`.
3. `pytest tests/test_purity.py` still green (grading stays web-framework-free).

---

## Subtask 2.2 — Quiz creation + scoring config (R1.1, R7 config storage)

**Goal.** Create a quiz with its options-count `N` and full grading config, validated
server-side. Service layer only (UI is Phase 8).

**Deliverables.**
- `app/core/services.py`:
  - `create_quiz(*, professor, title, options_per_question, marking_mode,
    negative_marking, default_points) -> Quiz` — validates and persists.
  - Validation: `title` non-empty; `2 ≤ N ≤ 6`; `default_points ≥ 0`;
    `marking_mode ∈ {partial, all_or_nothing}`. Raises `ValidationError` with a
    field-keyed message on any failure (nothing written).
- `tests/test_quiz_service.py`.

**Definition of Done (runnable).**
1. `pytest tests/test_quiz_service.py -q`:
   - valid input → a `Quiz` with the right `professor`, `N`, `marking_mode`,
     `negative_marking`, `default_points`, `status == "draft"`;
   - `N=1`, `N=7`, `default_points=-0.5`, blank title, bad `marking_mode` → each
     raises, `Quiz.objects.count()` unchanged;
   - defaults applied: omitting `marking_mode` → `partial`; omitting
     `negative_marking` → `False`; omitting `default_points` → `1.0`.
2. The created quiz is only visible via `Quiz.objects.owned_by(professor)` (extends
   the 1.2 isolation guarantee to the creation path).

---

## Subtask 2.3 — `.xlsx` ingestion parser (R1.2, R1.3, R1.4)

**Goal.** Parse a `.xlsx` of questions for a given quiz: header-validated by name,
`N` option columns, `correct_options` set, optional `points`; **all-or-nothing** with
**every** header error and **every** per-row reason reported in one pass.

**Deliverables.**
- `openpyxl` added to `pyproject.toml` dependencies.
- `app/core/xlsx_ingest.py` — pure parse/validate (no DB):
  - `parse_workbook(source, *, n_options, max_chars_per_option, max_questions)
    -> ParseResult`
  - `ParseResult` = either `.questions: list[ParsedQuestion]` **or**
    `.header_errors: list[str]` + `.row_errors: list[RowError]` (row number + list of
    reasons). Never both.
  - Header check (before any row): required `question_text`, `option_1..option_N`,
    `correct_options`; optional `points`; report missing / misnamed / duplicated /
    wrong option-column count vs `N`.
  - Row checks (all reasons collected per row): empty `question_text`; ≠ `N` non-empty
    option cells; duplicate option text in a row; `correct_options` letter outside
    `A..<Nth>` or empty; `points` present but not a non-negative number; an option
    string longer than `max_chars_per_option` (R1.4 / §3.2A).
  - Whole-file: `> max_questions` rows → error (R3.2 capacity).
- `app/core/ingest.py` — `ingest_quiz(quiz, source) -> IngestResult`:
  - loads `app.sheet_template.load_template()`, passes `max_chars_per_option` and
    `capacity_for(quiz.options_per_question)` to the parser;
  - on success: creates `Question` rows in **file order** (`order_index` 1..n),
    single- vs multi-correct decided by `len(correct_options)`; returns success.
  - on failure: returns the structured errors, **creates nothing** (atomic).
- `tests/test_xlsx_ingest.py` (pure, no DB) + `tests/test_ingest.py` (DB).

**Definition of Done (runnable).**
1. `pytest tests/test_xlsx_ingest.py -q` — workbooks built in-test with `openpyxl`:
   - good file (mix of single + multi-correct, some blank `points`) → N
     `ParsedQuestion`s in order;
   - missing `question_text` header; `option_3` missing at `N=4`; duplicated
     `option_1` header → each → `header_errors`, no `row_errors`, no questions;
   - a row with 3 filled options at `N=4` **and** a bad `correct_options` **and** a
     negative `points` → one `RowError` listing **all three** reasons;
   - duplicate option text; `correct_options="E"` at `N=4`; empty `correct_options`;
     `points="abc"`; an option of 200 chars → each surfaces as a row reason;
   - `max_questions + 1` rows → whole-file error.
2. `pytest tests/test_ingest.py -q` (needs Postgres):
   - good file → `quiz.questions.count() == n`, ordered, correct multi flags;
   - any invalid file → `IngestResult` errors + `quiz.questions.count() == 0`
     (wrap in a transaction; assert rollback).

---

## Subtask 2.4 — Questions immutable after versioning (R1.5)

**Goal.** Re-upload / discard is allowed only while the quiz is `draft`; once a version
exists (`status ≥ versioned`) questions are frozen; once `printed` it's hard-locked.

**Deliverables.**
- `ingest_quiz`: refuse unless `quiz.status == "draft"` → `IngestBlocked`.
- `discard_questions(quiz)`: delete all questions, allowed only while `draft`.
- Re-ingest while `draft` replaces (discard + insert) atomically.
- `tests/test_question_immutability.py` (DB).

**Definition of Done (runnable).**
1. `pytest tests/test_question_immutability.py -q`:
   - ingest into a `draft` quiz, then ingest again → questions replaced, count correct;
   - set `quiz.status = "versioned"` → `ingest_quiz` and `discard_questions` both
     raise, questions unchanged;
   - set `quiz.status = "printed"` → same.
2. `bash scripts/ci.sh` green with the Phase 2 additions.

---

## Phase 2 exit checklist

- [ ] 2.1 `score_question` — full R7 worked-example battery green; stays pure
- [ ] 2.2 `create_quiz` — validation + defaults + ownership tests green
- [ ] 2.3 ingestion — header + per-row + whole-file error battery (pure) and the
      atomic-create/rollback tests (DB) green
- [ ] 2.4 R1.5 — draft-only re-upload/discard; frozen at `versioned`/`printed`
- [ ] `scripts/ci.sh` green
