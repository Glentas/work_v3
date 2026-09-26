"""Тесты грамматических таблиц (функциональность лр. №1 и №3 весеннего семестра)."""

from __future__ import annotations

from app import grammar


def test_tag_map_penn_known():
    assert grammar.tag_rus("NN") == "Существительное, ед. ч. или неисчислимое"
    assert grammar.tag_rus("VBZ") == "Глагол, наст. вр., 3-е лицо ед.ч."
    assert grammar.tag_rus("JJR") == "Прилагательное, сравнительная степень"
    assert grammar.tag_rus("PRP$") == "Притяжательное местоимение"


def test_tag_map_unknown_fallback():
    assert grammar.tag_rus("QQQ").startswith("Неизвестно")
    assert "QQQ" in grammar.tag_rus("QQQ")


def test_dep_map_known():
    assert grammar.dep_rus("nsubj") == "Именное подлежащее (nominal subject)"
    assert grammar.dep_rus("auxpass") == "Вспомогательный глагол пассива (auxiliary passive)"
    # регистр не важен
    assert grammar.dep_rus("ROOT") == grammar.dep_rus("root")


def test_dep_map_unknown_fallback():
    assert grammar.dep_rus("zzz").startswith("Неизвестно")


def test_pos_map_known():
    assert grammar.pos_rus("NOUN") == "Существительное"
    assert grammar.pos_rus("VERB") == "Глагол"
    assert grammar.pos_rus("phrase") == "Оборот (несколько слов)"


def test_maps_are_complete_for_common_tags():
    # Все теги, которые выдаёт en_core_web_sm на наших текстах, расшифрованы.
    for tag in ("NN", "NNS", "NNP", "VB", "VBD", "VBG", "VBN", "VBP", "VBZ",
                "JJ", "RB", "DT", "IN", "PRP", "MD", "CC", "CD", ".", ","):
        assert tag in grammar.TAG_MAP
    for dep in ("nsubj", "dobj", "obj", "amod", "det", "prep", "pobj",
                "aux", "auxpass", "ROOT", "punct", "conj", "cc"):
        assert dep.lower() in grammar.DEP_MAP
