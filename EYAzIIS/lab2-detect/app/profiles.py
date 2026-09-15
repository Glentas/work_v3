"""Построение поисковых образов: ПОЯ (языка) и ПОД (документа)"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from . import config, text


@dataclass(frozen=True, slots=True)
class NgramProfile:
    """Упорядоченный профиль N-грамм: список по убыванию частоты + ранги"""

    ngrams: tuple[str, ...]
    ranks: dict[str, int]

    def __len__(self) -> int:
        return len(self.ngrams)


@dataclass(frozen=True, slots=True)
class AlphabetProfile:
    """ПОЯ алфавитного метода: алфавит языка и частотный профиль его букв"""

    alphabet: frozenset[str]
    letter_freq: dict[str, float]
    diacritic_share: float


def build_ngram_profile(
    source: str,
    size: int | None = None,
    n_max: int | None = None,
) -> NgramProfile:
    """Профиль N-грамм: топ-`size` самых частотных N-грамм текста"""
    limit = size if size is not None else config.NGRAM_PROFILE_SIZE
    counts = Counter(text.char_ngrams(source, n_max))
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ngrams = tuple(g for g, _ in ranked[:limit])
    return NgramProfile(ngrams=ngrams, ranks={g: i for i, g in enumerate(ngrams)})


def build_alphabet_profile(source: str, alphabet: frozenset[str]) -> AlphabetProfile:
    """Частотный профиль букв языка и ожидаемая доля диакритики по тренировочному тексту."""
    counts = text.letter_counts(source)
    total = sum(counts.values()) or 1
    return AlphabetProfile(
        alphabet=alphabet,
        letter_freq={ch: n / total for ch, n in counts.items()},
        diacritic_share=text.diacritic_share(counts),
    )
