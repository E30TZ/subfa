"""Configuration for SubFa, with environment variable overrides.

Environment variables use the SUBFA_ prefix, for example:
    SUBFA_WHISPER_MODEL=tiny  SUBFA_MAX_FILE_MB=100  SUBFA_TRANSLATOR=none

Translation settings:
    SUBFA_TRANSLATOR   argos (default, offline), llm or none.
    SUBFA_LLM_BASE_URL OpenAI-compatible base URL for the llm
                       translator, including the version prefix,
                       for example http://127.0.0.1:8317/v1
    SUBFA_LLM_API_KEY  Bearer key for that endpoint, when it needs
                       one. Never written to logs or reports.
    SUBFA_LLM_MODEL    Model id the endpoint should run.

Speech recognition (ASR) settings:
    SUBFA_ASR_ENGINE   auto (default), persian or whisper.
                       auto routes Persian audio to the Persian
                       fine-tuned model and everything else to
                       faster-whisper.
    SUBFA_WHISPER_MODEL  faster-whisper model (default large-v3-turbo).
                       The legacy SUBFA_MODEL still works as a fallback.
    SUBFA_PERSIAN_MODEL  Persian fine-tuned model id or local path
                       (default nezamisafa/whisper-persian-v4).
    SUBFA_MODEL_CACHE  Folder where `subfa download-models` stores
                       model files for fully offline runs.

YouTube high quality route (Invidious):
    SUBFA_INVIDIOUS_INSTANCES  Comma separated base URLs of public
                       Invidious instances tried in order when
                       YouTube gates the direct media download.
    SUBFA_DISABLE_INVIDIOUS  Set to 1 to skip that route entirely.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Repository root (config.py lives in <root>/subfa/).
REPO_ROOT = Path(__file__).resolve().parent.parent

VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v",
}
AUDIO_EXTENSIONS = {
    ".mp3", ".wav", ".m4a", ".ogg", ".opus", ".flac", ".aac",
}


def is_video(path: str | Path) -> bool:
    return Path(path).suffix.lower() in VIDEO_EXTENSIONS


def is_supported_media(path: str | Path) -> bool:
    suffix = Path(path).suffix.lower()
    return suffix in VIDEO_EXTENSIONS or suffix in AUDIO_EXTENSIONS


def _env(name: str, default: str) -> str:
    return os.environ.get(f"SUBFA_{name}", default)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(f"SUBFA_{name}")
    if raw is None:
        return default
    return raw.strip().lower() not in ("off", "0", "no", "false")


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(f"SUBFA_{name}", default))
    except (TypeError, ValueError):
        return default


DEFAULT_WHISPER_MODEL = "large-v3-turbo"
DEFAULT_PERSIAN_MODEL = "nezamisafa/whisper-persian-v4"


@dataclass
class Settings:
    """Runtime settings shared by the CLI, the bot and the web app."""

    translator: str = field(default_factory=lambda: _env("TRANSLATOR", "argos"))
    # -- LLM translation (SUBFA_TRANSLATOR=llm) -----------------------
    llm_base_url: str = field(default_factory=lambda: _env("LLM_BASE_URL", ""))
    llm_api_key: str = field(default_factory=lambda: _env("LLM_API_KEY", ""))
    llm_model: str = field(default_factory=lambda: _env("LLM_MODEL", ""))
    # -- ASR (speech recognition) ------------------------------------
    # Routing mode: auto, persian or whisper.
    asr_engine: str = field(
        default_factory=lambda: _env("ASR_ENGINE", "auto").strip().lower()
    )
    # faster-whisper model for non-Persian audio. SUBFA_WHISPER_MODEL
    # wins; the legacy SUBFA_MODEL is honoured as a fallback.
    whisper_model: str = field(
        default_factory=lambda: (
            os.environ.get("SUBFA_WHISPER_MODEL")
            or os.environ.get("SUBFA_MODEL")
            or DEFAULT_WHISPER_MODEL
        )
    )
    # Persian fine-tuned Whisper (HF model id or a local folder).
    persian_model: str = field(
        default_factory=lambda: _env("PERSIAN_MODEL", DEFAULT_PERSIAN_MODEL)
    )
    # Where download-models stores model files (offline runs).
    model_cache: Path = field(
        default_factory=lambda: Path(
            _env("MODEL_CACHE", str(Path.home() / ".cache" / "subfa" / "models"))
        )
    )
    # Anti-hallucination decoding for faster-whisper. Whisper invents
    # text on silence; VAD plus conservative thresholds plus not
    # conditioning on previous text is the standard fix.
    beam_size: int = field(default_factory=lambda: int(_env("BEAM_SIZE", "5")))
    vad_filter: bool = field(default_factory=lambda: _env_bool("VAD_FILTER", True))
    no_speech_threshold: float = field(
        default_factory=lambda: _env_float("NO_SPEECH_THRESHOLD", 0.6)
    )
    log_prob_threshold: float = field(
        default_factory=lambda: _env_float("LOG_PROB_THRESHOLD", -1.0)
    )
    compression_ratio_threshold: float = field(
        default_factory=lambda: _env_float("COMPRESSION_RATIO_THRESHOLD", 2.4)
    )
    condition_on_previous_text: bool = field(
        default_factory=lambda: _env_bool("CONDITION_ON_PREVIOUS_TEXT", False)
    )
    # Torch dtype for the Persian transformers engine: float16,
    # float32 or bfloat16. float16 halves memory on CPU and GPU.
    persian_dtype: str = field(
        default_factory=lambda: _env("PERSIAN_DTYPE", "float16")
    )
    default_target: str = field(default_factory=lambda: _env("TARGET", "fa"))
    default_source: str = field(default_factory=lambda: _env("SOURCE", "auto"))
    max_file_mb: int = field(
        default_factory=lambda: int(_env("MAX_FILE_MB", "200"))
    )
    subtitle_font: str = field(default_factory=lambda: _env("FONT", "Vazirmatn"))
    glossary_dir: Path = field(
        default_factory=lambda: Path(_env("GLOSSARY_DIR", str(REPO_ROOT / "glossaries")))
    )
    # faster-whisper compute type. int8 is a safe default on CPU.
    compute_type: str = field(default_factory=lambda: _env("COMPUTE_TYPE", "int8"))
    # Video link (yt-dlp) limits and behaviour.
    max_duration_seconds: int = field(
        default_factory=lambda: int(_env("MAX_DURATION_MIN", "60")) * 60
    )
    max_download_mb: int = field(
        default_factory=lambda: int(_env("MAX_DOWNLOAD_MB", "500"))
    )
    download_max_height: int = field(
        default_factory=lambda: int(_env("DOWNLOAD_MAX_HEIGHT", "720"))
    )
    # Use published captions as the transcript source when available.
    captions_fast_path: bool = field(
        default_factory=lambda: _env("CAPTIONS", "on").lower() not in ("off", "0", "no")
    )

    # Persian digit style for Persian output: fa, en or keep.
    digit_mode: str = field(default_factory=lambda: _env("DIGITS", "fa"))
    # Burn-in style preset: cinema, reels or learning.
    style: str = field(default_factory=lambda: _env("STYLE", "cinema"))

    def __post_init__(self):
        if self.asr_engine not in ("auto", "persian", "whisper"):
            self.asr_engine = "auto"

    @property
    def model(self) -> str:
        """Backwards compatible alias for whisper_model."""
        return self.whisper_model

    @model.setter
    def model(self, value: str) -> None:
        self.whisper_model = value

    @property
    def max_download_bytes(self) -> int:
        return self.max_download_mb * 1024 * 1024

    @property
    def max_file_bytes(self) -> int:
        return self.max_file_mb * 1024 * 1024


def load_settings() -> Settings:
    return Settings()
