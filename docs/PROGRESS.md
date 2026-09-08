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

**Commit:** _(this commit)_
