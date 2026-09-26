"""Общая подготовка тестов.

Переменные окружения задаются ДО импорта приложения, потому что
``app/config.py`` читает их на этапе импорта модуля. База данных и экспорт
создаются во временном каталоге, боевой словарь тесты не трогают.

Тесты перевода используют настоящую модель spaCy, если она установлена;
иначе такие проверки пропускаются (как нейросетевые тесты в лр. №2).
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

_SANDBOX = Path(tempfile.mkdtemp(prefix="lab4-tests-"))
os.environ["DB_PATH"] = str(_SANDBOX / "DB" / "test.db")
os.environ["EXPORTS_PATH"] = str(_SANDBOX / "exports")

import pytest  # noqa: E402

from app import config, db, dictionary  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def seeded_dictionary():
    """База создана, начальный словарь посеян (один раз на сессию тестов)."""
    config.ensure_dirs()
    db.init_db()
    dictionary.seed_from_tsv()
    yield


@pytest.fixture()
def spacy_required():
    """Пропуск теста, если модель spaCy не установлена."""
    from app import analysis
    if not analysis.available():
        pytest.skip("модель en_core_web_sm не установлена (scripts/download_model.py)")
