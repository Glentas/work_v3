"""Превращает :class:`Dataset` в табличные представления (pandas)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd

from .config import INDICATOR_CRIMES_TOTAL, SITE_URL
from .model import Codelist, Dataset, Fact, GeoNode

log = logging.getLogger("belstat.enrich")

GEO_LEVEL_NAMES = {
    0: "Республика Беларусь",
    1: "Область / г. Минск",
    2: "Район / город областного подчинения",
    3: "Посёлок городского типа / сельсовет",
}

#: Подпись для наблюдений показателя, у которого вообще нет территориального разреза.
NO_GEO_LABEL = "без территориального разреза"

#: Текстовые колонки, в которых пустая строка заменяется на NULL.
_NULLABLE_TEXT_COLUMNS = (
    "geo_code",
    "geo_name_ru",
    "breakdown_key",
    "breakdown_value_ru",
    "obs_attribute",
    "region_name_ru",
    "district_name_ru",
)

#: Колонки основной таблицы наблюдений.
#:
#: Намеренно «нормализовано»: переводы названий (en/be), полные подписи
#: измерений и ссылки на портал не дублируются в каждой строке — они лежат
#: в словарях ``indicators.csv``, ``territories.csv``, ``dimension_values.csv``.
FACT_COLUMNS = [
    "fact_id",
    "indicator_code",
    "indicator_name_ru",
    "time_period",
    "year",
    "geo_code",
    "geo_name_ru",
    "geo_level",
    "geo_level_name",
    "region_code",
    "region_name_ru",
    "district_code",
    "district_name_ru",
    "breakdown_key",
    "breakdown_value_ru",
    "unit_code",
    "unit_name_ru",
    "value",
    "value_raw",
    "obs_attribute",
    "source_window",
    "retrieved_at",
]


def _year_of(period: str) -> Optional[int]:
    if not period:
        return None
    head = period.strip().split("-")[0].split("/")[0]
    try:
        return int(head)
    except ValueError:
        return None


def _breakdown_labels(
    fact: Fact, ds_lookup: Dict[str, Codelist]
) -> tuple[str, str]:
    """Подписи разбивки: полная (``Виды преступлений: кража``) и короткая (``кража``)."""
    if not fact.dims:
        return "", ""
    full: List[str] = []
    short: List[str] = []
    for dim_id, code in sorted(fact.dims.items()):
        cl = ds_lookup.get(f"CL_{dim_id}")
        name = cl.entries[code].name_ru if cl and code in cl.entries else code
        dim_name = cl.name_ru if cl else dim_id
        full.append(f"{dim_name}: {name}" if dim_name else str(name))
        short.append(str(name))
    return " | ".join(full), " / ".join(short)


def facts_to_dataframe(
    dataset: Dataset, *, retrieved_at: Optional[str] = None
) -> pd.DataFrame:
    """Плоская «длинная» таблица наблюдений — ядро датасета."""
    retrieved_at = retrieved_at or datetime.now(timezone.utc).isoformat(timespec="seconds")

    indicators = {i.code: i for i in dataset.indicators}
    geo = dataset.geo

    unit_lookup: Dict[str, str] = {}
    for cl in dataset.codelists.values():
        if cl.id.startswith("CL_unit"):
            for code, entry in cl.entries.items():
                unit_lookup.setdefault(code, entry.name_ru)

    rows: List[Dict[str, Any]] = []
    for f in dataset.facts:
        ind = indicators.get(f.indicator_code)
        node: Optional[GeoNode] = geo.get(f.geo_code)
        _, breakdown_value = _breakdown_labels(f, dataset.codelists)
        rows.append(
            {
                "fact_id": f.fact_id(),
                "indicator_code": f.indicator_code,
                "indicator_name_ru": ind.name_ru if ind else "",
                "time_period": f.time_period,
                "year": _year_of(f.time_period),
                "geo_code": f.geo_code,
                "geo_name_ru": node.name_ru if node else "",
                "geo_level": node.level if node else None,
                "geo_level_name": (
                    GEO_LEVEL_NAMES.get(node.level, f"уровень {node.level}")
                    if node
                    else NO_GEO_LABEL
                ),
                "region_code": node.region_code if node else None,
                "region_name_ru": node.region_name_ru if node else None,
                "district_code": node.district_code if node else None,
                "district_name_ru": node.district_name_ru if node else None,
                "breakdown_key": f.breakdown_key,
                "breakdown_value_ru": breakdown_value,
                "unit_code": f.unit_code,
                "unit_name_ru": unit_lookup.get(f.unit_code or "", ""),
                "value": f.value,
                "value_raw": f.value_raw,
                "obs_attribute": f.obs_attribute,
                "source_window": f.source_window,
                "retrieved_at": retrieved_at,
            }
        )

    df = pd.DataFrame(rows, columns=FACT_COLUMNS)
    if not df.empty:
        # Целочисленные колонки с пропусками → nullable Int64, чтобы в CSV
        # писались «2023» и «0», а не «2023.0» и «0.0».
        for col in ("year", "geo_level"):
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
        # Единая семантика пропусков: NULL = «не применимо», а не пустая строка.
        # Пустые строки остаются только там, где это содержательное значение.
        for col in _NULLABLE_TEXT_COLUMNS:
            if col in df.columns:
                df[col] = df[col].replace("", None)
    if not df.empty:
        df = df.sort_values(
            ["indicator_code", "geo_level", "geo_code", "breakdown_key", "time_period"],
            kind="stable",
        ).reset_index(drop=True)
    return df


def indicators_to_dataframe(dataset: Dataset) -> pd.DataFrame:
    rows = [
        {
            "indicator_code": i.code,
            "name_ru": i.name_ru,
            "name_en": i.name_en,
            "name_be": i.name_be,
            "rubric_code": i.rubric_code,
            "rubric_name": i.rubric_name,
            "periodicities": ", ".join(i.periodicities),
            "year_min": min(i.years_available) if i.years_available else None,
            "year_max": max(i.years_available) if i.years_available else None,
            "n_years_available": len(i.years_available),
            "unit_codes": ", ".join(i.unit_codes),
            "n_facts": sum(1 for f in dataset.facts if f.indicator_code == i.code),
            "portal_page": i.page_url or f"{SITE_URL}/osids/indicator-info/{i.code}",
        }
        for i in dataset.indicators
    ]
    return pd.DataFrame(rows)


def territories_to_dataframe(dataset: Dataset) -> pd.DataFrame:
    rows = [
        {
            "geo_code": n.code,
            "name_ru": n.name_ru,
            "name_en": n.name_en,
            "name_be": n.name_be,
            "level": n.level,
            "level_name": GEO_LEVEL_NAMES.get(n.level, "прочее"),
            "parent_code": n.parent_code,
            "region_code": n.region_code,
            "region_name_ru": n.region_name_ru,
            "district_code": n.district_code,
            "district_name_ru": n.district_name_ru,
            "lat": n.lat,
            "lon": n.lon,
            "n_facts": sum(1 for f in dataset.facts if f.geo_code == n.code),
        }
        for n in dataset.geo.values()
    ]
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["level", "region_name_ru", "name_ru"], kind="stable")
    return df


def dimension_values_to_dataframe(dataset: Dataset) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for cl in dataset.codelists.values():
        for entry in cl.entries.values():
            rows.append(
                {
                    "codelist_id": cl.id,
                    "codelist_name_ru": cl.name_ru,
                    "code": entry.code,
                    "name_ru": entry.name_ru,
                    "name_en": entry.name_en,
                    "name_be": entry.name_be,
                    "parent_code": entry.parent,
                }
            )
    return pd.DataFrame(rows)


def dimensions_to_dataframe(dataset: Dataset) -> pd.DataFrame:
    return pd.DataFrame(dataset.dimensions)


def crime_long_table(
    facts: pd.DataFrame, indicator_code: str = INDICATOR_CRIMES_TOTAL
) -> pd.DataFrame:
    """Курируемая таблица «преступления по районам» в длинном формате.

    Одна строка = год × территория × вид преступления.
    """
    if facts.empty:
        return pd.DataFrame()
    sub = facts[facts["indicator_code"] == indicator_code].copy()
    if sub.empty:
        return sub
    sub = sub.rename(columns={"breakdown_value_ru": "crime_type"})
    cols = [
        "year",
        "time_period",
        "geo_code",
        "geo_name_ru",
        "geo_level",
        "region_code",
        "region_name_ru",
        "district_code",
        "district_name_ru",
        "crime_type",
        "breakdown_key",
        "unit_name_ru",
        "value",
        "retrieved_at",
    ]
    return sub[[c for c in cols if c in sub.columns]].sort_values(
        ["year", "region_name_ru", "geo_name_ru", "crime_type"], kind="stable"
    ).reset_index(drop=True)


def crime_wide_table(
    long_df: pd.DataFrame, value_col: str = "value"
) -> pd.DataFrame:
    """Широкая таблица: строки — год × территория, столбцы — виды преступлений.

    Такой вид удобен для ML и для быстрой выгрузки в GIS/Excel.
    """
    if long_df.empty or "crime_type" not in long_df.columns:
        return pd.DataFrame()
    keys = ["year", "geo_code", "geo_name_ru", "geo_level", "region_name_ru"]
    keys = [k for k in keys if k in long_df.columns]
    wide = long_df.pivot_table(
        index=keys, columns="crime_type", values=value_col, aggfunc="first"
    )
    wide.columns = [str(c) for c in wide.columns]
    return wide.reset_index()


def coverage_matrix(facts: pd.DataFrame) -> pd.DataFrame:
    """Матрица покрытия «показатель × год»: сколько наблюдений собрано."""
    if facts.empty:
        return pd.DataFrame()
    return (
        facts.pivot_table(
            index=["indicator_code", "indicator_name_ru"],
            columns="year",
            values="fact_id",
            aggfunc="count",
            fill_value=0,
        )
        .reset_index()
    )
