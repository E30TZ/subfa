"""The Persian tone layer: informal softening, auto resolution,
simple re-segmentation. The layer is lexical and conservative, so
the tests pin both what changes and what must never change."""

from subfa.srt import Cue
from subfa.tone import informalize, resegment_simple, resolve_tone


def test_informal_verb_endings():
    assert informalize("این کار انجام می‌شود.") == "این کار انجام میشه."
    assert informalize("او نمی‌تواند بیاید.") == "او نمی‌تونه بیاید."
    assert informalize("آن‌ها نمی‌خواهند بروند.") == "اونا نمی‌خوان بروند."
    assert informalize("معلم می‌گوید که دیر شده است.") == "معلم میگه که دیر شده."


def test_informal_copula_and_ra():
    assert informalize("این کتاب خوب است.") == "این کتاب خوبه."
    assert informalize("او را دیدم.") == "او رو دیدم."
    assert informalize("کتاب‌ها را برداشتم.") == "کتاب‌ها رو برداشتم."


def test_informal_never_touches_unsafe_spots():
    # است inside a longer word is not the copula.
    assert "استفاده" in informalize("از این استفاده می‌شود.")
    # را after a consonant ending stays را.
    assert informalize("این را دیدم.") == "این را دیدم."
    # A mid sentence است is not at a clause end and stays.
    assert informalize("کلمه است در جمله") == "کلمه است در جمله"
    # After a word ending in ه the copula has no safe spoken form here.
    assert informalize("این خانه است.") == "این خانه است."


def test_resolve_tone_explicit_passthrough():
    assert resolve_tone("formal", ["هر متنی"]) == "formal"
    assert resolve_tone("informal", ["هر متنی"]) == "informal"
    assert resolve_tone("simple", ["هر متنی"]) == "simple"
    assert resolve_tone("bogus", ["هر متنی"]) == "formal"


def test_resolve_tone_auto_reads_the_text():
    formal = ["این برنامه برای آموزش ساخته شده است و در ادامه بررسی می‌شود."]
    assert resolve_tone("auto", formal) == "formal"
    colloquial = [
        "سلام بچه‌ها، امروز می‌خوام یه چیزی رو بهتون نشون بدم که خیلی خوبه.",
        "اینو ببین، میشه راحت درستش کرد و دیگه لازم نیست نگران باشی.",
    ]
    assert resolve_tone("auto", colloquial) == "informal"


def test_resegment_simple_splits_at_conjunctions():
    cue = Cue(
        0.0,
        12.0,
        "این یک جمله بسیار طولانی است که چند ایده را با هم ترکیب می‌کند "
        "و بعد از آن هم ادامه پیدا می‌کند تا مخاطب خسته شود",
    )
    out = resegment_simple([cue])
    assert len(out) > 1
    for piece in out:
        assert piece.start >= 0.0 and piece.end <= 12.0
        assert len(piece.text.replace("\n", " ")) <= 60


def test_resegment_simple_keeps_short_cues_whole():
    cue = Cue(0.0, 2.0, "سلام به همه.")
    out = resegment_simple([cue])
    assert len(out) == 1
    assert out[0].text == "سلام به همه."
