"""Pure message routing for the bot, kept telegram-free for tests.

A text message that contains a video link is routed to the link
flow; anything else gets a short help reply. Files are routed by the
telegram handlers themselves.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from subfa.download import extract_url  # noqa: E402


def classify_message(text: str) -> tuple[str, str | None]:
    """Return ("url", link) or ("help", None) for a text message."""
    url = extract_url(text or "")
    if url:
        return "url", url
    return "help", None
