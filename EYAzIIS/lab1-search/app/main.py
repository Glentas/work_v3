"""Точка входа приложения: создание FastAPI, подключение маршрутов и статики.

При запуске создаётся схема базы данных и каталоги коллекции.
Скачивание ресурсов из интернета не выполняется — система рассчитана
на работу в изолированной локальной сети.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import config
from .db import connect, index_info, init_db
from .web import router

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.ensure_dirs()
    init_db()

    with connect() as conn:
        info = index_info(conn)

    if info["documents"] == 0:
        log.warning(
            "Индекс пуст. Положите документы в %s и нажмите «Переиндексация».",
            config.COLLECTION_PATH,
        )
    else:
        log.info(
            "Индекс загружен: %d документов, %d терминов, %d постингов.",
            info["documents"],
            info["terms"],
            info["postings"],
        )

    yield


app = FastAPI(
    title="Информационно-поисковая система",
    description=(
        "Учебная информационно-поисковая система: логический поиск по коллекции "
        "английских документов, ранжирование по TF-IDF (формула 1.6 методички) "
        "и оценка качества по метрикам РОМИП'2004."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.mount(
    "/static",
    StaticFiles(directory=config.BASE_DIR / "static"),
    name="static",
)

app.include_router(router)
