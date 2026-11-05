"""Premium face helpers (Bot API 9.4), adapted from the owner's
emoji-forge premium.py: styled inline buttons plus custom emojis
in the bot's own texts, with a cosmetic fallback.

Every custom emoji id below was taken verbatim from the owner's
harvested, Telegram-verified pool:
- ~/workspace/imperium/app/data/premium_emoji_ids.json (curated map)
- ~/workspace/imperium/data_harvest/pool.json (full pool)
A test asserts each shipped id exists in one of those files.

Taste rules kept from the owner's earlier bots: a button carries
at most one visual (a premium icon OR an emoji in its text, never
both), no icon-only buttons, colour by meaning only.
"""

from __future__ import annotations

import html
import re

# key -> {"alt": fallback char, "id": custom_emoji_id}
PREMIUM = {
    "brand":    {"alt": "🎬", "id": "5368653135101310687"},
    "link":     {"alt": "🔗", "id": "5372954927100351271"},
    "file":     {"alt": "📁", "id": "5357315181649076022"},
    "check":    {"alt": "✅", "id": "5237699328843200968"},
    "warning":  {"alt": "⚠️", "id": "5881702736843511327"},
    "settings": {"alt": "⚙️", "id": "5372925742797574389"},
    "globe":    {"alt": "🌐", "id": "5237937660873418362"},
    "book":     {"alt": "📚", "id": "5350481781306958339"},
    "cross":    {"alt": "❌", "id": "5370640017037218875"},
    "back":     {"alt": "⬅️", "id": "5875082500023258804"},
}


def icon_id(key: str) -> str | None:
    """Raw custom_emoji_id for an InlineKeyboardButton icon, or None."""
    entry = PREMIUM.get(key)
    return entry["id"] if entry else None


def pe(key: str) -> str:
    """HTML premium-emoji snippet for a message text (parse_mode
    HTML): <tg-emoji emoji-id="ID">ALT</tg-emoji>. Unknown keys
    degrade to an empty string."""
    entry = PREMIUM.get(key)
    if not entry:
        return ""
    return (
        f'<tg-emoji emoji-id="{entry["id"]}">'
        f'{html.escape(entry["alt"])}</tg-emoji>'
    )


_TG_EMOJI_RE = re.compile(r"<tg-emoji[^>]*>(.*?)</tg-emoji>", re.DOTALL)


def strip_premium_tags(text: str) -> str:
    """Reduce HTML <tg-emoji> tags to their plain alt character."""
    if not text:
        return text
    return _TG_EMOJI_RE.sub(lambda m: m.group(1), text)


def plain_markup(markup):
    """Rebuild an InlineKeyboardMarkup with every button's style
    and icon_custom_emoji_id removed (the cosmetic fallback when
    Telegram rejects a styled send; PTB objects are immutable, so
    the buttons are rebuilt). None passes through."""
    if markup is None:
        return None
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    rows = []
    for row in markup.inline_keyboard:
        rebuilt = []
        for button in row:
            data = {
                key: value
                for key, value in button.to_dict().items()
                if key not in ("style", "icon_custom_emoji_id")
            }
            rebuilt.append(InlineKeyboardButton(**data))
        rows.append(rebuilt)
    return InlineKeyboardMarkup(rows)
