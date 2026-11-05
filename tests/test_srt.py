import pytest

from subfa.srt import (
    Cue,
    cues_to_srt,
    format_timestamp,
    parse_srt,
    parse_timestamp,
    split_segment,
)


@pytest.mark.parametrize(
    "seconds,expected",
    [
        (0, "00:00:00,000"),
        (1.5, "00:00:01,500"),
        (61.25, "00:01:01,250"),
        (3661.999, "01:01:01,999"),
        (0.9999, "00:00:01,000"),  # rounding carries into the next second
        (36000, "10:00:00,000"),
    ],
)
def test_format_timestamp(seconds, expected):
    assert format_timestamp(seconds) == expected


@pytest.mark.parametrize("seconds", [0.0, 0.001, 3.75, 59.999, 125.4, 3723.042])
def test_timestamp_round_trip(seconds):
    assert parse_timestamp(format_timestamp(seconds)) == pytest.approx(seconds, abs=0.001)


def test_srt_write_parse_round_trip():
    cues = [Cue(0.0, 1.5, "Hello"), Cue(1.5, 3.0, "Line one\nLine two")]
    parsed = parse_srt(cues_to_srt(cues))
    assert len(parsed) == 2
    assert parsed[0].text == "Hello"
    assert parsed[1].text == "Line one\nLine two"
    assert parsed[1].start == pytest.approx(1.5)


def test_parse_srt_ignores_garbage_blocks():
    text = "not a subtitle file\n\n1\n00:00:01,000 --> 00:00:02,000\nReal cue\n"
    cues = parse_srt(text)
    assert len(cues) == 1 and cues[0].text == "Real cue"


def test_long_segment_is_split_into_readable_cues():
    text = " ".join(["word"] * 60)  # 299 chars over 20 seconds
    cues = split_segment(0.0, 20.0, text)
    assert len(cues) >= 3
    assert all(len(c.text) <= 84 for c in cues)
    assert cues[0].start == 0.0
    assert cues[-1].end == pytest.approx(20.0)
    # Order and timing stay monotonic.
    assert all(a.end <= b.start + 1e-9 for a, b in zip(cues, cues[1:]))


def test_short_segment_is_kept_as_one_cue():
    cues = split_segment(1.0, 3.0, "Short line.")
    assert len(cues) == 1 and cues[0].text == "Short line."
