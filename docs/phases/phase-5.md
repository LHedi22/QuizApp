# Phase 5 — Alignment on real captures

> Source: `docs/REBUILD_SPEC.md` §5 (Phases table, row 5), §2 R5.1–R5.3, §4
> "Design principles for the rebuild" (1–4, 6), §6 Q18. Governing rules:
> `docs/CLAUDE.md` (esp. rules 7 and 9).

## Phase goal

Given a page image, locate the registration perimeter, compute a perspective
transform to canonical answer-sheet geometry, decode the QR **from the rectified
image**, and hand downstream (Phase 6) rectified bubble-grid crop coordinates —
**or** return a clean, specific failure. A silent wrong fit is the one outcome that
is never acceptable (R5.3, "the single most important requirement in the document").

Everything in `app/omr/` is **pure** (rule 7): `numpy` / `opencv` / `app.sheet_template`
only, no Django.

## ⚠ Rule 9 — the corpus is the measurement standard

**Status (2026-09-11): the Phase 0.7 corpus now exists and passes its gate**
(`python scripts/check_corpus.py` exits 0 — 20 phone photos, 5 each of
sheet_a/b/c/d, `corpus/labels/*.json`). Per `CLAUDE.md` rule 9, no OMR DoD may
be signed off against synthetic images; 5.2–5.5 below may now be started against
this corpus. Two things any future session must know before touching 5.2–5.5:

- **The corpus has no upside-down/reversed/copier-scan/photocopied images —
  by deliberate user decision**, not an oversight (see `docs/PROGRESS.md`
  2026-09-11 "update 3"/"update 4"). REBUILD_SPEC.md's own text (R5.2, §6 Q18)
  still says the near-180° detect-vs-clean-failure choice should be "decided
  during Phase 5 based on what the corpus shows" — that can't happen here since
  there's no upside-down corpus evidence. **The user already made this call
  directly: implement the clean-specific-failure path only (no detect-and-correct
  attempt for near-180°/upside-down) — do not spend effort on 180°-orientation
  detection/correction.** The aligner must still never produce a *silent* wrong
  fit on such an input; it just doesn't need to succeed on one.
  `resolve_page_orientation` (5.1) already resolves the ±20° in-plane case via
  QR-corner asymmetry — that stays as-is; this note is only about the *separate*
  near-180° case.
  `marked_options` in every label is AI-transcribed, not independently verified —
  spot-check before using a given sheet as scoring ground truth in 6+.
- Real noise magnitudes, the actual numeric fit-quality gate threshold, and
  every accuracy/tolerance number for 5.2–5.5 should still be derived from this
  corpus's actual phone photos — that part of the original rule 9 intent is
  unchanged.

- **5.1 — solver core (DONE, see below).** The projective math: normalized-DLT
  homography, over-determined robust fit, absolute fit-quality gate, orientation
  resolution, grid projection. Corpus-independent because it is linear algebra with
  *known* ground-truth transforms — the corpus never had a role in verifying a
  homography solver. Tested against programmatically generated transforms
  (rotation ≤ ±20°, keystone, scale, framing) with analytic ground truth.
- **5.2–5.5 — corpus-gated, now UNBLOCKED (not yet started).** The image→points
  front-end (perimeter detection, adaptive threshold, contour/blob extraction),
  the real noise magnitudes, the actual numeric gate threshold, and every
  accuracy/tolerance number, measured against the corpus above. The near-180°
  question itself is no longer open — see the bullet above. **Confirm scope with
  the user before starting** (this is a substantial new phase, not a small
  follow-on) rather than launching straight into implementation.

## What Phase 5 does NOT do

- No bubble classification (filled/empty/ambiguous) — Phase 6.
- No scoring, no persistence, no submission rows — Phase 7.
- No batch/PDF intake — Phase 7 (R5.4).
- 5.1 writes **no** image-processing front-end. `detect_registration_marks(image)`
  is Phase 5.2 and is corpus-gated.

## Registration-point strategy (design principle 3: "≥ 6 points, not 4")

The initial fit cannot use the per-row/per-column timing marks — those depend on
(question count, N), which is unknown until the QR is decoded (R5.1 step 3). So:

- **Stage A — coarse (version-independent).** 4 corner fiducials + the 3 QR finder
  patterns (fixed canonical positions from `geometry.qr`) = **7 points**. Enough to
  rectify well enough to decode the QR.
- **Stage B — fine (version-known).** After the QR gives the version → question
  count + N → the full timing-mark set (4 fiducials + one tick per bubble row down
  both edges + one per option column across the top, all from `bubble_centres` /
  the grid geometry) = dozens of points. This over-determined fit carries the
  **absolute quality gate** and drives the Phase 6 bubble crops.

Both stages call the same `fit_homography_robust`. Stage B's point set is built by a
helper over the template geometry. **No geometry/`sheet_template.json` change is
needed for this** — if the corpus later shows Stage A is too weak, adding a fixed
version-independent edge ruler is a `template_version` bump and a `CLAUDE.md` rule 5
sign-off, not a Phase 5 code decision.

---

## Subtask 5.1 — Solver core (`app/omr/geometry.py`)  ← buildable now

**Goal.** A projective-geometry toolkit with an honest fit-quality signal, verified
against analytic ground truth.

**Deliverables.**
- `app/omr/geometry.py` (pure: `numpy`, no `cv2` needed here):
  - `homography_dlt(src, dst) -> (3,3)` — Hartley-normalized DLT + SVD; ≥ 4
    correspondences; exact (residual ≈ 0) for a clean projective map.
  - `apply_homography(H, pts) -> (N,2)`; `invert_homography(H)`.
  - `reprojection_error(H, src, dst) -> (N,)` — per-point Euclidean px error in
    `dst` space.
  - `HomographyFit` (frozen): `H`, `rms_px`, `max_px`, `n_points`, `n_inliers`,
    `inlier_mask`.
  - `AlignmentError(reason)` with `reason ∈ {marks_not_found, fit_quality,
    ambiguous_orientation}` (str enum) — the clean-failure channel (R5.3).
  - `fit_homography_robust(src, dst, *, gate_rms_px, gate_max_px, min_inliers,
    ransac_iters=200, rng=...) -> HomographyFit` — deterministic seeded RANSAC over
    4-point minimal samples, refit DLT on the inlier set, raise
    `AlignmentError("fit_quality")` if `rms/max` exceed the gate or inliers <
    `min_inliers`.
  - `resolve_page_orientation(detected_quad, canonical_quad, *, asym_canonical,
    asym_detected, margin_px) -> int` — returns 0/90/180/270; the rotation whose
    fit maps `asym_canonical` nearest `asym_detected`; raise
    `AlignmentError("ambiguous_orientation")` if the best two rotations are within
    `margin_px`.
  - `project_points_mm(H, points_mm) -> (N,2)` — canonical-mm → image-px convenience
    (H is defined canonical-mm → image-px throughout Phase 5).
- `tests/test_omr_geometry.py` (pure, no DB).

**Definition of Done (runnable).**
`pytest tests/test_omr_geometry.py -q` and `pytest tests/test_purity.py -q`:
1. **Exactness.** Random projective `H_true` (rotation ≤ 20°, keystone up to a
   realistic hand-held tilt, scale 0.4–1.0× frame, translation); project the 7
   Stage-A canonical points; `homography_dlt` recovers `H` with reprojection RMS
   < 1e-6 px and canonical bubble-grid centres within 1e-6 px of the true
   projected centres.
2. **Noise.** Add Gaussian σ = 1.5 px to the detected points → recovered fit maps
   the full bubble grid within < 3 px everywhere; `rms_px` is in a sane band.
3. **Robustness.** Inject 1–2 gross outliers (a mis-detected mark, 40 px off) into
   an otherwise-clean 12-point set → RANSAC flags them (`inlier_mask` false),
   final fit still < 2 px. Inject 6/12 gross outliers → `AlignmentError(fit_quality)`.
4. **Occlusion.** Drop points to 5/7 → still fits within tolerance; drop to 3 →
   `AlignmentError` (DLT needs 4; `min_inliers` guards the rest).
5. **Orientation.** Relabel the detected quad by a true 180° rotation →
   `resolve_page_orientation` returns 180 and the subsequent fit is within
   tolerance. A symmetric/garbled quad (no asymmetry signal) →
   `AlignmentError(ambiguous_orientation)`.
6. **Gate direction.** A deliberately bad correspondence set (residual >> gate)
   raises `AlignmentError(fit_quality)` — never returns a low-quality `HomographyFit`.
7. `app.omr` still imports with zero web-framework modules.

**Explicitly deferred to the corpus (write in PROGRESS.md, do not fake):** the
numeric values of `gate_rms_px` / `gate_max_px` / `min_inliers` / the σ that real
detection produces. 5.1 uses provisional constants and its tests assert *behaviour
relative to the gate*, not that the gate value is correct.

---

## Subtask 5.2 — Perimeter detection front-end (`app/omr/detect.py`)  ← DONE 2026-09-11

**Goal.** Turn a captured photo into the Stage-A correspondence set (mm ↔ px point
pairs) that `fit_homography_robust` (5.1) needs — the "image → points" half that
5.1 explicitly deferred.

**Design deviation from the original plan (documented, not silent):** Stage A is
**4 fiducials + the QR's own 4 corners (8 points)**, not "4 fiducials + 3 QR
finder-pattern centres (7 points)" as originally sketched. `pyzbar` already does
finder-pattern-level detection internally as part of decoding — using its returned
QR polygon directly is more robust than hand-rolling a 3-finder-pattern ratio
scanner, and yields one extra point. `cv2.QRCodeDetector` (tried first) was
unreliable on real photos at this resolution — 1/20 on the corpus, and that one hit
was a false positive. `pyzbar` decoded 20/20 correctly.

**Correspondence ordering.** Neither `pyzbar`'s polygon nor the fiducial contours
carry known corner identity by themselves. Both are resolved via nearest-corner
heuristics (nearest detected fiducial to each image corner; nearest QR-polygon
point to the detected top-left fiducial) — safe under the ±20° in-plane rotation
R5.1 targets, and **cross-validated against all 20 real corpus photos**: in every
one, the QR's centroid sits ~7-8x closer to the fiducial identified as top-left
than to any other detected fiducial (200-260px vs. 1600-3700px, on a ~5000px image
diagonal). A near-90°-rotated capture could break this heuristic — out of scope for
this corpus (none exist in it) and caught downstream by the absolute fit-quality
gate rather than silently mis-aligning (R5.3).

**Deliverables.**
- `app/omr/detect.py` (pure: `cv2`, `numpy`, `qrcode`, `pyzbar`, `app.sheet_template`
  — no Django, rule 7):
  - `canonical_fiducial_corners_mm(template)` / `canonical_qr_corners_mm(template)` —
    the mm-space Stage-A targets. The QR corners are computed from the actual
    `qrcode` render (module count 33, border 2, for the fixed-length UUID `qr_id`
    content) to exclude the quiet-zone the PDF renderer bakes into the QR image,
    not guessed.
  - `detect_fiducials(image) -> (4,2) px | None` — adaptive-threshold → contour
    filter (convex, near-square, high-solidity, page-relative area band) → nearest
    detected candidate to each of the 4 image corners.
  - `detect_qr(image, *, top_left_fiducial_px) -> (text, (4,2) px) | (None, None)` —
    `pyzbar` decode, polygon ordered via nearest-to-top-left-fiducial.
  - `detect_stage_a(image, template) -> StageACorrespondences` — combines both;
    raises `AlignmentError('marks_not_found')` if either half fails (R5.3 clean
    failure, never a partial guess).
- `tests/test_omr_detect.py`: pure/structural tests (canonical-geometry math,
  blank-image failure paths) + **`test_stage_a_detection_on_real_corpus_capture`**,
  parametrized over all 20 real `corpus/images/*.jpg` + their labels (rule 9) — a
  regression guard against `corpus/images` silently going empty/unlabeled.

**Definition of Done (runnable, against the real corpus).**
`pytest tests/test_omr_detect.py -q` — **26/26 pass**, including, for **all 20/20**
real corpus photos:
1. `detect_stage_a` finds both fiducials and QR (no `marks_not_found`).
2. The decoded QR text equals that photo's `sheet_token` label — an
   unambiguous, ground-truth-independent correctness signal.
3. `fit_homography_robust` on the resulting 8 points succeeds with **all 8/8
   inliers** (provisional gate: `rms_px<=12, max_px<=25, min_inliers=6` —
   generous headroom; observed on the corpus was rms 1.3-3.0px, max 1.9-5.4px on
   3024x4032-px photos).
`pytest tests/test_purity.py -q` — `app.omr` still imports with zero
web-framework modules.

**Explicitly deferred to 5.5:** a formally-written reliability budget (this
subtask's 20/20 is a strong real signal but 20 photos, 2 capture sessions, is not
the full "dozens... indoor lighting variety" corpus R5.2 envisioned — see
`docs/PROGRESS.md` 2026-09-11 for why the corpus stopped at 20 phone-only images).

## Subtask 5.3 — Two-stage alignment orchestration (`app/omr/alignment.py`)  ← DONE 2026-09-11

**Goal.** Stage A (5.2) → version lookup → Stage B (version-specific timing-mark
grid) → `PageAlignment`, or a clean `AlignmentError` (R5.3). This is where the
"coarse then fine" registration strategy (design principle 3) actually pays off:
Stage A gets close enough to identify the sheet, Stage B refines against dozens of
timing marks for the precision Phase 6's bubble crops need.

**Design decisions (documented, not silent deviations):**
- **No separate "rectify-then-decode" step.** R5.1 step 2 says "decodes the QR
  from the rectified image," but 5.2 already showed `pyzbar` decodes reliably
  straight from the raw photo (20/20 on the corpus) — `align_page` reuses that
  decode instead of warping the page and re-decoding, avoiding interpolation-blur
  risk for no measured benefit.
- **Version lookup is injected** (`version_lookup: Callable[[str], VersionGeometry
  | None]`), not looked up from the DB in this module. R5.1 step 3 ("looks up the
  version") is a real DB read in production, which can't live in `app/omr` (rule
  7). Phase 7 wires in the real `Version.qr_id` lookup; this module (and its
  tests) use a lookup built from `corpus/_source/*.meta.json` instead.
- **`AlignmentError` gained a 4th reason, `version_not_found`** (in
  `app.omr.geometry`, not duplicated locally) — a QR that decodes cleanly but
  isn't a known version is a real failure mode the original 3 fit-quality-only
  reasons didn't cover.
- **Stage B never re-detects fiducials** — reuses Stage A's already-precise
  detection, only newly detects the version-specific timing ticks (one per bubble
  row on both edges + one per option column, `canonical_stage_b_ticks_mm`,
  matches `_draw_timing_marks` in `app/pdf/answer_sheet.py` exactly). Each tick is
  found via a **local-window search**: Stage A's homography predicts roughly
  where a tick should be; a small window (3mm radius) around that prediction is
  Otsu-thresholded and searched for a plausibly-tick-sized dark blob. **100% (655/655)
  ticks found across all 20 real corpus photos** during development — Stage A's
  predictions were consistently accurate to a few px, well inside the search
  window.

**Deliverables.**
- `app/omr/alignment.py` (pure: `cv2`, `numpy`, `app.omr.detect`,
  `app.omr.geometry`, `app.sheet_template` — no Django, rule 7):
  - `VersionGeometry` (`num_questions`, `n_options`) — the injected lookup's
    return type.
  - `PageAlignment` (`H`, `qr_text`, `num_questions`, `n_options`,
    `stage_a_fit`, `stage_b_fit`) — the phase deliverable. `H` maps
    canonical-mm → **source-image** px directly; no page warp is ever
    materialized (Phase 6 crops bubbles straight from the original photo via
    `project_points_mm(H, bubble_mm)`).
  - `canonical_stage_b_ticks_mm(template, num_questions, n_options)`.
  - `detect_stage_b(gray, template, *, ..., stage_a_H) -> (mm, px)` — the matched
    correspondence set (fiducials + found ticks); raises
    `AlignmentError('marks_not_found')` if fewer than half the expected ticks are
    found (not enough signal for a meaningful Stage-B fit).
  - `align_page(image, template, *, version_lookup) -> PageAlignment` — the full
    orchestration.
- `tests/test_omr_alignment.py`: pure/structural tests + real-corpus DoD tests
  parametrized over all 20 labeled `corpus/images/*.jpg` (rule 9).

**Definition of Done (runnable, against the real corpus).**
`pytest tests/test_omr_alignment.py -q` — **43/43 pass**, including for all
**20/20** real corpus photos:
1. `align_page` succeeds (no `AlignmentError`) and returns a `PageAlignment`
   whose `qr_text`/`num_questions`/`n_options` match that photo's label/source
   meta exactly.
2. Stage B matches at least 90% of the expected timing ticks (plus the 4
   fiducials) — not just squeaking past the raw gate.
3. `stage_b_fit.rms_px` is within the provisional gate (`<=12px` on
   3024x4032-px photos).
4. The final `H` places the canonical bubble-grid centre sensibly inside the
   actual photo frame (a coarse degeneracy check).
5. A separate regression test confirms Stage B's rms is never meaningfully worse
   than Stage A's on any of the 20 photos (the two-stage design should earn its
   complexity, not just add it).
Plus structural failure-path tests (blank image → `marks_not_found`; an unknown
QR via a lookup returning `None` → `version_not_found`).
`pytest tests/test_purity.py -q` — `app.omr` still zero-Django.
`pytest -m "not django_db" -q` → **286 passed** (was 243).

**Explicitly deferred to 5.4/5.5:** actual bubble-crop coordinates (5.4) and the
formally-written reliability budget (5.5) — this subtask's 20/20 is real signal
but from a 20-photo, 2-session corpus, not the fuller corpus R5.2 originally
envisioned (see `docs/PROGRESS.md` 2026-09-11 for why).

## Subtasks 5.4–5.5 — not yet started

- **5.4 — Bubble-grid rectification**: `PageAlignment` + version → per-(question,
  option) crop boxes in the source image, within tolerance across the corpus.
- **5.5 — Reliability budget gate** (§5 process change 2): measured alignment
  success / clean-failure / wrong-fit rates on the corpus vs. a written bar in
  PROGRESS.md; a shortfall is documented and user-accepted, not worked around.

## Phase 5 exit checklist

- [x] 5.1 solver core — test_omr_geometry.py green (16), purity green, 200 non-DB tests pass
- [x] 5.2 perimeter detection — test_omr_detect.py green (26), 20/20 real corpus photos: fiducials+QR found, QR text matches label, homography fit 8/8 inliers
- [x] 5.3 two-stage alignment — test_omr_alignment.py green (43), 20/20 real corpus photos: PageAlignment correct, Stage B >=90% ticks matched, rms within gate, Stage B not worse than Stage A. R5.2 orientation decision already made (clean-failure only).
- [ ] 5.4 bubble-grid rectification within tolerance (corpus)
- [ ] 5.5 reliability budget recorded + accepted (corpus)
- [ ] `scripts/ci.sh` green
