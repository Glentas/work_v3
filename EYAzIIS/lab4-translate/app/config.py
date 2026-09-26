"""Конфигурация системы машинного перевода (лабораторная работа 4, вариант 7).

Все пути можно переопределить переменными окружения — это используют тесты,
чтобы работать с временной базой и не трогать боевой словарь.
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Пути -------------------------------------------------------------------
DB_PATH = Path(os.getenv("DB_PATH", BASE_DIR / "DB" / "translate.db"))
EXPORTS_PATH = Path(os.getenv("EXPORTS_PATH", BASE_DIR / "exports"))
SEED_DICTIONARY_PATH = Path(
    os.getenv("SEED_DICTIONARY_PATH", BASE_DIR / "data" / "seed_dictionary.tsv")
)
SAMPLES_PATH = Path(os.getenv("SAMPLES_PATH", BASE_DIR / "data" / "samples"))

# --- Сеть --------------------------------------------------------------------
# 0.0.0.0 — сервер слушает все интерфейсы, доступен из локальной сети.
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8000"))

# --- Языковая пара варианта 7: англо-русский --------------------------------
SOURCE_LANG = "en"
SOURCE_LANG_NAME = "Английский"
TARGET_LANG = "ru"
TARGET_LANG_NAME = "Русский"

#: Модель spaCy — та же, что в лр. №3 весеннего семестра: она даёт теги
#: частей речи (Penn Treebank), синтаксические роли и морфологические
#: признаки, на которых работает анализ и трансфер.
SPACY_MODEL = os.getenv("SPACY_MODEL", "en_core_web_sm")

# --- Предметные области варианта 7 -------------------------------------------
#: general — общеупотребительная лексика, всегда участвует в переводе;
#: med и art — словари предметных областей (научные статьи по медицине,
#: критика предметов изобразительного искусства).
DOMAINS: tuple[str, ...] = ("general", "med", "art")

DOMAIN_NAMES: dict[str, str] = {
    "general": "Общая лексика",
    "med": "Медицина",
    "art": "Критика изобразительного искусства",
}

#: Ключевые слова для автоматического определения предметной области текста:
#: какая область набрала больше совпадений, та и приоритетна при выборе
#: перевода многозначных слов (knowledge-based компонент системы).
DOMAIN_KEYWORDS: dict[str, frozenset[str]] = {
    "med": frozenset(
        """patient patients disease diseases disorder diagnosis treatment therapy
        drug drugs medicine medical clinical symptom symptoms hospital surgery
        infection inflammatory inflammation immune blood cell cells tissue organ
        physician doctor nurse cancer tumor chronic acute mortality morbidity
        health healthcare vaccine antibody gene genetic protein dose prescription
        trial cohort placebo medication screening biopsy
        cardiovascular respiratory neural muscle bone kidney liver lung lungs""".split()
    ),
    "art": frozenset(
        """art artist artists painting paintings painter canvas brushstroke color
        palette composition sculpture statue exhibition museum gallery critic
        criticism aesthetic masterpiece portrait landscape genre visual style
        technique texture hue tone shade impressionism expressionism cubism
        surrealism baroque renaissance decorative ornament artwork viewer
        sketch watercolor fresco acrylic perspective harmony""".split()
    ),
}

# --- Режимы перевода ----------------------------------------------------------
#: literal — система прямого (пословно-оборотного) перевода: элементы текста
#: заменяются словарными эквивалентами, учитывается только локальный контекст
#: (обороты). transfer — система с трансфером: после анализа выполняется
#: межъязыковое преобразование и морфологический синтез русских словоформ.
MODES: tuple[str, ...] = ("transfer", "literal")

MODE_NAMES: dict[str, str] = {
    "transfer": "С трансфером (морфологический синтез)",
    "literal": "Прямой (пословно-оборотный)",
}

#: Ограничения на входной текст (защита от случайных «мегабайтов»).
MAX_TEXT_CHARS = int(os.getenv("MAX_TEXT_CHARS", "200000"))

#: Название системы для шапок страниц и экспорта.
APP_TITLE = "Автоматический машинный перевод текстов"
APP_VARIANT = "Вариант 7: англо-русский · медицина · критика изобразительного искусства"


def ensure_dirs() -> None:
    """Создаёт рабочие каталоги, чтобы первый запуск не падал."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    EXPORTS_PATH.mkdir(parents=True, exist_ok=True)
