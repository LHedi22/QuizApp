"""The real Phase-4 corpus master sheets (`corpus/_source/sheet_*`).

Phase 0.7 readiness (post-Phase-4): the capture corpus is shot on these, not the
pre-Phase-4 `throwaway_v0`.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pymupdf
import pytest
from PIL import Image
from pyzbar.pyzbar import decode

from scripts.check_corpus import load_sources
from scripts.make_corpus_sheets import SHEETS, generate, qr_id_for

_SOURCE = Path(__file__).resolve().parent.parent / "corpus" / "_source"


def test_committed_masters_are_the_current_deterministic_render(tmp_path):
    generate(tmp_path)
    for name, _, _ in SHEETS:
        committed = (_SOURCE / f"{name}.pdf").read_bytes()
        fresh = (tmp_path / f"{name}.pdf").read_bytes()
        assert committed == fresh, f"{name}.pdf stale — re-run `make_corpus_sheets.py` and commit"


@pytest.mark.parametrize("name,questions,options", SHEETS)
def test_meta_shape_and_qr(name, questions, options):
    meta = json.loads((_SOURCE / f"{name}.meta.json").read_text())
    assert meta["sheet_token"] == qr_id_for(name)
    assert meta["questions"] == questions
    assert meta["options"] == options
    assert meta["template_version"] == 2
    assert len(meta["fiducial_centres_mm"]) == 4
    assert set(meta["bubble_centres_mm"]) == {str(q) for q in range(1, questions + 1)}
    assert all(len(v) == options for v in meta["bubble_centres_mm"].values())

    with pymupdf.open(_SOURCE / f"{name}.pdf") as doc:
        png = doc[0].get_pixmap(dpi=200).tobytes("png")
    decoded = [d.data.decode() for d in decode(Image.open(io.BytesIO(png)))]
    assert meta["sheet_token"] in decoded


def test_check_corpus_resolves_every_master():
    sources = load_sources(_SOURCE)
    assert {qr_id_for(name) for name, _, _ in SHEETS} <= set(sources)
    assert "throwaway-290c04e0-b66f-44f2-b0ad-6fea46af6756" not in sources  # retired
