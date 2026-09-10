"""R8.3 — no LLM import, client library, API key, or call anywhere on the grading
path. Verified by a source scan that runs in CI (plain pytest, no DB).

The one bounded exception (§5 Phase 10) is any file under
`app/omr/readingsuggester/` — a suggestion-only aid, off by default, built later
only if the Phase 9 review queue proves a real time sink. That directory does not
exist yet; the exemption is named here so it is greppable when it does.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent

# Files/dirs the scan walks (POSIX-relative to the repo root).
_SCAN_DIRS = ("app", "scripts")

# §5 Phase 10 carve-out. Anything under one of these prefixes is exempt.
_LLM_SCAN_EXEMPT_PREFIXES = ("app/omr/readingsuggester/",)

_LLM_PACKAGES = (
    "openai",
    "anthropic",
    "cohere",
    "mistralai",
    "litellm",
    "llama_cpp",
    "ollama",
    "replicate",
    "huggingface_hub",
    "google.generativeai",
    "google.genai",
    "transformers",
)

_IMPORT_ALTERNATION = "|".join([*(re.escape(p) for p in _LLM_PACKAGES), r"langchain\w*"])

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "llm-import",
        re.compile(rf"^\s*(?:import|from)\s+(?:{_IMPORT_ALTERNATION})\b", re.MULTILINE),
    ),
    ("llm-api-key", re.compile(r"sk-(?:ant-)?[A-Za-z0-9_-]{16,}")),
    (
        "llm-endpoint",
        re.compile(
            r"\b(?:api\.openai\.com|api\.anthropic\.com|"
            r"generativelanguage\.googleapis\.com|api\.cohere\.ai|openrouter\.ai)\b"
        ),
    ),
)


def scan_source_for_llm(text: str, path: str) -> list[str]:
    """Return a list of `"<label>: <match>"` hits for `text` (empty if clean)."""
    if any(path.startswith(prefix) for prefix in _LLM_SCAN_EXEMPT_PREFIXES):
        return []
    hits: list[str] = []
    for label, pattern in _PATTERNS:
        for m in pattern.finditer(text):
            hits.append(f"{label}: {m.group(0).strip()!r}")
    return hits


def _iter_source_files():
    for name in _SCAN_DIRS:
        for path in (_REPO / name).rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            yield path.relative_to(_REPO).as_posix(), path.read_text(encoding="utf-8")


def test_detector_flags_a_planted_import():
    """A broken detector must not pass silently."""
    assert scan_source_for_llm("import openai\nx = 1\n", "app/omr/pipeline.py")
    assert scan_source_for_llm("client = OpenAI(api_key='sk-abcdefghij0123456789')", "app/x.py")
    # ...but the Phase 10 carve-out is honoured
    assert not scan_source_for_llm("import openai", "app/omr/readingsuggester/suggester.py")


def test_no_llm_in_app_or_scripts_source():
    offenders = {}
    for rel, text in _iter_source_files():
        hits = scan_source_for_llm(text, rel)
        if hits:
            offenders[rel] = hits
    assert not offenders, f"LLM references on the grading path (R8.3): {offenders}"


def test_no_llm_dependency_in_pyproject():
    data = tomllib.loads((_REPO / "pyproject.toml").read_text(encoding="utf-8"))
    deps: list[str] = list(data["project"].get("dependencies", []))
    for group in data["project"].get("optional-dependencies", {}).values():
        deps.extend(group)
    banned = [
        d for d in deps
        if re.split(r"[<>=!~ \[]", d.lower(), maxsplit=1)[0].replace("-", "_")
        in {p.split(".")[0].replace("-", "_") for p in _LLM_PACKAGES}
        or d.lower().startswith("langchain")
    ]
    assert not banned, f"LLM package(s) in pyproject dependencies (R8.3): {banned}"
