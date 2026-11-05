import shutil
import subprocess

import pytest

from subfa.config import Settings
from subfa.download import FakeDownloader
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
