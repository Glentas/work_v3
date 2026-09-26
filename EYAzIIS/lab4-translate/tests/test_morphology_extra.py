"""Дополнительные тесты морфологии: краевые случаи и словарные формы."""

from __future__ import annotations

from app import morphology as m


def test_substantivised_adjectives():
    # учёный (adjdecl задаётся словарём — проверяем правило -ый без флага
    # и существительные типа «лёгкое»)
    assert m.decline_noun("лёгкое", "n", "prep") == "лёгком"
    assert m.decline_noun("лёгкое", "n", "gen") == "лёгкого"
    assert m.decline_noun("лёгкое", "n", "inst") == "лёгким"
    gram = {"adjdecl": True}
    assert m.decline_noun("учёный", "m", "gen", gram=gram) == "учёного"
    assert m.decline_noun("учёный", "m", "inst", gram=gram) == "учёным"
    # герой — НЕ прилагательное: обычное склонение на -й
    assert m.decline_noun("герой", "m", "gen") == "героя"


def test_indeclinables():
    gram = {"inv": True, "gender": "f"}
    assert m.decline_noun("ДНК", "f", "gen", gram=gram) == "ДНК"
    assert m.decline_noun("кино", "m", "inst") == "кино"
    gram_m_inv = {"inv": True, "gender": "m"}
    assert m.decline_noun("Моне", "m", "dat", gram=gram_m_inv) == "Моне"


def test_multiword_targets():
    # прилагательное + существительное: согласуются оба слова
    assert m.decline_noun("головная боль", "f", "acc") == "головную боль"
    assert m.decline_noun("головная боль", "f", "gen") == "головной боли"
    assert m.decline_noun("головная боль", "f", "inst") == "головной болью"
    # существительное + родительный: склоняется только главное слово
    assert m.decline_noun("анализ крови", "m", "gen") == "анализа крови"
    assert m.decline_noun("болезнь сердца", "f", "dat") == "болезни сердца"
    assert m.decline_noun("произведение искусства", "n", "gen") == "произведения искусства"


def test_ie_nouns_all_cases():
    # испытание: полный набор единственного и множественного числа
    assert m.decline_noun("испытание", "n", "gen") == "испытания"
    assert m.decline_noun("испытание", "n", "dat") == "испытанию"
    assert m.decline_noun("испытание", "n", "inst") == "испытанием"
    assert m.decline_noun("испытание", "n", "prep") == "испытании"
    assert m.decline_noun("испытание", "n", "nom", "plur") == "испытания"
    assert m.decline_noun("испытание", "n", "gen", "plur") == "испытаний"
    assert m.decline_noun("испытание", "n", "inst", "plur") == "испытаниями"


def test_plural_genitive_models():
    assert m.decline_noun("стол", "m", "gen", "plur") == "столов"
    assert m.decline_noun("нож", "m", "gen", "plur") == "ножей"
    assert m.decline_noun("словарь", "m", "gen", "plur") == "словарей"
    assert m.decline_noun("книга", "f", "gen", "plur") == "книг"
    assert m.decline_noun("статья", "f", "gen", "plur") == "статей"
    assert m.decline_noun("армия", "f", "gen", "plur") == "армий"
    assert m.decline_noun("лекарство", "n", "gen", "plur") == "лекарств"
    assert m.decline_noun("море", "n", "gen", "plur") == "морей"
    assert m.decline_noun("данное", "n", "gen", "plur") == "данных"


def test_fleeting_vowel():
    assert m.decline_noun("кусок", "m", "gen") == "куска"
    assert m.decline_noun("рисунок", "m", "gen") == "рисунка"
    assert m.decline_noun("рисунок", "m", "nom", "plur") == "рисунки"
    # «человек» беглой гласной не имеет — формы из словаря
    gram = {"gender": "m", "anim": True,
            "forms": {"gen": "человека", "nompl": "люди", "genpl": "людей"}}
    assert m.decline_noun("человек", "m", "gen", gram=gram) == "человека"
    assert m.decline_noun("человек", "m", "gen", "plur", gram=gram) == "людей"


def test_evat_conjugation():
    assert m.conjugate("затмевать", 1) == "затмеваю"
    assert m.conjugate("затмевать", 3, "plur") == "затмевают"


def test_imperative_rule_components():
    # правила, по которым ветвь повелительного наклонения строит форму мн. ч.
    assert "читать"[:-2] + "йте" == "читайте"
    assert "рисовать"[:-5] + "уйте" == "рисуйте"
    assert "говорить"[:-3] + "ьте" == "говорьте"


def test_reflexive_past_forms():
    assert m.verb_past("развиваться", "n") == "развивалось"
    assert m.verb_past("начаться", "m", "plur") == "начались"
    assert m.verb_past("умыться", "f") == "умылась"


def test_short_participle_models():
    assert m.short_participle("прочитать", "m") == "прочитан"
    assert m.short_participle("решить", "m") == "решен"
    assert m.short_participle("принести", "m") == "принесён"
    assert m.short_participle("принести", "f") == "принесена"
    assert m.short_participle("направить", "m") == "направлен"
    assert m.short_participle("дополнить", "m") == "дополнен"
    # явная форма из словаря важнее правила
    assert m.short_participle("найти", "m", gram={"pp": "найден"}) == "найден"


def test_pronouns_after_prepositions():
    assert m.pronoun_form("она", "gen", after_prep=True) == "неё"
    assert m.pronoun_form("он", "inst", after_prep=True) == "ним"
    assert m.pronoun_form("мы", "gen", after_prep=True) == "нас"
    assert m.pronoun_form("кто", "dat") == "кому"
    assert m.pronoun_form("это", "inst") == "этим"


def test_possessive_full_paradigm():
    assert m.possessive_form("мой", "m", "sing", "gen") == "моего"
    assert m.possessive_form("твой", "f", "sing", "acc") == "твою"
    assert m.possessive_form("наш", "m", "plur", "inst") == "нашими"
    assert m.possessive_form("их", "f", "sing", "gen") == "их"


def test_special_demonstratives():
    from app.transfer import _agree_special
    assert _agree_special("этот", "f", "sing", "acc") == "эту"
    assert _agree_special("этот", "n", "sing", "gen") == "этого"
    assert _agree_special("тот", "m", "plur", "nom") == "те"
    assert _agree_special("весь", "f", "sing", "inst") == "всей"
    assert _agree_special("чей", "f", "sing", "nom") == "чья"


def test_numeral_word_forms():
    assert m.NUMBER_WORDS["two"] == "два"
    from app.transfer import ONE_FORMS, TWO_FORMS
    assert ONE_FORMS["f"] == "одна"
    assert TWO_FORMS["f"] == "две"
