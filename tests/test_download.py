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
    choose_invidious_streams,
    extract_url,
    invidious_instances,
    is_url,
    load_caption_cues,
    youtube_video_id,
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


# -- Invidious high quality route ------------------------------------


def _vfmt(itag, codec, height, bitrate=1_000_000, fps=30):
    return {
        "itag": str(itag),
        "encoding": codec,
        "container": "mp4" if codec == "h264" else "webm",
        "resolution": f"{height}p",
        "qualityLabel": f"{height}p",
        "fps": fps,
        "bitrate": str(bitrate),
        "type": f"video/{'mp4' if codec == 'h264' else 'webm'}",
        "url": f"https://inst.example/v/{itag}",
    }


def _afmt(itag, codec="aac", bitrate=130_000):
    return {
        "itag": str(itag),
        "encoding": codec,
        "container": "m4a" if codec == "aac" else "webm",
        "resolution": None,
        "qualityLabel": None,
        "fps": None,
        "bitrate": str(bitrate),
        "type": f"audio/{'mp4' if codec == 'aac' else 'webm'}",
        "url": f"https://inst.example/a/{itag}",
    }


def test_youtube_video_id_extraction():
    assert youtube_video_id("https://www.youtube.com/watch?v=abc123") == "abc123"
    assert youtube_video_id("https://youtu.be/abc123?t=9") == "abc123"
    assert youtube_video_id("https://www.youtube.com/shorts/abc123") == "abc123"
    assert youtube_video_id("https://example.com/watch?v=abc123") is None


def test_invidious_instances_config(monkeypatch):
    monkeypatch.delenv("SUBFA_DISABLE_INVIDIOUS", raising=False)
    monkeypatch.delenv("SUBFA_INVIDIOUS_INSTANCES", raising=False)
    assert invidious_instances()[0] == "https://yt.chocolatemoo53.com"
    monkeypatch.setenv(
        "SUBFA_INVIDIOUS_INSTANCES", "https://a.example/, https://b.example"
    )
    assert invidious_instances() == ["https://a.example", "https://b.example"]
    monkeypatch.setenv("SUBFA_DISABLE_INVIDIOUS", "1")
    assert invidious_instances() == []


def test_choose_invidious_streams_respects_height_cap():
    formats = [
        _vfmt(401, "av1", 2160), _vfmt(299, "h264", 1080),
        _vfmt(298, "h264", 720), _vfmt(134, "h264", 360),
        _afmt(140),
    ]
    video, audio, height = choose_invidious_streams(formats, 720)
    assert (video["itag"], height) == ("298", 720)
    assert audio["itag"] == "140"


def test_choose_invidious_streams_prefers_h264_at_same_height():
    formats = [
        _vfmt(303, "vp9", 1080, bitrate=9_000_000),
        _vfmt(299, "h264", 1080, bitrate=3_000_000),
        _afmt(251, "opus"), _afmt(140),
    ]
    video, audio, height = choose_invidious_streams(formats, 1080)
    assert video["itag"] == "299"
    assert audio["itag"] == "140"


def test_choose_invidious_streams_source_cap_takes_best_h264():
    # Cap lifted (source quality): no H.264 exists above 1080, so
    # the best H.264 wins over the taller VP9/AV1 formats.
    formats = [
        _vfmt(315, "vp9", 2160), _vfmt(400, "av1", 1440),
        _vfmt(299, "h264", 1080), _vfmt(298, "h264", 720),
        _afmt(140),
    ]
    video, _, height = choose_invidious_streams(formats, 10000)
    assert (video["itag"], height) == ("299", 1080)


def test_choose_invidious_streams_never_above_cap():
    formats = [_vfmt(298, "h264", 720), _afmt(140)]
    assert choose_invidious_streams(formats, 360) is None
    assert choose_invidious_streams([], 1080) is None
    assert choose_invidious_streams([_vfmt(299, "h264", 1080)], 1080) is None


def test_choose_invidious_streams_audio_fallback_is_first():
    formats = [_vfmt(299, "h264", 1080), _afmt(251, "opus"), _afmt(250, "opus")]
    _, audio, _ = choose_invidious_streams(formats, 1080)
    assert audio["itag"] == "251"


def _inv_fixture():
    return {
        "lengthSeconds": 120,
        "adaptiveFormats": [
            _vfmt(299, "h264", 1080), _vfmt(298, "h264", 720),
            _vfmt(134, "h264", 360), _afmt(140),
        ],
    }


def _patch_invidious_seams(monkeypatch, *, info_by_instance, mux_ok=True):
    """Replace the network and mux seams of the Invidious route
    with recording fakes. info_by_instance maps a base URL to a
    fixture dict, or to an Exception instance to raise."""
    calls = {"info": [], "fetch": []}

    def fake_info(self, instance, video_id):
        calls["info"].append(instance)
        outcome = info_by_instance[instance]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def fake_fetch(self, url, dest, budget_bytes):
        calls["fetch"].append(url)
        Path(dest).write_bytes(b"part-bytes")
        return len(b"part-bytes")

    def fake_mux(video_part, audio_part, dest):
        if not mux_ok:
            return False
        Path(dest).write_bytes(b"muxed-media")
        return True

    monkeypatch.setattr(YtDlpDownloader, "_invidious_video_info", fake_info)
    monkeypatch.setattr(YtDlpDownloader, "_fetch_to_file", fake_fetch)
    monkeypatch.setattr(
        YtDlpDownloader, "_mux_media_parts", staticmethod(fake_mux)
    )
    return calls


def test_youtube_media_route_invidious_when_primary_gated(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "SUBFA_INVIDIOUS_INSTANCES", "https://a.example,https://b.example"
    )
    monkeypatch.delenv("SUBFA_DISABLE_INVIDIOUS", raising=False)
    fake = _install_fake_yt_dlp(monkeypatch, primary_ok=False, android_ok=True)
    calls = _patch_invidious_seams(
        monkeypatch,
        info_by_instance={
            "https://a.example": RuntimeError("instance down"),
            "https://b.example": _inv_fixture(),
        },
    )
    result = YtDlpDownloader().download(
        "https://www.youtube.com/watch?v=abc",
        tmp_path / "job",
        Settings(download_max_height=10000),
    )
    assert result.media_path is not None and result.media_path.exists()
    assert result.media_path.read_bytes() == b"muxed-media"
    assert result.media_route == "invidious-1080"
    # Failover order: first instance tried first, second served.
    assert calls["info"] == ["https://a.example", "https://b.example"]
    # The android route was never needed.
    assert fake.attempts == [["web", "mweb", "ios"]]
    # The scratch parts folder is gone.
    assert not (tmp_path / "job" / "_invidious").exists()


def test_youtube_invidious_total_failure_falls_to_android(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBFA_INVIDIOUS_INSTANCES", "https://a.example")
    monkeypatch.delenv("SUBFA_DISABLE_INVIDIOUS", raising=False)
    fake = _install_fake_yt_dlp(monkeypatch, primary_ok=False, android_ok=True)
    _patch_invidious_seams(
        monkeypatch,
        info_by_instance={"https://a.example": RuntimeError("down")},
    )
    result = YtDlpDownloader().download(
        "https://youtu.be/abc", tmp_path / "job", Settings()
    )
    assert result.media_route == "android-360"
    assert fake.attempts == [["web", "mweb", "ios"], ["android"]]


def test_youtube_invidious_mux_failure_falls_to_android(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBFA_INVIDIOUS_INSTANCES", "https://a.example")
    monkeypatch.delenv("SUBFA_DISABLE_INVIDIOUS", raising=False)
    _install_fake_yt_dlp(monkeypatch, primary_ok=False, android_ok=True)
    _patch_invidious_seams(
        monkeypatch,
        info_by_instance={"https://a.example": _inv_fixture()},
        mux_ok=False,
    )
    result = YtDlpDownloader().download(
        "https://youtu.be/abc", tmp_path / "job", Settings()
    )
    assert result.media_route == "android-360"


def test_youtube_invidious_disabled_by_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBFA_DISABLE_INVIDIOUS", "1")
    _install_fake_yt_dlp(monkeypatch, primary_ok=False, android_ok=True)
    calls = _patch_invidious_seams(monkeypatch, info_by_instance={})
    result = YtDlpDownloader().download(
        "https://youtu.be/abc", tmp_path / "job", Settings()
    )
    assert result.media_route == "android-360"
    assert calls["info"] == []
