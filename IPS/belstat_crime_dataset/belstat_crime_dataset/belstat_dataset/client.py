"""HTTP-клиент портала открытых данных Белстата.

Портал (Angular SPA) работает с двумя слоями API:

1. ``{API_ROOT}/...`` — внутренний JSON-API веб-интерфейса. Отсюда берутся
   справочники, структура показателя и готовые экспорты (CSV/XLSX/SDMX-CSV).
2. ``{SDMX_ROOT}/...`` — официально документированный «система-система»
   SDMX-API. Его точные URL портал сам возвращает в ответе
   ``POST {API_ROOT}/indicator/indicatorApiInfoGet``.

Для сбора данных используется экспорт ``indicatorValuesSdmxCsvGet``: он
возвращает плоский SDMX-CSV (одна строка = одно наблюдение) без потери
измерений. Официальный ``sdmx-api/indicator/values/SDMX-JSON`` для этой цели
не годится — сервер Белстата генерирует в нём дублирующиеся ключи наблюдений
(``"0:0:0:-1"`` повторяется для каждого года), из-за чего при разборе JSON
часть значений молча теряется. Подробности — в README.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

import requests
from requests.adapters import HTTPAdapter

try:  # urllib3 >= 1.26
    from urllib3.util.retry import Retry
except Exception:  # pragma: no cover
    Retry = None  # type: ignore[assignment]

from .config import (
    API_ROOT,
    GEO_DIMENSION_ID,
    SDMX_ROOT,
    SITE_URL,
    USER_AGENT,
)

log = logging.getLogger("belstat.client")


class BelstatHTTPError(RuntimeError):
    """HTTP-ошибка портала (не 2xx после всех повторов)."""

    def __init__(self, url: str, status: int, body: str) -> None:
        super().__init__(f"HTTP {status} для {url}: {body[:300]}")
        self.url = url
        self.status = status
        self.body = body


class BelstatAPIError(RuntimeError):
    """Портал ответил 200/4xx содержательной ошибкой на русском."""


class BelstatClient:
    """Тонкая обёртка над REST-эндпоинтами портала с ретраями и кэшем."""

    def __init__(
        self,
        *,
        api_root: str = API_ROOT,
        sdmx_root: str = SDMX_ROOT,
        language: str = "ru",
        user_agent: str = USER_AGENT,
        timeout: int = 120,
        max_retries: int = 5,
        request_delay: float = 0.6,
        cache_dir: Optional[str] = "cache",
        use_cache: bool = True,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.api_root = api_root.rstrip("/")
        self.sdmx_root = sdmx_root.rstrip("/")
        self.language = language
        self.timeout = timeout
        self.max_retries = max_retries
        self.request_delay = float(request_delay)

        self._cache_dir = Path(cache_dir) if cache_dir else None
        self._use_cache = use_cache
        if self._cache_dir is not None:
            self._cache_dir.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._last_request_ts = 0.0
        self.requests_made = 0
        self.cache_hits = 0

        self.session = session or self._build_session(user_agent, max_retries)

    # ------------------------------------------------------------------ #
    #  Инфраструктура
    # ------------------------------------------------------------------ #

    @staticmethod
    def _build_session(user_agent: str, max_retries: int) -> requests.Session:
        s = requests.Session()
        s.headers.update(
            {
                "User-Agent": user_agent,
                "Origin": SITE_URL,
                "Referer": f"{SITE_URL}/osids/home-page",
                "Accept": "application/json, text/csv, application/octet-stream, */*",
            }
        )
        if Retry is not None:
            retry = Retry(
                total=max_retries,
                connect=max_retries,
                read=max_retries,
                status=max_retries,
                backoff_factor=1.5,
                status_forcelist=(429, 500, 502, 503, 504),
                allowed_methods=frozenset(["GET", "POST"]),
                raise_on_status=False,
            )
            adapter = HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=4)
            s.mount("https://", adapter)
            s.mount("http://", adapter)
        return s

    def _throttle(self) -> None:
        """Выдерживаем минимальный интервал между обращениями к порталу."""
        if self.request_delay <= 0:
            return
        with self._lock:
            wait = self.request_delay - (time.monotonic() - self._last_request_ts)
            if wait > 0:
                time.sleep(wait)
            self._last_request_ts = time.monotonic()

    def _cache_key(self, method: str, url: str, payload: Any, lang: str) -> str:
        raw = json.dumps(
            {"m": method.upper(), "u": url, "b": payload, "l": lang},
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def _cache_path(self, key: str) -> Optional[Path]:
        if self._cache_dir is None:
            return None
        return self._cache_dir / key[:2] / f"{key}.bin"

    def _request(
        self,
        method: str,
        url: str,
        *,
        json_body: Any = None,
        params: Optional[Dict[str, Any]] = None,
        language: Optional[str] = None,
        as_text: bool = True,
        cache_tag: str = "",
    ) -> Any:
        lang = language or self.language
        headers = {"Accept-Language": lang}
        if json_body is not None:
            headers["Content-Type"] = "application/json"

        key = self._cache_key(method + cache_tag, url, json_body or params, lang)
        cpath = self._cache_path(key)
        if cpath is not None and self._use_cache and cpath.exists():
            self.cache_hits += 1
            data = cpath.read_bytes()
            log.debug("кэш: %s", cpath.name)
            return data.decode("utf-8") if as_text else data

        self._throttle()
        last_err: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                self.requests_made += 1
                log.debug("%s %s (попытка %d)", method, url, attempt)
                resp = self.session.request(
                    method,
                    url,
                    json=json_body,
                    params=params,
                    headers=headers,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:  # сеть/таймаут
                last_err = exc
                sleep_for = min(60.0, 2.0 ** attempt)
                log.warning("сетевая ошибка (%s), повтор через %.0f c", exc, sleep_for)
                time.sleep(sleep_for)
                continue

            if resp.status_code in (429, 500, 502, 503, 504):
                sleep_for = min(60.0, 2.0 ** attempt)
                log.warning(
                    "HTTP %d, повтор через %.0f c", resp.status_code, sleep_for
                )
                time.sleep(sleep_for)
                continue

            if resp.status_code >= 400:
                raise BelstatHTTPError(url, resp.status_code, resp.text)

            data = resp.content
            if cpath is not None:
                cpath.parent.mkdir(parents=True, exist_ok=True)
                cpath.write_bytes(data)
            return data.decode("utf-8") if as_text else data

        raise BelstatHTTPError(url, 0, f"исчерпаны повторы: {last_err}")

    def _get_json(self, path: str, language: Optional[str] = None) -> Any:
        url = path if path.startswith("http") else f"{self.api_root}{path}"
        return json.loads(self._request("GET", url, language=language))

    def _post_json(
        self, path: str, body: Any, language: Optional[str] = None
    ) -> Any:
        url = path if path.startswith("http") else f"{self.api_root}{path}"
        return json.loads(self._request("POST", url, json_body=body, language=language))

    # ------------------------------------------------------------------ #
    #  Справочники и метаданные
    # ------------------------------------------------------------------ #

    def rubric_tree_node(self, rubric_code: str) -> Dict[str, Any]:
        """Узел рубрики: ``/rubric/rubricTreeNodeGet/{code}``."""
        return self._get_json(f"/rubric/rubricTreeNodeGet/{rubric_code}")

    def rubric_indicators(self, rubric_code: str) -> list[Dict[str, Any]]:
        """Показатели рубрики: ``/rubric/rubricIndicatorsGet/{code}``."""
        data = self._get_json(f"/rubric/rubricIndicatorsGet/{rubric_code}")
        return list(data.get("items") or [])

    def indicator_search(self) -> list[Dict[str, Any]]:
        """Полный каталог показателей портала (~940 шт.).

        Серверная фильтрация по строке поиска в этом эндпоинте фактически не
        работает (возвращает весь каталог), поэтому фильтр применяется на
        стороне клиента — см. :func:`belstat_dataset.pipeline.resolve_indicators`.
        """
        data = self._post_json("/indicator/indicatorSearch", {})
        return list(data.get("items") or [])

    def indicator_get(self, indicator_code: str) -> Dict[str, Any]:
        """Карточка показателя: ``/indicator/indicatorGet/{code}``."""
        return self._get_json(f"/indicator/indicatorGet/{indicator_code}")

    def indicator_view_cfg(self, indicator_code: str) -> Dict[str, Any]:
        """Конфигурация показателя: доступные годы, дерево измерений, фильтр.

        ``GET /indicator/indicatorViewCfgGet/{code}``
        """
        return self._get_json(f"/indicator/indicatorViewCfgGet/{indicator_code}")

    def indicator_metadata(self, indicator_code: str) -> Dict[str, Any]:
        """Метаданные показателя: ``POST /indicator/indicatorMetadataGet``."""
        return self._post_json("/indicator/indicatorMetadataGet", indicator_code)

    def indicator_api_info(
        self, indicator_code: str, values_filter: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Официальные SDMX-URL показателя (то, что показывает кнопка «API»).

        ``POST /indicator/indicatorApiInfoGet``
        """
        body = {"indicatorCode": indicator_code, "valuesFilter": values_filter}
        return self._post_json("/indicator/indicatorApiInfoGet", body)

    def datastructure_json(self, indicator_code: str) -> Dict[str, Any]:
        """SDMX-JSON структура данных показателя (DSD + codelists).

        ``GET {SDMX_ROOT}/indicator/datastructure/SDMX-JSON/{code}``

        Отсюда берутся: названия показателя на ru/be/en, состав измерений,
        все справочники значений (включая поле ``parent`` у территорий —
        оно и задаёт иерархию «область → район»).
        """
        url = f"{self.sdmx_root}/indicator/datastructure/SDMX-JSON/{indicator_code}"
        return json.loads(self._request("GET", url, as_text=True))

    def datastructure_ml(self, indicator_code: str) -> str:
        """SDMX-ML (XML) структура показателя — для архива/отладки."""
        url = f"{self.sdmx_root}/indicator/datastructure/SDMX-ML/{indicator_code}"
        return self._request("GET", url, as_text=True)

    # ------------------------------------------------------------------ #
    #  Данные
    # ------------------------------------------------------------------ #

    def values_sdmx_csv(
        self, indicator_code: str, values_filter: Dict[str, Any]
    ) -> str:
        """Плоский SDMX-CSV по показателю и фильтру.

        ``POST /indicator/indicatorValuesSdmxCsvGet``

        Ответ: ``DATAFLOW,<dim1>,<dim2>,...,TIME_PERIOD,OBS_VALUE,OBS_ATTRIBUTE``.
        Ограничение портала — не более 10 лет в ``valuesFilter.years``.
        """
        body = {"indicatorCode": indicator_code, "valuesFilter": values_filter}
        text = self._request(
            "POST",
            f"{self.api_root}/indicator/indicatorValuesSdmxCsvGet",
            json_body=body,
            as_text=True,
            cache_tag="sdmxcsv",
        )
        self._raise_for_plain_error(text)
        return text

    def values_table(self, indicator_code: str, values_filter: Dict[str, Any]) -> Dict[str, Any]:
        """Таблица в том виде, в котором её рисует веб-интерфейс.

        ``POST /indicator/indicatorValuesSearch``. Используется для контроля:
        удобно сверять агрегаты с тем, что видно на экране.
        """
        body = {"indicatorCode": indicator_code, "valuesFilter": values_filter}
        return self._post_json("/indicator/indicatorValuesSearch", body)

    def values_sdmx_json(
        self, indicator_code: str, values_filter: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Официальный SDMX-JSON с данными (``sdmx-api``).

        .. warning::
           Реализация портала генерирует дублирующиеся ключи наблюдений,
           поэтому формат теряет часть значений. Метод оставлен только для
           сверки/диагностики — в пайплайне не используется.
        """
        url = f"{self.sdmx_root}/indicator/values/SDMX-JSON/{indicator_code}"
        return json.loads(self._request("POST", url, json_body=values_filter))

    def values_xlsx(
        self, indicator_code: str, values_filter: Dict[str, Any]
    ) -> bytes:
        """XLSX-экспорт таблицы показателя (для ручных сверок)."""
        body = {"indicatorCode": indicator_code, "valuesFilter": values_filter}
        return self._request(
            "POST",
            f"{self.api_root}/indicator/indicatorValuesXlsxGet",
            json_body=body,
            as_text=False,
            cache_tag="xlsx",
        )

    # ------------------------------------------------------------------ #
    #  Вспомогательное
    # ------------------------------------------------------------------ #

    @staticmethod
    def _raise_for_plain_error(text: str) -> None:
        """Портал на часть ошибок отвечает 200 + русский текст вместо CSV."""
        head = text.lstrip("\ufeff").lstrip()
        if head and not head.startswith("DATAFLOW"):
            snippet = head.splitlines()[0][:200]
            if "," not in snippet:
                raise BelstatAPIError(snippet)

    @staticmethod
    def build_values_filter(
        view_cfg: Dict[str, Any],
        *,
        years: Sequence[int],
        geo_codes: Optional[Sequence[str]] = None,
        geo_dimension_id: str = GEO_DIMENSION_ID,
        dimension_overrides: Optional[Dict[str, Sequence[str]]] = None,
    ) -> Dict[str, Any]:
        """Собирает ``valuesFilter`` из конфигурации показателя.

        Правила портала (проверены эмпирически):

        * ``years`` — не более 10 значений за запрос;
        * ``dimensionParams[dim] = []`` означает «все значения измерения»;
        * ``dimensionOrder`` должен перечислять все измерения показателя;
        * ``units`` и ``periodicities`` берутся из преднастройки показателя.
        """
        base = json.loads(json.dumps(view_cfg.get("valuesFilter") or {}))
        structure = view_cfg.get("indicatorStructure") or {}
        dims = [d.get("code") for d in (structure.get("dimensions") or [])]

        order = base.get("dimensionOrder") or [d for d in dims if d]
        params: Dict[str, list] = dict(base.get("dimensionParams") or {})
        for d in order:
            params.setdefault(d, [])

        if geo_codes is not None and geo_dimension_id in params:
            params[geo_dimension_id] = list(geo_codes)

        for dim_id, codes in (dimension_overrides or {}).items():
            if dim_id in params:
                params[dim_id] = list(codes)

        units = base.get("units") or []
        if not units:
            unit_nodes = ((structure.get("units") or {}).get("nodes")) or []
            units = [n.get("code") for n in unit_nodes if n.get("code")]

        vf = {
            "years": [int(y) for y in years],
            "periodicities": list(base.get("periodicities") or []),
            "units": list(units),
            "dimensionOrder": list(order),
            "dimensionParams": params,
            "simbolsAfterComma": base.get("simbolsAfterComma"),
        }
        return vf
