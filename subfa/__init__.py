"""SubFa: subtitle generation and translation for ordinary people.

Send a video or audio file, get subtitles back (Persian by default),
a bilingual subtitle file, a plain transcript, and optionally the
video with subtitles burned in. Everything runs locally.
"""

__version__ = "0.1.0"


class SubfaError(Exception):
    """An error with a message that is safe to show to end users."""
