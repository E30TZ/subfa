"""Word and character error rates (WER / CER), implemented in-repo.

Used by tools/benchmark_asr.py. Normalization is deliberately
simple and documented: lowercase, strip punctuation, collapse
whitespace; Persian text first goes through the same character
normalization as subtitle cleanup (Arabic Yeh/Kaf to Persian) and
ZWNJ is removed, so می‌شود and میشود count as the same word.
"""

from __future__ import annotations

import re
import unicodedata

from .fa_text import normalize_chars

_ZWNJ = "‌"


def normalize_text(text: str, persian: bool = False) -> str:
    text = text or ""
    if persian:
        text = normalize_chars(text)
    text = text.replace(_ZWNJ, "")
    text = text.lower()
    kept = []
    for ch in text:
        category = unicodedata.category(ch)
        if category.startswith("P"):  # punctuation
            kept.append(" ")
        else:
            kept.append(ch)
    return re.sub(r"\s+", " ", "".join(kept)).strip()


def _edit_distance(a: list, b: list) -> int:
    """Levenshtein distance between two token lists."""
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, token_a in enumerate(a, start=1):
        current = [i]
        for j, token_b in enumerate(b, start=1):
            current.append(
                min(
                    previous[j] + 1,          # deletion
                    current[j - 1] + 1,       # insertion
                    previous[j - 1] + (token_a != token_b),  # substitution
                )
            )
        previous = current
    return previous[-1]


def wer(reference: str, hypothesis: str, persian: bool = False) -> float:
    """Word error rate: edit distance over words / reference words."""
    ref_tokens = normalize_text(reference, persian).split()
    hyp_tokens = normalize_text(hypothesis, persian).split()
    if not ref_tokens:
        return 0.0 if not hyp_tokens else 1.0
    return _edit_distance(ref_tokens, hyp_tokens) / len(ref_tokens)


def cer(reference: str, hypothesis: str, persian: bool = False) -> float:
    """Character error rate on normalized text, spaces included."""
    ref = normalize_text(reference, persian)
    hyp = normalize_text(hypothesis, persian)
    if not ref:
        return 0.0 if not hyp else 1.0
    return _edit_distance(list(ref), list(hyp)) / len(ref)
