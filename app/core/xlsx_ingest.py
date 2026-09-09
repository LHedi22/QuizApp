"""Pure `.xlsx` question parser (REBUILD_SPEC §2 R1.2, R1.3, R1.4).

No Django imports — parses + validates only. Persistence is `app/core/ingest.py`.

Contract (R1.2), columns identified by **name** (not position):

    question_text | option_1 | option_2 | ... | option_N | correct_options | points?

- `correct_options`: 1+ of the first N letters, comma- or space-separated (`A` or `A,C`).
- `points`: optional per-question weight; blank → the quiz default. No penalty column.

Parsing is all-or-nothing (R1.3): a valid file yields every `ParsedQuestion`; an
invalid file yields errors and no questions. Header errors are reported before any
row parsing; every bad row lists every reason in one pass.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

import openpyxl

_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


@dataclass(frozen=True)
class ParsedQuestion:
    order_index: int  # 1-based, file order
    text: str
    options: list[str]  # length == n_options
    correct_options: list[str]  # canonical letters, sorted, len >= 1
    points: float | None  # None → use the quiz default

    @property
    def is_multi(self) -> bool:
        return len(self.correct_options) > 1


@dataclass(frozen=True)
class RowError:
    row: int  # 1-based spreadsheet row (header is row 1)
    reasons: list[str]


@dataclass
class ParseResult:
    questions: list[ParsedQuestion] = field(default_factory=list)
    header_errors: list[str] = field(default_factory=list)
    file_errors: list[str] = field(default_factory=list)
    row_errors: list[RowError] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.header_errors or self.file_errors or self.row_errors)


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _expected_columns(n_options: int) -> set[str]:
    return {"question_text", "correct_options", "points", *(f"option_{i}" for i in range(1, n_options + 1))}


def _validate_header(header_row: list[object], n_options: int) -> tuple[list[str], dict[str, int]]:
    errors: list[str] = []
    names = [_cell_text(v).lower() for v in header_row]
    # trim trailing empty header cells
    while names and names[-1] == "":
        names.pop()

    if not names:
        return ["the spreadsheet has no header row"], {}

    index: dict[str, int] = {}
    seen: set[str] = set()
    for pos, name in enumerate(names):
        if name == "":
            errors.append(f"column {pos + 1} has no header")
            continue
        if name in seen:
            errors.append(f"duplicate column '{name}'")
            continue
        seen.add(name)
        index[name] = pos

    expected = _expected_columns(n_options)
    for required in ("question_text", "correct_options", *(f"option_{i}" for i in range(1, n_options + 1))):
        if required not in index:
            errors.append(f"missing required column '{required}'")
    for name in index:
        if name not in expected:
            errors.append(
                f"unexpected column '{name}' "
                f"(quiz has N={n_options}; expected question_text, "
                f"option_1..option_{n_options}, correct_options, points)"
            )
    return errors, index


def _parse_correct_options(raw: str, n_options: int) -> tuple[list[str], list[str]]:
    valid = set(_LETTERS[:n_options])
    tokens = [t for t in raw.replace(",", " ").split() if t]
    if not tokens:
        return [], ["correct_options is empty"]
    reasons: list[str] = []
    chosen: set[str] = set()
    last = _LETTERS[n_options - 1]
    for tok in tokens:
        up = tok.upper()
        if up in valid:
            chosen.add(up)
        else:
            reasons.append(
                f"correct_options token '{tok}' is not one of A-{last} (quiz has {n_options} options)"
            )
    return sorted(chosen), reasons


def _parse_points(raw: str) -> tuple[float | None, list[str]]:
    if raw == "":
        return None, []
    try:
        value = float(raw)
    except ValueError:
        return None, [f"points must be a non-negative number, got '{raw}'"]
    if math.isnan(value) or math.isinf(value):
        return None, [f"points must be a finite non-negative number, got '{raw}'"]
    if value < 0:
        return None, [f"points must be non-negative, got {value}"]
    return value, []


def _parse_row(
    cells: tuple[object, ...],
    *,
    row_number: int,
    order_index: int,
    index: dict[str, int],
    n_options: int,
    max_chars_per_option: int,
) -> ParsedQuestion | RowError:
    def col(name: str) -> str:
        pos = index.get(name)
        if pos is None or pos >= len(cells):
            return ""
        return _cell_text(cells[pos])

    reasons: list[str] = []

    text = col("question_text")
    if text == "":
        reasons.append("question_text is empty")

    raw_options = [col(f"option_{i}") for i in range(1, n_options + 1)]
    non_empty = [o for o in raw_options if o != ""]
    if len(non_empty) != n_options:
        reasons.append(f"expected {n_options} non-empty option cells, found {len(non_empty)}")

    lowered = [o.lower() for o in non_empty]
    dupes = sorted({o for o in non_empty if lowered.count(o.lower()) > 1})
    for d in dupes:
        reasons.append(f"duplicate option text: '{d}'")

    for o in non_empty:
        if len(o) > max_chars_per_option:
            reasons.append(
                f"option is {len(o)} characters, exceeds the printable limit of "
                f"{max_chars_per_option}: '{o[:40]}...'"
            )

    correct, correct_reasons = _parse_correct_options(col("correct_options"), n_options)
    reasons.extend(correct_reasons)

    points, points_reasons = _parse_points(col("points"))
    reasons.extend(points_reasons)

    if reasons:
        return RowError(row=row_number, reasons=reasons)
    return ParsedQuestion(
        order_index=order_index,
        text=text,
        options=raw_options,
        correct_options=correct,
        points=points,
    )


def parse_workbook(
    source: str | Path | bytes | BytesIO,
    *,
    n_options: int,
    max_chars_per_option: int,
    max_questions: int,
) -> ParseResult:
    if isinstance(source, bytes):
        source = BytesIO(source)
    try:
        workbook = openpyxl.load_workbook(source, read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 - any openpyxl failure is a user-facing header error
        return ParseResult(header_errors=[f"could not read the spreadsheet: {exc}"])

    try:
        worksheet = workbook.active
        rows = list(worksheet.iter_rows(values_only=True))
    finally:
        workbook.close()

    if not rows:
        return ParseResult(header_errors=["the spreadsheet is empty"])

    header_errors, index = _validate_header(list(rows[0]), n_options)
    if header_errors:
        return ParseResult(header_errors=header_errors)

    used_cols = max(index.values()) + 1 if index else 0
    data_rows = [
        (pos + 2, cells)
        for pos, cells in enumerate(rows[1:])
        if any(_cell_text(c) for c in (cells or ())[:used_cols])
    ]

    if len(data_rows) > max_questions:
        return ParseResult(
            file_errors=[
                f"{len(data_rows)} questions, but the maximum for N={n_options} is {max_questions}"
            ]
        )
    if not data_rows:
        return ParseResult(file_errors=["the spreadsheet has a header but no question rows"])

    result = ParseResult()
    for order_index, (row_number, cells) in enumerate(data_rows, start=1):
        parsed = _parse_row(
            tuple(cells or ()),
            row_number=row_number,
            order_index=order_index,
            index=index,
            n_options=n_options,
            max_chars_per_option=max_chars_per_option,
        )
        if isinstance(parsed, RowError):
            result.row_errors.append(parsed)
        else:
            result.questions.append(parsed)

    if result.row_errors:
        result.questions.clear()  # all-or-nothing (R1.3)
    return result
