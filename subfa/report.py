"""A small quality report for every finished job.

Every number here is computed from the actual cues of the job: cue
count, how many cues break the reading speed limit, which transcript
path was taken, which model ran, and how many glossary terms were
applied. Nothing is estimated or invented.
"""

from __future__ import annotations

from dataclasses import dataclass

from .srt import MAX_CHARS_PER_SECOND, Cue


@dataclass
class QualityReport:
    duration_seconds: float
    cue_count: int
    over_speed_count: int
    path_used: str
    model: str
    glossary_applied: int
    source_language: str
    target_language: str
    quality: str = ""
    tone_requested: str = ""
    tone_resolved: str = ""
    caption_track: str = ""
    media_route: str = ""
    # Which text the subtitles were built from: "published
    # captions", "auto captions" or "ASR".
    text_source: str = ""
    # Translation provider that produced the target text, when a
    # translation ran at all (for example "argos", "llm (model)").
    translator: str = ""

    @property
    def over_speed_percent(self) -> float:
        if self.cue_count == 0:
            return 0.0
        return 100.0 * self.over_speed_count / self.cue_count

    def to_dict(self) -> dict:
        return {
            "duration_seconds": round(self.duration_seconds, 1),
            "cue_count": self.cue_count,
            "over_speed_count": self.over_speed_count,
            "over_speed_percent": round(self.over_speed_percent, 1),
            "path_used": self.path_used,
            "model": self.model,
            "glossary_applied": self.glossary_applied,
            "source_language": self.source_language,
            "target_language": self.target_language,
            "quality": self.quality,
            "tone_requested": self.tone_requested,
            "tone_resolved": self.tone_resolved,
            "caption_track": self.caption_track,
            "media_route": self.media_route,
            "text_source": self.text_source,
            "translator": self.translator,
        }

    def to_text(self) -> str:
        minutes = int(self.duration_seconds // 60)
        seconds = int(self.duration_seconds % 60)
        lines = [
            "SubFa quality report",
            f"Timeline: {minutes}:{seconds:02d} ({self.duration_seconds:.1f}s, last cue end)",
            f"Cues: {self.cue_count}",
            f"Cues over the {MAX_CHARS_PER_SECOND:.0f} chars/sec reading limit: "
            f"{self.over_speed_count} ({self.over_speed_percent:.1f}%)",
            f"Transcript path: {self.path_used}",
            f"Model / engine info: {self.model}",
            f"Glossary terms applied: {self.glossary_applied}",
            f"Languages: {self.source_language} -> {self.target_language}",
        ]
        if self.text_source:
            lines.append(f"Text source: {self.text_source}")
        if self.translator:
            lines.append(f"Translator: {self.translator}")
        if self.caption_track:
            lines.append(f"Caption track: {self.caption_track}")
        if self.media_route == "android-360":
            lines.append("Media: android client (360p)")
        if self.quality:
            lines.append(f"Video quality: {self.quality}")
        if self.tone_requested:
            lines.append(f"Tone requested: {self.tone_requested}")
            lines.append(f"Tone resolved: {self.tone_resolved}")
        lines += [
            "",
            "گزارش کیفیت SubFa",
            f"تعداد زیرنویس‌ها: {self.cue_count}",
            f"زیرنویس‌های سریع‌تر از حد خواندن: {self.over_speed_count} "
            f"({self.over_speed_percent:.1f}٪)",
            f"مسیر متن: {self.path_used}",
            f"اصطلاحات واژه‌نامه اعمال‌شده: {self.glossary_applied}",
        ]
        if self.text_source:
            fa_source = {
                "published captions": "زیرنویس منتشرشده",
                "auto captions": "زیرنویس خودکار",
                "ASR": "تشخیص گفتار خودکار",
            }.get(self.text_source, self.text_source)
            lines.append(f"منبع متن: {fa_source}")
        if self.translator:
            lines.append(f"مترجم: {self.translator}")
        if self.caption_track:
            lines.append(f"ترک زیرنویس: {self.caption_track}")
        if self.media_route == "android-360":
            lines.append("رسانه: کلاینت اندروید (360p)")
        if self.quality:
            lines.append(f"کیفیت ویدیو: {self.quality}")
        if self.tone_requested:
            lines.append(
                f"لحن: {self.tone_requested} ← {self.tone_resolved}"
            )
        return "\n".join(lines) + "\n"


def build_report(
    cues: list[Cue],
    path_used: str,
    model: str,
    glossary_applied: int,
    source_language: str,
    target_language: str,
    quality: str = "",
    tone_requested: str = "",
    tone_resolved: str = "",
    caption_track: str = "",
    media_route: str = "",
    text_source: str = "",
    translator: str = "",
) -> QualityReport:
    over = 0
    for cue in cues:
        duration = max(cue.end - cue.start, 0.01)
        chars = len("".join(cue.text.split()))
        if chars / duration > MAX_CHARS_PER_SECOND:
            over += 1
    duration_seconds = cues[-1].end if cues else 0.0
    return QualityReport(
        duration_seconds=duration_seconds,
        cue_count=len(cues),
        over_speed_count=over,
        path_used=path_used,
        model=model,
        glossary_applied=glossary_applied,
        source_language=source_language,
        target_language=target_language,
        quality=quality,
        tone_requested=tone_requested,
        tone_resolved=tone_resolved,
        caption_track=caption_track,
        media_route=media_route,
        text_source=text_source,
        translator=translator,
    )
