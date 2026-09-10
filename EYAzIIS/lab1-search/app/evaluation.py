"""Оценка качества поиска по официальным метрикам РОМИП'2004 (дорожка поиска).

Реализованы метрики из методички ``romip_metrics.pdf``:

============  ============================================================
Полнота       recall = a / (a + c)                                        (п. 1.1.1)
Точность      precision = a / (a + b)                                     (п. 1.1.2)
F-мера        F = 2pr / (p + r)                                           (п. 1.1.5)
Ср. точность  AvgPrec = (1/k) Σ prec_rel(i)                               (п. 1.3.3)
Точность @n   precision(n) = число релевантных среди первых n / n         (п. 1.3.1)
R-точность    precision(n) при n = числе релевантных документов           (п. 1.3.2)
11 точек      интерполированный график полнота/точность по TREC           (п. 1.3.4)
============  ============================================================

где a — релевантные документы, найденные системой; b — найденные,
но не релевантные; c — релевантные, но не найденные.

Соглашение РОМИП: запросы, для которых нет ни одного релевантного документа,
при вычислении метрик не рассматриваются (полнота в этом случае —
неопределённость 0/0), поэтому :func:`compute_metrics` возвращает ``None``.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from .domain import Metrics

#: Число фиксированных уровней полноты: 0.0, 0.1, …, 1.0.
PR_CURVE_POINTS = 11


def compute_metrics(
    ranked_doc_ids: Sequence[int], relevant_doc_ids: Iterable[int]
) -> Metrics | None:
    """Считает метрики для одного запроса.

    :param ranked_doc_ids: выдача системы, упорядоченная по убыванию релевантности;
    :param relevant_doc_ids: документы, отмеченные экспертом как релевантные.
    """
    relevant = set(relevant_doc_ids)

    total_found = len(ranked_doc_ids)        # a + b
    total_relevant = len(relevant)           # a + c

    if total_relevant == 0:
        return None

    # Позиции релевантных документов в выдаче, начиная с 1.
    positions = tuple(
        position
        for position, doc_id in enumerate(ranked_doc_ids, start=1)
        if doc_id in relevant
    )
    found_relevant = len(positions)          # a

    recall = found_relevant / total_relevant
    precision = found_relevant / total_found if total_found else 0.0

    return Metrics(
        total_found=total_found,
        total_relevant=total_relevant,
        found_relevant=found_relevant,
        relevant_positions=positions,
        recall=recall,
        precision=precision,
        f_measure=f_measure(precision, recall),
        avg_prec=average_precision(positions, total_relevant),
        p5=precision_at(positions, 5),
        p10=precision_at(positions, 10),
        r_prec=precision_at(positions, total_relevant),
        pr_curve=interpolated_precision(positions, total_relevant),
    )


def f_measure(precision: float, recall: float) -> float:
    """F-мера — гармоническое среднее точности и полноты (РОМИП, п. 1.1.5)."""
    total = precision + recall
    return 2 * precision * recall / total if total else 0.0


def average_precision(positions: Sequence[int], total_relevant: int) -> float:
    """Средняя точность (РОМИП, п. 1.3.3).

    Точность на уровне i-го релевантного документа равна i / pos(i),
    если документ найден на позиции pos(i), и 0, если не найден.
    Итог — среднее по всем релевантным документам запроса, поэтому
    знаменатель всегда равен их полному числу, а не числу найденных.
    """
    if not total_relevant:
        return 0.0

    return sum(
        found / position for found, position in enumerate(positions, start=1)
    ) / total_relevant


def precision_at(positions: Sequence[int], level: int) -> float:
    """Точность на уровне ``level`` документов (РОМИП, п. 1.3.1).

    Если система выдала меньше ``level`` документов, значение заведомо
    не выше общей точности — знаменатель остаётся равным ``level``.
    """
    if level <= 0:
        return 0.0

    return sum(1 for position in positions if position <= level) / level


def interpolated_precision(
    positions: Sequence[int], total_relevant: int
) -> tuple[float, ...]:
    """11-точечный график полнота/точность по методике TREC (РОМИП, п. 1.3.4).

    Интерполированное значение точности для уровня полноты r равно
    максимальной точности на срезах выдачи, где полнота не меньше r::

        p(r) = max precision(n)  по всем n >= pos(r)

    Если уровень полноты недостижим (система нашла меньше релевантных
    документов), точность принимается равной нулю.
    """
    if not positions or not total_relevant:
        return tuple([0.0] * PR_CURVE_POINTS)

    # (полнота, точность) для каждого среза выдачи, заканчивающегося
    # на релевантном документе.
    cuts = [
        (found / total_relevant, found / position)
        for found, position in enumerate(positions, start=1)
    ]

    return tuple(
        max(
            (precision for recall, precision in cuts if recall >= level / 10),
            default=0.0,
        )
        for level in range(PR_CURVE_POINTS)
    )


def precision_recall_cuts(
    positions: Sequence[int], total_relevant: int
) -> tuple[tuple[float, float], ...]:
    """Фактические (неинтерполированные) точки графика полнота/точность.

    Каждая точка соответствует срезу выдачи, заканчивающемуся на очередном
    релевантном документе: ``(i / total_relevant, i / pos(i))``.

    Именно эти точки на рис. 2 методички РОМИП обозначены маркерами,
    а интерполированные значения — пунктирной линией. По ним видно, почему
    интерполированная кривая вырождается: если релевантных документов мало,
    полнота принимает всего два-три значения, и интерполяция максимумом
    «размазывает» их на все 11 уровней.
    """
    if not total_relevant:
        return ()

    return tuple(
        (found / total_relevant, found / position)
        for found, position in enumerate(positions, start=1)
    )
