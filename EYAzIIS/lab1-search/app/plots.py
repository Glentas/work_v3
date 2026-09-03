from __future__ import annotations

import base64
import io

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from .domain import MetricsItem


def _figure_to_base64(fig) -> str:
    buffer = io.BytesIO()

    fig.savefig(buffer, format="png", bbox_inches="tight")
    plt.close(fig)

    buffer.seek(0)

    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def metrics_bar_plot(metrics: list[MetricsItem]) -> str | None:
    """
    Строит столбчатую диаграмму по метрикам.

    Если запросов несколько, усредняет значения по всем запросам.
    """
    if not metrics:
        return None

    fields = [
        ("precision", "Precision"),
        ("recall", "Recall"),
        ("f_measure", "F-measure"),
        ("precision_5", "Precision@5"),
        ("precision_10", "Precision@10"),
        ("r_precision", "R-Precision"),
        ("average_precision", "AvgPrec"),
    ]

    labels: list[str] = []
    values: list[float] = []

    for field, label in fields:
        field_values = [
            getattr(metric, field)
            for metric in metrics
            if getattr(metric, field) is not None
        ]

        if field_values:
            labels.append(label)
            values.append(sum(field_values) / len(field_values))

    if not values:
        return None

    fig, ax = plt.subplots(figsize=(9, 4))

    ax.bar(labels, values, color="steelblue")
    ax.set_ylim(0, 1)
    ax.set_ylabel("Score")
    ax.set_title("Search quality metrics")
    ax.grid(axis="y", alpha=0.3)

    for tick in ax.get_xticklabels():
        tick.set_rotation(20)

    return _figure_to_base64(fig)


def eleven_point_plot(metric: MetricsItem | None) -> str | None:
    """
    Строит 11-точечный график интерполированной точности для одного запроса.
    """
    if metric is None or not metric.interpolated_precision:
        return None

    x = [i / 10 for i in range(11)]
    y = metric.interpolated_precision

    fig, ax = plt.subplots(figsize=(6, 4))

    ax.plot(x, y, marker="o", color="darkred")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("Recall")
    ax.set_ylabel("Interpolated precision")
    ax.set_title("11-point precision/recall")
    ax.grid(alpha=0.3)

    return _figure_to_base64(fig)