"""Command line interface.

Examples:
    subfa lecture.mp4
    subfa https://www.youtube.com/watch?v=... --target fa --burn
    subfa talk.mp3 --url https://example.com/talk --translator none
    subfa lesson.mkv --glossary programming --bilingual -o out/
    subfa download-models   (fetch all ASR models for offline runs)
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from . import SubfaError
from .config import load_settings
from .download import is_url, make_downloader
from .messages import limit_message
from .pipeline import Pipeline
from .transcribe import make_engine
from .translate import make_translator

STAGE_LABELS = {
    "download": "Downloading",
    "extract": "Extracting audio",
    "transcribe": "Transcribing (ASR)",
    "captions": "Reading published captions",
    "translate": "Translating",
    "write": "Writing subtitle files",
    "burn": "Burning subtitles into the video",
    "done": "Done",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="subfa",
        description=(
            "SubFa: make subtitles from a video or audio file, or from "
            "a video link. Persian by default. Everything runs locally."
        ),
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="A media file path, or a video page link (YouTube and other yt-dlp sites).",
    )
    parser.add_argument(
        "--url",
        help="A video page link, as an alternative to the positional input.",
    )
    parser.add_argument("--target", default=None,
                        help="Subtitle language code (default: fa).")
    parser.add_argument("--source", default="auto",
                        help="Source language code, or auto (default: auto).")
    parser.add_argument("--model", default=None,
                        help="faster-whisper model for non-Persian audio (default: large-v3-turbo). Persian audio uses the Persian fine-tuned model instead.")
    parser.add_argument("--asr-engine", choices=["auto", "persian", "whisper"], default=None,
                        help="Speech recognition routing: auto (default, Persian audio to the Persian fine-tuned model, everything else to faster-whisper), persian or whisper.")
    parser.add_argument("--translator", choices=["argos", "llm", "none"], default=None,
                        help="Translation engine: argos (offline, default), llm (OpenAI-compatible endpoint, needs SUBFA_LLM_BASE_URL and SUBFA_LLM_MODEL), or none.")
    parser.add_argument("--glossary", default="",
                        help="Comma separated glossary names, for example: programming,general")
    parser.add_argument("--burn", action="store_true",
                        help="Also produce the video with subtitles burned in.")
    parser.add_argument("--bilingual", action="store_true",
                        help="Burn the bilingual subtitles (source plus translation) instead of the target ones.")
    parser.add_argument("--style", choices=["cinema", "reels", "learning"], default=None,
                        help="Burn-in style preset: cinema (default), reels (vertical 9:16 safe area), learning (bilingual, source smaller above translation).")
    parser.add_argument("--quality", choices=["source", "720", "480", "360"], default="720",
                        help="Video quality: caps the link download height and the burned video height (default: 720). 'source' keeps the original resolution.")
    parser.add_argument("--tone", choices=["auto", "formal", "informal", "simple"], default="auto",
                        help="Persian subtitle tone: auto (default, informal only when the text already sounds colloquial), formal, informal (colloquial softening), simple (shorter cues, one idea each).")
    parser.add_argument("-o", "--out", default="subfa-out",
                        help="Output folder (default: subfa-out). For links, a work folder.")
    return parser


def _download_models_main() -> int:
    from .models import download_models

    settings = load_settings()
    try:
        download_models(settings)
    except SubfaError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "download-models":
        return _download_models_main()
    args = build_parser().parse_args(argv)
    settings = load_settings()
    if args.model:
        settings.model = args.model
    if args.asr_engine:
        settings.asr_engine = args.asr_engine
    if args.translator:
        settings.translator = args.translator

    link = args.url or (args.input if args.input and is_url(args.input) else None)
    file_input = None if link else args.input
    if not link and not file_input:
        print("Give me a media file or a video link. See: subfa --help",
              file=sys.stderr)
        return 2

    def progress(stage: str, fraction: float, note: str) -> None:
        label = STAGE_LABELS.get(stage, stage)
        extra = f" ({note})" if note else ""
        print(f"[{int(fraction * 100):3d}%] {label}{extra}")

    pipeline = Pipeline(
        settings=settings,
        engine=make_engine(settings),
        translator=make_translator(settings),
        downloader=make_downloader(settings) if link else None,
        progress=progress,
    )
    glossaries = [g.strip() for g in args.glossary.split(",") if g.strip()]
    try:
        if link:
            with tempfile.TemporaryDirectory(prefix="subfa-link-") as tmp:
                result = pipeline.run_url(
                    link,
                    out_dir=Path(args.out),
                    download_dir=Path(tmp) / "download",
                    target=args.target,
                    source=args.source,
                    glossaries=glossaries,
                    burn=args.burn,
                    bilingual_burn=args.bilingual,
                    style=args.style,
                    quality=args.quality,
                    tone=args.tone,
                )
        else:
            result = pipeline.run_file(
                file_input,
                out_dir=Path(args.out),
                target=args.target,
                source=args.source,
                glossaries=glossaries,
                burn=args.burn,
                bilingual_burn=args.bilingual,
                style=args.style,
                quality=args.quality,
                tone=args.tone,
            )
    except SubfaError as exc:
        code = str(exc)
        if code in ("too_long", "too_big", "too_large_upload"):
            en, fa = limit_message(code, settings)
            print(f"Error: {en}\n{fa}", file=sys.stderr)
        else:
            print(f"Error: {code}", file=sys.stderr)
        return 1

    print(f"Transcript source: {result.path_used}")
    if result.text_source:
        print(f"Text source: {result.text_source}")
    if result.caption_track:
        print(f"Caption track: {result.caption_track}")
    print(f"Quality: {result.quality} · Tone: {result.tone_requested} -> {result.tone_resolved}")
    for kind, path in result.outputs.items():
        print(f"{kind}: {path}")
    if result.report is not None:
        r = result.report
        print(
            f"Quality: {r.cue_count} cues, "
            f"{r.over_speed_percent:.1f}% over the reading speed limit, "
            f"glossary terms applied: {r.glossary_applied} "
            f"(full report in the report.txt output)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
