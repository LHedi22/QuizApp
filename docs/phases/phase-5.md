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

**The real-capture corpus (Phase 0.7) does not exist yet** (no printer). Per
`CLAUDE.md` rule 9, no OMR DoD may be signed off against synthetic images. This
splits Phase 5 into:

- **5.1 — solver core (buildable now).** The projective math: normalized-DLT
  homography, over-determined robust fit, absolute fit-quality gate, orientation
  resolution, grid projection. Corpus-independent because it is linear algebra with
  *known* ground-truth transforms — the corpus never had a role in verifying a
  homography solver. Tested against programmatically generated transforms
  (rotation ≤ ±20°, keystone, scale, framing) with analytic ground truth.
- **5.2–5.5 — corpus-gated (BLOCKED).** The image→points front-end (perimeter
  detection, adaptive threshold, contour/blob extraction), the real noise
  magnitudes, the actual numeric gate threshold, the near-180° decision (R5.2:
  detect-and-correct vs. clean-specific-failure — "decided during Phase 5 based on
  what the corpus shows"), and every accuracy/tolerance number. **Do not start
  these without the corpus. Stop and ask.**

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

## Subtasks 5.2–5.5 — BLOCKED on the Phase 0.7 corpus

Written out only so the plan is visible; **not to be started without the corpus**.

- **5.2 — Perimeter detection front-end** (`app/omr/detect.py`): grayscale →
  scale-invariant fiducial + QR-finder detection → ordered correspondence set.
  cv2. DoD measured on the corpus.
- **5.3 — Two-stage alignment orchestration** (`app/omr/alignment.py`): Stage A →
  rectify → `pyzbar` decode → Stage B → `PageAlignment` or `AlignmentError`.
  Includes the R5.2 near-180° decision.
- **5.4 — Bubble-grid rectification**: `PageAlignment` + version → per-(question,
  option) crop boxes in the source image, within tolerance across the corpus.
- **5.5 — Reliability budget gate** (§5 process change 2): measured alignment
  success / clean-failure / wrong-fit rates on the corpus vs. a written bar in
  PROGRESS.md; a shortfall is documented and user-accepted, not worked around.

## Phase 5 exit checklist

- [x] 5.1 solver core — test_omr_geometry.py green (16), purity green, 200 non-DB tests pass
- [ ] 5.2 perimeter detection (corpus)
- [ ] 5.3 two-stage alignment + R5.2 orientation decision (corpus)
- [ ] 5.4 bubble-grid rectification within tolerance (corpus)
- [ ] 5.5 reliability budget recorded + accepted (corpus)
- [ ] `scripts/ci.sh` green
