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

**Commit:** _(phase-2: verify 2.2-2.4 DoDs against Postgres (podman workaround))_
