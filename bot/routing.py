"""Pure message routing for the bot, kept telegram-free for tests.

A text message that contains a video link is routed to the link
flow; anything else gets a short help reply. Files are routed by the
telegram handlers themselves.

This module also holds the per chat UI language choice: which of
the bot's two languages (Persian or English) a chat sees. The
subtitle language flow ("lang:" callbacks) is separate and lives
in the job flow; UI language callbacks use the "ui:" prefix.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from subfa.download import extract_url  # noqa: E402

UI_LANGS = ("fa", "en")


def classify_message(text: str) -> tuple[str, str | None]:
    """Return ("url", link) or ("help", None) for a text message."""
    url = extract_url(text or "")
    if url:
        return "url", url
    return "help", None


def default_ui_lang(language_code: str | None) -> str:
    """Default UI language from Telegram's language_code: Persian
    for fa, English for any other known code, Persian when the
    client reports nothing."""
    if not language_code:
        return "fa"
    return "fa" if language_code.lower().startswith("fa") else "en"


def parse_ui_callback(data: str | None) -> str | None:
    """Return the UI language for a "ui:fa" / "ui:en" callback,
    or None for anything else (including the subtitle flow's
    "lang:" callbacks)."""
    if data and data.startswith("ui:"):
        lang = data.split(":", 1)[1]
        if lang in UI_LANGS:
            return lang
    return None


class LangStore:
    """Per chat UI language choices, persisted as a small JSON
    file so a restart does not reset everyone's language."""

    def __init__(self, path):
        self.path = Path(path)
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.data = {}

    def get(self, chat_id, language_code: str | None = None) -> str:
        lang = self.data.get(str(chat_id))
        if lang in UI_LANGS:
            return lang
        return default_ui_lang(language_code)

    def set(self, chat_id, lang: str) -> None:
        if lang not in UI_LANGS:
            return
        self.data[str(chat_id)] = lang
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False), encoding="utf-8"
        )
