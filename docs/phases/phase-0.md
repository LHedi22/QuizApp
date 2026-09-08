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

## Subtask ordering rationale

0.7 (physical printing / photographing / scanning) is the long-pole task and only the
user can do it. So the throwaway sheet (0.2) and the label schema + validator (0.3)
come **first**, right after the scaffold — the user can start the capture pass while
Claude builds the Django project (0.4), compose (0.5), and CI (0.6).

## What Phase 0 does NOT do

- No data model / migrations of our own tables, no custom auth (Phase 1). The Django
  project in 0.4 is bare `startproject` + settings + a health endpoint; the only
  migrations that exist are Django's built-ins (`auth`, `contenttypes`, `sessions`,
  `admin`) and `django_q`. That is enough to satisfy "CI runs a clean-DB migration."
- No `config/sheet_template.json` (Phase 1 — §3.2A). 0.2's throwaway sheet has its own
  disposable geometry baked into the script and must never be imported or referenced
  by Phases 1/4/5.
- No ingestion, version generation, OMR pipeline, or PDF renderer in `app/pdf`.

## Definition-of-Done rules for this phase

- Every subtask's DoD is a command that is actually run, with its output pasted into
  `docs/PROGRESS.md`. No "should work".
- One commit per completed subtask, message `phase-0: <subtask> (<theme>)`.
- Subtask 0.7 is executed by the user. Everything around it — generator, schema,
  validator, protocol — is built and proven first so that "run `check_corpus.py` and
  it exits 0" is the only remaining step.

## Open decisions carried into Phase 1 (not blocking Phase 0)

- **`config/` location.** REBUILD_SPEC §5's repo-tree diagram indents `config/` under
  `app/`, but `docs/CLAUDE.md` ("Where things live") and §3.2A both write
  `config/sheet_template.json` at the repo root. Phase 0 uses **repo-root `config/`**.
  Confirm at the start of Phase 1 before authoring `sheet_template.json` (rule 5 —
  geometry-adjacent).

---

## Subtask 0.1 — Repo scaffold + Python tooling  ✅ done (commit 19b8573)

**Goal.** Create the directory tree from §5 and a working lint/test toolchain.

**Delivered.** Directory tree, `pyproject.toml` (runtime + `[dev]` deps, ruff + pytest
config), `.gitignore`, `.gitattributes` (LF normalization + binary corpus),
`README.md`, `docs/PROGRESS.md` header, `tests/test_purity.py` (CLAUDE.md rule 7 —
subprocess check that `app.omr` / `app.grading` import with no django/flask/fastapi/
starlette), `tests/test_sanity.py`.

**DoD met.** `pip install -e ".[dev]"` → exit 0; `ruff check .` → `All checks passed!`;
`pytest -q` → `2 passed`. See PROGRESS phase-0.1.

---

## Subtask 0.2 — Throwaway OMR test sheet generator (corpus capture only)

**Goal.** Produce a printable single-page sheet good enough to photograph for the
corpus, without waiting on Phase 4.

**Deliverables.**
- `scripts/make_throwaway_sheet.py` — **standalone**, does NOT live in `app/pdf` and
  does NOT read `config/sheet_template.json` (which does not exist until Phase 1).
  ReportLab, one A4 portrait page with:
  - a full registration perimeter: 4 solid corner fiducials **plus** edge
    timing/registration marks along at least two sides (Scantron-style), with quiet
    zones;
  - a QR (top area) encoding a random `sheet_token`;
  - a bubble grid — default 40 questions × 4 options, printed `Q#` row labels and
    `A–D` column labels;
  - a handwriting box for a human-written sheet id and a "filled by" line.
  - CLI: `--questions` (default 40), `--options` (default 4), `--out <stem>`.
- Emits `<stem>.pdf`, `<stem>.png` (preview raster), `<stem>.meta.json`
  (`sheet_token`, `page_size`, `questions`, `options`, `generator_version`, and the
  grid geometry in mm for unambiguous labeling later).
- `scripts/check_throwaway_sheet.py <stem>` — rasterizes the PDF with PyMuPDF at
  ~180 DPI, decodes the QR with `pyzbar`, asserts it equals `meta.json`'s
  `sheet_token`.

**Definition of Done (runnable).**
1. `python scripts/make_throwaway_sheet.py --out corpus/_source/throwaway_v0` — creates
   `.pdf`, `.png`, `.meta.json`.
2. `python scripts/check_throwaway_sheet.py corpus/_source/throwaway_v0` — decodes the
   QR from the **rasterized page** (not the standalone QR image) and asserts it equals
   the meta token; exits 0.
3. `pytest tests/test_throwaway_sheet.py -q` — same check wired as a test (generates to
   a tmp dir, renders, decodes, asserts).
4. `throwaway_v0.png` sent to the user for visual confirmation (perimeter + grid + QR
   all present and legible at print size).

- PROGRESS records: this geometry is disposable; Phases 1/4/5 must not reference it.

---

## Subtask 0.3 — Corpus schema, capture protocol, and validator

**Goal.** Lock the ground-truth label format and build the validator that gates the
whole phase — proven correct on fixtures before any real image exists.

**Deliverables.**
- `corpus/README.md` — the capture protocol / checklist for the user:
  - target counts: **≥ 30 phone photos, ≥ 10 copier scans** (spec minimums);
  - **≥ 5** sheets photocopied 1–2 generations before being filled in (§6 Q10 — "must
    include"; 5 is this project's chosen floor, not a spec number);
  - **≥ 5** captures upside-down / fed reversed (§6 Q18 — likewise a chosen floor);
  - variety: rotation to ~±20°, page filling 40–100% of frame, normal indoor lighting,
    some shadow/glare;
  - **image size guidance:** long edge ~1500–2200 px is plenty (sheets are read at
    ~150–200 DPI); downscale phone photos before committing to keep the repo small and
    sidestep Git LFS.
- `corpus/labels/SCHEMA.md` + one worked example label.
- Label format — one JSON per image at `corpus/labels/<image_stem>.json`:
  - `image` — filename under `corpus/images/`
  - `capture_type` — `phone_photo` | `copier_scan`
  - `photocopy_generations` — int 0–3
  - `orientation` — `upright` | `upside_down` | `reversed`
  - `sheet_token` — resolves to a `corpus/_source/*.meta.json`
  - `lighting` — free text
  - `marked_options` — map `"<question_number>" → ["A", ...]`, `[]` = blank; letters
    within the source sheet's option count; this is the per-bubble filled/empty ground
    truth for Phase 6
  - `fiducial_px` — **optional**, recommended on ≥ 10 images: the four corner-fiducial
    centre pixel coordinates `[[x,y],...]`, hand-clicked, as gold alignment truth for
    Phase 5
  - `notes` — free text
- `scripts/new_label.py <image>` — scaffolds a label file (fills `image`, guesses
  `capture_type` from a filename prefix, leaves the rest for the user).
- `scripts/check_corpus.py` — validates:
  - every file in `corpus/images/` has a parseable label, and vice versa;
  - each `sheet_token` resolves; `marked_options` letters/question numbers in range for
    that sheet; enums valid; `fiducial_px` (if present) is 4 points in image bounds;
  - aggregate thresholds (all of): ≥ 30 `phone_photo`, ≥ 10 `copier_scan`, ≥ 5 with
    `photocopy_generations ≥ 1`, ≥ 5 with `orientation ∈ {upside_down, reversed}`;
  - prints a summary table; exits non-zero if anything fails, naming what is missing.
- `tests/test_corpus_validator.py` — runs the validator against
  `tests/fixtures/corpus_good/` and `tests/fixtures/corpus_bad/` (tiny hand-made label
  sets + 1×1 px stand-in images, no real captures needed) and asserts pass / the
  specific failures.

**Definition of Done (runnable).**
1. `pytest tests/test_corpus_validator.py -q` — exits 0 (validator proven on good + bad
   fixtures, including each individual failure mode).
2. `python scripts/check_corpus.py` — runs, prints the summary; with zero real images
   exits non-zero and names exactly what is missing. This is the standing gate for 0.7.

---

## Subtask 0.4 — Django project + Postgres settings + Django-Q2 wired

**Goal.** A bare Django project that checks clean, migrates clean against Postgres, and
answers a health check. No app models, no custom auth.

**Deliverables.**
- `manage.py` (→ `app.settings`), `app/settings.py`, `app/urls.py`, `app/wsgi.py`,
  `app/asgi.py`.
- `app/settings.py` env-driven via `dj-database-url`: `SECRET_KEY`, `DEBUG`,
  `ALLOWED_HOSTS`, `DATABASE_URL` (Postgres, `psycopg` v3). `django_q` + `app.web` in
  `INSTALLED_APPS`; `Q_CLUSTER` using the Django ORM broker (`orm: "default"`, no
  Redis).
- `app/web/` — Django app with `views.healthz` → `JsonResponse({"status": "ok"})`
  (HTTP 200) at `/healthz`; a `base.html` stub; `app/web/tests.py` (or
  `tests/test_healthz.py`) covering it.
- Add `DJANGO_SETTINGS_MODULE = "app.settings"` to `[tool.pytest.ini_options]`; add a
  `.env.example` at repo root for non-docker local runs.

**Definition of Done (runnable).**
1. `python manage.py check` — exits 0.
2. Throwaway Postgres:
   `docker run --rm -d -p 127.0.0.1:55432:5432 -e POSTGRES_PASSWORD=dev --name qs-pg postgres:16`
   then `DATABASE_URL=postgres://postgres:dev@localhost:55432/postgres`.
3. `python manage.py migrate` — reaches head, zero prompts; re-run → "No migrations to
   apply".
4. `python manage.py migrate --check` — exits 0.
5. `pytest -q` — healthz test + existing purity/sanity tests all pass.
6. `docker rm -f qs-pg`.

---

## Subtask 0.5 — `docker-compose` boots app + postgres on `localhost` (no proxy)

**Goal.** One command brings the app up on `127.0.0.1`, migrated and healthy — exactly
two services (plus the Django-Q2 worker running from the same image, no third
container).

**Deliverables.**
- `deploy/Dockerfile` — `python:3.12-slim` + `libzbar0` (pyzbar) + build deps;
  installs the project; non-root user.
- `deploy/docker-compose.yml` — services **`app`**, **`worker`** (same image,
  `command: python manage.py qcluster`), **`postgres`**. All host ports bound to
  `127.0.0.1` only. Volumes: `pgdata`, `blobstore` (mounted `/data/blob`). `app`
  entrypoint runs `migrate` then `gunicorn`. No `proxy`/`nginx`/`traefik`. No TLS.
- `deploy/.env.example`, `deploy/entrypoint.sh`, `.dockerignore`.

**Definition of Done (runnable).**
1. `cp deploy/.env.example deploy/.env`
2. `docker compose -f deploy/docker-compose.yml up -d --build` — succeeds.
3. `curl -fsS http://localhost:${APP_PORT}/healthz` → `{"status": "ok"}`, HTTP 200.
4. `docker compose -f deploy/docker-compose.yml exec app python manage.py migrate --check`
   — exits 0.
5. `docker compose -f deploy/docker-compose.yml ps` — `app`, `worker`, `postgres` only,
   no proxy. `docker compose ... port app 8000` → address starts `127.0.0.1:`.
6. `docker compose -f deploy/docker-compose.yml logs worker` — Django-Q2 cluster
   started, no errors (functional task processing is proven in Phase 7, not here).
7. `docker compose -f deploy/docker-compose.yml down` — clean.

- Paste outputs 2–7 into PROGRESS.

---

## Subtask 0.6 — CI: lint + tests + clean-DB migration

**Goal.** A CI definition that runs ruff, pytest, and proves a fresh empty database
migrates to head (precursor to R8.1), plus a local mirror script (no GitHub remote
exists yet).

**Deliverables.**
- `.github/workflows/ci.yml` — jobs: `lint` (ruff), `test` (pytest with a `postgres:16`
  service), `migrate-clean-db` (create empty DB → `migrate` → `migrate --check`).
- `scripts/ci.sh` — runs the same three steps locally against a disposable Postgres
  container so the DoD is runnable now.

**Definition of Done (runnable).**
1. `bash scripts/ci.sh` — exits 0; output shows ruff clean, pytest green, and `migrate`
   applying every migration to an empty DB then `--check` clean.
2. `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"` — exits 0
   (add `pyyaml` to `[dev]`). Run `actionlint` if available.
3. PROGRESS notes: pushing to a remote to see the green check is deferred until a
   GitHub remote exists; `scripts/ci.sh` is the standing proof until then.

---

## Subtask 0.7 — Capture and commit the real corpus  *(user-executed; phase gate)*

**Goal.** The actual images exist, are labeled, and the validator passes.

**Executed by the user** (physical steps — Claude cannot do these):
1. Print `corpus/_source/throwaway_v0.pdf` on a laser printer.
2. Photocopy a handful of copies 1 and 2 generations deep.
3. Fill in bubbles by hand on ~40 sheets (vary how cleanly).
4. Photograph ≥ 30 with a phone: vary angle (to ~±20°), distance (page 40–100% of
   frame), indoor lighting; **include ≥ 5 captured upside-down / fed reversed**.
5. Scan ≥ 10 on a copier/MFP to images or a PDF (split to pages).
6. Downscale to ~1500–2200 px long edge; drop in `corpus/images/`; run
   `scripts/new_label.py` per image and fill in the true `marked_options` from the
   physical sheets; add `fiducial_px` to ≥ 10.

**Deliverables.** `corpus/images/*`, `corpus/labels/*.json` committed (Git LFS only if
real file sizes warrant — decide then).

**Definition of Done (runnable).**
1. `python scripts/check_corpus.py` — **exits 0**; every image labeled, every label
   valid, all thresholds met.
2. `git log --stat` (or `git lfs ls-files`) shows the corpus committed.

**Phase 0 is complete only when 0.7's DoD passes.** Until then, 0.1–0.6 are committed
and PROGRESS records that the phase is blocked on the user's capture pass, with the
checklist above as the hand-off.

---

## Phase 0 exit checklist

- [x] 0.1 scaffold — `ruff` + `pytest` green in `.venv`  (commit 19b8573)
- [x] 0.2 throwaway sheet — generated; QR decodes from rasterized page  (commit 777bc63)
- [x] 0.3 corpus validator — proven on tmp-path corpora; `check_corpus.py` gate active  (commit 00c8d27)
- [x] 0.4 Django — `manage.py check` + `migrate --check` clean on Postgres, healthz 200
- [x] 0.5 compose — `docker compose up` → healthz 200; app + worker + postgres, 127.0.0.1
- [ ] 0.6 CI — `scripts/ci.sh` green; workflow YAML parses
- [ ] 0.7 real corpus — `check_corpus.py` exits 0; committed
