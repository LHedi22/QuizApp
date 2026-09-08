# Real-capture test corpus

This directory holds **real photographs and scanner output** of physically printed
OMR sheets, with hand-labeled ground truth. It is a Phase 0 deliverable and the
measurement standard for every OMR Definition of Done from Phase 5 on
(REBUILD_SPEC.md §5, §3.3, Appendix B.5). Synthetic PDF rasterizations are only ever
a supplement — never the primary evidence.

```
corpus/
  _source/    the printed master(s) these captures came from (committed: throwaway_v0.*)
  images/     the captures themselves (jpg/png/tif/webp)
  labels/     one <image_stem>.json of ground truth per image  (schema: labels/SCHEMA.md)
```

## What to capture (subtask 0.7 — done by the user)

The gate is `python scripts/check_corpus.py` exiting 0. It requires:

| Bucket | Minimum | Notes |
|---|---|---|
| `phone_photo` | **30** | Handheld phone photos, uploaded as-is (not scanned). |
| `copier_scan` | **10** | Fed through a copier/MFP to image or PDF (split PDF to pages). |
| `photocopy_generations >= 1` | **5** | Sheets **photocopied 1–2 times before being filled in** (§6 Q10). Not only first-generation laser prints. |
| `orientation` in `upside_down` / `reversed` | **5** | Captured upside-down or fed into the copier reversed (§6 Q18). Distinct from the ±20° rotation tolerance. |

The 30 + 10 are spec minimums. The 5 + 5 floors are this project's choice for "must
include" — more is better.

### Capture protocol

1. **Print** `_source/throwaway_v0.pdf` on a laser printer (A4, 100% scale, no
   "fit to page").
2. **Photocopy** a handful: make 1st- and 2nd-generation copies *before* filling them
   in. Label those with `photocopy_generations` 1 or 2.
3. **Fill in** bubbles by hand on ~40 sheets with a dark pen. Vary how neatly — some
   crisp, some light, some overfilled, a few with stray marks. Record exactly which
   bubbles you filled: that is the ground truth.
4. **Photograph** ≥ 30 with a phone:
   - vary rotation up to ~±20°, and include ≥ 5 that are ~180° (upside-down);
   - vary distance so the page fills 40–100% of the frame;
   - normal indoor lighting; deliberately include a few with a shadow, glare, or an
     uneven light gradient across the page;
   - one sheet can be photographed several times under different conditions.
5. **Scan** ≥ 10 on a copier/MFP. Include a few of the photocopied-generation sheets.
6. **Downscale** captures to ~1500–2200 px on the long edge (sheets are read at
   ~150–200 DPI — more resolution just bloats the repo). Keep JPEG quality ~85.
7. **Name** files `phone_0001.jpg`, `copier_0001.png`, … and put them in `images/`.
8. **Label** each: `python scripts/new_label.py corpus/images/phone_0001.jpg`, then
   edit the JSON — set `orientation`, `lighting`, `photocopy_generations`, and the
   real `marked_options`. Add `fiducial_px` (4 hand-clicked corner-marker pixel
   coordinates) to **≥ 10** images — this is gold alignment truth for Phase 5.
9. Run `python scripts/check_corpus.py` until it exits 0, then commit.

If the committed images push the repo over ~100 MB, switch `images/` to Git LFS
before committing (decision deferred to this step per `docs/phases/phase-0.md`).
