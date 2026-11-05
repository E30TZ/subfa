import pytest

from bot.routing import classify_message


def test_bot_routes_link_message_to_url_flow():
    kind, url = classify_message("اینو ببین https://www.youtube.com/watch?v=abc مرسی")
    assert kind == "url"
    assert url == "https://www.youtube.com/watch?v=abc"


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
