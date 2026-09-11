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
