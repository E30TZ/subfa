"""Rolling automatic captions: detection and repair.

YouTube automatic caption tracks roll: each cue repeats the tail of
the previous cue and adds a word or two. The fixture below mimics
that shape (growing windows plus a line transition), the way the
real tracks arrive from yt-dlp.
"""

from subfa.srt import Cue, looks_rolling, reconstruct_rolling_cues

ROLLING_EN = [
    Cue(0.0, 1.6, "Hello and"),
    Cue(1.6, 3.2, "Hello and welcome"),
    Cue(3.2, 4.8, "Hello and welcome to"),
    Cue(4.8, 6.4, "Hello and welcome to the channel."),
    Cue(6.4, 8.0, "to the channel. Today we"),
    Cue(8.0, 9.6, "Today we learn"),
    Cue(9.6, 11.2, "Today we learn Python"),
    Cue(11.2, 12.8, "Today we learn Python fast."),
]

ROLLING_FA = [
    Cue(0.0, 2.0, "سلام به"),
    Cue(2.0, 4.0, "سلام به همه"),
    Cue(4.0, 6.0, "سلام به همه دوستان."),
    Cue(6.0, 8.0, "همه دوستان. امروز درباره"),
    Cue(8.0, 10.0, "امروز درباره برنامه‌نویسی"),
    Cue(10.0, 12.0, "امروز درباره برنامه‌نویسی حرف می‌زنیم."),
]

NORMAL = [
    Cue(0.0, 2.0, "First published caption line"),
    Cue(2.0, 4.0, "Second published caption line"),
    Cue(4.0, 6.0, "Third published caption line"),
    Cue(6.0, 8.0, "Fourth published caption line"),
]


def test_looks_rolling_detects_auto_caption_shape():
    assert looks_rolling(ROLLING_EN) is True
    assert looks_rolling(ROLLING_FA) is True


def test_looks_rolling_leaves_normal_captions_alone():
    assert looks_rolling(NORMAL) is False
    assert looks_rolling(NORMAL[:2]) is False


def test_reconstruct_removes_every_duplicate():
    cues = reconstruct_rolling_cues(ROLLING_EN)
    full = " ".join(cue.text.replace("\n", " ") for cue in cues)
    assert full.count("Hello") == 1
    assert full.count("welcome") == 1
    assert full.count("channel") == 1
    assert full.count("Today") == 1
    assert "Hello and welcome to the channel." in full
    assert "Today we learn Python fast." in full


def test_reconstruct_persian_rolling():
    cues = reconstruct_rolling_cues(ROLLING_FA)
    full = " ".join(cue.text.replace("\n", " ") for cue in cues)
    assert full.count("سلام") == 1
    assert full.count("دوستان") == 1
    assert "سلام به همه دوستان." in full
    assert "امروز درباره برنامه‌نویسی حرف می‌زنیم." in full


def test_reconstruct_keeps_timing_inside_original_span():
    cues = reconstruct_rolling_cues(ROLLING_EN)
    assert cues[0].start == 0.0
    assert cues[-1].end <= 12.8 + 0.001
    for previous, current in zip(cues, cues[1:]):
        assert current.start >= previous.start
