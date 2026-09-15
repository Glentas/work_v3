"""Детектор: выбор языка с минимумом метрики, детерминизм, нейросетевой метод."""

from __future__ import annotations

from pathlib import Path

import pytest

from app import config, neural
from app.detector import Detector, read_train_texts

FR_SENT = "Bonjour, comment allez-vous aujourd'hui dans cette belle forêt?"
EN_SENT = "Hello, how are you today in this beautiful forest near the river?"


@pytest.fixture(scope="module")
def detector() -> Detector:
    return Detector(read_train_texts())


def _by_method(results):
    return {r.method: r for r in results}


def test_ngram_and_alphabet_recognize_french(detector):
    got = _by_method(detector.detect(FR_SENT))
    assert got["ngram"].lang == "fr"
    assert got["alphabet"].lang == "fr"


def test_ngram_and_alphabet_recognize_english(detector):
    got = _by_method(detector.detect(EN_SENT))
    assert got["ngram"].lang == "en"
    assert got["alphabet"].lang == "en"


def test_ranked_sorted_ascending_and_complete(detector):
    for result in detector.detect(FR_SENT):
        distances = [d for _, d in result.ranked]
        assert distances == sorted(distances)
        assert {lang for lang, _ in result.ranked} == set(config.LANGS)


def test_detection_is_deterministic(detector):
    first = detector.detect(FR_SENT)
    second = detector.detect(FR_SENT)
    assert [(r.method, r.lang, r.distance) for r in first] == [
        (r.method, r.lang, r.distance) for r in second
    ]


def test_neural_method_or_skip(detector):
    try:
        neural.predict_distances(FR_SENT)
    except neural.NeuralUnavailable:
        pytest.skip("модель fastText не скачана")
    got = _by_method(detector.detect(FR_SENT))
    assert got["neural"].lang == "fr"
    assert got["neural"].error is None
    # расстояние = 1 - вероятность: меньше у правильного языка
    ranked = dict(got["neural"].ranked)
    assert ranked["fr"] < ranked["en"]


def test_neural_unavailable_reported_as_error(monkeypatch, detector):
    monkeypatch.setattr(config, "MODEL_PATH", Path("/nonexistent/missing.ftz"))
    neural.reset()
    got = _by_method(detector.detect(FR_SENT))
    assert got["neural"].lang is None
    assert got["neural"].error is not None
    neural.reset()
