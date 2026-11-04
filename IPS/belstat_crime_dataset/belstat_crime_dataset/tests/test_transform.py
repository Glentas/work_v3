"""Офлайн-тесты разбора SDMX-структуры, SDMX-CSV и территориальной иерархии.

Сеть не нужна: используются фикстуры, повторяющие реальные ответы портала.

    python -m pytest tests -q
    # или без pytest:
    python tests/test_transform.py
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from belstat_dataset.client import BelstatClient  # noqa: E402
from belstat_dataset.enrich import facts_to_dataframe, territories_to_dataframe  # noqa: E402
from belstat_dataset.model import Dataset, Indicator  # noqa: E402
from belstat_dataset.pipeline import select_years, year_windows  # noqa: E402
from belstat_dataset.transform import (  # noqa: E402
    build_geo_index,
    dedupe_facts,
    geo_codes_by_levels,
    parse_datastructure,
    parse_sdmx_csv,
    parse_value,
    rows_to_facts,
)

# --------------------------------------------------------------------------- #
#  Фикстуры (фрагменты реальных ответов dataportal.belstat.gov.by)
# --------------------------------------------------------------------------- #

DSD_JSON = {
    "data": {
        "dataflows": [
            {
                "id": "10108000001_DATA_FLOW",
                "names": {
                    "ru": "Число зарегистрированных  преступлений",
                    "be": "Колькасць зарэгiстраваных злачынстваў",
                    "en": "The number of registered crimes",
                },
            }
        ],
        "conceptSchemes": [
            {
                "concepts": [
                    {"id": "razrez_594", "names": {"ru": "Территория Республики Беларусь", "en": "Territory"}},
                    {"id": "priznak_460", "names": {"ru": "Виды преступлений", "en": "Types of crime"}},
                    {"id": "unit_10108000001", "names": {"ru": "Единицы измерения"}},
                    {"id": "TIME_PERIOD", "names": {"en": "Time period"}},
                ]
            }
        ],
        "codelists": [
            {
                "id": "CL_razrez_594",
                "names": {"ru": "Территория Республики Беларусь"},
                "codes": [
                    {"id": "699961", "names": {"ru": "Республика Беларусь", "en": "Republic of Belarus"}, "parent": ""},
                    {"id": "919067", "names": {"ru": "Брестская область", "en": "Brest region"}, "parent": "699961"},
                    {"id": "919071", "names": {"ru": "г. Минск", "en": "Minsk city"}, "parent": "699961"},
                    {"id": "919075", "names": {"ru": "Барановичский", "en": "Baranovichy district"}, "parent": "919067"},
                    {"id": "984146", "names": {"ru": "гп. Городище"}, "parent": "919075"},
                ],
            },
            {
                "id": "CL_priznak_460",
                "names": {"ru": "Виды преступлений"},
                "codes": [
                    {"id": "517667", "names": {"ru": "Всего по всем  видам преступлений", "en": "Total crimes recorded"}, "parent": ""},
                    {"id": "517692", "names": {"ru": "кража", "en": "Theft"}, "parent": "517667"},
                ],
            },
            {
                "id": "CL_unit_10108000001",
                "names": {"ru": "Единицы измерения"},
                "codes": [{"id": "206", "names": {"ru": "единиц"}, "parent": ""}],
            },
        ],
        "dataStructures": [
            {
                "id": "10108000001_STRUCTURE",
                "dataStructureComponents": {
                    "dimensionList": {
                        "dimensions": [
                            {"id": "razrez_594", "position": 0,
                             "localRepresentation": {"enumeration": "urn:sdmx:org.sdmx.infomodel.codelist.Codelist=BELSTAT:CL_razrez_594(1.0)"}},
                            {"id": "priznak_460", "position": 1,
                             "localRepresentation": {"enumeration": "urn:sdmx:org.sdmx.infomodel.codelist.Codelist=BELSTAT:CL_priznak_460(1.0)"}},
                            {"id": "unit_10108000001", "position": 2,
                             "localRepresentation": {"enumeration": "urn:sdmx:org.sdmx.infomodel.codelist.Codelist=BELSTAT:CL_unit_10108000001(1.0)"}},
                        ],
                        "timeDimensions": [{"id": "TIME_PERIOD", "position": 3}],
                    },
                    "measureList": {"primaryMeasure": {"id": "OBS_VALUE"}},
                },
            }
        ],
    }
}

SDMX_CSV = (
    "DATAFLOW,razrez_594,priznak_460,unit_10108000001,TIME_PERIOD,OBS_VALUE,OBS_ATTRIBUTE\n"
    "BELSTAT:10108000001_DATA_FLOW(1.0),699961,517667,206,2023,85 374.0,\n"
    "BELSTAT:10108000001_DATA_FLOW(1.0),919067,517667,206,2023,10468.0,\n"
    "BELSTAT:10108000001_DATA_FLOW(1.0),919075,517692,206,2024,-,\n"
    "BELSTAT:10108000001_DATA_FLOW(1.0),919071,517692,206,2024,2653.0,\n"
)

VIEW_CFG = {
    "indicatorCode": "10108000001",
    "indicatorStructure": {
        "years": [2025, 2024, 2023, 2022, 2021, 2020, 2019, 2018, 2017, 2016, 2015, 2014],
        "units": {"code": "unit", "nodes": [{"code": "206", "name": "единиц"}]},
        "dimensions": [
            {"code": "razrez_594", "name": "Территория Республики Беларусь", "nodes": []},
            {"code": "priznak_460", "name": "Виды преступлений", "nodes": []},
        ],
    },
    "valuesFilter": {
        "years": [2025, 2024, 2023, 2022, 2021],
        "periodicities": [],
        "units": ["206"],
        "dimensionOrder": ["razrez_594", "priznak_460"],
        "dimensionParams": {"priznak_460": [], "razrez_594": ["699961"]},
        "simbolsAfterComma": None,
    },
}


# --------------------------------------------------------------------------- #


class TestDataStructure(unittest.TestCase):
    def setUp(self) -> None:
        self.dsd = parse_datastructure(DSD_JSON, "10108000001")

    def test_codelist_id_from_urn_with_version(self):
        """URN содержит версию в скобках — парсер не должен её проглатывать."""
        dim = next(d for d in self.dsd.dimensions if d.id == "razrez_594")
        self.assertEqual(dim.codelist_id, "CL_razrez_594")
        self.assertIsNotNone(self.dsd.codelist_for("razrez_594"))

    def test_dimension_roles(self):
        geo = self.dsd.geo_dimension()
        self.assertIsNotNone(geo)
        self.assertEqual(geo.id, "razrez_594")
        self.assertEqual([d.id for d in self.dsd.value_dimensions()], ["priznak_460"])
        unit = next(d for d in self.dsd.dimensions if d.is_unit)
        self.assertEqual(unit.id, "unit_10108000001")
        time_dim = next(d for d in self.dsd.dimensions if d.is_time)
        self.assertEqual(time_dim.id, "TIME_PERIOD")

    def test_trilingual_names_and_whitespace_normalisation(self):
        self.assertEqual(self.dsd.names["ru"], "Число зарегистрированных преступлений")
        cl = self.dsd.codelist_for("priznak_460")
        self.assertEqual(cl.entries["517667"].name_ru, "Всего по всем видам преступлений")
        self.assertEqual(cl.entries["517667"].name_en, "Total crimes recorded")


class TestGeoHierarchy(unittest.TestCase):
    def setUp(self) -> None:
        dsd = parse_datastructure(DSD_JSON, "10108000001")
        self.index = build_geo_index(dsd.codelist_for("razrez_594"))

    def test_levels(self):
        self.assertEqual(self.index["699961"].level, 0)
        self.assertEqual(self.index["919067"].level, 1)
        self.assertEqual(self.index["919075"].level, 2)
        self.assertEqual(self.index["984146"].level, 3)

    def test_region_and_district_propagation(self):
        node = self.index["984146"]
        self.assertEqual(node.region_code, "919067")
        self.assertEqual(node.region_name_ru, "Брестская область")
        self.assertEqual(node.district_code, "919075")
        self.assertEqual(node.district_name_ru, "Барановичский")
        self.assertIsNone(self.index["699961"].region_code)

    def test_select_by_levels(self):
        codes = geo_codes_by_levels(self.index, [0, 1])
        self.assertEqual(sorted(codes), ["699961", "919067", "919071"])


class TestValues(unittest.TestCase):
    def test_number_and_missing_parsing(self):
        self.assertEqual(parse_value("85 374.0"), (85374.0, "85374.0"))
        self.assertEqual(parse_value("1\u00a0234,5"), (1234.5, "1234.5"))
        self.assertEqual(parse_value("-"), (None, "-"))
        self.assertEqual(parse_value("…"), (None, "…"))
        self.assertEqual(parse_value(""), (None, ""))

    def test_sdmx_csv_to_facts(self):
        dsd = parse_datastructure(DSD_JSON, "10108000001")
        header, rows = parse_sdmx_csv(SDMX_CSV)
        facts = rows_to_facts(header, rows, dsd, source_url="http://x", source_window="2023-2024")
        self.assertEqual(len(facts), 4)

        by_key = {f.natural_key(): f for f in facts}
        total = by_key["10108000001|2023|699961|priznak_460=517667"]
        self.assertEqual(total.value, 85374.0)
        self.assertEqual(total.unit_code, "206")
        self.assertEqual(total.source_window, "2023-2024")

        missing = [f for f in facts if f.geo_code == "919075"][0]
        self.assertIsNone(missing.value)
        self.assertEqual(missing.value_raw, "-")

    def test_deduplication(self):
        dsd = parse_datastructure(DSD_JSON, "10108000001")
        header, rows = parse_sdmx_csv(SDMX_CSV)
        facts = rows_to_facts(header, rows, dsd) * 3
        self.assertEqual(len(dedupe_facts(facts)), 4)


class TestValuesFilter(unittest.TestCase):
    def test_years_and_geo_substitution(self):
        vf = BelstatClient.build_values_filter(
            VIEW_CFG, years=[2020, 2021], geo_codes=["699961", "919067"]
        )
        self.assertEqual(vf["years"], [2020, 2021])
        self.assertEqual(vf["dimensionParams"]["razrez_594"], ["699961", "919067"])
        self.assertEqual(vf["dimensionParams"]["priznak_460"], [])  # пусто = все значения
        self.assertEqual(vf["units"], ["206"])
        self.assertEqual(vf["dimensionOrder"], ["razrez_594", "priznak_460"])

    def test_dimension_override(self):
        vf = BelstatClient.build_values_filter(
            VIEW_CFG, years=[2024], dimension_overrides={"priznak_460": ["517692"]}
        )
        self.assertEqual(vf["dimensionParams"]["priznak_460"], ["517692"])


class TestYearWindows(unittest.TestCase):
    def test_ten_year_windows(self):
        self.assertEqual(year_windows(list(range(1990, 2026)), 10),
                         [list(range(1990, 2000)), list(range(2000, 2010)),
                          list(range(2010, 2020)), list(range(2020, 2026))])

    def test_empty(self):
        self.assertEqual(year_windows([], 10), [])

    def test_year_range_selection(self):
        self.assertEqual(select_years([1990, 2005, 2025], 2000, 2020), [2005])
        self.assertEqual(select_years([1990, 2005, 2025], None, None), [1990, 2005, 2025])


class TestEnrich(unittest.TestCase):
    def test_dataframe_with_hierarchy(self):
        dsd = parse_datastructure(DSD_JSON, "10108000001")
        header, rows = parse_sdmx_csv(SDMX_CSV)
        facts = rows_to_facts(header, rows, dsd)
        geo = build_geo_index(dsd.codelist_for("razrez_594"))
        ds = Dataset(
            facts=dedupe_facts(facts),
            indicators=[
                Indicator(
                    code="10108000001",
                    name_ru=dsd.names.get("ru", ""),
                    name_en=dsd.names.get("en", ""),
                    name_be=dsd.names.get("be", ""),
                )
            ],
            geo=geo,
            codelists=dsd.codelists,
        )
        df = facts_to_dataframe(ds, retrieved_at="2026-01-01T00:00:00+00:00")
        self.assertEqual(len(df), 4)
        row = df[df["geo_code"] == "919067"].iloc[0]
        self.assertEqual(row["region_name_ru"], "Брестская область")
        self.assertEqual(row["geo_level"], 1)
        self.assertEqual(row["indicator_name_ru"], "Число зарегистрированных преступлений")
        self.assertEqual(row["unit_name_ru"], "единиц")
        self.assertEqual(row["breakdown_value_ru"], "Всего по всем видам преступлений")
        # Переводы живут в словарях, а не в каждой строке фактов.
        terr = territories_to_dataframe(ds)
        self.assertEqual(
            terr.loc[terr["geo_code"] == "919067", "name_en"].iloc[0], "Brest region"
        )
        self.assertEqual(str(df["geo_level"].dtype), "Int64")


if __name__ == "__main__":
    unittest.main(verbosity=2)
