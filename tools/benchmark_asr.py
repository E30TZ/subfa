#!/usr/bin/env python3
"""Benchmark SubFa speech recognition engines on labelled clips.

Usage:
    python tools/benchmark_asr.py [--manifest tools/benchmark_manifest.json]
                                  [--engine whisper|persian|router|all]

The manifest is a JSON list of items:
    {"audio": "relative/or/absolute/path.wav",
     "reference": "the exact transcript of the clip",
     "language": "fa"}

Audio paths are resolved relative to the manifest file. For every
item, each selected engine transcribes the clip and the script
prints WER and CER against the reference (normalization and metric
definitions live in subfa/metrics.py), plus wall time.

Models are never downloaded implicitly by the test suite; run
`subfa download-models` first for real models. A failed engine is
reported as an ERROR row with its message, never hidden.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from subfa.config import load_settings  # noqa: E402
from subfa.metrics import cer, wer  # noqa: E402
from subfa.transcribe import (  # noqa: E402
    FasterWhisperEngine,
    PersianFineTunedEngine,
    RoutingEngine,
    make_engine,
)


def build_engines(settings, choice: str) -> dict:
    engines: dict = {}
    if choice in ("whisper", "all"):
        engines["whisper"] = FasterWhisperEngine(
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
    if choice in ("persian", "all"):
        engines["persian"] = PersianFineTunedEngine(
            model=settings.persian_model,
            cache_dir=settings.model_cache,
            compute_type=settings.compute_type,
            dtype=settings.persian_dtype,
        )
    if choice in ("router", "all"):
        engines["router"] = make_engine(settings)
    return engines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        default=str(Path(__file__).with_name("benchmark_manifest.json")),
    )
    parser.add_argument(
        "--engine", choices=["whisper", "persian", "router", "all"], default="all"
    )
    args = parser.parse_args(argv)

    manifest_path = Path(args.manifest)
    items = json.loads(manifest_path.read_text(encoding="utf-8"))
    base = manifest_path.resolve().parent
    settings = load_settings()
    engines = build_engines(settings, args.engine)

    print(f"Manifest: {manifest_path} ({len(items)} clips)")
    print(f"{'clip':28} {'engine':10} {'WER':>7} {'CER':>7} {'time':>7}  hypothesis")
    failures = 0
    for item in items:
        audio = Path(item["audio"])
        if not audio.is_absolute():
            audio = base / audio
        reference = item["reference"]
        language = item.get("language")
        persian = language == "fa"
        for name, engine in engines.items():
            started = time.time()
            try:
                result = engine.transcribe(
                    audio, None if not language else language
                )
            except Exception as exc:  # report honestly, keep going
                failures += 1
                print(f"{audio.name:28} {name:10} {'ERROR':>7} {'':>7} "
                      f"{time.time() - started:6.1f}s  {exc}")
                continue
            elapsed = time.time() - started
            hypothesis = " ".join(seg.text for seg in result.segments)
            print(
                f"{audio.name:28} {name:10} "
                f"{wer(reference, hypothesis, persian):7.3f} "
                f"{cer(reference, hypothesis, persian):7.3f} "
                f"{elapsed:6.1f}s  {hypothesis}"
            )
    return 1 if failures and failures == len(items) * len(engines) else 0


if __name__ == "__main__":
    raise SystemExit(main())
