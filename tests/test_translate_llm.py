"""LLM translator: OpenAI-compatible endpoint, mocked HTTP layer.

No network and no real endpoint in any of these tests; the HTTP
call is injected, exactly like the production urllib one is shaped.
"""

import json

import pytest

from subfa import SubfaError
from subfa.config import Settings
from subfa.translate import (
    FakeTranslator,
    LlmTranslator,
    make_translator,
    translate_with_context,
)


def reply_with(lines):
    """An http_post fake answering with the given JSON array lines."""
    calls = []

    def post(url, payload, headers):
        calls.append((url, payload, headers))
        return {
            "choices": [
                {"message": {"content": json.dumps(lines, ensure_ascii=False)}}
            ]
        }

    post.calls = calls
    return post


def make_llm(post, fallback=None):
    return LlmTranslator(
        base_url="http://llm.local/v1",
        model="test-model",
        fallback=fallback,
        http_post=post,
    )


def test_llm_translate_window_uses_context_and_parses_array():
    post = reply_with(["سلام دنیا", "برنامه‌نویسی جالب است"])
    llm = make_llm(post)
    out = llm.translate_window(
        ["Hello world", "Programming is fun"],
        ["Previous line"],
        ["Next line"],
        "en",
        "fa",
    )
    assert out == ["سلام دنیا", "برنامه‌نویسی جالب است"]
    url, payload, headers = post.calls[0]
    assert url == "http://llm.local/v1/chat/completions"
    assert payload["model"] == "test-model"
    user = json.loads(payload["messages"][1]["content"])
    assert user["lines"] == ["Hello world", "Programming is fun"]
    assert user["context_before"] == ["Previous line"]
    assert user["context_after"] == ["Next line"]
    system = payload["messages"][0]["content"]
    assert "ONLY a JSON array" in system
    # No key configured, so no Authorization header is sent.
    assert "Authorization" not in headers


def test_llm_sends_bearer_key_when_configured():
    post = reply_with(["سلام"])
    llm = LlmTranslator(
        base_url="http://llm.local/v1", model="m", api_key="secret-key",
        http_post=post,
    )
    llm.translate(["Hello"], "en", "fa")
    assert post.calls[0][2]["Authorization"] == "Bearer secret-key"


def test_llm_parses_code_fenced_reply():
    def post(url, payload, headers):
        return {"choices": [{"message": {"content": "```json\n[\"سلام\"]\n```"}}]}

    llm = make_llm(post)
    assert llm.translate(["Hello"], "en", "fa") == ["سلام"]


def test_llm_retries_once_on_count_mismatch():
    answers = [["only one"], ["سلام", "دنیا"]]
    calls = []

    def post(url, payload, headers):
        lines = answers[len(calls)]
        calls.append(1)
        return {
            "choices": [
                {"message": {"content": json.dumps(lines, ensure_ascii=False)}}
            ]
        }

    llm = make_llm(post)
    out = llm.translate(["Hello", "World"], "en", "fa")
    assert out == ["سلام", "دنیا"]
    assert len(calls) == 2


def test_llm_falls_back_to_argos_side_on_persistent_mismatch():
    post = reply_with(["only one"])
    fallback = FakeTranslator(prefix="[fallback] ")
    llm = make_llm(post, fallback=fallback)
    out = llm.translate(["Hello", "World"], "en", "fa")
    assert out == ["[fallback] Hello", "[fallback] World"]


def test_llm_falls_back_on_http_error():
    def post(url, payload, headers):
        raise OSError("connection refused")

    fallback = FakeTranslator(prefix="[fallback] ")
    llm = make_llm(post, fallback=fallback)
    out = llm.translate(["Hello"], "en", "fa")
    assert out == ["[fallback] Hello"]


def test_llm_without_fallback_raises_subfa_error():
    def post(url, payload, headers):
        raise OSError("connection refused")

    llm = make_llm(post)
    with pytest.raises(SubfaError):
        llm.translate(["Hello"], "en", "fa")


def test_llm_same_language_short_circuits_without_http():
    post = reply_with([])
    llm = make_llm(post)
    assert llm.translate(["سلام"], "fa", "fa") == ["سلام"]
    assert post.calls == []


def test_llm_works_through_translate_with_context():
    post = reply_with(["الف", "ب"])
    llm = make_llm(post)
    out = translate_with_context(llm, ["a", "b"], "en", "fa", window=10, context=2)
    assert out == ["الف", "ب"]
    user = json.loads(post.calls[0][1]["messages"][1]["content"])
    assert user["lines"] == ["a", "b"]


def test_make_translator_llm_from_settings():
    settings = Settings()
    settings.translator = "llm"
    settings.llm_base_url = "http://llm.local/v1"
    settings.llm_model = "test-model"
    translator = make_translator(settings)
    assert isinstance(translator, LlmTranslator)
    assert translator.describe() == "llm (test-model)"


def test_make_translator_llm_requires_endpoint_config():
    settings = Settings()
    settings.translator = "llm"
    with pytest.raises(SubfaError):
        make_translator(settings)
