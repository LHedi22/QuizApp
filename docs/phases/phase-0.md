# Phase 0 — Scaffold + capture corpus

> Source: `docs/REBUILD_SPEC.md` §5 (Phases table, row 0) and §5 "Change four things
> about the process" item 1. Governing rules: `docs/CLAUDE.md`.

## Phase goal

Stand up the empty-repo skeleton so every later phase has a place to put code, a
one-command local runtime, and a CI gate — **and**, most importantly, collect the
**real-capture test corpus** now, before any alignment code is written, so every OMR
Definition of Done from Phase 5 on is measured against real optics instead of
synthetic PDF rasterizations (the single biggest process failure of the first build,
§3.3 / Appendix B.5).

## What Phase 0 does NOT do

- No data model / migrations of our own tables (Phase 1).
- No `config/sheet_template.json` (Phase 1 — §3.2A).
- No real PDF renderer in `app/pdf` (Phase 4). The throwaway sheet in subtask 0.5 is
  explicitly disposable and must never be imported or referenced by Phases 1/4/5.
- No ingestion, no version generation, no OMR pipeline.

## Definition-of-Done rules for this phase

- Every subtask's DoD is a command that is actually run, with its output pasted into
  `docs/PROGRESS.md`. No "should work".
- One commit per completed subtask, message `phase-0: <subtask> (<theme>)`.
- Subtask 0.7 is executed by the user (physical printing/photographing). Everything
  around it — generator, schema, validator, protocol — is built and proven first so
  that "run `check_corpus.py` and it exits 0" is the only remaining step.

---

## Subtask 0.1 — Repo scaffold + Python tooling

**Goal.** Create the directory tree from §5 and a working lint/test toolchain.

**Deliverables.**
- Directory tree (all with `__init__.py` or `.gitkeep` as appropriate):
  ```
  app/  app/omr/  app/grading/  app/pdf/  app/web/  app/config/
  corpus/  corpus/images/  corpus/labels/  corpus/_source/
  tests/  deploy/  scripts/  .github/workflows/
  ```
- `pyproject.toml` — project metadata, runtime deps, `[project.optional-dependencies].dev`
  (ruff, pytest, pytest-django), `[tool.ruff]`, `[tool.pytest.ini_options]`.
- `.gitignore` (`.venv/`, `__pycache__/`, `*.pyc`, `.env`, `db.sqlite3`, `/media/`,
  `staticfiles/`, `.pytest_cache/`, `*.pdf` under `corpus/_source/` kept — see note).
- `.gitattributes` — mark `corpus/images/**` as binary (LFS decision deferred to 0.7).
- `README.md` — one-paragraph what/why + "see docs/REBUILD_SPEC.md".
- `docs/PROGRESS.md` header.
- `tests/test_purity.py` — asserts `import app.omr` and `import app.grading` succeed
  with **no `django` / web framework module** present in `sys.modules` afterward
  (CLAUDE.md rule 7).
- `tests/test_sanity.py` — one trivial passing test so the runner is proven.

**Definition of Done (runnable).**
1. `python -m venv .venv` then `.venv/Scripts/python -m pip install -e ".[dev]"` — exits 0.
2. `.venv/Scripts/ruff check .` — exits 0.
3. `.venv/Scripts/python -m pytest -q` — exits 0, ≥ 2 tests passed, `test_purity.py`
   among them.

---

## Subtask 0.2 — Django project + Postgres settings + Django-Q2 wired

**Goal.** A minimal Django project that checks clean, migrates clean against Postgres,
and answers a health check. No app models yet.

**Deliverables.**
- `manage.py` (→ `app.settings`), `app/settings.py`, `app/urls.py`, `app/wsgi.py`,
  `app/asgi.py`.
- `app/settings.py` env-driven: `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`,
  `DATABASE_URL` (parsed; Postgres via `psycopg` v3), `DJANGO_Q` config using the
  Django ORM broker (no Redis). `django_q` and `app.web` in `INSTALLED_APPS`.
- `app/web/` — Django app with `views.healthz` returning `JsonResponse({"status":"ok"})`
  (HTTP 200), wired at `/healthz`. A `base.html` stub.
- `.env.example` at repo root for local (non-docker) runs.

**Definition of Done (runnable).**
1. `python manage.py check` — exits 0.
2. Start a throwaway Postgres: `docker run --rm -d -p 127.0.0.1:55432:5432 -e POSTGRES_PASSWORD=dev --name qs-pg postgres:16` ; set `DATABASE_URL` to it.
3. `python manage.py migrate` — reaches head, zero prompts. Re-run → "No migrations to apply".
4. `python manage.py migrate --check` — exits 0.
5. `python manage.py test app.web` (or `pytest tests/test_healthz.py`) — healthz returns
   200 and JSON body `{"status": "ok"}`.
6. Tear down: `docker rm -f qs-pg`.

---

## Subtask 0.3 — `docker-compose` boots app + postgres on `localhost` (no proxy)

**Goal.** One command brings the whole app up on `127.0.0.1`, migrated, healthy —
exactly two services.

**Deliverables.**
- `deploy/Dockerfile` — `python:3.12-slim` + `libzbar0` (pyzbar) + build deps; installs
  the project; non-root user.
- `deploy/docker-compose.yml` — services **`app`** and **`postgres`** only. Both bind
  to `127.0.0.1` (`ports: ["127.0.0.1:${APP_PORT}:8000"]` etc). Volumes: `pgdata`,
  `blobstore` (mounted at `/data/blob`). `app` command runs migrate → gunicorn. A
  `qcluster` process for Django-Q2 runs as a **second command in the same image**
  (either a `command`-override sidecar service reusing the built image, or an entrypoint
  supervisor) — no third service, no broker container.
- `deploy/.env.example`, `deploy/entrypoint.sh`.
- No `proxy`/`nginx`/`traefik` service. No TLS. No exposed `0.0.0.0`.

**Definition of Done (runnable).**
1. `cp deploy/.env.example deploy/.env`
2. `docker compose -f deploy/docker-compose.yml up -d --build` — succeeds.
3. `curl -fsS http://localhost:${APP_PORT}/healthz` → `{"status": "ok"}`, HTTP 200.
4. `docker compose -f deploy/docker-compose.yml exec app python manage.py migrate --check`
   — exits 0.
5. `docker compose -f deploy/docker-compose.yml ps` — shows only `app` (+ its qcluster)
   and `postgres`. `docker compose ... port app 8000` → address starts `127.0.0.1:`.
6. `docker compose -f deploy/docker-compose.yml down` — clean.
- Paste all six outputs into PROGRESS.

---

## Subtask 0.4 — CI: lint + tests + clean-DB migration

**Goal.** A CI definition that runs ruff, pytest, and proves a fresh empty database
migrates to head (precursor to R8.1), plus a local mirror script.

**Deliverables.**
- `.github/workflows/ci.yml` — jobs: `lint` (ruff), `test` (pytest with a `postgres:16`
  service), `migrate-clean-db` (create empty DB → `migrate` → `migrate --check`).
- `scripts/ci.sh` — runs the same three steps locally against a disposable Postgres
  container so the DoD is runnable without a GitHub remote.

**Definition of Done (runnable).**
1. `bash scripts/ci.sh` — exits 0; output shows ruff clean, pytest green, migrate
   applying all migrations to an empty DB then `--check` clean.
2. `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"` — exits 0
   (YAML parses). Run `actionlint` if available.
3. PROGRESS notes that pushing to a remote to see the green check is deferred until a
   GitHub remote exists; the local mirror is the standing proof until then.

---

## Subtask 0.5 — Throwaway OMR test sheet generator (corpus capture only)

**Goal.** Produce a printable single-page sheet good enough to photograph for the
corpus, without waiting on Phase 4.

**Deliverables.**
- `scripts/make_throwaway_sheet.py` — **standalone**, does NOT live in `app/pdf` and
  does NOT read `config/sheet_template.json` (which does not exist until Phase 1).
  Renders one A4 portrait page with:
  - a full registration perimeter: 4 solid corner fiducials **plus** edge
    timing/registration marks along at least two sides (Scantron-style), with quiet
    zones;
  - a QR encoding a dummy `sheet_token`;
  - a bubble grid — default 40 questions × 4 options, printed `Q#` and `A–D` labels;
  - a handwriting field for a human-written sheet id.
- Emits `<out>.pdf`, `<out>.png` (preview), `<out>.meta.json` (token, page size,
  question count, option count, grid geometry) for unambiguous labeling later.
- `scripts/check_throwaway_sheet.py` — rasterizes the PDF (via PyMuPDF) at ~180 DPI and
  decodes the QR with `pyzbar`.

**Definition of Done (runnable).**
1. `python scripts/make_throwaway_sheet.py --out corpus/_source/throwaway_v0` — creates
   the three files.
2. `python scripts/check_throwaway_sheet.py corpus/_source/throwaway_v0` — decodes the
   QR from the rasterized page and asserts it equals `meta.json`'s `sheet_token`;
   exits 0.
3. `throwaway_v0.png` sent to the user for visual confirmation (perimeter + grid + QR
   all present and legible).
- PROGRESS records: this geometry is disposable; Phases 1/4/5 must not reference it.

---

## Subtask 0.6 — Corpus schema, capture protocol, and validator

**Goal.** Lock the ground-truth label format and build the validator that gates the
whole phase — proven correct on fixtures before any real image exists.

**Deliverables.**
- `corpus/README.md` — the capture protocol / checklist for the user: target counts,
  phone vs copier split, photocopy generations, orientations (incl. upside-down /
  reversed), lighting/angle variety, filename convention.
- `corpus/labels/SCHEMA.md` + one worked example label.
- Label format — one JSON per image at `corpus/labels/<image_stem>.json`:
  `image`, `capture_type` (`phone_photo` | `copier_scan`),
  `photocopy_generations` (int 0–3), `orientation` (`upright` | `upside_down` |
  `reversed`), `sheet_token` (resolves to a `_source/*.meta.json`), `lighting` (free
  text), `marked_options` (map `question_number → [letters]`, `[]` = blank),
  `notes`.
- `scripts/new_label.py` — helper that scaffolds a label file for an image.
- `scripts/check_corpus.py` — validates:
  - every file in `corpus/images/` has a parseable label, and vice versa;
  - each `sheet_token` resolves to a known source sheet; `marked_options` letters lie
    within that sheet's option count; question numbers in range;
  - aggregate thresholds: **≥ 30 `phone_photo`, ≥ 10 `copier_scan`**, **≥ 5** with
    `photocopy_generations ≥ 1`, **≥ 5** with `orientation` in
    {`upside_down`, `reversed`};
  - prints a summary table; exits non-zero if anything fails.
- `tests/test_corpus_validator.py` — runs `check_corpus.py`'s logic against
  `tests/fixtures/corpus_good/` and `tests/fixtures/corpus_bad/` (tiny hand-made label
  sets, no real images needed) and asserts pass / specific failures.

**Definition of Done (runnable).**
1. `python -m pytest tests/test_corpus_validator.py -q` — exits 0 (validator proven on
   good + bad fixtures).
2. `python scripts/check_corpus.py` — runs, prints the summary; with zero real images
   exits non-zero and names exactly what is missing. This is the standing gate for 0.7.

---

## Subtask 0.7 — Capture and commit the real corpus  *(user-executed; phase gate)*

**Goal.** The actual images exist, are labeled, and the validator passes.

**Executed by the user** (physical steps — Claude cannot do these):
1. Print `corpus/_source/throwaway_v0.pdf` on a laser printer.
2. Photocopy a handful of copies 1 and 2 generations deep.
3. Fill in bubbles by hand on ~40 sheets (vary how cleanly).
4. Photograph ≥ 30 with a phone: vary angle (to ~±20°), distance (page 40–100% of
   frame), indoor lighting, and **include several captured upside-down / fed reversed**.
5. Scan ≥ 10 on a copier/MFP to images or a PDF (split to pages).
6. Drop images in `corpus/images/`, create labels with `scripts/new_label.py`, fill in
   the true `marked_options` from the physical sheets.

**Deliverables.** `corpus/images/*`, `corpus/labels/*.json` committed (Git LFS if
`git` history size warrants — decide when real file sizes are known).

**Definition of Done (runnable).**
1. `python scripts/check_corpus.py` — **exits 0**; every image labeled, every label
   valid, all thresholds met.
2. `git log --stat` (or `git lfs ls-files`) shows the corpus committed.

**Phase 0 is complete only when 0.7's DoD passes.** Until then, subtasks 0.1–0.6 are
committed and PROGRESS records that the phase is blocked on the user's capture pass,
with the checklist above as the hand-off.

---

## Phase 0 exit checklist

- [x] 0.1 scaffold — `ruff` + `pytest` green in `.venv`  (commit 19b8573)
- [ ] 0.2 Django — `manage.py check` + `migrate --check` clean on Postgres, healthz 200
- [ ] 0.3 compose — `docker compose up` → healthz 200, exactly app + postgres, 127.0.0.1
- [ ] 0.4 CI — `scripts/ci.sh` green; workflow YAML parses
- [ ] 0.5 throwaway sheet — generated; QR decodes from rasterized page
- [ ] 0.6 corpus validator — proven on fixtures; `check_corpus.py` gate active
- [ ] 0.7 real corpus — `check_corpus.py` exits 0; committed
