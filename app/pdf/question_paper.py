"""Question-paper renderer (REBUILD_SPEC §2 R3.1, §3.2).

ReportLab Platypus (no WeasyPrint — native-dep weight, §3.2 permits Platypus). The
paper shows a version's questions in *sheet order* (`version.question_order`) with
options in *sheet order* (`version.option_order`), labelled `A) … B) …`, no bubbles.
Deterministic / byte-identical (invariant mode).
"""

from __future__ import annotations

from io import BytesIO

from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer

from app.core.models import Question, Version
from app.sheet_template import SheetTemplate, load_template

_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def paper_rows(version: Version) -> list[tuple[int, str, list[str]]]:
    """`(sheet_number, question_text, [option_texts in sheet order])` per question."""
    questions = {q.id: q for q in Question.objects.filter(quiz_id=version.quiz_id)}
    rows: list[tuple[int, str, list[str]]] = []
    for number, qid in enumerate(version.question_order, start=1):
        question = questions[qid]
        order = version.option_order[str(qid)]
        rows.append((number, question.text, [question.options[i] for i in order]))
    return rows


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_question_paper(version: Version, *, template: SheetTemplate | None = None) -> bytes:
    template = template or load_template()
    rows = paper_rows(version)
    page_label = f"v{version.version_number} · {len(rows)} questions · {version.qr_id}"

    base = getSampleStyleSheet()["BodyText"]
    q_style = ParagraphStyle("Q", parent=base, spaceBefore=8, spaceAfter=3, leading=13)
    opt_style = ParagraphStyle("Opt", parent=base, leftIndent=14, leading=12, alignment=TA_LEFT)
    head_style = ParagraphStyle("Head", parent=base, fontSize=8, textColor="#555555")

    story = [Paragraph(_escape(page_label), head_style), Spacer(1, 6 * mm)]
    for number, text, options in rows:
        story.append(Paragraph(f"<b>{number}.</b> {_escape(text)}", q_style))
        for letter, option in zip(_LETTERS, options, strict=False):
            story.append(Paragraph(f"{letter}) {_escape(option)}", opt_style))

    buf = BytesIO()
    doc = BaseDocTemplate(
        buf,
        pagesize=(template.page_width_mm * mm, template.page_height_mm * mm),
        leftMargin=template.margin_mm * mm,
        rightMargin=template.margin_mm * mm,
        topMargin=template.margin_mm * mm,
        bottomMargin=template.margin_mm * mm,
        invariant=1,
        title="Question paper",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="body")
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame])])
    doc.build(story)
    return buf.getvalue()
