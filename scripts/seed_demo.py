"""Seed a small demo dataset — one professor, one versioned quiz with stored PDFs.

Used by `deploy/RUNBOOK.md` ("wipe & reseed") and `scripts/check_backup_restore.sh`.
Idempotent by email: re-running resets the demo professor's password and replaces
their quizzes. No scan data (the pipeline is Phase 7).

    DJANGO_SETTINGS_MODULE=app.settings DATABASE_URL=... python scripts/seed_demo.py
"""

from __future__ import annotations

import os
from io import BytesIO

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings")
django.setup()

import openpyxl  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402

from app.core.ingest import ingest_quiz  # noqa: E402
from app.core.services import create_quiz  # noqa: E402
from app.core.versioning_service import generate_versions_for_quiz  # noqa: E402
from app.pdf.artifacts import render_and_store_version_pdfs  # noqa: E402

DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "demo-pass-12345"  # noqa: S105 - demo credential, localhost only
QUESTIONS = 12
VERSIONS = 3


def _demo_xlsx(n: int) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(
        ["question_text", "option_1", "option_2", "option_3", "option_4", "correct_options", "points"]
    )
    for i in range(1, n + 1):
        correct = "A" if i % 2 else "B, C"
        ws.append([f"Demo question {i}", "alpha", "beta", "gamma", "delta", correct, ""])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def main() -> None:
    user_model = get_user_model()
    prof, _ = user_model.objects.get_or_create(email=DEMO_EMAIL)
    prof.set_password(DEMO_PASSWORD)
    prof.save()
    prof.quizzes.all().delete()

    quiz = create_quiz(professor=prof, title="Demo midterm", options_per_question=4)
    result = ingest_quiz(quiz, BytesIO(_demo_xlsx(QUESTIONS)))
    if not result.ok:
        raise SystemExit(f"seed_demo: ingest failed: {result}")
    versions = generate_versions_for_quiz(quiz, VERSIONS, seed=12)
    stored = [render_and_store_version_pdfs(v) for v in versions]

    print(f"professor  {DEMO_EMAIL} / {DEMO_PASSWORD}")
    print(f"quiz       {quiz.id} '{quiz.title}'  status={quiz.status}  {quiz.questions.count()} questions")
    for version, paths in zip(versions, stored, strict=True):
        print(f"  version {version.id}  #{version.version_number}  qr={version.qr_id}")
        print(f"    {paths['answer_sheet']}")
        print(f"    {paths['question_paper']}")


if __name__ == "__main__":
    main()
