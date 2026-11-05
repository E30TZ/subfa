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
    # player clients, "invidious-<height>" when a public Invidious
    # instance proxied it, "android-360" when YouTube's android
    # client fallback did, None when no media was served at all.
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

# Public Invidious instances used as the high quality YouTube media
# route. An instance's API, asked with local=true, returns stream
# URLs proxied through the instance itself, so the bytes never come
# from a gated googlevideo host and no account or cookies are
# needed. Instances are community servers: any of them can be slow
# or down, so the route tries each in order and quietly gives up.
# Override the list with SUBFA_INVIDIOUS_INSTANCES (comma separated)
# or disable the route with SUBFA_DISABLE_INVIDIOUS=1.
DEFAULT_INVIDIOUS_INSTANCES = (
    "https://yt.chocolatemoo53.com",
    "https://inv.nadeko.net",
    "https://invidious.nerdvpn.de",
)

# itags whose video encoding is H.264 (the family that always
# stream-copies cleanly into an MP4 container).
H264_ITAGS = {"133", "134", "135", "136", "137", "160", "298", "299"}


def invidious_instances() -> list[str]:
    """The configured Invidious instance base URLs, in try order.

    Empty when the route is disabled via SUBFA_DISABLE_INVIDIOUS."""
    if os.environ.get("SUBFA_DISABLE_INVIDIOUS", "").strip() in (
        "1", "true", "yes", "on",
    ):
        return []
    raw = os.environ.get("SUBFA_INVIDIOUS_INSTANCES", "")
    if raw.strip():
        return [
            part.strip().rstrip("/")
            for part in raw.split(",")
            if part.strip()
        ]
    return list(DEFAULT_INVIDIOUS_INSTANCES)


def youtube_video_id(url: str) -> str | None:
    """The video id of a YouTube link, or None when it has none."""
    from urllib.parse import parse_qs, urlparse

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host == "youtu.be" or host.endswith(".youtu.be"):
        candidate = parsed.path.lstrip("/").split("/")[0]
        return candidate or None
    if not _is_youtube_url(url):
        return None
    values = parse_qs(parsed.query).get("v")
    if values and values[0]:
        return values[0]
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 2 and parts[0] in ("shorts", "embed", "live", "v"):
        return parts[1]
    return None


def _ssl_context():
    """TLS context honouring the environment CA bundle, like the
    caption fetch: behind a TLS-intercepting egress proxy the env
    names the bundle plain urllib must verify against."""
    import ssl

    context = ssl.create_default_context()
    bundle = os.environ.get("SSL_CERT_FILE") or os.environ.get(
        "REQUESTS_CA_BUNDLE"
    )
    if bundle:
        try:
            context.load_verify_locations(bundle)
        except (OSError, ssl.SSLError):
            pass
    return context


def _format_height(fmt: dict) -> int:
    """Pixel height of an Invidious adaptive format (0 if unknown)."""
    for key in ("resolution", "qualityLabel"):
        match = re.match(r"(\d+)p", str(fmt.get(key) or ""))
        if match:
            return int(match.group(1))
    return 0


def _format_codec(fmt: dict) -> str:
    """Normalised codec name of an Invidious adaptive format."""
    encoding = str(fmt.get("encoding") or "").lower()
    if encoding:
        if encoding.startswith("av01") or encoding.startswith("av1"):
            return "av1"
        return encoding
    mime = str(fmt.get("type") or "")
    if "avc1" in mime:
        return "h264"
    if "vp09" in mime or "vp9" in mime:
        return "vp9"
    if "av01" in mime:
        return "av1"
    if "mp4a" in mime:
        return "aac"
    if "opus" in mime:
        return "opus"
    return ""


def choose_invidious_streams(
    formats: list[dict], max_height: int
) -> tuple[dict, dict, int] | None:
    """Pick (video, audio, height) from Invidious adaptive formats.

    The video is the best H.264 stream at or under the height cap
    (H.264 stream-copies into MP4 without surprises); when no H.264
    stream fits the cap, the best stream overall under the cap
    wins. A height is never picked above the cap. The audio is the
    itag 140 AAC track when present, else the first audio format.
    """
    videos = [
        fmt for fmt in formats
        if str(fmt.get("type") or "").startswith("video") and fmt.get("url")
    ]
    audios = [
        fmt for fmt in formats
        if str(fmt.get("type") or "").startswith("audio") and fmt.get("url")
    ]
    if not videos or not audios:
        return None

    def rank(fmt: dict) -> tuple[int, int, int]:
        try:
            bitrate = int(fmt.get("bitrate") or 0)
        except (TypeError, ValueError):
            bitrate = 0
        return (_format_height(fmt), int(fmt.get("fps") or 0), bitrate)

    under_cap = [fmt for fmt in videos if _format_height(fmt) <= max_height]
    if not under_cap:
        return None
    h264 = [
        fmt for fmt in under_cap
        if _format_codec(fmt) == "h264" or str(fmt.get("itag")) in H264_ITAGS
    ]
    video = max(h264 or under_cap, key=rank)
    audio = next(
        (fmt for fmt in audios if str(fmt.get("itag")) == "140"),
        audios[0],
    )
    return video, audio, _format_height(video)


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
            # High quality route: public Invidious instances proxy
            # the media bytes through their own hosts, which
            # YouTube's datacenter gate never sees. Any failure
            # here simply falls through to the android route below.
            invidious = self._fetch_invidious_media(url, dest_dir, settings)
            if invidious is not None:
                media_path, media_route = invidious
        if media_path is None and _is_youtube_url(url):
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


    def _invidious_video_info(self, instance: str, video_id: str) -> dict:
        """One instance's video JSON. local=true makes the returned
        stream URLs proxy through the instance host itself."""
        import json
        import urllib.request

        url = f"{instance}/api/v1/videos/{video_id}?local=true"
        request = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(
            request, context=_ssl_context(), timeout=20
        ) as response:
            return json.loads(response.read().decode("utf-8"))

    def _fetch_to_file(
        self, url: str, dest: Path, budget_bytes: int
    ) -> int:
        """Stream a URL into dest, aborting once the byte budget is
        spent. Returns the number of bytes written."""
        import urllib.request

        request = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0"}
        )
        written = 0
        with urllib.request.urlopen(
            request, context=_ssl_context(), timeout=60
        ) as response, dest.open("wb") as handle:
            while True:
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > budget_bytes:
                    raise SubfaError("too_big")
                handle.write(chunk)
        return written

    @staticmethod
    def _mux_media_parts(
        video_part: Path, audio_part: Path, dest: Path
    ) -> bool:
        """Mux separate video and audio files into one MP4 with a
        stream copy (no re-encode). False when ffmpeg refuses, for
        example a codec the MP4 container cannot hold."""
        import subprocess

        completed = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(video_part),
                "-i", str(audio_part),
                "-c", "copy",
                str(dest),
            ],
            capture_output=True,
            text=True,
        )
        return (
            completed.returncode == 0
            and dest.exists()
            and dest.stat().st_size > 0
        )

    def _fetch_invidious_media(
        self, url: str, dest_dir: Path, settings
    ) -> tuple[Path, str] | None:
        """The Invidious route: (media path, route) or None.

        Tries each configured instance in order; every failure
        (instance down, no usable formats, oversized pair, mux
        refusal) falls through to the next instance, and total
        failure returns None so the caller continues to the android
        route. Parts live in a scratch subfolder that is always
        removed, so a failed attempt leaves nothing the other
        routes could mistake for served media.
        """
        video_id = youtube_video_id(url)
        instances = invidious_instances()
        if not video_id or not instances:
            return None
        parts_dir = dest_dir / "_invidious"
        for instance in instances:
            try:
                info = self._invidious_video_info(instance, video_id)
                length = int(info.get("lengthSeconds") or 0)
                if length and length > settings.max_duration_seconds:
                    return None
                chosen = choose_invidious_streams(
                    info.get("adaptiveFormats") or [],
                    settings.download_max_height,
                )
                if chosen is None:
                    continue
                video_fmt, audio_fmt, height = chosen
                shutil.rmtree(parts_dir, ignore_errors=True)
                parts_dir.mkdir(parents=True, exist_ok=True)
                video_part = parts_dir / "video.part"
                audio_part = parts_dir / "audio.part"
                budget = settings.max_download_bytes
                spent = self._fetch_to_file(
                    video_fmt["url"], video_part, budget
                )
                spent += self._fetch_to_file(
                    audio_fmt["url"], audio_part, budget - spent
                )
                muxed = parts_dir / "source.mp4"
                if not self._mux_media_parts(video_part, audio_part, muxed):
                    continue
                final = dest_dir / "source.mp4"
                shutil.move(str(muxed), str(final))
                return final, f"invidious-{height}"
            except Exception:
                continue
            finally:
                shutil.rmtree(parts_dir, ignore_errors=True)
        return None

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
