"""Тесты морфологического синтеза русских словоформ."""

from __future__ import annotations

from app import morphology as m


def test_noun_masculine_hard():
    assert m.decline_noun("стол", "m", "gen") == "стола"
    assert m.decline_noun("стол", "m", "dat") == "столу"
    assert m.decline_noun("стол", "m", "inst") == "столом"
    assert m.decline_noun("стол", "m", "prep") == "столе"


def test_noun_animacy():
    assert m.decline_noun("пациент", "m", "acc", anim=True) == "пациента"
    assert m.decline_noun("стол", "m", "acc", anim=False) == "стол"
    assert m.decline_noun("врач", "m", "acc", "plur", anim=True) == "врачей"


def test_noun_feminine():
    assert m.decline_noun("книга", "f", "gen") == "книги"
    assert m.decline_noun("книга", "f", "acc") == "книгу"
    assert m.decline_noun("рука", "f", "gen") == "руки"      # после к — и
    assert m.decline_noun("болезнь", "f", "inst") == "болезнью"
    assert m.decline_noun("терапия", "f", "prep") == "терапии"


def test_noun_neuter():
    assert m.decline_noun("окно", "n", "inst") == "окном"
    assert m.decline_noun("море", "n", "gen") == "моря"
    assert m.decline_noun("здание", "n", "prep") == "здании"
    assert m.decline_noun("лёгкое", "n", "prep") == "лёгком"


def test_noun_plural():
    assert m.decline_noun("стол", "m", "nom", "plur") == "столы"
    assert m.decline_noun("врач", "m", "nom", "plur") == "врачи"
    assert m.decline_noun("книга", "f", "nom", "plur") == "книги"
    assert m.decline_noun("болезнь", "f", "gen", "plur") == "болезней"
    assert m.decline_noun("посетитель", "m", "gen", "plur") == "посетителей"
    assert m.decline_noun("рисунок", "m", "nom", "plur") == "рисунки"
    assert m.decline_noun("рисунок", "m", "gen", "plur") == "рисунков"
    assert m.decline_noun("испытание", "n", "gen", "plur") == "испытаний"
    assert m.decline_noun("поле", "n", "gen", "plur") == "полей"
    assert m.decline_noun("стол", "m", "dat", "plur") == "столам"
    assert m.decline_noun("неделя", "f", "inst", "plur") == "неделями"


def test_explicit_forms_override_rules():
    gram = {"gender": "m", "anim": True,
            "forms": {"nompl": "люди", "genpl": "людей", "inst": "врачом"}}
    assert m.decline_noun("человек", "m", "nom", "plur", gram=gram) == "люди"
    assert m.decline_noun("человек", "m", "gen", "plur", gram=gram) == "людей"
    assert m.decline_noun("врач", "m", "inst", gram=gram) == "врачом"


def test_adjective_agreement():
    assert m.agree_adj("красивый", "f") == "красивая"
    assert m.agree_adj("красивый", "n", case="gen") == "красивого"
    assert m.agree_adj("синий", "f") == "синяя"
    assert m.agree_adj("синий", "m", case="gen") == "синего"
    assert m.agree_adj("широкий", "f", case="inst") == "широкой"
    assert m.agree_adj("широкий", "m", case="inst") == "широким"
    assert m.agree_adj("клинический", "n") == "клиническое"
    assert m.agree_adj("клинический", "m", "plur", "gen") == "клинических"
    assert m.agree_adj("висящий", "f") == "висящая"
    assert m.agree_adj("русский", "f") == "русская"


def test_verb_conjugation_regular():
    assert m.conjugate("читать", 1, "sing") == "читаю"
    assert m.conjugate("читать", 3, "sing") == "читает"
    assert m.conjugate("читать", 3, "plur") == "читают"
    assert m.conjugate("говорить", 1, "sing") == "говорю"
    assert m.conjugate("рисовать", 1, "sing") == "рисую"
    assert m.conjugate("исследовать", 3, "sing") == "исследует"


def test_verb_conjugation_alternation():
    assert m.conjugate("находить", 1, "sing") == "нахожу"
    assert m.conjugate("платить", 1, "sing") == "плачу"
    assert m.conjugate("купить", 1, "sing") == "куплю"
    assert m.conjugate("пустить", 1, "sing") == "пущу"
    # орфография: после ж/ч/ш/щ — «у»
    assert m.conjugate("назначить", 1, "sing") == "назначу"


def test_verb_reflexive():
    assert m.conjugate("развиваться", 3, "sing") == "развивается"
    assert m.conjugate("находиться", 1, "sing") == "нахожусь"
    assert m.verb_past("начаться", "f") == "началась"
    assert m.verb_past("развиваться", "m", "plur") == "развивались"


def test_verb_past():
    assert m.verb_past("читать", "m") == "читал"
    assert m.verb_past("читать", "f") == "читала"
    assert m.verb_past("читать", "n") == "читало"
    assert m.verb_past("читать", "m", "plur") == "читали"
    assert m.verb_past("идти", "m") == "шёл"
    assert m.verb_past("идти", "f") == "шла"
    assert m.verb_past("помочь", "f") == "помогла"
    assert m.verb_past("мочь", "m", "plur") == "могли"
    assert m.verb_past("сесть", "m") == "сел"


def test_participles_and_gerund():
    assert m.short_participle("обследовать", "m") == "обследован"
    assert m.short_participle("обследовать", "f") == "обследована"
    assert m.short_participle("обследовать", "m", "plur") == "обследованы"
    assert m.short_participle("написать", "m") == "написан"
    assert m.short_participle("открыть", "m") == "открыт"
    assert m.short_participle("выставить", "m") == "выставлен"
    assert m.full_participle("написать") == "написанный"
    assert m.full_participle("открыть") == "открытый"
    assert m.gerund("читать") == "читая"
    assert m.gerund("говорить") == "говоря"
    assert m.gerund("развиваться") == "развиваясь"


def test_pronouns_and_possessives():
    assert m.pronoun_form("я", "acc") == "меня"
    assert m.pronoun_form("он", "gen", after_prep=True) == "него"
    assert m.pronoun_form("они", "inst", after_prep=True) == "ними"
    assert m.possessive_form("мой", "f", "sing", "nom") == "моя"
    assert m.possessive_form("наш", "f", "sing", "acc") == "нашу"
    assert m.possessive_form("его", "f", "sing", "nom") == "его"


def test_numeral_government():
    assert m.numeral_noun_case(1) == "nom_sing"
    assert m.numeral_noun_case(2) == "gen_sing"
    assert m.numeral_noun_case(5) == "gen_plur"
    assert m.numeral_noun_case(21) == "nom_sing"
    assert m.numeral_noun_case(11) == "gen_plur"
    assert m.numeral_noun_case(102) == "gen_sing"
