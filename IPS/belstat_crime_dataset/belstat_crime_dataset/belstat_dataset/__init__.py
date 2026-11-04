"""Сбор агрегированной официальной статистики правонарушений с портала Белстата.

Реализация «Варианта 1» автоматизации: официальный портал открытых данных
Национального статистического комитета Республики Беларусь
(https://dataportal.belstat.gov.by), SDMX-API, разрез — районы и города
областного подчинения.

Публичный API пакета:

    from belstat_dataset import BelstatClient, collect_dataset, PipelineConfig
"""

from .client import BelstatClient, BelstatAPIError, BelstatHTTPError
from .config import PipelineConfig, DEFAULT_RUBRIC_CRIME
from .model import (
    Codelist,
    CodelistEntry,
    DataStructure,
    Dataset,
    Fact,
    GeoNode,
    Indicator,
)
from .pipeline import collect_dataset, resolve_indicators

__version__ = "1.0.0"

__all__ = [
    "BelstatClient",
    "BelstatAPIError",
    "BelstatHTTPError",
    "PipelineConfig",
    "DEFAULT_RUBRIC_CRIME",
    "Codelist",
    "CodelistEntry",
    "DataStructure",
    "Dataset",
    "Fact",
    "GeoNode",
    "Indicator",
    "collect_dataset",
    "resolve_indicators",
    "__version__",
]
