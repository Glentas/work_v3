"""Метрики расстояния между ПОД и ПОЯ.

Все метрики возвращают число: категория с наименьшим
значением принимается за язык документа.
"""

from __future__ import annotations

from collections import Counter

from . import config, text
from .profiles import AlphabetProfile, NgramProfile


def out_of_place(doc: NgramProfile, lang: NgramProfile) -> int:
    """Мера несовпадения позиций N-грамм.

    Для каждой N-граммы профиля документа берётся разница её позиций в профилях
    документа и языка; суммы этих разниц и есть расстояние. N-грамме, которой
    нет в профиле языка, назначается максимальная величина оценки — в эталонной
    реализации (R-пакет textcat, метод CT) это длина профиля категории.
    Она заведомо больше любой разности позиций внутри профиля (len - 1).
    """
    penalty = len(lang)
    return sum(
        abs(lang.ranks[g] - i) if g in lang.ranks else penalty
        for i, g in enumerate(doc.ngrams)
    )


def alphabet_distance(counts: Counter[str], lang: AlphabetProfile) -> float:
    """Расстояние алфавитного метода: полная вариация частот букв + штраф за чужие буквы.

    Первое слагаемое сравнивает наблюдаемое распределение букв документа
    (включая диакритические знаки) с распределением языка: это знание только
    об алфавите и характерных частотах его символов. Второе слагаемое — доля
    букв текста, которых в алфавите языка нет вовсе (например, «é» для английского).
    """
    total = sum(counts.values())
    if not total:
        return 1.0
    observed = {ch: n / total for ch, n in counts.items()}
    variation = sum(
        abs(observed.get(ch, 0.0) - freq) for ch, freq in lang.letter_freq.items()
    ) + sum(observed.get(ch, 0.0) for ch in observed if ch not in lang.letter_freq)
    alien = sum(n for ch, n in counts.items() if ch not in lang.alphabet) / total
    return variation + alien


def diacritic_distance(counts: Counter[str], lang: AlphabetProfile) -> float:
    """Дополнительный режим: расстояние только по доле диакритических знаков"""
    total = sum(counts.values())
    if not total:
        return 1.0
    observed = sum(v for k, v in counts.items() if not k.isascii()) / total
    alien = sum(v for k, v in counts.items() if k not in lang.alphabet) / total
    return abs(observed - lang.diacritic_share) + alien


def unique_char_count(source: str, lang: str) -> int:
    """Дополнительный режим: 
    Считает знаки текста, уникальные для алфавита языка. У английского таких
    знаков нет, поэтому для пары fr/en критерий «в лоб» оставляет английские
    тексты без победителя — это показано в отчёте и тестах.
    """
    unique = config.LANG_UNIQUE_CHARS[lang]
    return sum(1 for ch in text.normalize(source) if ch in unique)
