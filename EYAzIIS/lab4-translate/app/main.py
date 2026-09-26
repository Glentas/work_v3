"""Сборка приложения FastAPI: инициализация БД, словаря и проверка модели."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import analysis, config, db, dictionary
from .web import router

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.ensure_dirs()
    db.init_db()

    if dictionary.count_entries() == 0:
        added = dictionary.seed_from_tsv()
        log.info("Словарь пуст — выполнен посев из %s: +%d записей",
                 config.SEED_DICTIONARY_PATH.name, added)
    else:
        log.info("Словарь: %d записей (med: %d, art: %d, general: %d)",
                 dictionary.count_entries(),
                 dictionary.count_entries("med"),
                 dictionary.count_entries("art"),
                 dictionary.count_entries("general"))

    if not analysis.available():
        log.warning(
            "Модель spaCy %s не найдена. Выполните один раз: "
            "python scripts/download_model.py", config.SPACY_MODEL,
        )
    else:
        log.info("Модель анализа загружена: %s", config.SPACY_MODEL)

    yield


app = FastAPI(
    title=config.APP_TITLE,
    description=(
        "Лабораторная работа 4, вариант 7: англо-русский перевод текстов "
        "предметных областей «научные статьи по медицине» и «критика "
        "предметов изобразительного искусства». Словарная система с "
        "трансфером и режимом прямого пословно-оборотного перевода."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=config.BASE_DIR / "static"), name="static")
app.include_router(router)
