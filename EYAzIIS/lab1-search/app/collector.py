"""Агент сбора документов.

Обходит каталог коллекции и извлекает текст из поддерживаемых файлов.
Это первый компонент информационно-поисковой системы по методичке —
«агент (паук, кроулер, робот), который собирает информацию о документах».

Файлы обходятся в отсортированном порядке, чтобы идентификаторы документов
были одинаковыми при каждой переиндексации и оценки качества поиска
оставались воспроизводимыми.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

SUPPORTED_SUFFIXES = (".txt", ".pdf")

#: Текст документа хранится в базе целиком, но в выдаче показывается только
#: заголовок, поэтому длинные «заголовки» укорачиваются.
TITLE_MAX_LENGTH = 100

#: Кодировки, которые пробуем для текстовых файлов, по порядку.
_TEXT_ENCODINGS = ("utf-8", "utf-8-sig", "cp1251", "latin-1")


@dataclass(frozen=True, slots=True)
class RawDocument:
    """Документ, подготовленный для индексирования."""

    title: str
    text: str
    path: str
    date: str
    time: str


def collect_documents(root: Path) -> list[RawDocument]:
    """Собирает все документы коллекции из каталога ``root``."""
    documents: list[RawDocument] = []

    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue

        text = _read(path)
        if not text.strip():
            log.warning("Пропущен документ без текста: %s", path.name)
            continue

        documents.append(_to_document(path, text))

    log.info("Собрано документов: %d из %s", len(documents), root)
    return documents


def _to_document(path: Path, text: str) -> RawDocument:
    modified = datetime.fromtimestamp(path.stat().st_mtime)
    return RawDocument(
        title=derive_title(text, path),
        text=text,
        path=str(path.resolve()),
        date=modified.strftime("%Y-%m-%d"),
        time=modified.strftime("%H:%M:%S"),
    )


def _read(path: Path) -> str:
    """Читает содержимое файла в зависимости от формата."""
    if path.suffix.lower() == ".pdf":
        return _read_pdf(path)
    return _read_text(path)


def _read_text(path: Path) -> str:
    for encoding in _TEXT_ENCODINGS:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
        except OSError as exc:
            log.warning("Не удалось прочитать %s: %s", path.name, exc)
            return ""

    log.warning("Не удалось определить кодировку %s", path.name)
    return ""


def _read_pdf(path: Path) -> str:
    """Извлекает текстовый слой PDF.

    Файлы без текстового слоя (сканы-картинки) возвращают пустую строку
    и пропускаются: распознавание текста в рамках работы не выполняется.
    """
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages)
    except Exception as exc:  # pypdf бросает разные исключения на битых файлах
        log.warning("Ошибка чтения PDF %s: %s", path.name, exc)
        return ""


def derive_title(text: str, path: Path) -> str:
    """Определяет заголовок документа.

    Берётся первая непустая строка — обычно это название раздела или главы.
    Если она вырожденная (одна буква или римская цифра, как в разметке книг
    «I.», «V.»), заголовок дополняется началом текста, чтобы в выдаче
    было понятно, о каком документе речь.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return path.stem[:TITLE_MAX_LENGTH]

    heading = _clean_heading(lines[0])

    if _is_meaningful(heading):
        return heading[:TITLE_MAX_LENGTH]

    body = " ".join(lines[1:]).strip()
    combined = f"{heading} — {body}" if body else f"{path.stem}: {heading}"
    return combined[:TITLE_MAX_LENGTH].rstrip(" ,;—-")


def _is_meaningful(heading: str) -> bool:
    """Заголовок содержательный, если в нём больше одного значимого символа."""
    letters = sum(char.isalpha() for char in heading)
    return letters >= 4


def _clean_heading(heading: str) -> str:
    """Убирает артефакты разметки из строки-заголовка.

    В текстах Project Gutenberg разделы встречаются в виде «Chapter I.]»
    или «[Illustration: ...]» — служебные скобки и маркеры читателю не нужны.
    """
    cleaned = heading.strip().strip("[]{}*#=").strip()
    return cleaned or heading.strip()
