"""Video link downloading through yt-dlp, behind a small interface.

A user pastes a link to a video page (YouTube or any site yt-dlp
supports). The downloader fetches the media at a capped quality,
plus the published captions when the site offers them. The pipeline
then treats the downloaded file exactly like an upload.

Tests use FakeDownloader, so the suite never touches the network.
"""

from __future__ import annotations

import os
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
    media_path: Path | None = None
    captions_path: Path | None = None
    captions_language: str | None = None
    # "manual" or "automatic" when the caption track's origin is
    # known; the pipeline derolls automatic tracks and reports it.
    captions_kind: str | None = None
    title: str = ""
    duration_seconds: float | None = None
    # Which route served the media file: "standard" for the main
    # player clients, "android-360" when YouTube's android client
    # fallback did, None when no media was served at all.
    media_route: str | None = None


class Downloader:
    name = "base"

    def download(self, url: str, dest_dir: Path, settings) -> DownloadResult:
        raise NotImplementedError


class FakeDownloader(Downloader):
    """Offline downloader for tests: copies local fixtures into place."""

    name = "fake"

    def __init__(self, media_path, captions_path=None, captions_language="en",
                 title="Fake video", duration_seconds=30.0, captions_kind=None):
        self.media_path = Path(media_path)
        self.captions_path = Path(captions_path) if captions_path else None
        self.captions_language = captions_language
        self.captions_kind = captions_kind
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
            captions_kind=self.captions_kind if captions_dest else None,
            title=self.title,
            duration_seconds=self.duration_seconds,
        )


def base_options() -> dict:
    """yt-dlp options shared by every pass.

    When the environment names a CA bundle (SSL_CERT_FILE or
    REQUESTS_CA_BUNDLE, e.g. behind a TLS-intercepting egress
    proxy), yt-dlp must use the system trust store instead of
    certifi: its "no-certifi" compat opt makes it call
    load_default_certs(), which honours SSL_CERT_FILE. Without
    this, every HTTPS request dies with CERTIFICATE_VERIFY_FAILED.
    """
    options = {"quiet": True, "no_warnings": True}
    if os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE"):
        options["compat_opts"] = ["no-certifi"]
    # YouTube's default player clients are bot-checked on datacenter
    # IPs ("Sign in to confirm you're not a bot"). The web/mweb/ios
    # clients still answer from such IPs with real formats and caption
    # tracks, so prefer them; the key only affects the youtube
    # extractor, every other site is untouched.
    options["extractor_args"] = {
        "youtube": {"player_client": ["web", "mweb", "ios"]}
    }
    return options


YOUTUBE_HOSTS = (
    "youtube.com",
    "youtu.be",
    "youtube-nocookie.com",
)


def _is_youtube_url(url: str) -> bool:
    """True for YouTube watch/share links (any subdomain counts)."""
    from urllib.parse import urlparse

    host = (urlparse(url).hostname or "").lower()
    return any(
        host == domain or host.endswith("." + domain)
        for domain in YOUTUBE_HOSTS
    )


def _language_rank(language: str) -> int:
    """Persian first (a Persian track skips translation entirely,
    the best quality path), English next, everything else after."""
    base = language.split("-")[0].lower()
    if base == "fa":
        return 0
    if base == "en":
        return 1
    return 2


def choose_caption_tracks(info: dict) -> list[tuple[str, str, str]]:
    """All usable caption tracks from yt-dlp metadata, best first.

    Preference order: manual Persian, manual other, automatic
    Persian, automatic other. The SRT rendering of a track wins
    over VTT; tracks without a downloadable rendering are skipped.
    The fetcher walks this list, so a track whose URL the site
    refuses (YouTube rate limits some auto translated tracks)
    falls through to the next candidate instead of failing the job.
    """
    candidates: list[tuple[str, str, str]] = []
    for kind, key in (("manual", "subtitles"), ("automatic", "automatic_captions")):
        tracks = info.get(key) or {}
        languages = sorted(tracks, key=_language_rank)
        for language in languages:
            entries = tracks.get(language) or []
            for ext in ("srt", "vtt"):
                url = next(
                    (
                        entry.get("url")
                        for entry in entries
                        if entry.get("ext") == ext and entry.get("url")
                    ),
                    None,
                )
                if url:
                    candidates.append(
                        (kind, language.split("-")[0].lower(), url)
                    )
                    break
    return candidates


def choose_caption_track(info: dict) -> tuple[str, str, str] | None:
    """The single best caption track, or None."""
    candidates = choose_caption_tracks(info)
    return candidates[0] if candidates else None


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

    @staticmethod
    def _find_media_file(dest_dir: Path) -> Path | None:
        """The media file a download pass left behind, or None.

        Caption files and partial downloads never count; when
        several files qualify, the largest is the real media."""
        media_files = sorted(
            p for p in dest_dir.iterdir()
            if p.is_file() and p.suffix.lower() not in (".srt", ".vtt", ".part")
            and not p.name.endswith(".part")
        )
        if not media_files:
            return None
        return max(media_files, key=lambda p: p.stat().st_size)

    def download(self, url, dest_dir, settings):
        yt_dlp = self._ydl()
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        max_height = settings.download_max_height

        # Pass 1: metadata only, so limits are checked before any
        # large file moves. ignore_no_formats_error keeps metadata
        # and caption tracks readable on hosts where the site gates
        # the media formats themselves (YouTube on datacenter IPs).
        meta_options = {**base_options(), "ignore_no_formats_error": True}
        with yt_dlp.YoutubeDL(meta_options) as ydl:
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
            **base_options(),
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
        media_route = None
        primary_error = None
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                ydl.download([url])
        except Exception as exc:
            primary_error = exc
        media_path = self._find_media_file(dest_dir)
        if media_path is not None:
            media_route = "standard"
        elif _is_youtube_url(url):
            # YouTube bot-gates every player client for media on
            # datacenter IPs except one: the android client still
            # serves format 18, a progressive 360p MP4 with audio.
            # A 360p video that can carry burned subtitles beats
            # captions alone, so retry once through it.
            android_options = {
                **base_options(),
                "extractor_args": {
                    "youtube": {"player_client": ["android"]}
                },
                "outtmpl": str(dest_dir / "source.%(ext)s"),
                "format": "18/best[height<=360]/best",
                "merge_output_format": "mp4",
                "max_filesize": settings.max_download_bytes,
            }
            try:
                with yt_dlp.YoutubeDL(android_options) as ydl:
                    ydl.download([url])
            except Exception:
                pass
            media_path = self._find_media_file(dest_dir)
            if media_path is not None:
                media_route = "android-360"
        if media_path is None:
            # Media gated everywhere it was tried: the caption
            # tracks from pass 1 are still fetchable, and subtitles
            # alone beat nothing.
            fallback = self._fetch_caption_track(info, dest_dir)
            if fallback is not None:
                captions_path, captions_language, captions_kind = fallback
                return DownloadResult(
                    media_path=None,
                    captions_path=captions_path,
                    captions_language=captions_language,
                    captions_kind=captions_kind,
                    title=title,
                    duration_seconds=float(duration) if duration else None,
                )
            if primary_error is not None:
                raise SubfaError(
                    f"Download failed: {primary_error}"
                ) from primary_error
            raise SubfaError("Download finished but no media file was produced.")
        if media_path.stat().st_size > settings.max_download_bytes:
            raise SubfaError("too_big")

        # The caption track is chosen from the pass 1 metadata by
        # the documented preference order and fetched directly, so
        # the choice (and its manual/automatic origin) is known.
        # Only when that fetch fails do we fall back to whatever
        # caption files the media pass wrote.
        captions_path = None
        captions_language = None
        captions_kind = None
        fetched = self._fetch_caption_track(info, dest_dir)
        if fetched is not None:
            captions_path, captions_language, captions_kind = fetched
        else:
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
            captions_kind=captions_kind,
            title=title,
            duration_seconds=float(duration) if duration else None,
            media_route=media_route,
        )


    def _fetch_caption_track(self, info: dict, dest_dir: Path):
        """Fetch the chosen caption track straight from the pass-1
        metadata. Returns (path, language, kind) or None, where kind
        is "manual" or "automatic". The fetch honours the environment
        CA bundle like every other request here."""
        import ssl
        import urllib.request

        candidates = choose_caption_tracks(info)
        if not candidates:
            return None
        context = ssl.create_default_context()
        bundle = os.environ.get("SSL_CERT_FILE") or os.environ.get(
            "REQUESTS_CA_BUNDLE"
        )
        if bundle:
            try:
                context.load_verify_locations(bundle)
            except (OSError, ssl.SSLError):
                pass
        for kind, language, url in candidates:
            request = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0"}
            )
            try:
                with urllib.request.urlopen(
                    request, context=context, timeout=30
                ) as response:
                    raw = response.read()
            except Exception:
                continue
            text = raw.decode("utf-8", errors="replace")
            if "-->" not in text:
                continue
            ext = "vtt" if text.lstrip().startswith("WEBVTT") else "srt"
            path = dest_dir / f"source.{language}.{ext}"
            path.write_text(text, encoding="utf-8")
            return path, language, kind
        return None


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
