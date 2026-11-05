"""Burning subtitles into a video with FFmpeg and libass.

Subtitles are converted to ASS first, because ASS gives real styling
control: font, size, outline and position. The default style uses the
Vazirmatn font for Persian text. libass applies the Unicode bidi
algorithm, so Persian lines render right to left correctly as long
as the font is installed; on systems without Vazirmatn, libass falls
back to a system font and the subtitles still work, with a plainer
look. This trade-off is stated in the README.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from . import SubfaError
from .srt import Cue

DEFAULT_FONT = "Vazirmatn"

# Style presets. cinema is the safe default for landscape video;
# reels moves text up into the 9:16 safe area, bold and larger;
# learning shrinks the source line above the translation in
# bilingual cues. Font stays Vazirmatn for Persian presets.
STYLE_PRESETS = {
    "cinema": {
        "font_size": 22, "outline": 3, "shadow": 0, "bold": 0,
        "margin_v": 30, "alignment": 2,
    },
    "reels": {
        "font_size": 26, "outline": 3, "shadow": 1, "bold": 1,
        "margin_v": 170, "alignment": 2,
    },
    "learning": {
        "font_size": 20, "outline": 2, "shadow": 0, "bold": 0,
        "margin_v": 36, "alignment": 2,
    },
}
DEFAULT_STYLE = "cinema"


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
) -> str:
    preset = STYLE_PRESETS.get(style, STYLE_PRESETS[DEFAULT_STYLE])
    header = (
        "[Script Info]\n"
        "Title: SubFa subtitles\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1280\n"
        "PlayResY: 720\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font},{preset['font_size']},&H00FFFFFF,&H000000FF,"
        f"&H00000000,&H64000000,{preset['bold']},0,0,0,100,100,0,0,1,"
        f"{preset['outline']},{preset['shadow']},{preset['alignment']},"
        f"10,10,{preset['margin_v']},1\n"
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
            text = (
                "{\\fs13\\c&H00D8D8D8&}" + first
                + "{\\fs20\\c&H00FFFFFF&}\\N"
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


def build_burn_command(
    input_video: str | Path,
    ass_path: str | Path,
    output_path: str | Path,
) -> list[str]:
    """Build the ffmpeg command for burn-in (no shell involved)."""
    escaped = str(ass_path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    return [
        "ffmpeg",
        "-y",
        "-i", str(input_video),
        "-vf", f"ass='{escaped}'",
        "-c:a", "copy",
        str(output_path),
    ]


def burn_subtitles(
    input_video: str | Path,
    cues: list[Cue],
    output_path: str | Path,
    font: str = DEFAULT_FONT,
    work_dir: str | Path | None = None,
    style: str = DEFAULT_STYLE,
) -> Path:
    """Write the ASS file and run ffmpeg. Returns the output path."""
    output_path = Path(output_path)
    ass_dir = Path(work_dir) if work_dir else output_path.parent
    ass_dir.mkdir(parents=True, exist_ok=True)
    ass_path = ass_dir / (output_path.stem + ".ass")
    ass_path.write_text(cues_to_ass(cues, font=font, style=style), encoding="utf-8")
    command = build_burn_command(input_video, ass_path, output_path)
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        # Keep the tail of stderr, not just the last line: ffmpeg
        # puts the generic failure last and the actual cause (bad
        # filter, missing library, font problem) a few lines above.
        tail = "\n".join(completed.stderr.strip().splitlines()[-8:])
        raise SubfaError(
            "Burning subtitles into the video failed. "
            f"ffmpeg said: {tail if tail else 'unknown error'}"
        )
    return output_path
