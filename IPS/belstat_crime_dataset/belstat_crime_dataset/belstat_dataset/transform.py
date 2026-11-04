"""Разбор ответов портала: SDMX-структура, SDMX-CSV, территориальная иерархия."""

from __future__ import annotations

import csv
import io
import logging
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .config import GEO_DIMENSION_ID, GEO_ROOT_CODE
from .model import (
    Codelist,
    CodelistEntry,
    DataStructure,
    Dimension,
    Fact,
    GeoNode,
)

log = logging.getLogger("belstat.transform")

#: Значения, которыми портал кодирует «нет данных» / «данные не публикуются».
_MISSING_TOKENS = {
    "", "-", "–", "—", "…", "...", "x", "X", "н/д", "нд", "null", "None", "nan",
}

_NBSP_RE = re.compile(r"[\s\u00a0\u2007\u202f]+")


# --------------------------------------------------------------------------- #
#  SDMX-структура (DSD)
# --------------------------------------------------------------------------- #


def _names(obj: Any) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not isinstance(obj, dict):
        return out
    nm = obj.get("names")
    if isinstance(nm, dict):
        out.update(
            {k: _norm(v) for k, v in nm.items() if isinstance(v, str)}
        )
    if isinstance(obj.get("name"), str) and obj["name"]:
        out.setdefault("ru", _norm(obj["name"]))
    return out


def _norm(s: Any) -> str:
    """Схлопывает пробелы — в подписях Белстата встречаются двойные пробелы."""
    return " ".join(str(s or "").split())


def parse_codelists(dsd_json: Dict[str, Any]) -> Dict[str, Codelist]:
    """Справочники из SDMX-JSON: ``data.codelists``."""
    result: Dict[str, Codelist] = {}
    for cl in ((dsd_json.get("data") or {}).get("codelists") or []):
        nm = _names(cl)
        codelist = Codelist(
            id=cl.get("id", ""),
            name_ru=nm.get("ru", ""),
            name_be=nm.get("be", ""),
            name_en=nm.get("en", ""),
        )
        for code in cl.get("codes") or []:
            cn = _names(code)
            parent = code.get("parent") or None
            codelist.entries[str(code.get("id"))] = CodelistEntry(
                codelist_id=codelist.id,
                code=str(code.get("id")),
                name_ru=cn.get("ru", ""),
                name_be=cn.get("be", ""),
                name_en=cn.get("en", ""),
                parent=(parent if parent not in ("", None) else None),
            )
        result[codelist.id] = codelist
    return result


def parse_datastructure(
    dsd_json: Dict[str, Any], indicator_code: str
) -> DataStructure:
    """Собирает :class:`DataStructure` из SDMX-JSON ответа ``datastructure``."""
    data = dsd_json.get("data") or {}
    codelists = parse_codelists(dsd_json)

    concepts: Dict[str, Dict[str, str]] = {}
    for cs in data.get("conceptSchemes") or []:
        for c in cs.get("concepts") or []:
            concepts[str(c.get("id"))] = _names(c)

    names: Dict[str, str] = {}
    for df in data.get("dataflows") or []:
        if str(df.get("id", "")).startswith(indicator_code):
            names = _names(df)
            break

    ds = DataStructure(indicator_code=indicator_code, names=names, codelists=codelists)

    structures = data.get("dataStructures") or []
    if not structures:
        log.warning("DSD %s: пустой dataStructures", indicator_code)
        return ds

    components = structures[0].get("dataStructureComponents") or {}
    dim_list = components.get("dimensionList") or {}
    measure_list = components.get("measureList") or {}

    raw_dims: List[Dict[str, Any]] = []
    for d in dim_list.get("dimensions") or []:
        raw_dims.append({**d, "_time": False})
    for d in dim_list.get("timeDimensions") or []:
        raw_dims.append({**d, "_time": True})

    def codelist_id_of(dim: Dict[str, Any]) -> Optional[str]:
        """Достаёт id справочника из URN вида
        ``urn:sdmx:...Codelist=BELSTAT:CL_razrez_594(1.0)``."""
        enum = ((dim.get("localRepresentation") or {}).get("enumeration")) or ""
        m = re.search(r"Codelist=([^()]+)\(([^)]*)\)", enum)
        if m:
            return m.group(1).split(":")[-1]
        guess = f"CL_{dim.get('id')}"
        return guess if guess in codelists else None

    for dim in sorted(raw_dims, key=lambda x: (x.get("position") or 0)):
        dim_id = str(dim.get("id"))
        concept = concepts.get(dim_id, {})
        cl_id = codelist_id_of(dim)
        cl = codelists.get(cl_id) if cl_id else None
        is_time = bool(dim.get("_time")) or dim_id.upper() == "TIME_PERIOD"
        is_unit = dim_id.startswith("unit_") or (cl_id or "").startswith("CL_unit")
        is_geo = _looks_like_geo(dim_id, concept, cl)
        ds.dimensions.append(
            Dimension(
                id=dim_id,
                position=int(dim.get("position") or 0),
                concept_name_ru=concept.get("ru", ""),
                concept_name_be=concept.get("be", ""),
                concept_name_en=concept.get("en", ""),
                codelist_id=cl_id,
                is_time=is_time,
                is_geo=is_geo,
                is_unit=is_unit,
            )
        )

    primary = measure_list.get("primaryMeasure") or {}
    ds.measure_id = str(primary.get("id") or "OBS_VALUE")
    return ds


def _looks_like_geo(dim_id: str, concept: Dict[str, str], cl: Optional[Codelist]) -> bool:
    """Определяет территориальное измерение.

    Надёжный признак — наличие в справочнике кода ``699961`` (Республика
    Беларусь). Дополнительно сверяемся с идентификатором и названием концепта.
    """
    if cl is not None and GEO_ROOT_CODE in cl.entries:
        return True
    if dim_id == GEO_DIMENSION_ID:
        return True
    text = " ".join([dim_id, *concept.values()]).lower()
    return "территор" in text or "territory" in text


# --------------------------------------------------------------------------- #
#  Территориальная иерархия
# --------------------------------------------------------------------------- #


def build_geo_index(
    codelist: Optional[Codelist], root_code: str = GEO_ROOT_CODE
) -> Dict[str, GeoNode]:
    """Строит индекс территорий с уровнями и предками.

    Иерархия берётся из поля ``parent`` справочника SDMX:
    ``Республика Беларусь → область / г. Минск → район → посёлок/сельсовет``.
    """
    index: Dict[str, GeoNode] = {}
    if codelist is None:
        return index

    for entry in codelist.entries.values():
        index[entry.code] = GeoNode(
            code=entry.code,
            name_ru=entry.name_ru,
            name_be=entry.name_be,
            name_en=entry.name_en,
            parent_code=entry.parent,
        )

    # Уровень = длина цепочки до корня.
    for code, node in index.items():
        level, cursor, guard = 0, node, 0
        while cursor.parent_code and cursor.parent_code in index and guard < 32:
            level += 1
            cursor = index[cursor.parent_code]
            guard += 1
        node.level = level

    # Пробрасываем область (уровень 1) и район (уровень 2) в каждую запись.
    for node in index.values():
        chain: List[GeoNode] = []
        cursor, guard = node, 0
        while cursor is not None and guard < 32:
            chain.append(cursor)
            cursor = index.get(cursor.parent_code) if cursor.parent_code else None
            guard += 1
        by_level = {n.level: n for n in chain}
        region = by_level.get(1)
        district = by_level.get(2)
        node.region_code = region.code if region else None
        node.region_name_ru = region.name_ru if region else None
        node.district_code = district.code if district else None
        node.district_name_ru = district.name_ru if district else None
    return index


def geo_codes_by_levels(
    index: Dict[str, GeoNode], levels: Sequence[int]
) -> List[str]:
    """Коды территорий заданных уровней (порядок — как в справочнике)."""
    wanted = set(levels)
    return [c for c, n in index.items() if n.level in wanted]


# --------------------------------------------------------------------------- #
#  SDMX-CSV
# --------------------------------------------------------------------------- #


def parse_sdmx_csv(text: str) -> Tuple[List[str], List[List[str]]]:
    """Читает SDMX-CSV портала в ``(заголовок, строки)``."""
    if text.startswith("\ufeff"):
        text = text[1:]
    reader = csv.reader(io.StringIO(text))
    rows = [r for r in reader if any((c or "").strip() for c in r)]
    if not rows:
        return [], []
    return rows[0], rows[1:]


def parse_value(raw: str) -> Tuple[Optional[float], str]:
    """Преобразует строковое значение портала в float.

    Возвращает ``(значение, нормализованная_строка)``. Для «нет данных»
    значение ``None``, но исходный токен сохраняется в ``value_raw``.
    """
    if raw is None:
        return None, ""
    token = _NBSP_RE.sub("", str(raw)).replace(",", ".")
    if token in _MISSING_TOKENS:
        return None, str(raw).strip()
    try:
        return float(token), token
    except ValueError:
        m = re.search(r"-?\d+(?:\.\d+)?", token)
        if m:
            try:
                return float(m.group(0)), m.group(0)
            except ValueError:
                pass
        log.debug("не разобрал значение: %r", raw)
        return None, str(raw).strip()


def rows_to_facts(
    header: Sequence[str],
    rows: Iterable[Sequence[str]],
    ds: DataStructure,
    source_url: str = "",
    source_window: str = "",
) -> List[Fact]:
    """Превращает строки SDMX-CSV в список :class:`Fact`."""
    cols = list(header)
    idx = {name: i for i, name in enumerate(cols)}

    time_col = "TIME_PERIOD" if "TIME_PERIOD" in idx else None
    value_col = "OBS_VALUE" if "OBS_VALUE" in idx else None
    if value_col is None:
        for cand in ("OBS_VALUE", ds.measure_id):
            if cand in idx:
                value_col = cand
                break
    attr_col = "OBS_ATTRIBUTE" if "OBS_ATTRIBUTE" in idx else None

    dim_ids = [d.id for d in ds.dimensions if not d.is_time]
    geo_dim = ds.geo_dimension()
    unit_dim = next((d for d in ds.dimensions if d.is_unit), None)

    facts: List[Fact] = []
    for row in rows:
        if len(row) < len(cols):
            row = list(row) + [""] * (len(cols) - len(row))

        def cell(name: Optional[str]) -> str:
            if name is None or name not in idx:
                return ""
            return (row[idx[name]] or "").strip()

        dims: Dict[str, str] = {}
        for dim_id in dim_ids:
            if dim_id in idx:
                val = cell(dim_id)
                if val:
                    dims[dim_id] = val

        geo_code = dims.pop(geo_dim.id, "") if geo_dim else ""
        unit_code = dims.pop(unit_dim.id, "") if unit_dim else ""

        value, value_norm = parse_value(cell(value_col))
        breakdown_key = ",".join(f"{k}={v}" for k, v in sorted(dims.items()))

        facts.append(
            Fact(
                indicator_code=ds.indicator_code,
                time_period=cell(time_col),
                geo_code=geo_code,
                value=value,
                value_raw=value_norm or cell(value_col),
                unit_code=unit_code or None,
                breakdown_key=breakdown_key,
                dims=dims,
                obs_attribute=cell(attr_col),
                source_url=source_url,
                source_window=source_window,
            )
        )
    return facts


def dedupe_facts(facts: Iterable[Fact]) -> List[Fact]:
    """Убирает дубликаты (окна годов могут пересекаться) — оставляем последний."""
    seen: Dict[str, Fact] = {}
    for f in facts:
        seen[f.natural_key()] = f
    out = list(seen.values())
    out.sort(key=lambda f: (f.indicator_code, f.geo_code, f.breakdown_key, f.time_period))
    return out
