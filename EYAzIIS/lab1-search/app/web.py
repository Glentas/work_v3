from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from . import config, db, search as search_engine
from .domain import (
    METRIC_LABELS,
    BatchRelevanceRequest,
    Metrics,
    RelevanceRequest,
    SearchParams,
)
from .evaluation import compute_metrics
from .indexer import IndexStats, build_index

log = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory=str(config.BASE_DIR / "templates"))

#: Результат последней переиндексации — показывается в интерфейсе.
_last_index: IndexStats | None = None


# ---------------------------------------------------------------------------
# Зависимости
# ---------------------------------------------------------------------------
def get_conn() -> Iterator[sqlite3.Connection]:
    """Соединение с базой данных для обработчика запроса.

    FastAPI закрывает генератор после отправки ответа, поэтому соединение
    освобождается в том числе при возникновении исключения.
    """
    with db.connect() as conn:
        yield conn


#: Соединение с БД как зависимость обработчика.
DbConn = Annotated[sqlite3.Connection, Depends(get_conn)]


def _page_context(
    params: SearchParams,
    *,
    outcome=None,
    page: int = 1,
    checked_ids: set[int] | None = None,
    query_id: int = 0,
    conn: sqlite3.Connection | None = None,
) -> dict:
    """Общий контекст страницы поиска."""
    checked = checked_ids or set()
    total = outcome.total if outcome else 0

    return {
        "params": params,
        "outcome": outcome,
        "total": total,
        "page": page,
        "per_page": config.PER_PAGE,
        "total_pages": _pages(total, config.PER_PAGE),
        "checked_ids": checked,
        "checked_count": len(checked),
        "query_id": query_id,
        "index": db.index_info(conn) if conn is not None else _index_info(),
    }


def _pages(total: int, per_page: int) -> int:
    return (total + per_page - 1) // per_page if total else 0


def _index_info() -> dict[str, int]:
    with db.connect() as conn:
        return db.index_info(conn)


# ---------------------------------------------------------------------------
# Страницы
# ---------------------------------------------------------------------------
@router.get("/")
def home(request: Request) -> object:
    return templates.TemplateResponse(
        request=request, name="search.html", context=_page_context(SearchParams())
    )


@router.get("/search")
def search_page(
    request: Request,
    conn: DbConn,
    q: str = "",
    all_words: bool = False,
    date_start: str = "",
    date_end: str = "",
    page: int = 1,
) -> object:
    params = SearchParams(
        q=q, all_words=all_words, date_start=date_start, date_end=date_end
    )

    if not q.strip():
        return templates.TemplateResponse(
            request=request, name="search.html", context=_page_context(params)
        )

    page = max(1, page)
    outcome = search_engine.search(
        params, offset=(page - 1) * config.PER_PAGE, limit=config.PER_PAGE
    )

    query_id = db.find_query_id(conn, params) or 0
    checked_ids = db.relevant_doc_ids(conn, query_id) if query_id else set()

    return templates.TemplateResponse(
        request=request, name="search.html", context=_page_context(
            params,
            outcome=outcome,
            page=page,
            checked_ids=checked_ids,
            query_id=query_id,
            conn=conn,
        ),
    )


@router.get("/documents/{doc_id}")
def document_page(
    request: Request, doc_id: int, conn: DbConn
) -> object:
    document = db.get_document(conn, doc_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Документ не найден")

    return templates.TemplateResponse(
        request=request, name="document.html", context={"doc": document}
    )


@router.get("/documents/{doc_id}/download")
def document_download(doc_id: int, conn: DbConn) -> FileResponse:
    document = db.get_document(conn, doc_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Документ не найден")

    path = Path(document["path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Файл не найден на диске")

    # PDF отдаётся для просмотра в браузере, остальные файлы — на скачивание.
    media_type = "application/pdf" if path.suffix.lower() == ".pdf" else None
    return FileResponse(path, filename=path.name, media_type=media_type)


@router.get("/metrics")
def metrics_page(request: Request, conn: DbConn) -> object:
    return templates.TemplateResponse(
        request=request, name="metrics.html", context={
            "summary": db.metrics_summary(conn),
            "labels": METRIC_LABELS,
            "index": _index_info(),
        },
    )


@router.get("/help")
def help_page(request: Request) -> object:
    return templates.TemplateResponse(
        request=request, name="help.html", context={"index": _index_info(), "last_index": _last_index}
    )


@router.post("/reindex")
def reindex() -> RedirectResponse:
    """Перестраивает индекс по содержимому каталога коллекции.

    Выполняется в отдельном потоке пула FastAPI, поэтому не блокирует
    остальные запросы, а запись в базу идёт одной транзакцией: при сбое
    коллекция не потеряется.
    """
    global _last_index

    _last_index = build_index()
    log.info("Переиндексация: %s", _last_index.describe())

    return RedirectResponse("/?reindexed=1", status_code=303)


# ---------------------------------------------------------------------------
# JSON API
# ---------------------------------------------------------------------------
@router.get("/api/status")
def api_status(conn: DbConn) -> dict:
    """Состояние системы: индекс, коллекция, адрес для клиентов локальной сети."""
    return {
        "index": db.index_info(conn),
        "collection": str(config.COLLECTION_PATH),
        "last_reindex": _last_index.describe() if _last_index else None,
        "per_page": config.PER_PAGE,
        "snippet_length": config.SNIPPET_LENGTH,
        "fallback_enabled": config.ENABLE_FALLBACK,
    }


@router.get("/api/search")
def api_search(
    q: str,
    all_words: bool = False,
    date_start: str = "",
    date_end: str = "",
    limit: int | None = None,
    offset: int = 0,
) -> dict:
    """Поиск для внешних клиентов локальной сети."""
    params = SearchParams(
        q=q, all_words=all_words, date_start=date_start, date_end=date_end
    )
    outcome = search_engine.search(params, offset=offset, limit=limit)

    return {
        "total": outcome.total,
        "mode": outcome.mode,
        "fallback": outcome.fallback,
        "known_terms": list(outcome.known_terms),
        "unknown_terms": list(outcome.unknown_terms),
        "results": [
            {
                "doc_id": hit.doc_id,
                "position": hit.position,
                "title": hit.title,
                "rank": round(hit.rank, 6),
                "matched_words": list(hit.matched_words),
                "keywords": hit.keywords,
                "date": hit.date,
                "url": f"/documents/{hit.doc_id}",
            }
            for hit in outcome.hits
        ],
    }


def _mark(
    conn: sqlite3.Connection, params: SearchParams, doc_ids: list[int], relevant: bool
) -> int:
    """Сохраняет отметки; повтор при гонке с переиндексацией выполняет слой данных."""
    try:
        return db.mark_relevance(conn, params, doc_ids, relevant)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                "Коллекция переиндексирована во время запроса. "
                "Обновите страницу и повторите отметку."
            ),
        ) from exc


@router.post("/api/relevance")
def api_relevance(req: RelevanceRequest, conn: DbConn) -> dict:
    return {
        "query_id": _mark(conn, req.params, [req.doc_id], req.relevant)
    }


@router.post("/api/relevance-batch")
def api_relevance_batch(req: BatchRelevanceRequest, conn: DbConn) -> dict:
    return {
        "query_id": _mark(conn, req.params, req.doc_ids, req.relevant)
    }


@router.post("/api/select-all")
def api_select_all(params: SearchParams, conn: DbConn) -> dict:
    """Отмечает все найденные документы как релевантные.

    Внимание: при такой разметке полнота и точность становятся равными 1,
    поэтому оценка теряет смысл. Режим предназначен для быстрой проверки
    механизма расчёта метрик, а не для получения итоговых результатов.
    """
    query_id = db.ensure_query(conn, params)
    ranked = search_engine.ranked_doc_ids(params)
    db.set_relevance(conn, query_id, ranked, True)

    return {"query_id": query_id, "count": len(ranked)}


@router.post("/api/deselect-all")
def api_deselect_all(params: SearchParams, conn: DbConn) -> dict:
    query_id = db.ensure_query(conn, params)
    db.clear_relevance(conn, query_id)
    return {"query_id": query_id}


@router.post("/api/save-metrics")
def api_save_metrics(params: SearchParams, conn: DbConn) -> dict:
    """Вычисляет и сохраняет оценки качества поиска для запроса."""
    query_id = db.ensure_query(conn, params)
    relevant = db.relevant_doc_ids(conn, query_id)
    ranked = search_engine.ranked_doc_ids(params)

    metrics: Metrics | None = compute_metrics(ranked, relevant)
    if metrics is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "Для этого запроса не отмечено ни одного релевантного документа. "
                "Согласно методике РОМИП такие запросы не участвуют в оценке."
            ),
        )

    db.save_metrics(conn, query_id, metrics)

    return {
        "query_id": query_id,
        "total_found": metrics.total_found,
        "total_relevant": metrics.total_relevant,
        "found_relevant": metrics.found_relevant,
        "recall": metrics.recall,
        "precision": metrics.precision,
        "f_measure": metrics.f_measure,
        "avg_prec": metrics.avg_prec,
        "p5": metrics.p5,
        "p10": metrics.p10,
        "r_prec": metrics.r_prec,
        "pr_curve": list(metrics.pr_curve),
    }


@router.get("/api/metrics")
def api_metrics(
    conn: DbConn, offset: int = 0, limit: int = 100
) -> dict:
    rows = db.metrics_rows(conn, limit, offset)
    return {
        "rows": [dict(row) for row in rows],
        "total": db.metrics_count(conn),
        "summary": _summary_payload(db.metrics_summary(conn)),
    }


@router.get("/api/metrics/summary")
def api_metrics_summary(conn: DbConn) -> dict:
    return _summary_payload(db.metrics_summary(conn))


@router.get("/api/pr-curve/{query_id}")
def api_pr_curve(query_id: int, conn: DbConn) -> dict:
    """Данные графика: интерполированная кривая и фактические срезы выдачи."""
    data = db.pr_curve_data(conn, query_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Оценка для запроса не сохранена")
    return data


def _summary_payload(summary) -> dict:
    """Представление сводных показателей для JSON-клиентов."""
    return {
        "total_queries": summary.total_queries,
        "macro": summary.macro,
        "micro": summary.micro,
        "avg_pr_curve": list(summary.avg_pr_curve),
    }
