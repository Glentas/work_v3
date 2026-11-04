"""Необязательное геокодирование территорий через Nominatim (OpenStreetMap).

Нужно, если собранный агрегированный датасет дальше поедет в GIS или на карту:
к каждому району добавляются координаты его центра.

Соблюдаем правила использования OSM: не чаще 1 запроса в секунду, осмысленный
User-Agent, локальный кэш, чтобы повторные прогоны не дёргали сервис.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Dict, Optional

import requests

from .model import Dataset

log = logging.getLogger("belstat.geocode")

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
MIN_INTERVAL = 1.05  # сек между запросами — требование OSM

#: Типы территорий, для которых геокодирование имеет смысл.
GEOCODED_LEVELS = (1, 2)


def _clean_name(name: str) -> str:
    name = re.sub(r"\s+", " ", name or "").strip()
    name = re.sub(r"^(г\.|г |гор\.|город)\s+", "", name)
    return name


class NominatimGeocoder:
    """Мини-клиент Nominatim с файловым кэшем."""

    def __init__(
        self,
        cache_path: Path | str = ".cache/belstat/nominatim.json",
        user_agent: str = "belstat-dataset-collector/1.0 (research; contact: unknown)",
        timeout: int = 30,
    ) -> None:
        self.cache_path = Path(cache_path)
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent, "Accept-Language": "ru,en"})
        self._cache: Dict[str, Optional[Dict[str, float]]] = {}
        if self.cache_path.exists():
            try:
                self._cache = json.loads(self.cache_path.read_text("utf-8"))
            except json.JSONDecodeError:
                log.warning("кэш геокодера повреждён, начинаю заново")
                self._cache = {}
        self._last = 0.0
        self.hits = 0
        self.misses = 0

    def _save(self) -> None:
        self.cache_path.write_text(
            json.dumps(self._cache, ensure_ascii=False, indent=1), "utf-8"
        )

    def geocode(self, query: str) -> Optional[Dict[str, float]]:
        if query in self._cache:
            return self._cache[query]
        wait = MIN_INTERVAL - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        result: Optional[Dict[str, float]] = None
        try:
            r = self.session.get(
                NOMINATIM_URL,
                params={
                    "q": query,
                    "format": "jsonv2",
                    "countrycodes": "by",
                    "limit": 1,
                    "addressdetails": 0,
                },
                timeout=self.timeout,
            )
            if r.status_code == 200:
                items = r.json()
                if items:
                    result = {
                        "lat": float(items[0]["lat"]),
                        "lon": float(items[0]["lon"]),
                        "display_name": items[0].get("display_name", ""),
                    }
        except (requests.RequestException, ValueError, KeyError) as exc:
            log.warning("геокодинг %r не удался: %s", query, exc)
        self._cache[query] = result
        return result

    def flush(self) -> None:
        self._save()


def geocode_dataset(
    dataset: Dataset,
    *,
    cache_path: Path | str = ".cache/belstat/nominatim.json",
    user_agent: str = "belstat-dataset-collector/1.0",
    levels: tuple[int, ...] = GEOCODED_LEVELS,
    only_with_data: bool = True,
) -> Dataset:
    """Проставляет ``lat``/``lon`` территориям датасета (in-place).

    Args:
        only_with_data: геокодировать только территории, по которым есть
            наблюдения. Справочник портала содержит 374 кода (включая
            сельсоветы, по которым статистика не публикуется) — без этого
            флага запросов к Nominatim будет заметно больше.
    """
    geocoder = NominatimGeocoder(cache_path=cache_path, user_agent=user_agent)
    with_data = {f.geo_code for f in dataset.facts if f.geo_code}
    targets = [
        n
        for n in dataset.geo.values()
        if n.level in levels and (not only_with_data or n.code in with_data)
    ]
    targets.sort(key=lambda n: (n.level, n.region_name_ru or "", n.name_ru))
    log.info("геокодирование: %d территорий", len(targets))
    try:
        for i, node in enumerate(targets, start=1):
            region = node.region_name_ru or ""
            candidates = []
            if node.name_en:
                candidates.append(_clean_name(node.name_en))
            if node.name_ru:
                candidates.append(_clean_name(node.name_ru))
            found = None
            for name in candidates:
                q = f"{name}, {region}, Belarus" if region and node.level > 1 else f"{name}, Belarus"
                found = geocoder.geocode(q)
                if found:
                    break
            if found:
                node.lat = found["lat"]
                node.lon = found["lon"]
                geocoder.hits += 1
            else:
                geocoder.misses += 1
                log.info("не найден: %s (%s)", node.name_ru, node.code)
            if i % 10 == 0:
                log.info("  геокодировано %d/%d", i, len(targets))
                geocoder.flush()
    finally:
        geocoder.flush()
    log.info(
        "геокодирование завершено: найдено %d, не найдено %d",
        geocoder.hits,
        geocoder.misses,
    )
    return dataset
