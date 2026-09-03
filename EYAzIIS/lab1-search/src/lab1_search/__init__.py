#!/usr/bin/env python3
"""
Скрипт для наполнения папки collection/ английскими текстами.

Скачивает статьи из Wikipedia (English) по темам, близким к варианту 7:
  - Information retrieval
  - Database
  - Computer network
  - Search engine
  - Artificial intelligence
  - Machine learning
  - Natural language processing
  - Operating system
  - Algorithm
  - Cryptography

Использование:
    uv run python scripts/fill_collection.py --count 5 --topics all
    uv run python scripts/fill_collection.py --count 10 --topics "Database,Algorithm"
    uv run python scripts/fill_collection.py --clean
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# Конфигурация
# ---------------------------------------------------------------------------

COLLECTION_DIR = Path("collection")
REQUEST_TIMEOUT = 15
REQUEST_DELAY = 0.5  # вежливый интервал между запросами (Wikipedia policy)
USER_AGENT = "Lab1SearchBot/1.0 (educational project; contact@example.com)"

TOPICS: dict[str, list[str]] = {
    "information_retrieval": [
        "Information retrieval",
        "Search engine",
        "Web search engine",
        "Boolean retrieval",
        "Inverted index",
        "Relevance (information retrieval)",
        "Vector space model",
        "Precision and recall",
        "Query expansion",
        "Document retrieval",
    ],
    "database": [
        "Database",
        "Relational database",
        "SQL",
        "Relational model",
        "Database index",
        "Transaction processing",
        "ACID",
        "NoSQL",
        "Database normalization",
        "Query optimizer",
    ],
    "network": [
        "Computer network",
        "Internet protocol suite",
        "TCP/IP",
        "Domain Name System",
        "HTTP",
        "Transport Layer Security",
        "Routing",
        "Local area network",
        "Ethernet",
        "Network socket",
    ],
    "ai": [
        "Artificial intelligence",
        "Machine learning",
        "Deep learning",
        "Neural network (machine learning)",
        "Natural language processing",
        "Supervised learning",
        "Unsupervised learning",
        "Reinforcement learning",
        "Knowledge representation and reasoning",
        "Expert system",
    ],
    "cs": [
        "Algorithm",
        "Data structure",
        "Operating system",
        "Computer architecture",
        "Compiler",
        "Programming language",
        "Cryptography",
        "Distributed computing",
        "Parallel computing",
        "Computational complexity theory",
    ],
}

# ---------------------------------------------------------------------------
# Логирование
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("fill_collection")

# ---------------------------------------------------------------------------
# Загрузка и очистка текста
# ---------------------------------------------------------------------------

WIKI_API = "https://en.wikipedia.org/w/api.php"


def _safe_filename(title: str) -> str:
    """
    Приводит заголовок статьи к безопасному имени файла.
    """
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", title).strip("_")
    return cleaned[:80] or "article"


def _clean_wiki_html(html: str) -> str:
    """
    Удаляет служебные блоки Wikipedia и оставляет только осмысленный текст.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Удаляем всё, что не нужно: ссылки на правки, сноски, оглавление,
    # навигационные блоки, инфобоксы, галереи и т.д.
    for tag in soup.find_all(
        [
            "table",
            "sup",
            "span.mw-editsection",
            "span.reference",
            "div.navbox",
            "div.hatnote",
            "div.metadata",
            "div.thumb",
            "div.reflist",
            "div.sistersitebox",
            "div.toc",
            "div.mw-authority-control",
            "ul.gallery",
        ]
    ):
        tag.decompose()

    for tag in soup.find_all(class_=re.compile(
        r"(mw-editsection|reference|navbox|toc|metadata|infobox|hatnote|reflist|noprint|sisterproject|authority-control)",
        re.IGNORECASE,
    )):
        tag.decompose()

    for tag in soup.find_all(id=re.compile(
        r"(References|External_links|See_also|Bibliography|Notes|Further_reading|Citations)",
        re.IGNORECASE,
    )):
        # Удаляем сам заголовок секции и всё, что после него до следующего h2
        section = tag.find_parent("div") or tag.parent
        if section is not None:
            next_h2 = section.find_next_sibling("h2")
            if next_h2 is not None:
                for sib in list(section.next_siblings):
                    if sib == next_h2:
                        break
                    if hasattr(sib, "decompose"):
                        sib.decompose()
                    elif isinstance(sib, str):
                        sib.replace_with("")

    # Извлекаем абзацы
    paragraphs = []
    for p in soup.find_all("p"):
        text = p.get_text(" ", strip=True)
        if not text:
            continue
        # Игнорируем короткие заглушки и "italic disambiguation"
        if len(text) < 40:
            continue
        paragraphs.append(text)

    return "\n\n".join(paragraphs)


def fetch_wiki_article(title: str) -> tuple[str, str] | None:
    """
    Возвращает (title, plain_text) для статьи Wikipedia, либо None.
    """
    params = {
        "action": "parse",
        "page": title,
        "prop": "text",
        "format": "json",
        "formatversion": 2,
        "disableeditsection": True,
        "redirects": True,
    }

    headers = {"User-Agent": USER_AGENT}

    try:
        response = requests.get(
            WIKI_API,
            params=params,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        log.warning("Не удалось скачать '%s': %s", title, exc)
        return None

    if "error" in payload:
        log.warning("Wikipedia вернула ошибку для '%s': %s", title, payload["error"])
        return None

    parsed = payload.get("parse", {})
    final_title = parsed.get("title", title)
    html = parsed.get("text", "")

    if not html:
        return None

    plain = _clean_wiki_html(html)

    if len(plain) < 500:
        # Слишком короткая статья (disambiguation, stub и т.п.)
        return None

    return final_title, plain


# ---------------------------------------------------------------------------
# Запись файлов
# ---------------------------------------------------------------------------

def write_document(path: Path, title: str, text: str, source_url: str) -> None:
    """
    Записывает документ в формате:
        TITLE
        URL
        ---
        plain text
    """
    header = (
        f"{title}\n"
        f"Source: {source_url}\n"
        f"---\n\n"
    )
    path.write_text(header + text, encoding="utf-8")


# ---------------------------------------------------------------------------
# Основная логика
# ---------------------------------------------------------------------------

def select_titles(topics: list[str], per_topic: int) -> list[str]:
    """
    Собирает уникальные заголовки для заданных тем.
    """
    if "all" in topics:
        topics = list(TOPICS.keys())

    seen: set[str] = set()
    ordered: list[str] = []

    for topic in topics:
        topic_key = topic.strip().lower().replace(" ", "_")
        items = TOPICS.get(topic_key)
        if items is None:
            log.warning("Неизвестная тема '%s', пропускаем", topic)
            continue

        for title in items[:per_topic]:
            if title not in seen:
                seen.add(title)
                ordered.append(title)

    return ordered


def fill_collection(titles: list[str], clean_first: bool) -> int:
    """
    Скачивает статьи и записывает их в collection/.
    Возвращает количество успешно сохранённых файлов.
    """
    COLLECTION_DIR.mkdir(parents=True, exist_ok=True)

    if clean_first:
        for existing in COLLECTION_DIR.glob("*.txt"):
            existing.unlink()
        log.info("Папка collection/ очищена")

    saved = 0
    failed = 0

    for index, title in enumerate(titles, start=1):
        log.info("[%d/%d] Скачиваем: %s", index, len(titles), title)

        result = fetch_wiki_article(title)
        time.sleep(REQUEST_DELAY)

        if result is None:
            failed += 1
            continue

        final_title, plain = result
        filename = f"{_safe_filename(final_title)}.txt"
        path = COLLECTION_DIR / filename

        # Если файл с таким именем уже есть — добавляем суффикс
        counter = 1
        while path.exists():
            filename = f"{_safe_filename(final_title)}_{counter}.txt"
            path = COLLECTION_DIR / filename
            counter += 1

        source_url = f"https://en.wikipedia.org/wiki/{final_title.replace(' ', '_')}"
        write_document(path, final_title, plain, source_url)

        log.info("    -> Сохранено: %s (%d символов)", path.name, len(plain))
        saved += 1

    log.info("Готово: успешно %d, пропущено %d", saved, failed)
    return saved


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Наполняет collection/ английскими статьями из Wikipedia."
    )
    parser.add_argument(
        "--topics",
        default="all",
        help=(
            "Список тем через запятую. Доступные: "
            + ", ".join(TOPICS.keys())
            + " или 'all'."
        ),
    )
    parser.add_argument(
        "--count",
        type=int,
        default=5,
        help="Количество статей с каждой темы (по умолчанию 5).",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Очистить collection/ перед запуском.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    topics = [t.strip() for t in args.topics.split(",") if t.strip()]
    titles = select_titles(topics, args.count)

    if not titles:
        log.error("Не выбрано ни одного заголовка для скачивания")
        return 1

    log.info("План: скачать %d статей", len(titles))
    fill_collection(titles, clean_first=args.clean)
    return 0


if __name__ == "__main__":
    sys.exit(main())