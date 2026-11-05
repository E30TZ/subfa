"""SRT subtitle reading, writing and timestamp handling.

Also contains cue segmentation: whisper segments can be long, and a
subtitle cue that stays on screen for 30 seconds or fills four lines
is hard to read. Long segments are split into readable cues.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MAX_CUE_CHARS = 84
MAX_CUE_SECONDS = 7.0
# Readability rules for real subtitles (see README quality notes):
MAX_LINE_CHARS = 42        # one line should fit a phone screen
MAX_LINES = 2              # never stack more than two lines
MAX_CHARS_PER_SECOND = 20.0  # faster than this is hard to read
MIN_CUE_SECONDS = 1.0      # shorter flashes are merged away

_SENTENCE_END = (".", "!", "?", "؟", "…")
_CLAUSE_END = (",", "،", "؛", ";", ":")


@dataclass
class Cue:
    start: float  # seconds
    end: float  # seconds
    text: str

    def __post_init__(self) -> None:
        self.text = self.text.strip()
        if self.end < self.start:
            self.end = self.start


def format_timestamp(seconds: float) -> str:
    """Format seconds as an SRT timestamp: HH:MM:SS,mmm."""
    if seconds < 0:
        seconds = 0.0
    total_ms = int(round(seconds * 1000))
    ms = total_ms % 1000
    total_s = total_ms // 1000
    s = total_s % 60
    m = (total_s // 60) % 60
    h = total_s // 3600
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


_TIMESTAMP_RE = re.compile(
    r"^(\d+):(\d{1,2}):(\d{1,2})[,.](\d{1,3})$"
)


def parse_timestamp(value: str) -> float:
    """Parse an SRT (or ASS style) timestamp into seconds."""
    match = _TIMESTAMP_RE.match(value.strip())
    if not match:
        raise ValueError(f"Invalid timestamp: {value!r}")
    hours, minutes, seconds, frac = match.groups()
    frac_value = int(frac.ljust(3, "0")) / 1000.0
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + frac_value


def cues_to_srt(cues: list[Cue]) -> str:
    blocks = []
    for index, cue in enumerate(cues, start=1):
        blocks.append(
            f"{index}\n"
            f"{format_timestamp(cue.start)} --> {format_timestamp(cue.end)}\n"
            f"{cue.text}\n"
        )
    return "\n".join(blocks)


def parse_srt(text: str) -> list[Cue]:
    cues: list[Cue] = []
    blocks = re.split(r"\n\s*\n", text.strip())
    for block in blocks:
        lines = [line for line in block.strip().splitlines() if line.strip()]
        if len(lines) < 2:
            continue
        timing_line = None
        text_lines: list[str] = []
        for line in lines:
            if "-->" in line:
                timing_line = line
            elif timing_line is not None:
                text_lines.append(line)
        if timing_line is None or not text_lines:
            continue
        start_raw, end_raw = timing_line.split("-->", 1)
        # The end part may carry position metadata after a space.
        end_token = end_raw.strip().split()[0]
        cues.append(
            Cue(
                start=parse_timestamp(start_raw.strip()),
                end=parse_timestamp(end_token),
                text="\n".join(text_lines).strip(),
            )
        )
    return cues


def wrap_lines(text: str, max_line: int = MAX_LINE_CHARS) -> str:
    """Wrap cue text into at most MAX_LINES balanced lines."""
    text = " ".join(text.split())
    if len(text) <= max_line:
        return text
    words = text.split(" ")
    if len(words) == 1:
        return text
    best: tuple[int, int] | None = None  # (longest line, split index)
    for i in range(1, len(words)):
        left = " ".join(words[:i])
        right = " ".join(words[i:])
        score = max(len(left), len(right))
        # Prefer a break right after clause punctuation when the
        # balance is close.
        bonus = 6 if words[i - 1].endswith(_CLAUSE_END + _SENTENCE_END) else 0
        candidate = (score - bonus, i)
        if best is None or candidate < best:
            best = candidate
    split = best[1]
    return " ".join(words[:split]) + "\n" + " ".join(words[split:])


def _chunk_words(words: list[str], chunk_count: int, max_chars: int) -> list[str]:
    """Split words into about chunk_count chunks, preferring breaks
    at sentence ends, then clause ends, over mid sentence breaks."""
    if chunk_count <= 1:
        return [" ".join(words)]
    total = sum(len(w) for w in words) + len(words) - 1
    target = total / chunk_count
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for index, word in enumerate(words):
        remaining_words = len(words) - index - 1
        chunks_left_after = chunk_count - len(chunks) - 1
        extra = len(word) + (1 if current else 0)
        must_leave_enough = remaining_words >= chunks_left_after
        if (
            current
            and must_leave_enough
            and current_len >= target * 0.75
            and (
                current[-1].endswith(_SENTENCE_END)
                or current_len >= target
                and (current[-1].endswith(_CLAUSE_END) or current_len >= target * 1.2)
                or current_len + extra > max_chars
            )
        ):
            chunks.append(" ".join(current))
            current = [word]
            current_len = len(word)
        else:
            current.append(word)
            current_len += extra
    if current:
        chunks.append(" ".join(current))
    return chunks


def split_segment(
    start: float,
    end: float,
    text: str,
    max_chars: int = MAX_CUE_CHARS,
    max_seconds: float = MAX_CUE_SECONDS,
) -> list[Cue]:
    """Split one transcription segment into readable cues.

    Rules enforced here (this is where amateur subtitles fail):
    - at most MAX_LINE_CHARS per line and MAX_LINES lines per cue
    - reading speed at most MAX_CHARS_PER_SECOND where timing allows
    - breaks prefer sentence ends, then clause ends
    - cues shorter than MIN_CUE_SECONDS are merged with a neighbour
    Time inside a segment is shared in proportion to characters.
    """
    import math

    text = " ".join(text.split())
    if not text:
        return []
    duration = max(end - start, 0.1)
    char_count = len(text)
    by_size = math.ceil(char_count / max_chars)
    by_speed = math.ceil(char_count / (MAX_CHARS_PER_SECOND * duration))
    by_time = math.ceil(duration / max_seconds)
    chunk_count = max(by_size, by_speed, by_time, 1)

    chunks = _chunk_words(text.split(" "), chunk_count, max_chars)
    total_chars = sum(len(chunk) for chunk in chunks) or 1
    cues: list[Cue] = []
    cursor = start
    for chunk in chunks:
        share = len(chunk) / total_chars
        cue_end = end if chunk is chunks[-1] else cursor + duration * share
        cues.append(Cue(cursor, cue_end, chunk))
        cursor = cue_end

    # Merge micro cues: a cue under the minimum duration joins its
    # neighbour when the combined text still fits one cue.
    merged: list[Cue] = []
    for cue in cues:
        if (
            merged
            and (cue.end - cue.start) < MIN_CUE_SECONDS
            and len(merged[-1].text) + 1 + len(cue.text) <= max_chars
        ):
            previous = merged[-1]
            merged[-1] = Cue(previous.start, cue.end, previous.text + " " + cue.text)
        else:
            merged.append(cue)
    if len(merged) > 1 and (merged[0].end - merged[0].start) < MIN_CUE_SECONDS:
        first, second = merged[0], merged[1]
        if len(first.text) + 1 + len(second.text) <= max_chars:
            merged[1] = Cue(first.start, second.end, first.text + " " + second.text)
            merged.pop(0)

    return [Cue(cue.start, cue.end, wrap_lines(cue.text)) for cue in merged]


def segment_to_cues(segments) -> list[Cue]:
    """Convert transcription segments (objects with start/end/text)."""
    cues: list[Cue] = []
    for segment in segments:
        cues.extend(split_segment(segment.start, segment.end, segment.text))
    return cues


# -- Rolling caption repair -------------------------------------------
# YouTube automatic captions "roll": the caption window keeps the
# previous words on screen and appends the new one, so every cue
# repeats the tail of the cue before it. Imported raw, that is
# unreadable and it poisons translation (every sentence translated
# three times, half of it duplicated). The repair rebuilds the word
# stream once, with each word timed by the cue that introduced it,
# then re-segments the stream at sentence boundaries with the normal
# craft rules in split_segment.


def word_overlap(previous: list[str], current: list[str]) -> int:
    """Length of the longest suffix of `previous` that is also a
    prefix of `current` (in whole words)."""
    best = 0
    for size in range(1, min(len(previous), len(current)) + 1):
        if previous[-size:] == current[:size]:
            best = size
    return best


def looks_rolling(cues: list[Cue], min_overlap: int = 2) -> bool:
    """True when a large share of consecutive cue pairs overlap the
    way rolling automatic captions do."""
    if len(cues) < 4:
        return False
    pairs = 0
    hits = 0
    for previous, current in zip(cues, cues[1:]):
        prev_words = previous.text.split()
        cur_words = current.text.split()
        if not prev_words or not cur_words:
            continue
        pairs += 1
        if (
            word_overlap(prev_words, cur_words) >= min_overlap
            or cur_words[: len(prev_words)] == prev_words
        ):
            hits += 1
    return pairs > 0 and hits / pairs >= 0.4


_ROLLING_SENTENCE_END = (".", "!", "?", "؟", "…")


def _is_sentence_end(token: str) -> bool:
    stripped = token.rstrip("\"'»”’)")
    return stripped.endswith(_ROLLING_SENTENCE_END) or stripped.endswith("...")


def reconstruct_rolling_cues(cues: list[Cue]) -> list[Cue]:
    """Rebuild clean, sentence-based cues from rolling captions.

    Words are deduplicated across consecutive cues (each word kept
    once, timed by the cue that first showed it), grouped into
    sentences, and each sentence is re-segmented with split_segment
    so the usual line length and reading speed rules hold.
    """
    words: list[tuple[str, float, float]] = []  # (token, start, end)
    stream: list[str] = []
    for cue in cues:
        tokens = cue.text.split()
        if not tokens:
            continue
        skip = word_overlap(stream, tokens)
        fresh = tokens[skip:]
        if not fresh:
            continue
        span = max(cue.end - cue.start, 0.1)
        for index, token in enumerate(fresh):
            start = cue.start + span * index / len(fresh)
            end = cue.start + span * (index + 1) / len(fresh)
            words.append((token, start, end))
            stream.append(token)
    if not words:
        return []

    sentences: list[list[tuple[str, float, float]]] = []
    current: list[tuple[str, float, float]] = []
    for entry in words:
        current.append(entry)
        if _is_sentence_end(entry[0]):
            sentences.append(current)
            current = []
    if current:
        sentences.append(current)

    rebuilt: list[Cue] = []
    for sentence in sentences:
        text = " ".join(token for token, _, _ in sentence)
        start = sentence[0][1]
        end = max(sentence[-1][2], start + 0.5)
        rebuilt.extend(split_segment(start, end, text))
    return rebuilt
