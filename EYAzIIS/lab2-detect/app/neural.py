"""Нейросетевой метод: готовая специализированная модель fastText"""

from __future__ import annotations

from . import config

_MODEL = None
_LOAD_ERROR: str | None = None


class NeuralUnavailable(RuntimeError):
    """Модель не найдена или не загрузилась — метод помечается недоступным."""


def _load():
    global _MODEL, _LOAD_ERROR
    if _MODEL is not None or _LOAD_ERROR is not None:
        return _MODEL
    if not config.MODEL_PATH.exists():
        _LOAD_ERROR = (
            f"файл модели не найден: {config.MODEL_PATH}. "
            "Запустите scripts/download_model.py один раз."
        )
        return None
    try:
        import fasttext

        _MODEL = fasttext.load_model(str(config.MODEL_PATH))
    except Exception as exc:  # битый файл, несовместимая платформа
        _LOAD_ERROR = f"не удалось загрузить модель: {exc}"
        return None
    return _MODEL


def predict_distances(source: str) -> dict[str, float]:
    """Расстояния 1 - P(язык) для всех языков варианта."""
    model = _load()
    if model is None:
        raise NeuralUnavailable(_LOAD_ERROR or "модель недоступна")

    # fastText принимает только однострочный текст.
    line = " ".join(source.split())
    labels, probs = model.predict(line, k=len(config.LANGS))

    distances = {lang: 1.0 for lang in config.LANGS}
    for label, prob in zip(labels, probs):
        lang = label.replace("__label__", "")
        if lang in distances:
            distances[lang] = 1.0 - float(prob)
    return distances


def reset() -> None:
    """Сброс кэша модели (используется тестами)."""
    global _MODEL, _LOAD_ERROR
    _MODEL = None
    _LOAD_ERROR = None
