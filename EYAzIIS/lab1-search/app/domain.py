from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Запросы к API
# ---------------------------------------------------------------------------
class SearchParams(BaseModel):
    """Параметры поиска"""

    q: str = ""
    all_words: bool = False
    date_start: str = ""
    date_end: str = ""

    @property
    def key(self) -> str:
        """Стабильный строковый ключ (используется как params_json в БД)."""
        return self.model_dump_json()


class RelevanceRequest(BaseModel):
    params: SearchParams
    doc_id: int
    relevant: bool


class BatchRelevanceRequest(BaseModel):
    params: SearchParams
    doc_ids: list[int]
    relevant: bool


@dataclass(frozen=True, slots=True)
class Hit:
    """Один документ поисковой выдачи (аналог SearchResult из методички)."""

    doc_id: int
    position: int                 # 1-based позиция в полном ранжированном списке
    title: str
    snippet_html: str             # фрагмент текста с подсветкой слов запроса
    rank: float                   # Σ A_i^j по совпавшим терминам
    matched_count: int            # сколько терминов запроса найдено в документе
    matched_words: tuple[str, ...]  # исходные слова запроса, присутствующие в документе
    keywords: str
    date: str


@dataclass(frozen=True, slots=True)
class SearchOutcome:
    """Полный результат поиска: выдача + служебная информация для интерфейса."""

    hits: list[Hit] = field(default_factory=list)
    total: int = 0
    doc_ids: tuple[int, ...] = ()          # весь ранжированный список (нужен для метрик)
    mode: str = "and"                      # фактически применённая логика: "and" или "or"
    fallback: bool = False                 # сработала ли стратегия с отказами
    known_terms: tuple[str, ...] = ()      # термины запроса, найденные в индексе
    unknown_terms: tuple[str, ...] = ()    # термины, которых нет в словаре коллекции


METRIC_LABELS: tuple[tuple[str, str], ...] = (
    ("recall", "Recall"),
    ("precision", "Precision"),
    ("f_measure", "F-мера"),
    ("avg_prec", "AvgPrec"),
    ("p5", "P@5"),
    ("p10", "P@10"),
    ("r_prec", "R-Prec"),
)


@dataclass(frozen=True, slots=True)
class Metrics:
    """Оценки качества поиска для одного запроса."""

    total_found: int                      # a + b
    total_relevant: int                   # a + c
    found_relevant: int                   # a
    relevant_positions: tuple[int, ...]   # позиции релевантных документов, 1-based
    recall: float
    precision: float
    f_measure: float
    avg_prec: float
    p5: float
    p10: float
    r_prec: float
    pr_curve: tuple[float, ...]           # 11 интерполированных значений точности


@dataclass(frozen=True, slots=True)
class MetricsSummary:
    """Интегральные показатели по всем сохранённым оценкам"""

    total_queries: int
    macro: dict[str, float | None]
    micro: dict[str, float | None]
    avg_pr_curve: tuple[float, ...]
