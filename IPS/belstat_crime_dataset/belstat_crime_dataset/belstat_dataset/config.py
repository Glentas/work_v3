"""Константы портала и конфигурация пайплайна сбора."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

# --------------------------------------------------------------------------- #
#  Адреса портала открытых данных Белстата
# --------------------------------------------------------------------------- #

SITE_URL = "https://dataportal.belstat.gov.by"

#: Корень внутреннего JSON-API портала (его использует веб-интерфейс).
API_ROOT = f"{SITE_URL}/osids-public-api"

#: Корень официального «система-система» SDMX-API.
#: Точные URL выдаёт сам портал: POST {API_ROOT}/indicator/indicatorApiInfoGet
SDMX_ROOT = f"{API_ROOT}/sdmx-api"

#: Раздел портала «Статистика правосудия и правонарушений».
RUBRIC_CRIME = "10620"
DEFAULT_RUBRIC_CRIME = RUBRIC_CRIME

#: Основной показатель: «Число зарегистрированных преступлений».
INDICATOR_CRIMES_TOTAL = "10108000001"
#: «Уровень преступности на 100 000 человек населения».
INDICATOR_CRIME_RATE = "10108000002"

#: Идентификатор измерения «Территория Республики Беларусь» (единый для портала).
GEO_DIMENSION_ID = "razrez_594"
#: Код территории «Республика Беларусь» (корень иерархии).
GEO_ROOT_CODE = "699961"

#: Портал отдаёт не более 10 лет за один запрос
#: (иначе: «Просмотр данных возможен за период не более 10 лет.»).
MAX_YEARS_PER_REQUEST = 10

#: Форматы файлов, которые принимает SDMX-API.
SDMX_FORMATS = ("SDMX-JSON", "SDMX-ML")

USER_AGENT = (
    "belstat-dataset-collector/1.0 (+research use; contact: set --user-agent)"
)

# --------------------------------------------------------------------------- #
#  Конфигурация
# --------------------------------------------------------------------------- #


@dataclass
class PipelineConfig:
    """Параметры одного прогона пайплайна сбора.

    Attributes:
        rubrics: коды рубрик портала, из которых брать показатели.
        indicator_codes: явный список кодов показателей (имеет приоритет).
        name_filter: подстроки для фильтрации названий показателей
            (применяется к результатам поиска по рубрикам).
        year_from / year_to: границы собираемого периода (включительно).
            ``None`` — брать всё, что отдаёт портал.
        geo_levels: уровни территориальной иерархии, которые нужны:
            0 = Республика Беларусь, 1 = области и г. Минск,
            2 = районы и города областного подчинения, 3 = посёлки/сельсоветы.
            По умолчанию 0..2 — это и есть «разрез районов и городов».
        languages: языки подписей в выходных словарях.
        max_years_per_request: размер годового окна одного запроса.
        dim_batch_size: если у негеографического измерения больше кодов,
            запросы дополнительно режутся на батчи по этой размерности
            (защита от слишком больших ответов). ``0`` — не резать.
        request_delay: минимальная пауза между запросами, сек (вежливость).
        timeout: таймаут одного HTTP-запроса, сек.
        max_retries: число повторов при сетевых ошибках и 5xx/429.
        cache_dir: каталог кэша сырых ответов; ``None`` — кэш выключен.
        use_cache: читать ли из кэша (``False`` — только писать).
        user_agent: строка User-Agent.
        dry_run: не выполнять запросы за данными, только показать план.
    """

    rubrics: Sequence[str] = (RUBRIC_CRIME,)
    indicator_codes: Sequence[str] = ()
    name_filter: Sequence[str] = ()

    year_from: Optional[int] = None
    year_to: Optional[int] = None

    geo_levels: Sequence[int] = (0, 1, 2)

    languages: Sequence[str] = ("ru", "en", "be")

    max_years_per_request: int = MAX_YEARS_PER_REQUEST
    dim_batch_size: int = 0

    request_delay: float = 0.6
    timeout: int = 120
    max_retries: int = 5

    cache_dir: Optional[str] = ".cache/belstat"
    use_cache: bool = True

    user_agent: str = USER_AGENT
    dry_run: bool = False

    extra_indicators: List[str] = field(default_factory=list)

    def year_window(self) -> tuple[Optional[int], Optional[int]]:
        return self.year_from, self.year_to

    def as_dict(self) -> dict:
        d = self.__dict__.copy()
        for k in ("rubrics", "indicator_codes", "name_filter", "geo_levels", "languages"):
            d[k] = list(d.get(k) or [])
        return d
