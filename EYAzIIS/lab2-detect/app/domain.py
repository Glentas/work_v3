from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Document:
    """Один входной документ тестовой коллекции."""

    id: str                    # имя файла без расширения, уникален в коллекции
    name: str                  # имя файла, например fr_07.html
    path: str                  # абсолютный путь к файлу
    lang_true: str             # истинный язык (из имени файла), для оценки точности
    suite: str                 # набор: "main" или имя стресс-сценария
    encoding: str = ""         # кодировка, фактически использованная на шаге 1
    chars: int = 0             # длина видимого текста после шага 1


@dataclass(frozen=True, slots=True)
class DetectionResult:
    """Решение одного метода по одному документу."""

    doc_id: str
    method: str
    lang: str | None           # None — метод не смог решить / недоступен
    distance: float            # метрика расстояния ПОД до ПОЯ выбранного языка
    ranked: tuple[tuple[str, float], ...]   # все языки, по возрастанию расстояния
    elapsed_ms: float
    error: str | None = None   # например: отсутствует файл модели


@dataclass(frozen=True, slots=True)
class MethodReport:
    """Сводка по одному методу на одном наборе документов."""

    method: str
    total: int
    correct: int
    accuracy: float | None
    per_lang: dict[str, tuple[int, int]]            # язык -> (верно, всего)
    confusion: dict[str, dict[str, int]]            # истинный -> {предсказанный: число}
    time_median_ms: float
    time_total_ms: float
    errors: int                                     # число сбоев метода


@dataclass(frozen=True, slots=True)
class PairReport:
    """Попарное сравнение двух методов: пункт «оценка для пары методов»."""

    first: str
    second: str
    agreement: float                                # доля документов с одинаковым ответом
    accuracy_first: float | None
    accuracy_second: float | None
    time_first_ms: float
    time_second_ms: float


@dataclass(frozen=True, slots=True)
class SuiteResult:
    """Полный результат распознавания одного набора документов."""

    suite: str
    documents: tuple[Document, ...]
    results: tuple[DetectionResult, ...]
    reports: dict[str, MethodReport] = field(default_factory=dict)
    pairs: tuple[PairReport, ...] = ()
    total_ms: float = 0.0
