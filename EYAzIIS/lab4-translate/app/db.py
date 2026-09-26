"""Доступ к базе данных SQLite: соединение, транзакции, инициализация схемы."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from . import config

_SCHEMA = Path(__file__).parent / "schema.sql"


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Открывает соединение и гарантированно закрывает его на выходе."""
    config.ensure_dirs()
    conn = sqlite3.connect(
        config.DB_PATH,
        timeout=15,
        isolation_level=None,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 15000")
        yield conn
    finally:
        conn.close()


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Атомарный блок: либо фиксируются все изменения, либо ни одного."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def init_db() -> None:
    """Создаёт таблицы по schema.sql (идемпотентно).

    ``executescript`` сам управляет транзакциями (неявно фиксирует текущую),
    поэтому внешняя транзакция здесь не нужна.
    """
    with connect() as conn:
        conn.executescript(_SCHEMA.read_text(encoding="utf-8"))
