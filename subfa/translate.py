"""Translation engines.

Translation is pluggable. The default implementation is Argos
Translate, which works fully offline after a one time model download.
A "none" translator returns the text unchanged, which is the right
choice when the target language is the source language. Tests use
FakeTranslator, so the suite never needs a model.
"""

from __future__ import annotations

from . import SubfaError

CHUNK_SIZE = 32


class Translator:
    name = "base"

    def translate(self, texts: list[str], source: str, target: str) -> list[str]:
        raise NotImplementedError

    def translate_window(
        self,
        core: list[str],
        before: list[str],
        after: list[str],
        source: str,
        target: str,
    ) -> list[str]:
        """Translate core cues with neighbouring context available.

        Context cues are for coherence only and must never appear in
        the output. The default implementation ignores the context;
        engines that can use it (LLM based ones) override this.
        """
        return self.translate(core, source, target)


def translate_with_context(
    translator: Translator,
    texts: list[str],
    source: str,
    target: str,
    window: int = 10,
    context: int = 2,
) -> list[str]:
    """Translate cue texts in sliding windows with context.

    Translating subtitle lines one by one loses pronouns, tense and
    sentence continuations. Each call carries a window of core cues
    plus up to `context` neighbouring cues on each side, marked as
    context through the translate_window interface. Output order and
    count match the input exactly.
    """
    results: list[str] = []
    for offset in range(0, len(texts), window):
        core = texts[offset : offset + window]
        before = texts[max(0, offset - context) : offset]
        after = texts[offset + window : offset + window + context]
        translated = translator.translate_window(core, before, after, source, target)
        if len(translated) != len(core):
            raise ValueError(
                "Translator returned "
                f"{len(translated)} lines for a window of {len(core)}."
            )
        results.extend(translated)
    return results


class NoneTranslator(Translator):
    """Skips translation and returns the input unchanged."""

    name = "none"

    def translate(self, texts, source, target):
        return list(texts)


class FakeTranslator(Translator):
    """Deterministic translator for tests.

    Prefixes each text with a target tag and counts chunk calls, so
    tests can assert both the output and the chunking behaviour.
    """

    name = "fake"

    def __init__(self, prefix: str = "[fa] "):
        self.prefix = prefix
        self.calls = 0
        self.chunk_sizes: list[int] = []
        # (before_count, core_count, after_count) per window, so tests
        # can prove how context windows were assembled.
        self.windows: list[tuple[int, int, int]] = []

    def translate(self, texts, source, target):
        self.calls += 1
        self.chunk_sizes.append(len(texts))
        return [self.prefix + text for text in texts]

    def translate_window(self, core, before, after, source, target):
        self.windows.append((len(before), len(core), len(after)))
        return [self.prefix + text for text in core]


class ArgosTranslator(Translator):
    """Offline translation through Argos Translate.

    The language package for a pair (for example en to fa) is
    downloaded once from the Argos package index, then reused.
    """

    name = "argos"

    def __init__(self, auto_install: bool = True):
        self.auto_install = auto_install

    def _get_language_pair(self, source: str, target: str):
        try:
            import argostranslate.package
            import argostranslate.translate
        except ImportError as exc:
            raise SubfaError(
                "argostranslate is not installed. Install it with: "
                "pip install argostranslate, or run with translator 'none'."
            ) from exc

        def find_pair():
            languages = argostranslate.translate.get_installed_languages()
            from_lang = next((l for l in languages if l.code == source), None)
            to_lang = next((l for l in languages if l.code == target), None)
            if from_lang is None or to_lang is None:
                return None
            return from_lang.get_translation(to_lang)

        translation = find_pair()
        if translation is None and self.auto_install:
            argostranslate.package.update_package_index()
            available = argostranslate.package.get_available_packages()
            package = next(
                (p for p in available if p.from_code == source and p.to_code == target),
                None,
            )
            if package is None:
                raise SubfaError(
                    f"No Argos translation package exists for {source} to {target}."
                )
            argostranslate.package.install_from_path(package.download())
            translation = find_pair()
        if translation is None:
            raise SubfaError(
                f"Argos translation package for {source} to {target} is not installed."
            )
        return translation

    def translate(self, texts, source, target):
        if source == target:
            return list(texts)
        translation = self._get_language_pair(source, target)
        return [translation.translate(text) for text in texts]


def translate_in_chunks(
    translator: Translator,
    texts: list[str],
    source: str,
    target: str,
    chunk_size: int = CHUNK_SIZE,
) -> list[str]:
    """Translate a list of cue texts in chunks, preserving order."""
    results: list[str] = []
    for offset in range(0, len(texts), chunk_size):
        chunk = texts[offset : offset + chunk_size]
        results.extend(translator.translate(chunk, source, target))
    return results


def make_translator(settings) -> Translator:
    name = getattr(settings, "translator", "argos")
    if name == "none":
        return NoneTranslator()
    if name == "fake":
        return FakeTranslator()
    return ArgosTranslator()
