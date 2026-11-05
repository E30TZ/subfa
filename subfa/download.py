"""Video link downloading through yt-dlp, behind a small interface.

A user pastes a link to a video page (YouTube or any site yt-dlp
supports). The downloader fetches the media at a capped quality,
plus the published captions when the site offers them. The pipeline
then treats the downloaded file exactly like an upload.

Tests use FakeDownloader, so the suite never touches the network.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from . import SubfaError
from .srt import Cue, parse_srt

URL_RE = re.compile(r"https?://[^\s<>\]]+", re.IGNORECASE)


def is_url(value: str) -> bool:
    """True when the value looks like a single http(s) link."""
    value = value.strip()
    return bool(re.fullmatch(r"https?://\S+", value, flags=re.IGNORECASE))


def extract_url(text: str) -> str | None:
    """Pull the first link out of a chat message, or return None."""
    match = URL_RE.search(text or "")
    if not match:
        return None
    return match.group(0).rstrip(").,!")


@dataclass
class DownloadResult:
    media_path: Path
    captions_path: Path | None = None
    captions_language: str | None = None
    title: str = ""
    duration_seconds: float | None = None


class Downloader:
    name = "base"

    def download(self, url: str, dest_dir: Path, settings) -> DownloadResult:
        raise NotImplementedError


class FakeDownloader(Downloader):
    """Offline downloader for tests: copies local fixtures into place."""

    name = "fake"

    def __init__(self, media_path, captions_path=None, captions_language="en",
                 title="Fake video", duration_seconds=30.0):
        self.media_path = Path(media_path)
        self.captions_path = Path(captions_path) if captions_path else None
        self.captions_language = captions_language
        self.title = title
        self.duration_seconds = duration_seconds
        self.calls: list[str] = []

    def download(self, url, dest_dir, settings):
        self.calls.append(url)
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        if self.duration_seconds and self.duration_seconds > settings.max_duration_seconds:
            raise SubfaError("too_long")
        media_dest = dest_dir / self.media_path.name
        shutil.copyfile(self.media_path, media_dest)
        captions_dest = None
        if self.captions_path is not None:
            captions_dest = dest_dir / self.captions_path.name
            shutil.copyfile(self.captions_path, captions_dest)
        return DownloadResult(
            media_path=media_dest,
            captions_path=captions_dest,
            captions_language=self.captions_language if captions_dest else None,
            title=self.title,
            duration_seconds=self.duration_seconds,
        )


class YtDlpDownloader(Downloader):
    """Real downloader backed by yt-dlp (Python API)."""

    name = "yt-dlp"

    def _ydl(self):
        try:
            import yt_dlp
        except ImportError as exc:
            raise SubfaError(
                "yt-dlp is not installed. Install it with: pip install yt-dlp"
            ) from exc
        return yt_dlp

    def download(self, url, dest_dir, settings):
        yt_dlp = self._ydl()
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        max_height = settings.download_max_height

        # Pass 1: metadata only, so limits are checked before any
        # large file moves.
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
            except Exception as exc:
                raise SubfaError(f"Could not read this link: {exc}") from exc
        duration = info.get("duration")
        if duration and duration > settings.max_duration_seconds:
            raise SubfaError("too_long")
        title = info.get("title", "")

        # Pass 2: download media at a capped quality (subtitling does
        # not need 4K) and the published captions when they exist.
        options = {
            "quiet": True,
            "no_warnings": True,
            "outtmpl": str(dest_dir / "source.%(ext)s"),
            "format": (
                f"bv*[height<={max_height}]+ba/"
                f"b[height<={max_height}]/b/best"
            ),
            "merge_output_format": "mp4",
            "max_filesize": settings.max_download_bytes,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitlesformat": "srt/vtt/best",
            "skip_download": False,
        }
        with yt_dlp.YoutubeDL(options) as ydl:
            try:
                ydl.download([url])
            except Exception as exc:
                raise SubfaError(f"Download failed: {exc}") from exc

        media_files = sorted(
            p for p in dest_dir.iterdir()
            if p.is_file() and p.suffix.lower() not in (".srt", ".vtt", ".part")
            and not p.name.endswith(".part")
        )
        if not media_files:
            raise SubfaError("Download finished but no media file was produced.")
        media_path = max(media_files, key=lambda p: p.stat().st_size)
        if media_path.stat().st_size > settings.max_download_bytes:
            raise SubfaError("too_big")

        captions_path = None
        captions_language = None
        caption_files = sorted(
            list(dest_dir.glob("*.srt")) + list(dest_dir.glob("*.vtt"))
        )
        if caption_files:
            captions_path = caption_files[0]
            # yt-dlp names caption files like source.en.srt
            parts = captions_path.stem.split(".")
            if len(parts) > 1:
                captions_language = parts[-1].split("-")[0]
        return DownloadResult(
            media_path=media_path,
            captions_path=captions_path,
            captions_language=captions_language,
            title=title,
            duration_seconds=float(duration) if duration else None,
        )


def load_caption_cues(captions_path: str | Path) -> list[Cue]:
    """Parse a downloaded captions file (SRT or VTT) into cues.

    Returns an empty list when the file is unusable, so the caller
    can fall back to transcription without special error handling.
    """
    path = Path(captions_path)
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    text = raw.replace("\r\n", "\n")
    if path.suffix.lower() == ".vtt":
        lines = []
        for line in text.splitlines():
            if line.startswith(("WEBVTT", "NOTE", "Kind:", "Language:", "STYLE")):
                continue
            lines.append(line)
        text = "\n".join(lines)
    try:
        cues = parse_srt(text)
    except ValueError:
        return []
    total_chars = sum(len(c.text) for c in cues)
    if len(cues) < 3 or total_chars < 20:
        return []
    return cues


def make_downloader(settings) -> Downloader:
    return YtDlpDownloader()
