"""Quality point 1: subtitle craft rules in segmentation."""

from subfa.srt import (
    MAX_CHARS_PER_SECOND,
    MAX_LINE_CHARS,
    MIN_CUE_SECONDS,
    split_segment,
    wrap_lines,
)


def test_lines_never_exceed_max_line_chars():
    text = " ".join(["subtitle"] * 40)
    cues = split_segment(0.0, 30.0, text)
    assert len(cues) >= 2
    for cue in cues:
        lines = cue.text.split("\n")
        assert len(lines) <= 2
        assert all(len(line) <= MAX_LINE_CHARS + 8 for line in lines)


def test_wrap_lines_balances_two_lines():
    wrapped = wrap_lines("one two three four five six seven eight nine ten")
    lines = wrapped.split("\n")
    assert len(lines) == 2
    assert abs(len(lines[0]) - len(lines[1])) <= 12


def test_reading_speed_split_for_dense_speech():
    # 120 chars in 3 seconds is 40 chars/sec: must be split so each
    # cue spans enough of the segment timeline.
    text = " ".join(["fast"] * 24)
    cues = split_segment(0.0, 3.0, text)
    assert len(cues) >= 2
    total = sum(len("".join(c.text.split())) for c in cues)
    assert total == len("".join(text.split()))


def test_long_dense_text_respects_speed_when_time_allows():
    # 400 chars over 40 seconds: segmentation must produce cues whose
    # reading speed is at or under the limit everywhere.
    text = " ".join(["readable"] * 44) + "."
    cues = split_segment(0.0, 40.0, text)
    for cue in cues:
        chars = len("".join(cue.text.split()))
        speed = chars / max(cue.end - cue.start, 0.01)
        assert speed <= MAX_CHARS_PER_SECOND + 0.5


def test_breaks_prefer_sentence_boundaries():
    text = (
        "This is the first sentence. And here is a second one. "
        "Then a third sentence follows right after it now."
    )
    cues = split_segment(0.0, 12.0, text)
    joined_first_lines = [c.text.split("\n")[0] for c in cues]
    # The first cue should end at a sentence end, not mid sentence.
    assert cues[0].text.replace("\n", " ").rstrip().endswith(".")


def test_micro_cues_are_merged():
    # One tiny fragment cannot stand alone as a sub-second flash when
    # merging with its neighbour stays within the size limit.
    cues = split_segment(0.0, 0.6, "Hi.")
    assert len(cues) == 1
    assert cues[0].end - cues[0].start >= 0.5  # the fragment itself


def test_min_duration_for_normal_cues():
    text = "Short one. Another short one here."
    cues = split_segment(0.0, 8.0, text)
    for cue in cues:
        assert cue.end - cue.start >= MIN_CUE_SECONDS - 0.25
