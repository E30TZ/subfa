"""Glossaries: fixed term translations applied after translation.

Machine translation often renders technical terms inconsistently.
A glossary is a small JSON file mapping a term to the exact wording
the community wants, for example:

    {"programming": "برنامه‌نویسی", "bug": "باگ"}

Adding a glossary is the easiest contribution to SubFa: one JSON
file in the glossaries/ folder, no code changes.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import SubfaError


def load_glossary(names: list[str], glossary_dir: str | Path) -> dict[str, str]:
    """Load and merge one or more glossaries by name or file path."""
    merged: dict[str, str] = {}
    base = Path(glossary_dir)
    for name in names:
        candidate = Path(name)
        if not candidate.is_absolute() and candidate.suffix != ".json":
            candidate = base / f"{name}.json"
        elif not candidate.is_absolute() and not candidate.exists():
            candidate = base / candidate.name
        if not candidate.exists():
            raise SubfaError(f"Glossary not found: {name}")
        data = json.loads(candidate.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise SubfaError(f"Glossary {name} must be a JSON object of term to term.")
        for key, value in data.items():
            if isinstance(value, str) and key.strip():
                merged[key.strip()] = value
    return merged


def apply_glossary_counted(text: str, glossary: dict[str, str]) -> tuple[str, int]:
    """Like apply_glossary, but also returns how many terms applied."""
    if not glossary or not text:
        return text, 0
    result = text
    applied = 0
    for term in sorted(glossary, key=len, reverse=True):
        replacement = glossary[term]
        if re.fullmatch(r"[\w .+#/-]+", term, flags=re.UNICODE):
            pattern = re.compile(
                r"(?<!\w)" + re.escape(term) + r"(?!\w)", flags=re.IGNORECASE
            )
            result, count = pattern.subn(replacement, result)
            applied += count
        else:
            count = result.count(term)
            if count:
                result = result.replace(term, replacement)
                applied += count
    return result, applied


def apply_glossary(text: str, glossary: dict[str, str]) -> str:
    """Replace glossary terms in text (longest terms first).

    Matching is case-insensitive for Latin terms and respects word
    boundaries, so "bug" does not rewrite inside "debug" unless the
    glossary explicitly lists "debug".
    """
    result, _ = apply_glossary_counted(text, glossary)
    return result
