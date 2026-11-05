"""Translation engines.

Translation is pluggable. The default implementation is Argos
Translate, which works fully offline after a one time model download.
An OpenAI-compatible LLM endpoint can be selected instead
(SUBFA_TRANSLATOR=llm); it translates with the surrounding cues as
context, which keeps the meaning far closer to the source than
word-by-word offline translation of noisy captions. The LLM
translator falls back to Argos per chunk when the endpoint fails or
returns the wrong number of lines, so a flaky endpoint degrades the
job instead of killing it. A "none" translator returns the text
unchanged, which is the right choice when the target language is
the source language. Tests use FakeTranslator, so the suite never
needs a model.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from . import SubfaError

CHUNK_SIZE = 32

LANGUAGE_NAMES = {
    "fa": "Persian",
    "en": "English",
    "ar": "Arabic",
    "tr": "Turkish",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "ru": "Russian",
}


def _language_name(code: str) -> str:
    return LANGUAGE_NAMES.get(code, code)


class Translator:
    name = "base"

    def describe(self) -> str:
        """Short label recorded in the job report."""
        return self.name

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


class LlmTranslator(Translator):
    """Translation through an OpenAI-compatible chat endpoint.

    Each window of cues is sent as one chat completion together with
    the neighbouring context cues. The model must answer with ONLY a
    JSON array of translated strings, in the same order and count as
    the core lines. A count mismatch is retried once; after that, or
    on any request or parse failure, the chunk falls back to the
    fallback translator (Argos by default) so one bad chunk never
    fails the whole job.
    """

    name = "llm"

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "",
        fallback: Translator | None = None,
        timeout: float = 180.0,
        http_post=None,
    ):
        if not base_url or not model:
            raise SubfaError(
                "SUBFA_TRANSLATOR=llm needs SUBFA_LLM_BASE_URL and "
                "SUBFA_LLM_MODEL to be set."
            )
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.fallback = fallback
        self.timeout = timeout
        self._http_post = http_post or self._urllib_post

    def describe(self) -> str:
        return f"llm ({self.model})"

    # -- HTTP layer ---------------------------------------------------

    def _urllib_post(self, url: str, payload: dict, headers: dict) -> dict:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _request_lines(
        self,
        core: list[str],
        before: list[str],
        after: list[str],
        source: str,
        target: str,
    ) -> list[str]:
        source_name = _language_name(source)
        target_name = _language_name(target)
        system = (
            "You are a professional subtitle translator. Translate "
            f"subtitle lines from {source_name} to {target_name}. "
            "Keep the meaning faithful to the source and use natural, "
            f"fluent {target_name} as spoken in real subtitles. "
            "You are given the lines to translate plus neighbouring "
            "context lines before and after them; use the context for "
            "pronouns, tense and sentence continuations, but translate "
            "ONLY the core lines. Reply with ONLY a JSON array of "
            "strings: the translated core lines, in the same order "
            f"and exactly {len(core)} items. No commentary, no keys."
        )
        user = json.dumps(
            {
                "context_before": before,
                "lines": core,
                "context_after": after,
            },
            ensure_ascii=False,
        )
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        data = self._http_post(
            f"{self.base_url}/chat/completions", payload, headers
        )
        content = data["choices"][0]["message"]["content"]
        return self._parse_lines(content)

    @staticmethod
    def _parse_lines(content: str) -> list[str]:
        text = content.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()
        start, end = text.find("["), text.rfind("]")
        if start >= 0 and end > start:
            text = text[start : end + 1]
        parsed = json.loads(text)
        if not isinstance(parsed, list) or not all(
            isinstance(item, str) for item in parsed
        ):
            raise ValueError("LLM reply is not a JSON array of strings.")
        return parsed

    # -- Translator interface ------------------------------------------

    def _translate_chunk(
        self,
        core: list[str],
        before: list[str],
        after: list[str],
        source: str,
        target: str,
    ) -> list[str]:
        last_error: Exception | None = None
        for _attempt in range(2):
            try:
                lines = self._request_lines(core, before, after, source, target)
                if len(lines) == len(core):
                    return lines
                last_error = ValueError(
                    f"LLM returned {len(lines)} lines for {len(core)} cues."
                )
            except Exception as exc:  # request, parse or shape failure
                last_error = exc
        if self.fallback is not None:
            return self.fallback.translate(core, source, target)
        raise SubfaError(f"LLM translation failed: {last_error}")

    def translate(self, texts, source, target):
        if source == target:
            return list(texts)
        return self._translate_chunk(list(texts), [], [], source, target)

    def translate_window(self, core, before, after, source, target):
        if source == target:
            return list(core)
        return self._translate_chunk(
            list(core), list(before), list(after), source, target
        )


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
    if name == "llm":
        return LlmTranslator(
            base_url=getattr(settings, "llm_base_url", ""),
            model=getattr(settings, "llm_model", ""),
            api_key=getattr(settings, "llm_api_key", ""),
            fallback=ArgosTranslator(),
        )
    return ArgosTranslator()
