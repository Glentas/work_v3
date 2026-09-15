from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import config, neural
from .web import router

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.ensure_dirs()

    train = [config.TRAIN_PATH / f"{lang}.txt" for lang in config.LANGS]
    missing_train = [p.name for p in train if not p.exists()]
    if missing_train:
        log.warning(
            "Нет тренировочного набора (%s). Запустите scripts/build_corpus.py "
            "и scripts/make_test_docs.py.",
            ", ".join(missing_train),
        )
    else:
        for path in train:
            log.info("ПОЯ строятся по %s (%.1f Кб)", path.name, path.stat().st_size / 1024)

    if not config.MODEL_PATH.exists():
        log.warning(
            "Модель нейросетевого метода не найдена: %s. "
            "Запустите scripts/download_model.py; до этого нейросетевой метод "
            "будет помечаться недоступным.",
            config.MODEL_PATH,
        )
    else:
        try:
            neural.predict_distances("probe")
            log.info("Нейросетевая модель загружена: %s", config.MODEL_PATH)
        except neural.NeuralUnavailable as exc:
            log.warning("%s", exc)

    yield


app = FastAPI(
    title="Распознавание языка текста",
    description=(
        "Лабораторная работа 2, вариант 7: французский и английский, HTML. "
        "Методы: N-грамм, алфавитный, нейросетевой (fastText)."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=config.BASE_DIR / "static"), name="static")
app.include_router(router)
