"""CLAUDE.md rule 7: app.omr and app.grading must import with zero web-framework deps.

Run in a subprocess so the assertion is not polluted by pytest-django importing
Django into this process.
"""
from __future__ import annotations

import subprocess
import sys

_CHECK = (
    "import importlib, sys; "
    "importlib.import_module('app.omr'); "
    "importlib.import_module('app.grading'); "
    "banned = [m for m in sys.modules "
    "if m == 'django' or m.startswith(('django.', 'flask', 'fastapi', 'starlette'))]; "
    "print(banned); "
    "sys.exit(1 if banned else 0)"
)


def test_omr_and_grading_are_web_framework_free() -> None:
    result = subprocess.run(
        [sys.executable, "-c", _CHECK],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"web-framework modules leaked into app.omr/app.grading: {result.stdout.strip()}"
    )
