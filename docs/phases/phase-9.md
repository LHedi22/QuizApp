# Phase 9 — Review UI + audit

> Source: `docs/REBUILD_SPEC.md` §5 (Phases table, row 9), §2 R6.2–R6.6, R3.5,
> R6.5, Appendix A. Governing rules: `docs/CLAUDE.md`.

## Phase goal

The per-submission review surface and the mutation/audit trail:

1. **Submission detail (R6.2)** — full answer sheet for any submission (any
   status): each question 1..n with what the system read, confidence, the
   canonical correct answer, correct/wrong/flagged, the resulting score, and an
   "edited" marker; flagged rows pinned to the top.
2. **Inline override (R6.3)** — the professor edits any answer's marked-option
   set on any submission (finalized included); it re-scores **via the shared
   `score_question`**, clears the flag, stamps `manually_edited` + `edited_at`,
   recomputes the submission total, and finalizes the submission if nothing is
   still flagged.
3. **Manual student assignment (R6.4)** — free text or a pick from an optional
   per-quiz roster the professor pastes in (`name` or `name, external_id` per
   line). Editable, logged.
4. **Append-only audit log (R6.5)** — every grading decision and manual action is
   an `AuditEvent`; the submission detail view shows the history. Passive views
   are **not** logged.
5. **CSV export (R6.6)** — student, version, total, per-question scores.
6. **"Mark printed" control (R3.5)** — per-version `printed_at`; the first one on
   a quiz flips `quiz.status → printed` (which already blocks re-upload via the
   Phase 2 `IngestBlocked` guard).

## What Phase 9 does NOT do

- The scan pipeline that *populates* submissions/answers is Phases 5–7. Like the
  Phase 8 results list, Phase 9 is built and e2e-tested against hand-built
  `Submission` / `Answer` fixtures (same user approval, 2026-09-10).
- The R5.7 confidence gate and R7.6 auto-re-score-on-config-change are Phase 6/7.
  Phase 9's override uses the **local** R6.3 rule only ("finalize iff no answer
  on this submission is still flagged"); it never runs the full gate.
- The LLM suggestion aid (Phase 10).

## Data model / scoring / geometry check (CLAUDE.md rule 5)

- **No new columns.** Every field Phase 9 writes already exists in Appendix A /
  `app/core/models.py`: `answer.{detected_options,score,correct,manually_edited,
  edited_at,flagged,flag_reason}`, `submission.{total_score,roster_entry,
  student_label,status}`, `roster_entry.{label,external_id}`,
  `version.printed_at`, `quiz.status`, `AuditEvent` (actions `overridden`,
  `assigned`, `printed` already defined).
- **Scoring formula untouched** — the override path calls `score_question`
  (R7.5) and nothing else. This is the first production call site; the R7.5
  parity assertion still lands in Phase 7 (the scan pipeline is the other site).
- **No `sheet_template.json` change.**

## Environment

Postgres for every subtask. This session: `docker run -d -p 127.0.0.1:5433:5432
-e POSTGRES_PASSWORD=dev --name qs-pg8 postgres:16`,
`DATABASE_URL=postgres://postgres:dev@127.0.0.1:5433/<db>`.

---

## Subtask 9.1 — Review + grading services (`app/core/review_service.py`)

**Goal.** One funnel for every Phase 9 mutation, each writing an `AuditEvent`.

**Deliverables.**
- `app/grading/regrade.py` (pure, no Django):
  - `submission_total(scores: Iterable[float | None]) -> float` — sum, `None` → 0.
  - `status_after_override(current: str, any_flagged: bool) -> str` — R6.3 local
    rule: `needs_review` + not `any_flagged` → `finalized`; `finalized` stays
    `finalized`; otherwise unchanged.
- `app/core/review_service.py`:
  - `override_answer(*, answer, professor, marked_options: list[str]) -> Answer`
    — recover the question's canonical key letters
    (`versioning_service.recover_correct_letters`), call
    `score_question(marked_options, key, points, quiz.marking_mode,
    quiz.negative_marking)`, write `answer.{detected_options,score,correct,
    manually_edited=True,edited_at=now,flagged=False,flag_reason=""}`; recompute
    `submission.total_score` and `submission.status`
    (`status_after_override`); `AuditEvent(action="overridden", submission,
    quiz, actor_professor, detail={before, after})`. Atomic.
  - `assign_student(*, submission, professor, roster_entry=None, label="")
    -> Submission` — set exactly one of `roster_entry` / `student_label`
    (clearing the other); `AuditEvent(action="assigned", …)`. Atomic.
  - `parse_roster(text: str) -> list[tuple[str, str]]` — one entry per non-blank
    line, `label` or `label, external_id` (first comma splits); trims; ignores
    blank lines; raises `ValueError` on a line with an empty label.
  - `replace_roster(*, quiz, professor, text) -> list[RosterEntry]` — parse then
    replace `quiz.roster_entries` atomically; `AuditEvent(action="assigned",
    submission=None, detail={"roster_size": n})` (quiz-scoped).
  - `mark_version_printed(*, version, professor) -> Version` — set
    `version.printed_at = now` if unset (idempotent: already-printed → return
    unchanged, no second audit); if this is the first printed version of the
    quiz, `quiz.status = "printed"`; `AuditEvent(action="printed", …)`. Atomic.
    This is the **only** code path that sets `printed_at` / flips to `printed`.

**Definition of Done (runnable).** `pytest tests/test_review_service.py -q`:
- `submission_total` / `status_after_override` unit cases (pure);
- `override_answer` on a `needs_review` submission with one flagged answer:
  score matches a hand-computed `score_question` value, flag cleared,
  `manually_edited` + `edited_at` set, `total_score` = sum, status →
  `finalized`, exactly one `overridden` `AuditEvent` with before/after;
- `override_answer` on a `finalized` submission → stays `finalized`, still
  audited;
- `override_answer` leaving another answer still flagged → status stays
  `needs_review`;
- `assign_student` by roster entry then by free text → the other field cleared,
  two `assigned` events;
- `parse_roster`: `"Ada\nBabbage, 42\n\n  \n"` → `[("Ada",""),("Babbage","42")]`;
  a blank-label line raises `ValueError`;
- `replace_roster` twice → second call replaces, not appends;
- `mark_version_printed`: first version → `printed_at` set + `quiz.status ==
  printed` + `printed` event; second call on the same version → no-op, no new
  event; a second version of the same quiz → `printed_at` set, status already
  `printed`, new event.

---

## Subtask 9.2 — Submission detail view (R6.2) + audit history (R6.5)

**Deliverables.**
- `app/web/review_views.py` `submission_detail(request, pk)` —
  `get_owned_or_404(Submission, pk, user)`; builds a row per `answer`
  (question no, `detected_options`, `confidence`, canonical correct letters via
  `recover_correct_letters`, `correct`, `flagged` + reason, `score`,
  `manually_edited`); **flagged rows first**, then by question no. Also passes
  the submission's `AuditEvent`s (newest first) and the assignment state.
- `web/submission_detail.html`.
- Route `submissions/<int:pk>/` (name `submission_detail`).
- Link from `quiz_results.html` rows.

**Definition of Done (runnable).** `pytest tests/test_web_submission_detail.py -q`:
- a submission with 5 answers (2 flagged, 1 manually edited) renders: all 5
  question rows, the 2 flagged rows appear before any unflagged row in the HTML,
  the edited row shows the "edited" marker, each row shows the canonical correct
  letters and the score;
- the audit history block lists the submission's events newest-first;
- opening the submission writes **no** `AuditEvent` (R6.5 — passive view);
- foreign / missing submission pk → 404; unauthenticated → login redirect.

---

## Subtask 9.3 — Override + student-assignment endpoints (R6.3 / R6.4)

**Deliverables.**
- `AnswerOverrideForm` (`marked_options` — a multi-checkbox of `A..N` for the
  question's option count) and `StudentAssignForm` (`roster_entry` choice +
  `student_label` text; clean rejects both-set / neither-set).
- `answer_override(request, pk)` (POST) → `review_service.override_answer`,
  redirect back to the submission with a message.
- `submission_assign(request, pk)` (POST) → `review_service.assign_student`.
- Routes `answers/<int:pk>/override`, `submissions/<int:pk>/assign`.
- Both forms rendered on `submission_detail.html`.

**Definition of Done (runnable).** `pytest tests/test_web_review_actions.py -q`:
- POST an override that corrects a wrong answer → answer row updated, submission
  total + status updated on the reloaded detail page, `overridden` event shown;
- POST an override on a **finalized** submission → accepted, stays finalized;
- POST assignment by roster pick, then by free text → reflected on the page and
  in the results list; both `assigned` events shown;
- assignment form with both fields / neither field → form error, nothing
  written;
- foreign answer / submission pk → 404.

---

## Subtask 9.4 — Roster paste (R6.4)

**Deliverables.**
- `RosterPasteForm` (`text` textarea).
- `quiz_roster(request, pk)` GET (textarea prefilled with the current roster,
  one entry per line) / POST (`review_service.replace_roster`, redirect to the
  quiz with a count message; `ValueError` from a bad line → form error naming
  the line).
- Route `quizzes/<int:pk>/roster` (name `quiz_roster`); link on
  `quiz_detail.html`.

**Definition of Done (runnable).** `pytest tests/test_web_roster.py -q`:
- paste 3 lines (one with `, id`) → 3 `RosterEntry` rows, the `external_id`
  parsed; re-paste 2 lines → 2 rows (old ones gone);
- a line with an empty label → form error, roster unchanged;
- the roster entries then appear as options in the submission assignment form;
- foreign quiz pk → 404.

---

## Subtask 9.5 — CSV export (R6.6)

**Deliverables.**
- `quiz_results_csv(request, pk)` — `text/csv` attachment. Header:
  `student, version, total, q1, q2, …, qN` (N = quiz question count, canonical
  order). One row per submission (own quiz only); `student` = roster label /
  free text / `""`; per-question cell = that submission's `answer.score` for
  that `question_no` (blank if no answer row). Deterministic row order
  (submission id).
- Route `quizzes/<int:pk>/results.csv` (name `quiz_results_csv`); button on
  `quiz_results.html`.

**Definition of Done (runnable).** `pytest tests/test_web_results_csv.py -q`:
- `Content-Type: text/csv`, attachment; header row has `student,version,total`
  then one `qN` column per question;
- a quiz with 3 submissions → 3 data rows in submission-id order, totals and
  per-question scores match the fixture values;
- a submission with a missing answer row → blank cell, not a crash;
- foreign quiz pk → 404; unauthenticated → login redirect.

---

## Subtask 9.6 — "Mark printed" control (R3.5) + route sweep + phase close

**Deliverables.**
- `version_mark_printed(request, pk)` (POST) → `review_service.mark_version_printed`;
  button per version on `quiz_detail.html` (shows `printed_at` once set; hidden
  once printed). A whole-quiz "mark all printed" is just a loop over versions.
- `quiz_detail.html` reflects `quiz.status == printed` (upload / generate / edit
  / delete controls already hidden for non-draft from Phase 8).
- Extend `tests/test_web_route_isolation.py` with the new routes
  (`submission_detail`, `answer_override`, `submission_assign`, `quiz_roster`,
  `quiz_results_csv`, `version_mark_printed`): unauth → login (R0.3), foreign id
  → 404 (R0.2).

**Definition of Done (runnable).**
- `pytest tests/test_web_printed.py -q`: marking a version printed sets
  `printed_at` + flips `quiz.status` to `printed`; a subsequent `ingest_quiz`
  raises `IngestBlocked`; the control is idempotent; `printed` `AuditEvent`
  written; foreign version pk → 404.
- `pytest tests/test_web_route_isolation.py -q` green with the Phase 9 routes.
- `pytest -q` full suite green on Postgres.
- fresh-DB `migrate` + `migrate --check` clean; `makemigrations --check` → no
  changes (Phase 9 adds **no** migration); `manage.py check` → 0.
- `bash scripts/ci.sh` green on the `docker` runtime (or the documented direct
  steps if the compose loop is impractical).

---

## Phase 9 exit checklist

- [x] 9.1 review/grading services — override / assign / roster / mark-printed,
      each audited; pure regrade helpers  (e75e6f1)
- [x] 9.2 submission detail — full answer sheet, flagged pinned, audit history,
      no audit on view  (7186599)
- [x] 9.3 override + assignment endpoints — shared scoring path, status
      re-evaluated  (0094aa9)
- [x] 9.4 roster paste — `name` / `name, external_id`, replace-not-append  (2302405)
- [x] 9.5 CSV export — student / version / total / per-question  (bcfe06d)
- [x] 9.6 mark-printed + R0.2/R0.3 sweep + full verification
- [x] full suite green on Postgres (332); `scripts/ci.sh` **ALL GREEN** on the
      default `docker` runtime
- [x] `docs/PROGRESS.md` entry per subtask, one commit each

**Phase 9 complete** (2026-09-10). No migration added. The review UI + overrides
are wired to real `Submission` / `Answer` rows but only fixture-populated until
the Phase 7 scan pipeline exists. `scripts/ci.sh` on the real `docker` runtime is
now green — the long-standing "owed once Docker healthy" item is cleared;
`docker compose up --build` + the in-container 1.4 loader check remain.
