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

**Commit:** _(phase-1: data model + ordered migrations + immutability triggers (1.1))_
