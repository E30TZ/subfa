import subprocess
import shutil

import pytest

from subfa import SubfaError
from subfa.config import Settings
from subfa.download import (
    FakeDownloader,
    base_options,
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
