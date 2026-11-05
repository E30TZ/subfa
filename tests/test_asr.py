"""ASR engine routing, anti-hallucination decoding, model downloads
and WER/CER metrics. Fully offline: fake engines and stubbed
downloaders only, no model is ever fetched here."""

from pathlib import Path

import pytest

from subfa import models as models_module
from subfa.config import Settings
from subfa.metrics import cer, wer
from subfa.transcribe import (
    FakeEngine,
    FasterWhisperEngine,
    PersianFineTunedEngine,
    RoutingEngine,
    Segment,
    make_engine,
)


def named_fake(name, language, marker):
    engine = FakeEngine(language=language, segments=[Segment(0.0, 1.0, marker)])
    engine.name = name
    return engine


def make_router():
    whisper = named_fake("faster-whisper", "en", "from whisper")
    persian = named_fake("persian-finetuned", "fa", "from persian")
    return RoutingEngine(whisper, persian, mode="auto"), whisper, persian


# -- config ------------------------------------------------------------

def test_asr_config_defaults():
    settings = Settings()
    assert settings.asr_engine == "auto"
    assert settings.whisper_model == "large-v3-turbo"
    assert settings.model == "large-v3-turbo"  # backwards compatible alias
    assert settings.persian_model == "nezamisafa/whisper-persian-v4"
    assert settings.model_cache.name == "models"
    # Anti-hallucination defaults
    assert settings.beam_size == 5
    assert settings.vad_filter is True
    assert settings.no_speech_threshold == 0.6
    assert settings.log_prob_threshold == -1.0
    assert settings.compression_ratio_threshold == 2.4
    assert settings.condition_on_previous_text is False


def test_asr_config_env_overrides(monkeypatch):
    monkeypatch.setenv("SUBFA_ASR_ENGINE", "persian")
    monkeypatch.setenv("SUBFA_WHISPER_MODEL", "tiny")
    monkeypatch.setenv("SUBFA_PERSIAN_MODEL", "someone/other-model")
    monkeypatch.setenv("SUBFA_MODEL_CACHE", "/tmp/subfa-models-test")
    settings = Settings()
    assert settings.asr_engine == "persian"
    assert settings.whisper_model == "tiny"
    assert settings.persian_model == "someone/other-model"
    # Compare as paths: on Windows the same location stringifies
    # with backslashes, which is the same directory.
    assert settings.model_cache == Path("/tmp/subfa-models-test")


def test_asr_config_legacy_model_env(monkeypatch):
    monkeypatch.delenv("SUBFA_WHISPER_MODEL", raising=False)
    monkeypatch.setenv("SUBFA_MODEL", "base")
    assert Settings().whisper_model == "base"


def test_asr_config_invalid_engine_falls_back_to_auto(monkeypatch):
    monkeypatch.setenv("SUBFA_ASR_ENGINE", "nonsense")
    assert Settings().asr_engine == "auto"


def test_model_alias_setter_updates_whisper_model():
    settings = Settings()
    settings.model = "tiny"
    assert settings.whisper_model == "tiny"


# -- routing -------------------------------------------------------------

def test_router_explicit_persian_uses_persian_engine():
    router, whisper, persian = make_router()
    result = router.transcribe("a.wav", "fa")
    assert result.segments[0].text == "from persian"
    assert result.engine == "persian-finetuned"
    assert persian.calls == 1 and whisper.calls == 0


def test_router_explicit_other_language_uses_whisper():
    router, whisper, persian = make_router()
    result = router.transcribe("a.wav", "de")
    assert result.segments[0].text == "from whisper"
    assert whisper.calls == 1 and persian.calls == 0


def test_router_auto_detects_persian():
    whisper = named_fake("faster-whisper", "fa", "from whisper")
    persian = named_fake("persian-finetuned", "fa", "from persian")
    router = RoutingEngine(whisper, persian, mode="auto")
    result = router.transcribe("a.wav", None)
    assert result.segments[0].text == "from persian"
    assert persian.calls == 1 and whisper.calls == 0


def test_router_auto_detects_english():
    router, whisper, persian = make_router()
    result = router.transcribe("a.wav", "auto")
    assert result.segments[0].text == "from whisper"
    assert whisper.calls == 1 and persian.calls == 0


def test_router_forced_modes():
    whisper = named_fake("faster-whisper", "en", "from whisper")
    persian = named_fake("persian-finetuned", "fa", "from persian")
    forced_persian = RoutingEngine(whisper, persian, mode="persian")
    assert forced_persian.transcribe("a.wav", "en").segments[0].text == "from persian"
    forced_whisper = RoutingEngine(whisper, persian, mode="whisper")
    assert forced_whisper.transcribe("a.wav", "fa").segments[0].text == "from whisper"


def test_make_engine_modes():
    settings = Settings()
    settings.asr_engine = "auto"
    assert isinstance(make_engine(settings), RoutingEngine)
    settings.asr_engine = "whisper"
    assert isinstance(make_engine(settings), FasterWhisperEngine)
    settings.asr_engine = "persian"
    assert isinstance(make_engine(settings), PersianFineTunedEngine)


# -- anti-hallucination decoding -----------------------------------------

class StubInfo:
    language = "en"


class StubModel:
    def __init__(self):
        self.kwargs = None

    def transcribe(self, path, **kwargs):
        self.kwargs = kwargs
        return iter([]), StubInfo()


def test_faster_whisper_decode_kwargs_are_anti_hallucination():
    engine = FasterWhisperEngine(model="large-v3-turbo")
    stub = StubModel()
    engine._model = stub
    engine.transcribe("a.wav", None)
    assert stub.kwargs["vad_filter"] is True
    assert stub.kwargs["no_speech_threshold"] == 0.6
    assert stub.kwargs["log_prob_threshold"] == -1.0
    assert stub.kwargs["compression_ratio_threshold"] == 2.4
    assert stub.kwargs["condition_on_previous_text"] is False
    assert stub.kwargs["beam_size"] == 5
    assert stub.kwargs["language"] is None


def test_faster_whisper_result_reports_engine_and_model():
    engine = FasterWhisperEngine(model="large-v3-turbo")
    engine._model = StubModel()
    result = engine.transcribe("a.wav", "en")
    assert result.engine == "faster-whisper"
    assert result.model == "large-v3-turbo"


# -- persian engine backend selection -------------------------------------

def test_persian_backend_ct2_when_model_bin_present(tmp_path):
    (tmp_path / "config.json").write_text("{}")
    (tmp_path / "model.bin").write_bytes(b"x")
    engine = PersianFineTunedEngine(model=str(tmp_path))
    assert engine.resolve_backend() == "ct2"


def test_persian_backend_transformers_for_safetensors_snapshot(tmp_path):
    (tmp_path / "config.json").write_text("{}")
    (tmp_path / "model.safetensors").write_bytes(b"x")
    engine = PersianFineTunedEngine(model=str(tmp_path))
    assert engine.resolve_backend() == "transformers"


def test_persian_backend_uses_offline_cache(tmp_path):
    snapshot = tmp_path / "persian" / "whisper-persian-v4"
    snapshot.mkdir(parents=True)
    (snapshot / "config.json").write_text("{}")
    engine = PersianFineTunedEngine(
        model="nezamisafa/whisper-persian-v4", cache_dir=tmp_path
    )
    assert engine._snapshot_dir() == snapshot
    assert engine.resolve_backend() == "transformers"


# -- download-models --------------------------------------------------------

def test_download_models_offline_with_stubs(tmp_path, monkeypatch):
    import faster_whisper.utils

    def fake_download_model(model, output_dir=None, **kwargs):
        path = tmp_path / "ct2"
        path.mkdir(exist_ok=True)
        (path / "model.bin").write_bytes(b"weights")
        return str(path)

    monkeypatch.setattr(
        faster_whisper.utils, "download_model", fake_download_model
    )

    import huggingface_hub

    def fake_snapshot_download(repo_id=None, local_dir=None, **kwargs):
        path = tmp_path / "fa"
        path.mkdir(exist_ok=True)
        (path / "config.json").write_text("{}")
        return str(path)

    monkeypatch.setattr(
        huggingface_hub, "snapshot_download", fake_snapshot_download
    )

    settings = Settings()
    settings.translator = "none"  # skip the Argos branch entirely
    settings.model_cache = tmp_path / "cache"
    logs: list[str] = []
    results = models_module.download_models(settings, log=logs.append)
    labels = [item["label"] for item in results]
    assert any("faster-whisper" in label for label in labels)
    assert any("persian" in label for label in labels)
    assert any("HF_HUB_OFFLINE=1" in line for line in logs)


def test_download_models_reports_hf_endpoint(tmp_path, monkeypatch):
    import faster_whisper.utils
    import huggingface_hub

    monkeypatch.setattr(
        faster_whisper.utils,
        "download_model",
        lambda model, output_dir=None, **kw: str(tmp_path),
    )
    monkeypatch.setattr(
        huggingface_hub,
        "snapshot_download",
        lambda repo_id=None, local_dir=None, **kw: str(tmp_path),
    )
    monkeypatch.setenv("HF_ENDPOINT", "https://mirror.example")
    settings = Settings()
    settings.translator = "none"
    settings.model_cache = tmp_path / "cache"
    # Pre-seed the cache so the stubs are not even needed for layout.
    logs: list[str] = []
    models_module.download_models(settings, log=logs.append)
    assert any("mirror.example" in line for line in logs)


# -- metrics ------------------------------------------------------------------

def test_wer_cer_perfect_and_wrong():
    assert wer("hello world", "hello world") == 0.0
    assert cer("hello world", "hello world") == 0.0
    assert wer("hello world", "hello there world") == pytest.approx(0.5)
    assert wer("hello world", "") == 1.0
    assert cer("abc", "abd") == pytest.approx(1 / 3)


def test_metrics_persian_normalization():
    # Arabic Yeh in the reference, Persian Yeh in the hypothesis,
    # and a missing ZWNJ in the hypothesis: all must count as the
    # same words, because ZWNJ is stripped during normalization.
    assert wer("سلام دنيا", "سلام دنیا", persian=True) == 0.0
    assert wer("می‌شود", "میشود", persian=True) == 0.0
    assert cer("کتاب‌ها", "کتابها", persian=True) == 0.0
