"""Quality points 3, 4 and 6: context windows, style presets, report."""

import pytest

from subfa.burn import STYLE_PRESETS, cues_to_ass
from subfa.report import build_report
from subfa.srt import Cue
from subfa.translate import FakeTranslator, translate_with_context


def test_context_window_assembly():
    translator = FakeTranslator()
    texts = [f"line {i}" for i in range(25)]
    out = translate_with_context(translator, texts, "en", "fa", window=10, context=2)
    assert out == [f"[fa] line {i}" for i in range(25)]
    # Windows: first has no before-context, middle has both sides,
    # last has before-context and no after-context.
    assert translator.windows == [(0, 10, 2), (2, 10, 2), (2, 5, 0)]


def test_context_window_count_mismatch_raises():
    class BadTranslator(FakeTranslator):
        def translate_window(self, core, before, after, source, target):
            return ["only one"]

    with pytest.raises(ValueError):
        translate_with_context(BadTranslator(), ["a", "b"], "en", "fa")


def test_style_presets_exist_and_differ():
    cues = [Cue(0, 2, "سلام دنیا")]
    cinema = cues_to_ass(cues, style="cinema")
    reels = cues_to_ass(cues, style="reels")
    assert "Vazirmatn" in cinema and "Vazirmatn" in reels
    # Reels sits higher on screen (bigger bottom margin) than cinema.
    def margin_of(ass: str) -> int:
        style_line = ass.split("Style: Default")[1].splitlines()[0]
        return int(style_line.rsplit(",", 2)[1])

    reels_margin = margin_of(reels)
    cinema_margin = margin_of(cinema)
    assert reels_margin > cinema_margin
    assert set(STYLE_PRESETS) == {"cinema", "reels", "learning"}


def test_learning_preset_shrinks_source_line():
    cues = [Cue(0, 2, "Hello world\nسلام دنیا")]
    ass = cues_to_ass(cues, style="learning")
    assert "{\\fs34" in ass
    assert "Hello world" in ass and "سلام دنیا" in ass


def test_report_computes_from_real_cues():
    cues = [
        Cue(0.0, 2.0, "Short"),                      # 5 chars / 2s, fine
        Cue(2.0, 2.5, "This line is far too fast"),   # 22 chars / 0.5s, over
        Cue(2.5, 6.0, "A calm normal line"),          # fine
    ]
    report = build_report(
        cues, path_used="whisper", model="fake / small",
        glossary_applied=3, source_language="en", target_language="fa",
    )
    assert report.cue_count == 3
    assert report.over_speed_count == 1
    assert report.over_speed_percent == pytest.approx(33.3, abs=0.1)
    assert report.duration_seconds == pytest.approx(6.0)
    text = report.to_text()
    assert "Glossary terms applied: 3" in text
    assert "Transcript path: whisper" in text
