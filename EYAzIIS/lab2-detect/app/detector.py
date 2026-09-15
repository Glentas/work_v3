"""Шаги 2–3: распознавание языка входного текста и выбор языка с минимумом метрики"""

from __future__ import annotations

import time
from functools import lru_cache

from . import config, distances, neural, text
from .domain import DetectionResult
from .profiles import AlphabetProfile, NgramProfile, build_alphabet_profile, build_ngram_profile


class Detector:
    """Хранит поисковые образы языков и применяет к тексту три метода."""

    def __init__(self, train_texts: dict[str, str]) -> None:
        self.ngram: dict[str, NgramProfile] = {
            lang: build_ngram_profile(source) for lang, source in train_texts.items()
        }
        self.alphabet: dict[str, AlphabetProfile] = {
            lang: build_alphabet_profile(source, config.LANG_ALPHABETS[lang])
            for lang, source in train_texts.items()
        }

    # -- отдельные методы ----------------------------------------------------
    def _detect_ngram(self, source: str) -> tuple[tuple[tuple[str, float], ...], float]:
        doc = build_ngram_profile(source)
        ranked = tuple(
            (lang, float(distances.out_of_place(doc, profile)))
            for lang, profile in self.ngram.items()
        )
        return _sort_ranked(ranked), 0.0

    def _detect_alphabet(self, source: str) -> tuple[tuple[tuple[str, float], ...], float]:
        counts = text.letter_counts(source)
        ranked = tuple(
            (lang, distances.alphabet_distance(counts, profile))
            for lang, profile in self.alphabet.items()
        )
        return _sort_ranked(ranked), 0.0

    @staticmethod
    def _detect_neural(source: str) -> tuple[tuple[tuple[str, float], ...], float]:
        ranked = tuple(neural.predict_distances(source).items())
        return _sort_ranked(ranked), 0.0

    # -- общий вход ----------------------------------------------------------
    def detect(self, source: str, doc_id: str = "") -> list[DetectionResult]:
        """Прогоняет текст через все методы; время каждого метода замеряется."""
        results: list[DetectionResult] = []
        for method, runner in (
            ("ngram", self._detect_ngram),
            ("alphabet", self._detect_alphabet),
            ("neural", self._detect_neural),
        ):
            started = time.perf_counter()
            error: str | None = None
            try:
                ranked, _ = runner(source)
                lang, distance = ranked[0]
            except neural.NeuralUnavailable as exc:
                ranked, lang, distance, error = (), None, float("inf"), str(exc)
            elapsed = (time.perf_counter() - started) * 1000.0
            results.append(
                DetectionResult(
                    doc_id=doc_id,
                    method=method,
                    lang=lang,
                    distance=distance,
                    ranked=ranked,
                    elapsed_ms=elapsed,
                    error=error,
                )
            )
        return results


def _sort_ranked(ranked: tuple[tuple[str, float], ...]) -> tuple[tuple[str, float], ...]:
    """Сортировка по расстоянию; при равенстве — детерминированный тай-брейк
    по порядку языков варианта, иначе результат зависел бы от порядка обхода."""
    order = {lang: i for i, lang in enumerate(config.LANGS)}
    return tuple(sorted(ranked, key=lambda item: (item[1], order.get(item[0], 99))))


def read_train_texts() -> dict[str, str]:
    """Тренировочный набор: по одному файлу на язык (20–120 Кб)."""
    texts: dict[str, str] = {}
    for lang in config.LANGS:
        path = config.TRAIN_PATH / f"{lang}.txt"
        if not path.exists():
            raise FileNotFoundError(
                f"тренировочный набор не найден: {path}. "
                "Запустите scripts/build_corpus.py и scripts/make_test_docs.py."
            )
        texts[lang] = path.read_text(encoding="utf-8")
    return texts


@lru_cache(maxsize=1)
def get_detector() -> Detector:
    """Детектор строится один раз на процесс: ПОЯ не меняются во время работы."""
    return Detector(read_train_texts())
