"""Модели данных: показатели, справочники, территории, факты, итоговый датасет."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Indicator:
    """Статистический показатель портала."""

    code: str
    name_ru: str = ""
    name_be: str = ""
    name_en: str = ""
    rubric_code: Optional[str] = None
    rubric_name: Optional[str] = None
    periodicities: List[str] = field(default_factory=list)
    years_available: List[int] = field(default_factory=list)
    unit_codes: List[str] = field(default_factory=list)
    page_url: str = ""
    api_info: Dict[str, Any] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.name_ru or self.name_en or self.code


@dataclass
class CodelistEntry:
    """Значение справочника измерения (код + подписи на трёх языках + родитель)."""

    codelist_id: str
    code: str
    name_ru: str = ""
    name_be: str = ""
    name_en: str = ""
    parent: Optional[str] = None

    @property
    def name(self) -> str:
        return self.name_ru or self.name_en or self.code


@dataclass
class Codelist:
    """Справочник измерения (SDMX Codelist)."""

    id: str
    name_ru: str = ""
    name_be: str = ""
    name_en: str = ""
    entries: Dict[str, CodelistEntry] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.name_ru or self.name_en or self.id

    def codes(self) -> List[str]:
        return list(self.entries.keys())


@dataclass
class Dimension:
    """Измерение структуры данных показателя (SDMX Dimension)."""

    id: str
    position: int
    concept_name_ru: str = ""
    concept_name_be: str = ""
    concept_name_en: str = ""
    codelist_id: Optional[str] = None
    is_time: bool = False
    is_geo: bool = False
    is_unit: bool = False

    @property
    def name(self) -> str:
        return self.concept_name_ru or self.concept_name_en or self.id


@dataclass
class DataStructure:
    """Разобранная SDMX-структура показателя."""

    indicator_code: str
    names: Dict[str, str] = field(default_factory=dict)
    dimensions: List[Dimension] = field(default_factory=list)
    codelists: Dict[str, Codelist] = field(default_factory=dict)
    measure_id: str = "OBS_VALUE"

    def geo_dimension(self) -> Optional[Dimension]:
        for d in self.dimensions:
            if d.is_geo:
                return d
        return None

    def value_dimensions(self) -> List[Dimension]:
        """Измерения, которые дают содержательную разбивку (не гео, не единицы, не время)."""
        return [d for d in self.dimensions if not (d.is_geo or d.is_unit or d.is_time)]

    def codelist_for(self, dim_id: str) -> Optional[Codelist]:
        dim = next((d for d in self.dimensions if d.id == dim_id), None)
        if dim is None or not dim.codelist_id:
            return None
        return self.codelists.get(dim.codelist_id)


@dataclass
class GeoNode:
    """Территориальная единица с положением в иерархии."""

    code: str
    name_ru: str = ""
    name_be: str = ""
    name_en: str = ""
    level: int = 0  # 0=РБ, 1=область/г.Минск, 2=район, 3=посёлок/сельсовет...
    parent_code: Optional[str] = None
    region_code: Optional[str] = None  # уровень 1
    region_name_ru: Optional[str] = None
    district_code: Optional[str] = None  # уровень 2
    district_name_ru: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None

    @property
    def name(self) -> str:
        return self.name_ru or self.name_en or self.code


@dataclass
class Fact:
    """Одно наблюдение: показатель × год × территория × разбивка."""

    indicator_code: str
    time_period: str
    geo_code: str
    value: Optional[float]
    value_raw: str = ""
    unit_code: Optional[str] = None
    breakdown_key: str = ""  # ``"priznak_460=517667"`` или ``""``
    dims: Dict[str, str] = field(default_factory=dict)
    obs_attribute: str = ""
    source_url: str = ""
    source_window: str = ""  # окно годов, из которого пришло наблюдение

    def natural_key(self) -> str:
        parts = [self.indicator_code, self.time_period, self.geo_code or "-"]
        parts.extend(f"{k}={v}" for k, v in sorted(self.dims.items()))
        return "|".join(parts)

    def fact_id(self) -> str:
        import hashlib

        return hashlib.sha1(self.natural_key().encode("utf-8")).hexdigest()[:32]


@dataclass
class Dataset:
    """Результат работы пайплайна."""

    facts: List[Fact] = field(default_factory=list)
    indicators: List[Indicator] = field(default_factory=list)
    geo: Dict[str, GeoNode] = field(default_factory=dict)
    codelists: Dict[str, Codelist] = field(default_factory=dict)
    dimensions: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)

    def __len__(self) -> int:  # pragma: no cover - удобства ради
        return len(self.facts)
