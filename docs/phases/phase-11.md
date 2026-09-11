# Phase 11 — End-to-end + load

> Source: `docs/REBUILD_SPEC.md` §5 (Phases table, row 11). Governing rules:
> `docs/CLAUDE.md`.

## Phase goal

Happy path and unhappy path (bad spreadsheet row, ambiguous bubble,
unreadable QR, failed alignment, duplicate, upside-down scan, infeasible `M`
request) through the real UI + real backend; a class-scale batch (60 sheets,
5 versions, 100 questions) completes within a written time bound with no
correctness or memory regression.

This is the last phase in the §5 order that hasn't been built — Phases 8, 9,
and 12 were built out of order earlier (sanctioned parallel track while
5.2–7 were blocked on the corpus); Phase 10 (LLM suggestion aid) stays
deferred by spec ("build only if the Phase 9 review queue proves a real time
sink" — not yet established, so it is intentionally skipped here, not built).

## Shared test input: a real rendered-and-rasterized answer sheet

Every real corpus photo (Phase 0.7) is tied to one of 4 fixed corpus master
sheets with a fixed `qr_id` — it can't be scanned against a *freshly created*
quiz/version from Phase 11's own e2e flow (fresh versions get a fresh
`qr_id` from `generate_versions_for_quiz`, and real quizzes shuffle
`question_order`/`option_order`, unlike the corpus masters' identity
ordering). So Phase 11 needs its own scannable input, generated from
whatever quiz/version the test itself just created through the real UI.

`tests/conftest.py::render_filled_submission_image(version, fill_pattern)`:
renders the version's real answer-sheet PDF via Phase 4's actual
`render_and_store_version_pdfs`, rasterizes it via `pymupdf` exactly like
Phase 7's real batch-upload path, and draws filled bubbles onto the raster
at the real `bubble_centres()` mm positions. This exercises `align_page` /
`classify_page` for real (Stage A/B detection, QR decode) — not the
identity-homography shortcut Phase 6's synthetic accuracy tests use. It's
deliberately noise-free; real-capture noise robustness is Phase 5/6's
separate, already-established claim over the real corpus (rule 9). Phase 11
is about workflow correctness and throughput, not re-proving OMR accuracy.

## Subtask 11.1 — Happy path e2e

`tests/test_e2e_happy_path.py`: one test walks the full professor workflow
through the real Django views (no service-layer shortcuts): create quiz →
upload questions (.xlsx) → generate versions → download both PDFs per
version → mark a version printed → scan an all-correct submission (via the
shared render helper) → submission finalizes automatically → assign a
student label → the result shows up in the results list and the CSV export.
Every step asserts against the real DB state, not just response codes.

## Subtask 11.2 — Unhappy paths

`tests/test_e2e_unhappy_paths.py`, each through the real view that owns that
failure mode:
- **Bad spreadsheet row** (R1.3/R1.5): a row missing an option cell →
  `quiz_upload` returns 200 with the row error rendered, zero `Question`
  rows written (all-or-nothing).
- **Infeasible `M` request** (R2.2): a 1-question quiz (1! = 1 ordering)
  asked for `m=2` versions → `version_generate` redirects with an error
  message, zero `Version` rows written.
- **Unreadable QR / failed alignment** (R5.1): a blank white image posted to
  `submission_upload` → `FAILED`/`ALIGNMENT_FAILED`, zero `Answer` rows,
  inline error shown, raw image still saved (never silently dropped).
  Distinguished from a QR that decodes but doesn't match any known version
  (`version_not_found` — still surfaces as the same `ALIGNMENT_FAILED`
  reason today; documented in Phase 6/7, not re-litigated here) by directly
  exercising `app.omr.alignment.align_page` with a synthetic QR payload that
  isn't a UUID any `version_lookup` would resolve.
- **Ambiguous bubble** (R5.7): a rendered sheet with a mid-gray (neither
  clearly filled nor empty) mark on one bubble → that answer is flagged
  `ambiguous_bubble`, submission is `NEEDS_REVIEW`, `total_score` withheld.
- **Duplicate submission** (R5.8): the same rendered image submitted twice
  under the same version → matching `answer_hash`,
  `find_probable_duplicate` finds the first one, `duplicate_of` stays
  `None` (never auto-set — Appendix A; there's no UI wired to this yet per
  Phase 7's design, so this test calls the pipeline/helper directly rather
  than a nonexistent view).
- **Upside-down scan** (R5.2): the happy-path rendered image rotated 180°
  posted to `submission_upload` → fails cleanly (`FAILED`/
  `ALIGNMENT_FAILED`), never silently misgraded. This is the behavioral
  requirement R5.2 always carried; only the *corpus testing* requirement for
  it was dropped by the user's 2026-09-11 corpus-gate decision (§2 R5.2's
  behavior is still in scope, documented in `phase_status.md`).

## Subtask 11.3 — Class-scale load

`scripts/load_test.py`: a standalone script (not part of `pytest -q`, since
it's a timed benchmark, not a correctness gate) that builds a 100-question,
N=4 quiz, generates 5 versions, and runs 60 rendered-and-filled submissions
(12 per version, all-correct patterns) through `process_batch` — the same
orchestrator the real batch-upload view calls. Reports: total wall time,
per-sheet average, and peak Python-level memory (`tracemalloc`, cross-platform
— no `resource`/`psutil` dependency exists in this repo and Windows dev
lacks `resource`). Written time bound: **≤ 5 seconds/sheet average**
(generous vs. the ~1-2s/sheet typical for clean OpenCV template-matching on
a laptop; a real regression — an accidental O(n²) or a retry loop — would
blow well past this, while normal machine variance won't). Every submission
must finalize with the expected all-correct score (a correctness check
alongside the timing one — a fast-but-wrong pipeline doesn't pass).

`tests/test_load_batch.py` wraps a **smaller** version of the same scenario
(20 questions, 2 versions, 10 sheets) as a real `pytest` DoD check — same
code path, same timing assertion, small enough to run in CI every time.

## Phase 11 exit checklist

- [x] 11.1 happy path e2e green
- [x] 11.2 unhappy paths green (7 scenarios)
- [x] 11.3 `scripts/load_test.py` run once and its output recorded in
      `docs/PROGRESS.md` (60/60 finalized, 60/60 correct, 1.995s/sheet,
      15.2 MB peak); `tests/test_load_batch.py` green in the normal suite
- [x] `pytest -q` (with Postgres) green — **484 passed** — `ruff` clean,
      purity green, `PGPORT=5435 bash scripts/ci.sh` → **ALL GREEN**
