"""Общая подготовка тестов.

Переменные окружения задаются до импорта приложения, потому что
``app/config.py`` читает их на этапе импорта модуля.

Тестовая коллекция подобрана так, чтобы ожидаемые значения весов и порядок
выдачи можно было вычислить вручную по формулам методички:

    ==========================  =========================================
    Файл                        Содержимое (значимые слова)
    ==========================  =========================================
    doc_01.txt                  cat cat cat dog
    doc_02.txt                  cat dog dog dog bird bird
    doc_03.txt                  bird bird bird bird
    doc_04.txt                  zebra elephant
    doc_05.txt                  cat cat cat cat cat
    ==========================  =========================================

    N = 5 документов. Документные частоты и инверсные частоты (формула 1.5):

    =======  ====  ============================
    Термин   P_i   B_i = log(N / P_i)
    =======  ====  ============================
    cat      3     log(5/3) ≈ 0.5108
    dog      2     log(5/2) ≈ 0.9163
    bird     2     log(5/2) ≈ 0.9163
    zebra    1     log(5)   ≈ 1.6094
    =======  ====  ============================
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

_SANDBOX = Path(tempfile.mkdtemp(prefix="lab1-search-tests-"))
os.environ["DB_PATH"] = str(_SANDBOX / "test.db")
os.environ["COLLECTION_PATH"] = str(_SANDBOX / "collection")

import pytest  # noqa: E402  (импорт после настройки окружения)

#: Содержимое тестовой коллекции: имя файла -> текст.
SAMPLE_DOCUMENTS: dict[str, str] = {
    "doc_01.txt": "cat cat cat dog",
    "doc_02.txt": "cat dog dog dog bird bird",
    "doc_03.txt": "bird bird bird bird",
    "doc_04.txt": "zebra elephant",
    "doc_05.txt": "cat cat cat cat cat",
}

#: Частоты терминов Q_i^j по документам (для проверки формулы 1.6).
EXPECTED_TF: dict[str, dict[str, int]] = {
    "cat": {"doc_01.txt": 3, "doc_02.txt": 1, "doc_05.txt": 5},
    "dog": {"doc_01.txt": 1, "doc_02.txt": 3},
    "bird": {"doc_02.txt": 2, "doc_03.txt": 4},
    "zebra": {"doc_04.txt": 1},
    "elephant": {"doc_04.txt": 1},
}

#: Документные частоты P_i.
EXPECTED_DF: dict[str, int] = {
    "cat": 3,
    "dog": 2,
    "bird": 2,
    "zebra": 1,
    "elephant": 1,
}


def write_collection(documents: dict[str, str] | None = None) -> Path:
    """Записывает тестовую коллекцию и возвращает путь к каталогу."""
    from app import config

    root = config.COLLECTION_PATH
    if root.exists():
        for path in root.iterdir():
            if path.is_file():
                path.unlink()
    root.mkdir(parents=True, exist_ok=True)

    for name, text in (documents or SAMPLE_DOCUMENTS).items():
        (root / name).write_text(text, encoding="utf-8")

    return root


def reset_database() -> None:
    """Удаляет файл базы данных вместе с WAL-журналом."""
    from app import config

    for suffix in ("", "-wal", "-shm"):
        path = Path(str(config.DB_PATH) + suffix)
        if path.exists():
            path.unlink()


@pytest.fixture(scope="session")
def sample_index():
    """Индекс тестовой коллекции. Строится один раз на сессию."""
    from app.db import init_db
    from app.indexer import build_index

    reset_database()
    write_collection()
    init_db()
    stats = build_index()

    assert stats.documents == len(SAMPLE_DOCUMENTS)
    return stats


@pytest.fixture
def doc_id_by_name(sample_index):
    """Соответствие «имя файла -> идентификатор документа»."""
    from app.db import connect

    with connect() as conn:
        rows = conn.execute("SELECT id, path FROM documents").fetchall()

    return {Path(row["path"]).name: row["id"] for row in rows}


@pytest.fixture
def clean_evaluations(sample_index):
    """Очищает разметку и оценки до и после теста.

    Гарантирует, что сводные показатели в проверках не зависят от того,
    какие тесты выполнялись раньше.
    """
    from app.db import clear_evaluations, connect

    def _clear() -> None:
        with connect() as conn:
            clear_evaluations(conn)

    _clear()
    yield
    _clear()
