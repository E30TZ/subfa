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

from bot.bot import start_keyboard, start_text  # noqa: E402
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
