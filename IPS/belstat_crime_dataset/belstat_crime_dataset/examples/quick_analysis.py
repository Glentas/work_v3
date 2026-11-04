#!/usr/bin/env python3
"""Пример работы с собранным датасетом.

Читает SQLite (или CSV), который оставил после себя
``python -m belstat_dataset collect``, и показывает несколько типовых
срезов: динамику по стране, рейтинг районов, долю краж, pivot-таблицу.

    python examples/quick_analysis.py --db data/belstat_crime.sqlite
    python examples/quick_analysis.py --csv data/facts.csv --year 2025
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from belstat_dataset.config import INDICATOR_CRIMES_TOTAL  # noqa: E402

pd.set_option("display.width", 160)
pd.set_option("display.max_columns", 40)
pd.set_option("display.float_format", lambda v: f"{v:,.1f}")


def load_facts(db: str | None, csv: str | None) -> pd.DataFrame:
    if db:
        con = sqlite3.connect(db)
        try:
            return pd.read_sql_query("SELECT * FROM facts", con)
        finally:
            con.close()
    path = Path(csv or "data/facts.csv")
    return pd.read_csv(path, dtype={"geo_code": str, "indicator_code": str})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=None, help="путь к SQLite-базе")
    ap.add_argument("--csv", default=None, help="или путь к facts.csv")
    ap.add_argument("--indicator", default=INDICATOR_CRIMES_TOTAL, help="код показателя")
    ap.add_argument("--year", type=int, default=None, help="год для среза (по умолчанию последний)")
    ap.add_argument("--top", type=int, default=15)
    args = ap.parse_args()

    if not args.db and not args.csv:
        args.db = "data/belstat_crime.sqlite"
    df = load_facts(args.db, args.csv)
    if df.empty:
        print("Датасет пуст. Сначала выполните: python -m belstat_dataset collect")
        return 1

    print("=" * 78)
    print(f"Всего наблюдений: {len(df):,}".replace(",", " "))
    geo = df["geo_code"].fillna("").astype(str)
    print(f"Показателей: {df['indicator_code'].nunique()}, "
          f"территорий: {geo[geo != ''].nunique()}, "
          f"годы: {int(df['year'].min())}–{int(df['year'].max())}")
    print("=" * 78)

    crimes = df[(df["indicator_code"] == args.indicator)].copy()
    if crimes.empty:
        print(f"Показатель {args.indicator} в датасете не найден.")
        return 1
    total = crimes[crimes["breakdown_key"].astype(str).str.contains("517667")]
    year = args.year or int(total["year"].max())

    print("\n1. Динамика зарегистрированных преступлений, Республика Беларусь")
    country = (
        total[total["geo_level"] == 0][["year", "value"]]
        .dropna().sort_values("year")
    )
    country["к предыдущему году, %"] = country["value"].pct_change() * 100
    print(country.tail(12).to_string(index=False))

    print(f"\n2. Топ-{args.top} районов и городов областного подчинения за {year} г.")
    districts = total[(total["geo_level"] == 2) & (total["year"] == year)]
    top = (
        districts.groupby(["region_name_ru", "geo_name_ru"], dropna=False)["value"]
        .sum().sort_values(ascending=False).head(args.top).reset_index()
    )
    top.index = top.index + 1
    print(top.to_string(index=False))

    print(f"\n3. Структура преступности по видам, {year} г. (в целом по стране)")
    by_type = (
        crimes[(crimes["geo_level"] == 0) & (crimes["year"] == year)]
        .groupby("breakdown_value_ru", dropna=False)["value"]
        .sum().sort_values(ascending=False)
    )
    all_crimes = by_type.get("Всего по всем видам преступлений")
    if all_crimes:
        by_type = by_type.drop(index="Всего по всем видам преступлений", errors="ignore")
        by_type = by_type[~by_type.index.str.startswith("из них")]
        share = (by_type / all_crimes * 100).round(2)
        out = pd.DataFrame({"число": by_type, "доля, %": share})
        print(out.to_string())
        print(f"\nВсего зарегистрировано: {all_crimes:,.0f}")

    print(f"\n4. Сравнение областей за {year} г.")
    regions = (
        total[(total["geo_level"] == 1) & (total["year"] == year)]
        .groupby("geo_name_ru", dropna=False)["value"].sum().sort_values(ascending=False)
    )
    print(regions.to_string())

    print("\n5. Матрица «территория × вид преступления» за год (областной уровень)")
    pivot = (
        crimes[(crimes["geo_level"] == 1) & (crimes["year"] == year)]
        .pivot_table(index="geo_name_ru", columns="breakdown_value_ru",
                     values="value", aggfunc="first")
    )
    pivot = pivot[[c for c in pivot.columns if not c.startswith("из них")]]
    print(pivot.iloc[:, :7].to_string())
    print(f"\n(полная матрица: {pivot.shape[0]} строк × {pivot.shape[1]} столбцов)")
    print("\nNB: разбивка по видам преступлений публикуется только по областям и")
    print("    г. Минску; по районам доступен лишь итог «всего видов преступлений».")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
