"""Transcription engines.

An engine turns an audio file into timed text segments. Tests use
FakeEngine, so no model download is ever needed to run the suite.

Production routing (Settings.asr_engine, default "auto"):

- Persian audio goes to PersianFineTunedEngine: a Whisper model
  fine-tuned for Persian (default nezamisafa/whisper-persian-v4,
  the top Persian model on the PESTE benchmark). Stock Whisper is
  weak on Persian, so this distinction matters. See docs/ASR.md.
- Everything else goes to FasterWhisperEngine (default model
  large-v3-turbo) with anti-hallucination decoding: VAD filtering
  plus conservative no-speech, log-probability and compression
  thresholds, and no conditioning on previous text. That combination
  is the standard fix for Whisper inventing text on silence.

RoutingEngine decides per job. When the source language is given,
routing is direct. When it is "auto", the faster-whisper model
detects the language first (detection is cheap: it only needs the
start of the audio) and Persian detections are handed to the
Persian engine.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from . import SubfaError


@dataclass
class Segment:
    start: float
    end: float
    text: str


@dataclass
class TranscriptionResult:
    segments: list[Segment]
    language: str = "en"
    # Which engine and model actually produced this result. The job
    # report copies these, so users are told the truth per job.
    engine: str = ""
    model: str = ""


class TranscriptionEngine:
    """Interface every transcription engine must implement."""

    name = "base"

    def transcribe(self, audio_path: str | Path, language: str | None) -> TranscriptionResult:
        raise NotImplementedError


def ct2_cache_dir(cache_dir, model: str) -> Path:
    """Where download-models stores a faster-whisper (CTranslate2) model."""
    return Path(cache_dir) / "faster-whisper" / model.replace("/", "--")


def persian_cache_dir(cache_dir, model: str) -> Path:
    """Where download-models stores the Persian model snapshot."""
    return Path(cache_dir) / "persian" / model.rstrip("/").split("/")[-1]


def resolve_ct2_model(model: str, cache_dir=None) -> str:
    """Resolve a faster-whisper model to a local folder when the
    offline cache (or the given path itself) holds a CTranslate2
    conversion; otherwise return the model id for the hub lookup."""
    path = Path(model)
    if (path / "model.bin").exists():
        return str(path)
    if cache_dir:
        candidate = ct2_cache_dir(cache_dir, model)
        if (candidate / "model.bin").exists():
            return str(candidate)
    return model


class FasterWhisperEngine(TranscriptionEngine):
    name = "faster-whisper"

    def __init__(
        self,
        model: str = "large-v3-turbo",
        compute_type: str = "int8",
        cache_dir=None,
        beam_size: int = 5,
        vad_filter: bool = True,
        no_speech_threshold: float = 0.6,
        log_prob_threshold: float = -1.0,
        compression_ratio_threshold: float = 2.4,
        condition_on_previous_text: bool = False,
    ):
        self.model_name = model
        self.compute_type = compute_type
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.beam_size = beam_size
        self.vad_filter = vad_filter
        self.no_speech_threshold = no_speech_threshold
        self.log_prob_threshold = log_prob_threshold
        self.compression_ratio_threshold = compression_ratio_threshold
        self.condition_on_previous_text = condition_on_previous_text
        self._model = None

    @property
    def resolved_model(self) -> str:
        return resolve_ct2_model(self.model_name, self.cache_dir)

    def _load(self):
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise SubfaError(
                    "faster-whisper is not installed. Install it with: "
                    "pip install faster-whisper"
                ) from exc
            download_root = (
                str(self.cache_dir / "faster-whisper") if self.cache_dir else None
            )
            self._model = WhisperModel(
                self.resolved_model,
                compute_type=self.compute_type,
                download_root=download_root,
            )
        return self._model

    def decode_kwargs(self, language: str | None) -> dict:
        """The decode options used for every transcription, including
        the anti-hallucination set. Kept in one place so tests can
        pin them down."""
        return {
            "language": None if language in (None, "auto") else language,
            "beam_size": self.beam_size,
            "vad_filter": self.vad_filter,
            "no_speech_threshold": self.no_speech_threshold,
            "log_prob_threshold": self.log_prob_threshold,
            "compression_ratio_threshold": self.compression_ratio_threshold,
            "condition_on_previous_text": self.condition_on_previous_text,
        }

    def detect_language(self, audio_path) -> str | None:
        """Detect the spoken language without a full transcription."""
        model = self._load()
        _segments, info = model.transcribe(
            str(audio_path), beam_size=1, without_timestamps=True
        )
        return getattr(info, "language", None)

    def transcribe(self, audio_path, language=None):
        model = self._load()
        segments_iter, info = model.transcribe(
            str(audio_path), **self.decode_kwargs(language)
        )
        segments = [
            Segment(start=s.start, end=s.end, text=s.text.strip())
            for s in segments_iter
            if s.text.strip()
        ]
        return TranscriptionResult(
            segments=segments,
            language=getattr(info, "language", language or "en") or "en",
            engine=self.name,
            model=self.model_name,
        )


def _audio_duration(audio_path) -> float:
    """Duration in seconds via ffprobe; 0.0 when it cannot be read."""
    try:
        completed = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(audio_path),
            ],
            capture_output=True, text=True, timeout=30,
        )
        return float(completed.stdout.strip())
    except (subprocess.SubprocessError, ValueError, OSError):
        return 0.0


class PersianFineTunedEngine(TranscriptionEngine):
    """Persian ASR from a fine-tuned Whisper model.

    Default model: nezamisafa/whisper-persian-v4, a fine-tune of
    whisper-large-v3 and the top entry on the PESTE Persian
    benchmark (docs/ASR.md).

    Backends, picked from what is on disk:
    - If the resolved model folder contains model.bin, it is a
      CTranslate2 conversion and faster-whisper runs it (fastest).
    - Otherwise the Hugging Face transformers pipeline runs the
      safetensors snapshot. No official CTranslate2 conversion of
      this model is published, so transformers is the default path.
    """

    name = "persian-finetuned"

    def __init__(
        self,
        model: str = "nezamisafa/whisper-persian-v4",
        cache_dir=None,
        compute_type: str = "int8",
        dtype: str = "float16",
        device: str | None = None,
    ):
        self.model_id = model
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.compute_type = compute_type
        self.dtype = dtype
        self.device = device
        self._pipeline = None
        self._ct2_engine: FasterWhisperEngine | None = None

    def _snapshot_dir(self) -> Path | None:
        path = Path(self.model_id)
        if path.is_dir():
            return path
        if self.cache_dir:
            candidate = persian_cache_dir(self.cache_dir, self.model_id)
            if (candidate / "config.json").exists():
                return candidate
        return None

    def resolve_backend(self) -> str:
        """Return "ct2" when a CTranslate2 conversion is on disk,
        otherwise "transformers"."""
        snapshot = self._snapshot_dir()
        if snapshot is not None and (snapshot / "model.bin").exists():
            return "ct2"
        return "transformers"

    def _load_pipeline(self):
        if self._pipeline is not None:
            return self._pipeline
        try:
            import torch
            from transformers import pipeline
        except ImportError as exc:
            raise SubfaError(
                "The Persian engine needs transformers and torch. "
                "Install them with: pip install \"subfa[persian]\" "
                "(or pip install transformers torch safetensors)."
            ) from exc
        snapshot = self._snapshot_dir()
        model_ref = str(snapshot) if snapshot is not None else self.model_id
        dtype = getattr(torch, self.dtype, torch.float16)
        device = self.device
        if device is None:
            device = 0 if torch.cuda.is_available() else -1
        kwargs = {"model": model_ref, "device": device, "chunk_length_s": 30}
        try:
            self._pipeline = pipeline(
                "automatic-speech-recognition", dtype=dtype, **kwargs
            )
        except TypeError:
            # transformers versions before the dtype rename.
            self._pipeline = pipeline(
                "automatic-speech-recognition", torch_dtype=dtype, **kwargs
            )
        return self._pipeline

    def transcribe(self, audio_path, language=None):
        # This engine is Persian only; the language hint is ignored
        # on purpose so a wrong "auto" guess cannot leak through.
        if self.resolve_backend() == "ct2":
            if self._ct2_engine is None:
                snapshot = self._snapshot_dir()
                self._ct2_engine = FasterWhisperEngine(
                    model=str(snapshot), compute_type=self.compute_type
                )
            result = self._ct2_engine.transcribe(audio_path, "fa")
            return TranscriptionResult(
                segments=result.segments,
                language="fa",
                engine=self.name,
                model=f"{self.model_id} (ctranslate2)",
            )
        pipe = self._load_pipeline()
        output = pipe(
            str(audio_path),
            return_timestamps=True,
            generate_kwargs={"language": "fa", "task": "transcribe"},
        )
        segments: list[Segment] = []
        for chunk in output.get("chunks") or []:
            start, end = chunk.get("timestamp") or (0.0, 0.0)
            text = (chunk.get("text") or "").strip()
            if text:
                segments.append(
                    Segment(
                        start=float(start or 0.0),
                        end=float(end) if end else _audio_duration(audio_path),
                        text=text,
                    )
                )
        if not segments and (output.get("text") or "").strip():
            segments.append(
                Segment(
                    start=0.0,
                    end=_audio_duration(audio_path),
                    text=output["text"].strip(),
                )
            )
        return TranscriptionResult(
            segments=segments,
            language="fa",
            engine=self.name,
            model=f"{self.model_id} (transformers)",
        )


class RoutingEngine(TranscriptionEngine):
    """Routes each job to the Persian engine or to faster-whisper.

    mode "persian" always uses the Persian engine, mode "whisper"
    always uses faster-whisper, mode "auto" routes by the requested
    language and, when that is "auto", by a quick detection pass.
    """

    name = "asr-router"

    def __init__(
        self,
        whisper_engine: TranscriptionEngine,
        persian_engine: TranscriptionEngine,
        mode: str = "auto",
    ):
        self.whisper = whisper_engine
        self.persian = persian_engine
        self.mode = mode if mode in ("auto", "persian", "whisper") else "auto"

    def transcribe(self, audio_path, language=None):
        requested = None if language in (None, "auto") else language
        if self.mode == "persian":
            return self.persian.transcribe(audio_path, "fa")
        if self.mode == "whisper":
            return self.whisper.transcribe(audio_path, requested)
        if requested == "fa":
            return self.persian.transcribe(audio_path, "fa")
        if requested:
            return self.whisper.transcribe(audio_path, requested)
        detected = None
        detect = getattr(self.whisper, "detect_language", None)
        if detect is not None:
            try:
                detected = detect(audio_path)
            except Exception:
                detected = None
        if detected == "fa":
            return self.persian.transcribe(audio_path, "fa")
        return self.whisper.transcribe(audio_path, None)


@dataclass
class FakeEngine(TranscriptionEngine):
    """Deterministic engine for tests and demos. Never downloads."""

    name = "fake"
    language: str = "en"
    segments: list[Segment] = field(
        default_factory=lambda: [
            Segment(0.0, 2.5, "Hello world, this is a test."),
            Segment(2.5, 5.0, "Programming is fun and useful."),
        ]
    )
    calls: int = 0

    def detect_language(self, audio_path):
        return self.language

    def transcribe(self, audio_path, language=None):
        self.calls += 1
        return TranscriptionResult(
            segments=list(self.segments),
            language=self.language,
            engine=self.name,
            model="fake",
        )


def make_engine(settings) -> TranscriptionEngine:
    whisper = FasterWhisperEngine(
        model=settings.whisper_model,
        compute_type=settings.compute_type,
        cache_dir=settings.model_cache,
        beam_size=settings.beam_size,
        vad_filter=settings.vad_filter,
        no_speech_threshold=settings.no_speech_threshold,
        log_prob_threshold=settings.log_prob_threshold,
        compression_ratio_threshold=settings.compression_ratio_threshold,
        condition_on_previous_text=settings.condition_on_previous_text,
    )
    persian = PersianFineTunedEngine(
        model=settings.persian_model,
        cache_dir=settings.model_cache,
        compute_type=settings.compute_type,
        dtype=settings.persian_dtype,
    )
    mode = settings.asr_engine
    if mode == "whisper":
        return whisper
    if mode == "persian":
        return persian
    return RoutingEngine(whisper, persian, mode="auto")
