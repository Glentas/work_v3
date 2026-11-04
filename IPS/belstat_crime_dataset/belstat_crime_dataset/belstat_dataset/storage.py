"""Сохранение датасета: CSV-файлы и база SQLite."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import pandas as pd

log = logging.getLogger("belstat.storage")


# --------------------------------------------------------------------------- #
#  CSV
# --------------------------------------------------------------------------- #


def write_csv(df: pd.DataFrame, path: Path | str, *, encoding: str = "utf-8-sig") -> Path:
    """Атомарно пишет DataFrame в CSV (utf-8-sig — чтобы Excel читал кириллицу)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    os.close(fd)
    try:
        df.to_csv(tmp, index=False, encoding=encoding)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    try:  # mkstemp создаёт файл с правами 0600 — делаем читаемым для всех
        os.chmod(path, 0o644)
    except OSError:
        pass
    log.info("записано %s (%d строк)", path, len(df))
    return path


def write_csv_files(tables: Dict[str, pd.DataFrame], out_dir: Path | str) -> Dict[str, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: Dict[str, Path] = {}
    for name, df in tables.items():
        written[name] = write_csv(df, out_dir / f"{name}.csv")
    return written


# --------------------------------------------------------------------------- #
#  SQLite
# --------------------------------------------------------------------------- #

_DDL = {
    "meta": """
        CREATE TABLE IF NOT EXISTS meta (
            key   TEXT PRIMARY KEY,
            value TEXT
        )""",
    "indicators": """
        CREATE TABLE IF NOT EXISTS indicators (
            indicator_code      TEXT PRIMARY KEY,
            name_ru             TEXT,
            name_en             TEXT,
            name_be             TEXT,
            rubric_code         TEXT,
            rubric_name         TEXT,
            periodicities       TEXT,
            year_min            INTEGER,
            year_max            INTEGER,
            n_years_available   INTEGER,
            unit_codes          TEXT,
            n_facts             INTEGER,
            portal_page         TEXT
        )""",
    "territories": """
        CREATE TABLE IF NOT EXISTS territories (
            geo_code         TEXT PRIMARY KEY,
            name_ru          TEXT,
            name_en          TEXT,
            name_be          TEXT,
            level            INTEGER,
            level_name       TEXT,
            parent_code      TEXT,
            region_code      TEXT,
            region_name_ru   TEXT,
            district_code    TEXT,
            district_name_ru TEXT,
            lat              REAL,
            lon              REAL,
            n_facts          INTEGER
        )""",
    "dimension_values": """
        CREATE TABLE IF NOT EXISTS dimension_values (
            codelist_id       TEXT,
            codelist_name_ru  TEXT,
            code              TEXT,
            name_ru           TEXT,
            name_en           TEXT,
            name_be           TEXT,
            parent_code       TEXT,
            PRIMARY KEY (codelist_id, code)
        )""",
    "dimensions": """
        CREATE TABLE IF NOT EXISTS dimensions (
            indicator_code TEXT,
            dimension_id   TEXT,
            position       INTEGER,
            name_ru        TEXT,
            name_be        TEXT,
            name_en        TEXT,
            codelist_id    TEXT,
            is_time        INTEGER,
            is_geo         INTEGER,
            is_unit        INTEGER,
            n_codes        INTEGER,
            PRIMARY KEY (indicator_code, dimension_id)
        )""",
    "facts": """
        CREATE TABLE IF NOT EXISTS facts (
            fact_id            TEXT PRIMARY KEY,
            indicator_code     TEXT NOT NULL,
            indicator_name_ru  TEXT,
            time_period        TEXT NOT NULL,
            year               INTEGER,
            geo_code           TEXT,
            geo_name_ru        TEXT,
            geo_level          INTEGER,
            geo_level_name     TEXT,
            region_code        TEXT,
            region_name_ru     TEXT,
            district_code      TEXT,
            district_name_ru   TEXT,
            breakdown_key      TEXT,
            breakdown_value_ru TEXT,
            unit_code          TEXT,
            unit_name_ru       TEXT,
            value              REAL,
            value_raw          TEXT,
            obs_attribute      TEXT,
            source_window      TEXT,
            retrieved_at       TEXT
        )""",
    "errors": """
        CREATE TABLE IF NOT EXISTS errors (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            indicator_code TEXT,
            years          TEXT,
            error          TEXT,
            logged_at      TEXT
        )""",
}

_FACT_INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_facts_indicator ON facts(indicator_code)",
    "CREATE INDEX IF NOT EXISTS ix_facts_geo ON facts(geo_code)",
    "CREATE INDEX IF NOT EXISTS ix_facts_year ON facts(year)",
    "CREATE INDEX IF NOT EXISTS ix_facts_region ON facts(region_code)",
    "CREATE INDEX IF NOT EXISTS ix_facts_district ON facts(district_code)",
    "CREATE INDEX IF NOT EXISTS ix_facts_breakdown ON facts(breakdown_key)",
]


def _sqlite_value(v: Any) -> Any:
    """Приводит значение pandas/numpy к типу, понятному sqlite3."""
    if v is None:
        return None
    if isinstance(v, bool):
        return int(v)
    if hasattr(v, "item") and not isinstance(v, (str, bytes)):  # numpy-скаляр
        try:
            v = v.item()
        except Exception:  # noqa: BLE001
            return str(v)
    if isinstance(v, (list, dict, tuple, set)):
        return json.dumps(v, ensure_ascii=False, default=str)
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


def write_sqlite(
    tables: Dict[str, pd.DataFrame],
    path: Path | str,
    *,
    replace_indicator_codes: Optional[Iterable[str]] = None,
    meta: Optional[Dict[str, Any]] = None,
    errors: Optional[Iterable[Dict[str, Any]]] = None,
) -> Path:
    """Пишет таблицы в SQLite (идемпотентно, через ``INSERT OR REPLACE``).

    Args:
        tables: словарь ``имя_таблицы -> DataFrame``.
        path: путь к файлу БД.
        replace_indicator_codes: если задано, перед вставкой удаляются старые
            строки ``facts`` по этим показателям — так повторный прогон не
            дублирует данные и работает как инкрементальное обновление.
        meta: произвольные пары key/value для таблицы ``meta``.
        errors: список словарей с ошибками сбора.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
        for ddl in _DDL.values():
            con.execute(ddl)

        codes = list(replace_indicator_codes or [])
        if codes and "facts" in tables:
            marks = ",".join("?" * len(codes))
            con.execute(f"DELETE FROM facts WHERE indicator_code IN ({marks})", codes)

        for name, df in tables.items():
            if name not in _DDL or df is None or df.empty:
                continue
            cols = [c for c in df.columns if c in _column_names(con, name)]
            if not cols:
                continue
            placeholders = ",".join("?" * len(cols))
            sql = (
                f"INSERT OR REPLACE INTO {name} ({','.join(cols)}) "
                f"VALUES ({placeholders})"
            )
            payload = [
                tuple(_sqlite_value(row[c]) for c in cols)
                for row in df.to_dict(orient="records")
            ]
            con.executemany(sql, payload)
            log.info("sqlite: %s <- %d строк", name, len(payload))

        for idx in _FACT_INDEXES:
            con.execute(idx)

        if errors:
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            con.executemany(
                "INSERT INTO errors (indicator_code, years, error, logged_at) "
                "VALUES (?,?,?,?)",
                [
                    (
                        e.get("indicator_code"),
                        json.dumps(e.get("years"), ensure_ascii=False)
                        if e.get("years")
                        else None,
                        str(e.get("error"))[:1000],
                        now,
                    )
                    for e in errors
                ],
            )

        meta_payload = dict(meta or {})
        meta_payload.setdefault(
            "updated_at", datetime.now(timezone.utc).isoformat(timespec="seconds")
        )
        con.executemany(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?,?)",
            [(k, json.dumps(v, ensure_ascii=False, default=str)) for k, v in meta_payload.items()],
        )
        con.commit()
    finally:
        con.close()
    log.info("записано %s", path)
    return path


def _column_names(con: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in con.execute(f"PRAGMA table_info({table})")}


def read_sqlite(path: Path | str, query: str) -> pd.DataFrame:
    """Читает произвольный SQL-запрос из собранной базы."""
    con = sqlite3.connect(str(path))
    try:
        return pd.read_sql_query(query, con)
    finally:
        con.close()
