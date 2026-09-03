import json
import sqlite3
from pathlib import Path
from datetime import datetime

from . import config


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = get_conn()
    schema_path = Path(__file__).parent / "schema.sql"
    with open(schema_path, "r", encoding="utf-8") as f:
        conn.executescript(f.read())

    row = conn.execute("SELECT id FROM metrics_summary WHERE id = 1").fetchone()
    if row is None:
        conn.execute("INSERT INTO metrics_summary (id) VALUES (1)")

    conn.commit()
    conn.close()


def get_query_by_params(conn: sqlite3.Connection, params):
    params_json = params.model_dump_json()
    return conn.execute(
        "SELECT * FROM queries WHERE params_json = ?",
        (params_json,)
    ).fetchone()


def ensure_query(conn: sqlite3.Connection, params) -> int:
    existing = get_query_by_params(conn, params)
    if existing:
        return existing["id"]

    now = datetime.now().isoformat(timespec="seconds")
    cur = conn.execute(
        "INSERT INTO queries (query_text, params_json, created_at) VALUES (?, ?, ?)",
        (params.q, params.model_dump_json(), now)
    )
    conn.commit()
    return cur.lastrowid


def get_relevant_doc_ids(conn: sqlite3.Connection, query_id: int) -> set[int]:
    rows = conn.execute(
        "SELECT doc_id FROM relevance_marks WHERE query_id = ?",
        (query_id,)
    ).fetchall()
    return {row["doc_id"] for row in rows}


def set_relevance(conn: sqlite3.Connection, query_id: int, doc_id: int, relevant: bool) -> None:
    if relevant:
        conn.execute(
            "INSERT OR IGNORE INTO relevance_marks (query_id, doc_id, relevant) VALUES (?, ?, 1)",
            (query_id, doc_id)
        )
    else:
        conn.execute(
            "DELETE FROM relevance_marks WHERE query_id = ? AND doc_id = ?",
            (query_id, doc_id)
        )
    conn.commit()


def set_relevance_batch(conn: sqlite3.Connection, query_id: int, doc_ids: list[int], relevant: bool) -> None:
    if not doc_ids:
        return

    chunk_size = 500

    if relevant:
        for i in range(0, len(doc_ids), chunk_size):
            chunk = doc_ids[i:i + chunk_size]
            conn.executemany(
                "INSERT OR IGNORE INTO relevance_marks (query_id, doc_id, relevant) VALUES (?, ?, 1)",
                [(query_id, doc_id) for doc_id in chunk]
            )
    else:
        for i in range(0, len(doc_ids), chunk_size):
            chunk = doc_ids[i:i + chunk_size]
            placeholders = ",".join("?" for _ in chunk)
            conn.execute(
                f"DELETE FROM relevance_marks WHERE query_id = ? AND doc_id IN ({placeholders})",
                [query_id, *chunk]
            )

    conn.commit()


def delete_all_relevance(conn: sqlite3.Connection, query_id: int) -> None:
    conn.execute("DELETE FROM relevance_marks WHERE query_id = ?", (query_id,))
    conn.commit()


def _update_summary(conn: sqlite3.Connection, values: dict, factor: int) -> None:
    row = conn.execute("SELECT * FROM metrics_summary WHERE id = 1").fetchone()

    total = row["total_queries"] + factor
    if total <= 0:
        conn.execute(
            """
            UPDATE metrics_summary
            SET total_queries = 0,
                sum_recall = 0,
                sum_precision = 0,
                sum_avg_prec = 0,
                sum_p5 = 0,
                sum_p10 = 0,
                sum_r_prec = 0,
                sum_pr_curve = '[]'
            WHERE id = 1
            """
        )
        return

    old_curve = json.loads(row["sum_pr_curve"] or "[]")
    if len(old_curve) != 11:
        old_curve = [0.0] * 11

    new_curve = [
        old_curve[i] + factor * values["pr_curve"][i]
        for i in range(11)
    ]

    conn.execute(
        """
        UPDATE metrics_summary
        SET total_queries = ?,
            sum_recall = ?,
            sum_precision = ?,
            sum_avg_prec = ?,
            sum_p5 = ?,
            sum_p10 = ?,
            sum_r_prec = ?,
            sum_pr_curve = ?
        WHERE id = 1
        """,
        (
            total,
            row["sum_recall"] + factor * values["recall"],
            row["sum_precision"] + factor * values["precision"],
            row["sum_avg_prec"] + factor * values["avg_prec"],
            row["sum_p5"] + factor * values["p5"],
            row["sum_p10"] + factor * values["p10"],
            row["sum_r_prec"] + factor * values["r_prec"],
            json.dumps(new_curve),
        )
    )


def save_metrics_for_query(conn: sqlite3.Connection, query_id: int, metrics: dict) -> None:
    old = conn.execute(
        "SELECT * FROM query_metrics WHERE query_id = ?",
        (query_id,)
    ).fetchone()

    if old:
        old_values = {
            "recall": old["recall"],
            "precision": old["precision"],
            "avg_prec": old["avg_prec"],
            "p5": old["p5"],
            "p10": old["p10"],
            "r_prec": old["r_prec"],
            "pr_curve": json.loads(old["pr_curve"] or "[]"),
        }
        _update_summary(conn, old_values, -1)
        conn.execute("DELETE FROM query_metrics WHERE query_id = ?", (query_id,))

    now = datetime.now().isoformat(timespec="seconds")

    conn.execute(
        """
        INSERT INTO query_metrics (
            query_id, total_found, total_relevant, relevant_positions,
            recall, precision, avg_prec, p5, p10, r_prec, pr_curve, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            query_id,
            metrics["total_found"],
            metrics["total_relevant"],
            json.dumps(metrics["relevant_positions"]),
            metrics["recall"],
            metrics["precision"],
            metrics["avg_prec"],
            metrics["p5"],
            metrics["p10"],
            metrics["r_prec"],
            json.dumps(metrics["pr_curve"]),
            now,
        )
    )

    _update_summary(conn, metrics, 1)
    conn.commit()


def get_metrics_summary(conn: sqlite3.Connection) -> dict:
    row = conn.execute("SELECT * FROM metrics_summary WHERE id = 1").fetchone()
    total = row["total_queries"]

    if total == 0:
        return {
            "total_queries": 0,
            "avg_recall": None,
            "avg_precision": None,
            "avg_avg_prec": None,
            "avg_p5": None,
            "avg_p10": None,
            "avg_r_prec": None,
            "avg_pr_curve": [0.0] * 11,
        }

    curve_sum = json.loads(row["sum_pr_curve"] or "[]")
    if len(curve_sum) != 11:
        curve_sum = [0.0] * 11

    avg_curve = [x / total for x in curve_sum]

    return {
        "total_queries": total,
        "avg_recall": row["sum_recall"] / total,
        "avg_precision": row["sum_precision"] / total,
        "avg_avg_prec": row["sum_avg_prec"] / total,
        "avg_p5": row["sum_p5"] / total,
        "avg_p10": row["sum_p10"] / total,
        "avg_r_prec": row["sum_r_prec"] / total,
        "avg_pr_curve": avg_curve,
    }


def get_metrics_rows(conn: sqlite3.Connection, limit: int, offset: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT
            qm.query_id,
            q.query_text,
            qm.recall,
            qm.precision,
            qm.avg_prec,
            qm.p5,
            qm.p10,
            qm.r_prec,
            qm.created_at
        FROM query_metrics qm
        JOIN queries q ON q.id = qm.query_id
        ORDER BY qm.created_at DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset)
    ).fetchall()

    return [dict(row) for row in rows]


def get_metrics_row_count(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS cnt FROM query_metrics").fetchone()
    return row["cnt"]


def get_pr_curve(conn: sqlite3.Connection, query_id: int) -> list[float]:
    row = conn.execute(
        "SELECT pr_curve FROM query_metrics WHERE query_id = ?",
        (query_id,)
    ).fetchone()

    if not row:
        return []

    return json.loads(row["pr_curve"] or "[]")