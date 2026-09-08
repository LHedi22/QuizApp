# REBUILD_SPEC.md — Exam Version Generator & Scanner (clean rebuild)

> **Status:** planning document. Single source of truth for rebuilding this project
> from an empty repository. Written to be usable with no memory of the conversation
> that produced it.
>
> **This supersedes the old `CLAUDE.md` / `prompts/` / `PROGRESS.md` set.** Those
> describe the first implementation, which is being abandoned (accumulated CV/OMR
> reliability problems, architectural drift, a fragile laptop-dependent deployment).
> The *problem* the first build solved is still the problem. Almost none of its
> *solution decisions* are carried over unexamined.
>
> **Decisions already made by the user** are marked **[LOCKED]**.
> **Recommendations still needing sign-off** are marked **[RECOMMENDED — confirm]**.
> **Things the user must answer before build starts** are in §6.
>
> **§6 open questions are now resolved across three rounds of Q&A.** Round 1/2
> resolutions are folded into §2/§3/§5. **Round 3 (this revision) is a critical
> review pass** that found and closed several real gaps — a spec ambiguity around
> multi-correct anti-clustering, a phase-ordering dependency, a missing data-model
> field, and a few smaller items. Round 3 resolutions are also folded into §2/§3/§5
> and recorded in §6.3.
>
> **Deployment reality: this is a laptop prototype.** One `docker-compose` (app +
> Postgres), bound to `localhost`, no TLS, no reverse proxy, no remote target. The
> architecture stays deployment-portable but nothing in the build plan provisions a
> server.

---

## 1. Problem statement & goals

### The problem

A professor sets a multiple-choice exam. To deter copying between adjacent students,
they want several **versions** of the same exam — identical questions, but with the
question order shuffled and the answer options shuffled within each question. Producing
those versions by hand is tedious; **grading them by hand is worse**, because every
version has a different answer key and the professor has to keep track of which
physical paper maps to which shuffle.

### The solution, in one line

Upload the questions once → the system produces N shuffled versions and their
print-ready answer sheets → the professor prints, photocopies, administers on paper,
then photographs or scans the completed sheets → the system reads the marks, un-shuffles
them back to the canonical questions, grades against the master key, and shows the
professor a results dashboard with a review queue for anything it wasn't sure about.

### Who it's for

- **Primary and only user role: the professor.** They own quizzes, generate versions,
  print, scan, review, and export results. Small scale — think one professor handling a
  class of up to ~60 students, a handful of versions per exam.
- **Students never touch the software.** They only ever see a printed paper.
- **Deployment context:** a single self-hosted server for one institution
  (see §3). Not a public multi-tenant SaaS.

### Non-negotiable goals

1. **Eliminate the manual burden** of creating shuffled MCQ versions *and* grading
   them. Both halves. A rebuild that generates versions beautifully but still needs
   hand-grading has failed.
2. **Grades must be trustworthy and auditable.** A wrong grade on an exam is
   high-stakes. For every submission the professor must be able to see *what the
   system read*, *how confident it was*, *what the correct answer was*, and *what
   score resulted* — and override any of it, with the override recorded.
3. **The system must never silently auto-finalize a grade it isn't sure about.**
   Ambiguous reads go to a review queue, always.
4. **The version-mapping data is sacred.** Losing or corrupting a version's
   `question_order` / `option_order` means every paper of that version is
   ungradeable forever. It must be immutable after first print and included in
   backups.

### Deliberately in scope now (new vs. the first build)

- **Weighted / negative / partial-credit marking** **[LOCKED]** — see §2 R7 and §6 Q1.
- **Multiple-correct-answer questions** ("select all that apply") **[LOCKED]** — §2 R6.
- **Professor-set option count per quiz** (not hardcoded to 4) **[LOCKED]** — §2 R2.
- **Batch upload of a multi-page scan/PDF** as a capture method **[LOCKED]** — §2 R8.

### Deliberately out of scope

- **No mobile app.** Web only. **[LOCKED]** No Flutter, no offline queue, no native
  client, no "mobile contract" on the API. Scanning happens in the browser (camera or
  file upload) and via batch PDF upload.
- **No short-answer / essay / numeric grading.** MCQ bubbles only.
- **No LMS / gradebook integration**, no roster sync, no student accounts.
- **No data migration** from the old system. Clean slate. **[LOCKED]**
- **No always-on cloud SaaS.** Single self-hosted server. **[LOCKED]**
- **No password-reset flow.** **[LOCKED — Round 3]** Single-professor local tool; if
  a password is lost, recovery is via direct DB/Django-admin access on the laptop
  itself. Revisit if this ever becomes multi-professor or network-exposed (same
  trigger as §6 Q7).

---

## 2. Functional requirements

Written as testable statements. "The system" = the whole application. Each is a
verification target, not an implementation instruction.

### Authentication & accounts

- **R0.1** A visitor can self-register a professor account with email + password and
  log in. **[LOCKED: open self-signup, no allowlist / invite / approval gate]** —
  acceptable only because the app is `localhost`-only (§6 Q7). Revisit before any
  network exposure. **No password-reset flow is built** (Round 3 — see §6 Q13); a
  lost password is recovered via direct database or Django-admin access.
- **R0.2** All quiz/version/submission/result data is owned by the creating professor.
  A logged-in professor can only ever read or modify their own data, enforced on the
  server for every request path — verified by a cross-account test that attempts to
  read another professor's quiz, version, submission, and answers by direct ID and
  gets a not-found response every time. **Re-confirmed [LOCKED] in Round 3** despite
  being more machinery than a strictly single-user tool needs (§6 Q14) — kept because
  it was already a signed-off decision and costs little given Django ships it for
  free.
- **R0.3** An unauthenticated request to any data route is rejected before any data is
  returned.

### Quiz ingestion

- **R1.1** A professor creates a quiz with a title, an **options-per-question count
  `N`** (2–6, uniform for the whole quiz), and a **grading configuration** (§2 R7:
  marking mode + negative-marking toggle + default per-question points).
- **R1.2** The professor uploads one **`.xlsx`** spreadsheet of questions (**xlsx only,
  no CSV**). Columns are identified by a **required, name-validated header row** (not by
  position — the old positional layout allowed silent misloads). Contract:

  ```
  question_text | option_1 | option_2 | … | option_N | correct_options | points(optional)
  ```

  - `correct_options`: one or more of the first `N` letters, comma- or space-separated
    (e.g. `A` or `A,C`). The size of this set determines whether the question is
    single- or multi-correct — there is no separate "type" column.
  - `points`: optional per-question weight; blank → the quiz default. **There is no
    penalty column** — wrong-answer penalty is expressed entirely by the R7 formula and
    the quiz-level negative-marking toggle.

  The system parses rows in file order into canonical `questions` (text, `N` option
  texts, correct-option set, points).
- **R1.3** Parsing is **all-or-nothing** and reports **every** bad row with **every**
  reason for that row in one pass (not just the first failure). A valid file inserts
  all questions; an invalid file inserts none and returns a structured per-row error
  list, not a generic 500. Header errors (missing/misnamed/duplicated column, wrong
  option-column count vs. `N`) are reported before any row parsing.
- **R1.4** Row validation rejects, with a clear message: empty question text; wrong
  number of non-empty option cells (≠ `N`); duplicate option text within a row; a
  `correct_options` entry naming a letter outside the first `N` letters, or an empty
  `correct_options` cell; a `points` value that isn't a non-negative number; an option
  text too long to print legibly, measured against the **printable column width in the
  shared geometry config** (see §3.2A — this config is authored as a static artifact
  in Phase 1, *before* ingestion is built, specifically so this check has a real
  number to validate against instead of a not-yet-built PDF template — Round 3 fix,
  §6 Q15).
- **R1.5** Questions are immutable after any version has been generated for the quiz
  (re-uploading requires discarding all versions first, which is blocked once any
  version has been marked printed — R3.5).

### Version generation

- **R2.1** The professor requests `M` versions. The system generates `M` versions,
  each with an independently shuffled question order and, per question, an
  independently shuffled option order. Stored as `question_order` (canonical question
  IDs in shuffled order) and `option_order` (per question: canonical option indices in
  shuffled order).
- **R2.2** For a realistic `M` (≤ ~20), no two versions share an identical
  `question_order` — verified programmatically. **Feasibility guard (Round 3, §6
  Q12):** at request time, the system checks `M` against the quiz's actual number of
  distinct question-orderings (`num_questions!`, or a saturating comparison for large
  question counts). If `M` exceeds that count, generation is **rejected outright**
  with a clear error ("cannot generate `M` versions with distinct question orders for
  a `Q`-question quiz — maximum is `Q!`") — nothing is written. Silently allowing
  duplicate `question_order`s would defeat the anti-copying purpose, so this fails
  loud rather than degrading quietly. (This limit is only reachable on very small
  quizzes — e.g. `Q=3` caps `M` at 6 — and is not expected to bind at realistic exam
  sizes.)
- **R2.3** Every version's per-question option order is a genuine permutation of that
  question's options (same multiset, reordered) — verified programmatically for every
  question of every version.
- **R2.4** The correct answer is always recoverable: for a known input, the true
  correct-option text for a sampled question is reconstructed **purely** from the
  stored `question_order` + `option_order` (no side bookkeeping) and matches the source
  spreadsheet — verified for multiple versions and multiple questions including at
  least one where both orders are non-identity permutations.
- **R2.5 — Anti-clustering (exact thresholds, multi-correct-aware).** After shuffling,
  the *sheet position(s)* each question's correct answer(s) land in (bubble column
  `A..`, which equals the shuffled option letter) must satisfy **both** constraints
  across the version:
  1. **No run of 3+ consecutive questions** shares the same correct-answer letter
     (i.e. at most 2 in a row).
  2. **No single letter** is the correct answer for more than
     `MAX_LETTER_COUNT = ceil(num_questions × (1/N + 0.20))` questions — that is,
     `1/N` plus 20 percentage points, rounded up. (Examples: `N=4` → ≤ 45% of
     questions per letter; `N=5` → ≤ 40%; `N=3` → ≤ 53%.)

  **Multi-correct definition (Round 3 fix — closes a real ambiguity, §6 Q11):** for a
  question whose correct set `K` has `|K| > 1`, **every letter in `K` counts once**
  toward that letter's histogram total for constraint 2, and toward the consecutive-run
  check in constraint 1 (each letter's run is tracked independently — "letter B is in
  `K` for questions 5, 6, 7" is a violation of constraint 1 for letter B, regardless of
  what else those questions' `K` sets contain). A single-correct question is just the
  `|K| = 1` case of the same rule, so no separate code path is needed.

  The pass re-rolls the option order of offending questions (up to
  `MAX_RESHUFFLE_ATTEMPTS`, a named constant) until both hold, and also re-rolls if the
  version's per-letter correct-count histogram exactly equals that of an
  already-generated version in the same batch. If `MAX_RESHUFFLE_ATTEMPTS` is exhausted
  (only possible on pathologically small quizzes where the constraints are
  mathematically unsatisfiable), it falls back to the least-skewed candidate seen and
  records that in the version row — it never loops forever. All three constants are
  module-level, tested for termination.
- **R2.6** Generation is rejected (clear error, nothing written) if `M < 1`, the quiz
  has zero questions, or the R2.2 feasibility guard fails.
- **R2.7** **A version's `question_order` / `option_order` can never be updated or
  re-shuffled after creation.** There is no code path, no endpoint, and no admin
  action that mutates them. Verified by a route/table introspection test plus live
  attempts. A destructive migration touching the `versions` table requires an explicit
  backup step.

### Printable output

- **R3.1** For each version the system produces two PDFs:
  - a **question paper** — the version's questions in shuffled order with their
    shuffled options, human-readable, no bubbles required on it; and
  - a **generic OMR answer sheet** — a bubble grid only (`Q1..Qn`, each with `N`
    bubbles `A..`), plus registration marks, a page identifier, and the version's QR
    code. The answer sheet is *generic per (question count, N)* — it does not name the
    questions — so the same physical layout works regardless of shuffle.
- **R3.2** The answer sheet is **a single page** **[LOCKED]**, **A4 portrait**
  (US Letter also supported — slightly wider, never fewer questions). Quiz creation is
  rejected with a clear message if `num_questions` exceeds the capacity for its `N`:

  | `N` | Max questions per quiz |
  |---|---|
  | 2–4 | **120** |
  | 5 | **100** |
  | 6 | **80** |

  These figures live in the **shared geometry config** (§3.2A), authored in Phase 1
  as the design targets for the Phase 4 grid (4-column layout at `N≤4`, 3-column at
  `N≥5`, ~6mm bubble pitch, full quiet zones). Phase 4 may adjust each figure by ≤ 15%
  once the real grid is laid out and proof-printed — done as a config version bump
  (`template_version`), not a spec violation — and may not remove the cap. Rationale:
  class-scale exams here run well under 100 questions; a hard single-page cap
  eliminates multi-page stitching, a documented weak point of the first build.
- **R3.3** The answer sheet carries, in fixed template positions: a **full-perimeter
  registration system** — corner markers **and** edge timing/registration marks along
  at least two sides (Scantron-style), not just 4–5 isolated corner squares — plus a
  QR encoding the version's `qr_id`. **`qr_id` is a securely random, non-sequential
  token** (e.g. UUIDv4), not a guessable incrementing ID (Round 3 nit, §6 Q16). All of
  this geometry lives in **one machine-readable template file** that both the PDF
  renderer and the OMR pipeline read. They never hardcode coordinates independently.
- **R3.4** Re-downloading a version's PDFs returns byte-identical content each time
  (deterministic render; cached artifact). The QR remains decodable after the sheet is
  rasterized at scan resolution — verified by decoding it out of a rendered-then-
  degraded page image, not just the standalone QR PNG.
- **R3.5** The professor marks a version (or the whole quiz) "printed / in use."
  **Printed status is tracked at both levels (Round 3 fix — closes a data-model gap,
  §6 Q13):** each `version` row has its own `printed_at` (nullable), settable
  individually; `quiz.status` transitions to `printed` automatically the first time
  *any* version of that quiz is marked printed (this is the trigger that blocks
  re-upload per R1.5 — it does not require every version to be printed first). After a
  given version is marked printed, that version's data is hard-locked (R2.7 already
  makes the shuffle maps immutable unconditionally; the printed flag additionally
  gates question re-upload at the quiz level via R1.5).
- **R3.6** Because the professor **photocopies per-version masters** rather than
  printing one serialized sheet per student **[LOCKED]**, two answer sheets of the same
  version are physically identical. The system therefore does **not** rely on a
  per-sheet serial for identity or grouping. Consequences: R5.4 (grouping), R5.8
  (dedupe is best-effort), R6.4 (identity is manual).

### Scan capture

- **R4.1** Supported capture inputs **[LOCKED]**:
  - **a) Handheld phone photo** — one image per sheet, uploaded from the browser
    (file picker) or taken with the in-browser camera. Expect perspective/keystone
    distortion, uneven lighting, rotation, the page filling an unknown fraction of the
    frame, shadows, and glare.
  - **b) Batch multi-page PDF or image set** — the professor scans a stack on a
    copier/MFP to one PDF (or a zip/multiselect of images) and uploads it; the system
    splits it into pages and processes each page as one sheet.
  - **Soft operational limits (Round 3, §6 Q17):** batch uploads are capped at 200
    pages and 100MB per upload (configurable constants, not hardcoded magic numbers);
    exceeding either is rejected with a clear message before processing starts. Sized
    for the stated scale (~60 students) with headroom, and chosen to keep the
    lightweight DB-backed queue (§3.4) from being handed something it wasn't sized for.
- **R4.2** In-browser camera capture runs a fast local quality pre-check (blur +
  "is a page with a QR plausibly in frame") and prompts a retake on failure, before
  anything is uploaded. Thresholds are calibrated against **real** captured frames, not
  synthetic test patterns.
- **R4.3** If the browser is offline or the server is unreachable, camera capture is
  disabled with a persistent banner. A submission whose upload fails mid-flight is
  shown as "not submitted — retry," never counted as processed, never silently dropped.
  (No offline queue — that was a mobile-only feature and mobile is gone.)

### OMR & grading pipeline

- **R5.1** Given a page image, the pipeline: (1) locates the registration
  marks and computes a perspective transform that maps the scan to canonical answer-
  sheet geometry; (2) decodes the QR **from the rectified image**; (3) looks up the
  version; (4) crops every bubble region from the rectified image using the shared
  template geometry; (5) classifies each bubble filled / empty / ambiguous with a
  confidence; (6) translates filled positions back to canonical (question, option-set)
  via `question_order` + `option_order`; (7) scores against the master key and the
  grading config; (8) applies the confidence gate; (9) persists a submission + answers.
- **R5.2** **Alignment must work on real handheld phone photos**, not only on flat
  scans. Concretely: the alignment DoD is verified against a corpus of **real
  photographs of really-printed sheets** (see §5 Phase 5), covering rotation to ±20°,
  moderate keystone, the page occupying 40–100% of the frame, and typical indoor
  lighting. **Near-180° / upside-down orientation is an explicit, separately-tested
  case (Round 3, §6 Q18):** the corpus must include sheets captured upside-down or
  fed into the copier reversed. The registration-mark search must be orientation-
  tolerant enough to detect and correct a ~180° rotation (in addition to the ±20°
  fine-rotation tolerance), or — if that proves unreliable — must reliably recognize
  the "wrong orientation" case and return a clean, specific failure rather than
  attempting a bad fit. Which of those two behaviors is targeted is decided during
  Phase 5 based on what the corpus shows; either is acceptable, a silent wrong fit is
  not. Synthetic rasterizations of the PDF are a supplementary check, never the
  primary evidence. **This is the single most important requirement in the document**
  — it is what the first build never actually achieved.
- **R5.3** If registration marks can't be found or the fit quality is below an
  absolute threshold, the pipeline returns a clean "alignment failed — rescan"
  result. It never produces a guessed-but-wrong alignment. A wrong-but-"successful"
  read is strictly worse than a clean failure.
- **R5.4** For a batch upload, each page is an independent, complete submission
  (single-page sheets, R3.2). Pages that fail QR decode or alignment are listed
  individually as failures with the page number; they do not fail the batch.
- **R5.5** The bubble classifier's filled-vs-empty accuracy on a held-out set is
  ≥ 99% on clean scans and is measured **and reported** on the real-photo corpus
  separately (a lower bar there is acceptable if documented, as long as errors surface
  as *ambiguous* — R5.6 — not as confident wrong reads). **A second, professor-facing
  metric is also tracked (Round 3, §6 Q19): the expected per-submission finalize rate**
  — the share of real-corpus submissions that finalize with zero flagged answers at
  the chosen confidence threshold, given a stated typical question count. Per-bubble
  accuracy alone doesn't tell you what the professor experiences: on a 100-question,
  `N=4` sheet, ~400 bubbles at 99% accuracy implies several misclassifications per
  sheet, and R5.7 flags a whole question on any single ambiguous bubble within it — so
  a healthy finalize rate is not automatic from the bubble-accuracy number and is
  reported as its own DoD item in Phase 6.
- **R5.6** The classifier is robust to a **page-wide illumination gradient** — a
  darker bottom-of-page must not push genuinely-empty bubbles into "ambiguous" en
  masse. (Approach: per-crop local background normalization before feature extraction.
  Validate on the real-photo corpus.)
- **R5.7 — Confidence gate (mandatory).** An individual answer is **flagged** (not
  auto-scored, routes the whole submission to `needs_review`) when **any** of:
  - the QR is unreadable → whole submission fails with a distinct `qr_unreadable`
    result, no scoring, **no answer rows written**;
  - alignment failed → whole submission fails with a distinct `alignment_failed`
    result;
  - any bubble in that question classifies as `ambiguous` / below the confidence
    threshold;
  - **0** bubbles are filled for the question (always flags, regardless of type);
  - **> 1** bubble is filled for a **single-answer** question (`|key| = 1`).
  For a **multi-answer** question (`|key| > 1`), the number of filled bubbles is
  **not** itself a flag — any 1…`N` marks is a gradeable response, scored via R7.2;
  only low classifier confidence flags it.
  A submission is `finalized` **only** if zero of its answers are flagged.
- **R5.8** Duplicate detection is **best-effort** (no per-sheet serial, R3.6): if a
  new submission's rectified answer-pattern hash matches an existing finalized
  submission for the same version, it is flagged as a probable duplicate for the
  professor to confirm or keep. It is never auto-discarded.

### Scoring rules — **exact, resolved**

Per quiz, two toggles: **marking mode** (`partial` | `all_or_nothing`, default
`partial`) and **negative marking** (`on` | `off`, default `off`). Per question:
`points` (weight, default 1.0), the correct-option **set** `K` (`|K| = k ≥ 1`), and the
student's marked **set** `M`. Let `c = |M ∩ K|` (correct selected) and
`w = |M \ K|` (incorrect selected).

- **R7.1 — Unanswered.** If `M = ∅` the question scores **0**, always, under every
  toggle combination. (Negative marking never punishes a blank.)
- **R7.2 — `partial` mode.**
  `fraction = (c − w) / k`
  - negative marking **off**: `question_score = points × max(0, fraction)` — floored at
    0 per question.
  - negative marking **on**: `question_score = points × fraction` — may be negative
    (bounded below by `−points` when `c = 0, w = k`).

  Worked: single-correct (`k = 1`), right answer → `(1−0)/1 = 1.0` → full points; one
  wrong option → `(0−1)/1 = −1` → `0` (off) or `−points` (on). Multi-correct `k = 2`,
  student marks one right + one wrong → `(1−1)/2 = 0`. Marks both right → `1.0`.
- **R7.3 — `all_or_nothing` mode.**
  - `M = K` exactly → `question_score = points`.
  - `M ≠ K` (and `M ≠ ∅`) → `0` (negative marking off) or `−points` (on).
- **R7.4 — Total.** While a submission is `needs_review`, `total_score` is **null**
  (withheld — a partial total is misleading). Once `finalized` (no answer flagged),
  `total_score = Σ question_score` over **all** answers. With negative marking off the
  total is ≥ 0 by construction; with it on the total **is not floored** and may be
  negative. (A "floor the quiz total at 0" switch is a trivial future addition — §6 Q1
  residual.)
- **R7.5 — One implementation.** The scan pipeline and every professor manual
  correction compute `question_score` through a **single shared pure function**
  `score_question(marked_set, key_set, points, mode, negative)`. They can never diverge.
  A parity test asserts identical output for both call sites on a fixed battery of
  answer sets.
- **R7.6 — Re-score on config change (no stale scores).** Changing a quiz's marking
  mode, negative-marking toggle, default points, or any question's `points`
  **immediately re-scores every submission of that quiz** — finalized ones included —
  by re-running R7.2/R7.3 over each answer's **stored marked-option set** (which already
  incorporates any manual overrides). The re-score is a single audit-logged event per
  submission (`action: rescored`, with before/after totals). It is never blocked and
  never deferred. Re-scoring does not re-introduce confidence flags or change
  `manually_edited` markers; it can flip a submission's status only via the normal gate
  (e.g. `needs_review → finalized` is *not* caused by a re-score; a re-score of a
  `finalized` submission leaves it `finalized`).

### Results & review

- **R6.1** A results dashboard lists a quiz's submissions with status, score, capture
  time, assigned student (if any), and flag reasons. Filterable by status, sortable
  stably.
- **R6.2** Opening any submission (any status, not just flagged) shows a full answer
  sheet: every question 1..n with what the system read, the confidence, the canonical
  correct answer, correct/wrong/flagged, the resulting score, and an "edited" marker
  where a human changed it. Flagged rows are pinned to the top.
- **R6.3** The professor can override any answer's marked-option set on any submission
  (including finalized ones). An override re-scores that answer via the shared scoring
  function, clears the flag, stamps `manually_edited` + timestamp, recomputes the
  submission total, and re-evaluates status (finalizes if nothing is still flagged).
- **R6.4** Student identity is **manual** **[LOCKED]**: submissions arrive
  unidentified; the professor assigns each to a student — free text, or picked from an
  optional per-quiz roster the professor can paste in. **Roster paste format (Round 3,
  §6 Q20):** one student per line, `name` or `name, external_id` — the simplest format
  that covers both the plain-name and the has-an-ID cases without asking for a file
  upload. Assignment is editable and logged. (See §6 Q6 — if roster-bubble matching is
  wanted later, the sheet and data model change; decide now if so.)
- **R6.5** Every **automated grading decision** (initial read, score, status) and every
  **manual action** (override, student assignment, re-grade, duplicate confirmation) is
  written to an **append-only audit log** keyed to the submission, with actor,
  timestamp, and before/after. The submission detail view can show this history. This
  directly serves the "auditability / trust" priority. **Passive `read`/view events are
  explicitly not audited (Round 3, §6 Q13a)** — logging every open of a submission
  serves no stated goal here, and would make the audit log noisy for a single-user
  tool. Only state-changing and grading events are logged.
- **R6.6** The professor can export a quiz's results (CSV at minimum: student, version,
  total, per-question scores).

### Data integrity

- **R8.1** Migrations are ordered, versioned, and runnable non-interactively against a
  fresh database with zero manual steps. A CI job proves a clean DB migrates to head.
- **R8.2** The deployment ships a documented backup + restore path covering the
  database (especially `versions`) and the stored PDFs/scans. Restore is tested, not
  assumed.
- **R8.3** No LLM API key, LLM client library, or LLM network call exists anywhere in
  the **auto-finalize grading path** — verified by a source scan in CI (see §3 for the
  one bounded exception the user is being asked to approve).

---

## 3. Architecture — options & recommendations

**Nothing below is fixed except where marked [LOCKED].** The user is "open to
anything" on stack, with **architectural simplicity, scan/grade reliability, and
auditability** as the top priorities. **Deployment target: a laptop prototype** — one
`docker-compose` (app + Postgres), `localhost` only, **no TLS, no reverse proxy, no
remote host**. Scale is small (one professor, ~60 students/exam). Keep the design
deployment-portable (a proxy + real host can be added later) but build nothing for a
server now.

### 3.0 Shape of the system

Two realistic shapes:

| Option | Description | Trade-offs |
|---|---|---|
| **A — Python monolith + server-rendered UI** *(one deployable)* | One Python web app (FastAPI **or** Django) serves the API, renders the dashboard (server-side templates + a little JS, or HTMX), does the CV work in-process, talks to a local Postgres. `docker-compose` with just `app` + `postgres` (bind to `127.0.0.1`). | **+** Fewest moving parts; one language; one deploy; CV libraries are already in-process; trivial to run on one laptop; easiest to reason about and back up. **−** Dashboard interactivity is more manual than React; long CV jobs need a background worker (same codebase, e.g. a task queue or a thread pool) so web requests don't block. |
| **B — Python API + separate JS SPA** | FastAPI (or Django REST) backend + a React/Next.js frontend, deployed as two containers behind one proxy. | **+** Richer dashboard/review UI; familiar to the user (they just rebuilt the web app in Next.js). **−** Two build toolchains, two deploy units, CORS/auth-token plumbing, API-contract drift between them — exactly the class of glue the "simplicity" priority is pushing against. Overkill for one professor at a time. |

**[RECOMMENDED — confirmed default]: Option A, with Django.** Reasoning: Django gives
you auth, admin, migrations, an ORM, forms, file storage, and a templating layer out of
the box — most of the non-CV surface of this app is CRUD + a review screen, which
Django does with very little code, and the built-in admin is a genuine asset for an
auditable professor-facing tool (it's also the fallback path for the no-password-reset
decision above). FastAPI is the alternative if you prefer typed Pydantic everywhere and
a lighter framework, but you'd re-add auth, migrations (Alembic), and an admin
yourself. Either way: **one repo, one app container + Postgres, one
`docker-compose.yml` on `localhost`** (a TLS proxy is a one-service addition if the
prototype is ever hosted — not now). The review UI's interactivity (inline answer
edits) is comfortably handled by HTMX or a few hundred lines of vanilla JS — it does
not need a SPA framework.

If the user wants React specifically for the review UI, do **Option B but still one
repo**, and generate the API client types from the backend's OpenAPI schema so they
can't drift.

### 3.1 Database / auth / storage

| Concern | Options | Recommendation |
|---|---|---|
| **Database** | (a) **Postgres in a container** in the same compose file. (b) SQLite file. | **[RECOMMENDED] Postgres.** JSONB for the shuffle maps, real concurrency, a real backup story. SQLite is tempting at this scale but the `versions` data is irreplaceable and Postgres's backup/replication tooling is worth it. Still trivial to self-host. |
| **Auth** | (a) **Framework-native** (Django auth / a small FastAPI + `argon2` + session cookies). (b) Supabase Auth. (c) An external IdP (Authentik/Keycloak). | **[RECOMMENDED] Framework-native, session-cookie based.** The first build used Supabase Auth and then *bypassed its RLS entirely* ("the backend is a trusted intermediary") — so Supabase was carrying auth complexity for no security benefit. Self-signup is **open, no allowlist / invite gate** [LOCKED] — acceptable because this is a localhost prototype. A standard hashed-password + secure-cookie session is right; no JWT/JWKS/clock-skew machinery, and no password-reset flow (§2 R0.1). |
| **Blob storage** (PDFs, raw + rectified scans) | (a) **Local filesystem** on a mounted Docker volume. (b) MinIO (S3 API) in the compose file. (c) Cloud object storage. | **[RECOMMENDED] Local filesystem volume**, accessed through a thin storage interface so it *could* be swapped for S3/MinIO later. At single-server small scale, a directory tree + the DB row that points at it is the simplest thing that is also easy to back up (`tar` the volume). |

**Net:** drop Supabase entirely. `docker-compose`: `app`, `postgres` (both on
`127.0.0.1`, no `proxy` service). One volume for Postgres data, one for blob storage.

### 3.2 PDF generation

| Option | Trade-offs |
|---|---|
| **ReportLab** (draw to exact coordinates) | **+** Precise, deterministic, pin every bubble/mark to an exact point, share the geometry file with OMR. Proven for this in the first build. **−** Layout code is imperative and verbose, especially the question paper's flowing text. |
| **WeasyPrint** (HTML/CSS → PDF) | **+** The *question paper* (flowing text) is far nicer to lay out in HTML. **−** Sub-pixel placement of OMR marks/bubbles is not something you want to trust to a CSS layout engine. |
| **Hybrid** | Question paper via WeasyPrint/HTML; **answer sheet via ReportLab** from the shared geometry template. |

**[RECOMMENDED — confirmed default]: Hybrid.** The answer sheet is the one that must
be geometrically exact and identical every time — ReportLab, driven by the same
template file the OMR pipeline reads. The question paper is just readable text —
HTML/WeasyPrint, or ReportLab Platypus if you'd rather not add a dependency. Keep the
OMR-critical path simple and exact; don't over-engineer the question paper.

### 3.2A Shared geometry config — extracted early **(Round 3 fix, §6 Q15)**

**Problem this closes:** R1.4 (option-text print-legibility check) and R3.2 (the
120/100/80 capacity table) are both *ingestion-time* validations (Phase 2), but the
numbers they validate against were originally scoped as Phase 4 (PDF renderer)
outputs. As sequenced, Phase 2 would have been validating against numbers that didn't
formally exist yet — a real phase-ordering bug, not just an inconvenience.

**Fix:** `config/sheet_template.json` — the single geometry source of truth referenced
throughout this document — is authored as a **static config artifact in Phase 1**,
before ingestion (Phase 2) or the renderer (Phase 4) are built. It only needs the
*numbers* (page size, margins, printable column width, chars-per-option limit at that
width, the capacity table by `N`), not a working renderer:

- Phase 1 ships `config/sheet_template.json` (v1) with these fields hand-derived from
  the page dimensions and a chosen font/size, plus the capacity table from R3.2.
- Phase 2 (ingestion) validates R1.4/R3.2 against this file directly — no PDF code
  involved.
- Phase 4 (PDF output) builds the actual ReportLab renderer **against the same file**
  and proof-prints it. If proof-printing shows the numbers need adjusting (R3.2's
  allowed ≤15% tolerance), Phase 4 bumps `template_version` in the config — a normal,
  planned config change, not a retroactive rewrite of what Phase 2 already validated
  against. Quizzes created in Phase 2 testing under `template_version: 1` remain
  self-consistent; production quiz creation after Phase 4 uses whatever
  `template_version` is current.
- The OMR pipeline (Phase 5/6) reads the same file for crop geometry, per R3.3's
  "one machine-readable template file" requirement — this was already the plan; the
  only change is *when* the file is created.

### 3.3 The CV / OMR + grading pipeline — the crux

This is where the first build failed repeatedly (a documented 6-round live-debugging
saga: wrong decode order, fixed-scale alignment assumptions, contour-retrieval mode,
keystone distortion, an illumination gradient, plus a stale-cache incident). The
lesson is **not** "the classical approach can't work" — it's that it was **designed
and tested against synthetic perfectly-aligned page rasterizations and then met real
phone photos for the first time in production.**

#### Design principles for the rebuild (apply regardless of which option below)

1. **A dedicated, generic, single-page OMR answer sheet** with a **full registration
   perimeter** (corner fiducials + edge timing marks), generous quiet zones, and a
   sparse bubble grid. This is a large reliability lever the first build gave up by
   putting bubbles inline with variable-length question text. A generic sheet also
   means one well-tuned template instead of per-quiz layout variance.
2. **Build a real-capture test corpus in Phase 0, before writing the aligner** —
   dozens of actual phone photos and actual copier scans of actually-printed sheets,
   with hand-labeled ground truth, **including upside-down / reversed captures**
   (Round 3, §2 R5.2). Every alignment/classification DoD is measured against it.
   Synthetic images are a supplement.
3. **An absolute fit-quality gate** on alignment (R5.3): below it → clean failure.
   Over-determine the perspective fit (≥ 6 registration points, not 4) so the fit
   residual is a real signal.
4. **Scale/level-invariant registration search** — never assume the page fills the
   frame or is at a known DPI.
5. **Local (per-bubble-neighbourhood) normalization** before classification (R5.6).
6. **Never cache a rendered artifact past a template change** (bust the cache on a
   template-version bump; the first build served 4-fiducial PDFs after moving to 5).

#### Option 1 — Classical pipeline, done properly

OpenCV homography from the registration perimeter → rectify → `pyzbar` QR decode →
grid crop from template → trained bubble classifier (start with logistic-regression on
darkness features + local normalization; escalate to a small CNN only if the corpus
demands it) → deterministic translate + score.

- **Reliability:** high *if* Phase 0's corpus work is done honestly. Fully predictable
  failure modes. The dedicated sheet + full perimeter removes most of what bit the
  first build.
- **Complexity:** moderate. All in-process Python. No external services, no GPU, no
  network.
- **Determinism / auditability:** total. Same image → same result, every time. Every
  step inspectable. This is the gold standard for "a professor must be able to trust
  and verify a grade."
- **Latency / cost / offline:** ~sub-second per page on CPU, zero marginal cost, fully
  offline.

#### Option 2 — Classical core + **bounded** LLM-vision fallback (review queue only)

Everything in Option 1 for the **auto-finalize path**. Additionally: for a bubble or a
sheet the classical gate has **already flagged**, optionally send that **cropped
region** (or the rectified sheet) to a vision model to produce a *suggested* reading,
shown to the professor in the review UI as "AI suggestion: B — confirm?". The LLM output
**never** auto-finalizes, never changes a score without a human click, and is labeled
as a suggestion in the audit log.

- **Buys:** a faster review queue — the professor confirms suggestions instead of
  reading every ambiguous crop cold. Helpful when a batch has many marginal marks.
- **Costs:** an optional external dependency + API key + per-call cost + latency on the
  review path only; a second code path to maintain; a source-scan exception in CI
  (scoped to the review module). Determinism of *final* grades is unaffected because a
  human is always in the loop for anything the LLM touched.
- **Offline:** the fallback is unavailable offline; the system still fully functions
  (it just shows the raw crop, as Option 1 would).

#### Option 3 — LLM vision as the primary reader

Send each rectified sheet (or the raw photo) to a vision model and ask for the marked
options per question.

- **Buys:** potentially less CV code; possibly more tolerant of bad captures.
- **Costs:** **not acceptable for this project as the primary path.** Non-deterministic
  (same image can yield different reads across calls/model versions); not
  auditable in the way a professor needs ("why did it read B?" has no inspectable
  answer); per-exam cost and latency scale with class size; requires connectivity at
  grading time; a model deprecation silently changes grades; and it directly violates
  the "auditability / trust" priority the user ranked top-three. Listed for
  completeness only.

#### Decision on the pipeline — **RESOLVED (§6 Q4 → option b)**

**Build Option 1 as the sole grading path.** The classical pipeline auto-finalizes and
is **the only thing that ever produces a grade.** Design the flagged-item review module
with a clean internal seam (a `ReadingSuggester` interface) so an LLM aid can be added
**behind an off-by-default config flag** (Phase 10). That aid may **only** suggest a
reading for a mark the classical gate has **already flagged** for manual review; it
never scores, never auto-finalizes, never runs on the auto-finalize path, and every
suggestion it makes is labeled as such in the audit log. Shipped default: **flag off →
strict zero-LLM.** The CI source-scan (R8.3) permits an LLM import **only** inside the
`readingsuggester/` module and fails the build on an LLM reference anywhere else.

#### The zero-LLM analysis (kept for the record)

The first build treated "no LLM anywhere in scanning/grading" as an absolute. Re-examined:

| Dimension | Purely classical (Option 1) | LLM-assisted (Option 2, fallback only) | LLM-primary (Option 3) |
|---|---|---|---|
| **Reliability on good scans** | Excellent | Excellent (classical handles them) | Good but variable |
| **Reliability on bad scans** | Fails *safely* (flags) | Same, + a suggestion to speed review | Sometimes better, sometimes confidently wrong |
| **Determinism** | Total | Total for final grades (human confirms) | None |
| **Auditability** | Full — every step inspectable | Full for grades; LLM step labeled "suggestion" | Poor — no inspectable reason for a read |
| **Latency** | Sub-second/page, local | Same, + seconds per *flagged* item | Seconds per sheet, every sheet |
| **Cost** | Zero marginal | ~cents per flagged item, opt-in | Per-sheet cost, unavoidable |
| **Offline** | Fully offline | Core offline; fallback needs network | Needs network to grade at all |
| **Failure mode of the dependency** | n/a | Fallback unavailable → back to raw crop | Grading stops / silently drifts on model change |

**This was the user's call and it matches the recommendation:** auto-finalize path
stays strictly classical and LLM-free; a strictly-bounded, off-by-default LLM
*suggestion* aid is permitted on the human review queue only (Phase 10, built only if
the review queue proves slow in practice).

### 3.4 Background processing

CV on an uploaded batch shouldn't block a web worker. At this scale you do **not** need
Celery + Redis. **[RECOMMENDED — confirmed default, Round 3, §6 Q21]: Django-Q2**,
running as a second process in the same container (`docker-compose` already brings up
`app` + `postgres`; Django-Q2 uses the Postgres ORM as its broker, so no third
service is needed). Chosen over `dramatiq`/`arq`/a bare `ThreadPoolExecutor` because it
is Django-native (fits the Option A / Django default in §3.0), has a DB-backed job
table out of the box (crash recovery for free, matching R4.3's "never silently
dropped"), and needs no extra broker container — keeping the deployable at exactly
`app` + `postgres`.

### 3.5 Summary of the recommended default stack

| Layer | Recommendation |
|---|---|
| Deployable shape | Single Python app, one `docker-compose` (app + Postgres, `localhost`, no proxy/TLS) |
| Framework | Django |
| Frontend | Server-rendered templates + HTMX / minimal JS |
| DB | Postgres (container) |
| Auth | Framework-native, session cookies, open self-signup (no gate), no password reset |
| Storage | Local filesystem volume behind a storage interface |
| PDF | ReportLab for the answer sheet (from shared geometry config, §3.2A); HTML/WeasyPrint or Platypus for the question paper |
| CV/OMR | OpenCV + `pyzbar` + a trained bubble classifier; dedicated single-page generic OMR sheet with a full registration perimeter; real-capture test corpus (incl. upside-down captures) |
| Grading | Deterministic; one shared scoring function; strictly LLM-free auto-finalize path |
| LLM | None on any grading path. A bounded suggestion-only review-queue aid is permitted behind an off-by-default flag (Phase 10, build later only if needed) |
| Background jobs | Django-Q2, same container, Postgres-backed |

---

## 4. Scope

### Recommended product scope for the rebuild

**Keep (core to the original goal — eliminate manual creation + grading of shuffled
MCQ exams):**

- Professor auth (self-signup, no password reset).
- Quiz creation + spreadsheet upload + validation.
- Version generation (question + option shuffle) with multi-correct-aware
  anti-clustering, immutable maps, and an `M`-feasibility guard.
- Per-version question paper PDF + generic single-page OMR answer sheet PDF with QR.
- Scan intake: single phone photo (upload or in-browser camera) **and** batch
  multi-page PDF/scan upload, with soft size/page limits.
- Classical OMR pipeline: rectify → decode → crop → classify → translate → score →
  confidence gate.
- Results dashboard + full per-submission answer-sheet review + manual overrides.
- Manual student assignment (+ optional pasted roster).
- Audit log for every automated grading decision and manual action (not passive reads).
- CSV export of results.
- `docker-compose` on `localhost` (one command), with local backup + tested restore
  and a short ops runbook.

**Add vs. the first build (all [LOCKED] by user answers):**

- Weighted / negative / partial-credit scoring config per quiz.
- Multiple-correct-answer ("select all") questions.
- Professor-set option count `N` (2–6) per quiz.
- Batch scan/PDF upload as a first-class capture path.
- A dedicated generic OMR answer sheet, separate from the question paper.
- An explicit audit log (was only partial "edited" markers before).
- A shared geometry config authored early (Phase 1) so ingestion-time print/capacity
  checks have real numbers to validate against (Round 3 addition).

**Drop vs. the first build (proposed — all consistent with user answers, listed for
explicit sign-off):**

- **The entire Flutter mobile app**, its offline queue, background sync, and any
  "mobile contract" constraint on the API. **[LOCKED]**
- **Supabase** (Postgres+Auth+Storage) → self-hosted Postgres + native auth + volume
  storage. Follows from the localhost-prototype target + "open to anything" +
  simplicity priority.
- **Handwritten-name OCR** (Tesseract) — dropped entirely. Replaced by manual student
  assignment **[LOCKED: identity = manual]**; OCR was a confidence-gate maintenance
  burden for marginal benefit. No roster/student-ID-bubble matching either (§6 Q6).
- **The QR-only, bubbles-inline-with-questions answer format** → dedicated generic
  answer sheet. *Proposed (§6 Q3 answered — single-page dedicated sheet confirmed).*
- **Cloud Run / Vercel / hosted deployment / TLS / Cloudflare tunnel.** Gone —
  the target is `docker-compose` on `localhost` **[LOCKED: laptop prototype]**.
- **Client-generated `capture_id` idempotency.** With per-page batch submissions and
  best-effort content-hash dedupe (R5.8), a client capture token adds little. *Proposed
  to drop; revisit only if in-browser retry proves to double-submit.*
- **Password-reset flow.** Not needed for a single-professor local tool; DB/admin
  access is the recovery path. **(Round 3.)**

**Explicitly NOT adding (guard against scope creep):**

- LMS/gradebook integration, student accounts, email notifications, analytics
  dashboards, multi-institution tenancy, a public API, i18n. None serve the core goal.

### Deviations from the original goal — all signed off

| Deviation | Why it still serves "eliminate manual creation + grading of shuffled MCQ exams" | Status |
|---|---|---|
| Separate answer sheet instead of one combined PDF | Professor still prints + hands out paper and still gets auto-grading; reliability of the auto-grading (the goal's second half) goes up materially. Slight cost: two documents to print instead of one. | ✅ §6 Q3 |
| Manual student assignment instead of automated name reading | The goal is about *grading effort*, not *identity capture*. Assigning ~60 scans to names is minutes; chasing OCR misreads was hours. Net manual burden goes **down**. | ✅ §6 Q6 |
| Single-page answer-sheet cap | Removes multi-page stitching (a first-build weak point) entirely. Cost: a hard ceiling on questions per quiz (120 / 100 / 80 by `N`). Ample at this scale. | ✅ §6 Q3 |
| Drop mobile | User abandoned it. Browser camera + batch upload cover the capture need for a web-only tool. | ✅ [LOCKED] |
| LLM permitted (bounded) on the review queue | Auto-finalize grades stay 100% classical/deterministic/auditable; the LLM only ever speeds a human confirming an already-flagged mark. | ✅ §6 Q4 → b |
| No password reset | Single-user local tool; DB/admin access covers the recovery case at near-zero build cost. | ✅ §6 Q13 (Round 3) |

---

## 5. Build plan

### Process pattern — keep it

**Keep the first build's process**: a governing doc (`CLAUDE.md`-equivalent — this
file's descendant), numbered phase files worked in order, and a **per-subtask
Definition of Done that is verified by running something, not by assertion**, with a
running `PROGRESS.md` log and one commit per subtask. **Why:** independent of what got
built, that process produced honest, traceable progress — the `PROGRESS.md` log is
detailed enough that this very rebuild spec could be written from it. The discipline of
"DoD verified by a real test run" is exactly right for a high-stakes grading tool.

**Change four things about the process** (Round 3 adds the fourth):

1. **The real-capture test corpus is a Phase 0 deliverable, not a Phase 5
   afterthought.** Nothing in the OMR phases may be marked DoD-done against synthetic
   images alone.
2. **A "reliability budget" gate**: the OMR phases don't complete until measured
   accuracy on the real corpus meets a written bar, or the shortfall is documented and
   accepted by the user in `PROGRESS.md`.
3. **No "note the assumption and continue" on anything touching the scoring formula,
   the data model's hard-to-change columns, or the answer-sheet geometry.** Those
   stop-and-ask. (The first build's looser default was fine for UI details, not these.)
4. **The shared geometry config (§3.2A) is authored in Phase 1, not Phase 4.** Any
   phase that validates against page/print geometry (Phase 2's ingestion checks)
   reads this file directly instead of waiting on the renderer. This is the Round 3
   fix for the ordering bug described in §3.2A / §6 Q15.

### Phases

| # | Phase | Key DoD themes |
|---|---|---|
| **0** | **Scaffold + capture corpus** | One repo; `docker-compose` boots `app` + `postgres` on `localhost` (no proxy); CI runs lint + tests + a clean-DB migration; **a starter corpus of ≥ 30 real phone photos + ≥ 10 real copier scans of printed test sheets, with hand-labeled ground truth, is committed.** The corpus **must include sheets photocopied 1–2 generations before being filled in** (§6 Q10) — not only first-generation laser prints — **and must include upside-down / reversed captures** (§6 Q18, Round 3). Use a throwaway hand-designed sheet if Phase 4 isn't done; the point is real optics early. |
| **1** | **Data model + auth + migrations + shared geometry config** | All tables (see below, incl. `version.printed_at`) created by ordered migrations; cross-account isolation test passes; self-signup + login + session works end to end (no password-reset route). **`config/sheet_template.json` v1 authored** (page size, printable column width, chars-per-option limit, capacity table) per §3.2A — numbers only, no renderer yet. |
| **2** | **Quiz ingestion + scoring config** | Header-validated `.xlsx` parser per R1.2 (name-checked columns, `N` option columns, `correct_options` set, optional `points`); all-or-nothing with full per-row + header error lists; option-length and quiz-capacity checks validated **against `config/sheet_template.json` from Phase 1** (not a not-yet-built renderer); scoring config per R7 (mode toggle, negative-marking toggle, default points) stored + validated; the shared `score_question` pure function + its parity test (R7.5); option count `N` enforced. |
| **3** | **Version generation** | Shuffle + independent per-question option shuffle; `M`-feasibility guard (R2.2/R2.6) rejects infeasible `M` before writing anything; **anti-clustering to the exact, multi-correct-aware R2.5 thresholds** (≤ 2 consecutive same letter per-letter-independent; ≤ `ceil(n × (1/N + 0.20))` per letter, each letter of a multi-correct `K` counted; no duplicate histogram in a batch) + provable termination; maps immutable (route + ORM introspection test); correct-answer recoverable purely from stored maps, including multi-correct questions. |
| **4** | **PDF output** | Deterministic byte-identical renders; generic single-page A4 OMR sheet built **against `config/sheet_template.json`** with a full registration perimeter (corners + edge marks), random (non-sequential) `qr_id` in the QR; capacity cap enforced per the R3.2 table; grid proof-printed and, if needed, adjusted ≤15% via a `template_version` bump (not a rewrite of Phase 2's already-validated numbers); question paper legible; over-long quiz rejected at creation; QR decodes after rasterization + degradation; template-version cache-busting on the stored artifact. |
| **5** | **Alignment on real captures** | Registration-perimeter detection + over-determined perspective fit + absolute quality gate + scale-invariant search; orientation handling for near-180° captures per R5.2 (detect-and-correct or clean-and-specific-failure — decided against the corpus); **measured against the Phase 0 corpus**: rectified bubble-grid coordinates within tolerance across the corpus's rotation/keystone/framing range; occluded/failed/reversed cases return clean failure, never a wrong fit. |
| **6** | **Bubble classifier + confidence gate** | Local-normalization feature path; ≥99% held-out on clean + a reported number on the real corpus; **expected per-submission finalize rate reported as its own metric** (R5.5, Round 3) alongside bubble accuracy; illumination-gradient robustness shown on the corpus; ambiguous cases route to low confidence, never confident-wrong; gate rules for multi-correct + `N` options implemented exactly per R5.7. |
| **7** | **Scan → grade service** | Full pipeline wired; single-image and batch-PDF intake with the R4.1 soft size/page limits enforced; per-page independent submissions; the R7.5 shared `score_question` used by the pipeline; partial / negative / multi-correct / weighted scoring matches hand-computed expected values for several constructed sets across both toggle combinations; **R7.6 auto-re-score on config change** (finalized submissions included, audit-logged); distinct failure modes (`qr_unreadable`, `alignment_failed`) never folded into `needs_review`; best-effort content-hash dedupe (§6 Q5 — flag-and-confirm, never auto-discard). |
| **8** | **Dashboard + ingestion UI** | Quiz CRUD, upload, version generation, PDF download, results list with filter/sort — all against the real backend, e2e-tested. |
| **9** | **Review UI + audit** | Full per-submission answer sheet (all statuses), inline overrides via the shared scoring path, manual student assignment + pasted roster (`name` or `name, external_id` per line), append-only audit log (grading/mutation events only, not passive reads) surfaced in the UI, CSV export. Per-version "mark printed" control (sets `version.printed_at`; first one on a quiz flips `quiz.status` to `printed`). |
| **10** | **(Deferred) LLM suggestion aid** | Permitted (§6 Q4 → b) but **build only if the Phase 9 review queue proves a real time sink.** `ReadingSuggester` behind an off-by-default flag, review-queue only, suggests on already-flagged marks only, never auto-finalizes, labeled in the audit log; CI source-scan exception scoped to `readingsuggester/` alone. |
| **11** | **End-to-end + load** | Happy path and unhappy path (bad spreadsheet row, ambiguous bubble, unreadable QR, failed alignment, duplicate, upside-down scan, infeasible `M` request) through the real UI + real backend; a class-scale batch (60 sheets, 5 versions, 100 questions) completes within a written time bound with no correctness or memory regression. |
| **12** | **Packaging + ops** | `docker-compose up` on a clean laptop brings the whole app to `http://localhost:<port>` with one command and a documented `.env`; `pg_dump`/restore scripts writing to a local backup dir + **a tested restore** (the `versions` data is irreplaceable — R8.2); a short runbook (first run, migrate, backup, restore, wipe-and-reseed); CI green. **No TLS, no host provisioning, no remote deploy** — out of scope until the prototype graduates. |

### Repo structure (recommended, Option A / Django)

```
/app            the Django project
  /omr            alignment, classification, geometry — pure, no web imports
  /grading        shuffle, scoring — pure, no web imports
  /pdf            renderers, reads /config/sheet_template.json
  /web            views, templates, forms
  /config         sheet_template.json  (shared geometry — single source of truth, authored Phase 1)
/corpus         real captured images + ground-truth labels  (Phase 0, incl. upside-down)
/tests
/deploy         docker-compose.yml, .env.example, backup/restore scripts, runbook
/docs           REBUILD_SPEC.md (this file), PROGRESS.md, phase files
```

Keep `/omr` and `/grading` importable with zero web-framework dependencies so they're
testable in isolation and the pipeline logic never gets tangled with request handling.

---

## 6. Decision record (was: open questions) — all resolved

Every item below is answered. Resolutions are already folded into §2/§3/§5; this
section records *what was decided*, across three rounds. Round 1/2 items (Q1–Q10) are
unchanged from the prior revision. **Round 3 (Q11–Q21) is a critical-review pass that
found and closed real gaps.**

### Round 1/2 — Q1 through Q10

#### Q1 — Scoring formula — **RESOLVED** (full spec in §2 R7)

- **Partial credit, per question:**
  `fraction = (correct_selected − incorrect_selected) / |key|`, then
  `question_score = points × fraction`. Floored at **0 per question** when negative
  marking is off; **not** floored when it is on.
- **`all_or_nothing`** is a per-quiz toggle (default `partial`).
- **Negative marking** is a per-quiz toggle, **default off**. On ⇒ per-question scores
  and the quiz total may go negative.
- **Unanswered = 0**, always, under every toggle combination.
- **`points`** is a per-question optional spreadsheet column with a quiz-level default.
  **No penalty parameter** — the formula + negative-marking toggle express it.
- **Config change ⇒ automatic re-score of every submission** (finalized included),
  audit-logged, never blocked (R7.6). No frozen/stale scores.
- **Residual (non-blocking):** no "floor the quiz *total* at 0 while negative marking is
  on" switch; add later only if asked.

#### Q2 — Spreadsheet contract — **RESOLVED** (§2 R1.2)

`question_text | option_1 … option_N | correct_options | points(optional)`.
**`.xlsx` only, no CSV.** **Header row required, validated by column name**, not by
position. `N` is set in the quiz-creation form; the parser checks each row has exactly
`N` non-empty option cells. `correct_options` = one or more of the first `N` letters,
comma/space separated; its size decides single- vs multi-correct. **No penalty column.**

#### Q3 — Single-page capacity — **RESOLVED** (§2 R3.2)

**A4 portrait** (Letter also fine). Caps enforced at quiz creation: **120 questions for
N ≤ 4, 100 for N = 5, 80 for N = 6.** Phase 4 may tune each by ≤ 15% after
proof-printing; the single-page cap itself stays. (Round 3: these numbers now live in
`config/sheet_template.json`, authored Phase 1 — see §3.2A.)

#### Q4 — Zero-LLM — **RESOLVED: option (b)** (§3.3)

Classical pipeline auto-finalizes and is the **only** thing that ever produces a grade.
An LLM aid, **off by default**, may **only** suggest a reading on the manual-review
queue for marks the classical gate already flagged — never scores, never auto-finalizes,
never on the auto-finalize path. Build it (Phase 10) only if the review queue proves a
real time sink.

#### Q5 — Duplicate prompts — **RESOLVED: acceptable**

Keep best-effort content-hash dedupe (R5.8): a probable duplicate is **flagged for the
professor to confirm or keep**, never auto-discarded. No per-sheet serial, no
`printed_sheets` table. A low rate of confirm prompts is accepted.

#### Q6 — Roster / student-ID matching — **RESOLVED: not now**

Manual student assignment only (R6.4). **No student-ID bubble block is designed into the
sheet.** If roster matching is wanted later it is an explicit sheet-changing,
data-model-changing project at that time — accepted cost.

#### Q7 — Self-signup — **RESOLVED: open, no gate**

No allowlist, no invite code, no admin approval. Acceptable because the app runs on
`localhost` only. **If it is ever put on a network, revisit this before doing so** —
same trigger point applies to the Round 3 no-password-reset decision (Q13).

#### Q8 — Where it runs — **RESOLVED: laptop prototype**

One `docker-compose` on the user's laptop, `localhost`, **no TLS / proxy / remote host /
dynamic DNS**. Phase 12 = packaging + local backup/restore only. Graduating the
prototype to a real host is future work with its own decisions (TLS, domain, off-box
backups, auth hardening per Q7).

#### Q9 — Anti-clustering — **RESOLVED: correct-answer letter, exact thresholds** (§2 R2.5)

The user chose letter-based constraints (not column-position):
1. **≤ 2 consecutive** questions may share the same correct-answer letter (no run of 3+).
2. **≤ `ceil(num_questions × (1/N + 0.20))`** questions may share the same
   correct-answer letter (`1/N` plus 20 percentage points, rounded up).
Plus: no two versions in a batch may share an identical per-letter correct-count
histogram. Re-roll offenders up to a named max-attempts, then fall back to the
least-skewed candidate. **(Round 3, Q11 below, closes the multi-correct ambiguity in
this rule that Round 1/2 left implicit.)**

#### Q10 — Photocopy robustness — **RESOLVED: required in the corpus**

The Phase 0 test corpus **must** include sheets photocopied 1–2 generations before
being filled in and captured — not only first-generation laser prints. The
registration-perimeter and classifier DoDs are measured against those too.

### Round 3 — Q11 through Q21 (this revision)

#### Q11 — Multi-correct anti-clustering — **RESOLVED: per-letter-independent counting**

R2.5 as originally written assumed one correct letter per question. Resolved: for a
multi-correct question, **every letter in its correct set `K` counts once** toward
that letter's histogram total (constraint 2) and toward that letter's independent
consecutive-run tracking (constraint 1). Single-correct questions are the `|K|=1` case
of the same rule — no separate code path.

#### Q12 — `M` exceeding feasible distinct question-orders — **RESOLVED: hard reject**

If the requested `M` exceeds the number of distinct question orderings possible for
the quiz's question count (`num_questions!`), generation is rejected outright with a
clear error before anything is written (R2.2/R2.6). Chosen over a silent-fallback
because allowing duplicate `question_order`s would defeat the anti-copying purpose of
the whole feature. Only reachable on very small quizzes.

#### Q13 — Per-version "printed" flag — **RESOLVED: tracked at both levels**

`version.printed_at` (nullable) is settable per version. `quiz.status` flips to
`printed` automatically the first time *any* version of the quiz is marked printed —
this is what triggers the R1.5 re-upload block, not a requirement that every version
be printed first.

#### Q13a — Password reset — **RESOLVED: not built**

Single-professor local tool; recovery via direct DB/Django-admin access on the laptop.
Revisit at the same trigger point as Q7 (network exposure) or if the tool becomes
multi-professor.

#### Q14 — Multi-tenant auth machinery for a single-user tool — **RESOLVED: kept as-is**

R0.2's cross-account isolation model stays, even though the stated primary use case is
one professor on one laptop. Reasoning: it was already a signed-off decision from an
earlier round, Django provides most of it for free, and it costs little to keep versus
the churn of relitigating a locked decision without a concrete reason to change it.

#### Q15 — Phase-ordering dependency (ingestion validating against a not-yet-built renderer) — **RESOLVED: geometry config extracted to Phase 1**

See §3.2A. `config/sheet_template.json` is authored as a static numbers-only artifact
in Phase 1; Phase 2 validates against it directly; Phase 4 builds the actual renderer
against the same file and may bump `template_version` by ≤15% after proof-printing
without invalidating what Phase 2 already checked.

#### Q16 — QR token predictability — **RESOLVED: random token**

`qr_id` is a securely random, non-sequential token (UUIDv4 or equivalent), not an
incrementing ID. Low real-world risk here (paper exam, not an auth credential) but
free to get right.

#### Q17 — Batch upload limits — **RESOLVED: soft caps added**

200 pages / 100MB per batch upload, rejected with a clear message before processing.
Sized with headroom over the ~60-student scale and chosen to keep the DB-backed queue
(no Celery/Redis) from being handed an unbounded job.

#### Q18 — Upside-down / reversed captures — **RESOLVED: explicit corpus + DoD case**

The Phase 0 corpus must include upside-down/reversed captures, distinct from the
±20° fine-rotation tolerance already required. Phase 5 decides, based on what the
corpus shows, whether the aligner detects-and-corrects near-180° rotation or reliably
returns a clean, specific failure for it — either is acceptable, a silent wrong fit is
not.

#### Q19 — Bubble accuracy vs. professor-experienced finalize rate — **RESOLVED: track both**

R5.5's ≥99% bubble-level accuracy target is necessary but not sufficient to describe
what the professor experiences, since any single ambiguous bubble flags its whole
question (R5.7). Phase 6 additionally reports an **expected per-submission finalize
rate** on the real corpus as its own DoD metric.

#### Q20 — Roster paste format — **RESOLVED: one line per student**

`name` or `name, external_id` per line — no file upload required, covers both the
plain-name and has-an-ID cases.

#### Q21 — Background job queue — **RESOLVED: Django-Q2**

Committed default (was left as three open options in the prior revision): Django-Q2,
Postgres-backed, same container as the app — no third `docker-compose` service. See
§3.4.

---

## Appendix A — Provisional data model (for discussion; finalize in Phase 1)

Reflects the §6 resolutions, including Round 3. Finalize column types in Phase 1.
Postgres.

- **professor** — id, email (unique), password_hash, created_at. *(No
  password-reset-token field — no reset flow, §6 Q13a.)*
- **quiz** — id, professor_id, title, options_per_question `N` (2–6), marking_mode
  (`partial` | `all_or_nothing`, default `partial`), negative_marking (bool, default
  false), default_points (default 1.0), status (`draft` | `versioned` | `printed`),
  created_at. (No penalty / floor columns — R7 needs none. `status` flips to `printed`
  automatically the first time any child `version.printed_at` is set — §6 Q13.)
- **question** — id, quiz_id, order_index, text, options (jsonb: `["A text", ...]`,
  length `N`), correct_options (jsonb: `["A","C"]` canonical, length ≥ 1 — `is_multi`
  is just `len > 1`, not stored), points (nullable → quiz default). Immutable once
  quiz.status ≥ `versioned`.
- **version** — id, quiz_id, version_number, qr_id (unique, **securely random token —
  §6 Q16**), question_order (jsonb), option_order (jsonb:
  `{question_id: [canonical_option_index,...]}`), template_version (int),
  **printed_at (nullable timestamp — Round 3, §6 Q13)**, created_at. **No update path
  for `question_order`/`option_order`. Ever.**
- **roster_entry** — id, quiz_id, label (free text / name), external_id (nullable).
  Optional, professor-pasted (one `name` or `name, external_id` per input line — §6
  Q20).
- **submission** — id, version_id, status (`pending` | `needs_review` | `finalized` |
  `failed`), failure_reason (nullable: `qr_unreadable` | `alignment_failed` | ...),
  roster_entry_id (nullable), student_label (nullable free text), total_score
  (nullable), raw_image_path, rectified_image_path (nullable), answer_hash (nullable),
  duplicate_of (nullable self-fk, professor-confirmed), source (`photo` | `batch_pdf`),
  batch_id (nullable), page_number (nullable), created_at.
- **answer** — id, submission_id, question_no (canonical order_index), detected_options
  (jsonb: `["B"]` or `["A","C"]` or `[]`), confidence (float), flagged (bool),
  flag_reason (nullable), correct (bool, nullable), score (float, nullable),
  manually_edited (bool), edited_at (nullable).
- **audit_event** — id, submission_id (nullable — some events are quiz-scoped, e.g. a
  scoring-config change that triggers R7.6), quiz_id, actor (`system` | professor_id),
  action (`scored` | `overridden` | `assigned` | `rescored` | `duplicate_confirmed` |
  `suggested` | `printed` | …), detail (jsonb: before/after), created_at. Append-only.
  **`read` is intentionally not an audited action — §6 Q13a / R6.5 (Round 3).**

## Appendix B — What to carry forward from the first build's hard-won lessons

Not code — lessons, safe to reuse:

1. QR decoding: `pyzbar` was reliable on this class of image; OpenCV's `QRCodeDetector`
   was not. Decode **after** rectification, never before.
2. Alignment must not assume the page fills the frame or a fixed DPI — sweep scale
   hypotheses; gate on an absolute fit residual; over-determine the fit.
3. A page-wide illumination gradient will falsely flag empty bubbles unless each crop
   is locally background-normalized. Threshold-tuning and training-data brightness
   augmentation were both tried and both made other things worse.
4. Never serve a cached rendered PDF after changing the sheet template — every printed
   page in the world still has the old geometry. Version the template and bust on bump.
5. Test OMR against real optics from day one. Synthetic PDF rasterizations hid every
   single real-world failure until production.
6. One geometry source of truth, read by both the renderer and the OMR code. Two
   copies drift. **(Round 3 extends this lesson one step earlier: the ingestion
   validator reads it too, from Phase 1 onward — §3.2A.)**
7. One shared scoring function for the pipeline and manual corrections. Two expressions
   drift.
8. `versions` mapping immutability enforced structurally (no route, no ORM path), not
   by convention.

---

*End of REBUILD_SPEC.md*
