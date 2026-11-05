"""User facing limit messages in English and Persian.

Download and file checks raise SubfaError with a short code such as
"too_long"; surfaces (CLI, bot, web) turn the code into a clear
message in both languages through this module.
"""

from __future__ import annotations

LIMIT_MESSAGES = {
    "too_long": (
        "This video is longer than the limit of {minutes} minutes. "
        "Please send a shorter one.",
        "این ویدیو از حد مجاز {minutes} دقیقه طولانی‌تر است. "
        "لطفاً ویدیوی کوتاه‌تری بفرستید.",
    ),
    "too_big": (
        "This file is larger than the limit of {mb} MB. "
        "Please send a smaller one.",
        "حجم این فایل از حد مجاز {mb} مگابایت بیشتر است. "
        "لطفاً فایل کوچک‌تری بفرستید.",
    ),
    "too_large_upload": (
        "This file is larger than the limit of {mb} MB. "
        "Please upload a smaller one.",
        "حجم این فایل از حد مجاز {mb} مگابایت بیشتر است. "
        "لطفاً فایل کوچک‌تری بارگذاری کنید.",
    ),
}


def limit_message(code: str, settings) -> tuple[str, str]:
    """Return the (English, Persian) message for a limit code."""
    en, fa = LIMIT_MESSAGES.get(code, (code, code))
    values = {
        "minutes": max(1, settings.max_duration_seconds // 60),
        "mb": settings.max_download_mb,
    }
    if code == "too_large_upload":
        values["mb"] = settings.max_file_mb
    return en.format(**values), fa.format(**values)
