"""Quality point 2: Persian text cleanup with real examples."""

from subfa.fa_text import apply_zwnj, clean_fa_text, fix_punctuation, normalize_chars


def test_arabic_yeh_kaf_normalized():
    assert normalize_chars("يك كتاب") == "یک کتاب"
    assert clean_fa_text("سلام يك دنيا") == "سلام یک دنیا"


def test_zwnj_for_mi_prefix():
    assert apply_zwnj("می شود") == "می‌شود"
    assert apply_zwnj("نمی روم") == "نمی‌روم"
    assert clean_fa_text("او می رود به مدرسه") == "او می‌رود به مدرسه"


def test_zwnj_for_plural_ha():
    assert apply_zwnj("کتاب ها") == "کتاب‌ها"
    assert apply_zwnj("این کتاب های من است") == "این کتاب‌های من است"


def test_punctuation_spacing():
    assert fix_punctuation("سلام ، خوبی ؟") == "سلام، خوبی؟"
    assert fix_punctuation("گفت:سلام") == "گفت: سلام"


def test_quotes_hug_content_and_convert():
    assert fix_punctuation("« سلام »") == "«سلام»"
    cleaned = fix_punctuation('او گفت "سلام" و رفت')
    assert cleaned == "او گفت «سلام» و رفت"


def test_digits_to_persian():
    assert clean_fa_text("سال 2026 و ٣ فصل", digits="fa") == "سال ۲۰۲۶ و ۳ فصل"


def test_digits_to_english():
    assert clean_fa_text("سال ۲۰۲۶", digits="en") == "سال 2026"


def test_digits_keep_mode():
    assert clean_fa_text("سال 2026", digits="keep") == "سال 2026"


def test_known_compounds_get_zwnj():
    assert clean_fa_text("برنامه نویسی سرگرم کننده است") == "برنامه‌نویسی سرگرم کننده است"
    assert clean_fa_text("این نرم افزار خوب است") == "این نرم‌افزار خوب است"


def test_full_cleanup_example():
    raw = "يك ويديو جديد در سال 2026 مي آيد ، ببين"
    out = clean_fa_text(raw, digits="fa")
    assert "یک" in out
    assert "۲۰۲۶" in out
    assert "، ببین" in out
    assert " ،" not in out
