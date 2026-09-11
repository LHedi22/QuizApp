"""Shared fixtures for DB-backed core-model tests."""
from __future__ import annotations

import json
import uuid
from io import BytesIO
from pathlib import Path

import openpyxl
import pytest

_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
CORPUS_ROOT = Path(__file__).resolve().parent.parent / "corpus"


def _load_source_metas() -> dict[str, dict]:
    metas = {}
    for p in (CORPUS_ROOT / "_source").glob("*.meta.json"):
        meta = json.loads(p.read_text())
        metas[meta["sheet_token"]] = meta
    return metas


def load_corpus_cases() -> list[tuple[Path, dict, dict]]:
    """`(image_path, label, source_meta)` for every real, labeled corpus photo —
    shared by Phase 7's DB-integration tests (rule 9)."""
    images_dir, labels_dir = CORPUS_ROOT / "images", CORPUS_ROOT / "labels"
    if not images_dir.is_dir():
        return []
    sources = _load_source_metas()
    cases = []
    for image_path in sorted(images_dir.glob("*.jpg")):
        label_path = labels_dir / f"{image_path.stem}.json"
        if not label_path.is_file():
            continue
        label = json.loads(label_path.read_text())
        meta = sources.get(label["sheet_token"])
        if meta is not None:
            cases.append((image_path, label, meta))
    return cases

def render_filled_submission_image(version, fill_pattern: dict[int, set[int]], *, dpi: int = 150) -> bytes:
    """Render `version`'s real answer-sheet PDF (Phase 4), rasterize it exactly
    like the real batch-upload path (Phase 7's `pymupdf` raster), and draw
    filled bubbles onto the raster at the real `bubble_centres` mm positions.

    A genuine "real UI + real backend" scan input for Phase 11's e2e/load
    tests: `align_page`/`classify_page` run for real against it (Stage A/B
    detection, QR decode), not the identity-homography shortcut
    `tests/test_omr_classify.py` uses for its held-out accuracy metric. It is
    deliberately noise-free (no camera perspective/lighting) — real-capture
    robustness is Phase 5/6's separate, already-established claim over the
    real corpus (CLAUDE.md rule 9); Phase 11 is about workflow correctness
    and throughput, not re-proving OMR accuracy.

    `fill_pattern`: `{sheet_position: {sheet_option_index, ...}}` — 1-based
    sheet position (not question id), 0-based sheet option index (0=A).
    """
    import cv2
    import numpy as np
    import pymupdf

    from app.core.blob_storage import get_blob_storage
    from app.pdf.artifacts import render_and_store_version_pdfs
    from app.sheet_template import bubble_centres, load_template

    paths = render_and_store_version_pdfs(version)
    pdf_bytes = get_blob_storage().read(paths["answer_sheet"])

    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    page = doc[0]
    pix = page.get_pixmap(dpi=dpi)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    gray = cv2.cvtColor(arr[:, :, :3], cv2.COLOR_RGB2GRAY) if pix.n >= 3 else arr[:, :, 0].copy()
    doc.close()

    template = load_template()
    n_options = version.quiz.options_per_question
    num_questions = len(version.question_order)
    centres = bubble_centres(template, num_questions, n_options)
    scale = dpi / 25.4
    radius_px = max(2, int(template.geometry.grid.bubble_diameter_mm / 2 * scale * 0.8))
    for q, opts in centres.items():
        for opt_idx in fill_pattern.get(q, set()):
            x_mm, y_mm = opts[opt_idx]
            cv2.circle(gray, (int(x_mm * scale), int(y_mm * scale)), radius_px, 0, thickness=-1)

    ok, buf = cv2.imencode(".jpg", gray, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
    assert ok
    return buf.tobytes()


QUESTION_HEADER = [
    "question_text",
    "option_1",
    "option_2",
    "option_3",
    "option_4",
    "correct_options",
    "points",
]


@pytest.fixture
def make_xlsx():
    """Build an .xlsx workbook (bytes) from a list of row lists."""

    def _build(rows: list[list]) -> bytes:
        wb = openpyxl.Workbook()
        ws = wb.active
        for row in rows:
            ws.append(row)
        buf = BytesIO()
        wb.save(buf)
        return buf.getvalue()

    return _build


@pytest.fixture
def professor(db):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(email="prof@example.com", password="pw-12345")


@pytest.fixture
def other_professor(db):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(email="other@example.com", password="pw-12345")


@pytest.fixture
def make_quiz(db):
    from app.core.models import Quiz

    def _make(professor, **kw):
        defaults = {"title": "Q", "options_per_question": 4}
        return Quiz.objects.create(professor=professor, **{**defaults, **kw})

    return _make


@pytest.fixture
def make_version(db):
    from app.core.models import Question, Version

    def _make(quiz, **kw):
        q = Question.objects.create(
            quiz=quiz, order_index=1, text="t", options=["a", "b", "c", "d"], correct_options=["A"]
        )
        defaults = {
            "version_number": 1,
            "question_order": [q.id],
            "option_order": {str(q.id): [0, 1, 2, 3]},
            "template_version": 1,
        }
        return Version.objects.create(quiz=quiz, **{**defaults, **kw})

    return _make


@pytest.fixture
def make_submission(db):
    from app.core.models import Submission

    def _make(version, **kw):
        defaults = {"raw_image_path": "/data/blob/x.jpg", "source": Submission.Source.PHOTO}
        return Submission.objects.create(version=version, **{**defaults, **kw})

    return _make


@pytest.fixture
def batch_id():
    return uuid.uuid4()
