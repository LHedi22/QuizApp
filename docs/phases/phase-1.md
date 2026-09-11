# Phase 1 — Data model + auth + migrations + shared geometry config

> Source: `docs/REBUILD_SPEC.md` §5 (Phases table, row 1), Appendix A, §3.1, §3.2A,
> §2 R0.1–R0.3. Governing rules: `docs/CLAUDE.md` (esp. rules 5 and 8).

## Phase goal

Turn Appendix A's provisional model into real, ordered migrations; stand up
framework-native session auth with open self-signup and **no password-reset route**;
enforce per-professor data ownership on the server; and author
`config/sheet_template.json` v1 (numbers only) so Phase 2's ingestion checks have
something concrete to validate against (§3.2A).

## ⚠ Two subtasks are gated on user sign-off (CLAUDE.md rule 5)

- **1.1 (data model)** touches Appendix A's hard-to-change columns → the field-type
  and enforcement decisions in the "Decisions for sign-off" section below must be
  approved before any `models.py` is written.
- **1.4 (`config/sheet_template.json`)** is answer-sheet geometry → the v1 numbers
  must be approved before the file is written.
- 1.2 (ownership) and 1.3 (auth) are not gated — build once 1.1 lands.

## What Phase 1 does NOT do

- No ingestion / parsing (Phase 2), no version generation (Phase 3), no PDF renderer
  (Phase 4), no OMR (Phase 5+).
- `config/sheet_template.json` v1 carries **numbers only** — no bubble-grid
  coordinates, fiducial positions, or timing-mark geometry. Those are authored in
  Phase 4 against the same file, which may bump `template_version` by ≤ 15% then
  (§3.2A). v1 just needs page size, margins, the question-paper printable width +
  chars-per-option limit, and the capacity table.

---

## Subtask 1.1 — Data model + ordered migrations  *(gated on sign-off)*

**Goal.** Every Appendix A table as a Django model with finalized field types, created
by ordered migrations that run non-interactively against a fresh DB.

**App layout.** Models live in a new Django app **`app.core`** (pure data + managers,
no views). `app.omr` / `app.grading` stay web-framework-free (rule 7) and must not
import `app.core`.

**Deliverables.**
- `app/core/models.py` — `Professor` (custom `AUTH_USER_MODEL`), `Quiz`, `Question`,
  `Version`, `RosterEntry`, `Submission`, `Answer`, `AuditEvent`.
- `app/core/managers.py` — an owner-scoped manager/queryset (feeds 1.2).
- `app/core/migrations/0001_initial.py` (+ any follow-ups), ordered.
- `app/core/apps.py`; add `app.core` to `INSTALLED_APPS`; set `AUTH_USER_MODEL`.
- `tests/test_data_model.py` — introspection tests (see DoD).

**Definition of Done (runnable).**
1. `python manage.py makemigrations --check --dry-run` → clean (no model drift) after
   the migration is committed.
2. Fresh DB: `python manage.py migrate` → head, zero prompts; `migrate --check` → 0.
3. `scripts/ci.sh` green (CI now migrates our own schema — re-asserts R8.1 precursor).
4. `tests/test_data_model.py` asserts, via `django.apps`/`_meta` introspection:
   - all 8 tables exist with the Appendix A columns;
   - `Version` has `printed_at` (nullable), `question_order`, `option_order`,
     `template_version`, `qr_id` (unique);
   - `Quiz.status` choices are exactly `draft|versioned|printed`;
   - `Submission.status` choices are exactly `pending|needs_review|finalized|failed`;
   - `AuditEvent` has no `update`/`delete`-exposing manager method beyond the guard
     (see 1.1 decisions).
5. `tests/test_immutability.py` (rule 8): constructing a `Version`, then attempting to
   reassign `question_order` / `option_order` and `save()` raises; `save(update_fields=[...])`
   targeting them raises; there is no admin registration or form/serializer exposing
   them. (DB-trigger layer: per sign-off.)

---

## Subtask 1.2 — Per-professor ownership isolation (R0.2)

**Goal.** A logged-in professor can only ever read/modify their own data; every data
route enforces it server-side.

**Deliverables.**
- Owner FK chain: `Quiz.professor` → everything else reachable by FK. An
  `owned_by(user)` queryset method on the core manager.
- A view mixin / helper `get_owned_or_404(model, pk, user)` used by every data view
  (only the ones that exist this phase — more added per phase).
- `tests/test_cross_account_isolation.py`.

**Definition of Done (runnable).**
1. `tests/test_cross_account_isolation.py`: create professors A and B; as A create a
   quiz, question, version, submission, answer, roster entry; then **as B**, request
   each by direct primary-key id through every read path that exists → **404 every
   time** (not 403, not 200). Repeat for every write/mutate path that exists.
2. An unauthenticated request to any data route → redirect to login / 403 **before**
   any queryset is evaluated (R0.3) — asserted with `assertNumQueries` or a spy.

---

## Subtask 1.3 — Auth: self-signup + login + session, no password reset (R0.1/R0.3)

**Goal.** A visitor can register (email + password) and log in; sessions work; there
is **no password-reset flow**.

**Deliverables.**
- `app/web/` auth views/urls: `register`, `login`, `logout` (Django's
  `LoginView`/`LogoutView` + a `CreateView`-style signup on the custom user).
- Templates: `register.html`, `login.html` extending `base.html`.
- `login_required` on the (currently trivial) dashboard placeholder view.
- **No** `PasswordResetView` / `password_reset` urls anywhere.
- `tests/test_auth_flow.py`.

**Definition of Done (runnable).**
1. `tests/test_auth_flow.py` (e2e via test client):
   - `POST /register` with email+password → account created, redirected, logged in;
   - `POST /login` after logout → session established, protected view returns 200;
   - `GET /logout` → protected view now redirects to login;
   - duplicate-email registration → form error, no second account;
   - `reverse("password_reset")` raises `NoReverseMatch`; `GET /accounts/password_reset/`
     (and common variants) → 404.
2. `python manage.py check` → 0 issues.

---

## Subtask 1.4 — `config/sheet_template.json` v1  *(gated on sign-off)*

**Goal.** Author the numbers-only geometry config and a pure loader both Phase 2 and
Phase 4 will use.

**Deliverables.**
- `config/sheet_template.json` — `template_version: 1`, page block (size, w/h mm,
  margins), `question_paper` block (printable column width mm, option font + size,
  derived `max_chars_per_option`), `answer_sheet.capacity_by_n` (the R3.2 table).
  Exact values per "Decisions for sign-off".
- `app/core/sheet_template.py` **or** `app/sheet_template.py` — a pure loader
  (`load_template() -> SheetTemplate` dataclass) with **zero web imports** so
  `app/omr` and ingestion can both use it. Validates on load.
- `tests/test_sheet_template.py`.

**Definition of Done (runnable).**
1. `tests/test_sheet_template.py`:
   - the file loads and validates (all required keys, types, positive dimensions);
   - `capacity_by_n` covers N = 2..6 and equals `{2:120,3:120,4:120,5:100,6:80}`
     (R3.2) — or the signed-off values;
   - `max_chars_per_option` is consistent with `printable_column_width_mm` and the
     font size (recompute in the test, assert within ±1);
   - `template_version == 1`.
2. `python -c "from app... import load_template; load_template()"` succeeds from a
   clean checkout.
3. Loader import does not pull Django (extend `tests/test_purity.py` to cover it if
   it lands under `app/`).

---

## Decisions for sign-off (proposals — Claude will not implement until approved)

### D1 — Custom user model
**Proposal:** `app.core.Professor` as `AUTH_USER_MODEL`, `USERNAME_FIELD = "email"`,
no `username`, fields `email` (unique, cased-lower on save), `password` (Django hash),
`is_active`, `is_staff`, `is_superuser` (for Django admin — the no-password-reset
fallback path, §3.1), `date_joined`. Set before the first migration.
**Alternative:** keep Django's default `User`, match on username=email. Rejected —
Appendix A is email-keyed and a later switch to a custom model is the single most
painful migration in Django.

### D2 — JSON columns
**Proposal:** Postgres `JSONField` for `question.options`, `question.correct_options`,
`version.question_order`, `version.option_order`, `answer.detected_options`,
`audit_event.detail`. `option_order` shape: `{"<canonical_question_id>": [int, …]}`
(string keys — JSON requirement). Matches §3.1 "JSONB for the shuffle maps".

### D3 — Points / score numeric type  *(scoring-adjacent — §2 R7)*
**Proposal:** `FloatField` for `quiz.default_points`, `question.points` (nullable),
`answer.score` (nullable), `submission.total_score` (nullable). R7's
`fraction = (c − w) / k` is real-valued; floats display fine and Σ over ≤120 questions
has no meaningful rounding drift.
**Alternative:** `DecimalField(max_digits=7, decimal_places=3)` for exactness/audit.
Costs: every score computation needs `Decimal` and the R7 division still isn't exact
(e.g. 1/3). **Need your call.**

### D4 — Immutability & append-only enforcement  *(rule 8)*
**Proposal (two layers):**
1. **App layer (always):** `Version.save()` raises `ImmutableFieldError` if
   `question_order`/`option_order`/`qr_id` differ from the DB row (on any update);
   `AuditEvent.save()` raises on update and `AuditEvent` has no delete path; neither is
   registered in Django admin for editing. Covered by `tests/test_immutability.py`.
2. **DB layer (optional — your call):** a Postgres trigger on `versions` that raises on
   `UPDATE` of `question_order`/`option_order`, and on `audit_event` `UPDATE`/`DELETE`,
   shipped as a `RunSQL` migration. Belt-and-braces per rule 8's "enforced
   structurally, not by convention", at the cost of a raw-SQL migration to maintain.
**Options:** (a) app layer only, (b) app + DB trigger. Recommend **(b)** — rule 8 and
§2 R2.7 both stress *structural* enforcement, and the trigger is ~15 lines.

### D5 — `config/` location
Confirming the Phase 0 assumption: `config/sheet_template.json` at the **repo root**
(not `app/config/`). Matches `docs/CLAUDE.md` and §3.2A prose.

### D6 — `sheet_template.json` v1 numbers  *(geometry — §3.2A)*
**Proposal:**
```json
{
  "template_version": 1,
  "page": { "size": "A4", "width_mm": 210.0, "height_mm": 297.0,
            "margin_mm": 12.0 },
  "question_paper": {
    "printable_column_width_mm": 176.0,
    "option_font": "Helvetica",
    "option_font_size_pt": 10.5,
    "max_chars_per_option": 92
  },
  "answer_sheet": {
    "capacity_by_n": { "2": 120, "3": 120, "4": 120, "5": 100, "6": 80 }
  }
}
```
- `printable_column_width_mm = 176`: A4 210mm − 2×12mm margins − ~10mm for the
  `"A) "` option-letter indent = 176mm.
- `max_chars_per_option = 92`: at Helvetica 10.5pt, mean glyph advance ≈ 5.25pt ≈
  1.85mm; 176mm / 1.85 ≈ 95, rounded down to 92 for safety. The loader/test
  recomputes this so it can't silently drift.
- `capacity_by_n`: verbatim from R3.2 (locked); Phase 4 may adjust ≤15% via a
  `template_version` bump, not here.
- US Letter: supported implicitly (wider than A4 → never fewer questions, R3.2); no
  separate table in v1. Add a `letter` block in Phase 4 if proof-printing needs it.
**Need your confirmation or edits**, especially `printable_column_width_mm`,
`option_font_size_pt`, and whether Letter needs its own v1 block.

---

## Phase 1 exit checklist

- [x] D1–D6 signed off by user 2026-09-09 (see PROGRESS.md)
- [x] 1.1 data model — `makemigrations --check` clean, `migrate --check` 0,
      introspection + immutability (app + DB trigger) tests pass  (commit a80c354)
- [x] 1.2 ownership — `owned_by` + `get_owned_or_404` + cross-account test for all 7
      non-Professor models; route-level coverage **closed in Phases 8–9**
      (`test_web_route_isolation.py`, R0.2/R0.3 sweep)  (e286230)
- [x] 1.3 auth — register/login/logout e2e; `password_reset` is `NoReverseMatch` + 404
      (commit 6e68631)
- [x] 1.4 geometry config — `sheet_template.json` v1 loads + validates; capacity table
      == R3.2; pure loader covered by the purity test  (commit bdbe446)
- [x] `scripts/ci.sh` green with the new schema (`65 passed`, core 0001+0002 to fresh DB)

**Phase 1 complete** except the R0.2 route-level verification, which by nature lands
with the data views (Phases 8–9) — noted in PROGRESS 1.2.
