"""SubFa Telegram bot.

Run:
    BOT_TOKEN=... python -m bot.bot

The user sends a video, an audio file, a document, or pastes a video
link (YouTube and other yt-dlp sites). The bot asks for the subtitle
language with inline buttons, processes the file in a temporary
folder, sends back the subtitles, and deletes everything.

The token is read from the BOT_TOKEN environment variable only.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from subfa import SubfaError
from subfa.config import load_settings
from subfa.download import make_downloader
from subfa.messages import limit_message
from subfa.pipeline import Pipeline
from subfa.transcribe import make_engine
from subfa.translate import make_translator

from bot.routing import classify_message

settings = load_settings()

# The public Bot API refuses bot downloads over 20 MB and bot uploads
# over 50 MB. A local Bot API server raises both; the code reports
# the effective cap honestly instead of failing mid job.
TELEGRAM_DOWNLOAD_CAP = 20 * 1024 * 1024
TELEGRAM_UPLOAD_CAP = 50 * 1024 * 1024

START_TEXT = (
    "سلام! من SubFa هستم. 🎬\n"
    "یک ویدیو یا فایل صوتی بفرست، یا لینک ویدیو (یوتیوب و سایت‌های دیگر) "
    "را پیست کن؛ زیرنویس فارسی، زیرنویس دوزبانه و متن کامل را تحویل بگیر.\n"
    "فایل‌ها روی همین سرور پردازش و بعد پاک می‌شوند.\n\n"
    "Hi! I am SubFa. Send a video or audio file, or paste a video link "
    "(YouTube and other yt-dlp sites), and get Persian subtitles, a "
    "bilingual subtitle file and a transcript back. Files are processed "
    "locally and deleted afterwards."
)

ASK_LANGUAGE = (
    "زبان زیرنویس را انتخاب کن / Choose the subtitle language:"
)

LANG_BUTTONS = [
    [InlineKeyboardButton("فارسی (پیش‌فرض) / Persian", callback_data="lang:fa")],
    [InlineKeyboardButton("English", callback_data="lang:en")],
    [InlineKeyboardButton("دوزبانه / Bilingual", callback_data="lang:bilingual")],
]

ASK_STYLE = "سبک زیرنویس روی ویدیو را انتخاب کن / Choose the burn-in style:"

STYLE_BUTTONS = [
    [InlineKeyboardButton("🎬 سینمایی / Cinema", callback_data="style:cinema")],
    [InlineKeyboardButton("📱 ریلز عمودی / Reels 9:16", callback_data="style:reels")],
    [InlineKeyboardButton("📚 آموزشی دوزبانه / Learning", callback_data="style:learning")],
]


def friendly_error(code: str) -> str:
    """Turn engine errors into guidance a non developer can act on."""
    lowered = code.lower()
    if "no speech" in lowered:
        return (
            "صدای گفتاری پیدا نشد. مطمئن شو فایل صدا دارد و دوباره بفرست.\n"
            "No speech was found. Check the file has audible speech and send it again."
        )
    if "could not read this link" in lowered or "download failed" in lowered:
        return (
            "لینک خوانده نشد. لینک کامل صفحه ویدیو را بفرست و چند دقیقه دیگر دوباره تلاش کن.\n"
            "The link could not be read. Send the full video page link and try again in a few minutes."
        )
    if "argos" in lowered or "argostranslate" in lowered:
        return (
            "بسته ترجمه روی این نصب آماده نیست. به مدیر بات اطلاع بده.\n"
            "The translation pack is not ready on this installation. Please tell the bot admin."
        )
    if "faster-whisper" in lowered:
        return (
            "موتور پیاده‌سازی صدا روی این نصب آماده نیست. به مدیر بات اطلاع بده.\n"
            "The transcription engine is not ready on this installation. Please tell the bot admin."
        )
    return f"خطا / Error: {code}"

STAGE_TEXT = {
    "download": "در حال دانلود / Downloading",
    "extract": "در حال استخراج صدا / Extracting audio",
    "transcribe": "در حال پیاده‌سازی صدا / Transcribing",
    "captions": "در حال خواندن زیرنویس منتشرشده / Reading published captions",
    "translate": "در حال ترجمه / Translating",
    "write": "در حال ساخت فایل‌ها / Writing files",
    "burn": "در حال چسباندن زیرنویس روی ویدیو / Burning subtitles",
    "done": "تمام شد / Done",
}


def _effective_download_cap() -> int:
    return min(settings.max_file_bytes, TELEGRAM_DOWNLOAD_CAP)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(START_TEXT)


async def on_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    attachment = message.video or message.audio or message.document
    if attachment is None:
        return
    if attachment.file_size and attachment.file_size > _effective_download_cap():
        en, fa = limit_message("too_large_upload", settings)
        await message.reply_text(f"{fa}\n{en}")
        return
    file_name = getattr(attachment, "file_name", None) or "media.bin"
    context.user_data["pending"] = {
        "kind": "file",
        "file_id": attachment.file_id,
        "file_name": file_name,
    }
    await message.reply_text(
        ASK_LANGUAGE, reply_markup=InlineKeyboardMarkup(LANG_BUTTONS)
    )


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    kind, url = classify_message(update.message.text or "")
    if kind == "url":
        context.user_data["pending"] = {"kind": "url", "url": url}
        await update.message.reply_text(
            ASK_LANGUAGE, reply_markup=InlineKeyboardMarkup(LANG_BUTTONS)
        )
    else:
        await update.message.reply_text(
            "یک فایل ویدیو یا صدا بفرست، یا لینک ویدیو را پیست کن.\n"
            "Send a video or audio file, or paste a video link."
        )


async def on_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    choice = (query.data or "lang:fa").split(":", 1)[1]
    if "pending" not in context.user_data:
        await query.edit_message_text(
            "این درخواست منقضی شده است. فایل یا لینک را دوباره بفرست.\n"
            "This request expired. Send the file or link again."
        )
        return
    context.user_data["lang_choice"] = choice
    await query.edit_message_text(
        ASK_STYLE, reply_markup=InlineKeyboardMarkup(STYLE_BUTTONS)
    )


async def on_style(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    style = (query.data or "style:cinema").split(":", 1)[1]
    pending = context.user_data.pop("pending", None)
    choice = context.user_data.pop("lang_choice", "fa")
    if pending is None:
        await query.edit_message_text(
            "این درخواست منقضی شده است. فایل یا لینک را دوباره بفرست.\n"
            "This request expired. Send the file or link again."
        )
        return

    target = "fa" if choice in ("fa", "bilingual") else "en"
    bilingual_burn = choice == "bilingual" or style == "learning"
    status_message = await query.edit_message_text("شروع شد / Started")

    state = {"stage": "start", "fraction": 0.0}

    def progress(stage: str, fraction: float, note: str) -> None:
        state["stage"] = stage
        state["fraction"] = fraction

    async def poll_progress() -> None:
        last = ""
        while True:
            label = STAGE_TEXT.get(state["stage"], state["stage"])
            text = f"{label} ({int(state['fraction'] * 100)}٪)"
            if text != last:
                last = text
                try:
                    await status_message.edit_text(text)
                except Exception:
                    pass
            await asyncio.sleep(2)

    poller = asyncio.create_task(poll_progress())

    async def run_job() -> None:
        with tempfile.TemporaryDirectory(prefix="subfa-bot-") as tmp:
            tmp_path = Path(tmp)
            pipeline = Pipeline(
                settings=settings,
                engine=make_engine(settings),
                translator=make_translator(settings),
                downloader=make_downloader(settings),
                progress=progress,
            )
            if pending["kind"] == "file":
                tg_file = await context.bot.get_file(pending["file_id"])
                local = tmp_path / pending["file_name"]
                await tg_file.download_to_drive(str(local))
                result = await asyncio.to_thread(
                    pipeline.run_file,
                    local,
                    tmp_path / "out",
                    target,
                    "auto",
                    [],
                    True,
                    bilingual_burn,
                    style,
                )
            else:
                result = await asyncio.to_thread(
                    pipeline.run_url,
                    pending["url"],
                    tmp_path / "out",
                    tmp_path / "download",
                    target,
                    "auto",
                    [],
                    True,
                    bilingual_burn,
                    style,
                )
            for kind_name in ("srt", "bilingual", "transcript", "report"):
                path = result.outputs.get(kind_name)
                if path and path.exists():
                    with path.open("rb") as handle:
                        await context.bot.send_document(
                            chat_id=query.message.chat_id, document=handle
                        )
            burned = result.outputs.get("burned")
            if burned and burned.exists():
                if burned.stat().st_size <= TELEGRAM_UPLOAD_CAP:
                    with burned.open("rb") as handle:
                        await context.bot.send_video(
                            chat_id=query.message.chat_id, video=handle
                        )
                else:
                    await context.bot.send_message(
                        chat_id=query.message.chat_id,
                        text=(
                            "ویدیوی زیرنویس‌دار از سقف ارسال تلگرام بزرگ‌تر شد و "
                            "ارسال نشد. فایل‌های زیرنویس بالا ارسال شده‌اند.\n"
                            "The subtitled video exceeds Telegram's upload cap, "
                            "so it was not sent. The subtitle files above are complete."
                        ),
                    )
            path_note = (
                "Transcript source: published captions"
                if result.path_used == "captions"
                else "Transcript source: Whisper transcription"
            )
            report_lines = ""
            if result.report is not None:
                r = result.report
                report_lines = (
                    f"\n📊 {r.cue_count} cues · "
                    f"over reading limit: {r.over_speed_percent:.0f}% · "
                    f"glossary applied: {r.glossary_applied}"
                    f"\nزیرنویس‌ها: {r.cue_count} · سریع‌تر از حد خواندن: "
                    f"{r.over_speed_percent:.0f}٪ · واژه‌نامه: {r.glossary_applied}"
                )
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"تمام شد ✅\nDone ✅\n{path_note}{report_lines}",
            )

    try:
        await run_job()
    except SubfaError as exc:
        code = str(exc)
        if code in ("too_long", "too_big", "too_large_upload"):
            en, fa = limit_message(code, settings)
            await context.bot.send_message(
                chat_id=query.message.chat_id, text=f"{fa}\n{en}"
            )
        else:
            await context.bot.send_message(
                chat_id=query.message.chat_id, text=friendly_error(code)
            )
    finally:
        poller.cancel()


def main() -> None:
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise SystemExit("BOT_TOKEN environment variable is not set.")
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(
        MessageHandler(filters.VIDEO | filters.AUDIO | filters.Document.ALL, on_file)
    )
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(CallbackQueryHandler(on_language, pattern=r"^lang:"))
    app.add_handler(CallbackQueryHandler(on_style, pattern=r"^style:"))
    app.run_polling()


if __name__ == "__main__":
    main()
