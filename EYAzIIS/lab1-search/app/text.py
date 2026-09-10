"""Лингвистическая обработка текста: токенизация, стемминг, стоп-слова,
разбор запроса и построение сниппета.

Система работает с английскими документами (вариант 7), поэтому
используются английский список стоп-слов и стеммер Портера.

Список стоп-слов поставляется вместе с проектом (``stopwords_english.txt``),
поэтому скачивание корпусов NLTK при запуске не требуется и система
работает в локальной сети без доступа в интернет.
"""

from __future__ import annotations

import html
import re
from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from nltk.stem import PorterStemmer

_STOPWORDS_FILE = Path(__file__).parent / "stopwords_english.txt"

#: Минимальный набор стоп-слов на случай повреждения файла.
_FALLBACK_STOPWORDS = frozenset(
    "a an the and or but if then else of to in on at by for with without "
    "is are was were be been being it its this that these those i you he "
    "she we they them his her their our your".split()
)

_stemmer = PorterStemmer()
_TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")

#: Минус трактуется как исключение только в начале запроса или после пробела,
#: чтобы дефис внутри слова (well-known) не превращал вторую часть в запрет.
_EXCLUDE_RE = re.compile(r"(?:^|(?<=\s))-([a-zA-Z0-9]+)")


@lru_cache(maxsize=1)
def stopwords() -> frozenset[str]:
    """Английские стоп-слова. Читаются из файла проекта — работа без сети."""
    try:
        words = _STOPWORDS_FILE.read_text(encoding="utf-8").split()
    except OSError:
        words = []

    if not words:
        try:  # запасной вариант: корпус NLTK, если он уже установлен локально
            from nltk.corpus import stopwords as _nltk_stopwords

            words = _nltk_stopwords.words("english")
        except Exception:
            words = []

    return frozenset(words) or _FALLBACK_STOPWORDS


@lru_cache(maxsize=65536)
def stem(token: str) -> str:
    """Основа слова (стемминг Портера). Результат кэшируется."""
    return _stemmer.stem(token)


def tokenize(text: str) -> list[str]:
    """Разбивает текст на буквенно-цифровые токены в нижнем регистре."""
    return _TOKEN_RE.findall(text.lower())


def analyze(text: str) -> list[tuple[str, str]]:
    """Возвращает пары (исходное слово, основа). Стоп-слова отбрасываются.

    Именно этот список формирует поисковый образ документа (ПОД).
    """
    stop = stopwords()
    return [
        (token, stem(token))
        for token in tokenize(text)
        if token not in stop
    ]


# ---------------------------------------------------------------------------
# Разбор запроса
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class QueryTerms:
    """Поисковый образ запроса (ПОЗ).

    Ключи — основы слов (стеммы), значения — исходные написания, которые
    встретились в запросе. Несколько написаний могут давать одну основу
    (``run``, ``running`` → ``run``).
    """

    include: dict[str, list[str]] = field(default_factory=dict)
    exclude: dict[str, list[str]] = field(default_factory=dict)

    @property
    def include_stems(self) -> list[str]:
        return list(self.include)

    @property
    def exclude_stems(self) -> list[str]:
        return list(self.exclude)

    @property
    def is_empty(self) -> bool:
        return not self.include


def parse_query(query: str) -> QueryTerms:
    """Разбирает запрос пользователя.

    Слова, перечисленные через пробел, образуют множество обязательных
    либо желательных терминов (переключается флагом «все слова вместе»).
    Знак минус перед словом запрещает его: ``holmes -watson``.
    """
    excluded: list[str] = []

    def _take_excluded(match: re.Match[str]) -> str:
        excluded.append(match.group(1))
        return " "

    included_text = _EXCLUDE_RE.sub(_take_excluded, query)

    def _group(text: str) -> dict[str, list[str]]:
        grouped: dict[str, list[str]] = defaultdict(list)
        for original, term_stem in analyze(text):
            if original not in grouped[term_stem]:   # одно написание — одна запись
                grouped[term_stem].append(original)
        return dict(grouped)

    return QueryTerms(
        include=_group(included_text),
        exclude=_group(" ".join(excluded)),
    )


# ---------------------------------------------------------------------------
# Сниппет
# ---------------------------------------------------------------------------
def make_snippet(text: str, match_stems: set[str], max_length: int = 300) -> str:
    """Фрагмент документа с подсветкой слов запроса.

    В отличие от наивного «первые N символов» выбирается окно той же длины,
    содержащее наибольшее число совпадений, поэтому пользователь всегда
    видит, чем именно документ оказался полезен. Если совпадений нет,
    показывается начало документа.

    Возвращает HTML: текст экранирован, совпадения обёрнуты в ``<mark>``.
    """
    if not text:
        return ""

    stop = stopwords()
    tokens: list[tuple[int, int, str, bool]] = []
    for match in _TOKEN_RE.finditer(text):
        token = match.group(0)
        lowered = token.lower()
        is_match = lowered not in stop and stem(lowered) in match_stems
        tokens.append((match.start(), match.end(), token, is_match))

    if not tokens:
        return ""

    # Скользящее окно: максимум совпадений при ограничении на длину фрагмента.
    best_start = best_end = 0
    best_score = -1
    score = 0
    right = 0
    for left in range(len(tokens)):
        if right < left:
            right, score = left, 0
        while right < len(tokens) and tokens[right][1] - tokens[left][0] <= max_length:
            score += tokens[right][3]
            right += 1
        if score > best_score:
            best_score, best_start, best_end = score, left, right
        score -= tokens[left][3]

    window = tokens[best_start:best_end]
    if not window:
        return ""

    first, last = window[0], window[-1]
    parts: list[str] = []
    if text[: first[0]].strip():
        parts.append("… ")
    cursor = first[0]
    for start, end, token, is_match in window:
        parts.append(html.escape(text[cursor:start]))
        escaped = html.escape(token)
        parts.append(f"<mark>{escaped}</mark>" if is_match else escaped)
        cursor = end
    if text[last[1] :].strip():
        parts.append(" …")

    return "".join(parts)
