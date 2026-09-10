from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from . import config
from .domain import METRIC_LABELS, Metrics, MetricsSummary, SearchParams

_SCHEMA = Path(__file__).parent / "schema.sql"
_PR_CURVE_POINTS = 11


# ---------------------------------------------------------------------------
# Соединение
# ---------------------------------------------------------------------------
@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Открывает соединение и гарантированно закрывает его на выходе"""
    conn = sqlite3.connect(
        config.DB_PATH,
        timeout=config.DB_BUSY_TIMEOUT_MS / 1000,
        isolation_level=None,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(f"PRAGMA busy_timeout = {config.DB_BUSY_TIMEOUT_MS}")
        yield conn
    finally:
        conn.close()


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Атомарный блок: либо фиксируются все изменения, либо ни одного"""

    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def init_db() -> None:
    """Создаёт схему и переводит базу в режим WAL."""
    config.ensure_dirs()
    with connect() as conn:
        conn.executescript(_SCHEMA.read_text(encoding="utf-8"))
        conn.execute("PRAGMA journal_mode = WAL")


def _in_clause(values: Sequence) -> str:
    """Плейсхолдеры для оператора IN. Значения всегда передаются параметрами."""
    return ",".join("?" * len(values))


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def get_document(conn: sqlite3.Connection, doc_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM documents WHERE id = ?", (doc_id,)
    ).fetchone()


def count_documents(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]


def find_query_id(conn: sqlite3.Connection, params: SearchParams) -> int | None:
    row = conn.execute(
        "SELECT id FROM queries WHERE params_json = ?", (params.key,)
    ).fetchone()
    return row["id"] if row else None


def ensure_query(conn: sqlite3.Connection, params: SearchParams) -> int:
    """Возвращает id запроса, создавая запись при первом обращении."""
    existing = find_query_id(conn, params)
    if existing is not None:
        return existing

    return conn.execute(
        "INSERT INTO queries (query_text, params_json, created_at) VALUES (?, ?, ?)",
        (params.q, params.key, _now()),
    ).lastrowid


def relevant_doc_ids(conn: sqlite3.Connection, query_id: int) -> set[int]:
    rows = conn.execute(
        "SELECT doc_id FROM relevance_marks WHERE query_id = ?", (query_id,)
    ).fetchall()
    return {row["doc_id"] for row in rows}


def set_relevance(
    conn: sqlite3.Connection,
    query_id: int,
    doc_ids: Iterable[int],
    relevant: bool,
) -> None:
    """Отмечает документы как релевантные либо снимает отметку"""
    ids = list(dict.fromkeys(doc_ids))
    if not ids:
        return

    if relevant:
        conn.executemany(
            "INSERT OR IGNORE INTO relevance_marks (query_id, doc_id) VALUES (?, ?)",
            [(query_id, doc_id) for doc_id in ids],
        )
    else:
        conn.execute(
            f"DELETE FROM relevance_marks WHERE query_id = ? AND doc_id IN ({_in_clause(ids)})",
            [query_id, *ids],
        )


def clear_relevance(conn: sqlite3.Connection, query_id: int) -> None:
    conn.execute("DELETE FROM relevance_marks WHERE query_id = ?", (query_id,))


def mark_relevance(
    conn: sqlite3.Connection, params: SearchParams, doc_ids: list[int], relevant: bool
) -> int:
    """Сохраняет отметки и возвращает id запроса, переживая переиндексацию"""
    try:
        query_id = ensure_query(conn, params)
        set_relevance(conn, query_id, doc_ids, relevant)
        return query_id
    except sqlite3.IntegrityError:
        query_id = ensure_query(conn, params)
        set_relevance(conn, query_id, doc_ids, relevant)
        return query_id


# ---------------------------------------------------------------------------
# Метрики качества
# ---------------------------------------------------------------------------
def save_metrics(conn: sqlite3.Connection, query_id: int, m: Metrics) -> None:
    """Сохраняет оценку запроса, заменяя предыдущую"""
    conn.execute(
        """
        INSERT INTO query_metrics (
            query_id, total_found, total_relevant, found_relevant,
            relevant_positions, recall, precision, f_measure, avg_prec,
            p5, p10, r_prec, pr_curve, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(query_id) DO UPDATE SET
            total_found        = excluded.total_found,
            total_relevant     = excluded.total_relevant,
            found_relevant     = excluded.found_relevant,
            relevant_positions = excluded.relevant_positions,
            recall             = excluded.recall,
            precision          = excluded.precision,
            f_measure          = excluded.f_measure,
            avg_prec           = excluded.avg_prec,
            p5                 = excluded.p5,
            p10                = excluded.p10,
            r_prec             = excluded.r_prec,
            pr_curve           = excluded.pr_curve,
            created_at         = excluded.created_at
        """,
        (
            query_id,
            m.total_found,
            m.total_relevant,
            m.found_relevant,
            json.dumps(list(m.relevant_positions)),
            m.recall,
            m.precision,
            m.f_measure,
            m.avg_prec,
            m.p5,
            m.p10,
            m.r_prec,
            json.dumps(list(m.pr_curve)),
            _now(),
        ),
    )


def metrics_summary(conn: sqlite3.Connection) -> MetricsSummary:
    """Макро- и микроусреднённые показатели по всем сохранённым оценкам."""
    row = conn.execute(
        """
        SELECT COUNT(*)            AS n,
               AVG(recall)         AS recall,
               AVG(precision)      AS precision,
               AVG(f_measure)      AS f_measure,
               AVG(avg_prec)       AS avg_prec,
               AVG(p5)             AS p5,
               AVG(p10)            AS p10,
               AVG(r_prec)         AS r_prec,
               SUM(found_relevant) AS found_relevant,
               SUM(total_found)    AS total_found,
               SUM(total_relevant) AS total_relevant
        FROM query_metrics
        """
    ).fetchone()

    total = row["n"] or 0
    macro = {name: row[name] for name, _ in METRIC_LABELS}

    if total == 0:
        return MetricsSummary(
            total_queries=0,
            macro={name: None for name, _ in METRIC_LABELS},
            micro={"recall": None, "precision": None, "f_measure": None},
            avg_pr_curve=tuple([0.0] * _PR_CURVE_POINTS),
        )

    # Микроусреднение: метрика считается по суммарным
    # количествам документов матрицы классификации, а не как среднее запросов.
    a = row["found_relevant"] or 0        # релевантные, найденные системой
    ab = row["total_found"] or 0          # a + b: все найденные
    ac = row["total_relevant"] or 0       # a + c: все релевантные
    micro_p = a / ab if ab else 0.0
    micro_r = a / ac if ac else 0.0
    micro_f = (
        2 * micro_p * micro_r / (micro_p + micro_r) if (micro_p + micro_r) else 0.0
    )

    curves = [
        json.loads(value)
        for (value,) in conn.execute("SELECT pr_curve FROM query_metrics")
    ]
    curves = [c for c in curves if len(c) == _PR_CURVE_POINTS]
    avg_curve = tuple(
        sum(c[i] for c in curves) / len(curves) if curves else 0.0
        for i in range(_PR_CURVE_POINTS)
    )

    return MetricsSummary(
        total_queries=total,
        macro=macro,
        micro={"recall": micro_r, "precision": micro_p, "f_measure": micro_f},
        avg_pr_curve=avg_curve,
    )


def metrics_rows(
    conn: sqlite3.Connection, limit: int, offset: int
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT qm.query_id, q.query_text, qm.total_found, qm.total_relevant,
               qm.recall, qm.precision, qm.f_measure, qm.avg_prec,
               qm.p5, qm.p10, qm.r_prec, qm.created_at
        FROM query_metrics qm
        JOIN queries q ON q.id = qm.query_id
        ORDER BY qm.created_at DESC, qm.query_id DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    ).fetchall()


def metrics_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM query_metrics").fetchone()[0]


def pr_curve(conn: sqlite3.Connection, query_id: int) -> list[float]:
    row = conn.execute(
        "SELECT pr_curve FROM query_metrics WHERE query_id = ?", (query_id,)
    ).fetchone()
    return json.loads(row["pr_curve"]) if row and row["pr_curve"] else []


def pr_curve_data(conn: sqlite3.Connection, query_id: int) -> dict | None:
    """Данные для графика полнота/точность: кривая и фактические срезы"""
    from .evaluation import precision_recall_cuts

    row = conn.execute(
        """
        SELECT q.query_text      AS query_text,
               qm.total_found    AS total_found,
               qm.total_relevant AS total_relevant,
               qm.relevant_positions AS relevant_positions,
               qm.pr_curve       AS pr_curve
        FROM query_metrics qm
        JOIN queries q ON q.id = qm.query_id
        WHERE qm.query_id = ?
        """,
        (query_id,),
    ).fetchone()

    if row is None:
        return None

    positions = json.loads(row["relevant_positions"] or "[]")
    return {
        "query_text": row["query_text"],
        "total_found": row["total_found"],
        "total_relevant": row["total_relevant"],
        "relevant_positions": positions,
        "interpolated": json.loads(row["pr_curve"] or "[]"),
        "cuts": [
            list(cut) for cut in precision_recall_cuts(positions, row["total_relevant"])
        ],
    }


def reset_all(conn: sqlite3.Connection) -> None:
    """Полностью очищает базу перед переиндексацией"""
    for table in (
        "query_metrics",
        "relevance_marks",
        "queries",
        "postings",
        "documents",
        "terms",
    ):
        conn.execute(f"DELETE FROM {table}")


def index_info(conn: sqlite3.Connection) -> dict[str, int]:
    """Состояние индекса — для отображения на страницах интерфейса."""
    row = conn.execute(
        """
        SELECT (SELECT COUNT(*) FROM documents) AS documents,
               (SELECT COUNT(*) FROM terms)     AS terms,
               (SELECT COUNT(*) FROM postings)  AS postings
        """
    ).fetchone()
    return {key: row[key] for key in row.keys()}


def clear_evaluations(conn: sqlite3.Connection) -> None:
    """Удаляет разметку и сохранённые оценки, не трогая индекс"""
    for table in ("query_metrics", "relevance_marks", "queries"):
        conn.execute(f"DELETE FROM {table}")
