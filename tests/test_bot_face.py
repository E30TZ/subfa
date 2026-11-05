"""The bot's branded face: start keyboard shape and the premium
emoji ids shipped in bot/premium.py.

The ids must exist verbatim in the owner's harvested pool files
(the curated map or the full pool); if those files are absent
(e.g. a fresh CI checkout) the id test skips instead of failing.
"""

import json
from pathlib import Path

import pytest

pytest.importorskip("telegram")

from bot.bot import settings_keyboard, start_keyboard, start_text  # noqa: E402
from bot.premium import PREMIUM  # noqa: E402

POOL_FILES = [
    Path.home() / "workspace/imperium/app/data/premium_emoji_ids.json",
    Path.home() / "workspace/imperium/data_harvest/pool.json",
]


def _pool_ids() -> set[str]:
    ids: set[str] = set()
    for path in POOL_FILES:
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for value in data.values():
            if isinstance(value, dict) and "id" in value:
                ids.add(str(value["id"]))
            elif isinstance(value, list):
                for entry in value:
                    if isinstance(entry, dict) and "id" in entry:
                        ids.add(str(entry["id"]))
    return ids


def test_premium_ids_come_from_owner_pool():
    pool = _pool_ids()
    if not pool:
        pytest.skip("owner premium emoji pool files not present")
    for key, entry in PREMIUM.items():
        assert entry["id"] in pool, f"{key} id not in the owner pool"


def test_start_keyboard_shape():
    for lang in ("fa", "en"):
        rows = start_keyboard(lang).inline_keyboard
        assert len(rows) == 3
        start_btn = rows[0][0]
        help_btn, lang_btn = rows[1]
        github_btn = rows[2][0]
        # Colour by meaning: primary for the main action, success
        # for the outbound link, default for navigation.
        assert start_btn.callback_data == "howto"
        assert start_btn.style == "primary"
        assert start_btn.icon_custom_emoji_id == PREMIUM["brand"]["id"]
        assert help_btn.callback_data == "help"
        assert help_btn.style is None
        assert help_btn.icon_custom_emoji_id == PREMIUM["book"]["id"]
        assert lang_btn.callback_data == "uil"
        assert lang_btn.text == "زبان | Language"
        assert lang_btn.icon_custom_emoji_id == PREMIUM["globe"]["id"]
        assert github_btn.url == "https://github.com/E30TZ/subfa"
        assert github_btn.style == "success"
        assert github_btn.icon_custom_emoji_id == PREMIUM["link"]["id"]
        # One visual per button: an icon means no emoji in the text.
        for button in (start_btn, help_btn, lang_btn, github_btn):
            assert not any(ord(ch) > 0x2500 for ch in button.text)


def test_start_text_has_one_premium_emoji_in_header():
    text = start_text("fa")
    assert text.count("<tg-emoji") == 1
    assert text.startswith("<tg-emoji")


def test_settings_keyboard_shape_and_defaults():
    rows = settings_keyboard("fa").inline_keyboard
    # Three style rows, one quality row, one tone row, Start row.
    assert len(rows) == 6
    assert rows[0][0].callback_data == "style:cinema"
    assert rows[0][0].text.startswith("✓")  # cinema is the default
    quality_row = rows[3]
    assert [b.callback_data for b in quality_row] == [
        "quality:source", "quality:720", "quality:480", "quality:360",
    ]
    # 720 is the marked default; the others are unmarked.
    assert quality_row[1].text.startswith("✓")
    assert not quality_row[0].text.startswith("✓")
    tone_row = rows[4]
    assert [b.callback_data for b in tone_row] == [
        "tone:auto", "tone:formal", "tone:informal", "tone:simple",
    ]
    assert tone_row[0].text.startswith("✓")  # auto is the default
    go = rows[5][0]
    assert go.callback_data == "go"
    assert go.style == "primary"


def test_settings_keyboard_marks_nondefault_choices():
    rows = settings_keyboard("en", style="reels", quality="480", tone="simple").inline_keyboard
    assert rows[1][0].text.startswith("✓")       # reels style row
    assert not rows[0][0].text.startswith("✓")   # cinema unmarked now
    assert rows[3][2].text.startswith("✓")       # 480
    assert rows[4][3].text.startswith("✓")       # simple
