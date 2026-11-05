"""SubFa Telegram bot.

Run:
    BOT_TOKEN=... python -m bot.bot

The user sends a video, an audio file, a document, or pastes a video
link (YouTube and other yt-dlp sites). The bot asks for the subtitle
language with inline buttons, processes the file in a temporary
folder, sends back the subtitles, and deletes everything.

Each chat sees the bot in one UI language (Persian or English),
chosen with the language button on the start screen; the subtitle
language picked per job is a separate choice.

The token is read from the BOT_TOKEN environment variable only.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
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

from bot.premium import icon_id, pe, plain_markup, strip_premium_tags
from bot.routing import LangStore, classify_message, parse_ui_callback

settings = load_settings()
lang_store = LangStore(Path(tempfile.gettempdir()) / "subfa_lang_prefs.json")

# The public Bot API refuses bot downloads over 20 MB and bot uploads
# over 50 MB. A local Bot API server raises both; the code reports
# the effective cap honestly instead of failing mid job.
TELEGRAM_DOWNLOAD_CAP = 20 * 1024 * 1024
TELEGRAM_UPLOAD_CAP = 50 * 1024 * 1024

GITHUB_URL = "https://github.com/E30TZ/subfa"

TEXTS = {
    "fa": {
        "start": (
            "سلام! من SubFa هستم.\n"
            "یک ویدیو یا فایل صوتی بفرست، یا لینک ویدیو را پیست کن؛ "
            "زیرنویس فارسی، زیرنویس دوزبانه و متن کامل را تحویل بگیر.\n"
            "فایل‌ها روی همین سرور پردازش و بعد پاک می‌شوند."
        ),
        "help": (
            "فایل ویدیو یا صدا را بفرست، یا لینک ویدیو (یوتیوب و "
            "سایت‌های دیگر) را پیست کن.\n"
            "بعد زبان و سبک زیرنویس را انتخاب کن؛ فایل‌های زیرنویس و "
            "ویدیوی زیرنویس‌دار همین‌جا تحویل داده می‌شوند."
        ),
        "btn_help": "راهنما",
        "btn_github": "گیت‌هاب پروژه",
        "btn_start": "ساخت زیرنویس",
        "btn_back": "بازگشت",
        "howto": (
            "فایل ویدیو یا صدا را همین‌جا بفرست، یا لینک ویدیو را پیست کن. "
            "بقیه‌اش با من است."
        ),
        "no_video_note": (
            "نکته: یوتیوب فایل ویدیو را به سرورهای ناشناس نمی‌دهد، برای همین "
            "این بار فقط فایل‌های زیرنویس ساخته شدند. اگر خود فایل ویدیو را "
            "بفرستی، نسخه با زیرنویس چسبیده هم تحویل می‌گیری."
        ),
        "ask_subtitle_lang": "زبان زیرنویس را انتخاب کن:",
        "ask_style": "سبک زیرنویس روی ویدیو را انتخاب کن:",
        "expired": "این درخواست منقضی شده است. فایل یا لینک را دوباره بفرست.",
        "hint": "یک فایل ویدیو یا صدا بفرست، یا لینک ویدیو را پیست کن.",
        "started": "شروع شد",
        "done": "تمام شد ✅",
        "burned_too_big": (
            "ویدیوی زیرنویس‌دار از سقف ارسال تلگرام بزرگ‌تر شد و ارسال "
            "نشد. فایل‌های زیرنویس بالا ارسال شده‌اند."
        ),
        "path_captions": "منبع متن: زیرنویس منتشرشده",
        "path_whisper": "منبع متن: پیاده‌سازی صدا",
        "report": (
            "📊 زیرنویس‌ها: {n} · سریع‌تر از حد خواندن: {p}٪ · "
            "واژه‌نامه: {g}"
        ),
    },
    "en": {
        "start": (
            "Hi! I am SubFa.\n"
            "Send a video or audio file, or paste a video link; get "
            "Persian subtitles, a bilingual subtitle file and a "
            "transcript back.\n"
            "Files are processed on this server and deleted afterwards."
        ),
        "help": (
            "Send a video or audio file, or paste a video link "
            "(YouTube and other sites).\n"
            "Then pick the subtitle language and style; the subtitle "
            "files and the subtitled video are delivered right here."
        ),
        "btn_help": "Help",
        "btn_github": "Project on GitHub",
        "btn_start": "Make subtitles",
        "btn_back": "Back",
        "howto": (
            "Send the video or audio file right here, or paste a video "
            "link. The rest is on me."
        ),
        "no_video_note": (
            "Note: YouTube does not hand the video file to anonymous "
            "servers, so this time only the subtitle files were made. "
            "Send the video file itself and you also get the burned-in "
            "version."
        ),
        "ask_subtitle_lang": "Choose the subtitle language:",
        "ask_style": "Choose the burn-in style:",
        "expired": "This request expired. Send the file or link again.",
        "hint": "Send a video or audio file, or paste a video link.",
        "started": "Started",
        "done": "Done ✅",
        "burned_too_big": (
            "The subtitled video exceeds Telegram's upload cap, so it "
            "was not sent. The subtitle files above are complete."
        ),
        "path_captions": "Transcript source: published captions",
        "path_whisper": "Transcript source: Whisper transcription",
        "report": (
            "📊 {n} cues · over reading limit: {p}% · "
            "glossary applied: {g}"
        ),
    },
}

STAGE_TEXT = {
    "fa": {
        "download": "در حال دانلود",
        "extract": "در حال استخراج صدا",
        "transcribe": "در حال پیاده‌سازی صدا",
        "captions": "در حال خواندن زیرنویس منتشرشده",
        "translate": "در حال ترجمه",
        "write": "در حال ساخت فایل‌ها",
        "burn": "در حال چسباندن زیرنویس روی ویدیو",
        "done": "تمام شد",
    },
    "en": {
        "download": "Downloading",
        "extract": "Extracting audio",
        "transcribe": "Transcribing",
        "captions": "Reading published captions",
        "translate": "Translating",
        "write": "Writing files",
        "burn": "Burning subtitles",
        "done": "Done",
    },
}

ERROR_TEXT = {
    "no_speech": (
        "صدای گفتاری پیدا نشد. مطمئن شو فایل صدا دارد و دوباره بفرست.",
        "No speech was found. Check the file has audible speech and send it again.",
    ),
    "link": (
        "لینک خوانده نشد. لینک کامل صفحه ویدیو را بفرست و چند دقیقه دیگر دوباره تلاش کن.",
        "The link could not be read. Send the full video page link and try again in a few minutes.",
    ),
    "translator": (
        "بسته ترجمه روی این نصب آماده نیست. به مدیر بات اطلاع بده.",
        "The translation pack is not ready on this installation. Please tell the bot admin.",
    ),
    "engine": (
        "موتور پیاده‌سازی صدا روی این نصب آماده نیست. به مدیر بات اطلاع بده.",
        "The transcription engine is not ready on this installation. Please tell the bot admin.",
    ),
}


def t(lang: str, key: str) -> str:
    return TEXTS[lang][key]


def limit_text(code: str, lang: str) -> str:
    en, fa = limit_message(code, settings)
    return fa if lang == "fa" else en


def friendly_error(code: str, lang: str = "fa") -> str:
    """Turn engine errors into guidance a non developer can act on."""
    idx = 0 if lang == "fa" else 1
    lowered = code.lower()
    if "no speech" in lowered:
        return ERROR_TEXT["no_speech"][idx]
    if "could not read this link" in lowered or "download failed" in lowered:
        return ERROR_TEXT["link"][idx]
    if "argos" in lowered or "argostranslate" in lowered:
        return ERROR_TEXT["translator"][idx]
    if "faster-whisper" in lowered:
        return ERROR_TEXT["engine"][idx]
    return f"{'خطا' if lang == 'fa' else 'Error'}: {code}"


def start_text(lang: str) -> str:
    """Branded welcome: one premium emoji in the header line only."""
    return f"{pe('brand')} {t(lang, 'start')}"


def start_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Colour by meaning: primary for the main action, success for
    the outbound project link, default for navigation. One premium
    icon per button, never an icon plus a text emoji."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    t(lang, "btn_start"),
                    callback_data="howto",
                    style="primary",
                    icon_custom_emoji_id=icon_id("brand"),
                )
            ],
            [
                InlineKeyboardButton(
                    t(lang, "btn_help"),
                    callback_data="help",
                    icon_custom_emoji_id=icon_id("book"),
                ),
                InlineKeyboardButton(
                    "زبان | Language",
                    callback_data="uil",
                    icon_custom_emoji_id=icon_id("globe"),
                ),
            ],
            [
                InlineKeyboardButton(
                    t(lang, "btn_github"),
                    url=GITHUB_URL,
                    style="success",
                    icon_custom_emoji_id=icon_id("link"),
                )
            ],
        ]
    )


UI_PICKER_TEXT = "زبان بات را انتخاب کن / Choose the bot language:"
UI_PICKER_KEYBOARD = InlineKeyboardMarkup(
    [
        [InlineKeyboardButton("فارسی", callback_data="ui:fa")],
        [InlineKeyboardButton("English", callback_data="ui:en")],
        [
            InlineKeyboardButton(
                "بازگشت | Back",
                callback_data="uib",
                icon_custom_emoji_id=icon_id("back"),
            )
        ],
    ]
)

LANG_BUTTONS = [
    [InlineKeyboardButton("فارسی (پیش‌فرض) / Persian", callback_data="lang:fa")],
    [InlineKeyboardButton("English", callback_data="lang:en")],
    [InlineKeyboardButton("دوزبانه / Bilingual", callback_data="lang:bilingual")],
]

STYLE_BUTTONS = [
    [
        InlineKeyboardButton(
            "سینمایی / Cinema",
            callback_data="style:cinema",
            icon_custom_emoji_id=icon_id("brand"),
        )
    ],
    [InlineKeyboardButton("📱 ریلز عمودی / Reels 9:16", callback_data="style:reels")],
    [
        InlineKeyboardButton(
            "آموزشی دوزبانه / Learning",
            callback_data="style:learning",
            icon_custom_emoji_id=icon_id("book"),
        )
    ],
]


def ui_lang(update: Update) -> str:
    """The UI language for this chat: the stored choice, else the
    default from the user's Telegram language_code."""
    user = update.effective_user
    code = user.language_code if user else None
    chat = update.effective_chat
    return lang_store.get(chat.id if chat else 0, code)


async def _reply_screen(message, text: str, markup) -> None:
    """Send a branded screen; if Telegram rejects the premium
    cosmetics, retry once with them stripped."""
    try:
        await message.reply_text(text, parse_mode="HTML", reply_markup=markup)
    except Exception:
        await message.reply_text(
            strip_premium_tags(text), reply_markup=plain_markup(markup)
        )


async def _edit_screen(query, text: str, markup) -> None:
    """Edit into a branded screen, with the same one time cosmetic
    fallback as _reply_screen."""
    try:
        await query.edit_message_text(
            text, parse_mode="HTML", reply_markup=markup
        )
    except Exception:
        await query.edit_message_text(
            strip_premium_tags(text), reply_markup=plain_markup(markup)
        )


def _effective_download_cap() -> int:
    return min(settings.max_file_bytes, TELEGRAM_DOWNLOAD_CAP)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = ui_lang(update)
    await _reply_screen(
        update.message, start_text(lang), start_keyboard(lang)
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = ui_lang(update)
    await _reply_screen(update.message, t(lang, "help"), start_keyboard(lang))


async def on_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    lang = ui_lang(update)
    await _edit_screen(query, t(lang, "help"), start_keyboard(lang))


async def on_howto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    lang = ui_lang(update)
    await _edit_screen(query, t(lang, "howto"), start_keyboard(lang))


async def on_ui_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    lang = ui_lang(update)
    await _edit_screen(query, start_text(lang), start_keyboard(lang))


async def on_ui_picker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        UI_PICKER_TEXT, reply_markup=UI_PICKER_KEYBOARD
    )


async def on_ui_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    lang = parse_ui_callback(query.data)
    if lang is None:
        return
    lang_store.set(query.message.chat_id, lang)
    await _edit_screen(query, start_text(lang), start_keyboard(lang))


async def on_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    lang = ui_lang(update)
    attachment = message.video or message.audio or message.document
    if attachment is None:
        return
    if attachment.file_size and attachment.file_size > _effective_download_cap():
        await message.reply_text(limit_text("too_large_upload", lang))
        return
    file_name = getattr(attachment, "file_name", None) or "media.bin"
    context.user_data["pending"] = {
        "kind": "file",
        "file_id": attachment.file_id,
        "file_name": file_name,
    }
    await message.reply_text(
        t(lang, "ask_subtitle_lang"),
        reply_markup=InlineKeyboardMarkup(LANG_BUTTONS),
    )


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    kind, url = classify_message(update.message.text or "")
    if kind == "url":
        context.user_data["pending"] = {"kind": "url", "url": url}
        await update.message.reply_text(
            t(ui_lang(update), "ask_subtitle_lang"),
            reply_markup=InlineKeyboardMarkup(LANG_BUTTONS),
        )
    else:
        await update.message.reply_text(t(ui_lang(update), "hint"))


async def on_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    lang = ui_lang(update)
    choice = (query.data or "lang:fa").split(":", 1)[1]
    if "pending" not in context.user_data:
        await query.edit_message_text(t(lang, "expired"))
        return
    context.user_data["lang_choice"] = choice
    await query.edit_message_text(
        t(lang, "ask_style"), reply_markup=InlineKeyboardMarkup(STYLE_BUTTONS)
    )


async def on_style(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    lang = ui_lang(update)
    style = (query.data or "style:cinema").split(":", 1)[1]
    pending = context.user_data.pop("pending", None)
    choice = context.user_data.pop("lang_choice", "fa")
    if pending is None:
        await query.edit_message_text(t(lang, "expired"))
        return

    target = "fa" if choice in ("fa", "bilingual") else "en"
    bilingual_burn = choice == "bilingual" or style == "learning"
    status_message = await query.edit_message_text(t(lang, "started"))

    state = {"stage": "start", "fraction": 0.0}

    def progress(stage: str, fraction: float, note: str) -> None:
        state["stage"] = stage
        state["fraction"] = fraction

    percent_sign = "٪" if lang == "fa" else "%"

    async def poll_progress() -> None:
        last = ""
        while True:
            label = STAGE_TEXT[lang].get(state["stage"], state["stage"])
            text = f"{label} ({int(state['fraction'] * 100)}{percent_sign})"
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
                        text=t(lang, "burned_too_big"),
                    )
            if result.media_missing:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=t(lang, "no_video_note"),
                )
            path_note = t(
                lang,
                "path_captions" if result.path_used == "captions" else "path_whisper",
            )
            report_lines = ""
            if result.report is not None:
                r = result.report
                report_lines = "\n" + t(lang, "report").format(
                    n=r.cue_count,
                    p=f"{r.over_speed_percent:.0f}",
                    g=r.glossary_applied,
                )
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"{t(lang, 'done')}\n{path_note}{report_lines}",
            )

    try:
        await run_job()
    except SubfaError as exc:
        code = str(exc)
        if code in ("too_long", "too_big", "too_large_upload"):
            await context.bot.send_message(
                chat_id=query.message.chat_id, text=limit_text(code, lang)
            )
        else:
            await context.bot.send_message(
                chat_id=query.message.chat_id, text=friendly_error(code, lang)
            )
    finally:
        poller.cancel()


async def _post_init(app: Application) -> None:
    await app.bot.set_my_commands(
        [
            BotCommand("start", "شروع / Start"),
            BotCommand("help", "راهنما / Help"),
        ]
    )


def main() -> None:
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise SystemExit("BOT_TOKEN environment variable is not set.")
    app = Application.builder().token(token).post_init(_post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(
        MessageHandler(filters.VIDEO | filters.AUDIO | filters.Document.ALL, on_file)
    )
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(CallbackQueryHandler(on_language, pattern=r"^lang:"))
    app.add_handler(CallbackQueryHandler(on_style, pattern=r"^style:"))
    app.add_handler(CallbackQueryHandler(on_ui_set, pattern=r"^ui:"))
    app.add_handler(CallbackQueryHandler(on_ui_picker, pattern=r"^uil$"))
    app.add_handler(CallbackQueryHandler(on_help, pattern=r"^help$"))
    app.add_handler(CallbackQueryHandler(on_howto, pattern=r"^howto$"))
    app.add_handler(CallbackQueryHandler(on_ui_back, pattern=r"^uib$"))
    app.run_polling()


if __name__ == "__main__":
    main()
