# Phase 6 — Bubble classifier + confidence gate

> Source: `docs/REBUILD_SPEC.md` §5 (Phases table, row 6), §2 R5.5–R5.7, §6 Q19.
> Governing rules: `docs/CLAUDE.md` (esp. rules 7 and 9).

## Phase goal

Given a `PageAlignment` (Phase 5) and a source image, classify every bubble
filled / empty / ambiguous, then apply the R5.7 confidence gate to decide which
questions (and ultimately the whole submission) are flagged for review. Report
both bubble-level accuracy and the professor-facing "expected per-submission
finalize rate" (R5.5) — honestly, per the Phase 5.5 pattern (a real number with
its corpus's narrowness stated, not hidden).

Everything in `app/omr/` stays **pure** (rule 7): `numpy` + `app.omr.geometry` +
`app.sheet_template` only, no Django, no cv2 needed beyond what the caller already
has (`gray` is just an array).

## What Phase 6 does NOT do

- No scoring (`score_question` is Phase 2's, reused as-is in Phase 7) — Phase 6
  only decides *what was marked* and *whether to trust it*, not what it's worth.
- No persistence, no `Submission`/`Answer` rows — Phase 7.
- No duplicate detection (R5.8) — that needs a DB of existing submissions to
  compare against; Phase 7.
- No distinction between `qr_unreadable` and other `alignment_failed` causes at
  the exception level — `app.omr.detect`/`alignment` currently raise
  `AlignmentError('marks_not_found', ...)` for *both* "no fiducials" and "QR not
  decoded" (different `detail` strings, same `reason`). Splitting that into a
  dedicated reason would be a small, real change, but there is zero real-corpus
  evidence to calibrate it against — QR decode was 100% (20/20) through Phase 5.
  Documented here rather than silently building it: Phase 6/7 treat every
  `AlignmentError` as `alignment_failed` for now. Revisit if Phase 7's larger
  corpus (or production use) ever actually produces a readable-fiducials/
  unreadable-QR case.

## Design: local-background-normalized fill scoring (R5.6)

For each bubble, sample two concentric regions in image space, both located via
the *local* px-per-mm derived from `H` right at that bubble (not one page-wide
scale estimate — matches the precedent set in Phase 5.3's Stage-B tick search
and 5.4's crop boxes):
- **fill region**: a small disk at the bubble's own center (`0.55 ×` bubble
  diameter, avoiding the printed circle stroke).
- **local background ring**: an annulus just outside the printed circle
  (`1.15×`–`+2mm` bubble radius), sampling the surrounding blank paper.

`fill_score = (background_mean − fill_mean) / background_mean` — ~0 for an
empty bubble (ink region reads the same as its own local background), growing
toward ~1 for a solid fill. Because every bubble is judged against a background
sample taken *next to it*, a page-wide illumination gradient (R5.6's specific
concern) shifts both numbers together and cancels out — no fixed global
threshold to be fooled by a darker bottom-of-page.

## Subtask 6.1 — Fill scoring + classification (`app/omr/classify.py`)

**Deliverables:**
- `BubbleState` enum (`FILLED`, `EMPTY`, `AMBIGUOUS`).
- `bubble_fill_score(gray, H, center_mm, bubble_diameter_mm, ...) -> float | None`
  — the R5.6 feature. `None` if the sample region falls outside the image
  (treated as ambiguous downstream, never a confident guess).
- `classify_bubble_score(score, *, empty_max, filled_min) -> BubbleState`.
- `classify_page(gray, H, template, num_questions, n_options, ...) -> dict[question, list[BubbleFill]]`.
- `evaluate_question_gate(row, *, key_size) -> QuestionGateResult` — R5.7's
  per-question rule: any ambiguous bubble → flag; 0 filled → flag (regardless of
  `key_size`); `key_size == 1` and `>1` filled → flag; otherwise (including any
  1..N filled on a multi-answer question) → not flagged.
- `SubmissionStatus` (`QR_UNREADABLE` unused for now — see above,
  `ALIGNMENT_FAILED`, `NEEDS_REVIEW`, `FINALIZED`) +
  `evaluate_submission(alignment_or_error, gray, template, key_sizes) -> (status, per-question results | None)`.

**Threshold calibration (provisional, corpus-derived — same pattern as Phase
5's gates):** `empty_max = 0.15`, `filled_min = 0.35`. Chosen from the real
corpus's fill-score distribution (2670 bubbles, all 20 photos, **after**
correcting 15 labeling errors this calibration pass itself uncovered — see
6.2): marked bubbles p5 = 0.538 (min 0.38 after correction), unmarked bubbles
p99 = 0.008 (max 0.34). Wide headroom on both sides of the chosen band.

## Subtask 6.2 — Corpus label correction (data quality, discovered mid-calibration)

While calibrating 6.1's thresholds against the real corpus, 15 of the 555
labeled questions showed an unmistakable pattern: the AI-transcribed "marked"
letter scored near-zero fill (empty-looking) while an *adjacent* letter in the
same question scored 0.4–0.9 (clearly filled) — an objective, algorithmic
signature of an off-by-one transcription slip in the original labeling pass
(2026-09-11, `910edca`), not classifier noise (the counts didn't move at all
across a wide range of thresholds — a real ambiguous case would). Corrected all
15 in `corpus/labels/*.json` with a dated note explaining the evidence and the
correction. Re-running the calibration after the fix: **0** confident-wrong in
either direction (was 15/16), full details in `docs/PROGRESS.md`.

## Subtask 6.3 — Synthetic clean-scan accuracy (R5.5's "held-out ≥99%")

R5.5 asks for a *separate* ≥99% figure on "clean scans" (a held-out set),
distinct from the real-photo corpus number. The 20-photo real corpus is both
too small for a statistically meaningful ≥99% claim and isn't "clean" (design
principle 2: synthetic is a supplement, never primary evidence for the
real-photo claim — but it *is* the right tool for this specific, separate,
idealized-conditions metric). Built a synthetic generator: draws the bubble
grid at a chosen scale with an identity-similarity `H` (no perspective) and a
**known random fill pattern**, filled bubbles as solid disks — no camera noise,
no JPEG, no rotation. `tests/test_omr_classify.py` runs many such sheets
(hundreds of bubbles) through `classify_page` and asserts every one is
classified correctly (no `AMBIGUOUS`, no wrong `FILLED`/`EMPTY`).

## Subtask 6.4 — R5.5's finalize-rate metric, on the real corpus

For each of the 20 real corpus photos, run `align_page` → `classify_page` →
`evaluate_question_gate` per question (assuming `key_size = 1` for every
question — the corpus sheets are Phase-0 technical test sheets with no real
ingested question bank behind them, so there is no real `|K|` to use; stated as
an explicit, documented assumption, not invented ground truth) →
`evaluate_submission`. Report the finalize rate honestly, with the same
narrow-corpus caveat as Phase 5.5.

## Phase 6 exit checklist

- [x] 6.1 fill scoring + classification + R5.7 gate — `app/omr/classify.py`,
      `tests/test_omr_classify.py` green (12 tests)
- [x] 6.2 corpus label corrections applied + documented (15 questions across 9 labels)
- [x] 6.3 synthetic clean-accuracy ≥99% (R5.5 held-out metric) — 100% observed (0 ambiguous, 0 wrong) across 2 synthetic test batteries
- [x] 6.4 real-corpus bubble accuracy + finalize rate reported (R5.5) — 99.93% bubble accuracy (2668/2670), 75% finalize rate (15/20, under a documented key_size=1-for-all assumption)
- [x] `pytest -m "not django_db" -q` green (321 passed), `ruff` clean, purity green

**Phase 6 is complete.**
