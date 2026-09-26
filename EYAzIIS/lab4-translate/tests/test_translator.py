"""Тесты оркестратора перевода: статистика, частотный список, сессии, крайние случаи."""

from __future__ import annotations

import pytest

from app import config, translator


@pytest.fixture(autouse=True)
def _require_spacy(spacy_required):
    yield


def test_stats_match_manual_count():
    # The(арт) doctor examined the(арт) patient -> 5 слов, 2 артикля,
    # 3 значимых слова переведены.
    result = translator.translate_text("The doctor examined the patient.", name="count")
    stats = result.stats
    assert stats.total_words == 5
    assert stats.articles == 2
    assert stats.translated_words == 3   # doctor, examined, patient
    assert stats.digits == 0
    assert stats.sentences == 1
    # покрытие считается по значимым словам (без артиклей)
    assert stats.coverage == pytest.approx(2 / 2)


def test_stats_digits_and_unknown():
    text = "In 2004 the zqqqmark device was examined."
    result = translator.translate_text(text, name="digits")
    assert result.stats.digits == 1
    assert "zqqqmark" in result.stats.unknown
    assert result.stats.unknown_total >= 1
    assert "2004" in result.translated_text  # числа переносятся как есть


def test_unknown_word_bracketed_in_translation():
    result = translator.translate_text("The doctor used a zqqqmark.", name="unk")
    assert "[zqqqmark]" in result.translated_text


def test_freq_rows_grouped_and_ordered():
    text = ("The patients received the drug. The patients reported the "
            "symptoms. Doctors examined the patients.")
    result = translator.translate_text(text, name="freq")
    freqs = [row.freq for row in result.freq]
    assert freqs == sorted(freqs, reverse=True)
    lemmas = [row.lemma for row in result.freq]
    assert len(lemmas) == len(set(lemmas))       # группировка по леммам
    patients_row = next(r for r in result.freq if r.lemma == "patient")
    assert patients_row.freq == 3
    assert "patients" in patients_row.forms and "patient" not in patients_row.forms
    assert patients_row.translation == "пациент"
    assert patients_row.in_dict is True
    assert patients_row.tag and patients_row.tag_ru and patients_row.dep_ru


def test_freq_row_grammar_descriptions():
    result = translator.translate_text("The doctor examined the patient.", name="desc")
    row = next(r for r in result.freq if r.lemma == "examine")
    assert row.tag == "VBD"
    assert row.tag_ru == "Глагол, прошедшее время"
    assert row.pos == "VERB" and row.pos_ru == "Глагол"
    assert row.dep == "ROOT"


def test_sentence_translations_aligned():
    text = "The doctor examined the patient. The patient received the therapy."
    result = translator.translate_text(text, name="two sents")
    assert len(result.sentences) == 2
    assert all(s.translation for s in result.sentences)
    assert "Врач осмотрел пациента" in result.sentences[0].translation


def test_modes_differ():
    text = "The doctor examined the patient."
    a = translator.translate_text(text, name="m1", mode="transfer")
    b = translator.translate_text(text, name="m2", mode="literal")
    assert a.mode == "transfer" and b.mode == "literal"
    assert a.translated_text != b.translated_text
    assert "осмотрел" in a.translated_text
    assert "осматривать" in b.translated_text   # пословный: словарная форма


def test_invalid_mode_defaults_to_transfer():
    result = translator.translate_text("The doctor examined the patient.",
                                       name="bad mode", mode="qqq")
    assert result.mode == "transfer"


def test_empty_text_raises():
    with pytest.raises(ValueError):
        translator.translate_text("   ", name="empty")


def test_crlf_and_unicode_input():
    text = "The doctor examined the patient.\r\nПациент — это человек.\r\n"
    result = translator.translate_text(text, name="crlf")
    assert result.stats.sentences >= 1
    assert "Врач осмотрел пациента" in result.translated_text


def test_text_without_final_punctuation():
    result = translator.translate_text("The doctor examined the patient", name="no dot")
    assert "Врач осмотрел пациента" in result.translated_text


def test_domain_detection_medical_vs_art():
    med = translator.translate_text(
        "The patient received therapy for the disease at the hospital.", name="med")
    art = translator.translate_text(
        "The painting was exhibited at the gallery; the artist and the critic admired the canvas.",
        name="art")
    assert med.domain == "med"
    assert art.domain == "art"


def test_session_lifecycle():
    result = translator.translate_text("The doctor examined the patient.",
                                       name="жизненный цикл")
    sid = translator.save_session(result)
    assert sid > 0

    loaded = translator.load_session(sid)
    assert loaded is not None
    assert loaded.name == "жизненный цикл"
    assert loaded.translated_text == result.translated_text
    assert loaded.stats.total_words == result.stats.total_words
    assert len(loaded.freq) == len(result.freq)
    assert len(loaded.sentences) == len(result.sentences)

    assert translator.rename_session(sid, "новое имя") is True
    assert translator.load_session(sid).name == "новое имя"

    ids_before = {s.id for s in translator.list_sessions()}
    assert sid in ids_before
    assert translator.delete_session(sid) is True
    assert translator.load_session(sid) is None
    assert translator.delete_session(sid) is False


def test_unknown_words_of_result():
    result = translator.translate_text("The zqqalpha and zqqbeta devices work.", name="unk2")
    unknown = translator.unknown_words_of(result)
    words = {w for w, _ in unknown}
    assert "zqqalpha" in words and "zqqbeta" in words
    for _word, pos in unknown:
        assert pos in ("NOUN", "PROPN", "")


def test_samples_available_and_safe():
    samples = translator.samples()
    names = {s["name"] for s in samples}
    assert {"med_01", "med_02", "art_01", "art_02"} <= names
    for sample in samples:
        assert sample["chars"] > 500
    text = translator.sample_text("med_01")
    assert text and "Clinical trial" in text
    assert translator.sample_text("nonexistent") is None
    # защита от выхода за пределы каталога samples/
    assert translator.sample_text("../seed_dictionary") is None


def test_freq_total_equals_word_count():
    """Инвариант: сумма частот вкладки 1 = количеству слов во входном тексте."""
    text = (config.SAMPLES_PATH / "med_01.txt").read_text(encoding="utf-8")
    result = translator.translate_text(text, name="инвариант")
    assert sum(row.freq for row in result.freq) == result.stats.total_words
    assert result.stats.translated_words <= result.stats.total_words
