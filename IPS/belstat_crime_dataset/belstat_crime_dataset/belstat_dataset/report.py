"""Контроль качества и краткая аналитика собранного датасета."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from .config import INDICATOR_CRIMES_TOTAL
from .enrich import NO_GEO_LABEL
from .storage import write_csv

log = logging.getLogger("belstat.report")


def coverage_report(facts: pd.DataFrame) -> pd.DataFrame:
    """По каждому показателю: годы, число наблюдений, покрытие территорий."""
    if facts.empty:
        return pd.DataFrame()
    g = facts.groupby(["indicator_code", "indicator_name_ru"], dropna=False)
    out = g.agg(
        n_facts=("fact_id", "count"),
        year_min=("year", "min"),
        year_max=("year", "max"),
        n_years=("year", "nunique"),
        n_geo=("geo_code", "nunique"),
        n_breakdowns=("breakdown_key", "nunique"),
        n_missing_values=("value", lambda s: int(s.isna().sum())),
    ).reset_index()
    return out


def consistency_check(
    facts: pd.DataFrame,
    indicator_code: str = INDICATOR_CRIMES_TOTAL,
    tolerance: float = 0.02,
) -> pd.DataFrame:
    """Сверяет сумму областей с итогом по стране (внутренняя непротиворечивость).

    Для показателя «Число зарегистрированных преступлений» сумма шести областей
    и г. Минска должна совпадать со значением по Республике Беларусь.
    Расхождение больше ``tolerance`` помечается флагом.
    """
    if facts.empty:
        return pd.DataFrame()
    sub = facts[
        (facts["indicator_code"] == indicator_code)
        & (facts["breakdown_key"].astype(str).str.contains("517667"))
    ]
    if sub.empty:
        return pd.DataFrame()

    country = (
        sub[sub["geo_level"] == 0]
        .groupby("year", as_index=False)["value"]
        .sum()
        .rename(columns={"value": "country_value"})
    )
    regions = (
        sub[sub["geo_level"] == 1]
        .groupby("year", as_index=False)["value"]
        .sum()
        .rename(columns={"value": "regions_sum"})
    )
    merged = country.merge(regions, on="year", how="outer")
    merged["diff"] = merged["regions_sum"] - merged["country_value"]
    merged["diff_pct"] = (
        merged["diff"] / merged["country_value"].replace(0, pd.NA) * 100
    ).astype(float)
    merged["ok"] = merged["diff_pct"].abs() <= tolerance * 100
    return merged.sort_values("year").reset_index(drop=True)


def top_districts(
    facts: pd.DataFrame,
    indicator_code: str = INDICATOR_CRIMES_TOTAL,
    year: Optional[int] = None,
    n: int = 15,
) -> pd.DataFrame:
    """Топ территорий уровня «район» по значению показателя за год."""
    if facts.empty:
        return pd.DataFrame()
    sub = facts[
        (facts["indicator_code"] == indicator_code) & (facts["geo_level"] == 2)
    ]
    if sub.empty:
        return pd.DataFrame()
    y = year if year is not None else int(sub["year"].max())
    sub = sub[sub["year"] == y]
    if "breakdown_key" in sub.columns:
        total = sub[sub["breakdown_key"].astype(str).str.contains("517667")]
        if not total.empty:
            sub = total
    out = (
        sub.groupby(["geo_code", "geo_name_ru", "region_name_ru"], dropna=False)["value"]
        .sum()
        .sort_values(ascending=False)
        .head(n)
        .reset_index()
    )
    out.insert(0, "year", y)
    return out


def national_series(
    facts: pd.DataFrame, indicator_code: str = INDICATOR_CRIMES_TOTAL
) -> pd.DataFrame:
    """Динамика по стране (все виды преступлений)."""
    if facts.empty:
        return pd.DataFrame()
    sub = facts[
        (facts["indicator_code"] == indicator_code)
        & (facts["geo_level"] == 0)
        & (facts["breakdown_key"].astype(str).str.contains("517667"))
    ]
    if sub.empty:
        return pd.DataFrame()
    return (
        sub[["year", "value"]]
        .dropna()
        .sort_values("year")
        .reset_index(drop=True)
    )


def _df_to_md(df: pd.DataFrame, max_rows: int = 60) -> str:
    """Простая markdown-таблица (без зависимости от tabulate)."""
    if df.empty:
        return "_(нет данных)_"
    view = df.head(max_rows).copy()
    cols = [str(c) for c in view.columns]

    def fmt(v) -> str:
        if v is None:
            return ""
        if isinstance(v, float):
            if pd.isna(v):
                return ""
            return f"{v:,.2f}".rstrip("0").rstrip(".") if abs(v) < 1e15 else str(v)
        try:
            if pd.isna(v):
                return ""
        except (TypeError, ValueError):
            pass
        return str(v).replace("|", "\\|").replace("\n", " ")

    head = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join("---" for _ in cols) + " |"
    body = ["| " + " | ".join(fmt(v) for v in row) + " |" for row in view.itertuples(index=False)]
    if len(df) > max_rows:
        body.append(f"| … ещё {len(df) - max_rows} строк | |")
    return "\n".join([head, sep, *body])


def render_markdown(
    stats: Dict,
    facts: pd.DataFrame,
    coverage: pd.DataFrame,
    consistency: pd.DataFrame,
    tops: pd.DataFrame,
    series: pd.DataFrame,
    tolerance_note: str = "2%",
) -> str:
    lines: List[str] = []
    lines.append("# Отчёт о сборе датасета (Белстат, официальная статистика правонарушений)")
    lines.append("")
    lines.append("## Параметры прогона")
    lines.append("")
    for k, v in stats.items():
        if k == "per_indicator":
            continue
        lines.append(f"- **{k}**: {v}")
    lines.append("")

    if not facts.empty:
        lines.append("## Общие сведения")
        lines.append("")
        lines.append(f"- Наблюдений: **{len(facts):,}**".replace(",", " "))
        lines.append(f"- Показателей: **{facts['indicator_code'].nunique()}**")
        geo_codes = facts["geo_code"].dropna().astype(str)
        geo_codes = geo_codes[geo_codes != ""]
        lines.append(f"- Территорий с данными: **{geo_codes.nunique()}**")
        no_geo = int((facts["geo_level_name"] == NO_GEO_LABEL).sum())
        if no_geo:
            lines.append(
                f"- Наблюдений без территориального разреза: **{no_geo}** "
                "(показатели публикуются только в целом по стране)"
            )
        years = sorted(facts["year"].dropna().unique().tolist())
        if years:
            lines.append(f"- Период: **{years[0]}–{years[-1]}** ({len(years)} лет)")
        lines.append(
            "- Уровни разреза: "
            + ", ".join(
                f"{lvl} ({cnt})"
                for lvl, cnt in facts["geo_level_name"].value_counts().items()
            )
        )
        lines.append("")

    if not coverage.empty:
        lines.append("## Покрытие по показателям")
        lines.append("")
        lines.append(_df_to_md(coverage))
        lines.append("")

    if not series.empty:
        lines.append("## Динамика зарегистрированных преступлений по стране")
        lines.append("")
        lines.append(_df_to_md(series))
        lines.append("")

    if not consistency.empty:
        bad = consistency[~consistency["ok"]]
        lines.append("## Контроль: сумма областей vs итог по стране")
        lines.append("")
        if bad.empty:
            lines.append("Расхождений нет — данные внутренне непротиворечивы.")
        else:
            lines.append(
                f"Годы с расхождением больше {tolerance_note}: **{len(bad)}**"
            )
            lines.append("")
            lines.append(_df_to_md(bad))
            lines.append("")
            lines.append(
                "> Расхождение суммы областей и итога по стране — особенность "
                "первоисточника: часть зарегистрированных преступлений "
                "(например, по объектам транспорта и воинским формированиям) "
                "не распределяется по областям. Это не ошибка сбора."
            )
        lines.append("")

    if not tops.empty:
        lines.append("## Топ территорий (районный уровень)")
        lines.append("")
        lines.append(_df_to_md(tops))
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "Источник: портал открытых данных Белстата "
        "(https://dataportal.belstat.gov.by). Данные официальной статистики, "
        "агрегированы по районам и городам областного подчинения."
    )
    return "\n".join(lines) + "\n"


def build_report(
    dataset_stats: Dict,
    facts: pd.DataFrame,
    out_dir: Path | str,
    *,
    indicator_code: str = INDICATOR_CRIMES_TOTAL,
) -> Path:
    """Готовит отчёт и служебные таблицы контроля качества."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    coverage = coverage_report(facts)
    consistency = consistency_check(facts, indicator_code)
    tops = top_districts(facts, indicator_code)
    series = national_series(facts, indicator_code)

    write_csv(coverage, out_dir / "qa_coverage.csv")
    write_csv(consistency, out_dir / "qa_consistency.csv")
    write_csv(tops, out_dir / "qa_top_districts.csv")
    write_csv(series, out_dir / "qa_national_series.csv")

    md = render_markdown(dataset_stats, facts, coverage, consistency, tops, series)
    report_path = out_dir / "REPORT.md"
    report_path.write_text(md, "utf-8")
    log.info("отчёт: %s", report_path)
    return report_path
