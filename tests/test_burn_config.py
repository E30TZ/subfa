import shutil
import subprocess
import types

import pytest

from subfa import SubfaError
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
    vf = cmd[cmd.index("-vf") + 1]
    assert vf == "setsar=1,ass=filename=subs.ass"
    assert cmd[-1] == "out.mp4"
    assert "-c:a" in cmd
    # Explicit encoder rate control: ffmpeg defaults starved the
    # bitrate on low-resolution sources and softened the burned text.
    assert cmd[cmd.index("-c:v") + 1] == "libx264"
    assert cmd[cmd.index("-crf") + 1] == "18"
    assert cmd[cmd.index("-preset") + 1] == "medium"
    assert cmd[cmd.index("-pix_fmt") + 1] == "yuv420p"
    # faststart puts the moov atom at the front of the MP4, so chat
    # players probe the real dimensions instead of framing the file
    # with a wrong aspect ratio, and streaming starts progressively.
    assert cmd[cmd.index("-movflags") + 1] == "+faststart"


def test_burn_command_uses_bare_name_for_full_paths():
    cmd = build_burn_command(
        "in.mp4", "/some/dir/with space/tiny.subbed.ass", "out.mp4"
    )
    vf = cmd[cmd.index("-vf") + 1]
    assert "ass=filename=tiny.subbed.ass" in vf


def test_burn_command_scales_before_ass_when_capped():
    cmd = build_burn_command("in.mp4", "subs.ass", "out.mp4", max_height=480)
    vf = cmd[cmd.index("-vf") + 1]
    # setsar normalizes the display geometry first, scale caps the
    # height (min() never upscales), subtitles drawn last, at the
    # output size.
    assert vf == "setsar=1,scale=-2:min(ih\\,480),ass=filename=subs.ass"
    plain = build_burn_command("in.mp4", "subs.ass", "out.mp4")
    assert plain[plain.index("-vf") + 1] == "setsar=1,ass=filename=subs.ass"


def test_burn_command_uses_relative_fontsdir():
    # No host path may enter the filterchain (a raw Windows path
    # there breaks ffmpeg's filter parser on the backslash escapes);
    # the fonts live in the working directory and are referenced
    # with the relative fontsdir ".".
    cmd = build_burn_command("in.mp4", "subs.ass", "out.mp4", fonts=True)
    vf = cmd[cmd.index("-vf") + 1]
    assert vf == "setsar=1,ass=filename=subs.ass:fontsdir=."
    assert "\\" not in vf


def test_burn_command_scaled_with_fonts():
    cmd = build_burn_command(
        "in.mp4", "tiny.subbed.ass", "out.mp4", max_height=480, fonts=True
    )
    vf = cmd[cmd.index("-vf") + 1]
    assert vf == "setsar=1,scale=-2:min(ih\\,480),ass=filename=tiny.subbed.ass:fontsdir=."


class _FakeRun:
    """Stand-in for subprocess.run inside subfa.burn."""

    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.calls = []

    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs))
        if command[0] == "ffprobe":
            # No streams: probe_video_size falls back to defaults.
            return types.SimpleNamespace(
                returncode=0, stdout='{"streams": []}', stderr=""
            )
        return types.SimpleNamespace(
            returncode=self.returncode, stdout=self.stdout, stderr=self.stderr
        )


def test_burn_copies_bundled_fonts_into_work_dir(tmp_path, monkeypatch):
    fake = _FakeRun()
    monkeypatch.setattr("subfa.burn.subprocess.run", fake)
    out = tmp_path / "clip.subbed.mp4"
    burn_subtitles("in.mp4", [Cue(0.0, 0.9, "Hello")], out, work_dir=tmp_path)
    assert (tmp_path / "Vazirmatn-Regular.ttf").exists()
    assert (tmp_path / "Vazirmatn-Bold.ttf").exists()
    # The ffmpeg call ran in the work dir with the relative fontsdir.
    command, kwargs = fake.calls[-1]
    assert kwargs["cwd"] == str(tmp_path)
    vf = command[command.index("-vf") + 1]
    assert "ass=filename=clip.subbed.ass:fontsdir=." in vf


def test_burn_reuses_fonts_already_in_work_dir(tmp_path, monkeypatch):
    fake = _FakeRun()
    monkeypatch.setattr("subfa.burn.subprocess.run", fake)
    present = tmp_path / "Vazirmatn-Regular.ttf"
    present.write_bytes(b"already here")
    out = tmp_path / "clip.subbed.mp4"
    burn_subtitles("in.mp4", [Cue(0.0, 0.9, "Hello")], out, work_dir=tmp_path)
    # The pre-existing file is reused untouched, not recopied over.
    assert present.read_bytes() == b"already here"


def test_burn_libass_missing_error_message(tmp_path, monkeypatch):
    stderr = (
        "[AVFilterGraph @ 0x123] No such filter: 'ass'\n"
        "Error opening output files: Filter not found\n"
    )
    fake = _FakeRun(returncode=1, stderr=stderr)
    monkeypatch.setattr("subfa.burn.subprocess.run", fake)
    out = tmp_path / "clip.subbed.mp4"
    with pytest.raises(SubfaError) as excinfo:
        burn_subtitles("in.mp4", [Cue(0.0, 0.9, "Hello")], out, work_dir=tmp_path)
    message = str(excinfo.value)
    assert "lacks the libass subtitle filter" in message
    assert "full ffmpeg" in message
    # The raw ffmpeg tail stays attached after the clear sentence.
    assert "No such filter: 'ass'" in message


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
    # Cinema targets about 8 percent of the frame height: sized for
    # phone screens, where the earlier 5 percent read as tiny.
    assert small_size == 29
    assert large_size == 86
    assert "PlayResY: 360" in small
    assert "PlayResY: 1080" in large


def _ass_style_fields(ass: str) -> list[str]:
    style_line = ass.split("Style: Default")[1].splitlines()[0]
    return ("Default" + style_line).split(",")


def test_cinema_style_is_bold_on_backing_box():
    ass = cues_to_ass([Cue(0, 1, "سلام")], style="cinema",
                      frame_width=640, frame_height=360)
    fields = _ass_style_fields(ass)
    # Format order: ..., BackColour(6), Bold(7), ..., BorderStyle(15)
    assert fields[6] == "&H80000000"
    assert fields[7] == "1"
    assert fields[15] == "3"


def test_reels_style_also_uses_backing_box():
    ass = cues_to_ass([Cue(0, 1, "سلام")], style="reels",
                      frame_width=360, frame_height=640)
    fields = _ass_style_fields(ass)
    assert fields[6] == "&H80000000"
    assert fields[15] == "3"


def test_learning_style_stays_smaller_than_cinema():
    cues = [Cue(0, 2, "سلام دنیا")]
    learning = cues_to_ass(cues, style="learning",
                           frame_width=640, frame_height=360)
    cinema = cues_to_ass(cues, style="cinema",
                         frame_width=640, frame_height=360)
    assert _ass_font_size(learning) < _ass_font_size(cinema)
    assert _ass_font_size(learning) == 26


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
    # faststart in the real file: the moov atom precedes mdat.
    data = out.read_bytes()
    assert data.index(b"moov") < data.index(b"mdat")
