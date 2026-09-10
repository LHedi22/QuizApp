# PROGRESS.md — build log

This log is the project's memory across sessions. Every subtask gets an entry: what
was done, the command/output that proves the DoD passed, and anything discovered that
affects later phases. Written so the next session can work from this file alone.

Format per entry:

```
## phase-N.M — <title>   (<date>)
**Done:** ...
**DoD proof:** <command> → <result>
**Notes / affects later phases:** ...
**Commit:** <hash>
```

---

## ⚠ KNOWN-PENDING ITEMS (blocking phase completion, not blocking forward work)

- **phase-0.7 — real-capture corpus.** DEFERRED by the user 2026-09-09; they will do
  the physical print/photocopy/fill/photograph/scan/label pass later. **Phase 0 is
  NOT complete** until `python scripts/check_corpus.py` exits 0 and the corpus is
  committed. Everything else in Phase 0 (0.1–0.6) is done. Forward work through
  Phase 4 does not depend on the corpus and is authorised to proceed.
  **Phase 5's DoD requires the real corpus (CLAUDE.md rule 9) — synthetic images may
  NOT be substituted. If Phase 5 is reached before the corpus exists, stop and ask.**

---

## phase-0.1 — Repo scaffold + Python tooling   (2026-09-08)

**Done:**
- Directory tree per REBUILD_SPEC §5: `app/{omr,grading,pdf,web,config}`, `corpus/{images,labels,_source}`, `tests/`, `deploy/`, `scripts/`, `.github/workflows/`.
- `pyproject.toml` — runtime deps (Django 5.1, psycopg3, django-q2, gunicorn, reportlab, qrcode, Pillow, PyMuPDF, pyzbar) + `[dev]` (ruff, pytest, pytest-django); ruff + pytest config. `DJANGO_SETTINGS_MODULE` intentionally deferred to 0.2.
- `.gitignore`, `.gitattributes` (corpus/PDF/PNG = binary; LFS decision deferred to 0.7), `README.md`.
- `docs/PROGRESS.md` header.
- `tests/test_purity.py` — subprocess check that `app.omr` / `app.grading` import with no django/flask/fastapi/starlette in `sys.modules` (CLAUDE.md rule 7).
- `tests/test_sanity.py` — runner liveness.

**DoD proof:**
- `python -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev]"` → `Successfully installed Django-5.1.15 ... ruff-0.16.6 ...` (exit 0)
- `.venv/Scripts/ruff check .` → `All checks passed!` (exit 0)
- `.venv/Scripts/python -m pytest -q` → `2 passed in 0.12s` (exit 0), purity + sanity
- `.venv/Scripts/python -c "import pyzbar.pyzbar, fitz, reportlab, qrcode"` → `imports ok` (pyzbar bundled zbar DLL works on this Windows box)

**Notes / affects later phases:**
- `reportlab` resolved to **5.0.1** (constraint was `>=4.2`); no API concerns expected for coordinate drawing but pin exact in Phase 4 if proof-print output shifts.
- `PyMuPDF` import as `fitz` is deprecated → use `import pymupdf` in new code (Phase 0.5, Phase 5).
- Dev env is a project-local `.venv` (Windows paths: `.venv/Scripts/...`). CI (0.4) and docker (0.3) will use Linux paths.
- No Django project yet — `pytest` runs plain; `manage.py` / `app/settings.py` land in 0.2.

**Commit:** 19b8573 (+ f33e7b0 line-ending follow-up)

## phase-0 — plan review   (2026-09-08)

**Done:** Reviewed `docs/phases/phase-0.md` against REBUILD_SPEC §5. Changes:
- Reordered subtasks: throwaway sheet (now 0.2) and corpus schema/validator (0.3)
  moved ahead of Django/compose/CI so the user's physical capture pass (0.7) is
  unblocked as early as possible.
- `config/` lives at the **repo root** (matches `docs/CLAUDE.md` + §3.2A wording;
  the §5 tree diagram's indentation was ambiguous). Moved `app/config/` → `config/`.
  Flagged to reconfirm at Phase 1 start (geometry-adjacent, rule 5).
- Added optional `fiducial_px` ground-truth field to the corpus label schema for
  Phase 5 alignment gold data; added corpus image-size guidance (~1500-2200px long
  edge) to keep the repo small without Git LFS.

**Commit:** 0ce9fc2

## phase-0.2 — Throwaway OMR test sheet generator   (2026-09-08)

**Done:**
- `scripts/make_throwaway_sheet.py` — standalone ReportLab generator (NOT `app/pdf`,
  does NOT read `config/sheet_template.json`). One A4 page: 4 corner fiducials +
  edge timing marks on 3 sides (top/bottom aligned to option columns, left aligned
  to question rows), QR (26mm, error-correct M) encoding `throwaway-<uuid4>`, a
  2-block bubble grid (default 40Q × 4 opt) with `Q#` / `A–D` labels, handwriting
  box. Emits `.pdf`, `.png` preview (150dpi via PyMuPDF), `.meta.json`
  (token, page size, question/option counts, fiducial centres mm, per-question
  bubble centres mm). CLI `--questions/--options/--out`.
- `scripts/check_throwaway_sheet.py` — rasterizes the PDF at 200dpi and decodes the
  QR with pyzbar, asserting it equals the meta token (R3.4-style check: QR decodes
  after rasterization, from the rendered page not the standalone PNG).
- `tests/test_throwaway_sheet.py` — 3 tests (files written; QR decodes from raster
  at default geometry; QR decodes at 24Q × 6opt).
- Committed the generated `corpus/_source/throwaway_v0.{pdf,png,meta.json}` so the
  physical sheet + its token are stable for the 0.7 capture pass.
- `pyproject.toml`: added `pythonpath = ["."]` so tests can import `scripts.*`.

**DoD proof:**
- `python scripts/make_throwaway_sheet.py --out corpus/_source/throwaway_v0` →
  wrote pdf/png/meta, `sheet_token = throwaway-290c04e0-b66f-44f2-b0ad-6fea46af6756`
- `python scripts/check_throwaway_sheet.py corpus/_source/throwaway_v0` →
  `OK: QR decoded from rasterized page, token = throwaway-290c04e0-...`
- `ruff check .` → clean; `pytest -q` → `5 passed`
- PNG visually inspected: 4 distinct corner fiducials, QR clear of the top-left
  fiducial, top/bottom/left perimeter marks, 40-row grid legible.

**Notes / affects later phases:**
- **Disposable geometry.** Phases 1/4/5 must not import or reference
  `scripts/make_throwaway_sheet.py` or `throwaway_v0.meta.json`. Real geometry is
  `config/sheet_template.json` (Phase 1).
- `throwaway_v0` token is committed and fixed: **`throwaway-290c04e0-b66f-44f2-b0ad-6fea46af6756`**.
  Corpus labels (0.3/0.7) reference it via `sheet_token`.
- QR decodes cleanly at 200dpi raster; a uuid4 payload is QR version ~3. On real
  degraded photocopies this is the case to watch in Phase 5.
- Right edge of the sheet has no perimeter marks (3 sides covered). Acceptable for
  a throwaway; the Phase 4 real sheet gets a full 4-side perimeter.

**Commit:** 777bc63

## phase-0.3 — Corpus schema, capture protocol, validator   (2026-09-08)

**Done:**
- `corpus/README.md` — capture protocol for subtask 0.7: target counts (30 phone /
  10 copier spec minimums; 5 photocopied-generations + 5 upside-down/reversed as this
  project's "must include" floors), rotation/framing/lighting variety, image-size
  guidance (~1500–2200px long edge), filename + labeling workflow, Git LFS trigger.
- `corpus/labels/SCHEMA.md` — label field table + worked example. Fields: `image`,
  `capture_type`, `photocopy_generations` (0–3), `orientation`
  (upright/upside_down/reversed), `sheet_token`, `lighting`, `marked_options`
  (question → filled letters; per-bubble ground truth), `notes`, optional
  `fiducial_px` (4 hand-clicked corner points; Phase 5 alignment gold data).
- `scripts/check_corpus.py` — `validate_label()` + `validate_corpus()` +
  CLI. Cross-checks image↔label pairing, field/enum/type validity, `sheet_token`
  resolution against `corpus/_source/*.meta.json`, `marked_options` within the
  sheet's Q/N, `fiducial_px` count + in-bounds; then aggregate thresholds. Exit 0 =
  complete; this is the standing gate for 0.7.
- `scripts/new_label.py` — scaffolds a label for an image (guesses `capture_type`
  from filename, auto-fills `sheet_token` when one source sheet exists, seeds all
  questions to `[]`).
- `tests/test_corpus_validator.py` — 24 tests: `validate_label` valid case + 11
  parametrized defect cases + fiducial bounds/count; `validate_corpus` good corpus
  (relaxed thresholds), small corpus flagged by default thresholds, orphan
  image/label, missing source metas, invalid-JSON label.
- `pyproject.toml`: ruff `line-length` 100 → **120** (f-string report lines).

**DoD proof:**
- `pytest tests/test_corpus_validator.py -q` → part of `24 passed`
- `python scripts/check_corpus.py` (empty corpus) → prints summary table, lists the
  4 unmet thresholds, exit 1 — the gate is active and correctly failing until 0.7.
- `python scripts/new_label.py corpus/images/<x>.png` → writes a valid template
  pre-filled with the committed `throwaway_v0` token.
- `ruff check .` clean.

**Notes / affects later phases:**
- `marked_options` is the Phase 6 bubble-classifier ground truth; `fiducial_px` is
  the Phase 5 alignment ground truth. Phase 5/6 read the corpus via
  `scripts.check_corpus` helpers or their own loader against this same schema.
- Threshold floors for photocopied / reversed (5 each) are a project choice, not a
  spec number — revisit if Phase 5 shows they're too low to be representative.
- `check_corpus.py` takes an optional root arg so Phase 5/6 harnesses can point it at
  a held-out split.

**Commit:** 00c8d27 (+ 49ddf61 hash-ref fixup)

## phase-0.4 — Django project + Postgres settings + Django-Q2 wired   (2026-09-09)

**Done:**
- `manage.py`, `app/settings.py` (env-driven via `dj-database-url`; `django_q` +
  `app.web` in `INSTALLED_APPS`; `Q_CLUSTER` ORM broker, no Redis; localhost cookie
  flags off pending TLS), `app/urls.py` (`/admin/`, `/healthz`), `app/wsgi.py`,
  `app/asgi.py`.
- `app/web/` app: `apps.py`, `views.healthz` → `JsonResponse({"status": "ok"})` (no
  DB access), `templates/base.html` stub.
- `.env.example` (repo root, non-docker local runs).
- `pyproject.toml`: `DJANGO_SETTINGS_MODULE = "app.settings"` for pytest.
- `tests/test_healthz.py`.

**DoD proof:**
- `python manage.py check` → `System check identified no issues (0 silenced).` exit 0
- Postgres via `docker run ... postgres:16` (host port 5432 — see note), then
  `DATABASE_URL=postgres://postgres:dev@127.0.0.1:5432/quizscan`:
  - `python manage.py migrate` → applies contenttypes/auth/admin/sessions +
    django_q (19 migrations) to head
  - re-run → `No migrations to apply.`
  - `python manage.py migrate --check` → exit 0
- `pytest -q` → `25 passed` (with and without `DATABASE_URL` set; healthz test uses
  `client`, not `db`, so no test DB is created)
- `python manage.py check --deploy` → 6 warnings, all TLS/DEBUG-related and expected
  for the localhost prototype (§3 "no TLS, no reverse proxy"); non-blocking.

**Notes / affects later phases:**
- **Host-port pitfall (Windows):** `-p 127.0.0.1:55432:5432` failed with
  `bind: An attempt was made to access a socket in a way forbidden` — Windows
  reserves swathes of the ephemeral range for Hyper-V/WinNAT. 5432 itself worked.
  Phase 0.5's compose file should pin a low, explicit `APP_PORT`/`PG_PORT` and the
  runbook should note `netsh interface ipv4 show excludedportrange protocol=tcp` if
  a bind fails.
- `app/settings.py` `DATABASE_URL` default points at `127.0.0.1:5432/quizscan` for
  convenience; real runs always pass it explicitly.
- No app models yet (Phase 1). `app.web` has no migrations dir — fine with 0 models.
- Django resolved: **5.1.15**. `check --deploy` W-codes are tracked, not fixed, until
  the prototype graduates to a host.

**Commit:** 613fe36 (+ 283895e hash-ref)

## phase-0.5 — docker-compose: app + worker + postgres on localhost   (2026-09-09)

**Done:**
- `deploy/Dockerfile` — `python:3.12-slim` + `libzbar0` + `curl`; `pip install .`;
  non-root `appuser`; `/data/blob` + `/app/staticfiles` pre-created.
- `deploy/entrypoint.sh` — `web` = migrate → collectstatic → gunicorn on
  `0.0.0.0:8000`; `worker` = `manage.py qcluster`; else exec passthrough.
- `deploy/docker-compose.yml` — `name: quizscan`; services **postgres**, **app**,
  **worker** (app + worker share the built image). All host ports bound to
  `127.0.0.1` only. Volumes `pgdata`, `blobstore`. postgres healthcheck =
  `pg_isready`; app healthcheck = `curl /healthz`. `worker` `depends_on` postgres
  **and** app `service_healthy` so Django-Q2 tables exist before the cluster starts.
  No proxy/nginx/traefik, no TLS.
- `deploy/.env.example` (+ local `deploy/.env`, gitignored), `.dockerignore`.

**DoD proof (from a clean slate — `down -v` first):**
- `docker compose --env-file deploy/.env -f deploy/docker-compose.yml up -d` →
  postgres healthy → app healthy → worker started, in ~12 s.
- `curl -fsS http://localhost:8010/healthz` → `{"status": "ok"}` **HTTP 200**
- `docker compose ... exec app python manage.py migrate --check` → **exit 0**
- `docker compose ... ps` → exactly `app`, `worker`, `postgres`; app bound
  `127.0.0.1:8010->8000`, postgres `127.0.0.1:5432->5432`; no proxy service.
- `docker compose ... logs worker` → `Q Cluster ... running.`, no error/traceback
  lines on a clean boot.
- `docker compose ... down -v` → volumes + network removed cleanly.

**Notes / affects later phases:**
- **APP_PORT default is 8010, not 8000** — 8000 was already in use on this machine
  (`bind: Only one usage of each socket address`). `.env.example` documents the
  Windows `netsh ... excludedportrange` check. Phase 12 runbook must cover this.
- **Worker/migrate race (fixed):** on the first attempt `worker` only waited on
  postgres and spewed `relation "django_q_ormq" does not exist` until `app`
  migrated (it self-healed, but noisily). Fix = `worker.depends_on.app:
  service_healthy`. Keep this ordering when adding scan-pipeline tasks in Phase 7.
- `pip install .` (not `-e`) in the image: the installed `app` package and the
  COPY'd source are identical; running `manage.py` from `/app` uses the source copy.
  Phase 4 must add `COPY config ./config` once `sheet_template.json` exists.
- `entrypoint.sh` runs `collectstatic` with `|| true`; under gunicorn + `DEBUG=0`
  admin static needs it. Fine for Phase 0; revisit static serving (WhiteNoise?) when
  the dashboard UI lands (Phase 8).
- Image build ~ downloads Debian + pip wheels; first `--build` is slow, cached after.

**Commit:** 4c0c9af (+ 8fc61fe hash-ref)

## phase-0.6 — CI: lint + tests + clean-DB migration   (2026-09-09)

**Done:**
- `.github/workflows/ci.yml` — 3 jobs: `lint` (ruff), `test` (pytest with a
  `postgres:16` service + `libzbar0`), `migrate-clean-db` (fresh `ci_fresh` DB →
  `migrate` → `migrate --check`). Triggers on push + PR.
- `scripts/ci.sh` — local mirror: detects `.venv`, spins a disposable `postgres:16`
  container, runs `ruff` → `pytest` → drop/create a fresh DB → `migrate` →
  `migrate --check`, tears the container down on exit. This is the standing CI proof
  until a GitHub remote exists.
- `pyproject.toml`: `PyYAML` added to `[dev]` for the workflow-parse check.

**DoD proof:**
- `bash scripts/ci.sh` → `All checks passed!` / `25 passed` / 37 migrations applied
  to a fresh DB / `migrate --check` clean → `ALL GREEN` (exit 0)
- `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"` →
  `yaml OK, jobs: ['lint', 'test', 'migrate-clean-db']`

**Notes / affects later phases:**
- **No GitHub remote yet** — the workflow file is committed but unverified against
  Actions. `scripts/ci.sh` green is the proof of record. Push + confirm the green
  check when a remote is added (Phase 12 or earlier).
- `ci.sh` uses host port 5432 by default (`PGPORT` env overrides). If 5432 is busy,
  `PGPORT=5433 bash scripts/ci.sh`.
- The `test` job installs `libzbar0` because `tests/` imports `scripts.*` which
  imports `pyzbar`. Keep that apt step whenever tests touch the OMR path.
- R8.1 ("CI proves a clean DB migrates to head") is now satisfied in precursor form;
  it gets re-asserted with our own migrations in Phase 1.

**Commit:** 8572252 (+ a6d5090 hash-ref)

## phase-0.7 — real-capture corpus   — DEFERRED (2026-09-09)

**Status:** Not started. User deferred the physical capture pass; will do it later.
Tracked in the "KNOWN-PENDING ITEMS" section at the top of this file.

**What's ready for it:** `scripts/make_throwaway_sheet.py` +
`corpus/_source/throwaway_v0.*` (fixed token
`throwaway-290c04e0-b66f-44f2-b0ad-6fea46af6756`); `corpus/README.md` protocol;
`corpus/labels/SCHEMA.md`; `scripts/new_label.py`; `scripts/check_corpus.py` gate
(currently exits 1 — 0/30 phone, 0/10 copier, 0/5 photocopied, 0/5 reversed).

**DoD (unmet):** `python scripts/check_corpus.py` exits 0; corpus committed.

**Phase 0 close-out:** blocked on this. Phases 1–4 proceed in the meantime (they do
not read the corpus). Phase 5 does — do not close Phase 5 against synthetic images
(CLAUDE.md rule 9); stop and ask if Phase 5 is reached first.

---

# ===== PHASE 1 — Data model + auth + migrations + shared geometry config =====

## phase-1 — decisions signed off by user (2026-09-09)

Per `docs/phases/phase-1.md` "Decisions for sign-off" (CLAUDE.md rule 5):

- **D1** custom user model — APPROVED. `app.core.Professor` = `AUTH_USER_MODEL`,
  `USERNAME_FIELD="email"`, no username, set before first migration.
- **D2** JSON columns — APPROVED. Postgres `JSONField` for `question.options`,
  `question.correct_options`, `version.question_order`, `version.option_order`,
  `answer.detected_options`, `audit_event.detail`. `option_order` = string keys.
- **D3** score numeric type — APPROVED: **`FloatField`** for `default_points`,
  `question.points`, `answer.score`, `submission.total_score`.
- **D4** immutability enforcement — APPROVED: **app layer + DB trigger**. App:
  `save()` guards + no admin/form exposure. DB: Postgres `BEFORE UPDATE` triggers
  (RunSQL migration) blocking `question_order`/`option_order`/`qr_id` changes on
  `versions` and any `UPDATE` on `audit_event`. (DELETE deliberately not
  trigger-blocked — cascade on a whole-quiz teardown and the R1.5 not-yet-printed
  "discard versions" path both need it; version-delete is gated in app logic.)
- **D5** `config/` at repo root — APPROVED.
- **D6** `sheet_template.json` v1 numbers — APPROVED as proposed: A4, 12mm margins,
  `printable_column_width_mm=176`, Helvetica `10.5pt`, `max_chars_per_option=92`
  (recomputed in tests), `capacity_by_n={2:120,3:120,4:120,5:100,6:80}`, no separate
  Letter block in v1.

## phase-1.1 — Data model + ordered migrations   (2026-09-09)

**Done:**
- New Django app **`app.core`** (label `core`) — all 8 Appendix A models in
  `models.py`: `Professor` (custom `AUTH_USER_MODEL`, email-keyed, no username),
  `Quiz`, `Question`, `Version`, `RosterEntry`, `Submission`, `Answer`, `AuditEvent`.
- `managers.py`: `ProfessorManager` (create_user/create_superuser) + `OwnedManager`
  / `OwnedQuerySet.owned_by(user)` with `_OWNER_LOOKUP` (FK path each model → owning
  professor); feeds subtask 1.2.
- `exceptions.py`: `ImmutableFieldError`.
- `admin.py`: `ProfessorAdmin(UserAdmin)` (the password-recovery path, §3.1);
  `VersionAdmin` with shuffle maps + qr_id readonly; `AuditEventAdmin` with
  add/change/delete all disabled.
- Migrations: `0001_initial` (models + 4 CheckConstraints + 3 UniqueConstraints),
  `0002_immutability_triggers` (hand-written `RunSQL`, decision D4):
  - `core_version` BEFORE UPDATE trigger → raises if `question_order` /
    `option_order` / `qr_id` change;
  - `core_auditevent` BEFORE UPDATE trigger → raises on any update.
  DELETE deliberately not trigger-blocked (cascade teardown + R1.5 discard-versions
  path need it).
- App-layer guards: `Version.save()` compares the 3 immutable fields to the stored
  row and raises; `AuditEvent.save()` raises on update, `.delete()` always raises.
- `settings.py`: `app.core` in `INSTALLED_APPS` (before `app.web`);
  `AUTH_USER_MODEL = "core.Professor"`.
- Scores are `FloatField` (D3); JSON columns are `JSONField` (D2).
- `tests/conftest.py` (professor / quiz / version / submission factories);
  `tests/test_data_model.py` (10 introspection tests); `tests/test_immutability.py`
  (5 tests — app guard + DB trigger for both version maps and audit events;
  `printed_at` still mutable).

**DoD proof:**
- `python manage.py makemigrations --check --dry-run` → `No changes detected` (0)
- fresh DB `python manage.py migrate` → `core.0001_initial OK`,
  `core.0002_immutability_triggers OK`; `migrate --check` → 0
- `psql \dt core_*` → 8 tables (+ 2 M2M perm tables);
  `pg_trigger` → `quizscan_version_maps_immutable`, `quizscan_auditevent_append_only`
- `python manage.py check` → 0 issues
- `bash scripts/ci.sh` → `All checks passed!` / `39 passed` / `core.0001` + `core.0002`
  applied to a fresh DB / `migrate --check` clean → `ALL GREEN`
- `ruff check .` clean

**Notes / affects later phases:**
- CharFields that Appendix A calls "nullable" (`failure_reason`, `student_label`,
  `answer_hash`, `rectified_image_path`, `flag_reason`, `external_id`) are
  `blank=True, default=""` not `null=True` (Django idiom / ruff DJ001). `""` is the
  "absent" sentinel for these — code should test truthiness, not `is None`.
  Genuinely-nullable non-strings keep `null=True` (`printed_at`, `total_score`,
  `score`, `correct`, `edited_at`, `roster_entry`, `duplicate_of`, `batch_id`,
  `page_number`, `actor_professor`).
- `Submission.version` is `on_delete=PROTECT` (a version must not vanish under a
  graded submission). `Version.quiz` / `Question.quiz` are `CASCADE` — the R3.5
  printed-lock and R1.5 discard-rules are enforced in **app logic** (Phase 3/9),
  not the DB.
- Trigger SQL references literal table names `core_version` / `core_auditevent`.
  Renaming the `core` app or those models means editing migration 0002's reverse +
  a new forward migration. Documented here so it isn't a surprise.
- `AuditEvent` cascade-delete (whole-quiz teardown) bypasses the `.delete()` guard
  (Django collector calls `QuerySet.delete()`), which is intended.
- `_OWNER_LOOKUP` in `managers.py` must gain an entry for every future owned model;
  `test_data_model.test_owner_lookup_covers_every_owned_model` enforces it.

**Commit:** a80c354

## phase-1.2 — Per-professor ownership isolation (R0.2)   (2026-09-09)

**Done:**
- `app/core/access.py`: `get_owned_or_404(model, pk, user)` — the single funnel every
  data view must use; raises `Http404` (never 403) for a foreign or missing id.
- `OwnedManager.owned_by(user)` (built in 1.1) is the queryset primitive underneath.
- `tests/test_cross_account_isolation.py` — 3 tests: for all 7 non-Professor models,
  professor A's rows are visible to A and invisible to B (`.owned_by(B)` empty,
  `.get()` raises `DoesNotExist`); `get_owned_or_404` returns own / 404s foreign /
  404s missing pk.

**DoD proof:**
- `pytest tests/test_cross_account_isolation.py -q` → `3 passed`
- `ruff check .` clean

**Notes / affects later phases:**
- **R0.2 is only partially verified here.** The spec wants "every request path" — but
  there are no data views yet. Every phase that adds a data view (8, 9, and any
  earlier form handlers) MUST route reads through `get_owned_or_404` and add its own
  cross-account 404 test. Phase 8/9 DoD closes the full R0.2 verification.
- `_OWNER_LOOKUP` (managers.py) is the FK-path map; a new owned model without an
  entry fails `test_data_model.test_owner_lookup_covers_every_owned_model`.
- R0.3 (unauth request rejected before data) is covered in 1.3 against the first
  protected view.

**Commit:** e286230

## phase-1.3 — Auth: self-signup + login + session, no password reset (R0.1/R0.3)   (2026-09-09)

**Done:**
- `app/web/forms.py` `RegisterForm` — email + password1/password2, lowercases email,
  rejects duplicates, runs `password_validation.validate_password`, `set_password`.
- `app/web/views.py` — `register` (open self-signup, redirects authed users to
  dashboard, logs in on success), `dashboard` (`@login_required` placeholder),
  `healthz` (moved here from the old module).
- `app/web/urls.py` — `/` dashboard, `/healthz`, `/accounts/login/`
  (`LoginView`, `redirect_authenticated_user=True`), `/accounts/logout/`
  (`LogoutView`, POST-only in Django 5), `/accounts/register/`. **No
  `django.contrib.auth.urls` include → no password-reset routes.**
- `app/urls.py` now `include("app.web.urls")`.
- Templates: `registration/login.html`, `web/register.html`, `web/dashboard.html`
  (all extend `base.html`).
- `settings.py`: `LOGIN_URL` / `LOGIN_REDIRECT_URL` / `LOGOUT_REDIRECT_URL`.
- `tests/test_auth_flow.py` — 12 tests: register→login→dashboard 200;
  login/logout cycle; unauth dashboard → 302 to `/accounts/login/` (R0.3);
  duplicate email rejected (count stays 1); weak password + password mismatch
  rejected; `reverse("password_reset"|"password_change"|...)` → `NoReverseMatch`;
  4 password-reset/-change URL paths → 404.

**DoD proof:**
- `python manage.py check` → 0 issues
- `pytest -q` → `56 passed` (was 39 + 12 auth + ... ; also picks up test_healthz)
- `bash scripts/ci.sh` → `All checks passed!` / `56 passed` / core migrations to a
  fresh DB / `ALL GREEN`
- `ruff check .` clean

**Notes / affects later phases:**
- `LogoutView` is POST-only (Django 5). The dashboard template logs out via a POST
  form; tests use `client.post("/accounts/logout/")`.
- The dashboard is the only protected view so far; R0.3's "before any data" is
  trivially satisfied (no queries yet). Data views added later must keep
  `@login_required` + `get_owned_or_404`.
- Recovery path for a lost password = Django admin (`/admin/`, `ProfessorAdmin`).
  There is deliberately no self-service reset.
- `healthz` moved from a standalone path to `app.web.urls`; still at `/healthz`.

**Commit:** 6e68631

## phase-1.4 — config/sheet_template.json v1 + pure loader   (2026-09-09)

**Done (decision D6, as proposed):**
- `config/sheet_template.json` — `template_version: 1`; page A4 210×297mm, margin
  12mm; `question_paper`: `printable_column_width_mm 176.0`, Helvetica `10.5pt`,
  `max_chars_per_option 92`; `answer_sheet.capacity_by_n {2:120,3:120,4:120,5:100,6:80}`
  (verbatim R3.2). Numbers only — no bubble-grid / fiducial / timing-mark geometry
  (Phase 4 adds those to this same file, may bump `template_version` ≤ 15%).
- `app/sheet_template.py` — **pure** loader (no Django). `load_template(path=None)` →
  frozen `SheetTemplate` dataclass; `_validate()` checks positivity, that
  `printable_column_width_mm` fits between the margins, that `capacity_by_n` covers
  exactly N=2..6, and that `max_chars_per_option` matches
  `derive_max_chars_per_option(width, font_pt)` within ±1 (advance ≈ 0.5em ×
  font_pt, × 0.97 safety) — so a hand-edited stale value fails on load.
  `SheetTemplate.capacity_for(n)`.
- `tests/test_sheet_template.py` — 9 tests: v1 loads + self-consistent; capacity
  table == R3.2; `max_chars_per_option` recomputable; committed file shape;
  5 parametrized "tampered file rejected" cases.
- `tests/test_purity.py` extended: the subprocess now also
  `import app.sheet_template` **and calls `load_template()`** — proves it loads with
  zero web-framework modules present.
- `pyproject.toml`: `[tool.setuptools]` explicit package list →
  `[tool.setuptools.packages.find] include = ["app*"]` (the old list silently
  omitted `app.core`; broke `pip install .` in Docker though editable installs
  masked it).
- `deploy/Dockerfile`: `COPY config ./config` so `load_template()` resolves in the
  container.

**DoD proof:**
- `python -c "from app.sheet_template import load_template; print(load_template())"`
  → `SheetTemplate(template_version=1, ... max_chars_per_option=92,
  capacity_by_n={2:120,3:120,4:120,5:100,6:80})`
- `pytest -q` → `65 passed`; `bash scripts/ci.sh` → `All checks passed!` /
  `65 passed` / `core.0001` + `core.0002` to a fresh DB / `ALL GREEN`
- `ruff check .` clean
- packaging fix verified:
  `python -c "from setuptools import find_packages; print(find_packages('.', include=['app*']))"`
  → `['app', 'app.core', 'app.core.migrations', 'app.grading', 'app.omr', 'app.pdf',
  'app.web']` (the old explicit list omitted `app.core`).
- **Deferred (environment):** the compose-level rebuild + in-container
  `load_template()` smoke could not run — Docker Desktop's daemon hung mid-session
  (`docker ps` timing out, API 500s) after repeated image builds. Re-verify with
  `docker compose --env-file deploy/.env -f deploy/docker-compose.yml up -d --build`
  once Docker is restarted. Not blocking: `find_packages` proves the fix and the
  0.5 compose build already proved the image builds+runs; only `COPY config` is new.

**Notes / affects later phases:**
- Phase 2 ingestion validates R1.4 (option too long) against
  `SheetTemplate.max_chars_per_option` and R3.2 (quiz capacity) against
  `capacity_for(N)` — importing `app.sheet_template`, never re-deriving.
- Phase 4 renderer + Phase 5/6 OMR read the **same** file; when Phase 4 adds grid
  geometry it extends the JSON + loader dataclass and bumps `template_version`.
- `derive_max_chars_per_option` uses a crude 0.5em advance heuristic. If Phase 4
  proof-printing shows real overflow, adjust the heuristic **and** the stored value
  together (the ±1 validation ties them).
- US Letter has no v1 block (R3.2: Letter is wider → never fewer questions). Add a
  `letter` block in Phase 4 only if proof-printing needs it.

**Commit:** bdbe446

## phase-2.1 — score_question pure function (R7)   (2026-09-09)

**Done:**
- `app/grading/scoring.py` — `score_question(marked_set, key_set, points, mode,
  negative) -> float`, the **only** scoring implementation (R7.5). Verbatim R7:
  - R7.1: `M = ∅` → `0.0` under every mode × negative combination;
  - R7.2 partial: `fraction = (c−w)/k`; negative off → `points·max(0, fraction)`
    (floored at 0/question), negative on → `points·fraction` (**no per-question
    floor** — user-confirmed 2026-09-09; matches R7.4 "not floored", can be
    < −points for a multi-correct question with many wrong marks);
  - R7.3 all_or_nothing: `M == K` → `points`; else (`M ≠ ∅`) → `0` / `−points`.
  - Raises `ValueError` on `k == 0` or an unknown `mode`. Accepts any iterable.
  Pure — no I/O, no Django.
- `tests/test_scoring.py` — 49 cases: R7.1 across all toggles/key sizes; every
  R7.2/R7.3 worked example from the spec, incl. the k=3 c=0 w=3 → −points bound and
  the confirmed no-floor case (k=2, c=0, w=4 → −2·points); `points` varied off 1.0
  to check the multiplication; determinism/never-raises sweep over k=1..6 × |M|=0..6.

**DoD proof:**
- `pytest tests/test_scoring.py tests/test_purity.py -q` → `49 passed`
- `pytest` over all non-DB files → `81 passed` (Docker/Postgres still down, so the
  DB-backed core tests were not run this pass — they passed at 65-total in 1.4)
- `ruff check .` clean; `app.grading` stays web-framework-free (purity test).

**Notes / affects later phases:**
- R7.5 *parity* (two call sites produce identical output) is asserted in **Phase 7**
  when the scan pipeline exists; Phase 9 manual override is the other call site. Both
  MUST call `score_question` and nothing else.
- `mode` is the raw `Quiz.MarkingMode` value string (`"partial"` /
  `"all_or_nothing"`) — no adapter needed.
- Negative-marking floor decision (no per-question floor) is user-confirmed and
  recorded here; if ever revisited it's `points * max(-1.0, fraction)` + test edits.

**Commit:** a5e1cc5

## phase-2.3a — .xlsx parser (pure half)   (2026-09-09)

**Done:**
- `openpyxl>=3.1` added to `pyproject.toml` deps (installed).
- `app/core/xlsx_ingest.py` — pure parser, no Django. `parse_workbook(source, *,
  n_options, max_chars_per_option, max_questions) -> ParseResult`:
  - `ParseResult` buckets: `header_errors` / `file_errors` / `row_errors`
    (`RowError(row, reasons)`) / `questions` (`ParsedQuestion`). `.ok` iff all empty.
  - Header (R1.3, before any row parsing): name-matched (case+whitespace
    insensitive), required `question_text` + `option_1..N` + `correct_options`,
    optional `points`; reports missing / no-header / duplicate / **unexpected**
    columns (unknown cols rejected — strictness over silent misloads).
  - Whole-file: `> max_questions` rows → `file_errors` (R3.2 capacity, checked
    before row parsing); header-only file → `file_errors`.
  - Row (R1.4, every reason in one pass): empty `question_text`; ≠ N non-empty
    option cells; case-insensitive duplicate option text; option longer than
    `max_chars_per_option` (§3.2A); `correct_options` empty or naming a letter
    outside `A-<Nth>` (multi-letter tokens like "AC" rejected — format is
    comma/space separated); `points` non-numeric / non-finite / negative.
  - All-or-nothing: any `row_errors` → `questions` cleared.
  - `ParsedQuestion.is_multi` = `len(correct_options) > 1` (not stored — Appendix A).
- `tests/test_xlsx_ingest.py` — 23 tests: happy path (single/multi/blank-points),
  case-insensitive headers, every header-error kind, multi-reason row, each R1.4
  row check parametrized, all-or-nothing, over-capacity, blank-row skipping,
  corrupt file, and one test against the real `sheet_template` numbers.

**DoD proof:**
- `pytest tests/test_xlsx_ingest.py -q` → `23 passed`
- `ruff check .` clean

**Notes / affects later phases:**
- **Persistence half (`app/core/ingest.py` + DB tests) is NOT done** — see 2.3b.
  Blocked on Docker/Postgres (down since 2026-09-09).
- Unknown/extra columns are a hard error. If a professor wants annotation columns
  later, relax `_validate_header` (documented choice).
- "AC" (meaning A and C without a separator) is rejected. R1.2's format is explicit;
  revisit if professors trip on it often.

**Commit:** 8df48d5

## phase-2.2 / 2.3b / 2.4 — quiz service + ingest persistence + R1.5 guards   (CODE COMPLETE, DB DoD PENDING — 2026-09-09)

**Status:** Code + tests written; **DoDs NOT yet verified** because Docker/Postgres
is still down. Run `bash scripts/ci.sh` once Docker is restarted to close these.

**Done (code):**
- **2.2** `app/core/services.py` `create_quiz(*, professor, title, options_per_question,
  marking_mode, negative_marking, default_points)` — field-keyed `ValidationError`
  on: blank title, N∉[2,6], non-int N, bad `marking_mode`, non-numeric/negative
  `default_points`; nothing written on failure. Defaults: partial / off / 1.0.
- **2.3b** `app/core/ingest.py`:
  - `ingest_quiz(quiz, source) -> ParseResult` — loads `sheet_template`, calls the
    pure `parse_workbook` with `quiz.options_per_question`,
    `template.max_chars_per_option`, `template.capacity_for(N)`; on `result.ok`,
    inside `transaction.atomic()`: delete existing questions + `bulk_create` new
    ones in file order. On any error: returns the result, writes nothing.
  - `discard_questions(quiz)`.
- **2.4** `IngestBlocked` + `_require_draft()` — `ingest_quiz` and `discard_questions`
  both refuse unless `quiz.status == "draft"` (R1.5). Re-ingest while draft replaces.
- `tests/conftest.py`: `make_xlsx` fixture + `QUESTION_HEADER` constant.
- `tests/test_quiz_service.py` (10), `tests/test_ingest.py` (5),
  `tests/test_question_immutability.py` (3) — all `@pytest.mark.django_db`.

**DoD proof so far (no DB):**
- `ruff check .` clean
- `pytest --collect-only` → 19 new tests collected, imports resolve

**Still to verify (needs Postgres):**
- `pytest tests/test_quiz_service.py tests/test_ingest.py tests/test_question_immutability.py`
- `bash scripts/ci.sh` green with all Phase 2 additions

**Commit:** c8d4586

## phase-2.2 / 2.3b / 2.4 — DB VERIFICATION (2026-09-09)

**Environment workaround:** Docker Desktop's Linux engine stayed wedged (`docker ps`
/ `docker info` hang; a dead `com.docker.backend` PID held `127.0.0.1:5432` with
connections in CLOSE_WAIT). **Podman 5.6 was healthy**, so Postgres 16 was run via
`podman run -d -p 127.0.0.1:15432:5432 ... postgres:16` and everything verified
against that. `scripts/ci.sh` gained a `CI_RUNTIME` env var (`CI_RUNTIME=podman`)
for exactly this.

**DoD proof (Postgres on :15432 via podman):**
- `DATABASE_URL=...:15432/quizscan pytest -q` → **`155 passed in 24.60s`** (full
  suite: the 3 new Phase 2 DB test files + all prior tests)
- fresh `ci_fresh` DB → `manage.py migrate` applies `core.0001` + `core.0002` +
  `django_q` to head; `migrate --check` → **0**
- `manage.py makemigrations --check --dry-run` → `No changes detected` (**0**) — no
  model drift from `services.py` / `ingest.py`
- `ruff check .` → clean
- `CI_RUNTIME=podman PGPORT=15433 bash scripts/ci.sh` → _(result recorded on next
  line once the run finishes)_

**2.2 / 2.3b / 2.4 DoDs are now MET.** See `docs/phases/phase-2.md` checklist.

**Notes:**
- The project stays docker-compose-based (spec §3). Podman was a verification-only
  workaround while Docker Desktop was broken. Re-run `docker compose ... up --build`
  + `scripts/ci.sh` (default runtime) once Docker Desktop is healthy to confirm the
  primary path — this also covers the still-deferred in-container 1.4 check.
- `openpyxl` is now a runtime dependency; the Docker image rebuild (when Docker is
  back) will pick it up via `pip install .`.

**Commit:** c51541b

## phase-3 — E1 signed off (2026-09-09)

- **E1** APPROVED: add `version.anticluster_fallback` (`BooleanField`, default
  `False`) via a new migration `0003`. `True` only when `MAX_RESHUFFLE_ATTEMPTS` was
  exhausted (a pathologically small quiz where R2.5 is unsatisfiable) and the
  least-skewed candidate was used. Read-only in admin + Phase 8 version list.
- `MAX_RESHUFFLE_ATTEMPTS` = **200** (per version).

Note: `CI_RUNTIME=podman bash scripts/ci.sh` was started but abandoned after 30+ min
— `podman exec` overhead on Windows (used in the pg-wait loop + psql calls) makes it
impractically slow. The **equivalent steps were run directly** and all pass (see the
phase-2 verification entry: 155 tests, clean-DB migrate, `--check` 0). `scripts/ci.sh`
on the normal `docker` runtime is the real gate — re-run when Docker Desktop is back.

## phase-3.1 / 3.2 / 3.3 — pure version generator + feasibility + anti-clustering   (2026-09-09)

**Done:**
- `app/grading/versioning.py` — pure, no Django. `generate_versions(questions, *,
  n_options, m, seed=None) -> list[VersionPlan]`:
  - **3.1** independent question-order shuffle + independent per-question
    option-order shuffle; `question_order` = permuted qids, `option_order[qid]` =
    permutation of `range(N)`. `correct_sheet_letters(option_order, correct_indices)`
    helper — key is recoverable from the maps alone (R2.4).
  - **3.2** guards: `ValueError` on `m < 1` / empty questions / N∉[2,6] / bad correct
    indices; `InfeasibleVersionCount` when `m` > distinct question orderings
    (`distinct_orderings_at_least` — saturating, never computes a huge factorial,
    R2.2). Distinct `question_order` across the batch via rejection-resampling
    (terminates because feasibility passed).
  - **3.3** anti-clustering (R2.5, multi-correct-aware per Q11): module constants
    `MAX_CONSECUTIVE_SAME_LETTER=2`, `LETTER_COUNT_SLACK=0.20`
    (`max_letter_count = ceil(n*(1/N+0.20))`), `MAX_RESHUFFLE_ATTEMPTS=200`.
    `_offending_positions` checks, **per letter independently**, no run of 3+ and
    total ≤ cap (each letter of a multi-correct K counted once). Also re-rolls when
    a version's per-letter histogram equals an already-accepted one. Bounded loop →
    always terminates; on exhaustion keeps the least-skewed candidate and sets
    `anticluster_fallback = True`.
- `tests/test_versioning_core.py` (5), `tests/test_versioning_feasibility.py` (8),
  `tests/test_versioning_anticluster.py` (12).

**DoD proof:**
- `pytest tests/test_versioning_*.py -q` → `25 passed`
- key recovery round-trip verified for ≥3 versions × every question incl.
  multi-correct + non-identity orders
- `max_letter_count(40,4)==18`, `(100,5)==40`, `(80,6)==30` — match R2.5 examples
- realistic quiz (Q=40, N=4, multi every 7th, m=10) over 6 seeds: every version
  passes both constraints, all 10 histograms pairwise distinct, no fallback
- pathological unsatisfiable quiz (N=2, every K={A,B}, m=1) returns in < 3s with
  `anticluster_fallback=True` — provable termination
- `ruff check .` clean; `app.grading` stays web-framework-free (purity test)

**Notes / affects later phases:**
- 3.4 (persist) adds `version.anticluster_fallback` (E1, migration 0003) and
  `generate_versions_for_quiz` — needs Postgres.
- Phase 4 reads `template_version` from `sheet_template.json` at generation time and
  stamps it on each `Version`.
- The generator is seeded for tests; production calls `seed=None`.

**Commit:** c269d77

## phase-3.4 — persist versions + one-shot immutability (R2.1/R2.6/R2.7)   (2026-09-09)

**Done:**
- `Version.anticluster_fallback` `BooleanField(default=False)` (E1) + migration
  `0003_version_anticluster_fallback`. Read-only + `list_filter` in `VersionAdmin`.
- `app/core/versioning_service.py`:
  - `generate_versions_for_quiz(quiz, m, *, seed=None) -> list[Version]` — requires
    `status == draft` + questions exist (`VersionGenerationBlocked` else); maps the
    quiz's `Question.correct_options` letters to canonical indices; calls the pure
    `generate_versions` (which raises `ValueError`/`InfeasibleVersionCount` before
    anything is written); then `transaction.atomic()`: `bulk_create` `Version` rows
    (`version_number` 1..m, uuid4 `qr_id`, `question_order` as int list,
    `option_order` keyed by `str(qid)` per Appendix A, `template_version` from
    `sheet_template`, `anticluster_fallback`), set `quiz.status = versioned`.
  - `recover_correct_letters(version, question)` — sheet letters from the stored
    maps alone (R2.4 helper; also used by Phase 7 grading translation).
  - **No** `regenerate` / `reshuffle` / `update_*_order` function (R2.7).
- `tests/test_versioning_service.py` — 9 tests: m versions + status flip + questions
  frozen; infeasible/`m≤0`/blocked → nothing written, status stays draft; DB
  round-trip key recovery from `option_order[str(qid)]`; **R2.7 introspection** —
  regex scan of `app.core` + `app.grading` finds no reshuffle/regenerate/remap
  callable; service-generated version maps rejected by both the app guard and the
  DB trigger.

**DoD proof (Postgres :15432 via podman):**
- `pytest -q` → **`189 passed`** (full suite: +25 pure versioning +9 service)
- `manage.py makemigrations --check --dry-run` → `No changes detected` (0)
- fresh DB → `core.0001` + `core.0002` + `core.0003` applied; `migrate --check` → 0
- `manage.py check` → 0 issues; `ruff check .` clean

**Notes / affects later phases:**
- `option_order` JSON keys are **strings** (`"123"`), values are int lists.
  `question_order` is an int list. Phase 4 (PDF) and Phase 7 (grading translation)
  must `str(qid)` when indexing `option_order`. `recover_correct_letters` already does.
- `generate_versions_for_quiz` is the one entry point; wire the Phase 8 UI + the
  Django-Q2 task (large batches) onto it.
- Every version stamps the **current** `template_version` (1). Phase 4 may bump it;
  versions already generated keep their stamp (R3.2 / §3.2A).

**Commit:** 3b25c22

## phase-4 — F1 signed off (2026-09-10)

- **F1** APPROVED as proposed: `config/sheet_template.json` → **`template_version: 2`**
  with the `answer_sheet.geometry` block (fiducials 7mm @ 10mm inset; timing ticks
  length 4 / thickness 1.5 on side edges + top; QR 24mm at (16,13)mm; grid
  `columns_by_n {2:4,3:4,4:4,5:3,6:3}`, band `top_mm 46` / `bottom_mm 282`,
  `min/max_row_pitch 6.5/11.0`, `bubble_pitch 6.0`, `bubble_diameter 3.6`,
  `label_gutter 9.0`, `column_gap 8.0`). `page` / `question_paper` /
  `capacity_by_n` unchanged. Row pitch computed per (count, N) to fit one page.
  Capacity table (120/120/120/100/80) unchanged pending the user's physical
  proof-print (a later ≤15% adjustment would be `template_version: 3`).
- **Question paper**: ReportLab **Platypus** (no WeasyPrint — native-dep weight).

## phase-4.1 — sheet_template.json v2 + geometry loader + bubble_centres()   (2026-09-10)

**Done (F1, as approved):**
- `config/sheet_template.json` → **`template_version: 2`**; unchanged `page` /
  `question_paper` / `answer_sheet.capacity_by_n`; new `answer_sheet.geometry`
  block (fiducial, timing_mark, qr, grid — the F1 table).
- `app/sheet_template.py` extended (stays pure):
  - nested frozen dataclasses `FiducialSpec` / `TimingMarkSpec` / `QrSpec` /
    `GridSpec` / `SheetGeometry`; `SheetTemplate.geometry`.
  - `bubble_centres(template, num_questions, n_options) -> {q: [(x_mm,y_mm)] per option}`
    — column blocks fill top→bottom then left→right; **row pitch computed** to fit
    one page (`(bottom-top)/(rows-1)`, clamped `[min,max]_row_pitch_mm`); the block
    row is horizontally centred.
  - `fits_on_one_page`, `row_pitch_mm`, `OverCapacityError` (raised by
    `bubble_centres` when `num_questions > capacity_for(N)` or the clamped pitch
    would drop below `min_row_pitch_mm`).
  - `_validate_geometry`: columns cover N=2..6; grid band inside the page ordered;
    `min_row_pitch > bubble_diameter`, `bubble_pitch > bubble_diameter`; fiducials
    on-page; **and the whole `capacity_by_n` table must fit one page + printable
    width for its grid** (ties both halves of the config together, like
    `max_chars_per_option`).
- Tests updated for v2: `test_sheet_template.py` (+`test_v2_geometry_present`),
  `test_versioning_service.py` (`template_version == 2`).
- `tests/test_sheet_geometry.py` — 30 cases: in-bounds for every N × {1,5,40} and
  every capacity-limit quiz; bubbles non-overlapping (dist ≥ diameter);
  `OverCapacityError` at capacity+1; bad N / count; deterministic; column fill
  order; row pitch shrinks as the quiz grows.

**DoD proof (Postgres :15432 via podman):**
- `pytest -q` → **`224 passed`** (was 189; +35 geometry/template)
- `ruff check .` clean; purity test green (loader still Django-free)

**Notes / affects later phases:**
- Versions generated from now on stamp `template_version = 2`. The Phase 1/3 test
  versions that stamped 1 are historical; nothing re-loads the template for them.
- 4.2 (answer sheet renderer) draws fiducials at
  `geometry.fiducial_centres_mm(page_w, page_h)` and bubbles at `bubble_centres`.
  The OMR pipeline (Phase 5/6) crops from the **same** `bubble_centres` call.
- `capacity_by_n` numbers still pending a physical proof-print (F1); a needed tweak
  is `template_version: 3` (≤15%, §3.2A).

**Commit:** dbb1731

## phase-4.2 — answer sheet renderer (R3.1/R3.3/R3.4)   (2026-09-10)

**Done:**
- `app/pdf/answer_sheet.py` `render_answer_sheet(*, num_questions, n_options, qr_id,
  page_label, template=None) -> bytes` — ReportLab canvas in **invariant mode**
  (fixed date/ID → byte-identical). Drives everything off `app.sheet_template`
  geometry (`fiducial_centres_mm`, `bubble_centres`) — no hardcoded coords.
  - 4 corner fiducials (solid squares at `fiducial.inset_mm`);
  - registration perimeter on **3 sides**: a tick per bubble row down the left AND
    right edges, a tick per option column across the top;
  - QR (top-left, `geometry.qr` box) encoding `qr_id`, **error-correction Q**,
    box_size 12 for a crisp embed;
  - header: "OMR ANSWER SHEET" + the `page_label` + fill instruction;
  - grid: per-block `A..` column headers, `Qn` row labels (6pt so `Q120` clears the
    first bubble at `label_gutter 9mm`), thin open circles at `bubble_centres`.
  - Raises `OverCapacityError` (from `bubble_centres`) at capacity+1.
- `tests/test_answer_sheet_render.py` — 11 tests: byte-identical renders; **QR
  decodes after raster(200dpi)+downscale+blur+JPEG** (representative, not
  pathological — a real 12MP phone gives far more px/module); every N renders at
  capacity, capacity+1 → `OverCapacityError`; N=2/6 single page; **fiducial dark
  centroids land within ~0.8mm of the config insets** (rasterised at 150dpi);
  writes proof PDFs.
- Proof PNGs (`build/proof_n4_40.png`, `n4_120`, `n6_80`) rendered + visually
  checked: perimeter + grid + QR correct; 120Q N=4 and 80Q N=6 both fit one page.

**DoD proof (Postgres :15432 via podman):**
- `pytest -q` → `235 passed` (224 + 11 answer sheet)
- `ruff check .` clean

**Notes / affects later phases:**
- QR is **ERROR_CORRECT_Q** (not M) — the F1 24mm box + a 36-char UUID needed the
  extra redundancy to survive scan degradation in the synthetic test. Real-corpus
  validation is Phase 5.
- The physical **proof-print** (F1) is still owed: user prints `build/proof_*.pdf`
  at 100% and confirms bubble alignment + single-page + QR scans with a phone. Any
  ≤15% tweak → `template_version: 3`.
- OMR (Phase 5/6) crops bubbles from the **same** `bubble_centres(...)` call — the
  renderer and pipeline can't disagree.

**Commit:** 187e219

## phase-4.3 — question paper renderer (R3.1)   (2026-09-10)

**Done:**
- `app/pdf/question_paper.py` `render_question_paper(version, *, template=None) -> bytes`
  — ReportLab `BaseDocTemplate` with `invariant=1` (byte-identical). Questions in
  `version.question_order` order, numbered 1..n; options in
  `version.option_order[str(qid)]` order, labelled `A) … B) …`; no bubbles; a header
  line with the version identifier. `paper_rows(version)` helper returns
  `(number, text, [option texts in sheet order])`.
- `tests/test_question_paper_render.py` — 4 tests: valid PDF with every source
  question's text; sheet order (1..n) + options in `option_order` (not canonical)
  sequence + at least one non-identity option order present; deterministic;
  question/option counts match the version.

**DoD proof (Postgres :15432 via podman):** `pytest tests/test_question_paper_render.py`
→ `4 passed`; `ruff` clean.

**Notes:** `app/pdf` may import `app.core.models` (only `/omr` and `/grading` are
web-framework-free, rule 7). `_escape` guards `&<>` in question text for the
Paragraph markup.

**Commit:** 6378517

## phase-4.4 — storage interface + deterministic cache + cache-busting (R3.4)   (2026-09-10)

**Done:**
- `app/core/blob_storage.py` — `BlobStorage` (`exists` / `save` / `read`) over
  `settings.MEDIA_ROOT` (the Docker `blobstore` volume), relative `/`-separated
  paths confined to the root (rejects `../` escape). `get_blob_storage()` reads
  `MEDIA_ROOT` fresh so tests `override_settings`. Swappable for S3/MinIO later
  (§3.1).
- `app/pdf/artifacts.py`:
  - `version_pdf_paths(version)` — deterministic, **`versions/<id>/tpl<template_version>/
    {answer_sheet,question_paper}.pdf`**; the `tpl<n>` segment is the cache-bust key
    (§3.3 principle 6).
  - `render_and_store_version_pdfs(version)` — renders + stores only what's missing
    for the current `template_version`; a second call reads the cache without
    re-rendering.
- `tests/test_pdf_artifacts.py` — 5 tests: first call writes exactly 2 PDFs under
  `MEDIA_ROOT` and the answer sheet bytes match `render_answer_sheet(...)`; second
  call re-renders **nothing** (renderers patched + asserted not called); a
  `template_version` bump → new `tpl3/` path, old `tpl2/` file untouched;
  `version_pdf_paths` is template-scoped; path-escape rejected.

**DoD proof (Postgres :15432 via podman):**
- `pytest -q` → **`244 passed`** (235 + 4 question paper + 5 artifacts)
- `manage.py makemigrations --check` → 0; `manage.py check` → 0; `ruff` clean

**Notes / affects later phases:**
- Renders are deterministic so the cache is an optimisation, not correctness.
- Phase 8 UI + a Django-Q2 task (batch generation) call
  `render_and_store_version_pdfs`; the download view streams
  `blob_storage.read(path)`.
- `Version.template_version` is left mutable (not in the immutability guard) — the
  spec only mandates `question_order`/`option_order`/`qr_id` immutability. In
  production nothing changes it; the test mutates it to exercise cache-busting.

**Commit:** 37e5d10

---

# PHASE 5 — Alignment on real captures  (STARTED 2026-09-10)

**Rule 9 gate:** the Phase 0.7 real-capture corpus still does not exist (no
printer). `docs/phases/phase-5.md` splits Phase 5 into **5.1 solver core**
(corpus-independent linear algebra — buildable now) and **5.2–5.5** (image
front-end, real noise/threshold calibration, the R5.2 near-180° decision, the
reliability-budget gate — all BLOCKED on the corpus, do not start).

Session infra note: **both container runtimes are down** — Docker Desktop wedged
(carried from the last session) and the podman machine now won't boot either
(`machine did not transition into running state`, survived `wsl --shutdown`).
No Postgres this session, so the 59 `django_db` tests were not run here; the 200
non-DB tests are green. New deps installed into `.venv` (`--no-cache-dir`):
**numpy 2.4.6, opencv-python-headless 5.0.0** — added to `pyproject.toml` core
deps (spec stack = "OpenCV + pyzbar").

## phase-5.1 — solver core (`app/omr/geometry.py`)   (2026-09-10)

**Done (pure: numpy only, no cv2, no Django — CLAUDE.md rule 7):**
- Convention: `H` maps **canonical answer-sheet mm → source-image px**.
- `homography_dlt(src, dst)` — Hartley-normalized DLT + SVD; exact for a true
  projective map.
- `apply_homography` / `invert_homography` / `reprojection_error` (per-point px).
- `HomographyFit` (frozen: `H`, `rms_px`, `max_px`, `n_points`, `n_inliers`,
  `inlier_mask`).
- `AlignmentError(reason)` — the R5.3 clean-failure channel, `reason ∈
  {marks_not_found, fit_quality, ambiguous_orientation}`.
- `fit_homography_robust(src, dst, *, gate_rms_px, gate_max_px, min_inliers,
  inlier_thresh_px=None, ransac_iters=200, seed=0)` — seeded-deterministic RANSAC
  over 4-pt minimal samples → refit DLT on the inlier set → **absolute gate**;
  raises `AlignmentError('fit_quality')` over-gate / too-few-inliers,
  `AlignmentError('marks_not_found')` for < 4 correspondences. One all-points
  fallback fit before giving up (low-noise low-N case).
- `resolve_page_orientation(detected_quad, canonical_quad, *, asym_canonical,
  asym_detected, margin_px)` — 4 corners give an exact DLT for *every* rotation, so
  the QR-corner asymmetry is the only signal; returns 0/90/180/270, raises
  `ambiguous_orientation` when the best two are within `margin_px` (R5.2
  clean-specific-failure branch).
- `project_points_mm` — named wrapper for canonical-mm → image-px.
- Registration-point strategy documented in `phase-5.md`: **Stage A** (4 fiducials
  + 3 QR-box corners = 7, version-independent, enough to decode the QR) then
  **Stage B** (fiducials + per-row/per-column timing ticks, dozens of points,
  carries the gate + drives bubble crops). No `sheet_template.json` change needed.

**DoD proof:** `pytest tests/test_omr_geometry.py tests/test_purity.py -q` → **16
passed**; `pytest -m "not django_db" -q` → **200 passed**; `ruff` clean.
`tests/test_omr_geometry.py` builds a plausible capture homography (rot ≤ ±20°,
keystone, scale, translation) and checks against analytic ground truth:
1. DLT exact (rms < 1e-6; grid within 1e-6 px of the true projection);
2. σ=1.5 px detection noise → recovered grid within 3 px everywhere, rms in-band;
3. 2 gross outliers in 40 pts → flagged in `inlier_mask`, fit still < 2 px;
   30/40 random-corrupted → `AlignmentError(fit_quality)`;
4. 5/7 points → still fits; 3 points → `AlignmentError(marks_not_found)`;
5. upright → 0°, 180°-relabelled quad → 180°, centre (symmetric) landmark →
   `AlignmentError(ambiguous_orientation)`;
6. 8 non-projective correspondences + tight gate → `fit_quality` (never a bad
   `HomographyFit`) — this is design principle 3 (over-determination) working.

**Explicitly deferred to the corpus (NOT faked):** the numeric gate values
(`gate_rms_px` / `gate_max_px` / `min_inliers`), the σ real detection produces, and
the R5.2 detect-and-correct-vs-clean-fail decision. 5.1 uses provisional constants;
its tests assert behaviour *relative to* the gate, not the gate's value.

**Commit:** b9f6ef3

---

# ===== PHASE 8 — Dashboard + ingestion UI  (STARTED 2026-09-10) =====

**Out-of-order note.** Phases 5.2–7 are still blocked on the Phase 0.7 corpus.
Phase 8 (the professor web UI) is corpus-independent and was authorised as the
parallel track. Its "results list" DoD item (R6.1) depends on submissions, which
come from the scan pipeline (Phases 5–7) — **user approved 2026-09-10** building
it now and e2e-testing it against hand-built `Submission` fixtures; the real
pipeline wiring is revisited when Phase 7 lands. Subtask plan:
`docs/phases/phase-8.md`. Plan commit `1260f7c`.

**Environment:** Docker Desktop is healthy again this session. Postgres via
`docker run -d -p 127.0.0.1:5433:5432 -e POSTGRES_PASSWORD=dev --name qs-pg8
postgres:16`; `DATABASE_URL=postgres://postgres:dev@127.0.0.1:5433/<db>`.
Baseline before Phase 8: **259 passed** (the memory's "260" counted a test that
was later removed/renamed — 259 is the true Phase 1–5.1 count on Postgres).

## phase-8.1 — Quiz CRUD   (2026-09-10)

**Done:**
- `app/web/forms.py`: `QuizCreateForm` (delegates to `services.create_quiz`;
  `options_per_question` is a 2–6 `TypedChoiceField`), `QuizConfigForm`
  (`ModelForm` on `title` / `marking_mode` / `negative_marking` / `default_points`
  — **no `N`**, since changing it would invalidate ingested option counts).
- `app/web/quiz_views.py`: `quiz_list` (owner-scoped, `-created_at`, annotated
  question/version counts), `quiz_create`, `quiz_detail`, `quiz_edit` (draft-only),
  `quiz_delete` (draft-only, POST). Every view `@login_required` +
  `get_owned_or_404` → foreign/missing pk 404s.
- `app/web/urls.py`: root renamed view → `quiz_list` but **URL name kept as
  `dashboard`** (settings `LOGIN_REDIRECT_URL`, `views.register`, `test_auth_flow`
  all still resolve). New routes `quizzes/new`, `quizzes/<pk>/`,
  `quizzes/<pk>/edit`, `quizzes/<pk>/delete`.
- `app/web/views.py`: dropped the old `dashboard` placeholder view.
- Templates: `base.html` gains a nav bar + `messages` block + minimal inline CSS;
  new `web/quiz_list.html`, `web/quiz_form.html`, `web/quiz_detail.html`,
  `web/quiz_confirm_delete.html`; removed the `web/dashboard.html` stub.
- `tests/test_web_quiz_crud.py` — 13 tests (create valid → draft + redirect;
  5 invalid-field cases write nothing; owner-scoped list; foreign/missing pk 404
  on detail/edit/delete ×2; config edit persists + `N` untouched; edit blocked
  when versioned; delete draft then blocked when printed).

**DoD proof (Postgres :5433 via docker):**
- `pytest tests/test_web_quiz_crud.py tests/test_auth_flow.py -q` → `27 passed`
- `pytest -q` (full suite) → **`272 passed`** (259 + 13)
- `ruff check .` → `All checks passed!`
- `manage.py check` → 0 issues; `makemigrations --check --dry-run` → No changes

**Notes / affects later phases:**
- URL name `dashboard` == the quiz list. 8.6 nav already points there.
- Delete is draft-only (versions are irreplaceable, `Submission.version` is
  PROTECT). "Mark printed" is still Phase 9; nothing here sets `printed_at`.
- 8.2 adds `quizzes/<pk>/upload`; 8.3 `.../versions/generate`; 8.4
  `versions/<pk>/<kind>.pdf`; 8.5 `.../results`. All extend `quiz_detail.html`.

**Commit:** a091449

## phase-8.2 — Question upload UI (xlsx ingest)   (2026-09-10)

**Done:**
- `app/web/forms.py` `QuestionUploadForm` — single `FileField`, rejects
  non-`.xlsx` names; the real validation is `ingest.ingest_quiz`.
- `app/web/quiz_views.py` `quiz_upload` — `get_owned_or_404`, reads the upload
  into `BytesIO`, calls `ingest_quiz`:
  - `result.ok` → success message with the count, redirect to detail;
  - not ok → re-render `web/quiz_upload.html` with `header_errors` /
    `file_errors` / a `row_errors` table (row number + every reason), **HTTP 200**;
  - `IngestBlocked` → error message, redirect to detail (R1.5).
- Route `quizzes/<pk>/upload` (name `quiz_upload`); link on `quiz_detail.html`
  shown only while `can_edit` (draft).
- `tests/test_web_ingest.py` — 5 tests: valid xlsx ingests in file order;
  a 3-bad-row file lists every row + every reason and writes 0 questions;
  re-upload while draft replaces; upload to a versioned quiz → redirect, 0
  written; foreign quiz pk → 404.

**DoD proof (Postgres :5433 via docker):**
- `pytest tests/test_web_ingest.py -q` → `5 passed`
- `pytest -q` → **`277 passed`**; `ruff check .` clean

**Notes / affects later phases:**
- `ingest_quiz` accepts `BytesIO`; `SimpleUploadedFile` bytes round-trip fine.
- Row-error rows render as `<td>{{ re.row }}</td>` — the test greps that markup.

**Commit:** aff699b

## phase-8.3 — Version generation UI   (2026-09-10)

**Done:**
- `app/web/forms.py` `VersionGenerateForm` — `m = IntegerField(min_value=1)`.
- `app/web/quiz_views.py` `version_generate` (POST only; GET → redirect):
  `get_owned_or_404`, calls `generate_versions_for_quiz(quiz, m)`, catches
  `VersionGenerationBlocked` / `InfeasibleVersionCount` / `ValueError` → error
  message + redirect, **nothing written**; success → count message + redirect.
- `quiz_detail` context gains `can_generate` (draft + has questions) and an
  unbound `version_form`; `quiz_detail.html` shows the generate form only then,
  and "add questions first" while draft-without-questions.
- Route `quizzes/<pk>/versions/generate` (name `version_generate`).
- `tests/test_web_versions.py` — 7 tests: generate 3 → 3 rows + status
  `versioned` + detail lists them; `m=0`/`m=-1` → 0 rows, status still draft;
  infeasible (3-question quiz, `m=10`) → 0 rows; generate-twice blocked (stays
  at first batch); no-questions blocked; foreign quiz → 404.

**DoD proof (Postgres :5433 via docker):**
- `pytest tests/test_web_versions.py -q` → `7 passed`
- `pytest -q` → **`284 passed`**; `ruff check .` clean

**Notes:** version generation runs synchronously in the request (Phase 8 design
choice — realistic `M ≤ 20` is fast; Django-Q2 offload is a Phase 7/11 concern
for the batch scan path).

**Commit:** 785b026

## phase-8.4 — Version PDF download   (2026-09-10)

**Done:**
- `app/web/quiz_views.py` `version_pdf(request, pk, kind)` — `kind ∈
  {answer_sheet, question_paper}` else `Http404`; `get_owned_or_404(Version)`;
  `render_and_store_version_pdfs(version)` then streams
  `get_blob_storage().read(paths[kind])` as `application/pdf` with a
  `Content-Disposition: attachment` filename.
- Route `versions/<int:pk>/<str:kind>.pdf` (name `version_pdf`); per-version
  answer-sheet / question-paper links on `quiz_detail.html`.
- `tests/test_web_pdf_download.py` — 6 tests (`override_settings(MEDIA_ROOT=
  tmp_path)`): each kind → 200 + `application/pdf` + `%PDF-` + attachment;
  re-download byte-identical (R3.4); unknown kind → 404; foreign/missing version
  → 404; unauthenticated → redirect to login.

**DoD proof (Postgres :5433 via docker):**
- `pytest tests/test_web_pdf_download.py -q` → `6 passed`
- `pytest -q` → **`290 passed`**; `ruff check .` clean

**Commit:** 3f7fa54

## phase-8.5 — Results list (R6.1)   (2026-09-10)

**Done:**
- `app/web/quiz_views.py` `quiz_results(request, pk)` —
  `Submission.objects.owned_by(user).filter(version__quiz=quiz)`
  `.select_related("roster_entry","version").prefetch_related("answers")`.
  - `?status=<Submission.Status>` filter (unknown value → ignored);
  - `?sort=` ∈ {`captured`,`-captured`,`score`,`-score`}, default `-captured`;
    score sorts use `F("total_score").asc/desc(nulls_last=True)` + `id` tiebreak;
  - per row: status, `total_score`, `created_at`, student
    (`roster_entry.label` → `student_label` → "—"), flags
    (`get_failure_reason_display()` for FAILED, else the distinct `flag_reason`
    of that submission's flagged answers).
- `web/quiz_results.html` — table + status filter links + score/capture sort
  links. "View results" link on `quiz_detail.html`.
- Route `quizzes/<pk>/results` (name `quiz_results`).
- `tests/test_web_results.py` — 6 tests against hand-built `Submission`
  fixtures (`Submission.objects.filter(pk=…).update(created_at=…)` to set the
  auto-now-add capture time): all 4 rows, newest capture first by default;
  `?status=needs_review` filters to 1; `?sort=-score` orders by score desc
  (failed/NULL last), `?sort=captured` oldest first; roster + `student_label` +
  flagged-answer reason + failure reason all render; foreign quiz → 404;
  unauthenticated → login redirect.

**DoD proof (Postgres :5433 via docker):**
- `pytest tests/test_web_results.py -q` → `6 passed`
- `pytest -q` → **`296 passed`**; `ruff check .` clean

**Notes:** submissions are fixtures — the scan pipeline (Phases 5–7) doesn't
exist yet (user-approved 2026-09-10). When Phase 7 lands, the pipeline populates
these rows; the view needs no change.

**Commit:** 03d3aed

## phase-8.6 — Nav + WhiteNoise + R0.2/R0.3 route sweep   (2026-09-10)

**Done:**
- **WhiteNoise** added: `pyproject.toml` dep `whitenoise>=6.6`; `settings.py`
  `whitenoise.middleware.WhiteNoiseMiddleware` right after `SecurityMiddleware`;
  `STORAGES["staticfiles"]` → `whitenoise.storage.CompressedStaticFilesStorage`
  (gzip/brotli, **not** manifest-hashed — no CDN, avoids a collectstatic
  ordering constraint). `deploy/entrypoint.sh`: dropped `|| true` on
  `collectstatic`.
- `base.html`: inline `<style>` moved to `app/web/static/web/app.css`, linked via
  `{% static %}`; nav bar + `messages` block already added in 8.1.
- `pyproject.toml` pytest `filterwarnings` ignores WhiteNoise's "No directory at"
  `UserWarning` (tests don't run collectstatic).
- `tests/test_web_route_isolation.py` — 2 sweep tests over **12** (method, url)
  pairs covering every Phase 8 route:
  - unauthenticated → 302 to `/accounts/login/` (R0.3);
  - professor B against professor A's quiz / version ids → **404** (R0.2, never
    403). Closes the route-level R0.2 verification deferred from Phase 1.2.

**DoD proof (Postgres :5433 via docker):**
- `pytest tests/test_web_route_isolation.py -q` → `2 passed`
- `pytest -q` → **`298 passed`**; `ruff check .` clean
- `manage.py collectstatic --noinput` → 128 files, no collision
- `manage.py check --deploy` → 6 warnings, **same classes** as the Phase 0.4
  baseline (SECRET_KEY / SESSION_COOKIE_SECURE / CSRF_COOKIE_SECURE / DEBUG — all
  TLS/localhost-prototype, non-blocking); `manage.py check` → 0
- fresh `ci_fresh` DB → `migrate` to head; `migrate --check` → exit 0
- `makemigrations --check --dry-run` → No changes detected

**Notes / affects later phases:**
- **Deps added**: `whitenoise 6.12.0` (in `.venv` + pyproject core deps).
- Docker image rebuild picks up whitenoise via `pip install .`; the `web`
  entrypoint now hard-fails if `collectstatic` fails (intended).
- **Still owed on the `docker` runtime**: `scripts/ci.sh` (default),
  `docker compose ... up --build` with the new static pipeline — Docker Desktop
  daemon is up this session but the full compose path wasn't re-exercised.

**Phase 8 complete.** All 6 subtasks done + verified on Postgres. Phase 8 was
built out of §5 order (Phases 5.2–7 still blocked on the Phase 0.7 corpus) as the
sanctioned parallel track; the results list is fixture-tested pending Phase 7.

**Commit:** bb60a98

---

# ===== PHASE 9 — Review UI + audit  (STARTED 2026-09-10) =====

Same out-of-order rationale as Phase 8 (Phases 5.2–7 blocked on the corpus; Phase 9
is corpus-independent and builds on Phase 8's views). Review UI + overrides are
e2e-tested against hand-built `Submission`/`Answer` fixtures pending the Phase 7
pipeline (user-approved 2026-09-10). No new columns; scoring formula untouched.
Plan: `docs/phases/phase-9.md`.

## phase-9.1 — Review + grading services   (2026-09-10)

**Done:**
- `app/grading/regrade.py` (pure): `submission_total(scores)` (skips `None`),
  `status_after_override(current, any_flagged)` — R6.3 local rule
  (`needs_review` + no flags → `finalized`; `finalized` stays; else unchanged).
- `app/core/review_service.py`:
  - `override_answer(*, answer, professor, marked_options)` — recovers the
    question's sheet-letter key (`recover_correct_letters`), re-scores via
    `score_question` (R7.5, first prod call site), sets
    `detected_options/score/correct/manually_edited/edited_at`, clears the flag,
    recomputes `submission.total_score` + `status`, writes an `overridden`
    `AuditEvent` (before/after). Atomic.
  - `assign_student(*, submission, professor, roster_entry=None, label="")` —
    sets exactly one of roster/free-text, clears the other; `assigned` event.
  - `parse_roster(text)` — `label` or `label, external_id` per non-blank line;
    `ValueError` on empty label.
  - `replace_roster(*, quiz, professor, text)` — parse + replace (not append);
    `assigned` event with `roster_size`. Removed entries → submissions'
    `roster_entry` goes NULL (FK `SET_NULL`).
  - `mark_version_printed(*, version, professor)` — sets `printed_at` if unset,
    flips `quiz.status → printed` on the first printed version, `printed` event.
    Idempotent. **Only** path that sets `printed_at` / flips to `printed` (R3.5).
- `tests/test_review_service.py` — 15 tests (2 pure param sets + DB): override
  re-score + flag clear + finalize + audit; status held while another flag
  remains; override on finalized stays finalized; assign roster→free-text (2
  events); `parse_roster` forms + empty-label reject; `replace_roster` replaces;
  `mark_version_printed` flips quiz + idempotent + second version.

**DoD proof (Postgres :5433 via docker):**
- `pytest tests/test_review_service.py tests/test_purity.py -q` → `15 passed`
  (purity still green — `regrade.py` is numpy/stdlib only)
- `ruff check .` clean

**Notes / affects later phases:**
- `override_answer` is the first `score_question` call site in production code;
  the R7.5 parity assertion still lands in Phase 7 (scan pipeline = other site).
- `mark_version_printed` does the R3.5 `quiz.status` flip in app logic (no DB
  trigger) — safe because it's the sole writer of `printed_at`.

**Commit:** e75e6f1

## phase-9.2 — Submission detail view (R6.2) + audit history (R6.5)   (2026-09-10)

**Done:**
- `app/web/review_views.py` `submission_detail(request, pk)` —
  `get_owned_or_404(Submission)`; builds an answer row per `answer` (question no,
  `detected_options`, confidence, canonical correct letters via
  `recover_correct_letters`, `correct`, flagged+reason, score, `manually_edited`);
  **flagged rows sorted to the top**, then question order. Passes the
  submission's `AuditEvent`s newest-first and an unbound `StudentAssignForm`.
- `app/web/forms.py`: `AnswerOverrideForm` (`n_options`-kwarg
  `MultipleChoiceField` of `A..`, `required=False`), `StudentAssignForm`
  (`roster_entry` ModelChoice + `student_label`; `clean` rejects both/neither),
  `RosterPasteForm` (textarea; `clean_text` runs `parse_roster`).
- `web/submission_detail.html` — assignment form, answer-sheet table with a
  per-row A.. checkbox override form, history table. Status-cell link added on
  `quiz_results.html`.
- Routes `submissions/<pk>/`, `submissions/<pk>/assign`, `answers/<pk>/override`
  (the assign/override endpoints ship here; **tested in 9.3**).
- `tests/test_web_submission_detail.py` — 4 tests: 5-answer sheet renders all
  rows, flagged rows precede the edited (unflagged) row, "edited" marker shown,
  flag reason + correct key + score shown; history newest-first; **opening the
  page writes no `AuditEvent`** (R6.5 passive-view); foreign/missing pk → 404;
  unauthenticated → login redirect.

**DoD proof (Postgres :5433 via docker):**
- `pytest tests/test_web_submission_detail.py -q` → `4 passed`
- `pytest -q` → **`316 passed`**; `ruff check .` clean

**Notes:** AuditEvent rows can't be `UPDATE`d (DB trigger `quizscan_block_audit_
update`) — tests rely on insertion order for `-created_at`, never `.update()`.

**Commit:** 7186599

## phase-9.3 — Override + student-assignment endpoints (R6.3 / R6.4)   (2026-09-10)

**Done:** (endpoints shipped in 9.2's commit; this subtask is their e2e test)
- `answer_override(request, pk)` POST → `review_service.override_answer` with the
  `AnswerOverrideForm`-validated letter set; message + redirect to detail.
- `submission_assign(request, pk)` POST → `review_service.assign_student`;
  `StudentAssignForm` both/neither → non-field error surfaced as a message,
  nothing written.
- `tests/test_web_review_actions.py` — 5 tests: override a wrong answer → row +
  total + status updated, `Overridden` in history; override on a finalized
  submission stays finalized; assign by roster then free text → shows in the
  results list, 2 `assigned` events; both-set / neither-set → rejected, no
  write, no event; foreign answer / submission pk → 404.

**DoD proof (Postgres :5433 via docker):**
- `pytest tests/test_web_review_actions.py -q` → `5 passed`
- `pytest -q` → **`321 passed`**; `ruff check .` clean

**Commit:** <pending>
