"""Loader for the shared sheet geometry config (REBUILD_SPEC §3.2A).

**Pure** — no Django / web imports (enforced by tests/test_purity.py) so ingestion
validation (Phase 2), the PDF renderer (Phase 4), and the OMR pipeline (Phase 5/6)
can all read the *same* numbers. There is exactly one geometry file
(`config/sheet_template.json`); never copy values out of it.

v1 carries numbers only. Phase 4 adds the bubble-grid / fiducial / timing-mark
coordinates against this same file and may bump `template_version` (≤ 15% per R3.2).
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


def derive_max_chars_per_option(printable_column_width_mm: float, font_size_pt: float) -> int:
    """The chars-per-option limit implied by the column width + font size.

    Kept as a function so `max_chars_per_option` in the JSON can be validated on load
    and can't silently drift away from the geometry it's supposed to describe.
    """
    advance_mm = font_size_pt * _GLYPH_ADVANCE_EM * _PT_TO_MM
    return math.floor(printable_column_width_mm / advance_mm * _SAFETY)


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

    def capacity_for(self, n: int) -> int:
        if n not in self.capacity_by_n:
            raise KeyError(f"no capacity for N={n}")
        return self.capacity_by_n[n]


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
    derived = derive_max_chars_per_option(
        t.printable_column_width_mm, t.option_font_size_pt
    )
    if abs(t.max_chars_per_option - derived) > 1:
        raise ValueError(
            f"max_chars_per_option ({t.max_chars_per_option}) is inconsistent with the "
            f"column width + font size (derived {derived})"
        )


def load_template(path: Path | str | None = None) -> SheetTemplate:
    path = Path(path) if path is not None else CONFIG_PATH
    raw = json.loads(path.read_text())
    page, qp, sheet = raw["page"], raw["question_paper"], raw["answer_sheet"]
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
    )
    _validate(template)
    return template
