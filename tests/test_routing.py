import pytest

from bot.routing import (
    LangStore,
    classify_message,
    default_ui_lang,
    parse_ui_callback,
)


def test_bot_routes_link_message_to_url_flow():
    kind, url = classify_message("اینو ببین https://www.youtube.com/watch?v=abc مرسی")
    assert kind == "url"
    assert url == "https://www.youtube.com/watch?v=abc"


def test_ui_language_selection_routing(tmp_path):
    # The picker callbacks route to a stored per chat choice.
    assert parse_ui_callback("ui:fa") == "fa"
    assert parse_ui_callback("ui:en") == "en"
    assert parse_ui_callback("ui:fr") is None
    # The subtitle flow's callbacks must not be swallowed.
    assert parse_ui_callback("lang:fa") is None
    assert parse_ui_callback(None) is None

    store = LangStore(tmp_path / "lang.json")
    # Defaults: fa clients get Persian, other known codes English,
    # no code at all still Persian.
    assert store.get(1, "fa-IR") == "fa"
    assert store.get(2, "en") == "en"
    assert store.get(3, None) == "fa"
    assert default_ui_lang("de") == "en"

    store.set(2, "fa")
    assert store.get(2, "en") == "fa"
    # The choice survives a restart (fresh store, same file).
    assert LangStore(tmp_path / "lang.json").get(2, "en") == "fa"
    # Unknown languages are ignored, never stored.
    store.set(2, "fr")
    assert store.get(2, "en") == "fa"


def test_bot_routes_plain_text_to_help():
    kind, url = classify_message("سلام")
    assert kind == "help" and url is None


def test_cli_help_mentions_url_and_link(tmp_path):
    from subfa.cli import build_parser

    help_text = build_parser().format_help()
    assert "--url" in help_text
    assert "link" in help_text.lower()


def test_web_decide_input_routes_file_then_url():
    pytest.importorskip("fastapi")
    from web.app import decide_input

    assert decide_input("movie.mp4", "")[0] == "file"
    assert decide_input(None, "https://youtu.be/xyz") == (
        "url",
        "https://youtu.be/xyz",
    )
    # A file wins over a pasted link.
    assert decide_input("movie.mp4", "https://youtu.be/xyz")[0] == "file"
    with pytest.raises(ValueError):
        decide_input(None, "not a link")
    with pytest.raises(ValueError):
        decide_input(None, "")
