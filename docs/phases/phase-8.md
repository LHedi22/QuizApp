# Phase 8 — Dashboard + ingestion UI

> Source: `docs/REBUILD_SPEC.md` §5 (Phases table, row 8), §2 R0.2/R0.3, R1.1–R1.5,
> R2.1/R2.2/R2.6, R3.1/R3.4, R6.1. Governing rules: `docs/CLAUDE.md`.

## Phase goal

The professor-facing web UI, server-rendered Django templates against the **real
backend services** built in Phases 1–4, end-to-end tested with the Django test
client:

1. **Quiz CRUD** — create (title + `N` + grading config), list (own quizzes only),
   detail, edit grading config (draft only), delete (draft only).
2. **Question upload** — `.xlsx` ingest via `ingest_quiz`, with the full
   header + per-row error report (R1.3/R1.4) rendered, never a 500; re-upload
   rules (R1.5).
3. **Version generation** — request `M`, surface the feasibility / blocked errors
   (R2.2/R2.6), list the generated versions.
4. **PDF download** — stream each version's answer sheet + question paper from blob
   storage, byte-identical on re-download (R3.4).
5. **Results list** — per-quiz submission list with status / score / capture time /
   assigned student / flag reasons, filterable by status and sortable by score and
   capture time (R6.1). Tested against hand-built `Submission` fixtures (the scan
   pipeline is Phases 5–7; user-approved 2026-09-10).
6. **Route-level R0.2/R0.3** — every data view is `@login_required` and funnels
   through `get_owned_or_404`; a foreign id 404s, an unauthenticated request
   redirects to login before any data. This closes the route-level R0.2
   verification deferred from Phase 1.2.

## What Phase 8 does NOT do (Phase 9+)

- Per-submission answer-sheet review page, inline answer overrides (R6.2/R6.3).
- Manual student assignment, pasted roster (R6.4).
- Audit-log UI, CSV export (R6.5/R6.6).
- Per-version / per-quiz **"mark printed"** control (`version.printed_at`,
  `quiz.status → printed`) — R3.5, Phase 9. Phase 8 still honours the existing
  status machine: `ingest_quiz` / `generate_versions_for_quiz` already block on
  non-`draft` status, and the UI reflects that.
- The bounded LLM suggestion aid (Phase 10).

## Design choices (not stop-and-ask; recorded here per CLAUDE.md rule 4)

- **Plain server-rendered full-page forms + querystring filters.** No HTMX
  dependency in Phase 8 — the spec's "simplicity" priority and the fact that every
  interaction is a single form post or a filtered list. HTMX can be added later for
  a specific view if it earns its place.
- **Version generation runs synchronously** in the request. Realistic `M` (≤ ~20)
  with the Phase 3 anti-clustering completes in well under a request timeout.
  Django-Q2 offload is wired in Phase 7/11 where the batch **scan** pipeline needs
  it (per the phase-3.4 note).
- **`N` (`options_per_question`) is fixed at quiz creation** — the edit form only
  exposes title + grading config. Changing `N` would invalidate already-ingested
  option counts; a different `N` means a new quiz.
- **Delete is draft-only.** Once versions exist they are irreplaceable (R8.2) and
  `Submission.version` is `PROTECT`; the UI disables delete for
  `versioned` / `printed` quizzes.
- **WhiteNoise** is added for static file serving under `DEBUG=0` (flagged in the
  phase-0.5 note as a Phase 8 decision). Dep addition noted in PROGRESS.md.

## Environment

Postgres required for every subtask (all views hit the ORM). This session: Docker
Desktop is healthy again — `postgres:16` on `127.0.0.1:5433`,
`DATABASE_URL=postgres://postgres:dev@127.0.0.1:5433/<db>`.

---

## Subtask 8.1 — Quiz CRUD

**Goal.** Create / list / view / edit-config / delete quizzes, owner-scoped.

**Deliverables.**
- `app/web/forms.py`:
  - `QuizCreateForm` — `title`, `options_per_question`, `marking_mode`,
    `negative_marking`, `default_points`. `save()` delegates to
    `app.core.services.create_quiz`, mapping its field-keyed `ValidationError`
    onto form errors.
  - `QuizConfigForm` — `title`, `marking_mode`, `negative_marking`,
    `default_points` (no `N`); updates the row directly, draft-only (the view
    guards status).
- `app/web/views.py` (or a new `app/web/quiz_views.py` imported there):
  - `dashboard` → quiz list, `Quiz.objects.owned_by(request.user)`, newest first,
    each row showing status + question count + version count.
  - `quiz_create` (GET form / POST create → redirect to detail).
  - `quiz_detail` — `get_owned_or_404(Quiz, pk, user)`; shows config, question
    count, versions, and the upload / version / results entry points.
  - `quiz_edit` — draft-only (`Http404` or a redirect with a message otherwise).
  - `quiz_delete` — POST only, draft-only, confirm page on GET.
- `app/web/urls.py` routes: `quizzes/new`, `quizzes/<pk>/`,
  `quizzes/<pk>/edit`, `quizzes/<pk>/delete`.
- Templates under `app/web/templates/web/`: `quiz_list.html` (replaces the
  dashboard stub), `quiz_form.html`, `quiz_detail.html`, `quiz_confirm_delete.html`.
- `base.html` gains a nav bar + `messages` rendering + minimal inline CSS.

**Definition of Done (runnable).** `pytest tests/test_web_quiz_crud.py -q`:
- create via POST → row exists, `professor == request.user`, `status == draft`,
  redirect to detail; invalid input (blank title, `N=7`, negative points) →
  form re-rendered with the field error, **no row written**;
- list shows only the caller's quizzes (prof B never sees prof A's);
- `quiz_detail` / `quiz_edit` / `quiz_delete` for a foreign or missing pk → 404;
- config edit persists and cannot change `N`; editing a `versioned` quiz → blocked;
- delete removes a draft quiz; delete on a `versioned` quiz → blocked, row kept.

---

## Subtask 8.2 — Question upload (xlsx ingest UI)

**Goal.** Upload a spreadsheet, ingest via the Phase 2 service, render every error.

**Deliverables.**
- `QuestionUploadForm` — single `FileField` (`.xlsx`).
- `quiz_upload` view — `get_owned_or_404`, calls
  `app.core.ingest.ingest_quiz(quiz, file)`:
  - `ParseResult.ok` → success message with the ingested count, redirect to detail;
  - not ok → re-render the upload page with `header_errors`, `file_errors`, and a
    table of `row_errors` (row number + **all** reasons for that row) — HTTP 200,
    never a 500;
  - `IngestBlocked` (quiz not draft) → clear message, redirect to detail.
- `quiz_upload.html` template with the error report block.
- Route `quizzes/<pk>/upload`.

**Definition of Done (runnable).** `pytest tests/test_web_ingest.py -q`:
- valid `.xlsx` (via the `make_xlsx` fixture) → questions created in file order,
  success message shows the count;
- file with several bad rows → response lists **every** bad row and **every**
  reason per row; `Question.objects.filter(quiz=quiz).count() == 0`;
- re-upload while `draft` replaces the question set;
- upload to a `versioned` quiz → blocked message, question set unchanged;
- foreign quiz pk → 404.

---

## Subtask 8.3 — Version generation UI

**Goal.** Request `M` versions; surface feasibility / blocked failures cleanly.

**Deliverables.**
- `VersionGenerateForm` — `m` (positive int).
- `version_generate` view — `get_owned_or_404`, calls
  `app.core.versioning_service.generate_versions_for_quiz(quiz, m)`:
  - success → message ("`M` versions generated"), redirect to detail, which now
    lists each version (number, short `qr_id`, `anticluster_fallback` badge);
  - `InfeasibleVersionCount` / `ValueError` (`m < 1`, bad data) /
    `VersionGenerationBlocked` → re-render with the exact message, **nothing
    written**, `status` unchanged.
- `quiz_detail.html` extended with the version list + the generate form (shown only
  while `draft` with questions present).
- Route `quizzes/<pk>/versions/generate`.

**Definition of Done (runnable).** `pytest tests/test_web_versions.py -q`:
- generate `M=3` for a real quiz → 3 `Version` rows, `quiz.status == versioned`,
  detail page lists all 3;
- `m=0` / `m=-1` → error shown, 0 versions, status still `draft`;
- infeasible `M` (e.g. 3-question quiz, `M=10`) → the R2.2 message, 0 versions
  written;
- generating again on a `versioned` quiz → blocked, still exactly the first batch;
- foreign quiz pk → 404.

---

## Subtask 8.4 — PDF download

**Goal.** Serve each version's two PDFs from the deterministic blob cache.

**Deliverables.**
- `version_pdf` view — `get_owned_or_404(Version, pk, user)`, `kind ∈
  {answer_sheet, question_paper}`; calls
  `app.pdf.artifacts.render_and_store_version_pdfs(version)` then streams
  `get_blob_storage().read(path)` with `Content-Type: application/pdf` and a
  `Content-Disposition: attachment; filename="…"`.
- Routes `versions/<pk>/answer_sheet.pdf`, `versions/<pk>/question_paper.pdf`
  (or `versions/<pk>/<kind>.pdf`).
- Links on `quiz_detail.html` per version.

**Definition of Done (runnable).** `pytest tests/test_web_pdf_download.py -q`
(with `override_settings(MEDIA_ROOT=tmp_path)`):
- GET each kind → 200, `Content-Type: application/pdf`, body starts `%PDF-`;
- two GETs of the same URL → **identical bytes** (R3.4);
- an unknown `kind` → 404;
- a foreign / missing version pk → 404;
- unauthenticated → redirect to login.

---

## Subtask 8.5 — Results list (R6.1)

**Goal.** Per-quiz submission list with status / score / capture time / student /
flags, filter by status, sort by score and capture time.

**Deliverables.**
- `quiz_results` view — `get_owned_or_404(Quiz, pk, user)`; queries
  `Submission.objects.owned_by(user).filter(version__quiz=quiz)` with:
  - `?status=<Submission.Status>` filter (invalid value → ignored / all);
  - `?sort=` one of `score`, `-score`, `captured`, `-captured` (default
    `-captured`), mapped to `total_score` / `created_at` with a stable tiebreak;
  - each row: status, `total_score`, `created_at`, assigned student
    (`roster_entry.label` or `student_label` or "—"), flag reasons
    (`failure_reason` for failed; else the distinct `flag_reason`s of that
    submission's flagged answers).
- `quiz_results.html` — table + the filter/sort controls as GET links/selects.
- Route `quizzes/<pk>/results`.
- `tests/conftest.py`: extend `make_submission` usage / add a helper to attach
  flagged `Answer` rows if needed.

**Definition of Done (runnable).** `pytest tests/test_web_results.py -q`:
- build ≥4 submissions across a quiz's version(s) with varied status / score /
  `created_at` (fixtures — no scan pipeline); list renders all, newest capture
  first by default;
- `?status=needs_review` → only those rows;
- `?sort=-score` → ordered by score desc; `?sort=captured` → oldest first;
- a `failed` submission shows its `failure_reason`; a submission with flagged
  answers shows those flag reasons;
- foreign quiz pk → 404; unauthenticated → redirect to login.

---

## Subtask 8.6 — Nav, static (WhiteNoise), and the R0.2/R0.3 route sweep

**Goal.** Tie the UI together and prove the isolation guarantee at the route layer.

**Deliverables.**
- `base.html` nav (Quizzes / log out), `messages` block, a small stylesheet in
  `app/web/static/web/app.css` served via WhiteNoise.
- `pyproject.toml`: add `whitenoise`; `settings.py`:
  `whitenoise.middleware.WhiteNoiseMiddleware` after `SecurityMiddleware`,
  `STATICFILES_STORAGE` / `STORAGES` compressed-manifest backend.
- `deploy/entrypoint.sh` — drop the `|| true` on `collectstatic` now that static
  serving is real (or keep it but assert the manifest exists).
- `tests/test_web_route_isolation.py` — parametrised over **every** Phase 8 route:
  1. unauthenticated GET/POST → 302 to `/accounts/login/` (R0.3);
  2. authenticated as prof B against prof A's `quiz` / `version` / results /
     PDF-download ids → 404 (R0.2, never 403).

**Definition of Done (runnable).**
- `pytest tests/test_web_route_isolation.py -q` green — every route covered;
- `pytest -q` full suite green on Postgres;
- `python manage.py check --deploy` — no **new** warning classes vs. the Phase 0.4
  baseline (TLS/DEBUG warnings still expected);
- `bash scripts/ci.sh` green (default `docker` runtime now that Docker is healthy);
- `python manage.py collectstatic --noinput` succeeds and the WhiteNoise manifest
  resolves.

---

## Phase 8 exit checklist

- [ ] 8.1 quiz CRUD — create/list/detail/edit/delete, owner-scoped, invalid input
      writes nothing
- [ ] 8.2 ingest UI — every header+row error rendered, never a 500, R1.5 rules
- [ ] 8.3 version generation UI — feasibility/blocked errors surfaced, nothing
      written on failure
- [ ] 8.4 PDF download — `application/pdf`, byte-identical re-download
- [ ] 8.5 results list — status filter + score/capture sort, fixture-tested
- [ ] 8.6 nav + WhiteNoise + full R0.2/R0.3 route-isolation sweep
- [ ] full suite green on Postgres; `scripts/ci.sh` green on the `docker` runtime
- [ ] `docs/PROGRESS.md` entry per subtask, one commit each
