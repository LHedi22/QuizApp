"""Scan intake orchestrator (REBUILD_SPEC §5 Phase 7, §2 R4.1/R5.1/R5.4/R5.8/R7.4-6).

Wires the pure Phase 5/6 OMR pipeline (`app.omr.alignment`/`classify`) into real
`Submission`/`Answer` rows. This module is Django/DB-aware — unlike `app.omr`, it
is *not* required to stay framework-free (rule 7 only covers `app/omr` and
`app/grading`).

**Upload is scoped to one `Version` at a time** (2026-09-11 user decision,
recorded in `docs/phases/phase-7.md`): `Submission.version` is a required FK, and
when alignment totally fails there's no `qr_id` to resolve a version from. The
professor picks a specific printed version before scanning; QR decode then
*validates* against that pre-selected version rather than identifying it from
scratch — a mismatch behaves like any other alignment failure (clean, specific,
R5.3), not a silent misfile.
"""

from __future__ import annotations

import hashlib
import json
import math
import uuid
from collections.abc import Callable, Iterable

import cv2
import numpy as np
from django.db import transaction

from app.core.blob_storage import get_blob_storage
from app.core.models import Answer, AuditEvent, Question, Submission, Version
from app.core.versioning_service import recover_correct_letters
from app.grading.regrade import submission_total
from app.grading.scoring import score_question
from app.omr.alignment import PageAlignment, VersionGeometry, align_page
from app.omr.classify import (
    DEFAULT_EMPTY_MAX,
    DEFAULT_FILLED_MIN,
    BubbleFill,
    BubbleState,
    classify_page,
    evaluate_question_gate,
)
from app.omr.geometry import AlignmentError
from app.sheet_template import load_template

_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _version_lookup_for(version: Version) -> Callable[[str], VersionGeometry | None]:
    """Only resolves the *pre-selected* version's own qr_id — any other decoded
    text (including a different real version's) is treated as unrecognized
    (`AlignmentError('version_not_found')`), which is exactly the "wrong sheet
    uploaded here" signal we want."""
    expected_qr = str(version.qr_id)
    num_questions = len(version.question_order)
    n_options = version.quiz.options_per_question

    def lookup(qr_text: str) -> VersionGeometry | None:
        if qr_text != expected_qr:
            return None
        return VersionGeometry(num_questions=num_questions, n_options=n_options)

    return lookup


def _question_confidence(
    row: list[BubbleFill], *, empty_max: float = DEFAULT_EMPTY_MAX, filled_min: float = DEFAULT_FILLED_MIN
) -> float:
    """A single [0, 1] confidence scalar for professor-facing display, derived
    from how far each bubble's fill_score sits from the nearest classification
    boundary. Provisional/practical — R5.7's actual gate decision is driven by
    `BubbleState` directly (see `evaluate_question_gate`), not this number.
    """
    band = max(filled_min - empty_max, 1e-6)
    worst = 1.0
    for b in row:
        if math.isnan(b.fill_score):
            worst = 0.0
            continue
        if b.state == BubbleState.FILLED:
            margin = (b.fill_score - filled_min) / band
        elif b.state == BubbleState.EMPTY:
            margin = (empty_max - b.fill_score) / band
        else:
            margin = -abs(b.fill_score - (empty_max + filled_min) / 2) / band
        worst = min(worst, max(0.0, min(1.0, 0.5 + margin)))
    return worst


def _answer_hash(detected_by_question: dict[int, list[str]]) -> str:
    """A stable hash of the rectified answer pattern (R5.8: best-effort duplicate
    detection). Order-independent per question, question-order-independent
    overall."""
    normalized = {str(q): sorted(opts) for q, opts in detected_by_question.items()}
    blob = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _decode_gray(image_bytes: bytes) -> np.ndarray | None:
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        return None
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


@transaction.atomic
def process_submission_image(
    *,
    version: Version,
    image_bytes: bytes,
    source: str,
    batch_id: uuid.UUID | None = None,
    page_number: int | None = None,
) -> Submission:
    """The Phase 7 core: one captured page -> one persisted `Submission` (+
    `Answer` rows on success). Never raises for an OMR failure — that becomes a
    `Submission(status=FAILED, ...)` row instead (R5.3/R5.7: a clean, specific,
    recorded failure, never a guess and never a silent drop).
    """
    blob = get_blob_storage()
    raw_path = f"submissions/{version.id}/{uuid.uuid4().hex}.jpg"
    blob.save(raw_path, image_bytes)

    gray = _decode_gray(image_bytes)
    template = load_template()

    if gray is None:
        return Submission.objects.create(
            version=version,
            status=Submission.Status.FAILED,
            failure_reason=Submission.FailureReason.ALIGNMENT_FAILED,
            raw_image_path=raw_path,
            source=source,
            batch_id=batch_id,
            page_number=page_number,
        )

    try:
        alignment: PageAlignment = align_page(gray, template, version_lookup=_version_lookup_for(version))
    except AlignmentError:
        return Submission.objects.create(
            version=version,
            status=Submission.Status.FAILED,
            failure_reason=Submission.FailureReason.ALIGNMENT_FAILED,
            raw_image_path=raw_path,
            source=source,
            batch_id=batch_id,
            page_number=page_number,
        )

    page = classify_page(gray, alignment.H, template, alignment.num_questions, alignment.n_options)

    submission = Submission.objects.create(
        version=version,
        status=Submission.Status.PENDING,
        raw_image_path=raw_path,
        source=source,
        batch_id=batch_id,
        page_number=page_number,
    )

    quiz = version.quiz
    detected_by_question: dict[int, list[str]] = {}
    any_flagged = False
    answers: list[Answer] = []
    for sheet_position, row in page.items():
        question_id = version.question_order[sheet_position - 1]
        question = Question.objects.get(pk=question_id)
        key = recover_correct_letters(version, question)
        gate = evaluate_question_gate(row, key_size=len(key))
        detected_letters = [_LETTERS[i] for i in gate.marked_indices]
        detected_by_question[question.order_index] = detected_letters
        any_flagged = any_flagged or gate.flagged

        score = None
        correct = None
        if not gate.flagged:
            points = question.points if question.points is not None else quiz.default_points
            score = score_question(detected_letters, key, points, quiz.marking_mode, quiz.negative_marking)
            correct = set(detected_letters) == key

        answers.append(
            Answer(
                submission=submission,
                question_no=question.order_index,
                detected_options=detected_letters,
                confidence=_question_confidence(row),
                flagged=gate.flagged,
                flag_reason=gate.reason or "",
                correct=correct,
                score=score,
            )
        )
    Answer.objects.bulk_create(answers)

    submission.status = Submission.Status.NEEDS_REVIEW if any_flagged else Submission.Status.FINALIZED
    submission.total_score = None if any_flagged else submission_total(a.score for a in answers)
    submission.answer_hash = _answer_hash(detected_by_question)
    submission.save(update_fields=["status", "total_score", "answer_hash"])

    AuditEvent.objects.create(
        quiz=quiz,
        submission=submission,
        actor_professor=None,  # system action — the scan pipeline, not a manual edit
        action=AuditEvent.Action.SCORED,
        detail={
            "status": submission.status,
            "total_score": submission.total_score,
            "flagged_count": sum(1 for a in answers if a.flagged),
            "answer_count": len(answers),
        },
    )
    return submission


def process_batch(
    *, version: Version, pages: Iterable[tuple[bytes, int]], source: str = Submission.Source.BATCH_PDF
) -> list[Submission]:
    """R5.4: each `(image_bytes, page_number)` is an independent, complete
    submission — one page's failure never aborts the batch."""
    batch_id = uuid.uuid4()
    return [
        process_submission_image(
            version=version, image_bytes=image_bytes, source=source, batch_id=batch_id, page_number=page_number
        )
        for image_bytes, page_number in pages
    ]


def find_probable_duplicate(submission: Submission) -> Submission | None:
    """R5.8: best-effort duplicate detection — another submission of the *same
    version* with an identical rectified-answer-pattern hash. Never auto-sets
    `duplicate_of` (Appendix A: that field is professor-confirmed); this is a
    pure query the review UI surfaces for the professor to confirm or dismiss.
    """
    if not submission.answer_hash:
        return None
    return (
        Submission.objects.filter(version=submission.version, answer_hash=submission.answer_hash)
        .exclude(pk=submission.pk)
        .exclude(answer_hash="")
        .order_by("created_at")
        .first()
    )
