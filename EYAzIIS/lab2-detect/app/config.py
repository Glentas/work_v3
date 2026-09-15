from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Пути -------------------------------------------------------------------
CORPUS_PATH = Path(os.getenv("CORPUS_PATH", BASE_DIR / "corpus"))
TRAIN_PATH = Path(os.getenv("TRAIN_PATH", CORPUS_PATH / "train"))
TEST_PATH = Path(os.getenv("TEST_PATH", CORPUS_PATH / "test"))
STRESS_PATH = Path(os.getenv("STRESS_PATH", CORPUS_PATH / "stress"))
MODEL_PATH = Path(os.getenv("MODEL_PATH", BASE_DIR / "models" / "lid.176.ftz"))

# --- Сеть -------------------------------------------------------------------
# 0.0.0.0 — сервер слушает все интерфейсы, доступен из локальной сети.
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8000"))

# --- Параметры методов ------------------------------------------------------
# Размер профиля языка (ПОЯ) в методе N-грамм: топ-N N-грамм по убыванию частоты.
NGRAM_PROFILE_SIZE = int(os.getenv("NGRAM_PROFILE_SIZE", "300"))
# Максимальная длина N-граммы: используются все длины от 1 до N («не более N»).
NGRAM_MAX_N = int(os.getenv("NGRAM_MAX_N", "5"))
# Размер входного документа в знаках видимого текста (~1 страница А4).
DOC_CHARS = int(os.getenv("DOC_CHARS", "2000"))

# --- Языки варианта 7 -------------------------------------------------------
LANGS: tuple[str, ...] = ("fr", "en")

LANG_NAMES: dict[str, str] = {
    "fr": "Французский",
    "en": "Английский",
}

#: Алфавиты языков: базовая латиница плюс характерная диакритика.
#: У английского уникальной диакритики практически нет — это особенность пары.
LANG_ALPHABETS: dict[str, frozenset[str]] = {
    "fr": frozenset("abcdefghijklmnopqrstuvwxyzàâæçéèêëîïôœùûüÿ"),
    "en": frozenset("abcdefghijklmnopqrstuvwxyz"),
}

LANG_UNIQUE_CHARS: dict[str, frozenset[str]] = {
    "fr": frozenset("àâæçéèêëîïôœùûüÿ"),
    "en": frozenset(),
}

# --- Методы распознавания ---------------------------------------------------
METHODS: tuple[str, ...] = ("ngram", "alphabet", "neural")

METHOD_NAMES: dict[str, str] = {
    "ngram": "N-грамм",
    "alphabet": "Алфавитный",
    "neural": "Нейросетевой (fastText)",
}


def ensure_dirs() -> None:
    """Создаёт рабочие каталоги, чтобы первый запуск не падал."""
    CORPUS_PATH.mkdir(parents=True, exist_ok=True)
    TRAIN_PATH.mkdir(parents=True, exist_ok=True)
    TEST_PATH.mkdir(parents=True, exist_ok=True)
