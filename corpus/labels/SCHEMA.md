# Corpus label schema

One file per image: `corpus/labels/<image_stem>.json`. All keys below are **required**
except `fiducial_px`. Validated by `scripts/check_corpus.py`.

| Key | Type | Meaning |
|---|---|---|
| `image` | string | Filename under `corpus/images/` (e.g. `"phone_0001.jpg"`). Must exist. |
| `capture_type` | `"phone_photo"` \| `"copier_scan"` | How it was captured. |
| `photocopy_generations` | int 0–3 | How many times the sheet was photocopied **before** being filled in. 0 = first-generation laser print. |
| `orientation` | `"upright"` \| `"upside_down"` \| `"reversed"` | Gross orientation of the sheet in the capture. `upside_down` ≈ 180° rotation; `reversed` = fed backwards through a scanner. |
| `sheet_token` | string | The `sheet_token` from a `corpus/_source/*.meta.json`. Ties the capture to a known printed master and its question/option counts. |
| `lighting` | string | Free text: `"even indoor"`, `"hard shadow lower-left"`, `"glare top edge"`, `"gradient dark at bottom"`, … |
| `marked_options` | object | `"<question number>"` → list of filled letters. `[]` = left blank. Letters must be within `A..` for the sheet's option count. This is the per-bubble filled/empty ground truth (Phase 6). |
| `notes` | string | Anything else worth knowing. May be `""`. |
| `fiducial_px` *(optional)* | list of 4 `[x, y]` | Hand-clicked pixel coordinates of the 4 corner-marker centres, in image pixels. Gold alignment truth for Phase 5. Add to ≥ 10 images. |

## Example

`corpus/labels/phone_0001.json`:

```json
{
  "image": "phone_0001.jpg",
  "capture_type": "phone_photo",
  "photocopy_generations": 1,
  "orientation": "upright",
  "sheet_token": "throwaway-290c04e0-b66f-44f2-b0ad-6fea46af6756",
  "lighting": "even indoor, slight glare top-right",
  "marked_options": {
    "1": ["B"],
    "2": ["A", "C"],
    "3": [],
    "4": ["D"]
  },
  "notes": "sheet #7, photographed at ~15 degrees rotation",
  "fiducial_px": [[212, 190], [1740, 205], [198, 2360], [1755, 2372]]
}
```

`marked_options` only needs entries for questions you want scored in tests; the
`scripts/new_label.py` scaffold seeds all of them to `[]` so you just edit the ones
you filled.
