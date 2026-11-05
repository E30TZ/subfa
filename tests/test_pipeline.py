import shutil
import subprocess

import pytest

from subfa.config import Settings
from subfa.download import DownloadResult, FakeDownloader
from subfa.pipeline import Pipeline
from subfa.transcribe import FakeEngine
from subfa.translate import FakeTranslator


def make_settings(tmp_path):
    settings = Settings()
    settings.glossary_dir = tmp_path / "glossaries"
    return settings


def make_pipeline(tmp_path, engine=None, downloader=None):
    return Pipeline(
        settings=make_settings(tmp_path),
        engine=engine or FakeEngine(),
        translator=FakeTranslator(),
        downloader=downloader,
    )


def make_wav(path):
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", str(path)],
        check=True, capture_output=True,
    )
    return path


def make_video(path):
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
         "-shortest", str(path)],
        check=True, capture_output=True,
    )
    return path


CAPTIONS = (
    "1\n00:00:00,000 --> 00:00:02,000\nFirst published caption line\n\n"
    "2\n00:00:02,000 --> 00:00:04,000\nSecond published caption line\n\n"
    "3\n00:00:04,000 --> 00:00:06,000\nThird published caption line\n"
)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_pipeline_file_end_to_end(tmp_path):
    media = make_wav(tmp_path / "talk.wav")
    pipeline = make_pipeline(tmp_path)
    result = pipeline.run_file(media, tmp_path / "out", target="fa")
    assert result.path_used == "whisper"
    srt_text = result.outputs["srt"].read_text(encoding="utf-8")
    assert "[fa] Hello world, this is a test." in srt_text
    assert result.outputs["bilingual"].exists()
    bilingual = result.outputs["bilingual"].read_text(encoding="utf-8")
    assert "Hello world, this is a test.\n[fa] Hello world" in bilingual
    transcript = result.outputs["transcript"].read_text(encoding="utf-8")
    assert "Programming is fun" in transcript


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_pipeline_applies_glossary_after_translation(tmp_path):
    gloss_dir = tmp_path / "glossaries"
    gloss_dir.mkdir()
    (gloss_dir / "programming.json").write_text(
        '{"programming": "برنامه‌نویسی"}', encoding="utf-8"
    )
    media = make_wav(tmp_path / "talk.wav")
    pipeline = make_pipeline(tmp_path)
    result = pipeline.run_file(
        media, tmp_path / "out", target="fa", glossaries=["programming"]
    )
    srt_text = result.outputs["srt"].read_text(encoding="utf-8")
    assert "برنامه‌نویسی is fun" in srt_text


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_pipeline_url_captions_fast_path_skips_whisper(tmp_path):
    media = make_video(tmp_path / "clip.mp4")
    captions = tmp_path / "clip.en.srt"
    captions.write_text(CAPTIONS, encoding="utf-8")
    engine = FakeEngine()
    downloader = FakeDownloader(media, captions)
    pipeline = make_pipeline(tmp_path, engine=engine, downloader=downloader)
    result = pipeline.run_url(
        "https://example.com/watch?v=1", tmp_path / "out", tmp_path / "dl", target="fa"
    )
    assert result.path_used == "captions"
    assert engine.calls == 0
    srt_text = result.outputs["srt"].read_text(encoding="utf-8")
    assert "[fa] First published caption line" in srt_text


class CaptionsOnlyDownloader:
    """Link whose media is gated by the site (YouTube on a
    datacenter IP): captions arrive, the video file does not."""

    name = "captions-only"

    def __init__(self, captions_path):
        self.captions_path = captions_path

    def download(self, url, dest_dir, settings):
        return DownloadResult(
            media_path=None,
            captions_path=self.captions_path,
            captions_language="en",
            title="Some Talk About GitHub",
        )


def test_pipeline_url_captions_only_when_media_gated(tmp_path):
    captions = tmp_path / "clip.en.srt"
    captions.write_text(CAPTIONS, encoding="utf-8")
    engine = FakeEngine()
    pipeline = make_pipeline(
        tmp_path, engine=engine, downloader=CaptionsOnlyDownloader(captions)
    )
    result = pipeline.run_url(
        "https://youtube.example/watch?v=9",
        tmp_path / "out",
        tmp_path / "dl",
        target="fa",
        burn=True,
    )
    assert result.media_missing is True
    assert result.path_used == "captions"
    assert engine.calls == 0
    assert "burned" not in result.outputs
    srt_text = result.outputs["srt"].read_text(encoding="utf-8")
    assert "[fa] First published caption line" in srt_text
    # Outputs are named from the video title when there is no file.
    assert result.outputs["srt"].name.startswith("Some-Talk-About-GitHub")


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_pipeline_url_falls_back_to_whisper_without_captions(tmp_path):
    media = make_video(tmp_path / "clip.mp4")
    engine = FakeEngine()
    downloader = FakeDownloader(media, captions_path=None)
    pipeline = make_pipeline(tmp_path, engine=engine, downloader=downloader)
    result = pipeline.run_url(
        "https://example.com/watch?v=2", tmp_path / "out", tmp_path / "dl", target="fa"
    )
    assert result.path_used == "whisper"
    assert engine.calls == 1


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_pipeline_url_falls_back_when_captions_unusable(tmp_path):
    media = make_video(tmp_path / "clip.mp4")
    captions = tmp_path / "clip.en.srt"
    captions.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nOnly one thin cue\n", encoding="utf-8"
    )
    engine = FakeEngine()
    downloader = FakeDownloader(media, captions)
    pipeline = make_pipeline(tmp_path, engine=engine, downloader=downloader)
    result = pipeline.run_url(
        "https://example.com/watch?v=3", tmp_path / "out", tmp_path / "dl", target="fa"
    )
    assert result.path_used == "whisper"
    assert engine.calls == 1


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_pipeline_burn_produces_video(tmp_path):
    media = make_video(tmp_path / "clip.mp4")
    pipeline = make_pipeline(tmp_path)
    result = pipeline.run_file(media, tmp_path / "out", target="fa", burn=True)
    assert result.outputs["burned"].exists()
    assert result.outputs["burned"].stat().st_size > 0


ROLLING_SRT = (
    "1\n00:00:00,000 --> 00:00:02,000\nHello and\n\n"
    "2\n00:00:02,000 --> 00:00:04,000\nHello and welcome\n\n"
    "3\n00:00:04,000 --> 00:00:06,000\nHello and welcome to the show.\n\n"
    "4\n00:00:06,000 --> 00:00:08,000\nto the show. Today we\n\n"
    "5\n00:00:08,000 --> 00:00:10,000\nToday we learn Python fast.\n"
)


class KindDownloader:
    """Captions-only link with a known track kind."""

    name = "kind"

    def __init__(self, captions_path, kind, language="en"):
        self.captions_path = captions_path
        self.kind = kind
        self.language = language

    def download(self, url, dest_dir, settings):
        return DownloadResult(
            media_path=None,
            captions_path=self.captions_path,
            captions_language=self.language,
            captions_kind=self.kind,
            title="Rolling Talk",
        )


def test_pipeline_derolls_automatic_captions(tmp_path):
    captions = tmp_path / "clip.en.srt"
    captions.write_text(ROLLING_SRT, encoding="utf-8")
    pipeline = make_pipeline(
        tmp_path, downloader=KindDownloader(captions, "automatic")
    )
    result = pipeline.run_url(
        "https://youtube.example/watch?v=7", tmp_path / "out", tmp_path / "dl",
        target="fa",
    )
    assert result.path_used == "captions"
    assert result.caption_track == "automatic en"
    srt_text = result.outputs["srt"].read_text(encoding="utf-8")
    # The rolling duplicates are gone before translation: the
    # greeting is translated once, not four times.
    assert srt_text.count("[fa] Hello") == 1
    assert "welcome to the show" in srt_text
    report_text = result.outputs["report"].read_text(encoding="utf-8")
    assert "Caption track: automatic en" in report_text


FA_CAPTIONS = (
    "1\n00:00:00,000 --> 00:00:03,000\nاین کار انجام می‌شود و نتیجه خوب است.\n\n"
    "2\n00:00:03,000 --> 00:00:06,000\nاو نمی‌تواند امروز بیاید و دیر شده است.\n\n"
    "3\n00:00:06,000 --> 00:00:09,000\nفردا دوباره تلاش می‌کنیم و موفق می‌شویم.\n"
)


def test_pipeline_tone_informal_on_persian_captions(tmp_path):
    captions = tmp_path / "clip.fa.srt"
    captions.write_text(FA_CAPTIONS, encoding="utf-8")
    pipeline = make_pipeline(
        tmp_path, downloader=KindDownloader(captions, "manual", language="fa")
    )
    result = pipeline.run_url(
        "https://example.com/watch?v=8", tmp_path / "out", tmp_path / "dl",
        target="fa", tone="informal",
    )
    assert result.tone_resolved == "informal"
    srt_text = result.outputs["srt"].read_text(encoding="utf-8")
    assert "میشه" in srt_text
    assert "نمی‌تونه" in srt_text
    assert "خوبه" in srt_text
    assert "می‌شود" not in srt_text
    report_text = result.outputs["report"].read_text(encoding="utf-8")
    assert "Tone requested: informal" in report_text
    assert "Tone resolved: informal" in report_text
    assert "Caption track: manual fa" in report_text


def test_pipeline_tone_auto_stays_formal_on_formal_text(tmp_path):
    captions = tmp_path / "clip.fa.srt"
    captions.write_text(FA_CAPTIONS, encoding="utf-8")
    pipeline = make_pipeline(
        tmp_path, downloader=KindDownloader(captions, "manual", language="fa")
    )
    result = pipeline.run_url(
        "https://example.com/watch?v=9", tmp_path / "out", tmp_path / "dl",
        target="fa", tone="auto",
    )
    assert result.tone_resolved == "formal"
    srt_text = result.outputs["srt"].read_text(encoding="utf-8")
    assert "می‌شود" in srt_text


class SettingsRecordingDownloader(FakeDownloader):
    def download(self, url, dest_dir, settings):
        self.seen_max_height = settings.download_max_height
        return super().download(url, dest_dir, settings)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_pipeline_quality_caps_download_and_burn(tmp_path):
    media = make_video(tmp_path / "clip.mp4")
    captions = tmp_path / "clip.en.srt"
    captions.write_text(CAPTIONS, encoding="utf-8")
    downloader = SettingsRecordingDownloader(media, captions)
    pipeline = make_pipeline(tmp_path, downloader=downloader)
    result = pipeline.run_url(
        "https://example.com/watch?v=10", tmp_path / "out", tmp_path / "dl",
        target="fa", burn=True, quality="480",
    )
    assert downloader.seen_max_height == 480
    assert result.quality == "480"
    assert result.outputs["burned"].exists()
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=height", "-of", "csv=p=0",
         str(result.outputs["burned"])],
        capture_output=True, text=True,
    )
    # The 240p fixture is below the cap: never upscaled.
    assert probe.stdout.strip() == "240"
    report_text = result.outputs["report"].read_text(encoding="utf-8")
    assert "Video quality: 480" in report_text


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_pipeline_quality_source_lifts_download_cap(tmp_path):
    media = make_video(tmp_path / "clip.mp4")
    downloader = SettingsRecordingDownloader(media, captions_path=None)
    pipeline = make_pipeline(tmp_path, downloader=downloader)
    pipeline.run_url(
        "https://example.com/watch?v=11", tmp_path / "out", tmp_path / "dl",
        target="fa", quality="source",
    )
    assert downloader.seen_max_height >= 4000
