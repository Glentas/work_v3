"""Оценка результатов: точность, матрицы ошибок, время, попарное сравнение"""

from __future__ import annotations

import statistics
from collections import defaultdict
from itertools import combinations

from . import config
from .domain import DetectionResult, Document, MethodReport, PairReport, SuiteResult

#: Метка предсказания, когда метод не дал ответа (сбой или «не определено»).
NO_ANSWER = "—"


def summarize(documents: list[Document], results: list[DetectionResult]) -> SuiteResult:
    """Сводка по набору: отчёт каждого метода + попарные сравнения."""
    by_doc: dict[str, Document] = {d.id: d for d in documents}
    per_method: dict[str, list[DetectionResult]] = defaultdict(list)
    for result in results:
        per_method[result.method].append(result)

    reports = {
        method: _method_report(method, per_method.get(method, []), by_doc)
        for method in config.METHODS
    }
    pairs = tuple(
        _pair_report(reports[a], reports[b], per_method[a], per_method[b])
        for a, b in combinations(config.METHODS, 2)
    )
    return SuiteResult(
        suite=documents[0].suite if documents else "",
        documents=tuple(documents),
        results=tuple(results),
        reports=reports,
        pairs=pairs,
        total_ms=sum(r.elapsed_ms for r in results),
    )


def _method_report(
    method: str, results: list[DetectionResult], by_doc: dict[str, Document]
) -> MethodReport:
    correct = 0
    errors = 0
    per_lang: dict[str, list[int]] = {lang: [0, 0] for lang in config.LANGS}
    confusion: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    times: list[float] = []

    for result in results:
        doc = by_doc[result.doc_id]
        per_lang.setdefault(doc.lang_true, [0, 0])
        per_lang[doc.lang_true][1] += 1
        times.append(result.elapsed_ms)

        if result.error is not None:
            errors += 1
            confusion[doc.lang_true][NO_ANSWER] += 1
            continue
        predicted = result.lang or NO_ANSWER
        confusion[doc.lang_true][predicted] += 1
        if predicted == doc.lang_true:
            correct += 1
            per_lang[doc.lang_true][0] += 1

    total = len(results)
    return MethodReport(
        method=method,
        total=total,
        correct=correct,
        accuracy=correct / total if total else None,
        per_lang={lang: (v[0], v[1]) for lang, v in per_lang.items()},
        confusion={t: dict(p) for t, p in confusion.items()},
        time_median_ms=statistics.median(times) if times else 0.0,
        time_total_ms=sum(times),
        errors=errors,
    )


def _pair_report(
    first: MethodReport,
    second: MethodReport,
    first_results: list[DetectionResult],
    second_results: list[DetectionResult],
) -> PairReport:
    """Сравнение пары методов: совпадение ответов, точности, время."""
    second_by_doc = {r.doc_id: r for r in second_results}
    same = 0
    compared = 0
    for result in first_results:
        other = second_by_doc.get(result.doc_id)
        if other is None or result.error or other.error:
            continue
        compared += 1
        same += result.lang == other.lang
    return PairReport(
        first=first.method,
        second=second.method,
        agreement=same / compared if compared else 0.0,
        accuracy_first=first.accuracy,
        accuracy_second=second.accuracy,
        time_first_ms=first.time_median_ms,
        time_second_ms=second.time_median_ms,
    )
