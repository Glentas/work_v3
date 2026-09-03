from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse, FileResponse, JSONResponse
from pathlib import Path

from . import config
from .domain import SearchParams, RelevanceRequest, BatchRelevanceRequest
from .db import (
    get_conn,
    get_query_by_params,
    ensure_query,
    get_relevant_doc_ids,
    set_relevance,
    set_relevance_batch,
    delete_all_relevance,
    save_metrics_for_query,
    get_metrics_summary,
    get_metrics_rows,
    get_metrics_row_count,
    get_pr_curve,
)
from .search import perform_search
from .evaluation import compute_metrics
from .indexer import index_all
from fastapi.templating import Jinja2Templates

router = APIRouter()

templates = Jinja2Templates(directory=str(config.BASE_DIR / "templates"))


@router.get("/")
def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="search.html",
        context={
            "params": SearchParams(),
            "results": None,
            "total": 0,
            "page": 1,
            "total_pages": 0,
            "checked_ids": set(),
            "query_id": 0,
            "per_page": config.PER_PAGE,
        }
    )


@router.get("/search")
def search(
    request: Request,
    q: str = "",
    all_words: bool = False,
    date_start: str = "",
    date_end: str = "",
    page: int = 1,
):
    params = SearchParams(
        q=q,
        all_words=all_words,
        date_start=date_start,
        date_end=date_end,
    )

    results = []
    total = 0
    total_pages = 0
    checked_ids = set()
    query_id = 0

    if q.strip():
        conn = get_conn()
        query_row = get_query_by_params(conn, params)

        if query_row:
            query_id = query_row["id"]
            checked_ids = get_relevant_doc_ids(conn, query_id)

        conn.close()

        offset = (page - 1) * config.PER_PAGE
        results, total = perform_search(
            params,
            limit=config.PER_PAGE,
            offset=offset,
            include_text=True
        )
        total_pages = (total + config.PER_PAGE - 1) // config.PER_PAGE

    return templates.TemplateResponse(
        request=request,
        name="search.html",
        context={
            "params": params,
            "results": results,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "checked_ids": checked_ids,
            "query_id": query_id,
            "per_page": config.PER_PAGE,
        }
    )


@router.get("/documents/{doc_id}")
def document(request: Request, doc_id: int):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM documents WHERE id = ?",
        (doc_id,)
    ).fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Документ не найден")

    return templates.TemplateResponse(
        request=request,
        name="document.html",
        context={
            "doc": row,
        }
    )


@router.get("/documents/{doc_id}/download")
def document_download(doc_id: int):
    conn = get_conn()
    row = conn.execute(
        "SELECT path, title FROM documents WHERE id = ?",
        (doc_id,)
    ).fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Документ не найден")

    path = Path(row["path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Файл не найден на диске")

    # Определяем MIME-тип: PDF открываем в браузере, остальное скачиваем
    if path.suffix.lower() == ".pdf":
        media_type = "application/pdf"
    else:
        media_type = "application/octet-stream"

    return FileResponse(
        path,
        filename=path.name,
        media_type=media_type
    )


@router.get("/metrics")
def metrics_page(request: Request):
    conn = get_conn()
    summary = get_metrics_summary(conn)
    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="metrics.html",
        context={
            "summary": summary,
        }
    )


@router.get("/api/metrics")
def api_metrics(offset: int = 0, limit: int = 100):
    conn = get_conn()
    rows = get_metrics_rows(conn, limit, offset)
    total = get_metrics_row_count(conn)
    conn.close()

    return {
        "rows": rows,
        "total": total,
    }


@router.get("/api/pr-curve/{query_id}")
def api_pr_curve(query_id: int):
    conn = get_conn()
    curve = get_pr_curve(conn, query_id)
    conn.close()
    return curve


@router.post("/api/relevance")
def api_relevance(req: RelevanceRequest):
    conn = get_conn()
    query_id = ensure_query(conn, req.params)
    set_relevance(conn, query_id, req.doc_id, req.relevant)
    conn.close()

    return {"query_id": query_id}


@router.post("/api/relevance-batch")
def api_relevance_batch(req: BatchRelevanceRequest):
    conn = get_conn()
    query_id = ensure_query(conn, req.params)
    set_relevance_batch(conn, query_id, req.doc_ids, req.relevant)
    conn.close()

    return {"query_id": query_id}


@router.post("/api/select-all")
def api_select_all(params: SearchParams):
    conn = get_conn()
    query_id = ensure_query(conn, params)
    conn.close()

    ranked, total = perform_search(
        params,
        limit=None,
        offset=0,
        include_text=False
    )

    conn = get_conn()
    set_relevance_batch(conn, query_id, ranked, True)
    conn.close()

    return {
        "query_id": query_id,
        "count": len(ranked),
    }


@router.post("/api/deselect-all")
def api_deselect_all(params: SearchParams):
    conn = get_conn()
    query_id = ensure_query(conn, params)
    delete_all_relevance(conn, query_id)
    conn.close()

    return {"query_id": query_id}


@router.post("/api/save-metrics")
def api_save_metrics(params: SearchParams):
    conn = get_conn()
    query_id = ensure_query(conn, params)
    relevant_doc_ids = get_relevant_doc_ids(conn, query_id)
    conn.close()

    ranked_doc_ids, total = perform_search(
        params,
        limit=None,
        offset=0,
        include_text=False
    )

    metrics = compute_metrics(ranked_doc_ids, relevant_doc_ids)

    if metrics is None:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Нет релевантных документов для этого запроса. Отметьте хотя бы один документ."
            }
        )

    conn = get_conn()
    save_metrics_for_query(conn, query_id, metrics)
    conn.close()

    return metrics


@router.get("/help")
def help_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="help.html",
        context={}
    )


@router.post("/reindex")
def reindex():
    index_all()
    return RedirectResponse("/", status_code=303)