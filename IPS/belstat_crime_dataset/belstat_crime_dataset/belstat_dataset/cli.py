"""Командная строка: ``python -m belstat_dataset <команда> [опции]``."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import List, Optional, Sequence

import pandas as pd

from . import __version__
from .client import BelstatClient
from .config import INDICATOR_CRIMES_TOTAL, RUBRIC_CRIME, PipelineConfig
from .enrich import (
    coverage_matrix,
    crime_long_table,
    crime_wide_table,
    dimensions_to_dataframe,
    dimension_values_to_dataframe,
    facts_to_dataframe,
    indicators_to_dataframe,
    territories_to_dataframe,
)
from .pipeline import collect_dataset, resolve_indicators
from .report import build_report
from .storage import read_sqlite, write_csv_files, write_sqlite

log = logging.getLogger("belstat.cli")

LEVEL_ALIASES = {
    "country": 0,
    "region": 1,
    "oblast": 1,
    "district": 2,
    "raion": 2,
    "settlement": 3,
    "all": None,
}


def _setup_logging(verbosity: int) -> None:
    level = logging.WARNING
    if verbosity == 1:
        level = logging.INFO
    elif verbosity >= 2:
        level = logging.DEBUG
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def _parse_years(value: Optional[str]) -> tuple[Optional[int], Optional[int]]:
    if not value:
        return None, None
    if "-" in value:
        a, b = value.split("-", 1)
        return (int(a) if a.strip() else None, int(b) if b.strip() else None)
    y = int(value)
    return y, y


def _parse_levels(values: Sequence[str]) -> Sequence[int]:
    out: List[int] = []
    for v in values:
        key = str(v).strip().lower()
        if key not in LEVEL_ALIASES:
            try:
                out.append(int(key))
                continue
            except ValueError:
                raise SystemExit(
                    f"--geo-level: непонятное значение {v!r}. "
                    f"Допустимы: {', '.join(sorted(LEVEL_ALIASES))} или 0..3"
                )
        lvl = LEVEL_ALIASES[key]
        if lvl is None:
            return [0, 1, 2, 3]
        out.append(lvl)
    return sorted(set(out)) or [0, 1, 2]


def _build_config(args: argparse.Namespace) -> PipelineConfig:
    year_from, year_to = _parse_years(args.years)
    return PipelineConfig(
        rubrics=args.rubric or (),
        indicator_codes=args.indicator or (),
        name_filter=args.name_filter or (),
        year_from=year_from,
        year_to=year_to,
        geo_levels=_parse_levels(args.geo_level or ["country", "region", "district"]),
        languages=[args.lang] if args.lang else ["ru"],
        max_years_per_request=args.max_years,
        dim_batch_size=args.dim_batch,
        request_delay=args.delay,
        timeout=args.timeout,
        max_retries=args.retries,
        cache_dir=None if args.no_cache else str(args.cache_dir),
        use_cache=not args.no_cache,
        user_agent=args.user_agent,
        dry_run=args.dry_run,
    )


# --------------------------------------------------------------------------- #
#  Команды
# --------------------------------------------------------------------------- #


def cmd_discover(args: argparse.Namespace) -> int:
    config = _build_config(args)
    client = BelstatClient(
        language=config.languages[0],
        user_agent=config.user_agent,
        timeout=config.timeout,
        max_retries=config.max_retries,
        request_delay=config.request_delay,
        cache_dir=config.cache_dir,
        use_cache=config.use_cache,
    )
    indicators = resolve_indicators(client, config)
    if args.json:
        print(
            json.dumps(
                [
                    {
                        "code": i.code,
                        "name_ru": i.name_ru,
                        "rubric_code": i.rubric_code,
                        "periodicities": i.periodicities,
                        "page_url": i.page_url,
                    }
                    for i in indicators
                ],
                ensure_ascii=False,
                indent=1,
            )
        )
        return 0
    print(f"Найдено показателей: {len(indicators)}\n")
    for i in indicators:
        print(f"  {i.code}  {i.name_ru or '(название уточняется при сборе)'}")
    return 0


def cmd_api_info(args: argparse.Namespace) -> int:
    """Печатает официальные SDMX-URL показателя (то, что показывает кнопка «API»)."""
    client = BelstatClient(
        language=args.lang,
        user_agent=args.user_agent,
        timeout=args.timeout,
        max_retries=args.retries,
        request_delay=args.delay,
        cache_dir=None if args.no_cache else str(args.cache_dir),
        use_cache=not args.no_cache,
    )
    cfg = client.indicator_view_cfg(args.indicator)
    vf = BelstatClient.build_values_filter(cfg, years=cfg["valuesFilter"].get("years") or [])
    info = client.indicator_api_info(args.indicator, vf)
    print(json.dumps(info, ensure_ascii=False, indent=1))
    return 0


def cmd_collect(args: argparse.Namespace) -> int:
    config = _build_config(args)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    total = {"n": 0}

    def progress(label: str, i: int, n: int) -> None:
        total["n"] = n
        log.info("[%d/%d] %s", i, n, label)

    dataset = collect_dataset(config, progress=progress)

    if config.dry_run:
        print("\nDRY RUN — запросы за данными не выполнялись.")
        print(json.dumps(dataset.stats, ensure_ascii=False, indent=1, default=str))
        return 0

    facts = facts_to_dataframe(dataset)
    indicators_df = indicators_to_dataframe(dataset)
    territories_df = territories_to_dataframe(dataset)
    dim_values_df = dimension_values_to_dataframe(dataset)
    dimensions_df = dimensions_to_dataframe(dataset)

    if args.geocode and not facts.empty:
        from .geocode import geocode_dataset

        geocode_dataset(
            dataset,
            cache_path=Path(config.cache_dir or ".cache/belstat") / "nominatim.json",
            user_agent=config.user_agent,
            only_with_data=not args.geocode_all_territories,
        )
        territories_df = territories_to_dataframe(dataset)

    tables = {
        "facts": facts,
        "indicators": indicators_df,
        "territories": territories_df,
        "dimension_values": dim_values_df,
        "dimensions": dimensions_df,
    }

    long_df = crime_long_table(facts, args.main_indicator)
    if not long_df.empty:
        tables["crime_by_district"] = long_df
        if not args.no_pivot:
            wide_df = crime_wide_table(long_df)
            if not wide_df.empty:
                tables["crime_by_district_wide"] = wide_df

    cov = coverage_matrix(facts)
    if not cov.empty:
        tables["qa_coverage_matrix"] = cov

    written = write_csv_files(tables, out_dir)
    print("\nCSV-файлы:")
    for name, path in written.items():
        print(f"  {path}  ({len(tables[name])} строк)")

    if args.db:
        db_path = Path(args.db)
        write_sqlite(
            {k: v for k, v in tables.items() if k not in ("crime_by_district_wide",)},
            db_path,
            replace_indicator_codes=sorted({i.code for i in dataset.indicators}),
            meta={
                "config": config.as_dict(),
                "stats": {k: v for k, v in dataset.stats.items() if k != "per_indicator"},
                "tool_version": __version__,
            },
            errors=dataset.errors,
        )
        print(f"\nSQLite: {db_path}")

    report_path = build_report(dataset.stats, facts, out_dir, indicator_code=args.main_indicator)
    print(f"Отчёт:    {report_path}")

    if dataset.errors:
        err_path = out_dir / "errors.json"
        err_path.write_text(json.dumps(dataset.errors, ensure_ascii=False, indent=1), "utf-8")
        print(f"Ошибки:   {err_path} ({len(dataset.errors)})")

    print(
        f"\nИтого: наблюдений {len(facts)}, показателей {len(dataset.indicators)}, "
        f"запросов {dataset.stats.get('http_requests')} "
        f"(из кэша {dataset.stats.get('cache_hits')})."
    )
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    """Пересобирает отчёт из уже сохранённых данных (CSV или SQLite)."""
    if args.db:
        facts = read_sqlite(args.db, "SELECT * FROM facts")
        stats: dict = {"source": f"sqlite:{args.db}"}
    else:
        facts = pd.read_csv(Path(args.out) / "facts.csv", dtype={"geo_code": str})
        stats = {"source": f"csv:{args.out}/facts.csv"}
    path = build_report(stats, facts, args.out, indicator_code=args.main_indicator)
    print(path.read_text("utf-8"))
    return 0


# --------------------------------------------------------------------------- #
#  Парсер
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="belstat_dataset",
        description=(
            "Сбор агрегированной официальной статистики правонарушений "
            "с портала открытых данных Белстата (dataportal.belstat.gov.by)."
        ),
    )
    p.add_argument("--version", action="version", version=f"belstat_dataset {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    def add_common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--lang", default="ru", help="язык ответов портала (ru/be/en)")
        sp.add_argument("--delay", type=float, default=0.6, help="пауза между запросами, сек")
        sp.add_argument("--timeout", type=int, default=120, help="таймаут запроса, сек")
        sp.add_argument("--retries", type=int, default=5, help="число повторов при ошибках")
        sp.add_argument("--cache-dir", default=".cache/belstat", help="каталог кэша ответов портала")
        sp.add_argument("--no-cache", action="store_true", help="не использовать кэш")
        sp.add_argument(
            "--user-agent",
            default=PipelineConfig().user_agent,
            help="строка User-Agent (хороший тон — указать свой контакт)",
        )
        sp.add_argument("-v", "--verbose", action="count", default=0, help="-v инфо, -vv отладка")

    # discover -------------------------------------------------------------
    d = sub.add_parser("discover", help="показать список показателей рубрики/поиска")
    d.add_argument("--rubric", action="append", default=None, help=f"код рубрики (по умолчанию {RUBRIC_CRIME})")
    d.add_argument("--indicator", action="append", default=None, help="явный код показателя")
    d.add_argument("--name-filter", action="append", default=None, help="подстрока в названии показателя")
    d.add_argument("--years", default=None, help="не используется, для единообразия")
    d.add_argument("--geo-level", action="append", default=None)
    d.add_argument("--max-years", type=int, default=10)
    d.add_argument("--dim-batch", type=int, default=0)
    d.add_argument("--dry-run", action="store_true")
    d.add_argument("--json", action="store_true", help="вывод в JSON")
    add_common(d)
    d.set_defaults(func=cmd_discover)

    # api-info -------------------------------------------------------------
    a = sub.add_parser("api-info", help="официальные SDMX-URL показателя")
    a.add_argument("indicator", nargs="?", default=INDICATOR_CRIMES_TOTAL, help="код показателя")
    add_common(a)
    a.set_defaults(func=cmd_api_info)

    # collect --------------------------------------------------------------
    c = sub.add_parser("collect", help="собрать датасет")
    c.add_argument("--rubric", action="append", default=None,
                   help=f"код рубрики портала (по умолчанию {RUBRIC_CRIME} — правосудие и правонарушения)")
    c.add_argument("--indicator", action="append", default=None, help="явный код показателя (можно несколько)")
    c.add_argument("--name-filter", action="append", default=None,
                   help="дополнительно включить показатели, содержащие подстроку в названии")
    c.add_argument("--years", default=None,
                   help="диапазон лет: 2015-2025, 2020- (от 2020), -2010 (до 2010), 2024 (один год)")
    c.add_argument("--geo-level", action="append", default=None,
                   help="уровни разреза: country|region|district|settlement|all или 0..3 (можно несколько)")
    c.add_argument("--max-years", type=int, default=10,
                   help="размер годового окна запроса (портал ограничивает 10 годами)")
    c.add_argument("--dim-batch", type=int, default=0,
                   help="резать большие измерения на батчи по N кодов (0 = не резать)")
    c.add_argument("--out", default="data", help="каталог для CSV-файлов")
    c.add_argument("--db", default=None, help="путь к SQLite-базе (если нужно — пишем и её)")
    c.add_argument("--main-indicator", default=INDICATOR_CRIMES_TOTAL,
                   help="код показателя для курируемой таблицы «преступления по районам»")
    c.add_argument("--no-pivot", action="store_true", help="не делать широкую pivot-таблицу")
    c.add_argument("--geocode", action="store_true",
                   help="добавить координаты центров территорий через Nominatim (OSM)")
    c.add_argument("--geocode-all-territories", action="store_true",
                   help="геокодировать весь справочник территорий, а не только те, где есть данные")
    c.add_argument("--dry-run", action="store_true", help="показать план запросов, не скачивая данные")
    add_common(c)
    c.set_defaults(func=cmd_collect)

    # report ---------------------------------------------------------------
    r = sub.add_parser("report", help="пересобрать отчёт из сохранённых данных")
    r.add_argument("--out", default="data", help="каталог с facts.csv")
    r.add_argument("--db", default=None, help="или читать из SQLite")
    r.add_argument("--main-indicator", default=INDICATOR_CRIMES_TOTAL)
    add_common(r)
    r.set_defaults(func=cmd_report)

    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(getattr(args, "verbose", 0))
    if getattr(args, "rubric", None) is None and not getattr(args, "indicator", None) \
            and getattr(args, "command", "") in ("collect", "discover"):
        args.rubric = [RUBRIC_CRIME]
    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        print("\nпрервано пользователем", file=sys.stderr)
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
