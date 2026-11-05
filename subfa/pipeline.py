"""The SubFa pipeline: media in, subtitles out.

One code path serves an uploaded file and a downloaded link alike:

    (optional download) -> captions fast path OR extract audio ->
    transcribe -> segment into cues -> translate -> glossary ->
    write SRT + bilingual SRT + transcript -> optional burn-in

Progress is reported through a callback with stage names so the
CLI, the bot and the web app can each render it their own way.
Stage names: download, extract, transcribe, captions, translate,
write, burn, done. The result records which transcript path was
used ("captions" or "whisper") so users can be told honestly.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import SubfaError
from .bilingual import merge_bilingual
from .burn import burn_subtitles
from .config import Settings, is_video
from .download import Downloader, load_caption_cues
from .fa_text import clean_fa_text
from .glossary import apply_glossary_counted, load_glossary
from .report import QualityReport, build_report
from .srt import Cue, cues_to_srt, segment_to_cues
from .translate import NoneTranslator, Translator, translate_with_context
from .transcribe import TranscriptionEngine

ProgressCallback = Callable[[str, float, str], None]


def _noop_progress(stage: str, fraction: float, note: str) -> None:
    pass


@dataclass
class JobResult:
    outputs: dict[str, Path] = field(default_factory=dict)
    source_language: str = ""
    target_language: str = ""
    path_used: str = ""  # "captions" or "whisper"
    media_missing: bool = False  # link jobs whose media was gated
    title: str = ""
    cue_count: int = 0
    report: QualityReport | None = None


class Pipeline:
    def __init__(
        self,
        settings: Settings,
        engine: TranscriptionEngine,
        translator: Translator,
        downloader: Downloader | None = None,
        progress: ProgressCallback | None = None,
    ):
        self.settings = settings
        self.engine = engine
        self.translator = translator
        self.downloader = downloader
        self.progress = progress or _noop_progress

    # -- entry points -------------------------------------------------

    def run_file(
        self,
        input_path: str | Path,
        out_dir: str | Path,
        target: str | None = None,
        source: str = "auto",
        glossaries: list[str] | None = None,
        burn: bool = False,
        bilingual_burn: bool = False,
        style: str | None = None,
    ) -> JobResult:
        input_path = Path(input_path)
        if not input_path.exists():
            raise SubfaError(f"File not found: {input_path}")
        if input_path.stat().st_size > self.settings.max_file_bytes:
            raise SubfaError("too_large_upload")
        return self._process(
            media_path=input_path,
            out_dir=Path(out_dir),
            target=target or self.settings.default_target,
            source=source,
            glossaries=glossaries or [],
            burn=burn,
            bilingual_burn=bilingual_burn,
            captions_path=None,
            captions_language=None,
            title="",
            style=style or self.settings.style,
        )

    def run_url(
        self,
        url: str,
        out_dir: str | Path,
        download_dir: str | Path,
        target: str | None = None,
        source: str = "auto",
        glossaries: list[str] | None = None,
        burn: bool = False,
        bilingual_burn: bool = False,
        style: str | None = None,
    ) -> JobResult:
        """Download a link into download_dir, process it, write outputs
        to out_dir. Callers delete download_dir with the job, so the
        downloaded media never lingers."""
        if self.downloader is None:
            raise SubfaError("Link input is not enabled in this installation.")
        download_dir = Path(download_dir)
        self.progress("download", 0.05, "")
        downloaded = self.downloader.download(url, download_dir, self.settings)
        note = "captions" if downloaded.captions_path else "whisper"
        self.progress("download", 0.2, note)
        return self._process(
            media_path=downloaded.media_path,
            out_dir=Path(out_dir),
            target=target or self.settings.default_target,
            source=source,
            glossaries=glossaries or [],
            burn=burn,
            bilingual_burn=bilingual_burn,
            captions_path=downloaded.captions_path,
            captions_language=downloaded.captions_language,
            title=downloaded.title,
            style=style or self.settings.style,
        )

    # -- internals ----------------------------------------------------

    def _extract_audio(self, media_path: Path, work_dir: Path) -> Path:
        audio_path = work_dir / "audio.wav"
        command = [
            "ffmpeg", "-y",
            "-i", str(media_path),
            "-vn", "-ac", "1", "-ar", "16000",
            str(audio_path),
        ]
        completed = subprocess.run(command, capture_output=True, text=True)
        if completed.returncode != 0 or not audio_path.exists():
            raise SubfaError(
                "Could not extract audio from this file. "
                "It may be damaged or in a format ffmpeg cannot read."
            )
        return audio_path

    def _source_cues(
        self,
        media_path: Path | None,
        work_dir: Path,
        source: str,
        captions_path: Path | None,
        captions_language: str | None,
    ) -> tuple[list[Cue], str, str, str]:
        """Return (source cues, source language, path used, engine info)."""
        if captions_path is not None and self.settings.captions_fast_path:
            cues = load_caption_cues(captions_path)
            if cues:
                self.progress("captions", 0.35, "captions")
                language = captions_language or (
                    source if source != "auto" else "en"
                )
                return cues, language, "captions", f"captions ({language})"
            self.progress("captions", 0.3, "fallback")
        if media_path is None:
            raise SubfaError(
                "The video file could not be downloaded from this "
                "link and it has no usable captions."
            )
        self.progress("extract", 0.35, "")
        audio_path = self._extract_audio(media_path, work_dir)
        self.progress("transcribe", 0.45, "whisper")
        result = self.engine.transcribe(
            audio_path, None if source == "auto" else source
        )
        cues = segment_to_cues(result.segments)
        if result.engine:
            engine_info = f"{result.engine} / {result.model}"
        else:
            engine_info = f"{self.engine.name} / {self.settings.model}"
        return cues, result.language, "whisper", engine_info

    def _process(
        self,
        media_path: Path | None,
        out_dir: Path,
        target: str,
        source: str,
        glossaries: list[str],
        burn: bool,
        bilingual_burn: bool,
        captions_path: Path | None,
        captions_language: str | None,
        title: str,
        style: str,
    ) -> JobResult:
        out_dir.mkdir(parents=True, exist_ok=True)
        work_dir = out_dir / "_work"
        work_dir.mkdir(parents=True, exist_ok=True)
        if media_path is not None:
            stem = media_path.stem
        else:
            slug = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-")[:48]
            stem = slug or "video"

        source_cues, source_language, path_used, engine_info = self._source_cues(
            media_path, work_dir, source, captions_path, captions_language
        )
        if not source_cues:
            raise SubfaError(
                "No speech was found in this file and no usable captions "
                "were available."
            )
        if source_language == "fa":
            source_cues = [
                Cue(c.start, c.end, clean_fa_text(c.text, digits=self.settings.digit_mode))
                for c in source_cues
            ]

        glossary = (
            load_glossary(glossaries, self.settings.glossary_dir)
            if glossaries
            else {}
        )

        outputs: dict[str, Path] = {}
        translated_texts: list[str] | None = None
        target_cues = source_cues
        glossary_applied = 0
        if target != source_language and not isinstance(self.translator, NoneTranslator):
            self.progress("translate", 0.6, "")
            raw = translate_with_context(
                self.translator,
                [cue.text for cue in source_cues],
                source_language,
                target,
            )
            if target == "fa":
                raw = [
                    clean_fa_text(text, digits=self.settings.digit_mode)
                    for text in raw
                ]
            translated_texts = []
            for text in raw:
                cleaned, count = apply_glossary_counted(text, glossary)
                translated_texts.append(cleaned)
                glossary_applied += count
            target_cues = [
                Cue(cue.start, cue.end, text)
                for cue, text in zip(source_cues, translated_texts)
            ]
        elif glossary:
            counted = [
                apply_glossary_counted(cue.text, glossary) for cue in source_cues
            ]
            glossary_applied = sum(count for _, count in counted)
            target_cues = [
                Cue(cue.start, cue.end, text)
                for cue, (text, _) in zip(source_cues, counted)
            ]

        self.progress("write", 0.75, "")
        target_srt = out_dir / f"{stem}.{target}.srt"
        target_srt.write_text(cues_to_srt(target_cues), encoding="utf-8")
        outputs["srt"] = target_srt

        primary_cues = target_cues
        if translated_texts is not None:
            bilingual_cues = merge_bilingual(source_cues, translated_texts)
            bilingual_srt = out_dir / f"{stem}.bilingual.srt"
            bilingual_srt.write_text(cues_to_srt(bilingual_cues), encoding="utf-8")
            outputs["bilingual"] = bilingual_srt
            if bilingual_burn:
                primary_cues = bilingual_cues

        transcript = out_dir / f"{stem}.transcript.txt"
        transcript.write_text(
            "\n".join(cue.text for cue in source_cues), encoding="utf-8"
        )
        outputs["transcript"] = transcript

        if burn:
            if media_path is None:
                self.progress("burn", 0.85, "skipped-no-video")
            elif not is_video(media_path):
                self.progress("burn", 0.85, "skipped-audio")
            else:
                self.progress("burn", 0.85, "")
                burned = burn_subtitles(
                    media_path,
                    primary_cues,
                    out_dir / f"{stem}.subbed.mp4",
                    font=self.settings.subtitle_font,
                    work_dir=work_dir,
                    style=style,
                )
                outputs["burned"] = burned

        report = build_report(
            target_cues,
            path_used=path_used,
            model=engine_info,
            glossary_applied=glossary_applied,
            source_language=source_language,
            target_language=target,
        )
        report_path = out_dir / f"{stem}.report.txt"
        report_path.write_text(report.to_text(), encoding="utf-8")
        outputs["report"] = report_path

        self.progress("done", 1.0, path_used)
        return JobResult(
            outputs=outputs,
            source_language=source_language,
            target_language=target,
            path_used=path_used,
            media_missing=media_path is None,
            title=title,
            cue_count=len(source_cues),
            report=report,
        )
