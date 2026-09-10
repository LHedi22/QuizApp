# Phase 12 — Packaging + ops

> Source: `docs/REBUILD_SPEC.md` §5 (Phases table, row 12), §2 R8.1–R8.3, §3.1,
> §6 (localhost-only, no TLS). Governing rules: `docs/CLAUDE.md`.

## Phase goal

Make the prototype self-hostable and its irreplaceable data recoverable:

1. **Zero-LLM source scan in CI (R8.3)** — a test proves no LLM import / client /
   API-key / call exists on the grading path. (No Phase 10 aid exists yet, so the
   scan currently covers the whole tree.)
2. **Backup + restore scripts (R8.2)** — `pg_dump` of the database (especially
   `versions`) + an archive of the blob store (PDFs / future scans), written to a
   local backup dir; `restore` reverses it.
3. **A *tested* restore (R8.2)** — an automated round-trip: seed → backup → wipe →
   restore → assert the data (quizzes, immutable version maps, stored PDF bytes)
   came back byte-for-byte. Restore is proven, not assumed.
4. **One-command bring-up** — `docker compose … up -d --build` brings the whole
   app to `http://localhost:<APP_PORT>` from a clean slate, now including the
   WhiteNoise `collectstatic` step (Phase 8.6); a documented `deploy/.env`.
   Closes the still-owed in-container Phase 1.4 loader check.
5. **Ops runbook** — `deploy/RUNBOOK.md`: first run, migrate, backup, restore,
   wipe-and-reseed, and the Windows / Docker gotchas hit across the build.
6. **CI green** with the new scan + a restore smoke.

## What Phase 12 does NOT do

- **No TLS, no reverse proxy, no host provisioning, no remote deploy, no
  scheduled/off-host backups** — explicitly out of scope until the prototype
  graduates (§6). The runbook may *mention* a cron line; it is not wired.
- **Scan-image backup is structurally covered but not yet exercised** — no scans
  exist until Phase 7. `backup.sh` archives all of `MEDIA_ROOT`, so scans are
  included the moment they exist; the tested round-trip uses the PDFs that do
  exist today.
- The reseed dataset is quiz + versions + PDFs (+ optionally a fixture
  submission) — a richer end-to-end seed waits for the Phase 7 pipeline.

## Stop-and-ask check (CLAUDE.md rule 5)

None. Phase 12 touches ops scripts, compose, CI, and docs — not the scoring
formula, not Appendix A columns, not `config/sheet_template.json`.

## Environment

Postgres + the `docker` runtime. This session: `docker run -d -p
127.0.0.1:5433:5432 -e POSTGRES_PASSWORD=dev --name qs-pg8 postgres:16`; compose
work uses `deploy/.env` with `APP_PORT=8010`, `PG_PORT=5434` (5432 is unrelated
Supabase containers on this box).

---

## Subtask 12.1 — Zero-LLM source scan (R8.3)

**Goal.** A CI-run test that fails if any LLM dependency or call is introduced on
the grading path.

**Deliverables.**
- `tests/test_no_llm_on_grading_path.py`:
  - walks `app/**/*.py` + `scripts/**/*.py` + `pyproject.toml`;
  - flags: imports / requirements matching `openai`, `anthropic`, `cohere`,
    `google.generativeai` / `google-genai`, `mistralai`, `litellm`,
    `llama_cpp`, `transformers`, `langchain*`, `ollama`, `replicate`,
    `huggingface_hub`; the string `sk-` followed by base62 (API-key shape);
    URLs `api.openai.com` / `api.anthropic.com` / `generativelanguage.googleapis.com`;
  - **exception**: any path under `app/omr/readingsuggester/` is exempt
    (§5 Phase 10 — the one bounded aid, built later behind an off-by-default
    flag). The exemption is a single named constant so it's greppable.
  - a **self-test**: the detector, run over a synthetic string containing
    `import openai`, returns a hit (so a broken detector can't pass silently).
- The test is plain `pytest` (no DB) so it runs in the `lint`/`test` CI jobs and
  in `scripts/ci.sh`.

**Definition of Done (runnable).**
1. `pytest tests/test_no_llm_on_grading_path.py -q` → passes on the current tree.
2. The self-test asserts the detector flags `import openai` in a fixture string.
3. Temporarily add `import openai  # noqa` to a scratch file under `app/` →
   `pytest` fails; remove it → passes. (Done by hand during the subtask, noted in
   PROGRESS.)

---

## Subtask 12.2 — Backup + restore scripts (R8.2)

**Goal.** `deploy/backup.sh` and `deploy/restore.sh` — parametrised, no hardcoded
credentials, work against the compose stack.

**Deliverables.**
- `deploy/backup.sh`:
  - reads `deploy/.env` (or env); target dir `${BACKUP_DIR:-deploy/backups}`.
  - `pg_dump -Fc` (custom format) of the database → `<BACKUP_DIR>/<ts>/db.dump`,
    run **inside the `postgres` container** (`docker compose … exec -T postgres
    pg_dump`) so no host `postgresql-client` is needed; a `--local` flag uses a
    host `pg_dump` against `DATABASE_URL` instead.
  - `tar czf <BACKUP_DIR>/<ts>/blob.tar.gz` of the blob store (from the
    `blobstore` volume via `docker compose … cp` or `exec tar`).
  - writes `<ts>/manifest.txt` (git SHA, `template_version`, row counts for
    `quiz` / `version` / `submission`, dump + archive sizes).
  - prints the backup path; exits non-zero on any step failure (`set -euo
    pipefail`).
- `deploy/restore.sh <backup-dir-or-timestamp>`:
  - **refuses without `--yes`** (destructive: `pg_restore --clean --if-exists`
    drops and recreates objects; blob extract overwrites).
  - `pg_restore --clean --if-exists --no-owner` of `db.dump` into the database;
    extract `blob.tar.gz` into the blob store.
  - re-runs `manage.py migrate --check` after restore and fails if the schema
    isn't at head.
- `.gitignore`: add `deploy/backups/`.
- `deploy/.env.example`: add `BACKUP_DIR` with a comment.

**Definition of Done (runnable).**
1. `bash deploy/backup.sh` against a running compose stack → creates
   `deploy/backups/<ts>/{db.dump,blob.tar.gz,manifest.txt}`, all non-empty;
   manifest row counts match `manage.py shell` counts.
2. `bash deploy/restore.sh <ts>` without `--yes` → refuses, exit non-zero,
   nothing changed.
3. `shellcheck deploy/backup.sh deploy/restore.sh` clean (or documented
   suppressions).

---

## Subtask 12.3 — Tested backup → wipe → restore round-trip (R8.2)

**Goal.** Prove restore actually restores — the spec's "tested, not assumed".

**Deliverables.**
- `scripts/seed_demo.py` — idempotent-ish seeder: creates a demo `Professor`
  (`demo@example.com` / a known password), one `Quiz` with N questions ingested
  from an in-memory xlsx, `generate_versions_for_quiz(quiz, 3)`, and
  `render_and_store_version_pdfs` for each version. Prints a summary
  (professor email, quiz id, version ids, PDF paths). Used by both the runbook's
  "wipe-and-reseed" and this test.
- `scripts/check_backup_restore.sh` — the round-trip, against a disposable
  `postgres:16` (like `scripts/ci.sh`):
  1. `migrate` + `python scripts/seed_demo.py`;
  2. record: quiz count, each version's `question_order` / `option_order` /
     `qr_id`, and the SHA-256 of every stored PDF;
  3. `deploy/backup.sh --local`;
  4. **wipe**: `DROP DATABASE` + recreate + `migrate` to an empty schema; delete
     the blob dir contents;
  5. `deploy/restore.sh --yes --local <ts>`;
  6. re-record and **assert every value from step 2 is identical** — especially
     the immutable version maps and the PDF SHAs (R2.7 data is irreplaceable);
  7. exit 0 only on a full match.

**Definition of Done (runnable).**
1. `bash scripts/check_backup_restore.sh` → `RESTORE VERIFIED` (exit 0): quiz +
   3 versions + 6 PDFs restored; every `qr_id` / shuffle map / PDF SHA matches
   pre-backup.
2. A deliberate corruption (e.g. `truncate` the dump) → the script fails loudly
   at restore or verification, never a false "verified".

---

## Subtask 12.4 — One-command bring-up + in-container checks

**Goal.** `docker compose up` works from a clean laptop, static included.

**Deliverables.**
- No compose/Dockerfile change expected; if `collectstatic` (now non-`|| true`,
  Phase 8.6) needs a writable `STATIC_ROOT`, confirm `/app/staticfiles` is
  `chown`ed (it is) and the manifest is generated at boot.
- `deploy/.env.example` — final pass (SECRET_KEY generation line, `APP_PORT`,
  `PG_PORT`, `BACKUP_DIR`, worker counts).

**Definition of Done (runnable), from a clean slate (`down -v` first):**
1. `docker compose --env-file deploy/.env -f deploy/docker-compose.yml up -d --build`
   → postgres healthy → app healthy → worker running, no traceback in
   `logs worker`.
2. `curl -fsS http://localhost:8010/healthz` → `{"status": "ok"}` HTTP 200.
3. `curl -fsS http://localhost:8010/static/web/app.css` → 200, CSS body
   (WhiteNoise serving the collected static under `DEBUG=0`).
4. `docker compose … exec app python manage.py migrate --check` → exit 0.
5. `docker compose … exec app python -c "from app.sheet_template import
   load_template; print(load_template())"` → prints the v2 `SheetTemplate`
   (the still-owed in-container Phase 1.4 check).
6. `docker compose … down -v` → volumes + network removed.

---

## Subtask 12.5 — Ops runbook + CI wiring + phase close

**Deliverables.**
- `deploy/RUNBOOK.md`:
  - **First run** — clone, `cp deploy/.env.example deploy/.env`, generate
    `SECRET_KEY`, `docker compose … up -d --build`, create a superuser
    (`docker compose … exec app python manage.py createsuperuser`).
  - **Everyday** — `logs`, `restart`, where data lives (`pgdata`, `blobstore`
    volumes).
  - **Backup** — `bash deploy/backup.sh`; what lands where; a commented cron
    suggestion (not wired — §6).
  - **Restore** — `bash deploy/restore.sh --yes <ts>`; how to verify
    (`scripts/check_backup_restore.sh` idea, or manual spot-check).
  - **Wipe & reseed** — `down -v` → `up` → `python scripts/seed_demo.py`.
  - **Troubleshooting** — Windows WinNAT port-range binds
    (`netsh … excludedportrange`), the worker/migrate ordering, Docker Desktop
    wedged → the podman fallback (`CI_RUNTIME=podman`), `APP_PORT` default 8010.
  - Every command in it must be one actually run during this phase.
- `.github/workflows/ci.yml` + `scripts/ci.sh`: the R8.3 scan runs via `pytest`
  already; add a `backup-restore` step to `scripts/ci.sh` that runs
  `scripts/check_backup_restore.sh` (CI job optional — heavy; at minimum
  `scripts/ci.sh` covers it locally).
- `README.md` — link `deploy/RUNBOOK.md` from a new "Run it" section.

**Definition of Done (runnable).**
1. `bash scripts/ci.sh` → `ALL GREEN` including the backup/restore round-trip.
2. `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"` OK
   if the workflow is edited.
3. Every fenced command in `deploy/RUNBOOK.md` has been executed this phase and
   its result noted in PROGRESS.

---

## Phase 12 exit checklist

- [x] 12.1 zero-LLM source scan (R8.3) — passes, self-tested, catches a planted import  (6b159f2)
- [x] 12.2 `backup.sh` / `restore.sh` — parametrised, no creds, `--yes` gate on restore  (6f97f4b)
- [x] 12.3 tested round-trip — seed → backup → wipe → restore → byte-identical (R8.2)  (8c02d6c)
- [x] 12.4 `docker compose up` clean-slate → app + static + worker healthy; in-container 1.4 check  (f606fa1)
- [x] 12.5 `deploy/RUNBOOK.md` + CI wiring (`backup-restore` job + `scripts/ci.sh` step) + README link
- [x] `scripts/ci.sh` green with the round-trip; full suite green (335)
- [x] `docs/PROGRESS.md` entry per subtask, one commit each

**Phase 12 complete** (2026-09-10). Worked ahead of Phases 5.2–7 / 10 / 11 (all
corpus- or pipeline-blocked). Remaining for a later pass once Phase 7 lands: the
scan-image half of R8.2 exercised with real scans, and a richer reseed dataset.
Physical proof-print of `build/proof_*.pdf` (F1) is still a user task.

**Note on order:** Phase 12 is worked ahead of Phases 5.2–7 / 10 / 11, which are
all blocked on the Phase 0.7 corpus or the scan pipeline. Same sanctioned
parallel-track rationale as Phases 8–9. The scan-image half of R8.2 and a richer
reseed dataset are finished when Phase 7 lands.
