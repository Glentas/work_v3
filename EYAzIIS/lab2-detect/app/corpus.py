"""Чтение тестовой коллекции: папки с входными документами системы"""

from __future__ import annotations

import logging
from pathlib import Path

from . import config, text
from .domain import Document

log = logging.getLogger(__name__)


def scan_suite(path: Path, suite: str) -> list[Document]:
    """Все .html-документы каталога; язык — префикс имени до первого '_'. """
    documents: list[Document] = []
    if not path.exists():
        log.warning("Каталог набора %s не существует: %s", suite, path)
        return documents

    for file in sorted(path.glob("*.html")):
        lang = file.name.split("_", 1)[0]
        if lang not in config.LANGS:
            log.warning("Пропущен документ без языкового префикса: %s", file.name)
            continue
        documents.append(
            Document(
                id=f"{suite}/{file.stem}",
                name=file.name,
                path=str(file),
                lang_true=lang,
                suite=suite,
            )
        )
    return documents


def scan_all() -> dict[str, list[Document]]:
    """Основная коллекция + все стресс-наборы, лежащие в corpus/stress/."""
    suites = {"main": scan_suite(config.TEST_PATH, "main")}
    if config.STRESS_PATH.exists():
        for sub in sorted(p for p in config.STRESS_PATH.iterdir() if p.is_dir()):
            suites[sub.name] = scan_suite(sub, sub.name)
    return suites


def open_document(doc: Document) -> tuple[str, Document]:
    """Шаг 1 для одного документа: видимый текст + фактические метаданные."""
    visible, encoding = text.read_html(Path(doc.path))
    filled = Document(
        id=doc.id,
        name=doc.name,
        path=doc.path,
        lang_true=doc.lang_true,
        suite=doc.suite,
        encoding=encoding,
        chars=len(visible),
    )
    return visible, filled
