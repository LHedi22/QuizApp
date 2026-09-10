"""Phase 4.4 DoD: storage interface + deterministic cache + template_version
cache-busting (R3.4, §3.3 principle 6). Needs Postgres."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.core.ingest import ingest_quiz
from app.core.versioning_service import generate_versions_for_quiz
from app.pdf import artifacts
from app.pdf.answer_sheet import render_answer_sheet
from app.pdf.artifacts import render_and_store_version_pdfs, version_pdf_paths
from tests.conftest import QUESTION_HEADER

pytestmark = pytest.mark.django_db


@pytest.fixture
def media_root(tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path / "blob")
    return tmp_path / "blob"


@pytest.fixture
def version(professor, make_quiz, make_xlsx):
    quiz = make_quiz(professor, options_per_question=4)
    rows = [QUESTION_HEADER] + [
        [f"q{i}", f"a{i}", f"b{i}", f"c{i}", f"d{i}", "ABCD"[i % 4], None] for i in range(12)
    ]
    assert ingest_quiz(quiz, make_xlsx(rows)).ok
    return generate_versions_for_quiz(quiz, 2, seed=1)[0]


def test_first_call_writes_two_pdfs_under_media_root(media_root, version):
    paths = render_and_store_version_pdfs(version)
    files = sorted(p.relative_to(media_root).as_posix() for p in media_root.rglob("*.pdf"))
    assert files == sorted(paths.values())
    assert all(str(media_root) in str(media_root / p) for p in paths.values())

    stored = (media_root / paths["answer_sheet"]).read_bytes()
    expected = render_answer_sheet(
        num_questions=12,
        n_options=4,
        qr_id=str(version.qr_id),
        page_label=f"v{version.version_number} · 12Q · N=4 · {version.qr_id}",
    )
    assert stored == expected


def test_second_call_is_cached_and_does_not_re_render(media_root, version):
    render_and_store_version_pdfs(version)
    with patch.object(artifacts, "render_answer_sheet") as m_as, patch.object(
        artifacts, "render_question_paper"
    ) as m_qp:
        paths = render_and_store_version_pdfs(version)
        m_as.assert_not_called()
        m_qp.assert_not_called()
    assert (media_root / paths["answer_sheet"]).exists()


def test_template_version_bump_busts_the_cache(media_root, version):
    old = render_and_store_version_pdfs(version)
    old_as = (media_root / old["answer_sheet"]).read_bytes()

    version.template_version = 3  # test-only: simulate a template bump
    version.save(update_fields=["template_version"])

    new = render_and_store_version_pdfs(version)
    assert new["answer_sheet"] != old["answer_sheet"]
    assert "tpl3" in new["answer_sheet"] and "tpl2" in old["answer_sheet"]
    assert (media_root / old["answer_sheet"]).read_bytes() == old_as  # old untouched
    assert (media_root / new["answer_sheet"]).exists()


def test_version_pdf_paths_are_template_scoped():
    class Fake:
        id = 7
        template_version = 5

    p = version_pdf_paths(Fake())
    assert p["answer_sheet"] == "versions/7/tpl5/answer_sheet.pdf"
    assert p["question_paper"] == "versions/7/tpl5/question_paper.pdf"


def test_storage_rejects_path_escape(media_root):
    from app.core.blob_storage import get_blob_storage

    with pytest.raises(ValueError):
        get_blob_storage().save("../evil.pdf", b"x")
