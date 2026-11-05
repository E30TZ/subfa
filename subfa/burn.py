"""Burning subtitles into a video with FFmpeg and libass.

Subtitles are converted to ASS first, because ASS gives real styling
control: font, size, outline and position. The default style uses the
Vazirmatn font for Persian text. libass applies the Unicode bidi
algorithm, so Persian lines render right to left correctly.

Two things keep the rendering identical and readable on every host:

- The Vazirmatn TTFs are bundled in assets/fonts, copied into the
  burn working directory and handed to the ass filter through a
  relative fontsdir (fontsdir=.), so libass never depends on a
  system installed font and no host path is embedded in the filter
  string (a raw Windows path there breaks ffmpeg's filter parser).
- Font size and margins scale with the actual output frame height
  (cinema targets about 8 percent of the frame height). A fixed
  PlayRes tuned for tall videos would shrink the text to nothing on
  a 360p output; sizing from the real height keeps subtitles legible
  at every resolution, phones included.
- The cinema and reels styles draw the text bold on a semi-opaque
  black backing box (ASS BorderStyle 3), so the lines stay readable
  on bright or busy scenes instead of relying on a thin outline.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from . import SubfaError
from .config import REPO_ROOT
from .srt import Cue

DEFAULT_FONT = "Vazirmatn"

# Where the bundled Vazirmatn TTFs live (OFL licensed, see the
# OFL.txt beside them). Copied into the burn working directory and
# referenced from the filter as the relative fontsdir ".".
BUNDLED_FONTS_DIR = REPO_ROOT / "assets" / "fonts"

# The presets' absolute values are tuned at this reference height;
# with a real frame height the fraction fields take over.
REFERENCE_HEIGHT = 720

# Style presets. cinema is the safe default for landscape video;
# reels moves text up into the 9:16 safe area, bold and larger;
# learning shrinks the source line above the translation in
# bilingual cues. Font stays Vazirmatn for Persian presets, rendered
# bold: at phone sizes the regular weight reads thin. cinema and
# reels sit on a semi-opaque black backing box (BorderStyle 3,
# BackColour alpha 0x80, about 50 percent transparent) so the text
# pops on any scene; with BorderStyle 3 the Outline field is the
# box padding, not a text outline.
STYLE_PRESETS = {
    "cinema": {
        "font_size": 58, "font_frac": 0.080, "outline": 3, "shadow": 0,
        "bold": 1, "margin_v": 30, "margin_frac": 0.042, "alignment": 2,
        "border_style": 3, "back_colour": "&H80000000",
    },
    "reels": {
        "font_size": 26, "font_frac": 0.059, "outline": 3, "shadow": 1,
        "bold": 1, "margin_v": 170, "margin_frac": 0.236, "alignment": 2,
        "border_style": 3, "back_colour": "&H80000000",
    },
    "learning": {
        "font_size": 52, "font_frac": 0.072, "outline": 2, "shadow": 0,
        "bold": 1, "margin_v": 36, "margin_frac": 0.050, "alignment": 2,
        "border_style": 1, "back_colour": "&H64000000",
    },
}
DEFAULT_STYLE = "cinema"


def _style_metrics(preset: dict, frame_height: int | None) -> tuple[int, int, int]:
    """(font size, outline, bottom margin) for a preset.

    Without a frame height the reference values are used as-is. With
    one, the size comes from the preset's fraction of the height
    (cinema: about 8 percent), so a 360p video gets proportionally
    the same on-screen text as a 1080p one.
    """
    if frame_height is None:
        return preset["font_size"], preset["outline"], preset["margin_v"]
    height = max(int(frame_height), 1)
    font_size = max(10, round(preset["font_frac"] * height))
    outline = max(1, round(preset["outline"] * height / REFERENCE_HEIGHT))
    margin_v = max(0, round(preset["margin_frac"] * height))
    return font_size, outline, margin_v


def probe_video_size(input_video: str | Path) -> tuple[int, int] | None:
    """(width, height) of the first video stream, or None."""
    try:
        completed = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "json", str(input_video),
            ],
            capture_output=True, text=True, timeout=30,
        )
        if completed.returncode != 0:
            return None
        streams = json.loads(completed.stdout).get("streams") or []
        if not streams:
            return None
        width, height = int(streams[0]["width"]), int(streams[0]["height"])
        return (width, height) if width > 0 and height > 0 else None
    except Exception:
        return None


def format_ass_timestamp(seconds: float) -> str:
    """ASS timestamps look like H:MM:SS.cc (centiseconds)."""
    if seconds < 0:
        seconds = 0.0
    total_cs = int(round(seconds * 100))
    cs = total_cs % 100
    total_s = total_cs // 100
    s = total_s % 60
    m = (total_s // 60) % 60
    h = total_s // 3600
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def cues_to_ass(
    cues: list[Cue],
    font: str = DEFAULT_FONT,
    style: str = DEFAULT_STYLE,
    frame_width: int | None = None,
    frame_height: int | None = None,
) -> str:
    preset = STYLE_PRESETS.get(style, STYLE_PRESETS[DEFAULT_STYLE])
    font_size, outline, margin_v = _style_metrics(preset, frame_height)
    if frame_height is not None:
        play_res_y = int(frame_height)
        play_res_x = int(frame_width) if frame_width else round(play_res_y * 16 / 9)
    else:
        play_res_x, play_res_y = 1280, REFERENCE_HEIGHT
    header = (
        "[Script Info]\n"
        "Title: SubFa subtitles\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {play_res_x}\n"
        f"PlayResY: {play_res_y}\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font},{font_size},&H00FFFFFF,&H000000FF,"
        f"&H00000000,{preset['back_colour']},{preset['bold']},0,0,0,"
        f"100,100,0,0,{preset['border_style']},"
        f"{outline},{preset['shadow']},{preset['alignment']},"
        f"10,10,{margin_v},1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
    )
    events = []
    for cue in cues:
        if style == "learning" and "\n" in cue.text:
            # Source line smaller, above the translation.
            first, rest = cue.text.split("\n", 1)
            source_size = max(8, round(font_size * 0.65))
            text = (
                f"{{\\fs{source_size}\\c&H00D8D8D8&}}" + first
                + f"{{\\fs{font_size}\\c&H00FFFFFF&}}\\N"
                + rest.replace("\n", "\\N")
            )
        else:
            text = cue.text.replace("\n", "\\N")
        events.append(
            "Dialogue: 0,"
            f"{format_ass_timestamp(cue.start)},{format_ass_timestamp(cue.end)},"
            f"Default,,0,0,0,,{text}"
        )
    return header + "\n".join(events) + "\n"


def _escape_filter_value(value: str) -> str:
    """Escape a value for use inside an ffmpeg filter option."""
    return (
        value.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace(",", "\\,")
        .replace(";", "\\;")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )


def build_burn_command(
    input_video: str | Path,
    ass_path: str | Path,
    output_path: str | Path,
    max_height: int | None = None,
    fonts: bool = False,
) -> list[str]:
    """Build the ffmpeg command for burn-in (no shell involved).

    The .ass file is referenced through the filter's NAMED filename
    option with a bare filename, never a full path and never the
    positional form: ffmpeg 8 (e.g. Homebrew's) rejects both the
    quoted-path form ass='/path/x.ass' and the positional form
    ass=x.ass with "No option name near", while ffmpeg 6/7 accepted
    them. burn_subtitles runs the command with cwd set to the .ass
    directory, and only the filter-special characters in the
    filename itself are escaped here.

    No absolute path of any kind goes into the filterchain: an
    earlier version embedded the fonts directory as a raw path
    (fontsdir=D:\\a\\...) and ffmpeg's filter parser broke on the
    backslash escapes. With fonts=True the filter instead gets the
    RELATIVE fontsdir "." and burn_subtitles copies the bundled
    Vazirmatn TTFs into that same working directory first, so
    rendering still does not depend on fonts installed on the host.

    With max_height set, a scale filter runs first and caps the
    output height; min() means a shorter source is never upscaled.
    The subtitles are drawn after scaling, at the output size.

    The chain opens with setsar=1 so the display aspect geometry of
    the source is preserved exactly (some phone-shot sources carry a
    non-square sample aspect that players otherwise stretch). The
    video is re-encoded with explicit rate control (libx264 CRF 18,
    preset medium, yuv420p): without it ffmpeg's defaults starved
    the output bitrate on low-resolution sources (146 kb/s out for a
    177 kb/s source in one measured case), softening both the scene
    and the burned text. Audio stays stream-copied.
    """
    escaped = _escape_filter_value(Path(ass_path).name)
    ass_filter = f"ass=filename={escaped}"
    if fonts:
        ass_filter += ":fontsdir=."
    filters = ["setsar=1"]
    if max_height:
        filters.append(f"scale=-2:min(ih\\,{int(max_height)})")
    filters.append(ass_filter)
    return [
        "ffmpeg",
        "-y",
        "-i", str(input_video),
        "-vf", ",".join(filters),
        "-c:v", "libx264",
        "-crf", "18",
        "-preset", "medium",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        str(output_path),
    ]


def _copy_fonts_into(fonts_dir: Path, dest_dir: Path) -> bool:
    """Copy the .ttf files from fonts_dir into dest_dir.

    Files already present in dest_dir are reused, not recopied.
    Returns True when at least one font file is in place there.
    """
    copied = False
    for src in sorted(fonts_dir.iterdir()):
        if src.is_file() and src.suffix.lower() == ".ttf":
            dest = dest_dir / src.name
            if not dest.exists():
                shutil.copy2(src, dest)
            copied = True
    return copied


def _libass_missing(stderr: str) -> bool:
    """True when ffmpeg failed because its build has no ass filter."""
    if "No such filter" in stderr and "ass" in stderr:
        return True
    return "Filter not found" in stderr


def burn_subtitles(
    input_video: str | Path,
    cues: list[Cue],
    output_path: str | Path,
    font: str = DEFAULT_FONT,
    work_dir: str | Path | None = None,
    style: str = DEFAULT_STYLE,
    max_height: int | None = None,
    fonts_dir: str | Path | None = None,
) -> Path:
    """Write the ASS file and run ffmpeg. Returns the output path.

    The input is probed so the ASS PlayRes and font size match the
    actual output frame: when max_height caps the output, the size
    math follows the same min() rule as the scale filter. fonts_dir
    defaults to the bundled Vazirmatn folder when it exists; its
    fonts are copied into the working directory and the filter
    references them with the relative fontsdir ".".
    """
    output_path = Path(output_path)
    ass_dir = Path(work_dir) if work_dir else output_path.parent
    ass_dir.mkdir(parents=True, exist_ok=True)
    ass_path = ass_dir / (output_path.stem + ".ass")

    size = probe_video_size(input_video)
    if size is not None:
        width, height = size
        if max_height and height > max_height:
            out_height = int(max_height)
            out_width = int(round(width * out_height / height / 2.0)) * 2
        else:
            out_width, out_height = width, height
    else:
        out_width, out_height = 1280, REFERENCE_HEIGHT
    ass_path.write_text(
        cues_to_ass(
            cues, font=font, style=style,
            frame_width=out_width, frame_height=out_height,
        ),
        encoding="utf-8",
    )
    if fonts_dir is None and BUNDLED_FONTS_DIR.is_dir():
        fonts_dir = BUNDLED_FONTS_DIR
    fonts_ready = False
    if fonts_dir is not None and Path(fonts_dir).is_dir():
        fonts_ready = _copy_fonts_into(Path(fonts_dir), ass_dir)
    command = build_burn_command(
        input_video, ass_path, output_path,
        max_height=max_height, fonts=fonts_ready,
    )
    completed = subprocess.run(
        command, capture_output=True, text=True, cwd=str(ass_dir)
    )
    if completed.returncode != 0:
        # Keep the tail of stderr, not just the last line: ffmpeg
        # puts the generic failure last and the actual cause (bad
        # filter, missing library, font problem) a few lines above.
        tail = "\n".join(completed.stderr.strip().splitlines()[-8:])
        detail = tail if tail else "unknown error"
        if _libass_missing(completed.stderr):
            # A clear, actionable message first: some ffmpeg builds
            # (e.g. Homebrew's plain ffmpeg formula) ship without
            # libass, so the ass filter simply does not exist there.
            raise SubfaError(
                "Burning subtitles into the video failed: your ffmpeg "
                "build lacks the libass subtitle filter (ass), which "
                "SubFa needs to draw subtitles. Install a full ffmpeg "
                "build that includes libass (on macOS the ffmpeg-full "
                "formula, or a static build), then try again. "
                f"ffmpeg said: {detail}"
            )
        raise SubfaError(
            "Burning subtitles into the video failed. "
            f"ffmpeg said: {detail}"
        )
    return output_path
