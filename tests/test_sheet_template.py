"""Phase 1.4 DoD: config/sheet_template.json v1 loads, validates, and matches R3.2."""
from __future__ import annotations

import json

import pytest

from app.sheet_template import (
    CONFIG_PATH,
    derive_max_chars_per_option,
    load_template,
)


def test_v1_loads_and_is_self_consistent():
    t = load_template()
    assert t.template_version == 1
    assert t.page_size == "A4"
    assert (t.page_width_mm, t.page_height_mm) == (210.0, 297.0)
    assert t.margin_mm == 12.0
    assert t.printable_column_width_mm <= t.page_width_mm - 2 * t.margin_mm


def test_capacity_table_matches_r3_2():
    t = load_template()
    assert t.capacity_by_n == {2: 120, 3: 120, 4: 120, 5: 100, 6: 80}
    assert t.capacity_for(4) == 120
    assert t.capacity_for(5) == 100
    assert t.capacity_for(6) == 80


def test_max_chars_per_option_is_recomputable():
    t = load_template()
    derived = derive_max_chars_per_option(t.printable_column_width_mm, t.option_font_size_pt)
    assert abs(t.max_chars_per_option - derived) <= 1


def test_committed_file_is_valid_json_with_expected_shape():
    raw = json.loads(CONFIG_PATH.read_text())
    assert set(raw["answer_sheet"]["capacity_by_n"]) == {"2", "3", "4", "5", "6"}


def _write(tmp_path, mutate):
    data = json.loads(CONFIG_PATH.read_text())
    mutate(data)
    p = tmp_path / "t.json"
    p.write_text(json.dumps(data))
    return p


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d["question_paper"].__setitem__("max_chars_per_option", 400),
        lambda d: d["answer_sheet"]["capacity_by_n"].pop("6"),
        lambda d: d["question_paper"].__setitem__("printable_column_width_mm", 500.0),
        lambda d: d.__setitem__("template_version", 0),
        lambda d: d["page"].__setitem__("margin_mm", -1.0),
    ],
)
def test_tampered_file_is_rejected(tmp_path, mutate):
    with pytest.raises((ValueError, KeyError)):
        load_template(_write(tmp_path, mutate))
