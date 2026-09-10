"""Проверка расчёта метрик качества поиска.

Основной тест повторяет эталонный пример из методички РОМИП'2004 (п. 1.3.4),
для которого в документе приведены ожидаемые значения интерполированной
точности — это позволяет сверить реализацию с первоисточником, а не
с собственными допущениями.
"""

from __future__ import annotations

import pytest

from app.evaluation import (
    average_precision,
    compute_metrics,
    f_measure,
    interpolated_precision,
    precision_at,
    precision_recall_cuts,
)


def test_romip_reference_example():
    """Эталонный пример РОМИП'2004, п. 1.3.4.

    Коллекция из 20 документов, 4 из них релевантны. Система выдала все 20,
    релевантными оказались 1-й, 2-й, 4-й и 15-й. Методичка указывает ожидаемые
    интерполированные значения: полнота 0…0.5 -> точность 1.0;
    полнота 0.6 и 0.7 -> 0.75; полнота 0.8…1.0 -> 0.27 (4/15).
    """
    ranked = list(range(1, 21))
    relevant = {1, 2, 4, 15}

    metrics = compute_metrics(ranked, relevant)

    assert metrics is not None
    assert metrics.total_found == 20
    assert metrics.total_relevant == 4
    assert metrics.found_relevant == 4
    assert metrics.relevant_positions == (1, 2, 4, 15)

    assert metrics.recall == pytest.approx(1.0)
    assert metrics.precision == pytest.approx(4 / 20)
    assert metrics.avg_prec == pytest.approx((1 / 1 + 2 / 2 + 3 / 4 + 4 / 15) / 4)
    assert metrics.p5 == pytest.approx(3 / 5)
    assert metrics.p10 == pytest.approx(3 / 10)
    assert metrics.r_prec == pytest.approx(3 / 4)
    assert metrics.f_measure == pytest.approx(2 * 0.2 * 1.0 / 1.2)

    expected_curve = [1.0] * 6 + [0.75, 0.75] + [4 / 15] * 3
    assert len(metrics.pr_curve) == 11
    for index, (actual, expected) in enumerate(zip(metrics.pr_curve, expected_curve)):
        assert actual == pytest.approx(expected, abs=1e-9), f"уровень полноты {index / 10}"


def test_query_without_relevant_documents_is_skipped():
    """РОМИП: запросы без релевантных документов в расчёте метрик не участвуют."""
    assert compute_metrics([1, 2, 3], set()) is None
    assert compute_metrics([], set()) is None


def test_nothing_found():
    """Система не нашла ничего: все метрики нулевые, кроме полноты знаменателя."""
    metrics = compute_metrics([], {1, 2})

    assert metrics.total_found == 0
    assert metrics.found_relevant == 0
    assert metrics.recall == 0.0
    assert metrics.precision == 0.0          # деление на ноль не выполняется
    assert metrics.f_measure == 0.0
    assert metrics.avg_prec == 0.0
    assert metrics.pr_curve == tuple([0.0] * 11)


def test_partial_recall_truncates_curve():
    """Уровни полноты, которых система не достигла, получают нулевую точность."""
    ranked = [1, 9, 8, 7]
    # Релевантных четыре, но в выдачу попали только два (1-й и 2-й документы).
    metrics = compute_metrics(ranked, {1, 9, 100, 200})

    assert metrics.total_relevant == 4
    assert metrics.found_relevant == 2
    assert metrics.recall == pytest.approx(0.5)
    assert metrics.precision == pytest.approx(0.5)
    assert metrics.relevant_positions == (1, 2)

    # Полнота достигает лишь 0.5, поэтому уровни 0.6…1.0 недостижимы.
    assert metrics.pr_curve[:6] == pytest.approx([1.0] * 6)
    assert metrics.pr_curve[6:] == pytest.approx([0.0] * 5)


def test_precision_at_level_exceeds_found_documents():
    """Если выдано меньше n документов, точность на уровне n занижается (п. 1.3.1)."""
    metrics = compute_metrics([1, 2], {1, 2})

    assert metrics.p5 == pytest.approx(2 / 5)
    assert metrics.p10 == pytest.approx(2 / 10)
    assert metrics.r_prec == pytest.approx(1.0)   # n = 2, оба в первых двух


def test_average_precision_denominator_is_total_relevant():
    """Знаменатель AvgPrec — полное число релевантных документов, а не найденных."""
    # Найден один релевантный из четырёх, на позиции 3.
    assert average_precision((3,), total_relevant=4) == pytest.approx((1 / 3) / 4)
    assert average_precision((), total_relevant=4) == 0.0
    assert average_precision((), total_relevant=0) == 0.0


def test_precision_at_boundaries():
    assert precision_at((1, 2, 3), 3) == pytest.approx(1.0)
    assert precision_at((1, 2, 7), 5) == pytest.approx(2 / 5)
    assert precision_at((4,), 3) == 0.0
    assert precision_at((1,), 0) == 0.0           # вырожденный уровень


def test_f_measure_properties():
    """Свойства F-меры из РОМИП'2004, п. 1.1.5."""
    assert f_measure(0.0, 0.0) == 0.0
    assert f_measure(0.5, 0.0) == 0.0             # p или r равно 0 -> F = 0
    assert f_measure(0.0, 0.5) == 0.0
    assert f_measure(0.7, 0.7) == pytest.approx(0.7)   # p = r -> F = p = r
    assert f_measure(1.0, 1.0) == pytest.approx(1.0)

    for p, r in [(0.2, 0.9), (0.8, 0.3), (0.5, 0.5), (0.05, 1.0)]:
        value = f_measure(p, r)
        assert 0.0 <= value <= 1.0
        # Гармоническое среднее лежит между минимальным и максимальным аргументом.
        assert min(p, r) - 1e-12 <= value <= max(p, r) + 1e-12
        assert value == pytest.approx(2 * p * r / (p + r))


def test_interpolated_precision_is_non_increasing():
    """Интерполированная точность не возрастает с ростом требуемой полноты."""
    positions = (1, 3, 4, 10, 15, 20)
    curve = interpolated_precision(positions, total_relevant=6)

    assert len(curve) == 11
    assert all(curve[i] >= curve[i + 1] - 1e-12 for i in range(10))
    assert interpolated_precision((), 6) == tuple([0.0] * 11)
    assert interpolated_precision((1,), 0) == tuple([0.0] * 11)


def test_positions_are_one_based():
    """Позиции отсчитываются от 1: ошибка на единицу сдвинула бы все метрики."""
    metrics = compute_metrics([7, 8, 9], {7})

    assert metrics.relevant_positions == (1,)
    assert metrics.p5 == pytest.approx(1 / 5)

    metrics = compute_metrics([7, 8, 9], {9})
    assert metrics.relevant_positions == (3,)
    assert metrics.avg_prec == pytest.approx((1 / 3) / 1)


class TestPrecisionRecallCuts:
    """Фактические (неинтерполированные) точки графика — маркеры на рис. 2 методички."""

    def test_romip_example_cuts(self):
        """Пример РОМИП'2004: релевантны 1-й, 2-й, 4-й и 15-й из 20."""
        cuts = precision_recall_cuts((1, 2, 4, 15), total_relevant=4)

        assert cuts == pytest.approx([(0.25, 1.0), (0.5, 1.0), (0.75, 0.75), (1.0, 4 / 15)])

    def test_cuts_are_consistent_with_curve(self):
        """Интерполированная кривая — максимум точности среди срезов."""
        positions = (1, 3, 4, 10, 15, 20)
        cuts = precision_recall_cuts(positions, total_relevant=6)
        curve = interpolated_precision(positions, total_relevant=6)

        assert len(cuts) == len(positions)
        assert max(precision for _, precision in cuts) == pytest.approx(curve[0])

    def test_marking_top_documents_flattens_curve(self):
        """Отметка верхних документов даёт точность 1.0 на всех срезах.

        Это объясняет «прямую» на графике: интерполяция максимумом не может
        показать спад, если спада нет в фактических данных.
        """
        metrics = compute_metrics([1, 2, 3], {1, 2, 3})

        assert precision_recall_cuts(metrics.relevant_positions, 3) == pytest.approx(
            [(1 / 3, 1.0), (2 / 3, 1.0), (1.0, 1.0)]
        )
        assert set(metrics.pr_curve) == {1.0}

    def test_cuts_without_relevant_documents(self):
        assert precision_recall_cuts((1, 2), total_relevant=0) == ()
