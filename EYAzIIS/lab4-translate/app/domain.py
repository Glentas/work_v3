"""Модели данных системы: разбор текста, словарь, результаты перевода.

Модели pydantic используются и как внутренние структуры, и как формат
сохранения сессий перевода в базе (``result_json``), и как ответы JSON API.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Разбор текста (функциональность лр. №3 весеннего семестра)
# ---------------------------------------------------------------------------
class TokenData(BaseModel):
    """Токен предложения с полной грамматической информацией."""

    id: int                      # порядковый номер токена в предложении (0-базовый)
    word: str                    # исходная словоформа
    lemma: str                   # лемма (нижний регистр)
    pos: str                     # универсальная часть речи (NOUN, VERB, ...)
    pos_ru: str = ""             # расшифровка части речи по-русски (лр. №1)
    tag: str                     # тег части речи Penn Treebank (NN, VBZ, ...)
    tag_ru: str = ""             # расшифровка тега по-русски (лр. №3)
    dep: str                     # синтаксическая роль (nsubj, dobj, ...)
    dep_ru: str = ""             # расшифровка роли по-русски (лр. №3)
    head_id: int = -1            # индекс родителя в предложении; -1 = ROOT
    feats: dict[str, str] = Field(default_factory=dict)  # морфопризнаки spaCy
    kind: str = "word"           # word | digit | punct

    @property
    def is_word(self) -> bool:
        return self.kind == "word"


class SentenceData(BaseModel):
    """Предложение: токены разбора и его перевод."""

    id: int
    text: str
    tokens: list[TokenData] = Field(default_factory=list)
    translation: str = ""

    @property
    def word_tokens(self) -> list[TokenData]:
        return [t for t in self.tokens if t.kind == "word"]


class TextData(BaseModel):
    """Разбор всего входного текста."""

    meta: dict = Field(default_factory=dict)
    sentences: list[SentenceData] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Словарь
# ---------------------------------------------------------------------------
class DictEntry(BaseModel):
    """Запись двуязычного словаря (таблица entries базы данных).

    ``gram`` — грамматическая информация для синтеза русских словоформ:
    род и одушевлённость существительных, вид и парный совершенный глагол,
    управление предлогов, явные формы-исключения и т. п.
    """

    id: int | None = None
    source: str                  # английская лемма или оборот (леммы через пробел)
    pos: str = ""                # универсальная часть речи или PHRASE
    target: str = ""             # русский эквивалент (им. п. / инфинитив / м. р.)
    gram: dict = Field(default_factory=dict)
    domain: str = "general"      # general | med | art
    verified: int = 1            # 0 — добавлено утилитой пополнения, ждёт проверки
    note: str = ""
    created_at: str = ""
    updated_at: str = ""

    @property
    def is_phrase(self) -> bool:
        return " " in self.source.strip()


# ---------------------------------------------------------------------------
# Результаты перевода
# ---------------------------------------------------------------------------
class FreqRow(BaseModel):
    """Строка вкладки 1: слово, частота, грамматика и перевод (лр. №1)."""

    lemma: str
    forms: list[str] = Field(default_factory=list)   # встреченные словоформы
    freq: int = 0                                    # частота встречаемости
    pos: str = ""
    pos_ru: str = ""
    tag: str = ""
    tag_ru: str = ""
    dep: str = ""
    dep_ru: str = ""
    translation: str = ""
    in_dict: bool = False


class Stats(BaseModel):
    """Сводная статистика перевода (требование ТЗ: количество слов и т. д.)."""

    total_words: int = 0         # слов во входном тексте (без пунктуации)
    translated_words: int = 0    # переведённых слов (найдены в словаре)
    digits: int = 0              # чисел (переносятся в перевод как есть)
    articles: int = 0            # артиклей (не имеют русского соответствия)
    unknown_total: int = 0       # вхождений неизвестных слов
    unknown: list[str] = Field(default_factory=list)  # неизвестные леммы (уникальные)
    coverage: float = 0.0        # доля переведённых слов, 0..1
    sentences: int = 0
    duration_ms: float = 0.0
    dict_size: int = 0           # записей в словаре на момент перевода


class TranslationResult(BaseModel):
    """Полный результат перевода одной сессии — сохраняется в базе целиком."""

    name: str = ""
    created_at: str = ""
    mode: str = "transfer"
    domain: str = "general"
    source_text: str = ""
    translated_text: str = ""
    stats: Stats = Field(default_factory=Stats)
    sentences: list[SentenceData] = Field(default_factory=list)
    freq: list[FreqRow] = Field(default_factory=list)


class SessionInfo(BaseModel):
    """Краткая информация о сохранённой сессии для страницы истории."""

    id: int
    name: str
    mode: str
    domain: str
    created_at: str
    stats: Stats = Field(default_factory=Stats)
