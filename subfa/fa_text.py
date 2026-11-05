"""Persian text cleanup for subtitles.

Machine translation and captions written with Arabic keyboards leave
predictable problems in Persian text: Arabic Yeh and Kaf, missing
ZWNJ (نیم‌فاصله) in words like می‌شود and کتاب‌ها, stray spaces around
punctuation, and mixed digit scripts. This module fixes the safe,
mechanical cases. It never rewrites wording.
"""

from __future__ import annotations

import re

ZWNJ = "‌"

_CHAR_MAP = {
    "ي": "ی",  # Arabic Yeh -> Persian Yeh
    "ك": "ک",  # Arabic Kaf -> Persian Kaf
    "ى": "ی",  # Alef Maksura -> Persian Yeh
    "ة": "ه",  # Teh Marbuta -> Heh
    "ؤ": "و",
}

_FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_DIGIT_SOURCES = "0123456789" + "٠١٢٣٤٥٦٧٨٩" + _FA_DIGITS


def _to_fa_digits(text: str) -> str:
    # _DIGIT_SOURCES is three blocks of ten digit glyphs (ASCII,
    # Arabic-Indic, Persian), each in 0 to 9 order.
    result = []
    for ch in text:
        if ch in _DIGIT_SOURCES:
            result.append(_FA_DIGITS[_DIGIT_SOURCES.index(ch) % 10])
        else:
            result.append(ch)
    return "".join(result)


def _to_en_digits(text: str) -> str:
    result = []
    for ch in text:
        if ch in _FA_DIGITS:
            result.append(str(_FA_DIGITS.index(ch)))
        elif ch in "٠١٢٣٤٥٦٧٨٩":
            result.append(str("٠١٢٣٤٥٦٧٨٩".index(ch)))
        else:
            result.append(ch)
    return "".join(result)


def normalize_chars(text: str) -> str:
    for source, target in _CHAR_MAP.items():
        text = text.replace(source, target)
    return text


# Well known compounds that machine translation often emits with a
# plain space. Kept deliberately small and safe.
_COMPOUNDS = {
    "برنامه نویسی": "برنامه‌نویسی",
    "به روز رسانی": "به‌روزرسانی",
    "نرم افزار": "نرم‌افزار",
    "سخت افزار": "سخت‌افزار",
}


def apply_zwnj(text: str) -> str:
    """Join common prefixes and suffixes with a ZWNJ."""
    for spaced, joined in _COMPOUNDS.items():
        text = text.replace(spaced, joined)
    # Verbal prefix می / نمی: "می شود" -> "می‌شود", "نمی روم" -> "نمی‌روم"
    text = re.sub(r"(?<!\S)(ن?می)\s+(?=\S)", r"\1" + ZWNJ, text)
    # Plural and related suffixes: "کتاب ها" -> "کتاب‌ها"
    text = re.sub(
        r"(\S)\s+(ها|های|هایی)(?=\s|$|[،؛:.!?؟])",
        r"\1" + ZWNJ + r"\2",
        text,
    )
    # Adjective suffix تر / ترین: "بزرگ تر" -> "بزرگ‌تر"
    text = re.sub(
        r"(\S)\s+(ترین|تر)(?=\s|$|[،؛:.!?؟])",
        r"\1" + ZWNJ + r"\2",
        text,
    )
    return text


def fix_punctuation(text: str) -> str:
    """No space before punctuation, exactly one space after it."""
    text = re.sub(r"\s+([،؛:.!?؟])", r"\1", text)
    text = re.sub(r"([،؛:.!?؟])(?=[^\s،؛:.!?؟])", r"\1 ", text)
    # Persian quotes hug their content: « متن » -> «متن»
    text = re.sub(r"«\s+", "«", text)
    text = re.sub(r"\s+»", "»", text)
    # Straight double quotes become guillemets in pairs.
    parts = text.split('"')
    if len(parts) > 2 and len(parts) % 2 == 1:
        rebuilt = []
        for index, part in enumerate(parts):
            rebuilt.append(part)
            if index < len(parts) - 1:
                rebuilt.append("«" if index % 2 == 0 else "»")
        text = "".join(rebuilt)
        text = re.sub(r"«\s+", "«", text)
        text = re.sub(r"\s+»", "»", text)
    return text


def clean_fa_text(text: str, digits: str = "fa") -> str:
    """Full cleanup pipeline for one Persian cue or line.

    digits: "fa" converts all digits to Persian, "en" converts all
    to ASCII, "keep" leaves digits untouched.
    """
    out_lines = []
    for line in text.split("\n"):
        line = normalize_chars(line)
        line = apply_zwnj(line)
        line = fix_punctuation(line)
        if digits == "fa":
            line = _to_fa_digits(line)
        elif digits == "en":
            line = _to_en_digits(line)
        out_lines.append(" ".join(line.split()) if line.strip() else line)
    return "\n".join(out_lines)
