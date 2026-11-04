"""Пайплайн сбора: каталог показателей → DSD → окна годов → SDMX-CSV → факты."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from .client import BelstatAPIError, BelstatClient, BelstatHTTPError
from .config import (
    API_ROOT,
    GEO_DIMENSION_ID,
    MAX_YEARS_PER_REQUEST,
    SITE_URL,
    PipelineConfig,
)
from .model import Codelist, Dataset, GeoNode, Indicator
from .transform import (
    build_geo_index,
    dedupe_facts,
    geo_codes_by_levels,
    parse_datastructure,
    parse_sdmx_csv,
    rows_to_facts,
)

log = logging.getLogger("belstat.pipeline")

ProgressFn = Optional[Callable[[str, int, int], None]]


# --------------------------------------------------------------------------- #
#  Отбор показателей
# --------------------------------------------------------------------------- #


def resolve_indicators(
    client: BelstatClient, config: PipelineConfig
) -> List[Indicator]:
    """Определяет список показателей для сбора.

    Приоритет: явные ``indicator_codes`` → рубрики → фильтр по названию.
    """
    found: Dict[str, Indicator] = {}

    for code in config.indicator_codes or []:
        found[str(code)] = Indicator(code=str(code))

    rubric_names: Dict[str, str] = {}
    for rubric in config.rubrics or []:
        try:
            node = client.rubric_tree_node(str(rubric)).get("item") or {}
            rubric_names[str(rubric)] = node.get("name") or ""
        except (BelstatHTTPError, BelstatAPIError) as exc:
            log.warning("не удалось прочитать рубрику %s: %s", rubric, exc)

        try:
            items = client.rubric_indicators(str(rubric))
        except (BelstatHTTPError, BelstatAPIError) as exc:
            log.error("рубрика %s недоступна: %s", rubric, exc)
            continue
        log.info(
            "рубрика %s «%s»: %d показателей",
            rubric,
            rubric_names.get(str(rubric), ""),
            len(items),
        )
        for it in items:
            code = str(it.get("code"))
            ind = found.get(code) or Indicator(code=code)
            ind.name_ru = " ".join(str(it.get("name") or "").split())
            ind.periodicities = list(it.get("periodicities") or [])
            ind.rubric_code = str(rubric)
            ind.rubric_name = rubric_names.get(str(rubric), "")
            ind.page_url = f"{SITE_URL}/osids/indicator-info/{code}"
            found[code] = ind

    if config.name_filter:
        needles = [s.lower() for s in config.name_filter]
        catalog = client.indicator_search()
        log.info("каталог портала: %d показателей", len(catalog))
        for it in catalog:
            name = " ".join(str(it.get("name") or "").split())
            if any(n in name.lower() for n in needles):
                code = str(it.get("code"))
                if code in found:
                    continue
                ind = Indicator(code=code)
                ind.name_ru = name
                ind.periodicities = list(it.get("periodicities") or [])
                ind.page_url = f"{SITE_URL}/osids/indicator-info/{code}"
                found[code] = ind

    for code in config.extra_indicators or []:
        found.setdefault(str(code), Indicator(code=str(code)))

    return [found[c] for c in sorted(found)]


# --------------------------------------------------------------------------- #
#  Планирование запросов
# --------------------------------------------------------------------------- #


def year_windows(
    years: Sequence[int], max_size: int = MAX_YEARS_PER_REQUEST
) -> List[List[int]]:
    """Режет список лет на окна не больше ``max_size`` (ограничение портала)."""
    ys = sorted({int(y) for y in years})
    size = max(1, int(max_size))
    return [ys[i : i + size] for i in range(0, len(ys), size)]


def select_years(
    available: Sequence[int], year_from: Optional[int], year_to: Optional[int]
) -> List[int]:
    ys = sorted({int(y) for y in available})
    if year_from is not None:
        ys = [y for y in ys if y >= int(year_from)]
    if year_to is not None:
        ys = [y for y in ys if y <= int(year_to)]
    return ys


def available_years(view_cfg: Dict[str, Any]) -> List[int]:
    structure = view_cfg.get("indicatorStructure") or {}
    out: List[int] = []
    for y in structure.get("years") or []:
        try:
            out.append(int(y))
        except (TypeError, ValueError):
            continue
    return sorted(set(out))


def dimension_batches(
    codelist: Optional[Codelist], batch_size: int
) -> List[Optional[List[str]]]:
    """Батчи кодов измерения. ``[None]`` означает «не ограничивать» (все значения)."""
    if not batch_size or batch_size <= 0 or codelist is None:
        return [None]
    codes = codelist.codes()
    if len(codes) <= batch_size:
        return [None]
    return [codes[i : i + batch_size] for i in range(0, len(codes), batch_size)]


# --------------------------------------------------------------------------- #
#  Сбор
# --------------------------------------------------------------------------- #


def _geo_index_from(
    dsd, view_cfg: Dict[str, Any]
) -> Dict[str, GeoNode]:
    """Индекс территорий: сначала из SDMX-справочника, запасной вариант — из дерева UI."""
    geo_dim = dsd.geo_dimension()
    if geo_dim is not None:
        index = build_geo_index(dsd.codelist_for(geo_dim.id))
        if index:
            return index

    structure = view_cfg.get("indicatorStructure") or {}
    for dim in structure.get("dimensions") or []:
        if dim.get("code") != GEO_DIMENSION_ID:
            continue
        index = {}

        def walk(nodes: Iterable[Dict[str, Any]], parent: Optional[str], level: int) -> None:
            for n in nodes or []:
                code = str(n.get("code"))
                node = GeoNode(
                    code=code,
                    name_ru=" ".join(str(n.get("name") or "").split()),
                    level=level,
                    parent_code=parent,
                )
                index[code] = node
                walk(n.get("childrens") or [], code, level + 1)

        walk(dim.get("nodes") or [], None, 0)
        for node in index.values():
            chain, cursor, guard = [], node, 0
            while cursor is not None and guard < 32:
                chain.append(cursor)
                cursor = index.get(cursor.parent_code) if cursor.parent_code else None
                guard += 1
            by_level = {n.level: n for n in chain}
            node.region_code = by_level[1].code if 1 in by_level else None
            node.region_name_ru = by_level[1].name_ru if 1 in by_level else None
            node.district_code = by_level[2].code if 2 in by_level else None
            node.district_name_ru = by_level[2].name_ru if 2 in by_level else None
        return index
    return {}


def collect_indicator(
    client: BelstatClient, indicator: Indicator, config: PipelineConfig
) -> Tuple[Dataset, Dict[str, Any]]:
    """Собирает один показатель. Возвращает частичный датасет и служебную статистику."""
    code = indicator.code
    part = Dataset()
    info: Dict[str, Any] = {"code": code, "requests": 0, "rows": 0}

    view_cfg = client.indicator_view_cfg(code)
    dsd_json = client.datastructure_json(code)
    dsd = parse_datastructure(dsd_json, code)
    info["requests"] += 2

    indicator.name_ru = dsd.names.get("ru") or indicator.name_ru
    indicator.name_be = dsd.names.get("be", "")
    indicator.name_en = dsd.names.get("en", "")

    years = select_years(available_years(view_cfg), config.year_from, config.year_to)
    indicator.years_available = available_years(view_cfg)
    if not years:
        log.warning("%s: нет годов в выбранном диапазоне", code)
        return part, info

    geo_index = _geo_index_from(dsd, view_cfg)
    geo_dim = dsd.geo_dimension()
    if geo_index and geo_dim is not None:
        wanted = geo_codes_by_levels(geo_index, config.geo_levels)
        # Оставляем только те коды, которые реально есть в структуре показателя.
        allowed = set(dsd.codelist_for(geo_dim.id).codes()) if dsd.codelist_for(geo_dim.id) else None
        if allowed:
            wanted = [c for c in wanted if c in allowed]
        geo_codes: Optional[List[str]] = wanted or None
    else:
        geo_codes = None
    info["geo_codes"] = len(geo_codes or [])
    info["years"] = [years[0], years[-1]] if years else []

    # Значимые (не гео) измерения, по которым пользователь хочет резать запросы.
    value_dims = dsd.value_dimensions()
    batch_plans: List[Tuple[str, List[Optional[List[str]]]]] = []
    for dim in value_dims:
        batch_plans.append(
            (dim.id, dimension_batches(dsd.codelist_for(dim.id), config.dim_batch_size))
        )
    if not batch_plans:
        batch_plans = []

    combos: List[Dict[str, Optional[List[str]]]] = [{}]
    for dim_id, batches in batch_plans:
        combos = [{**c, dim_id: b} for c in combos for b in batches]

    windows = year_windows(years, config.max_years_per_request)
    total_calls = len(windows) * max(1, len(combos))
    info["planned_requests"] = total_calls
    log.info(
        "%s «%s»: %d лет, %d окон, %d территорий, %d запросов",
        code,
        indicator.name,
        len(years),
        len(windows),
        info["geo_codes"],
        total_calls,
    )

    if config.dry_run:
        return part, info

    for win_i, win in enumerate(windows, start=1):
        for combo in combos:
            overrides = {k: v for k, v in combo.items() if v is not None}
            vf = BelstatClient.build_values_filter(
                view_cfg,
                years=win,
                geo_codes=geo_codes,
                geo_dimension_id=geo_dim.id if geo_dim else GEO_DIMENSION_ID,
                dimension_overrides=overrides,
            )
            source = f"{API_ROOT}/indicator/indicatorValuesSdmxCsvGet"
            window = f"{win[0]}-{win[-1]}"
            try:
                text = client.values_sdmx_csv(code, vf)
            except BelstatAPIError as exc:
                log.warning("%s %s: портал отклонил запрос: %s", code, win, exc)
                part.errors.append(
                    {"indicator_code": code, "years": win, "error": f"api: {exc}"}
                )
                continue
            except BelstatHTTPError as exc:
                log.warning("%s %s: HTTP %s", code, win, exc.status)
                part.errors.append(
                    {"indicator_code": code, "years": win, "error": f"http {exc.status}"}
                )
                continue

            header, rows = parse_sdmx_csv(text)
            if not header:
                log.warning("%s %s: пустой ответ", code, win)
                continue
            facts = rows_to_facts(header, rows, dsd, source_url=source, source_window=window)
            part.facts.extend(facts)
            info["rows"] += len(facts)
            info["requests"] += 1
            log.debug(
                "%s окно %d/%d (%d–%d): %d строк",
                code, win_i, len(windows), win[0], win[-1], len(facts),
            )

    part.geo = geo_index
    part.codelists = dict(dsd.codelists)
    for dim in dsd.dimensions:
        part.dimensions.append(
            {
                "indicator_code": code,
                "dimension_id": dim.id,
                "position": dim.position,
                "name_ru": dim.concept_name_ru,
                "name_be": dim.concept_name_be,
                "name_en": dim.concept_name_en,
                "codelist_id": dim.codelist_id,
                "is_time": dim.is_time,
                "is_geo": dim.is_geo,
                "is_unit": dim.is_unit,
                "n_codes": len(dsd.codelist_for(dim.id).entries)
                if dsd.codelist_for(dim.id)
                else 0,
            }
        )

    structure = view_cfg.get("indicatorStructure") or {}
    unit_nodes = ((structure.get("units") or {}).get("nodes")) or []
    indicator.unit_codes = [str(n.get("code")) for n in unit_nodes if n.get("code")]
    return part, info


def collect_dataset(
    config: Optional[PipelineConfig] = None,
    *,
    client: Optional[BelstatClient] = None,
    progress: ProgressFn = None,
) -> Dataset:
    """Главная точка входа: собирает весь датасет по конфигурации."""
    config = config or PipelineConfig()
    client = client or BelstatClient(
        language=(config.languages[0] if config.languages else "ru"),
        user_agent=config.user_agent,
        timeout=config.timeout,
        max_retries=config.max_retries,
        request_delay=config.request_delay,
        cache_dir=config.cache_dir,
        use_cache=config.use_cache,
    )

    indicators = resolve_indicators(client, config)
    if not indicators:
        log.error("не найдено ни одного показателя — проверьте --rubric/--indicators")
        return Dataset()

    log.info("к сбору: %d показателей", len(indicators))
    result = Dataset()
    per_indicator: List[Dict[str, Any]] = []

    for i, ind in enumerate(indicators, start=1):
        if progress:
            progress(f"{ind.code} {ind.name}".strip(), i, len(indicators))
        try:
            part, info = collect_indicator(client, ind, config)
        except (BelstatHTTPError, BelstatAPIError) as exc:
            log.error("%s: пропущен из-за ошибки: %s", ind.code, exc)
            result.errors.append({"indicator_code": ind.code, "error": str(exc)})
            continue
        except Exception as exc:  # noqa: BLE001 — один показатель не должен ронять прогон
            log.exception("%s: необработанная ошибка", ind.code)
            result.errors.append({"indicator_code": ind.code, "error": repr(exc)})
            continue

        result.facts.extend(part.facts)
        result.errors.extend(part.errors)
        for code, node in part.geo.items():
            result.geo.setdefault(code, node)
        for cl_id, cl in part.codelists.items():
            if cl_id not in result.codelists:
                result.codelists[cl_id] = cl
            else:
                result.codelists[cl_id].entries.update(cl.entries)
        result.dimensions.extend(part.dimensions)
        per_indicator.append(info)
        log.info(
            "[%d/%d] %s: +%d наблюдений (всего %d)",
            i, len(indicators), ind.code, len(part.facts), len(result.facts),
        )

    result.indicators = indicators
    result.facts = dedupe_facts(result.facts)
    result.stats = {
        "indicators_total": len(indicators),
        "indicators_collected": len(per_indicator),
        "facts": len(result.facts),
        "geo_units": len(result.geo),
        "codelists": len(result.codelists),
        "http_requests": client.requests_made,
        "cache_hits": client.cache_hits,
        "errors": len(result.errors),
        "per_indicator": per_indicator,
    }
    log.info(
        "готово: %d наблюдений, %d показателей, %d запросов (кэш: %d), ошибок: %d",
        len(result.facts),
        len(per_indicator),
        client.requests_made,
        client.cache_hits,
        len(result.errors),
    )
    return result
