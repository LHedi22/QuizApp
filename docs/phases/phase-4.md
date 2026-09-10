# Phase 4 — PDF output

> Source: `docs/REBUILD_SPEC.md` §5 (Phases table, row 4), §2 R3.1–R3.4, §3.2, §3.2A,
> §3.3 (design principles). Governing rules: `docs/CLAUDE.md` (esp. rule 5).

## Phase goal

Render, for each version, the two print artifacts:
1. a **generic single-page A4 OMR answer sheet** — bubble grid + full registration
   perimeter + QR(`qr_id`) + a human-readable page identifier, *generic per
   (question count, N)* (R3.1, R3.3);
2. a **question paper** — the version's questions in shuffled order with their
   shuffled options, human-readable, no bubbles (R3.1).

Renders are **deterministic / byte-identical** (R3.4) and stored behind a thin
storage interface, cache-keyed by `template_version` so a template bump busts the
cache (§3.3 principle 6).

## ⚠ Answer-sheet geometry needs sign-off (CLAUDE.md rule 5)

Phase 4 extends `config/sheet_template.json` from v1 (numbers only) to **v2** with the
full answer-sheet geometry — fiducials, timing marks, QR box, bubble-grid layout.
That is answer-sheet geometry: see "Decision for sign-off" below. Nothing is built
until the numbers are approved.

## What Phase 4 does NOT do

- No "mark printed" control — `version.printed_at` / `quiz.status → printed` is the
  **Phase 9** per-version control (R3.5). Phase 4 only produces paper.
- No OMR (Phase 5+). But the geometry Phase 4 writes is the *same file* the OMR
  pipeline will read for bubble crops (R3.3) — computed via one shared function,
  never re-derived.
- No physical proof-print. Phase 4 produces a **proof PDF**; the user prints it and
  confirms single-page fit + bubble alignment + QR scan. Any ≤15% adjustment to the
  capacity numbers (R3.2) is a follow-up `template_version` bump after that.
- WeasyPrint is **not** added (heavy native deps on Windows). The question paper uses
  ReportLab Platypus (§3.2 explicitly allows this "if you'd rather not add a
  dependency").

## Environment note

No DB needed for 4.1–4.3 (pure render + geometry). 4.4 (storage) uses `MEDIA_ROOT`
and, for the version round-trip test, Postgres.

---

## Subtask 4.1 — `sheet_template.json` v2 + geometry loader + `bubble_centres()`

**Goal.** One machine-readable geometry both the renderer (4.2) and the future OMR
pipeline read. Compact config + a shared function that computes every bubble centre.

**Deliverables.**
- `config/sheet_template.json` → `template_version: 2`, unchanged `page` +
  `question_paper` + `answer_sheet.capacity_by_n`, **new** `answer_sheet.geometry`
  block (values per "Decision for sign-off").
- `app/sheet_template.py` extended:
  - `SheetTemplate` gains a `geometry` field (nested frozen dataclass);
    `_validate` checks it (positive dims, columns cover N=2..6, grid band inside the
    page).
  - `bubble_centres(template, num_questions, n_options) -> dict[int, list[tuple[float, float]]]`
    — 1-based question → `[(x_mm, y_mm)]` per option, top-left origin. Fills column
    blocks top-to-bottom then left-to-right; **row pitch is computed** to fit
    `num_questions` on one page (clamped to `[min_row_pitch, max_row_pitch]`).
  - `fits_on_one_page(template, num_questions, n_options) -> bool` and
    `OverCapacityError` — raised when the clamped row pitch would fall below
    `min_row_pitch_mm`.
- `tests/test_sheet_geometry.py` (pure).

**Definition of Done (runnable).**
1. `pytest tests/test_sheet_geometry.py -q`:
   - v2 loads + validates; `template_version == 2`;
   - `bubble_centres` returns exactly `n_options` centres for every question
     `1..num_questions`, all within `[margin, page-margin]` in both axes, for the
     **capacity-limit** quiz of each N (120/120/120/100/80) and for small quizzes
     (1, 5, 40 questions);
   - centres are strictly ordered (no two bubbles overlap: pairwise distance ≥
     `bubble_diameter_mm`);
   - `num_questions = capacity + 1` → `OverCapacityError`;
   - deterministic (same inputs → identical output).
2. `pytest tests/test_sheet_template.py` updated for v2 and still green.
3. Purity test still green (loader stays Django-free).

---

## Subtask 4.2 — Answer sheet renderer (`app/pdf/answer_sheet.py`)

**Goal.** The generic OMR sheet, drawn to exact coordinates from the geometry, QR
decodable after scan-degradation, byte-identical every render.

**Deliverables.**
- `app/pdf/answer_sheet.py`:
  - `render_answer_sheet(*, num_questions, n_options, qr_id, page_label,
    template=None) -> bytes` — ReportLab canvas in **invariant mode** (fixed
    date/ID → deterministic).
  - Draws: 4 corner fiducials (solid squares at the config insets); edge
    timing/registration marks on ≥ 2 sides (one per bubble row down both side edges,
    one per option column across the top); the QR (encoding `qr_id`, in the config
    box); a page identifier line (`page_label`, e.g. `"v3 · 40Q · N=4 · a1b2c3d4"`);
    the bubble grid with `Q1..Qn` row labels and `A..` column headers, bubbles as
    thin open circles at `bubble_centres`.
  - Raises `OverCapacityError` if `num_questions` exceeds `capacity_for(n_options)`.
- `tests/test_answer_sheet_render.py`.

**Definition of Done (runnable).**
1. `pytest tests/test_answer_sheet_render.py -q`:
   - two renders with the same args → **identical bytes** (R3.4);
   - QR round-trips: rasterize the PDF at ~200 DPI, **downscale + JPEG-degrade +
     add mild blur/noise**, then `pyzbar` decodes exactly `qr_id` (R3.4 — from the
     rendered page, not a standalone QR);
   - rasterize and detect the 4 fiducial blobs (dark connected components in the
     corners); their centres match the config insets within a few px at that DPI;
   - `num_questions` at capacity renders; `capacity + 1` → `OverCapacityError`;
   - N=2 and N=6 both render on one page (rasterize → content bbox height ≤ page).
2. A proof PDF (`build/proof_answer_sheet_n4_120.pdf` etc.) + PNG previews are
   generated and **sent to the user** to print and confirm.

---

## Subtask 4.3 — Question paper renderer (`app/pdf/question_paper.py`)

**Goal.** A readable paper of a version's questions, shuffled per its maps.

**Deliverables.**
- `app/pdf/question_paper.py`:
  - `render_question_paper(version, *, template=None) -> bytes` — Platypus
    `SimpleDocTemplate`, invariant/deterministic.
  - Questions in `version.question_order` sequence, numbered `1..n` (sheet order);
    each question's options in `version.option_order[str(qid)]` sequence, labelled
    `A) … B) …`; no bubbles; a small header with the version's page identifier.
  - Long option text wraps (uses `question_paper.printable_column_width_mm`); an
    option that still overflows a line is a data problem caught at ingestion (R1.4),
    not here.
- `tests/test_question_paper_render.py` (needs Postgres for a real `Version`).

**Definition of Done (runnable).**
1. `pytest tests/test_question_paper_render.py -q`:
   - renders to a valid PDF (`pymupdf` opens it, `page_count >= 1`);
   - extracted text contains every source question's text, and for a sampled
     question the options appear in `option_order` sequence (not canonical order);
   - two renders → identical bytes;
   - the question count in the text == `len(version.question_order)`.

---

## Subtask 4.4 — Storage interface + deterministic cache + cache-busting

**Goal.** Store the two PDFs on the blob volume; re-download is byte-identical and
cheap; a `template_version` bump invalidates the cache (§3.3 principle 6).

**Deliverables.**
- `app/core/blob_storage.py` — a thin interface (`save(path, data)`, `open(path)`,
  `exists(path)`, `url(path)` optional) over `MEDIA_ROOT` (the Docker `blobstore`
  volume), written so an S3/MinIO backend could replace it.
- `app/pdf/artifacts.py`:
  - `version_pdf_paths(version) -> {answer_sheet, question_paper}` — deterministic
    paths **including `version.template_version`**, e.g.
    `versions/<version_id>/tpl<template_version>/answer_sheet.pdf`.
  - `render_and_store_version_pdfs(version) -> paths` — renders + stores if absent,
    returns paths; a second call re-reads the cached bytes without re-rendering.
- `tests/test_pdf_artifacts.py` (Postgres for the `Version`).

**Definition of Done (runnable).**
1. `pytest tests/test_pdf_artifacts.py -q`:
   - first call writes exactly 2 files under `MEDIA_ROOT`; the answer sheet's bytes
     equal `render_answer_sheet(...)` output;
   - second call returns identical bytes and does **not** re-render (patch the
     renderer with a spy / assert not called, or compare mtimes);
   - bump the `Version.template_version` in the row (test-only) → `version_pdf_paths`
     changes, `render_and_store_version_pdfs` writes a new file, the old one is
     untouched and no longer referenced;
   - `blob_storage` writes under `MEDIA_ROOT`, not the repo tree.
2. `bash scripts/ci.sh` green with the Phase 4 additions (default `docker` runtime
   once Docker Desktop is healthy; `CI_RUNTIME=podman` / direct steps otherwise).

---

## Decision for sign-off

### F1 — `config/sheet_template.json` v2 geometry

Bump `template_version` **1 → 2**. `page`, `question_paper`, and
`answer_sheet.capacity_by_n` are **unchanged**. Add `answer_sheet.geometry` (all mm,
top-left origin):

| Field | Proposed | Rationale |
|---|---|---|
| `fiducial.size_mm` | 7.0 | solid square, big enough to blob-detect at 150 DPI |
| `fiducial.inset_mm` | 10.0 | centre 10 mm from each page edge → 6.5 mm quiet zone outside |
| `timing_mark.length_mm` / `thickness_mm` | 4.0 / 1.5 | ticks down both side edges (per row) + across the top (per option column) |
| `qr.x_mm` / `y_mm` / `size_mm` | 16 / 13 / 24 | top-left, clear of the top-left fiducial (which spans x,y 6.5–13.5) |
| `grid.columns_by_n` | `{2:4, 3:4, 4:4, 5:3, 6:3}` | 4-column at N≤4, 3-column at N≥5 (R3.2) |
| `grid.top_mm` / `bottom_mm` | 46 / 282 | vertical band for bubble-row centres (238 mm) |
| `grid.left_mm` | auto-centred | first column block left edge = centre the block row |
| `grid.min_row_pitch_mm` / `max_row_pitch_mm` | 6.5 / 11.0 | row pitch computed to fit `num_questions`, clamped |
| `grid.bubble_pitch_mm` | 6.0 | between option bubbles in a row (R3.2 "~6 mm") |
| `grid.bubble_diameter_mm` | 3.6 | open circle |
| `grid.label_gutter_mm` | 9.0 | room for `Q120` before the first bubble |
| `grid.column_gap_mm` | 8.0 | between column blocks |

**Single-page check** (row pitch = band ÷ (rows_per_column − 1), clamped ≥ 6.5):
- N≤4, 120 Q, 4 cols → 30 rows → pitch 8.2 mm ✓
- N=5, 100 Q, 3 cols → 34 rows → pitch 7.2 mm ✓
- N=6, 80 Q, 3 cols → 27 rows → pitch 9.2 mm ✓
- block width N=6 = 9 + 6·6 = 45 mm; 3 blocks + 2·8 gap = 151 mm < 186 mm usable ✓

**Row pitch is computed per (count, N)** — the sheet is generic per that pair (R3.1),
so a 20-question quiz gets a roomier sheet than a 120-question one; both fit one page.
The `capacity_by_n` numbers stay as R3.2 pending your proof-print; if the printed grid
needs a tweak, that's a `template_version` 3 bump (≤15%, §3.2A) — not now.

**Confirm:** the table above (especially `grid.top_mm`/`bottom_mm`, `bubble_pitch_mm`,
`bubble_diameter_mm`), and that bumping to `template_version: 2` now is right.

---

## Phase 4 exit checklist

- [x] F1 signed off 2026-09-10 (v2 geometry, template_version 2)
- [x] 4.1 geometry (commit dbb1731)
      capacity-limit quiz; `OverCapacityError` at capacity+1; deterministic
- [x] 4.2 answer sheet (commit 187e219); proof PDFs sent to user
      fiducials at config positions; N=2..6 fit one page; proof PDF sent to user
- [x] 4.3 question paper (commit 6378517)
- [x] 4.4 storage + cache (commit 37e5d10)
      bump busts it, writes under `MEDIA_ROOT`
- [x] 244 tests pass, makemigrations --check clean (podman Postgres); scripts/ci.sh on real docker runtime still owed
