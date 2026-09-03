def compute_metrics(ranked_doc_ids: list[int], relevant_doc_ids: set[int]) -> dict | None:
    """
    Считает метрики по методике РОМИП для дорожки поиска.

    Если для запроса нет релевантных документов, возвращает None,
    такие запросы не учитываются.
    """
    total_found = len(ranked_doc_ids)
    total_relevant = len(relevant_doc_ids)

    if total_relevant == 0:
        return None

    relevant_positions = []

    for pos, doc_id in enumerate(ranked_doc_ids, start=1):
        if doc_id in relevant_doc_ids:
            relevant_positions.append(pos)

    found_relevant = len(relevant_positions)

    recall = found_relevant / total_relevant
    precision = found_relevant / total_found if total_found > 0 else 0.0

    sum_prec = 0.0
    for idx, pos in enumerate(relevant_positions, start=1):
        sum_prec += idx / pos

    avg_prec = sum_prec / total_relevant

    p5 = sum(1 for pos in relevant_positions if pos <= 5) / 5.0
    p10 = sum(1 for pos in relevant_positions if pos <= 10) / 10.0
    r_prec = sum(1 for pos in relevant_positions if pos <= total_relevant) / total_relevant

    pr_curve = compute_11_point(
        relevant_positions,
        total_relevant,
        total_found
    )

    return {
        "total_found": total_found,
        "total_relevant": total_relevant,
        "relevant_positions": relevant_positions,
        "recall": recall,
        "precision": precision,
        "avg_prec": avg_prec,
        "p5": p5,
        "p10": p10,
        "r_prec": r_prec,
        "pr_curve": pr_curve,
    }


def compute_11_point(relevant_positions: list[int], total_relevant: int, total_found: int) -> list[float]:
    """
    11-точечный график полноты/точности по методике TREC.
    """
    if total_found == 0 or total_relevant == 0:
        return [0.0] * 11

    curve = []

    for i in range(11):
        level = i / 10.0
        best_precision = 0.0

        for idx, pos in enumerate(relevant_positions, start=1):
            recall_at_pos = idx / total_relevant

            if recall_at_pos >= level:
                precision_at_pos = idx / pos
                if precision_at_pos > best_precision:
                    best_precision = precision_at_pos

        curve.append(best_precision)

    return curve