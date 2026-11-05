"""Model downloads for fully offline, local runs.

`subfa download-models` fetches every model the configured engines
need into Settings.model_cache (SUBFA_MODEL_CACHE):

- the faster-whisper model (CTranslate2 format),
- the Persian fine-tuned model snapshot (Hugging Face format),
- the Argos Translate packages for en/fa, when the translator is
  set to argos (Argos has its own package store).

After this command finishes, copy the cache folder anywhere and run
with HF_HUB_OFFLINE=1: no network access is needed at runtime.

Mirrors: every download goes through huggingface_hub or
faster-whisper's downloader, both of which respect the HF_ENDPOINT
environment variable, so an Iranian mirror can be used for the
initial fetch by setting HF_ENDPOINT before running this command.
Downloads show the libraries' own progress bars.
"""

from __future__ import annotations

import os
from pathlib import Path

from . import SubfaError
from .transcribe import ct2_cache_dir, persian_cache_dir


def _dir_size(path: Path) -> int:
    total = 0
    for item in Path(path).rglob("*"):
        if item.is_file():
            total += item.stat().st_size
    return total


def download_faster_whisper_model(settings, log=print) -> dict:
    """Download the configured faster-whisper model into the cache."""
    target = ct2_cache_dir(settings.model_cache, settings.whisper_model)
    if (target / "model.bin").exists():
        log(f"faster-whisper model already in cache: {target}")
    else:
        try:
            from faster_whisper.utils import download_model
        except ImportError as exc:
            raise SubfaError(
                "faster-whisper is not installed. Install it with: "
                "pip install faster-whisper"
            ) from exc
        target.mkdir(parents=True, exist_ok=True)
        log(
            f"Downloading faster-whisper model "
            f"'{settings.whisper_model}' to {target} ..."
        )
        download_model(settings.whisper_model, output_dir=str(target))
    return {
        "label": f"faster-whisper / {settings.whisper_model}",
        "path": str(target),
        "bytes": _dir_size(target),
    }


def download_persian_model(settings, log=print) -> dict:
    """Download the Persian fine-tuned model snapshot into the cache."""
    model = settings.persian_model
    if Path(model).is_dir():
        log(f"Persian model is a local folder, nothing to download: {model}")
        return {"label": f"persian / {model}", "path": model, "bytes": _dir_size(Path(model))}
    target = persian_cache_dir(settings.model_cache, model)
    if (target / "config.json").exists():
        log(f"Persian model already in cache: {target}")
    else:
        try:
            from huggingface_hub import snapshot_download
        except ImportError as exc:
            raise SubfaError(
                "huggingface_hub is not installed. Install it with: "
                "pip install huggingface_hub"
            ) from exc
        target.mkdir(parents=True, exist_ok=True)
        log(f"Downloading Persian model '{model}' to {target} ...")
        snapshot_download(
            repo_id=model,
            local_dir=str(target),
            ignore_patterns=["runs/*"],
        )
    return {
        "label": f"persian / {model}",
        "path": str(target),
        "bytes": _dir_size(target),
    }


def download_argos_packages(settings, log=print) -> dict | None:
    """Install the en/fa Argos packages when argos is the translator.

    Argos keeps its own model store; this uses its public API.
    Returns None when argos is not configured or not installed, and
    never fails the whole download when the Argos index is having a
    bad day: the failure is reported in the log instead.
    """
    if settings.translator != "argos":
        return None
    try:
        import argostranslate.package
        import argostranslate.translate
    except ImportError:
        log("argostranslate is not installed, skipping translation packages.")
        return None
    try:
        argostranslate.package.update_package_index()
        available = argostranslate.package.get_available_packages()
        installed = argostranslate.package.get_installed_packages()
        installed_pairs = {(p.from_code, p.to_code) for p in installed}
        fetched = []
        for from_code, to_code in (("en", "fa"), ("fa", "en")):
            if (from_code, to_code) in installed_pairs:
                fetched.append(f"{from_code}->{to_code} (already installed)")
                continue
            package = next(
                (
                    p
                    for p in available
                    if p.from_code == from_code and p.to_code == to_code
                ),
                None,
            )
            if package is None:
                log(f"No Argos package found for {from_code}->{to_code}, skipped.")
                continue
            log(f"Downloading Argos package {from_code}->{to_code} ...")
            argostranslate.package.install_from_path(package.download())
            fetched.append(f"{from_code}->{to_code}")
        return {"label": "argos packages: " + ", ".join(fetched), "path": "", "bytes": 0}
    except Exception as exc:  # network or index problems: report, do not fail
        log(f"Argos package download skipped after an error: {exc}")
        return None


def download_models(settings, log=print) -> list[dict]:
    """Download every model the configured engines need."""
    cache = Path(settings.model_cache)
    cache.mkdir(parents=True, exist_ok=True)
    endpoint = os.environ.get("HF_ENDPOINT")
    if endpoint:
        log(f"HF_ENDPOINT is set, downloads will use this mirror: {endpoint}")
    log(f"Model cache: {cache}")
    results = [
        download_faster_whisper_model(settings, log=log),
        download_persian_model(settings, log=log),
    ]
    argos = download_argos_packages(settings, log=log)
    if argos is not None:
        results.append(argos)
    total = sum(item["bytes"] for item in results)
    log(f"Done. Models on disk: {total / 1e9:.2f} GB in {cache}")
    log(
        "Offline runs: set HF_HUB_OFFLINE=1 and keep "
        "SUBFA_MODEL_CACHE pointing at this folder."
    )
    return results
