"""Phase 4.1 DoD: v2 geometry + bubble_centres() (pure, no DB)."""
from __future__ import annotations

import math

import pytest

from app.sheet_template import (
    OverCapacityError,
    bubble_centres,
    fits_on_one_page,
    load_template,
)

TEMPLATE = load_template()
CAPACITY = {2: 120, 3: 120, 4: 120, 5: 100, 6: 80}


def _in_page(x_mm, y_mm):
    m = TEMPLATE.margin_mm
    return m <= x_mm <= TEMPLATE.page_width_mm - m and m <= y_mm <= TEMPLATE.page_height_mm - m


@pytest.mark.parametrize("n_options", [2, 3, 4, 5, 6])
@pytest.mark.parametrize("count", [1, 5, 40])
def test_small_and_mid_quizzes_are_in_bounds(n_options, count):
    centres = bubble_centres(TEMPLATE, count, n_options)
    assert set(centres) == set(range(1, count + 1))
    for options in centres.values():
        assert len(options) == n_options
        assert all(_in_page(x, y) for x, y in options)


@pytest.mark.parametrize("n_options", [2, 3, 4, 5, 6])
def test_capacity_limit_quiz_fits_and_is_in_bounds(n_options):
    count = CAPACITY[n_options]
    assert fits_on_one_page(TEMPLATE, count, n_options)
    centres = bubble_centres(TEMPLATE, count, n_options)
    assert len(centres) == count
    for options in centres.values():
        assert all(_in_page(x, y) for x, y in options)


@pytest.mark.parametrize("n_options", [2, 3, 4, 5, 6])
def test_bubbles_do_not_overlap(n_options):
    diameter = TEMPLATE.geometry.grid.bubble_diameter_mm
    centres = bubble_centres(TEMPLATE, CAPACITY[n_options], n_options)
    all_pts = [p for opts in centres.values() for p in opts]
    # spot-check: nearest-neighbour within a row and the same option across rows
    for options in list(centres.values())[:5]:
        for a, b in zip(options, options[1:], strict=False):
            assert math.dist(a, b) >= diameter
    q1, q2 = centres[1], centres[2]
    assert math.dist(q1[0], q2[0]) >= diameter
    assert len(all_pts) == n_options * CAPACITY[n_options]


@pytest.mark.parametrize("n_options", [2, 3, 4, 5, 6])
def test_over_capacity_raises(n_options):
    with pytest.raises(OverCapacityError):
        bubble_centres(TEMPLATE, CAPACITY[n_options] + 1, n_options)


def test_zero_or_bad_n_raises():
    with pytest.raises(ValueError):
        bubble_centres(TEMPLATE, 0, 4)
    with pytest.raises(ValueError):
        bubble_centres(TEMPLATE, 10, 7)


def test_deterministic():
    a = bubble_centres(TEMPLATE, 60, 4)
    b = bubble_centres(TEMPLATE, 60, 4)
    assert a == b


def test_column_fill_is_top_to_bottom_then_left_to_right():
    # N=4 → 4 columns. 8 questions → 2 per column. q1,q2 in col 0 (same x, q2 lower).
    centres = bubble_centres(TEMPLATE, 8, 4)
    assert centres[1][0][0] == centres[2][0][0]  # same column x
    assert centres[2][0][1] > centres[1][0][1]  # q2 is below q1
    assert centres[3][0][0] > centres[1][0][0]  # q3 starts the next column


def test_row_pitch_shrinks_as_the_quiz_grows():
    from app.sheet_template import row_pitch_mm

    small = row_pitch_mm(TEMPLATE, 20, 4)
    big = row_pitch_mm(TEMPLATE, 120, 4)
    assert small >= big
    assert big >= TEMPLATE.geometry.grid.min_row_pitch_mm
