"""Generate a THROWAWAY single-page OMR test sheet for the Phase 0 capture corpus.

This is NOT the production answer sheet. Its geometry is disposable and defined
entirely in this file. Phases 1/4/5 must not import or reference it — the real
geometry is `config/sheet_template.json`, authored in Phase 1 (REBUILD_SPEC §3.2A).

The sheet carries what the corpus work needs to exercise real optics:
  * a full registration perimeter — 4 corner fiducials + edge timing marks on two
    sides, with quiet zones;
  * a QR encoding a random per-sheet token, decoded AFTER rectification in Phase 5;
  * a sparse bubble grid (default 40 questions x 4 options) with printed labels;
  * a handwriting box for a human-written sheet id.

Usage:
    python scripts/make_throwaway_sheet.py --out corpus/_source/throwaway_v0
    python scripts/make_throwaway_sheet.py --questions 40 --options 4 --out <stem>
"""

from __future__ import annotations

import argparse
import json
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

import pymupdf
import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

GENERATOR_VERSION = "v0"

# --- disposable geometry, all in millimetres from the TOP-LEFT corner ------------
PAGE_W_MM = 210.0
PAGE_H_MM = 297.0
MARGIN_MM = 12.0

FIDUCIAL_SIZE_MM = 10.0
FIDUCIAL_INSET_MM = 15.0  # centre distance from each page edge

TIMING_MARK_LEN_MM = 5.0
TIMING_MARK_THICK_MM = 2.0

QR_SIZE_MM = 26.0
QR_POS_MM = (30.0, 13.0)  # top-left of the QR; clear of the top-left fiducial (x 10-20)

HEADER_BOTTOM_MM = 58.0  # grid starts below this

BUBBLE_DIAMETER_MM = 4.2
BUBBLE_PITCH_MM = 7.0     # centre-to-centre between options in a row
ROW_PITCH_MM = 10.5       # centre-to-centre between question rows
COL_BLOCK_GAP_MM = 18.0   # gap between the two question columns
LABEL_GUTTER_MM = 12.0    # space for the "Qn" label before the first bubble


@dataclass
class SheetMeta:
    sheet_token: str
    generator_version: str
    page_size: str
    page_w_mm: float
    page_h_mm: float
    questions: int
    options: int
    fiducial_centres_mm: list[list[float]]
    bubble_centres_mm: dict[str, list[list[float]]]  # question_no -> [[x,y] per option]


def _pt(x_mm: float, y_mm_from_top: float) -> tuple[float, float]:
    """Convert top-left mm coordinates to ReportLab bottom-left points."""
    return x_mm * mm, (PAGE_H_MM - y_mm_from_top) * mm


def _fiducial_centres() -> list[list[float]]:
    i = FIDUCIAL_INSET_MM
    return [
        [i, i],
        [PAGE_W_MM - i, i],
        [i, PAGE_H_MM - i],
        [PAGE_W_MM - i, PAGE_H_MM - i],
    ]


def _draw_fiducials(c: canvas.Canvas) -> None:
    c.setFillColorRGB(0, 0, 0)
    half = FIDUCIAL_SIZE_MM / 2
    for cx, cy in _fiducial_centres():
        x, y = _pt(cx - half, cy + half)  # top-left of the square in RL coords
        c.rect(x, y, FIDUCIAL_SIZE_MM * mm, FIDUCIAL_SIZE_MM * mm, stroke=0, fill=1)


def _draw_timing_marks(c: canvas.Canvas, questions: int, options: int) -> None:
    """Ticks down the left edge (one per question row) and across the top edge
    (one per option column) — a registration perimeter on two sides."""
    c.setFillColorRGB(0, 0, 0)
    layout = _grid_layout(questions, options)

    # left-edge ticks, aligned to every question row
    for (_, cy) in layout["row_marks"]:
        x, y = _pt(MARGIN_MM - TIMING_MARK_LEN_MM - 1.0, cy + TIMING_MARK_THICK_MM / 2)
        c.rect(x, y, TIMING_MARK_LEN_MM * mm, TIMING_MARK_THICK_MM * mm, stroke=0, fill=1)

    # top- and bottom-edge ticks, aligned to every option column (both blocks)
    w = TIMING_MARK_THICK_MM * mm
    h = TIMING_MARK_LEN_MM * mm
    top_y = MARGIN_MM - 1.0
    bot_y = PAGE_H_MM - MARGIN_MM + 1.0 + TIMING_MARK_LEN_MM
    for cx in layout["col_marks"]:
        left = cx - TIMING_MARK_THICK_MM / 2
        xt, yt = _pt(left, top_y)
        c.rect(xt, yt, w, h, stroke=0, fill=1)
        xb, yb = _pt(left, bot_y)
        c.rect(xb, yb, w, h, stroke=0, fill=1)


def _make_qr_png(token: str, path: Path) -> None:
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=2)
    qr.add_data(token)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(path)


def _draw_qr(c: canvas.Canvas, qr_png: Path) -> None:
    x, y = _pt(QR_POS_MM[0], QR_POS_MM[1] + QR_SIZE_MM)
    c.drawImage(str(qr_png), x, y, QR_SIZE_MM * mm, QR_SIZE_MM * mm)


def _draw_header(c: canvas.Canvas, token: str, questions: int, options: int) -> None:
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 12)
    tx, ty = _pt(QR_POS_MM[0] + QR_SIZE_MM + 6, MARGIN_MM + 8)
    c.drawString(tx, ty, "THROWAWAY OMR TEST SHEET  -  not for grading")
    c.setFont("Helvetica", 8)
    tx2, ty2 = _pt(QR_POS_MM[0] + QR_SIZE_MM + 6, MARGIN_MM + 15)
    c.drawString(tx2, ty2, f"token {token}   |   {questions} questions x {options} options")

    # handwriting box
    bx, by = _pt(QR_POS_MM[0] + QR_SIZE_MM + 6, MARGIN_MM + 22)
    c.setFont("Helvetica", 9)
    c.drawString(bx, by, "Sheet ID: ______________________     Filled by: ______________________")
    gx, gy = _pt(QR_POS_MM[0] + QR_SIZE_MM + 6, MARGIN_MM + 30)
    c.setFont("Helvetica-Oblique", 7.5)
    c.drawString(gx, gy, "Fill one or more bubbles per row completely with a dark pen.")


def _grid_layout(questions: int, options: int) -> dict:
    """Compute bubble-centre geometry (top-left mm). Two question blocks side by side."""
    per_col = (questions + 1) // 2
    block_w = LABEL_GUTTER_MM + options * BUBBLE_PITCH_MM
    block1_x = MARGIN_MM + 4.0
    block2_x = block1_x + block_w + COL_BLOCK_GAP_MM
    top = HEADER_BOTTOM_MM + 6.0

    bubble_centres: dict[str, list[list[float]]] = {}
    row_marks: list[tuple[float, float]] = []
    col_marks: list[float] = []

    for idx in range(questions):
        block = 0 if idx < per_col else 1
        row = idx if block == 0 else idx - per_col
        base_x = block1_x if block == 0 else block2_x
        cy = top + row * ROW_PITCH_MM
        first_bx = base_x + LABEL_GUTTER_MM
        centres = [[first_bx + o * BUBBLE_PITCH_MM, cy] for o in range(options)]
        bubble_centres[str(idx + 1)] = centres
        if block == 0:
            row_marks.append((base_x, cy))

    for block_x in (block1_x, block2_x):
        first_bx = block_x + LABEL_GUTTER_MM
        col_marks.extend(first_bx + o * BUBBLE_PITCH_MM for o in range(options))

    return {
        "bubble_centres": bubble_centres,
        "row_marks": row_marks,
        "col_marks": col_marks,
        "per_col": per_col,
    }


def _draw_grid(c: canvas.Canvas, questions: int, options: int) -> dict:
    layout = _grid_layout(questions, options)
    letters = [chr(ord("A") + i) for i in range(options)]
    r = BUBBLE_DIAMETER_MM / 2

    c.setLineWidth(0.8)
    for q_str, centres in layout["bubble_centres"].items():
        # question label
        lx, ly = _pt(centres[0][0] - LABEL_GUTTER_MM + 1.0, centres[0][1] + 1.5)
        c.setFont("Helvetica", 8)
        c.setFillColorRGB(0, 0, 0)
        c.drawString(lx, ly, f"Q{q_str}")
        for (cx, cy), letter in zip(centres, letters, strict=True):
            px, py = _pt(cx, cy)
            c.circle(px, py, r * mm, stroke=1, fill=0)
            c.setFont("Helvetica", 5)
            c.drawCentredString(px, py - 4.6, letter)

    return layout


def generate(out_stem: Path, questions: int = 40, options: int = 4) -> SheetMeta:
    if not (2 <= options <= 6):
        raise ValueError("options must be 2..6")
    if not (1 <= questions <= 60):
        raise ValueError("throwaway sheet supports 1..60 questions")

    out_stem = Path(out_stem)
    out_stem.parent.mkdir(parents=True, exist_ok=True)
    token = f"throwaway-{uuid.uuid4()}"

    qr_png = out_stem.with_suffix(".qr.png")
    _make_qr_png(token, qr_png)

    pdf_path = out_stem.with_suffix(".pdf")
    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    _draw_fiducials(c)
    _draw_timing_marks(c, questions, options)
    _draw_qr(c, qr_png)
    _draw_header(c, token, questions, options)
    layout = _draw_grid(c, questions, options)
    c.showPage()
    c.save()

    # preview raster
    doc = pymupdf.open(pdf_path)
    pix = doc[0].get_pixmap(dpi=150)
    pix.save(out_stem.with_suffix(".png"))
    doc.close()
    qr_png.unlink(missing_ok=True)

    meta = SheetMeta(
        sheet_token=token,
        generator_version=GENERATOR_VERSION,
        page_size="A4",
        page_w_mm=PAGE_W_MM,
        page_h_mm=PAGE_H_MM,
        questions=questions,
        options=options,
        fiducial_centres_mm=_fiducial_centres(),
        bubble_centres_mm=layout["bubble_centres"],
    )
    out_stem.with_suffix(".meta.json").write_text(json.dumps(asdict(meta), indent=2))
    return meta


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, help="output path stem (no extension)")
    ap.add_argument("--questions", type=int, default=40)
    ap.add_argument("--options", type=int, default=4)
    args = ap.parse_args()
    meta = generate(Path(args.out), args.questions, args.options)
    stem = Path(args.out)
    print(f"wrote {stem.with_suffix('.pdf')}")
    print(f"wrote {stem.with_suffix('.png')}")
    print(f"wrote {stem.with_suffix('.meta.json')}")
    print(f"sheet_token = {meta.sheet_token}")


if __name__ == "__main__":
    main()
