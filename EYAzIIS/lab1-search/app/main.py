from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import config
from .db import init_db
from .text import ensure_nltk
from .web import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_nltk()
    init_db()
    yield


app = FastAPI(
    title="Информационно-поисковая система",
    lifespan=lifespan,
)

app.mount(
    "/static",
    StaticFiles(directory=config.BASE_DIR / "static"),
    name="static"
)

app.include_router(router)