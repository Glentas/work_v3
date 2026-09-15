"""Алфавитный метод: профили букв, диакритика, критерий Крапивина."""

from __future__ import annotations

from app import config, distances, text
from app.profiles import build_alphabet_profile

FR = "La forêt près de Genève est très belle: les chênes et les cèdres poussent côte à côte."
EN = "The forest near the town is very beautiful: the oaks and the cedars grow side by side."


def _profiles() -> dict:
    return {
        lang: build_alphabet_profile(src, config.LANG_ALPHABETS[lang])
        for lang, src in (("fr", FR * 30), ("en", EN * 30))
    }


def test_diacritic_share_separates_languages():
    fr = text.diacritic_share(text.letter_counts(FR))
    en = text.diacritic_share(text.letter_counts(EN))
    assert fr > 0.03          # французский: é, è, ô, ç, à
    assert en == 0.0          # английский: диакритики нет


def test_alphabet_distance_prefers_native_language():
    profiles = _profiles()
    for sample, lang in ((FR, "fr"), (EN, "en")):
        counts = text.letter_counts(sample)
        ranked = sorted(
            ((l, distances.alphabet_distance(counts, p)) for l, p in profiles.items()),
            key=lambda item: item[1],
        )
        assert ranked[0][0] == lang


def test_alphabet_distance_penalises_foreign_letters():
    profiles = _profiles()
    counts = text.letter_counts(FR)
    # Текст с «é» ближе к французскому, даже если убрать остальную диакритику.
    assert distances.alphabet_distance(counts, profiles["fr"]) < distances.alphabet_distance(
        counts, profiles["en"]
    )


def test_diacritic_only_mode_is_blind_without_diacritics():
    """Классическая формулировка (только диакритика) слепа к тексту без акцентов."""
    profiles = _profiles()
    stripped = "LA FORET PRES DE GENEVE EST TRES BELLE LES CHENES ET LES CEDRES"
    counts = text.letter_counts(stripped)
    ranked = sorted(
        (l, distances.diacritic_distance(counts, p)) for l, p in profiles.items()
    )
    assert ranked[0][0] == "en"     # акцентов нет -> сигнал указывает на английский


def test_kravivin_presence_criterion_leaves_english_undecided():
    """|A(T) ∩ A_i| по уникальным знакам: у английского таких знаков нет."""
    assert distances.unique_char_count(FR, "fr") > 0
    assert distances.unique_char_count(EN, "fr") == 0
    assert distances.unique_char_count(EN, "en") == 0
    assert distances.unique_char_count(FR, "en") == 0
