import json

import pytest

from subfa.bilingual import merge_bilingual
from subfa.glossary import apply_glossary, load_glossary
from subfa.srt import Cue
from subfa.translate import FakeTranslator, translate_in_chunks


def test_glossary_replacement_case_insensitive():
    glossary = {"programming": "برنامه‌نویسی", "bug": "باگ"}
    assert apply_glossary("Programming is fun", glossary) == "برنامه‌نویسی is fun"
    # Word boundaries: "debug" is not rewritten by the "bug" entry.
    assert apply_glossary("Please debug this", glossary) == "Please debug this"


def test_glossary_longest_first(tmp_path):
    glossary = {"source": "منبع", "source code": "کد منبع"}
    assert apply_glossary("the source code here", glossary) == "the کد منبع here"


def test_load_glossary_from_directory(tmp_path):
    (tmp_path / "mine.json").write_text(
        json.dumps({"server": "سرور"}), encoding="utf-8"
    )
    assert load_glossary(["mine"], tmp_path) == {"server": "سرور"}


def test_load_glossary_missing_raises(tmp_path):
    with pytest.raises(Exception):
        load_glossary(["nope"], tmp_path)


def test_translation_chunking_preserves_order():
    translator = FakeTranslator(prefix="T:")
    texts = [f"line {i}" for i in range(70)]
    out = translate_in_chunks(translator, texts, "en", "fa", chunk_size=32)
    assert out == [f"T:line {i}" for i in range(70)]
    assert translator.chunk_sizes == [32, 32, 6]


def test_bilingual_merge_aligns_lines():
    source = [Cue(0, 1, "Hello"), Cue(1, 2, "World")]
    merged = merge_bilingual(source, ["سلام", "دنیا"])
    assert merged[0].text == "Hello\nسلام"
    assert merged[1].text == "World\nدنیا"
    assert (merged[0].start, merged[0].end) == (0, 1)


def test_bilingual_merge_rejects_misalignment():
    with pytest.raises(ValueError):
        merge_bilingual([Cue(0, 1, "Hello")], ["سلام", "اضافی"])
