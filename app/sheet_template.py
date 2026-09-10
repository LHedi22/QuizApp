"""Loader + geometry for the shared sheet config (REBUILD_SPEC §3.2A, §2 R3.2/R3.3).

**Pure** — no Django / web imports (enforced by tests/test_purity.py) so ingestion
validation (Phase 2), the PDF renderer (Phase 4), and the OMR pipeline (Phase 5/6)
all read the *same* numbers. There is exactly one geometry file
(`config/sheet_template.json`); never copy values out of it, never re-derive bubble
positions — call `bubble_centres`.

- v1: numbers only (page, question-paper text width, capacity table).
- v2: adds `answer_sheet.geometry` — fiducials, timing marks, QR box, bubble grid.
  Row pitch is *computed* per (question count, N) so any allowed quiz fits one page.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "sheet_template.json"

_PT_TO_MM = 25.4 / 72.0
_GLYPH_ADVANCE_EM = 0.5  # Helvetica mean glyph advance ≈ 0.5 em
_SAFETY = 0.97  # keep clear of the ragged right edge
_VALID_N = frozenset({2, 3, 4, 5, 6})


class OverCapacityError(ValueError):
    """Raised when a quiz has more questions than the single-page answer sheet holds."""


def derive_max_chars_per_option(printable_column_width_mm: float, font_size_pt: float) -> int:
    """The chars-per-option limit implied by the column width + font size."""
    advance_mm = font_size_pt * _GLYPH_ADVANCE_EM * _PT_TO_MM
    return math.floor(printable_column_width_mm / advance_mm * _SAFETY)


@dataclass(frozen=True)
class FiducialSpec:
    size_mm: float
    inset_mm: float


@dataclass(frozen=True)
class TimingMarkSpec:
    length_mm: float
    thickness_mm: float


@dataclass(frozen=True)
class QrSpec:
    x_mm: float
    y_mm: float
    size_mm: float


@dataclass(frozen=True)
class GridSpec:
    columns_by_n: dict[int, int]
    top_mm: float
    bottom_mm: float
    min_row_pitch_mm: float
    max_row_pitch_mm: float
    bubble_pitch_mm: float
    bubble_diameter_mm: float
    label_gutter_mm: float
    column_gap_mm: float

    def columns_for(self, n_options: int) -> int:
        return self.columns_by_n[n_options]

    def block_width_mm(self, n_options: int) -> float:
        return self.label_gutter_mm + n_options * self.bubble_pitch_mm


@dataclass(frozen=True)
class SheetGeometry:
    fiducial: FiducialSpec
    timing_mark: TimingMarkSpec
    qr: QrSpec
    grid: GridSpec

    def fiducial_centres_mm(self, page_width_mm: float, page_height_mm: float) -> list[tuple[float, float]]:
        i = self.fiducial.inset_mm
        return [
            (i, i),
            (page_width_mm - i, i),
            (i, page_height_mm - i),
            (page_width_mm - i, page_height_mm - i),
        ]


@dataclass(frozen=True)
class SheetTemplate:
    template_version: int
    page_size: str
    page_width_mm: float
    page_height_mm: float
    margin_mm: float
    printable_column_width_mm: float
    option_font: str
    option_font_size_pt: float
    max_chars_per_option: int
    capacity_by_n: dict[int, int]
    geometry: SheetGeometry

    def capacity_for(self, n: int) -> int:
        if n not in self.capacity_by_n:
            raise KeyError(f"no capacity for N={n}")
        return self.capacity_by_n[n]


# --- geometry computation (the single source of bubble positions) ------------


def _rows_per_column(num_questions: int, columns: int) -> int:
    return math.ceil(num_questions / columns)


def _needed_row_pitch_mm(grid: GridSpec, rows_per_column: int) -> float:
    if rows_per_column <= 1:
        return grid.max_row_pitch_mm
    return (grid.bottom_mm - grid.top_mm) / (rows_per_column - 1)


def fits_on_one_page(template: SheetTemplate, num_questions: int, n_options: int) -> bool:
    grid = template.geometry.grid
    rows = _rows_per_column(num_questions, grid.columns_for(n_options))
    return _needed_row_pitch_mm(grid, rows) >= grid.min_row_pitch_mm - 1e-9


def row_pitch_mm(template: SheetTemplate, num_questions: int, n_options: int) -> float:
    grid = template.geometry.grid
    rows = _rows_per_column(num_questions, grid.columns_for(n_options))
    needed = _needed_row_pitch_mm(grid, rows)
    return min(grid.max_row_pitch_mm, max(grid.min_row_pitch_mm, needed))


def bubble_centres(
    template: SheetTemplate, num_questions: int, n_options: int
) -> dict[int, list[tuple[float, float]]]:
    """1-based question number → `[(x_mm, y_mm)]` per option (top-left origin).

    Column blocks fill top-to-bottom then left-to-right. Raises `OverCapacityError`
    if the quiz exceeds `capacity_for(n_options)` or would not fit one page.
    """
    if n_options not in _VALID_N:
        raise ValueError(f"n_options must be one of {sorted(_VALID_N)}")
    if num_questions < 1:
        raise ValueError("num_questions must be >= 1")
    if num_questions > template.capacity_for(n_options) or not fits_on_one_page(
        template, num_questions, n_options
    ):
        raise OverCapacityError(
            f"{num_questions} questions exceeds the single-page capacity for N={n_options} "
            f"({template.capacity_for(n_options)})"
        )

    grid = template.geometry.grid
    columns = grid.columns_for(n_options)
    rows_per_column = _rows_per_column(num_questions, columns)
    pitch = row_pitch_mm(template, num_questions, n_options)

    block_width = grid.block_width_mm(n_options)
    total_width = columns * block_width + (columns - 1) * grid.column_gap_mm
    usable_width = template.page_width_mm - 2 * template.margin_mm
    left = template.margin_mm + (usable_width - total_width) / 2

    centres: dict[int, list[tuple[float, float]]] = {}
    for question in range(1, num_questions + 1):
        idx = question - 1
        col = idx // rows_per_column
        row = idx % rows_per_column
        block_left = left + col * (block_width + grid.column_gap_mm)
        first_bubble_x = block_left + grid.label_gutter_mm
        cy = grid.top_mm + row * pitch
        centres[question] = [
            (first_bubble_x + option * grid.bubble_pitch_mm, cy) for option in range(n_options)
        ]
    return centres


# --- validation + load ------------------------------------------------------


def _validate(t: SheetTemplate) -> None:
    if t.template_version < 1:
        raise ValueError("template_version must be >= 1")
    positives = {
        "page_width_mm": t.page_width_mm,
        "page_height_mm": t.page_height_mm,
        "margin_mm": t.margin_mm,
        "printable_column_width_mm": t.printable_column_width_mm,
        "option_font_size_pt": t.option_font_size_pt,
        "max_chars_per_option": t.max_chars_per_option,
    }
    for name, value in positives.items():
        if value <= 0:
            raise ValueError(f"{name} must be > 0, got {value}")
    usable = t.page_width_mm - 2 * t.margin_mm
    if t.printable_column_width_mm > usable + 1e-6:
        raise ValueError(
            f"printable_column_width_mm ({t.printable_column_width_mm}) exceeds the "
            f"space between margins ({usable})"
        )
    if set(t.capacity_by_n) != set(_VALID_N):
        raise ValueError(f"capacity_by_n must cover exactly N={sorted(_VALID_N)}")
    if any(v <= 0 for v in t.capacity_by_n.values()):
        raise ValueError("capacity_by_n values must be > 0")
    derived = derive_max_chars_per_option(t.printable_column_width_mm, t.option_font_size_pt)
    if abs(t.max_chars_per_option - derived) > 1:
        raise ValueError(
            f"max_chars_per_option ({t.max_chars_per_option}) is inconsistent with the "
            f"column width + font size (derived {derived})"
        )

    _validate_geometry(t)


def _validate_geometry(t: SheetTemplate) -> None:
    g = t.geometry
    grid = g.grid
    if set(grid.columns_by_n) != set(_VALID_N):
        raise ValueError("geometry.grid.columns_by_n must cover exactly N=2..6")
    if not 0 < grid.top_mm < grid.bottom_mm < t.page_height_mm:
        raise ValueError("geometry.grid top/bottom must be inside the page and ordered")
    if grid.min_row_pitch_mm <= grid.bubble_diameter_mm:
        raise ValueError("min_row_pitch_mm must exceed bubble_diameter_mm")
    if grid.bubble_pitch_mm <= grid.bubble_diameter_mm:
        raise ValueError("bubble_pitch_mm must exceed bubble_diameter_mm")
    if not 0 < grid.min_row_pitch_mm <= grid.max_row_pitch_mm:
        raise ValueError("row pitch bounds must be positive and ordered")
    if g.fiducial.inset_mm - g.fiducial.size_mm / 2 <= 0:
        raise ValueError("fiducials must sit inside the page")
    if g.qr.x_mm < 0 or g.qr.y_mm < 0 or g.qr.size_mm <= 0:
        raise ValueError("qr box must be on the page with a positive size")

    # the capacity table must actually fit one page for every N
    for n_options, cap in t.capacity_by_n.items():
        columns = grid.columns_for(n_options)
        total_width = columns * grid.block_width_mm(n_options) + (columns - 1) * grid.column_gap_mm
        if total_width > t.page_width_mm - 2 * t.margin_mm + 1e-6:
            raise ValueError(f"grid for N={n_options} is wider than the printable area")
        if not fits_on_one_page(t, cap, n_options):
            raise ValueError(
                f"capacity_by_n[{n_options}]={cap} does not fit one page with the grid geometry"
            )


def load_template(path: Path | str | None = None) -> SheetTemplate:
    path = Path(path) if path is not None else CONFIG_PATH
    raw = json.loads(path.read_text())
    page, qp, sheet = raw["page"], raw["question_paper"], raw["answer_sheet"]
    geo = sheet["geometry"]
    grid = geo["grid"]

    template = SheetTemplate(
        template_version=int(raw["template_version"]),
        page_size=str(page["size"]),
        page_width_mm=float(page["width_mm"]),
        page_height_mm=float(page["height_mm"]),
        margin_mm=float(page["margin_mm"]),
        printable_column_width_mm=float(qp["printable_column_width_mm"]),
        option_font=str(qp["option_font"]),
        option_font_size_pt=float(qp["option_font_size_pt"]),
        max_chars_per_option=int(qp["max_chars_per_option"]),
        capacity_by_n={int(k): int(v) for k, v in sheet["capacity_by_n"].items()},
        geometry=SheetGeometry(
            fiducial=FiducialSpec(float(geo["fiducial"]["size_mm"]), float(geo["fiducial"]["inset_mm"])),
            timing_mark=TimingMarkSpec(
                float(geo["timing_mark"]["length_mm"]), float(geo["timing_mark"]["thickness_mm"])
            ),
            qr=QrSpec(float(geo["qr"]["x_mm"]), float(geo["qr"]["y_mm"]), float(geo["qr"]["size_mm"])),
            grid=GridSpec(
                columns_by_n={int(k): int(v) for k, v in grid["columns_by_n"].items()},
                top_mm=float(grid["top_mm"]),
                bottom_mm=float(grid["bottom_mm"]),
                min_row_pitch_mm=float(grid["min_row_pitch_mm"]),
                max_row_pitch_mm=float(grid["max_row_pitch_mm"]),
                bubble_pitch_mm=float(grid["bubble_pitch_mm"]),
                bubble_diameter_mm=float(grid["bubble_diameter_mm"]),
                label_gutter_mm=float(grid["label_gutter_mm"]),
                column_gap_mm=float(grid["column_gap_mm"]),
            ),
        ),
    )
    _validate(template)
    return template
