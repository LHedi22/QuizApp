"""Render + cache a version's two PDFs (REBUILD_SPEC §2 R3.4, §3.3 principle 6).

Renders are deterministic, so the cache is purely an optimisation. The stored path
includes `version.template_version` — a template bump changes the path, so old
artifacts are simply no longer referenced (cache-bust, §3.3 principle 6).
"""

from __future__ import annotations

from app.core.blob_storage import get_blob_storage
from app.core.models import Version
from app.pdf.answer_sheet import render_answer_sheet
from app.pdf.question_paper import render_question_paper


def _page_label(version: Version, num_questions: int, n_options: int) -> str:
    return f"v{version.version_number} · {num_questions}Q · N={n_options} · {version.qr_id}"


def version_pdf_paths(version: Version) -> dict[str, str]:
    base = f"versions/{version.id}/tpl{version.template_version}"
    return {
        "answer_sheet": f"{base}/answer_sheet.pdf",
        "question_paper": f"{base}/question_paper.pdf",
    }


def render_and_store_version_pdfs(version: Version) -> dict[str, str]:
    """Return `{answer_sheet, question_paper}` blob paths, rendering + storing any
    that aren't already cached for this `template_version`."""
    storage = get_blob_storage()
    paths = version_pdf_paths(version)
    num_questions = len(version.question_order)
    n_options = version.quiz.options_per_question

    if not storage.exists(paths["answer_sheet"]):
        storage.save(
            paths["answer_sheet"],
            render_answer_sheet(
                num_questions=num_questions,
                n_options=n_options,
                qr_id=str(version.qr_id),
                page_label=_page_label(version, num_questions, n_options),
            ),
        )
    if not storage.exists(paths["question_paper"]):
        storage.save(paths["question_paper"], render_question_paper(version))
    return paths
