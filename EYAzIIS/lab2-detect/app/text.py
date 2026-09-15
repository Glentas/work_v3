"""Шаг 1: предварительная обработка входного текста"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from pathlib import Path

from bs4 import BeautifulSoup

from . import config

#: Токен = последовательность букв и апострофов (Cavnar–Trenkle, §3.1):
#: цифры и пунктуация в построении N-грамм не участвуют.
TOKEN_RE = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)*", re.UNICODE)

#: Кодировки, которые пробуем, если meta charset отсутствует или не читается.
_FALLBACK_ENCODINGS = ("utf-8", "windows-1252", "latin-1")

_META_RE = re.compile(r'charset\s*=\s*["\']?([a-zA-Z0-9_\-]+)')

#: Служебные теги: их текст не является содержимым документа.
#: head убирается целиком, чтобы <title> и метаданные не попадали в профиль.
_SKIP_TAGS = ("script", "style", "nav", "header", "footer", "head")


def read_html(path: Path) -> tuple[str, str]:
    """Читает HTML-файл и возвращает (видимый текст, использованная кодировка)."""
    raw = path.read_bytes()
    encoding = _declared_encoding(raw)

    text = None
    for candidate in ([encoding] if encoding else []) + list(_FALLBACK_ENCODINGS):
        try:
            text = raw.decode(candidate)
            encoding = candidate
            break
        except (UnicodeDecodeError, LookupError):
            continue
    if text is None:                      # совсем экзотическая кодировка
        text = raw.decode("utf-8", errors="replace")
        encoding = "utf-8 (с заменами)"

    return html_to_visible(text), encoding


def _declared_encoding(raw: bytes) -> str | None:
    """Кодировка из <meta charset=...> в начале файла."""
    head = raw[:1024].decode("ascii", errors="ignore")
    match = _META_RE.search(head)
    return match.group(1).lower() if match else None


def html_to_visible(html: str) -> str:
    """Извлекает видимый текст: без разметки, служебных тегов, со схлопнутыми
    пробелами. BeautifulSoup попутно декодирует HTML-сущности (&eacute; -> é)."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(_SKIP_TAGS):
        tag.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True))


# ---------------------------------------------------------------------------
# Разбор текста для методов
# ---------------------------------------------------------------------------
def normalize(text: str) -> str:
    """Приведение к нижнему регистру и нормализации Unicode NFKC."""
    return unicodedata.normalize("NFKC", text).lower()


def tokenize(text: str) -> list[str]:
    """Токены из букв и апострофов в нижнем регистре."""
    return TOKEN_RE.findall(normalize(text))


def char_ngrams(text: str, n_max: int | None = None) -> list[str]:
    """Все N-граммы длин 1..N для каждого токена, дополненного пробелами '_'.

    Токен ``chat`` даёт: _c ch ha at t_ | _ch cha hat at_ | ... — в точности
    по §3.1 статьи Cavnar–Trenkle.
    """
    limit = n_max if n_max is not None else config.NGRAM_MAX_N
    out: list[str] = []
    for token in tokenize(text):
        padded = "_" + token + "_"
        for n in range(1, limit + 1):
            for i in range(len(padded) - n + 1):
                out.append(padded[i:i + n])
    return out


def letter_counts(text: str) -> Counter[str]:
    """Частоты букв (только буквы, нижний регистр) — материал алфавитного метода."""
    return Counter(ch for ch in normalize(text) if ch.isalpha())


def diacritic_share(counts: Counter[str]) -> float:
    """Доля букв с диакритикой (не ASCII) среди всех букв текста."""
    total = sum(counts.values())
    if not total:
        return 0.0
    return sum(v for k, v in counts.items() if not k.isascii()) / total
