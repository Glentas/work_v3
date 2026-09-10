from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Пути -------------------------------------------------------------------
COLLECTION_PATH = Path(os.getenv("COLLECTION_PATH", BASE_DIR / "collection"))
DB_PATH = Path(os.getenv("DB_PATH", BASE_DIR / "data" / "search.db"))

# --- Выдача результатов -----------------------------------------------------
SNIPPET_LENGTH = int(os.getenv("SNIPPET_LENGTH", "300"))
PER_PAGE = int(os.getenv("PER_PAGE", "10"))
TOP_KEYWORDS = int(os.getenv("TOP_KEYWORDS", "5"))
MAX_RESULTS = int(os.getenv("MAX_RESULTS", "10000"))

# --- Сеть -------------------------------------------------------------------
# 0.0.0.0 — сервер слушает все интерфейсы, доступен из локальной сети.
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8000"))

# --- База данных ------------------------------------------------------------
# Сколько миллисекунд запрос ждёт освобождения блокировки SQLite.
# Критично для сервера в локальной сети с несколькими клиентами.
DB_BUSY_TIMEOUT_MS = int(os.getenv("DB_BUSY_TIMEOUT_MS", "15000"))

# --- Поисковая стратегия ----------------------------------------------------
# Стратегия с отказами:
# если запрос с обязательным вхождением всех слов не дал результатов,
# система автоматически ослабляет условие до «любое из слов».
ENABLE_FALLBACK = os.getenv("ENABLE_FALLBACK", "1") == "1"


def ensure_dirs() -> None:
    """Создаёт рабочие каталоги, чтобы первый запуск не падал."""
    COLLECTION_PATH.mkdir(parents=True, exist_ok=True)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
