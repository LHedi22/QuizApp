"""Phase 4.2 DoD: deterministic answer-sheet render; QR survives scan degradation;
fiducials at the config positions (pure — no DB)."""
from __future__ import annotations

from io import BytesIO

import pymupdf
import pytest
from PIL import Image, ImageFilter
from pyzbar.pyzbar import decode as zbar_decode

from app.pdf.answer_sheet import render_answer_sheet
from app.sheet_template import OverCapacityError, load_template

TEMPLATE = load_template()
QR = "throwaway-11112222-3333-4444-5555-666677778888"


def _raster(pdf_bytes: bytes, dpi: int = 150) -> Image.Image:
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        pix = doc[0].get_pixmap(dpi=dpi)
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    finally:
        doc.close()


def test_render_is_byte_identical():
    a = render_answer_sheet(num_questions=40, n_options=4, qr_id=QR, page_label="v1 40Q N=4")
    b = render_answer_sheet(num_questions=40, n_options=4, qr_id=QR, page_label="v1 40Q N=4")
    assert a == b
    assert a[:5] == b"%PDF-"


def test_qr_decodes_after_rasterization_and_degradation():
    pdf = render_answer_sheet(num_questions=60, n_options=4, qr_id=QR, page_label="v2 60Q N=4")
    # ~200 DPI ≈ a decent phone capturing the full A4 (page ~1650 px wide)
    img = _raster(pdf, dpi=200)

    # representative degradation: mild downscale + blur + JPEG (not pathological —
    # a real 12MP phone gives far more px/module than this)
    small = img.resize((int(img.width * 0.8), int(img.height * 0.8)), Image.LANCZOS)
    small = small.filter(ImageFilter.GaussianBlur(0.6))
    jpg = BytesIO()
    small.save(jpg, format="JPEG", quality=65)
    jpg.seek(0)
    degraded = Image.open(jpg)

    decoded = {d.data.decode() for d in zbar_decode(degraded)}
    assert QR in decoded


@pytest.mark.parametrize("n_options", [2, 3, 4, 5, 6])
def test_capacity_limit_renders_and_capacity_plus_one_raises(n_options):
    cap = TEMPLATE.capacity_for(n_options)
    pdf = render_answer_sheet(num_questions=cap, n_options=n_options, qr_id=QR, page_label="cap")
    assert pdf[:5] == b"%PDF-"
    with pytest.raises(OverCapacityError):
        render_answer_sheet(num_questions=cap + 1, n_options=n_options, qr_id=QR, page_label="over")


@pytest.mark.parametrize("n_options", [2, 6])
def test_single_page(n_options):
    pdf = render_answer_sheet(
        num_questions=TEMPLATE.capacity_for(n_options), n_options=n_options, qr_id=QR, page_label="x"
    )
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    try:
        assert doc.page_count == 1
    finally:
        doc.close()


def _dark_centroid(img: Image.Image, box_px):
    """Weighted centroid of dark pixels inside box_px = (l, t, r, b)."""
    crop = img.convert("L").crop(box_px)
    px = crop.load()
    sx = sy = n = 0
    for yy in range(crop.height):
        for xx in range(crop.width):
            if px[xx, yy] < 96:
                sx += xx
                sy += yy
                n += 1
    assert n > 20, "no fiducial ink found in this corner"
    return box_px[0] + sx / n, box_px[1] + sy / n


def test_fiducials_are_at_the_config_insets():
    dpi = 150
    pdf = render_answer_sheet(num_questions=30, n_options=4, qr_id=QR, page_label="x")
    img = _raster(pdf, dpi=dpi)
    px_per_mm = dpi / 25.4
    win = int(16 * px_per_mm)  # 16 mm corner window

    expected = TEMPLATE.geometry.fiducial_centres_mm(TEMPLATE.page_width_mm, TEMPLATE.page_height_mm)
    for cx_mm, cy_mm in expected:
        cx_px, cy_px = cx_mm * px_per_mm, cy_mm * px_per_mm
        box = (
            max(0, int(cx_px - win / 2)),
            max(0, int(cy_px - win / 2)),
            min(img.width, int(cx_px + win / 2)),
            min(img.height, int(cy_px + win / 2)),
        )
        gx, gy = _dark_centroid(img, box)
        assert abs(gx - cx_px) <= 0.8 * px_per_mm  # within ~0.8 mm
        assert abs(gy - cy_px) <= 0.8 * px_per_mm


def test_writes_proof_pdfs(tmp_path):
    for n, count in [(4, 120), (4, 40), (5, 100), (6, 80)]:
        out = tmp_path / f"proof_n{n}_{count}.pdf"
        out.write_bytes(
            render_answer_sheet(num_questions=count, n_options=n, qr_id=QR, page_label=f"proof {count}Q N={n}")
        )
        assert out.stat().st_size > 2000
