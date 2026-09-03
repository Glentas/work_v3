import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

COLLECTION_PATH = Path(os.getenv("COLLECTION_PATH", BASE_DIR / "collection"))
DB_PATH = Path(os.getenv("DB_PATH", BASE_DIR / "data" / "search.db"))

SNIPPET_LENGTH = int(os.getenv("SNIPPET_LENGTH", "300"))
PER_PAGE = int(os.getenv("PER_PAGE", "10"))
METRICS_BATCH = int(os.getenv("METRICS_BATCH", "100"))
TOP_KEYWORDS = int(os.getenv("TOP_KEYWORDS", "5"))
MAX_RESULTS = int(os.getenv("MAX_RESULTS", "10000"))

APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8000"))

# Создаём нужные папки, чтобы не падать при первом запуске
COLLECTION_PATH.mkdir(parents=True, exist_ok=True)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)