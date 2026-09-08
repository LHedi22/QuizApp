"""Phase 0.2 DoD: the throwaway sheet generates and its QR decodes from a raster."""
from __future__ import annotations

import json

from scripts.check_throwaway_sheet import check, decode_qr_from_pdf
from scripts.make_throwaway_sheet import generate


def test_generate_writes_three_files(tmp_path):
    stem = tmp_path / "sheet"
    meta = generate(stem, questions=40, options=4)
    assert stem.with_suffix(".pdf").exists()
    assert stem.with_suffix(".png").exists()
    assert stem.with_suffix(".meta.json").exists()
    on_disk = json.loads(stem.with_suffix(".meta.json").read_text())
    assert on_disk["sheet_token"] == meta.sheet_token
    assert len(on_disk["bubble_centres_mm"]) == 40
    assert len(on_disk["fiducial_centres_mm"]) == 4


def test_qr_decodes_from_rasterized_page(tmp_path):
    stem = tmp_path / "sheet"
    meta = generate(stem, questions=40, options=4)
    assert check(stem) == meta.sheet_token


def test_qr_decodes_for_non_default_geometry(tmp_path):
    stem = tmp_path / "sheet_n6"
    meta = generate(stem, questions=24, options=6)
    tokens = decode_qr_from_pdf(stem.with_suffix(".pdf"))
    assert meta.sheet_token in tokens
