#!/usr/bin/env python3
"""
Скрипт для наполнения коллекции документов для лабораторной работы.

Скачивает классические английские книги с Project Gutenberg (public domain)
и разбивает их на отдельные документы по главам/секциям.

Использование:
    uv run python scripts/populate_collection.py
    uv run python scripts/populate_collection.py --books 5
    uv run python scripts/populate_collection.py --clear
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from dataclasses import dataclass


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
COLLECTION_DIR = PROJECT_ROOT / "collection"

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0 "
    "(academic IR lab crawler)"
)

# Список книг с Project Gutenberg.
# Формат: (gutenberg_id, short_name)
# Список взят из популярных классических произведений на английском.
BOOKS: list[tuple[int, str]] = [
    (1342, "pride_and_prejudice"),       # Jane Austen
    (11,   "alice_in_wonderland"),       # Lewis Carroll
    (1661, "sherlock_holmes"),           # Arthur Conan Doyle
    (36,   "war_of_the_worlds"),         # H. G. Wells
    (84,   "frankenstein"),              # Mary Shelley
    (345,  "dracula"),                   # Bram Stoker
    (2701, "moby_dick"),                 # Herman Melville
    (1232, "prince_and_pauper"),         # Mark Twain
    (1400, "great_expectations"),        # Charles Dickens
    (98,   "tale_of_two_cities"),        # Charles Dickens
    (76,   "adventures_of_huck_finn"),   # Mark Twain
    (74,   "adventures_of_tom_sawyer"),  # Mark Twain
]


@dataclass(frozen=True)
class Document:
    filename: str
    text: str


def download_text(gutenberg_id: int, retries: int = 3) -> str | None:
    """
    Скачивает текст книги с Project Gutenberg.

    URL имеет вид: https://www.gutenberg.org/cache/epub/{id}/pg{id}.txt
    """
    url = f"https://www.gutenberg.org/cache/epub/{gutenberg_id}/pg{gutenberg_id}.txt"

    for attempt in range(1, retries + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read()

            # Project Gutenberg обычно отдаёт UTF-8, но иногда latin-1.
            try:
                return raw.decode("utf-8")
            except UnicodeDecodeError:
                return raw.decode("latin-1", errors="ignore")

        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            log.warning(
                "Попытка %d/%d скачать книгу %d не удалась: %s",
                attempt,
                retries,
                gutenberg_id,
                exc,
            )
            if attempt < retries:
                time.sleep(1.5 * attempt)

    return None


def strip_gutenberg_header_footer(text: str) -> str:
    """
    Удаляет стандартные заголовок и футер Project Gutenberg.

    Gutenberg помечает начало и конец текста явными маркерами.
    """
    # Ищем стартовый маркер: "*** START OF THE PROJECT GUTENBERG EBOOK"
    # или похожие варианты.
    start_markers = [
        r"\*\*\*\s*START OF (?:THE |THIS )?PROJECT GUTENBERG EBOOK[^*]*\*\*\*",
        r"\*{3,}\s*START OF[^*]*\*{3,}",
    ]

    start_index = 0
    for pattern in start_markers:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            start_index = match.end()
            break

    # Ищем финальный маркер: "*** END OF THE PROJECT GUTENBERG EBOOK"
    end_markers = [
        r"\*\*\*\s*END OF (?:THE |THIS )?PROJECT GUTENBERG EBOOK[^*]*\*\*\*",
        r"\*{3,}\s*END OF[^*]*\*{3,}",
    ]

    end_index = len(text)
    for pattern in end_markers:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            end_index = match.start()
            break

    return text[start_index:end_index].strip()


def normalize_whitespace(text: str) -> str:
    """
    Нормализует пробельные символы: схлопывает множественные пустые строки.
    """
    text = re.sub(r"\r\n", "\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_into_chapters(text: str) -> list[Document]:
    """
    Разбивает книгу на главы/секции.

    Если глава не обнаружена, делит на блоки примерно по 20 000 символов.
    """
    # Ищем заголовки глав в разных форматах:
    # "CHAPTER I", "Chapter 1", "CHAPTER I.", "PREFACE", "PROLOGUE"
    chapter_pattern = re.compile(
        r"^(?:"
        r"CHAPTER\s+[IVXLCDM\d]+"
        r"|Chapter\s+[IVXLCDM\d]+"
        r"|PREFACE"
        r"|PROLOGUE"
        r"|EPILOGUE"
        r"|INTRODUCTION"
        r"|BOOK\s+[IVXLCDM\d]+"
        r"|PART\s+[IVXLCDM\d]+"
        r"|[IVXLCDM]+\.\s+[A-Z]"
        r")[\.\s:]*[^\n]*$",
        flags=re.IGNORECASE | re.MULTILINE,
    )

    matches = list(chapter_pattern.finditer(text))

    if len(matches) < 3:
        # Глава не обнаружена — режем по 20 000 символов, не разрывая абзацев.
        return _split_by_paragraphs(text, target_size=20_000)

    documents: list[Document] = []
    previous_end = 0

    for index, match in enumerate(matches):
        chunk = text[previous_end:match.start()].strip()

        if index > 0 and chunk:
            documents.append(
                Document(
                    filename=f"doc_{len(documents) + 1:03d}.txt",
                    text=chunk,
                )
            )

        previous_end = match.start()

    # Хвост книги
    tail = text[previous_end:].strip()
    if tail:
        documents.append(
            Document(
                filename=f"doc_{len(documents) + 1:03d}.txt",
                text=tail,
            )
        )

    # Если получилось очень мало крупных документов, дополнительно разбиваем.
    expanded: list[Document] = []
    for document in documents:
        if len(document.text) > 50_000:
            parts = _split_by_paragraphs(document.text, target_size=20_000)
            for part in parts:
                expanded.append(
                    Document(
                        filename=f"doc_{len(expanded) + 1:03d}.txt",
                        text=part.text,
                    )
                )
        else:
            expanded.append(
                Document(
                    filename=f"doc_{len(expanded) + 1:03d}.txt",
                    text=document.text,
                )
            )

    return expanded


def _split_by_paragraphs(text: str, target_size: int = 20_000) -> list[Document]:
    """
    Разбивает текст по абзацам, стремясь к целевому размеру блока.
    """
    paragraphs = re.split(r"\n\s*\n", text)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    documents: list[Document] = []
    current: list[str] = []
    current_size = 0

    for paragraph in paragraphs:
        paragraph_len = len(paragraph) + 2

        if current_size + paragraph_len > target_size and current:
            documents.append(
                Document(
                    filename="",  # будет переименован позже
                    text="\n\n".join(current),
                )
            )
            current = []
            current_size = 0

        current.append(paragraph)
        current_size += paragraph_len

    if current:
        documents.append(
            Document(filename="", text="\n\n".join(current))
        )

    # Переименовываем в финальные имена
    return [
        Document(filename=f"doc_{i + 1:03d}.txt", text=d.text)
        for i, d in enumerate(documents)
    ]


def process_book(gutenberg_id: int, book_name: str) -> list[Document]:
    """
    Скачивает, очищает и разбивает книгу на документы.
    """
    log.info("Скачиваю книгу %s (id=%d)...", book_name, gutenberg_id)

    text = download_text(gutenberg_id)
    if text is None:
        log.error("Не удалось скачать книгу %s", book_name)
        return []

    log.info(
        "Книга %s загружена: %d символов",
        book_name,
        len(text),
    )

    text = strip_gutenberg_header_footer(text)
    text = normalize_whitespace(text)

    if not text:
        log.warning("После очистки книга %s оказалась пустой", book_name)
        return []

    documents = split_into_chapters(text)
    log.info("Книга %s разбита на %d документов", book_name, len(documents))

    return documents


def clear_collection() -> None:
    """
    Очищает папку collection/.
    """
    if COLLECTION_DIR.exists():
        for path in COLLECTION_DIR.iterdir():
            if path.is_file():
                path.unlink()
        log.info("Папка %s очищена", COLLECTION_DIR)

    COLLECTION_DIR.mkdir(parents=True, exist_ok=True)


def save_documents(documents: list[Document]) -> None:
    """
    Сохраняет документы в папку collection/.
    """
    COLLECTION_DIR.mkdir(parents=True, exist_ok=True)

    for document in documents:
        path = COLLECTION_DIR / document.filename
        path.write_text(document.text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Наполнение коллекции английскими текстами для IR-лабораторной."
    )
    parser.add_argument(
        "--books",
        type=int,
        default=len(BOOKS),
        help=f"Сколько книг скачать (по умолчанию: {len(BOOKS)})",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Очистить папку collection/ перед началом",
    )
    parser.add_argument(
        "--no-clear",
        action="store_true",
        help="Не очищать папку collection/ перед началом",
    )
    args = parser.parse_args()

    if args.clear:
        clear_collection()

    COLLECTION_DIR.mkdir(parents=True, exist_ok=True)

    books_to_process = BOOKS[: max(1, min(args.books, len(BOOKS)))]
    log.info("Будет обработано книг: %d", len(books_to_process))

    all_documents: list[Document] = []

    for gutenberg_id, book_name in books_to_process:
        documents = process_book(gutenberg_id, book_name)
        all_documents.extend(documents)

        # Вежливость к серверу Gutenberg.
        time.sleep(0.5)

    if not all_documents:
        log.error("Не удалось получить ни одного документа.")
        return 1

    # Перенумеровываем документы последовательно.
    renumbered = [
        Document(filename=f"doc_{i + 1:03d}.txt", text=doc.text)
        for i, doc in enumerate(all_documents)
    ]

    save_documents(renumbered)

    total_chars = sum(len(d.text) for d in renumbered)
    log.info(
        "Готово! Документов: %d, суммарно символов: %d, папка: %s",
        len(renumbered),
        total_chars,
        COLLECTION_DIR,
    )

    # Статистика по размерам.
    sizes = sorted(len(d.text) for d in renumbered)
    log.info(
        "Размеры документов: min=%d, median=%d, max=%d",
        sizes[0],
        sizes[len(sizes) // 2],
        sizes[-1],
    )

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log.info("Прервано пользователем.")
        sys.exit(130)