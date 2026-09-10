"""Generate the real Phase-4 OMR answer sheets to print for the Phase 0.7 capture
corpus.

Phase 4 finished the real renderer, so the corpus is now captured on **these**
sheets (geometry from `config/sheet_template.json`), not the pre-Phase-4
`throwaway_v0`. Each master gets a deterministic `qr_id` so the QR that the Phase
5/6 pipeline decodes resolves to a known sheet, plus a `.meta.json` carrying the
ground-truth geometry (fiducial + bubble centres in mm).

    python scripts/make_corpus_sheets.py            # -> corpus/_source/
    python scripts/make_corpus_sheets.py --out /tmp/sheets

Deterministic: re-running overwrites with byte-identical PDFs.
"""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path

import pymupdf

from app.pdf.answer_sheet import render_answer_sheet
from app.sheet_template import bubble_centres, load_template

# name -> (questions, n_options). Chosen to span the layout space the reader must
# handle: 4-column (N<=4) and 3-column (N in {5,6}) grids, and a range of row
# pitches. Add denser / higher-N masters here if Phase 5/6 shows layout-specific
# failures.
SHEETS: list[tuple[str, int, int]] = [
    ("sheet_a_20q_n4", 20, 4),
    ("sheet_b_40q_n4", 40, 4),
    ("sheet_c_30q_n5", 30, 5),
    ("sheet_d_24q_n6", 24, 6),
]

_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://quizscan.local/corpus")


def qr_id_for(name: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, name))


def _png_preview(pdf_bytes: bytes, path: Path, dpi: int = 150) -> None:
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        doc[0].get_pixmap(dpi=dpi).save(path)


def _meta(name: str, questions: int, options: int, template) -> dict:
    page_w, page_h = template.page_width_mm, template.page_height_mm
    centres = bubble_centres(template, questions, options)
    return {
        "sheet_token": qr_id_for(name),
        "name": name,
        "short_name": name.split("_")[0] + "_" + name.split("_")[1],  # e.g. "sheet_b"
        "generator": "make_corpus_sheets.py (real Phase-4 renderer)",
        "template_version": template.template_version,
        "page_size": template.page_size,
        "page_w_mm": page_w,
        "page_h_mm": page_h,
        "questions": questions,
        "options": options,
        "fiducial_centres_mm": [list(pt) for pt in template.geometry.fiducial_centres_mm(page_w, page_h)],
        "bubble_centres_mm": {str(q): [list(pt) for pt in pts] for q, pts in centres.items()},
    }


def generate(out_dir: Path) -> list[dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    template = load_template()
    metas: list[dict] = []
    for name, questions, options in SHEETS:
        qr_id = qr_id_for(name)
        pdf = render_answer_sheet(
            num_questions=questions,
            n_options=options,
            qr_id=qr_id,
            page_label=f"corpus · {name} · {questions}Q · N={options}",
            template=template,
        )
        stem = out_dir / name
        stem.with_suffix(".pdf").write_bytes(pdf)
        _png_preview(pdf, stem.with_suffix(".png"))
        meta = _meta(name, questions, options, template)
        stem.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2) + "\n", newline="\n")
        metas.append(meta)
        print(f"{name}: {questions}Q N={options}  qr_id={qr_id}")
    return metas


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "corpus" / "_source",
        help="output directory (default: corpus/_source/)",
    )
    args = ap.parse_args()
    generate(args.out)
    print(f"\nwrote {len(SHEETS)} master(s) to {args.out}")


if __name__ == "__main__":
    main()
