# Real-capture test corpus

This directory holds **real photographs and scanner output** of physically printed
OMR sheets, with hand-labeled ground truth. It is a Phase 0 deliverable and the
measurement standard for every OMR Definition of Done from Phase 5 on
(REBUILD_SPEC.md §5, §3.3, Appendix B.5). Synthetic PDF rasterizations are only ever
a supplement — never the primary evidence.

```
corpus/
  _source/    the printed masters these captures came from — the real Phase-4
              answer sheets, committed as sheet_{a,b,c,d}_*.{pdf,png,meta.json}
              (regenerate with `python scripts/make_corpus_sheets.py`)
  images/     the captures themselves (jpg/png/tif/webp)
  labels/     one <image_stem>.json of ground truth per image  (schema: labels/SCHEMA.md)
```

**The masters are the real renderer's output** (geometry from
`config/sheet_template.json`), not the pre-Phase-4 `throwaway_v0` sheet — so a
corpus captured on them validates the actual Phase 5/6 bubble-crop geometry and QR
lookup, not just alignment. The four masters span the layout space:

| master | questions | N | grid |
|---|---|---|---|
| `sheet_a_20q_n4` | 20 | 4 | 4-column, roomy rows |
| `sheet_b_40q_n4` | 40 | 4 | 4-column, typical |
| `sheet_c_30q_n5` | 30 | 5 | 3-column |
| `sheet_d_24q_n6` | 24 | 6 | 3-column, 6 bubbles/row |

Each `.meta.json` carries its `sheet_token` (= the UUID the QR encodes),
`questions`, `options`, and the ground-truth `fiducial_centres_mm` /
`bubble_centres_mm` for Phase 5 alignment scoring.

## What to capture (subtask 0.7 — done, 2026-09-11)

**Status: complete.** `python scripts/check_corpus.py` exits 0 against the
20 real phone photos in `corpus/images/`. The thresholds below are as
**relaxed by the user on 2026-09-11** (see `docs/PROGRESS.md` and
`docs/phases/phase-0.md` 0.7) — copier/scanner capture, photocopy
generations, and upside-down/reversed orientation were judged "won't happen
in real life" for this deployment, so those buckets were dropped to 0 and
the phone-photo floor lowered to match what was actually captured:

| Bucket | Minimum (current) | Spec original | Notes |
|---|---|---|---|
| `phone_photo` | **20** | 30 | Handheld phone photos, uploaded as-is (not scanned). |
| `copier_scan` | **0** | 10 | Dropped — this deployment's sheets are always photographed, never scanned/copied. |
| `photocopy_generations >= 1` | **0** | 5 | Dropped — sheets are always filled and photographed first-generation. |
| `orientation` in `upside_down` / `reversed` | **0** | 5 | Dropped from the *corpus testing* requirement only — the aligner's clean-failure behavior on a near-180° sheet (R5.2) is still in scope, just not corpus-verified. |

`docs/REBUILD_SPEC.md` §2 R5.2 / §6 Q10/Q18 are intentionally left
**unedited** to preserve the original design rationale — `docs/PROGRESS.md`
is the authoritative record of this override, not this file or the spec
text. If you're re-capturing for a broader deployment later, the original
30/10/5/5 minimums above are still the more rigorous target.

### Capture protocol

*(This is the original, fuller protocol — phone + copier + photocopy +
upside-down. What was actually captured for this deployment was steps 1, 3,
4 only: print, fill in, photograph ≥ 20 phone photos. Kept here as the
target if the corpus is ever broadened.)*

1. **Print** the four `_source/sheet_*.pdf` masters on a laser printer (A4, **100%
   scale**, no "fit to page"). Print several copies of each — you need ~40 filled
   sheets total across the four, plus a few unfilled for the photocopy step.
2. **Photocopy** a handful *before* filling them in: make 1st- and 2nd-generation
   copies. Label those with `photocopy_generations` 1 or 2.
3. **Fill in** bubbles by hand with a dark pen. Vary how neatly — some crisp, some
   light, some overfilled, a few with stray marks. Record exactly which bubbles you
   filled per sheet: that is the ground truth. (You don't have to fill every
   question — empty bubbles are valid ground truth too.)
4. **Photograph** ≥ 30 with a phone:
   - vary rotation up to ~±20°, and include ≥ 5 that are ~180° (upside-down);
   - vary distance so the page fills 40–100% of the frame;
   - normal indoor lighting; deliberately include a few with a shadow, glare, or an
     uneven light gradient across the page;
   - one sheet can be photographed several times under different conditions.
5. **Scan** ≥ 10 on a copier/MFP. Include a few of the photocopied-generation sheets.
6. **Downscale** captures to ~1500–2200 px on the long edge (sheets are read at
   ~150–200 DPI — more resolution just bloats the repo). Keep JPEG quality ~85.
7. **Name** files so the master is visible, e.g. `phone_sheet_b_0001.jpg`,
   `copier_sheet_d_0003.png`, … and put them in `images/`.
8. **Label** each: `python scripts/new_label.py corpus/images/phone_sheet_b_0001.jpg`
   (it picks the master from the filename, or pass `--sheet sheet_b_40q_n4`), then
   edit the JSON — set `orientation`, `lighting`, `photocopy_generations`, and the
   real `marked_options`. Add `fiducial_px` (4 hand-clicked corner-marker pixel
   coordinates) to **≥ 10** images — this is gold alignment truth for Phase 5.
9. Run `python scripts/check_corpus.py` until it exits 0, then commit.

If the committed images push the repo over ~100 MB, switch `images/` to Git LFS
before committing (decision deferred to this step per `docs/phases/phase-0.md`).
