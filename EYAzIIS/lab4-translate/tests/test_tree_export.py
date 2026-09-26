"""Тесты дерева синтаксического разбора (вкладка 2) и TXT-экспорта."""

from __future__ import annotations

import pytest

from app import analysis, exporter, tree, translator
from app.domain import TokenData


@pytest.fixture(autouse=True)
def _require_spacy(spacy_required):
    yield


def _sentence(text: str):
    text_data, _ = analysis.parse_text(text)
    return text_data.sentences[0]


def test_tree_text_contains_all_words_and_root():
    sent = _sentence("The doctor examined the patient carefully.")
    rendered = tree.tree_text(sent.tokens)
    words = [t.word for t in sent.tokens if t.kind != "punct"]
    for word in words:
        assert word in rendered
    assert "ROOT:" in rendered
    # расшифровки тега и роли (функциональность лр. №3)
    assert "Глагол, прошедшее время" in rendered
    assert "Именное подлежащее" in rendered


def test_tree_text_branch_characters():
    sent = _sentence("The doctor examined the patient.")
    rendered = tree.tree_text(sent.tokens)
    assert "├─" in rendered or "└─" in rendered


def test_token_rows_complete_and_linked():
    sent = _sentence("The painting was exhibited at the gallery.")
    rows = tree.token_rows(sent.tokens)
    words = [t for t in sent.tokens if t.kind != "punct"]
    assert len(rows) == len(words)
    parents = {r["parent"] for r in rows}
    assert "—" in parents  # корень
    for row in rows:
        assert row["tag_ru"] and row["dep_ru"] and row["pos_ru"]


def test_tree_svg_structure():
    sent = _sentence("The doctor examined the patient.")
    svg = tree.tree_svg(sent.tokens)
    assert svg.startswith("<svg")
    assert svg.count("<rect") == len([t for t in sent.tokens if t.kind != "punct"])
    for word in ("doctor", "examined", "patient"):
        assert word in svg
    # корень подсвечен
    assert "#2563eb" in svg


def test_tree_on_punctuation_only():
    sent = _sentence("...")
    assert tree.tree_svg(sent.tokens) == "<svg></svg>"
    assert tree.tree_text(sent.tokens) == ""
    assert tree.token_rows(sent.tokens) == []


def test_tree_roots_single_for_simple_sentence():
    sent = _sentence("Smoking causes cancer.")
    found = tree.roots(tree.word_tokens(sent.tokens))
    assert len(found) == 1
    assert found[0].lemma == "cause"


# ---------------------------------------------------------------------------
# Экспорт TXT (требование ТЗ: сохранение результатов в файл Unicode)
# ---------------------------------------------------------------------------
def test_export_txt_sections():
    text = ("The doctor examined the patient. Many results of the clinical "
            "trial were published. The zqqq device works.")
    result = translator.translate_text(text, name="export unit", mode="transfer")
    report = exporter.build_txt(result)

    assert "АВТОМАТИЧЕСКИЙ МАШИННЫЙ ПЕРЕВОД ТЕКСТОВ" in report
    assert "Вариант 7" in report
    assert "ИСХОДНЫЙ ТЕКСТ" in report
    assert "ПЕРЕВОД (РУССКИЙ)" in report
    assert "СТАТИСТИКА ПЕРЕВОДА" in report
    assert "Количество слов во входном тексте:" in report
    assert "Количество переведённых слов:" in report
    assert "СПИСОК СЛОВ ПО ЧАСТОТЕ ВСТРЕЧАЕМОСТИ (вкладка 1)" in report
    assert "ДЕРЕВЬЯ СИНТАКСИЧЕСКОГО РАЗБОРА (вкладка 2)" in report
    # частотный список: лемма, перевод и расшифровка тега
    assert "doctor" in report and "врач" in report
    assert "Существительное" in report
    # неизвестные слова
    assert "zqqq" in report
    # перевод присутствует
    assert "Врач осмотрел пациента" in report


def test_export_txt_frequency_sorted():
    text = "The patient and the doctor examined the patient again."
    result = translator.translate_text(text, name="freq sort", mode="transfer")
    report = exporter.build_txt(result)
    freqs = [row.freq for row in result.freq]
    assert freqs == sorted(freqs, reverse=True)
    assert result.freq[0].lemma in ("the", "patient")


def test_txt_filename_ascii_only():
    result = translator.translate_text("The doctor examined the patient.",
                                       name="Статья про гипертонию №5")
    name = exporter.txt_filename(result)
    name.isascii()
    assert name.startswith("perevod_") and name.endswith(".txt")
