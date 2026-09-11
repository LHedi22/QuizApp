# Phase 7 — Scan intake + persistence (full pipeline wiring)

> Source: `docs/REBUILD_SPEC.md` §5 (Phases table, row 7), §2 R4.1, R5.1, R5.4,
> R5.8, R7.4-R7.6. Governing rules: `docs/CLAUDE.md`.

## Phase goal

Wire Phases 5 (`align_page`) and 6 (`classify_page`/`evaluate_submission`) into
real `Submission`/`Answer` rows via a Django-aware orchestrator, plus the
upload UI (single photo + batch) and best-effort duplicate detection (R5.8).

## Stop-and-ask resolved before starting (Appendix A)

`Submission.version` is a required FK (not nullable). When alignment totally
fails (no QR / no fiducials), there is no `qr_id` to resolve a version from.
**User decision (2026-09-11): scope upload to one quiz+version at a time** — no
schema change. The professor picks a specific printed `Version` before
scanning; that version is known from the URL/request context, not from OMR.
QR decode is then used to **detect a mismatch** (wrong version uploaded)
against the pre-selected version, not to identify the version from scratch.

## Subtask 7.1 — Core orchestrator (`app/core/scan_pipeline.py`)

`process_submission_image(*, version, image_bytes, source, batch_id=None,
page_number=None) -> Submission`:
1. Save the raw image via `get_blob_storage()`.
2. `align_page(image, load_template(), version_lookup=<matches only this
   version's qr_id>)`.
3. On `AlignmentError` → `Submission(status=FAILED, failure_reason=
   ALIGNMENT_FAILED, ...)`, **no `Answer` rows** (R5.7). Both `marks_not_found`
   and `version_not_found`/`fit_quality` map to `ALIGNMENT_FAILED` — the model
   only has 2 `FailureReason` choices and `qr_unreadable` vs the rest isn't
   distinguishable yet (documented in phase-6.md; not re-litigated here).
4. On success: `classify_page` → for each sheet position, resolve the real
   `Question` via `version.question_order`, `key = recover_correct_letters`
   (Phase 3) → `evaluate_question_gate(key_size=len(key))` → `Answer` row
   (`detected_options` = sheet letters, `score` via `score_question` — R7.5,
   the *same* function Phase 9's overrides use — `None` while flagged).
5. Submission status: `FINALIZED` iff no answer flagged, else `NEEDS_REVIEW`;
   `total_score` withheld (`None`) unless finalized (R7.4).
6. `answer_hash` (R5.8): a stable hash of the finalized/needs-review answer
   pattern, stored on every non-failed submission.

`find_probable_duplicate(submission) -> Submission | None`: best-effort query
for another submission of the same version with a matching `answer_hash`.
**Never auto-sets `duplicate_of`** (Appendix A: "professor-confirmed") — a pure
query helper the review UI surfaces, the professor confirms via existing Phase
9 mutations.

`process_batch(*, version, pages: list[bytes], source=BATCH_PDF) ->
list[Submission]`: R5.4 — each page is independent; a failure never aborts the
batch.

## Subtask 7.2 — Upload UI

`versions/<int:pk>/submissions/upload` (photo) — `@login_required`,
`get_owned_or_404(Version, ...)`, a form posting one image, calls
`process_submission_image`, redirects to `submission_detail` (Phase 9,
already built) or shows the failure inline.

## Real-corpus DoD (rule 9)

The Phase 0.7 corpus sheets were rendered directly by
`scripts/make_corpus_sheets.py` (bypassing quiz creation) with **sequential,
unshuffled** `question_order`/`option_order` (bubble position N = sheet-printed
question N, letter A = first drawn option — `render_answer_sheet` never
shuffles; only a real `generate_versions` call does). Phase 7's DB-integration
tests build matching fixtures — a real `Quiz`/`Question`/`Version` set with
`Version.qr_id = <corpus sheet_token>` and identity `question_order`/
`option_order` — then run `process_submission_image` against real corpus
photos end-to-end. **The `correct_options` assigned to these fixture questions
are arbitrary** (the corpus has no real exam behind it) — this validates
pipeline *mechanics* (alignment → classification → persistence → scoring
wiring) against real captures, not a new grading-accuracy claim (that's
Phase 5/6's, already established).

## Subtask 7.2 DoD proof

`app/web/scan_views.py` — `submission_upload` (single photo) and
`submission_upload_batch` (batch PDF, rasterized page-by-page via `pymupdf` at
200 DPI). Both `@login_required` + `get_owned_or_404(Version, ...)` (R0.2/R0.3).
Single-photo success redirects to `submission_detail`; a `FAILED` submission
re-renders the upload page with an inline error (raw image is still saved and
kept — never silently dropped). Batch success redirects to `quiz_results` with
a summary message (`n_ok` scanned / `n_failed` failed), since a batch produces
many submissions, not one detail page to land on.

`tests/test_web_scan_upload.py` (6 tests, all against the dev Postgres
container): upload page renders both forms; a real corpus photo posted through
the HTTP layer redirects to `submission_detail` with a FINALIZED/NEEDS_REVIEW
submission; a valid-but-unalignable photo (blank white JPEG — chosen because
Django's `ImageField` itself rejects genuinely malformed bytes before the view
ever runs, so this is the real "valid image, bad content" failure path) stays
on the upload page with a "Scan failed" message and a FAILED submission; a
one-page PDF built from a real corpus photo posted to the batch endpoint
redirects to `quiz_results` and creates exactly one `Submission` with the
right `page_number`/`batch_id`; a non-PDF upload is rejected by form
validation with zero submissions created; both routes 404 for another
professor's version.

Bug found and fixed in passing (not new Phase 7 code): `tests/
test_web_route_isolation.py` combined a `@override_settings(MEDIA_ROOT=None)`
decorator with the `settings` fixture on the same test — a known pytest-django
footgun where the fixture's override doesn't nest cleanly with the decorator's,
leaking `MEDIA_ROOT=None` into every test that runs afterward in the same
session. It only surfaced once Phase 7's web tests (which touch blob storage
through the full view) ran after that file alphabetically in a full-suite run.
Fixed by dropping the redundant decorator — the test body already sets
`settings.MEDIA_ROOT = tmp_path` via the fixture, so the decorator was dead
weight that was actively corrupting later tests.

## Phase 7 exit checklist

- [x] 7.1 orchestrator + `tests/test_scan_pipeline.py` (24 tests, real-corpus
      DB integration, 20/20 real corpus photos FINALIZED/NEEDS_REVIEW never
      FAILED) green
- [x] 7.2 upload view + template + `tests/test_web_scan_upload.py` (6 tests)
      green
- [x] `pytest -q` (with Postgres) green — **475 passed**, `ruff` clean, purity
      green (`app.omr`/`app.grading` untouched by Phase 7 — orchestrator lives
      in `app.core`/`app.web` only)
