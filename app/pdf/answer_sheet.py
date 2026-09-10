"""Generic single-page OMR answer sheet renderer (REBUILD_SPEC §2 R3.1, R3.3, R3.4).

Pure ReportLab, driven entirely by `app.sheet_template` geometry — the SAME numbers
the OMR pipeline reads for bubble crops (never hardcode coordinates here). Renders
are deterministic / byte-identical (ReportLab invariant mode).

The sheet is *generic per (question count, N)*: it carries a bubble grid, a full
registration perimeter, a QR of the version's `qr_id`, and a human-readable page
identifier — it does NOT name the questions.
"""

from __future__ import annotations

from io import BytesIO

import qrcode
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas

from app.sheet_template import SheetTemplate, bubble_centres, load_template

_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _y(template: SheetTemplate, y_mm_from_top: float) -> float:
    """Top-left-origin mm → ReportLab bottom-left-origin points."""
    return (template.page_height_mm - y_mm_from_top) * mm


def _draw_fiducials(c: Canvas, template: SheetTemplate) -> None:
    size = template.geometry.fiducial.size_mm
    half = size / 2
    c.setFillColorRGB(0, 0, 0)
    for cx, cy in template.geometry.fiducial_centres_mm(template.page_width_mm, template.page_height_mm):
        c.rect((cx - half) * mm, _y(template, cy + half), size * mm, size * mm, stroke=0, fill=1)


def _draw_timing_marks(
    c: Canvas, template: SheetTemplate, centres: dict[int, list[tuple[float, float]]], n_options: int
) -> None:
    tm = template.geometry.timing_mark
    length, thick = tm.length_mm, tm.thickness_mm
    margin = template.margin_mm
    c.setFillColorRGB(0, 0, 0)

    row_ys = sorted({round(y, 4) for opts in centres.values() for _, y in opts})
    for y_mm in row_ys:  # one tick per bubble row, down both side edges
        c.rect((margin - length - 1) * mm, _y(template, y_mm + thick / 2), length * mm, thick * mm, stroke=0, fill=1)
        c.rect(
            (template.page_width_mm - margin + 1) * mm,
            _y(template, y_mm + thick / 2),
            length * mm,
            thick * mm,
            stroke=0,
            fill=1,
        )

    col_xs = sorted({round(x, 4) for opts in centres.values() for x, _ in opts})
    top_y = margin - length - 1
    for x_mm in col_xs:  # one tick per option column, across the top edge
        c.rect((x_mm - thick / 2) * mm, _y(template, top_y + length), thick * mm, length * mm, stroke=0, fill=1)


def _draw_qr_and_header(c: Canvas, template: SheetTemplate, qr_id: str, page_label: str) -> None:
    from reportlab.lib.utils import ImageReader

    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_Q, box_size=12, border=2)
    qr.add_data(str(qr_id))
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    buf = BytesIO()
    image.save(buf, format="PNG")
    buf.seek(0)

    q = template.geometry.qr
    c.drawImage(ImageReader(buf), q.x_mm * mm, _y(template, q.y_mm + q.size_mm), q.size_mm * mm, q.size_mm * mm)

    c.setFillColorRGB(0, 0, 0)
    text_x = (q.x_mm + q.size_mm + 6) * mm
    c.setFont("Helvetica-Bold", 12)
    c.drawString(text_x, _y(template, q.y_mm + 7), "OMR ANSWER SHEET")
    c.setFont("Helvetica", 9)
    c.drawString(text_x, _y(template, q.y_mm + 14), page_label)
    c.setFont("Helvetica-Oblique", 7.5)
    c.drawString(
        text_x,
        _y(template, q.y_mm + 21),
        "Fill each chosen bubble completely with a dark pen; do not mark outside the circles.",
    )


def _draw_grid(
    c: Canvas, template: SheetTemplate, centres: dict[int, list[tuple[float, float]]], n_options: int
) -> None:
    radius = template.geometry.grid.bubble_diameter_mm / 2
    c.setLineWidth(0.7)

    # per-block column headers ("A B C ..."), once, above the first row of each block
    first_row_y = min(y for x, y in centres[1])
    block_first_xs = sorted({opts[0][0] for opts in centres.values()})
    for block_x in block_first_xs:
        for option in range(n_options):
            c.setFont("Helvetica-Bold", 7)
            c.setFillColorRGB(0, 0, 0)
            c.drawCentredString(
                (block_x + option * template.geometry.grid.bubble_pitch_mm) * mm,
                _y(template, first_row_y - radius - 3),
                _LETTERS[option],
            )

    for question, options in centres.items():
        label_x = options[0][0] - template.geometry.grid.label_gutter_mm + 0.5
        _, cy = options[0]
        c.setFont("Helvetica", 6)
        c.setFillColorRGB(0, 0, 0)
        c.drawString(label_x * mm, _y(template, cy + 1.2), f"Q{question}")
        for cx, cyy in options:
            c.circle(cx * mm, _y(template, cyy), radius * mm, stroke=1, fill=0)


def render_answer_sheet(
    *,
    num_questions: int,
    n_options: int,
    qr_id: str,
    page_label: str,
    template: SheetTemplate | None = None,
) -> bytes:
    """Render the answer sheet as PDF bytes. Raises `OverCapacityError` if the quiz
    exceeds the single-page capacity for `n_options`."""
    template = template or load_template()
    centres = bubble_centres(template, num_questions, n_options)  # raises OverCapacityError

    buf = BytesIO()
    c = Canvas(
        buf,
        pagesize=(template.page_width_mm * mm, template.page_height_mm * mm),
        invariant=1,
    )
    c.setTitle("OMR answer sheet")
    _draw_fiducials(c, template)
    _draw_timing_marks(c, template, centres, n_options)
    _draw_qr_and_header(c, template, qr_id, page_label)
    _draw_grid(c, template, centres, n_options)
    c.showPage()
    c.save()
    return buf.getvalue()
