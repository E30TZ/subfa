import shutil
import subprocess

import pytest

from subfa.burn import build_burn_command, burn_subtitles, cues_to_ass, format_ass_timestamp
from subfa.config import Settings, is_video
from subfa.srt import Cue


def test_ass_timestamp_format():
    assert format_ass_timestamp(0) == "0:00:00.00"
    assert format_ass_timestamp(61.5) == "0:01:01.50"
    assert format_ass_timestamp(3661.25) == "1:01:01.25"


def test_ass_style_uses_vazirmatn_by_default():
    ass = cues_to_ass([Cue(0, 1, "سلام")])
    assert "Vazirmatn" in ass
    assert "Dialogue: 0,0:00:00.00,0:00:01.00" in ass
    assert "سلام" in ass


def test_burn_command_construction():
    cmd = build_burn_command("in.mp4", "subs.ass", "out.mp4")
    assert cmd[0] == "ffmpeg"
    # Named filename option with a bare filename: ffmpeg 8 rejects
    # both the quoted-path form and the positional form, and the
    # command runs with cwd set to the .ass directory.
    assert "ass=filename=subs.ass" in cmd
    assert cmd[-1] == "out.mp4"
    assert "-c:a" in cmd


def test_burn_command_uses_bare_name_for_full_paths():
    cmd = build_burn_command(
        "in.mp4", "/some/dir/with space/tiny.subbed.ass", "out.mp4"
    )
    assert "ass=filename=tiny.subbed.ass" in cmd


def test_burn_command_scales_before_ass_when_capped():
    cmd = build_burn_command("in.mp4", "subs.ass", "out.mp4", max_height=480)
    vf = cmd[cmd.index("-vf") + 1]
    # Scale first (min() never upscales), subtitles drawn after, at
    # the output size.
    assert vf == "scale=-2:min(ih\\,480),ass=filename=subs.ass"
    # Without a cap the command is exactly the historical one.
    plain = build_burn_command("in.mp4", "subs.ass", "out.mp4")
    assert plain[plain.index("-vf") + 1] == "ass=filename=subs.ass"


def test_burn_command_includes_fontsdir_when_given():
    cmd = build_burn_command(
        "in.mp4", "subs.ass", "out.mp4", fontsdir="/repo/assets/fonts"
    )
    vf = cmd[cmd.index("-vf") + 1]
    assert vf == "ass=filename=subs.ass:fontsdir=/repo/assets/fonts"


def _ass_font_size(ass: str) -> int:
    style_line = ass.split("Style: Default")[1].splitlines()[0]
    # Format: ,Fontname,Fontsize,...
    return int(style_line.split(",")[2])


def test_ass_font_size_scales_with_frame_height():
    cues = [Cue(0, 2, "سلام دنیا")]
    small = cues_to_ass(cues, style="cinema", frame_width=640, frame_height=360)
    large = cues_to_ass(cues, style="cinema", frame_width=1920, frame_height=1080)
    small_size = _ass_font_size(small)
    large_size = _ass_font_size(large)
    assert small_size != large_size
    # Cinema targets about 5 percent of the frame height.
    assert small_size == 18
    assert large_size == 54
    assert "PlayResY: 360" in small
    assert "PlayResY: 1080" in large


def test_config_defaults():
    settings = Settings()
    # Updated with the ASR engine routing change (docs/ASR.md):
    # the faster-whisper default model is large-v3-turbo now.
    assert settings.model == "large-v3-turbo"
    assert settings.default_target == "fa"
    assert settings.captions_fast_path is True
    assert settings.max_duration_seconds == 3600
    assert settings.download_max_height == 720
    assert settings.max_file_bytes == settings.max_file_mb * 1024 * 1024


def test_is_video_detection():
    assert is_video("a.mp4") and is_video("a.MKV")
    assert not is_video("a.mp3")


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_burn_end_to_end_tiny_video(tmp_path):
    video = tmp_path / "tiny.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
         "-shortest", str(video)],
        check=True, capture_output=True,
    )
    out = tmp_path / "tiny.subbed.mp4"
    burn_subtitles(video, [Cue(0.0, 0.9, "Hello subtitles")], out, work_dir=tmp_path)
    assert out.exists() and out.stat().st_size > 0
