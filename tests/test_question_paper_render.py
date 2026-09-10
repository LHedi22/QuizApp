"""Phase 4.3 DoD: question paper — shuffled order + options, text matches source,
deterministic. Needs Postgres."""
from __future__ import annotations

import pymupdf
import pytest

from app.core.ingest import ingest_quiz
from app.core.versioning_service import generate_versions_for_quiz
from app.pdf.question_paper import paper_rows, render_question_paper
from tests.conftest import QUESTION_HEADER

pytestmark = pytest.mark.django_db


def _quiz(professor, make_quiz, make_xlsx, count=12):
    quiz = make_quiz(professor, options_per_question=4)
    rows = [QUESTION_HEADER] + [
        [f"Question number {i} about topic {i}", f"alpha{i}", f"beta{i}", f"gamma{i}", f"delta{i}",
         "ABCD"[i % 4], None]
        for i in range(count)
    ]
    assert ingest_quiz(quiz, make_xlsx(rows)).ok
    return quiz


def _text(pdf: bytes) -> str:
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


def test_renders_valid_pdf_with_every_question(professor, make_quiz, make_xlsx):
    quiz = _quiz(professor, make_quiz, make_xlsx, count=12)
    version = generate_versions_for_quiz(quiz, 2, seed=1)[0]
    pdf = render_question_paper(version)
    assert pdf[:5] == b"%PDF-"
    text = _text(pdf)
    for i in range(12):
        assert f"Question number {i} about topic {i}" in text


def test_questions_are_in_sheet_order_not_canonical(professor, make_quiz, make_xlsx):
    quiz = _quiz(professor, make_quiz, make_xlsx, count=15)
    version = generate_versions_for_quiz(quiz, 3, seed=3)[0]
    rows = paper_rows(version)
    assert [n for n, _, _ in rows] == list(range(1, 16))
    # the first paper row corresponds to the first question id in question_order
    from app.core.models import Question

    first_qid = version.question_order[0]
    assert rows[0][1] == Question.objects.get(pk=first_qid).text
    # options for that row are in option_order sequence, not canonical
    order = version.option_order[str(first_qid)]
    canonical = Question.objects.get(pk=first_qid).options
    assert rows[0][2] == [canonical[i] for i in order]
    # at least one version has a non-identity option order somewhere
    assert any(
        version.option_order[str(qid)] != [0, 1, 2, 3] for qid in version.question_order
    )


def test_deterministic(professor, make_quiz, make_xlsx):
    quiz = _quiz(professor, make_quiz, make_xlsx, count=10)
    version = generate_versions_for_quiz(quiz, 1, seed=5)[0]
    assert render_question_paper(version) == render_question_paper(version)


def test_option_count_and_question_count_match_version(professor, make_quiz, make_xlsx):
    quiz = _quiz(professor, make_quiz, make_xlsx, count=20)
    version = generate_versions_for_quiz(quiz, 2, seed=9)[1]
    rows = paper_rows(version)
    assert len(rows) == len(version.question_order)
    assert all(len(opts) == 4 for _, _, opts in rows)
