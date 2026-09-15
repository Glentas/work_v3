#!/usr/bin/env python3
"""Скачивание исходных текстов из Википедии (запускается один раз).

Результат складывается в corpus/sources/{fr,en}/*.txt и коммитится в репозиторий,
поэтому дальше вся система работает без интернета.

Особенности MediaWiki API, которые обязан учитывать скрипт:
* полные тексты (prop=extracts&explaintext) отдаются ТОЛЬКО по одной странице
  за запрос — exlimit>1 действует лишь вместе с exintro;
* без корректного User-Agent с контактом сервер отвечает HTTP 403,
  поэтому между запросами делается пауза.

Использование:
    python scripts/build_corpus.py
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCES_DIR = PROJECT_ROOT / "corpus" / "sources"

USER_AGENT = (
    "Lab2LanguageDetectionBot/1.0 "
    "(https://github.com/Glentas/work_v3; student.lab@example.com) Python-urllib"
)

HOSTS = {"fr": "fr.wikipedia.org", "en": "en.wikipedia.org"}

#: Статьи тренировочного и тестового наборов НЕ пересекаются: иначе оценка
#: точности измеряла бы запоминание, а не распознавание.
ARTICLES: dict[str, dict[str, list[str]]] = {
    "fr": {
        "train": ["Paris", "Histoire de France", "Cuisine française", "Géographie de la France"],
        "test": ["Lyon", "Molière"],
    },
    "en": {
        "train": ["London", "History of England", "English cuisine", "Geography of England"],
        "test": ["Manchester", "Charles Dickens"],
    },
}

PAUSE_SECONDS = 2.0


def fetch_extract(host: str, title: str, tries: int = 5) -> str:
    """Полный видимый текст одной статьи (plain text)."""
    params = {
        "action": "query",
        "prop": "extracts",
        "explaintext": 1,
        "exsectionformat": "plain",
        "titles": title,
        "redirects": 1,
        "format": "json",
    }
    url = f"https://{host}/w/api.php?" + urllib.parse.urlencode(params)
    for attempt in range(tries):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=60) as response:
                data = json.load(response)
            for page in data["query"]["pages"].values():
                return page.get("extract", "") or ""
        except Exception as exc:
            print(f"  попытка {attempt + 1}: {exc}")
            time.sleep(4 * (attempt + 1))
    return ""


def clean(text: str) -> str:
    """Убирает служебный мусор Википедии, оставляя связный prose."""
    text = re.sub(r"https?://\S+", " ", text)          # внешние ссылки
    text = re.sub(r"\[\d+\]", " ", text)                # сноски [1], [23]
    text = re.sub(r"==+.*?==+", " ", text)              # заголовки секций
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if len(line) < 40:                              # обрывки, подписи
            continue
        if sum(c.isalpha() for c in line) / max(len(line), 1) < 0.75:
            continue                                    # таблицы, инфобоксы, списки
        lines.append(line)
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def main() -> None:
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    for lang in ("fr", "en"):
        for split, titles in ARTICLES[lang].items():
            for title in titles:
                slug = re.sub(r"\W+", "_", title).strip("_").lower()
                target = SOURCES_DIR / lang / split / f"{slug}.txt"
                if target.exists():
                    print(f"есть: {target.relative_to(PROJECT_ROOT)}")
                    continue
                print(f"качаю: {lang} / {split} / {title} ...", end=" ", flush=True)
                text = clean(fetch_extract(HOSTS[lang], title))
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8")
                print(f"{len(text) / 1024:.1f} Кб")
                time.sleep(PAUSE_SECONDS)
    print("готово: corpus/sources/")


if __name__ == "__main__":
    main()
