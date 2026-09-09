"""Phase 2.3 DoD (pure): the .xlsx parser per R1.2 / R1.3 / R1.4.

Workbooks are built in-test with openpyxl — no fixture files, no DB.
"""
from __future__ import annotations

from io import BytesIO

import openpyxl
import pytest

from app.core.xlsx_ingest import parse_workbook

N = 4
MAXCHARS = 92
MAXQ = 120
HEADER = ["question_text", "option_1", "option_2", "option_3", "option_4", "correct_options", "points"]


def xlsx(rows: list[list]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def parse(rows, *, n=N, maxchars=MAXCHARS, maxq=MAXQ):
    return parse_workbook(xlsx(rows), n_options=n, max_chars_per_option=maxchars, max_questions=maxq)


# --- happy path ------------------------------------------------------------

def test_good_file_single_and_multi_correct():
    res = parse(
        [
            HEADER,
            ["Capital of France?", "Paris", "Lyon", "Berlin", "Rome", "A", None],
            ["Primes?", "2", "3", "4", "9", "A, B", 2.5],
            ["Colours of the flag?", "Red", "White", "Green", "Blue", "A B C", ""],
        ]
    )
    assert res.ok, (res.header_errors, res.file_errors, res.row_errors)
    assert [q.order_index for q in res.questions] == [1, 2, 3]
    assert res.questions[0].correct_options == ["A"] and not res.questions[0].is_multi
    assert res.questions[0].points is None
    assert res.questions[1].correct_options == ["A", "B"] and res.questions[1].points == 2.5
    assert res.questions[2].correct_options == ["A", "B", "C"] and res.questions[2].is_multi
    assert res.questions[0].options == ["Paris", "Lyon", "Berlin", "Rome"]


def test_headers_are_case_and_whitespace_insensitive():
    hdr = [" Question_Text ", "OPTION_1", "Option_2", "option_3", "option_4", "Correct_Options", "POINTS"]
    res = parse([hdr, ["q", "a", "b", "c", "d", "B", None]])
    assert res.ok
    assert res.questions[0].correct_options == ["B"]


def test_points_column_is_optional():
    res = parse([HEADER[:-1], ["q", "a", "b", "c", "d", "A"]])
    assert res.ok
    assert res.questions[0].points is None


# --- header errors (reported before any row parsing) ----------------------

def test_missing_question_text_header():
    hdr = ["option_1", "option_2", "option_3", "option_4", "correct_options"]
    res = parse([hdr, ["a", "b", "c", "d", "A"]])
    assert any("missing required column 'question_text'" in e for e in res.header_errors)
    assert res.questions == [] and res.row_errors == []


def test_missing_one_option_column():
    hdr = ["question_text", "option_1", "option_2", "option_4", "correct_options"]
    res = parse([hdr, ["q", "a", "b", "d", "A"]])
    assert any("missing required column 'option_3'" in e for e in res.header_errors)
    assert any("unexpected column 'option_4'" not in e for e in res.header_errors)  # option_4 is valid at N=4


def test_duplicate_option_header():
    hdr = ["question_text", "option_1", "option_1", "option_3", "option_4", "correct_options"]
    res = parse([hdr, ["q", "a", "b", "c", "d", "A"]])
    assert any("duplicate column 'option_1'" in e for e in res.header_errors)


def test_unexpected_column():
    hdr = [*HEADER, "notes"]
    res = parse([hdr, ["q", "a", "b", "c", "d", "A", 1, "hi"]])
    assert any("unexpected column 'notes'" in e for e in res.header_errors)


def test_extra_option_column_beyond_n():
    hdr = ["question_text", "option_1", "option_2", "option_3", "option_4", "option_5", "correct_options"]
    res = parse([hdr, ["q", "a", "b", "c", "d", "e", "A"]])
    assert any("unexpected column 'option_5'" in e for e in res.header_errors)


# --- row errors: every reason in one pass (R1.3) --------------------------

def test_row_lists_all_reasons_at_once():
    res = parse(
        [
            HEADER,
            ["", "a", "b", "", "", "E", "-3"],  # empty text, 2 options, bad letter, negative points
        ]
    )
    assert res.questions == []
    assert len(res.row_errors) == 1
    reasons = res.row_errors[0].reasons
    assert any("question_text is empty" in r for r in reasons)
    assert any("expected 4 non-empty option cells, found 2" in r for r in reasons)
    assert any("not one of A-D" in r for r in reasons)
    assert any("non-negative" in r for r in reasons)


@pytest.mark.parametrize(
    ("row", "needle"),
    [
        (["q", "Paris", "Paris", "c", "d", "A", None], "duplicate option text: 'Paris'"),
        (["q", "a", "b", "c", "d", "E", None], "not one of A-D"),
        (["q", "a", "b", "c", "d", "", None], "correct_options is empty"),
        (["q", "a", "b", "c", "d", "A", "abc"], "points must be a non-negative number, got 'abc'"),
        (["q", "a", "b", "c", "d", "A", -1], "points must be non-negative"),
        (["q", "a" * 200, "b", "c", "d", "A", None], "exceeds the printable limit of 92"),
        (["q", "a", "b", "c", "", "A", None], "expected 4 non-empty option cells, found 3"),
        (["q", "a", "b", "c", "d", "A C", None], None),  # space-separated multi is valid
    ],
)
def test_individual_row_checks(row, needle):
    res = parse([HEADER, row])
    if needle is None:
        assert res.ok, res.row_errors
    else:
        assert any(needle in r for r in res.row_errors[0].reasons), res.row_errors


# --- all-or-nothing + whole-file ----------------------------------------------

def test_one_bad_row_rejects_the_whole_file():
    res = parse(
        [
            HEADER,
            ["good", "a", "b", "c", "d", "A", None],
            ["bad", "a", "b", "c", "d", "Z", None],
        ]
    )
    assert res.questions == []
    assert len(res.row_errors) == 1 and res.row_errors[0].row == 3


def test_over_capacity_is_a_file_error():
    rows = [HEADER] + [[f"q{i}", "a", "b", "c", "d", "A", None] for i in range(MAXQ + 1)]
    res = parse(rows)
    assert res.file_errors and "maximum for N=4 is 120" in res.file_errors[0]
    assert res.questions == []


def test_header_only_file():
    res = parse([HEADER])
    assert res.file_errors and "no question rows" in res.file_errors[0]


def test_blank_rows_between_questions_are_skipped():
    res = parse(
        [
            HEADER,
            ["q1", "a", "b", "c", "d", "A", None],
            [None, None, None, None, None, None, None],
            ["q2", "a", "b", "c", "d", "B", None],
        ]
    )
    assert res.ok
    assert [q.order_index for q in res.questions] == [1, 2]


def test_corrupt_file():
    res = parse_workbook(b"not a spreadsheet", n_options=N, max_chars_per_option=MAXCHARS, max_questions=MAXQ)
    assert any("could not read the spreadsheet" in e for e in res.header_errors)


def test_uses_real_sheet_template_numbers():
    from app.sheet_template import load_template

    t = load_template()
    long_opt = "x" * (t.max_chars_per_option + 1)
    res = parse_workbook(
        xlsx([HEADER, ["q", long_opt, "b", "c", "d", "A", None]]),
        n_options=4,
        max_chars_per_option=t.max_chars_per_option,
        max_questions=t.capacity_for(4),
    )
    assert any("exceeds the printable limit" in r for r in res.row_errors[0].reasons)
