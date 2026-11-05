import subprocess
import shutil
import sys
import types
from pathlib import Path

import pytest

from subfa import SubfaError
from subfa.config import Settings
from subfa.download import (
    FakeDownloader,
    YtDlpDownloader,
    _is_youtube_url,
    base_options,
    choose_caption_track,
    extract_url,
    is_url,
    load_caption_cues,
)


def test_base_options_prefer_youtube_clients_that_answer_datacenter_ips():
    # YouTube bot-checks its default player clients on datacenter
    # IPs; web/mweb/ios still return metadata and caption tracks.
    clients = base_options()["extractor_args"]["youtube"]["player_client"]
    assert clients == ["web", "mweb", "ios"]


def test_base_options_use_system_certs_when_ca_bundle_env_set(monkeypatch):
    # Behind a TLS-intercepting proxy the env names a CA bundle;
    # yt-dlp must then prefer system certs (which honour it) over
    # certifi, or every request fails CERTIFICATE_VERIFY_FAILED.
    monkeypatch.setenv("SSL_CERT_FILE", "/run/example/ca-bundle.pem")
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    assert base_options()["compat_opts"] == ["no-certifi"]
    monkeypatch.delenv("SSL_CERT_FILE")
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", "/run/example/ca-bundle.pem")
    assert base_options()["compat_opts"] == ["no-certifi"]
    monkeypatch.delenv("REQUESTS_CA_BUNDLE")
    assert "compat_opts" not in base_options()


def test_is_url():
    assert is_url("https://www.youtube.com/watch?v=abc")
    assert is_url("http://example.com/video")
    assert not is_url("lecture.mp4")
    assert not is_url("see https://example.com later")
    assert not is_url("")


def test_extract_url_from_chat_text():
    assert extract_url("نگاه کن https://youtu.be/xyz اینو") == "https://youtu.be/xyz"
    assert extract_url("سلام، فایل رو بفرست") is None
    assert extract_url("(https://example.com/v).") == "https://example.com/v"


def _write_media(tmp_path, name="clip.mp4"):
    path = tmp_path / name
    path.write_bytes(b"fake-media")
    return path


def _write_captions(tmp_path, name="clip.en.srt", cues=3):
    lines = []
    for i in range(cues):
        lines.append(
            f"{i + 1}\n00:00:0{i},000 --> 00:00:0{i + 1},000\n"
            f"Caption line number {i + 1} here\n"
        )
    path = tmp_path / name
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def test_fake_downloader_copies_media_and_captions(tmp_path):
    media = _write_media(tmp_path)
    captions = _write_captions(tmp_path)
    downloader = FakeDownloader(media, captions)
    result = downloader.download(
        "https://example.com/v", tmp_path / "job", Settings()
    )
    assert result.media_path.exists()
    assert result.captions_path is not None and result.captions_path.exists()
    assert result.captions_language == "en"
    assert downloader.calls == ["https://example.com/v"]


def test_fake_downloader_enforces_duration_limit(tmp_path):
    media = _write_media(tmp_path)
    downloader = FakeDownloader(media, duration_seconds=99999)
    with pytest.raises(SubfaError, match="too_long"):
        downloader.download("https://example.com/v", tmp_path / "job", Settings())


def test_load_caption_cues_accepts_good_srt(tmp_path):
    captions = _write_captions(tmp_path)
    cues = load_caption_cues(captions)
    assert len(cues) == 3
    assert cues[0].text.startswith("Caption line")


def test_load_caption_cues_rejects_thin_file(tmp_path):
    captions = _write_captions(tmp_path, cues=1)
    assert load_caption_cues(captions) == []


def _track(ext, url=True):
    return [{"ext": ext, "url": "https://x/" + ext if url else None}]


def test_choose_caption_track_preference_order():
    # Manual Persian beats everything: it skips translation.
    info = {
        "subtitles": {"en": _track("srt"), "fa": _track("srt")},
        "automatic_captions": {"fa": _track("srt")},
    }
    assert choose_caption_track(info) == ("manual", "fa", "https://x/srt")
    # Manual other beats automatic Persian.
    info = {
        "subtitles": {"en": _track("srt")},
        "automatic_captions": {"fa": _track("srt"), "de": _track("srt")},
    }
    assert choose_caption_track(info)[0:2] == ("manual", "en")
    # Automatic Persian beats automatic other.
    info = {"automatic_captions": {"de": _track("srt"), "fa-IR": _track("srt")}}
    assert choose_caption_track(info)[0:2] == ("automatic", "fa")
    # Nothing usable anywhere.
    assert choose_caption_track({}) is None
    assert choose_caption_track({"subtitles": {"en": _track("json3")}}) is None


def test_choose_caption_track_skips_unusable_entries():
    # A track whose only rendering has no URL falls through to the
    # next language, and VTT is accepted when SRT is absent.
    info = {
        "subtitles": {
            "fa": [{"ext": "srt", "url": None}],
            "en": _track("vtt"),
        }
    }
    kind, language, url = choose_caption_track(info)
    assert (kind, language) == ("manual", "en")
    assert url.endswith("vtt")


def test_load_caption_cues_accepts_vtt(tmp_path):
    vtt = tmp_path / "clip.en.vtt"
    vtt.write_text(
        "WEBVTT\n\n"
        "00:00:00.000 --> 00:00:02.000\nFirst caption line here\n\n"
        "00:00:02.000 --> 00:00:04.000\nSecond caption line here\n\n"
        "00:00:04.000 --> 00:00:06.000\nThird caption line here\n",
        encoding="utf-8",
    )
    cues = load_caption_cues(vtt)
    assert len(cues) == 3
    assert cues[1].text == "Second caption line here"


def test_is_youtube_url():
    assert _is_youtube_url("https://www.youtube.com/watch?v=abc")
    assert _is_youtube_url("https://youtu.be/abc")
    assert _is_youtube_url("https://music.youtube.com/watch?v=abc")
    assert not _is_youtube_url("https://example.com/video")
    assert not _is_youtube_url("https://notyoutube.com/watch?v=abc")
    assert not _is_youtube_url("https://evil-youtube.com/watch?v=abc")


def _install_fake_yt_dlp(monkeypatch, *, primary_ok, android_ok):
    """Replace yt_dlp in sys.modules with a scripted stand-in.

    The fake gates each player client set exactly as the flags say
    and records which client sets were asked to download."""

    class FakeYDL:
        attempts: list[list[str]] = []

        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, url, download=False):
            return {"duration": 120, "title": "Gated video"}

        def download(self, urls):
            clients = list(
                self.options.get("extractor_args", {})
                .get("youtube", {})
                .get("player_client", [])
            )
            FakeYDL.attempts.append(clients)
            dest = Path(self.options["outtmpl"]).parent
            if "android" in clients:
                if not android_ok:
                    raise Exception("android client gated too")
                (dest / "source.mp4").write_bytes(b"android-media-bytes")
                return
            if not primary_ok:
                raise Exception("Sign in to confirm you are not a bot")
            (dest / "source.mp4").write_bytes(b"standard-media-bytes")

    module = types.ModuleType("yt_dlp")
    module.YoutubeDL = FakeYDL
    monkeypatch.setitem(sys.modules, "yt_dlp", module)
    return FakeYDL


def _stub_caption_fetch(monkeypatch):
    def fake_fetch(self, info, dest_dir):
        path = Path(dest_dir) / "source.en.srt"
        path.write_text("captions", encoding="utf-8")
        return path, "en", "automatic"

    monkeypatch.setattr(YtDlpDownloader, "_fetch_caption_track", fake_fetch)


def test_youtube_media_route_standard_when_primary_pass_serves(tmp_path, monkeypatch):
    fake = _install_fake_yt_dlp(monkeypatch, primary_ok=True, android_ok=False)
    result = YtDlpDownloader().download(
        "https://www.youtube.com/watch?v=abc", tmp_path / "job", Settings()
    )
    assert result.media_path is not None and result.media_path.exists()
    assert result.media_route == "standard"
    # The android fallback is never attempted when the primary pass works.
    assert fake.attempts == [["web", "mweb", "ios"]]


def test_youtube_media_route_android_when_primary_pass_gated(tmp_path, monkeypatch):
    fake = _install_fake_yt_dlp(monkeypatch, primary_ok=False, android_ok=True)
    result = YtDlpDownloader().download(
        "https://youtu.be/abc", tmp_path / "job", Settings()
    )
    assert result.media_path is not None and result.media_path.exists()
    assert result.media_path.read_bytes() == b"android-media-bytes"
    assert result.media_route == "android-360"
    assert fake.attempts == [["web", "mweb", "ios"], ["android"]]


def test_youtube_captions_only_when_every_pass_gated(tmp_path, monkeypatch):
    _install_fake_yt_dlp(monkeypatch, primary_ok=False, android_ok=False)
    _stub_caption_fetch(monkeypatch)
    result = YtDlpDownloader().download(
        "https://www.youtube.com/watch?v=abc", tmp_path / "job", Settings()
    )
    assert result.media_path is None
    assert result.media_route is None
    assert result.captions_path is not None and result.captions_path.exists()
    assert result.captions_language == "en"


def test_android_fallback_not_tried_for_other_hosts(tmp_path, monkeypatch):
    fake = _install_fake_yt_dlp(monkeypatch, primary_ok=False, android_ok=True)
    _stub_caption_fetch(monkeypatch)
    result = YtDlpDownloader().download(
        "https://example.com/video", tmp_path / "job", Settings()
    )
    assert result.media_path is None
    assert result.media_route is None
    assert fake.attempts == [["web", "mweb", "ios"]]
