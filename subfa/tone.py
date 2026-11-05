"""Persian subtitle tone: formal, informal, simple, or auto.

A lexical post-processing layer over finished Persian cues. It runs
after translation and cleanup, and it is deliberately conservative:

- formal: the clean normalized text the pipeline already produces.
  Nothing is rewritten.
- informal: a small curated table of formal to colloquial forms for
  frequent verb endings and phrases, applied only where the pattern
  is unambiguous (whole word, clear boundaries). It cannot change
  word order, cannot invent slang, and cannot make a stiff machine
  translation sound like a native speaker; it softens the most
  common formal markers and that is all. Offline translation
  (Argos) always outputs formal Persian, so this layer is a
  softener, not a rewriter.
- simple: same formal wording, but cues are re-segmented with a
  stricter length limit and split at conjunctions, so each cue
  carries one short idea.
- auto: informal when the Persian text itself already sounds
  colloquial (marker density over a threshold), otherwise formal.
  Auto inspects the Persian text: the source when the source is
  Persian, otherwise the translation.
"""

from __future__ import annotations

import re

from .srt import Cue, split_segment, wrap_lines

TONES = ("auto", "formal", "informal", "simple")

# Stricter limits for the simple tone: one short idea per cue.
SIMPLE_MAX_CHARS = 56
SIMPLE_MAX_LINE = 30

# -- informal conversion table ---------------------------------------
# Formal form -> colloquial form. Applied longest first, and only on
# whole words (see _apply_form). Every entry is a high frequency,
# unambiguous spoken form; anything doubtful stays out on purpose.

_INFORMAL_FORMS = {
    "نمی‌خواهم": "نمی‌خوام",
    "می‌خواهم": "می‌خوام",
    "نمی‌شود": "نمیشه",
    "می‌شود": "میشه",
    "نمی‌کنند": "نمی‌کنن",
    "می‌کنند": "می‌کنن",
    "نمی‌کند": "نمی‌کنه",
    "می‌کند": "می‌کنه",
    "نمی‌توانند": "نمی‌تونن",
    "می‌توانند": "می‌تونن",
    "نمی‌تواند": "نمی‌تونه",
    "می‌تواند": "می‌تونه",
    "نمی‌خواهد": "نمی‌خواد",
    "می‌خواهد": "می‌خواد",
    "نمی‌خواهند": "نمی‌خوان",
    "می‌خواهند": "می‌خوان",
    "می‌گویند": "میگن",
    "می‌گوید": "میگه",
    "می‌روند": "میرن",
    "می‌رود": "میره",
    "می‌آیند": "میان",
    "می‌آید": "میاد",
    "می‌دهند": "میدن",
    "می‌دهد": "میده",
    "می‌گیرند": "میگیرن",
    "می‌گیرد": "میگیره",
    "می‌دانند": "می‌دونن",
    "می‌داند": "می‌دونه",
    "می‌دانم": "می‌دونم",
    "می‌دانی": "می‌دونی",
    "آن‌ها": "اونا",
    "این‌ها": "اینا",
    "آن": "اون",
    "دیگر": "دیگه",
}

_AFTER_WORD = r"(?=[\s،؛:.!?؟»\]\)\n]|$)"
# Clause or sentence end only: punctuation or the end of the text.
# A following plain word means the phrase continues, and touching
# است there would be guessing, so it stays formal.
_AT_CLAUSE_END = r"(?=[،؛:.!?؟\n]|$)"


def _apply_form(text: str, formal: str, colloquial: str) -> str:
    pattern = re.compile(r"(?<!\S)" + re.escape(formal) + _AFTER_WORD)
    return pattern.sub(colloquial, text)


def informalize(text: str) -> str:
    """Soften one Persian cue into colloquial form, conservatively."""
    out = text
    for formal in sorted(_INFORMAL_FORMS, key=len, reverse=True):
        out = _apply_form(out, formal, _INFORMAL_FORMS[formal])
    # The copula است at a clause or sentence end: after a past
    # participle it simply drops ("دیر شده است." -> "دیر شده."),
    # after other words it becomes ه on that word ("خوب است." ->
    # "خوبه."). After a word ending in ه (خانه است) neither form is
    # safe, so it stays. است inside a longer word never matches:
    # the space before it and the clause end after it are required.
    out = re.sub(r"(?<=[دت]ه) است" + _AT_CLAUSE_END, "", out)
    out = re.sub(r"(?<=[^\sه]) است" + _AT_CLAUSE_END, "ه", out)
    # را becomes رو after vowel-ending words only: "او را" -> "او رو",
    # "کتاب‌ها را" -> "کتاب‌ها رو". After a consonant ("این را") را
    # is correct spoken Persian too and stays.
    out = re.sub(r"(?<=[اویها]) را" + _AFTER_WORD, " رو", out)
    return out


# -- auto detection ----------------------------------------------------
# Words that mark text as already colloquial. A formal text (book
# prose, news, machine translation) essentially never contains them.

COLLOQUIAL_MARKERS = (
    "میشه", "نمیشه", "می‌خوام", "میخوام", "نمی‌خوام", "می‌کنه", "میکنه",
    "می‌تونه", "میتونه", "میگه", "می‌خواد", "میخواد", "می‌دونم", "میدونم",
    "خوبه", "چیه", "اینه", "اونه", "اون", "اینا", "اونا", "دیگه",
    "داره", "دارن", "یه",
)
AUTO_MARKER_MIN_COUNT = 3
AUTO_MARKER_MIN_RATIO = 0.015  # markers per word


def colloquial_marker_count(texts: list[str]) -> int:
    joined = " ".join(texts)
    count = 0
    for marker in COLLOQUIAL_MARKERS:
        count += len(re.findall(r"(?<!\S)" + re.escape(marker) + _AFTER_WORD, joined))
    return count


def resolve_tone(requested: str, persian_texts: list[str]) -> str:
    """Resolve the requested tone to the concrete one applied.

    auto resolves to informal only when the Persian text carries
    enough colloquial markers; a single stray marker in a long
    formal text must not flip the whole job."""
    if requested not in TONES:
        requested = "auto"
    if requested != "auto":
        return requested
    words = sum(len(text.split()) for text in persian_texts)
    if words == 0:
        return "formal"
    markers = colloquial_marker_count(persian_texts)
    if markers >= AUTO_MARKER_MIN_COUNT and markers / words >= AUTO_MARKER_MIN_RATIO:
        return "informal"
    return "formal"


# -- simple re-segmentation --------------------------------------------

_CONJUNCTION_STARTERS = ("و", "اما", "ولی", "چون", "پس", "که")


def _split_at_conjunctions(text: str, min_chunk: int = 20) -> list[str]:
    """Split a sentence into idea chunks at conjunction words.

    A new chunk starts at a conjunction only once the current chunk
    is already substantial, so short sentences pass through whole."""
    words = text.split(" ")
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for word in words:
        if (
            current
            and word in _CONJUNCTION_STARTERS
            and current_len >= min_chunk
        ):
            chunks.append(" ".join(current))
            current = [word]
            current_len = len(word)
        else:
            current.append(word)
            current_len += len(word) + 1
    if current:
        chunks.append(" ".join(current))
    return chunks


def resegment_simple(cues: list[Cue]) -> list[Cue]:
    """Re-segment cues for the simple tone: shorter cues, split at
    conjunctions, narrower lines. Timing is shared inside each
    original cue in proportion to chunk length."""
    out: list[Cue] = []
    for cue in cues:
        chunks = _split_at_conjunctions(" ".join(cue.text.split()))
        total = sum(len(chunk) for chunk in chunks) or 1
        cursor = cue.start
        for index, chunk in enumerate(chunks):
            share = len(chunk) / total
            end = cue.end if index == len(chunks) - 1 else cursor + (cue.end - cue.start) * share
            for piece in split_segment(
                cursor, end, chunk, max_chars=SIMPLE_MAX_CHARS
            ):
                out.append(
                    Cue(piece.start, piece.end, wrap_lines(piece.text, max_line=SIMPLE_MAX_LINE))
                )
            cursor = end
    return out
