"""Bilingual subtitles: source line plus translated line in one cue.

Useful for language learners, and the format most viewers asked for:
read the original, check the translation directly under it.
"""

from __future__ import annotations

from .srt import Cue


def merge_bilingual(source_cues: list[Cue], translated_texts: list[str]) -> list[Cue]:
    """Align translated texts with source cues one to one.

    Alignment is positional: the translation step always returns one
    string per source cue, so index i of the translation belongs to
    cue i of the source.
    """
    if len(source_cues) != len(translated_texts):
        raise ValueError(
            f"Cannot merge bilingual cues: {len(source_cues)} source cues "
            f"but {len(translated_texts)} translations."
        )
    merged: list[Cue] = []
    for cue, translated in zip(source_cues, translated_texts):
        translated = translated.strip()
        if translated and translated != cue.text:
            merged.append(Cue(cue.start, cue.end, f"{cue.text}\n{translated}"))
        else:
            merged.append(Cue(cue.start, cue.end, cue.text))
    return merged
