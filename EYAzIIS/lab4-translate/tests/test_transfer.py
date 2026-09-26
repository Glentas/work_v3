"""Тесты трансфера и сквозного перевода (нужна модель spaCy — иначе skip)."""

from __future__ import annotations

import pytest

from app import analysis, dictionary, transfer, translator


def _translate(text: str, mode: str = "transfer", domain: str | None = None):
    dom = domain or dictionary.detect_domain(text)
    text_data, _ = analysis.parse_text(text)
    results = [transfer.translate_sentence(s, dom, mode) for s in text_data.sentences]
    return [r[0] for r in results], text_data


@pytest.fixture(autouse=True)
def _require_spacy(spacy_required):
    yield


def test_simple_svo_past():
    out, _ = _translate("The doctor examined the patient.")
    assert out[0] == "Врач осмотрел пациента."


def test_passive_past():
    out, _ = _translate("The painting was exhibited at the gallery.")
    assert "была выставлена" in out[0]
    assert "в галерее" in out[0]


def test_question_with_li():
    out, _ = _translate("Does the drug cause side effects?")
    assert out[0].startswith("Вызывает ли")
    assert out[0].endswith("?")


def test_negation():
    out, _ = _translate("The results were not observed.")
    assert "не были" in out[0]
    assert out[0].count("не ") == 1


def test_possessive_reordering():
    out, _translate_data = _translate("The doctor's decision was examined.")
    assert out[0].startswith("Решение врача")


def test_of_construction_genitive():
    out, _ = _translate("The results of the study were published.")
    assert "Результаты исследования" in out[0]


def test_compound_noun_swap():
    out, _ = _translate("The blood test revealed the disease.", domain="med")
    assert "анализ крови" in out[0].lower() or "Анализ крови" in out[0]


def test_modal_and_infinitive():
    out, _ = _translate("Patients should avoid stress.", domain="med")
    assert "должны избегать" in out[0]


def test_future_passive():
    out, _ = _translate("The control group will be examined by physicians.", domain="med")
    assert "будет" in out[0]
    assert "врачами" in out[0]


def test_there_is():
    out, _ = _translate("There is a tumor in the lung.", domain="med")
    assert out[0].startswith("Имеется") or "имеется" in out[0]
    assert "в лёгком" in out[0]


def test_numeral_government():
    out, _ = _translate("Two patients received the drug.", domain="med")
    assert "Два пациента" in out[0] or "Два пациента получили" in out[0]


def test_quantifier_genitive_plural():
    out, _ = _translate("Many patients received the therapy.", domain="med")
    assert "много пациентов" in out[0].lower()


def test_unknown_word_marked():
    out, _ = _translate("The zqqqlg device works.")
    assert "[zqqqlg]" in out[0]


def test_literal_mode_is_word_by_word():
    out, _ = _translate("The doctor examined the patient.", mode="literal")
    # Прямой перевод: словарные формы без спряжения и падежей.
    assert "врач" in out[0].lower()
    assert "осматривать" in out[0].lower() or "осмотреть" in out[0].lower()


def test_phrase_translation():
    out, _ = _translate("Clinical trials provide evidence.", domain="med")
    assert "клинические исследования" in out[0].lower()


def test_full_pipeline_stats():
    text = ("The doctor examined the patient. The painting was exhibited "
            "at the gallery in Paris.")
    result = translator.translate_text(text, name="тест", mode="transfer")
    assert result.stats.sentences == 2
    assert result.stats.total_words > 10
    assert result.stats.translated_words > 0
    assert 0.0 < result.stats.coverage <= 1.0
    assert result.translated_text
    # Вкладка 1: частотный список упорядочен по убыванию частоты.
    freqs = [row.freq for row in result.freq]
    assert freqs == sorted(freqs, reverse=True)
    assert all(row.tag_ru and row.dep_ru for row in result.freq if row.tag)
    # Вкладка 2: у каждого предложения есть токены с родителями для дерева.
    assert any(t.head_id == -1 for t in result.sentences[0].tokens)


def test_domain_detection_affects_translation():
    # В медицинском тексте cell -> «клетка», в общем — «ячейка».
    med, _ = _translate("The cell was studied by the physician.", domain="med")
    gen, _ = _translate("The cell was studied.", domain="general")
    assert "клетка" in med[0].lower()
    assert "ячейка" in gen[0].lower()
