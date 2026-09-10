# quizscanapp — Exam Version Generator & Scanner

A professor uploads MCQ questions once; the system produces N shuffled paper versions
and print-ready OMR answer sheets, then reads photographed/scanned completed sheets,
un-shuffles them to the canonical key, grades against a configurable marking scheme,
and shows a results dashboard with a review queue for anything it was unsure about.

**Single source of truth:** [`docs/REBUILD_SPEC.md`](docs/REBUILD_SPEC.md).
**Working rules:** [`docs/CLAUDE.md`](docs/CLAUDE.md).
**Phase plan / progress:** [`docs/phases/`](docs/phases/), [`docs/PROGRESS.md`](docs/PROGRESS.md).

Stack: Django monolith + server-rendered templates, Postgres, classical OpenCV/pyzbar
OMR (no LLM on the grading path), Django-Q2 background jobs, one `docker-compose`
(app + postgres) on `localhost`.

## Dev quickstart

```
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"     # Windows
.venv/Scripts/ruff check .
.venv/Scripts/python -m pytest -q
```

## Run it

```
cp deploy/.env.example deploy/.env      # then set a real SECRET_KEY
docker compose --env-file deploy/.env -f deploy/docker-compose.yml up -d --build
```

App on `http://localhost:${APP_PORT}` (default 8010). First run, backup/restore,
wipe-and-reseed, and troubleshooting: **[`deploy/RUNBOOK.md`](deploy/RUNBOOK.md)**.
