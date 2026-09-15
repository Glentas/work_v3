"""Прогон распознавания по наборам документов и кэш результатов"""

from __future__ import annotations

import logging
import time

from . import corpus, evaluation
from .detector import get_detector
from .domain import SuiteResult

log = logging.getLogger(__name__)

_CACHE: dict[str, SuiteResult] = {}


def run_suite(suite: str, force: bool = False) -> SuiteResult:
    """Распознаёт все документы набора всеми методами и считает сводку."""
    if not force and suite in _CACHE:
        return _CACHE[suite]

    documents = corpus.scan_suite(_suite_path(suite), suite)
    if not documents:
        raise FileNotFoundError(f"в наборе {suite!r} нет документов")

    detector = get_detector()
    filled: list = []
    results: list = []

    started = time.perf_counter()
    for doc in documents:
        visible, doc = corpus.open_document(doc)
        filled.append(doc)
        results.extend(detector.detect(visible, doc_id=doc.id))
    log.info(
        "Набор %s: %d документов распознано за %.0f мс",
        suite, len(filled), (time.perf_counter() - started) * 1000,
    )

    summary = evaluation.summarize(filled, results)
    _CACHE[suite] = summary
    return summary


def run_all(force: bool = False) -> dict[str, SuiteResult]:
    """Основная коллекция и все стресс-наборы."""
    out: dict[str, SuiteResult] = {}
    for suite in corpus.scan_all():
        try:
            out[suite] = run_suite(suite, force=force)
        except FileNotFoundError as exc:
            log.warning("%s", exc)
    return out


def recognize_text(source: str) -> list:
    """Разовое распознавание произвольного текста (форма на главной странице)."""
    return get_detector().detect(source, doc_id="")


def suites() -> list[str]:
    return list(corpus.scan_all())


def suites_documents() -> list[tuple[str, list]]:
    """Наборы и их документы без распознавания (для главной страницы)."""
    return [(name, docs) for name, docs in corpus.scan_all().items()]


def cached(suite: str) -> SuiteResult | None:
    return _CACHE.get(suite)


def reset_cache() -> None:
    _CACHE.clear()


def _suite_path(suite: str):
    from . import config

    return config.TEST_PATH if suite == "main" else config.STRESS_PATH / suite


def describe_documents(suite: str) -> list:
    """Метаданные документов набора без распознавания (для страницы набора)."""
    out = []
    for doc in corpus.scan_suite(_suite_path(suite), suite):
        _, filled = corpus.open_document(doc)
        out.append(filled)
    return out
