"""Страницы, JSON API и экспорт результатов"""

from __future__ import annotations

import csv
import dataclasses
import io
import json
import logging
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from . import config, corpus, detector, recognition
from .domain import SuiteResult

log = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory=str(config.BASE_DIR / "templates"))


# ---------------------------------------------------------------------------
# Вспомогательные
# ---------------------------------------------------------------------------
def _suite_result(suite: str) -> SuiteResult:
    try:
        return recognition.run_suite(suite)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _split_doc_id(doc_id: str) -> tuple[str, str]:
    suite, _, stem = doc_id.partition("/")
    if not _:
        raise HTTPException(status_code=404, detail=f"некорректный идентификатор: {doc_id}")
    return suite, stem


def _report_payload(report) -> dict:
    return {
        "method": report.method,
        "total": report.total,
        "correct": report.correct,
        "accuracy": report.accuracy,
        "per_lang": report.per_lang,
        "confusion": report.confusion,
        "time_median_ms": report.time_median_ms,
        "time_total_ms": report.time_total_ms,
        "errors": report.errors,
    }


def _common_context(request: Request, **extra) -> dict:
    context = {
        "lang_names": config.LANG_NAMES,
        "method_names": config.METHOD_NAMES,
        "methods": config.METHODS,
    }
    context.update(extra)
    return context


# ---------------------------------------------------------------------------
# Страницы
# ---------------------------------------------------------------------------
@router.get("/")
def home(request: Request) -> Response:
    suites = []
    for name, docs in recognition.suites_documents():
        cached = recognition.cached(name)
        suites.append(
            {
                "name": name,
                "count": len(docs),
                "done": cached is not None,
                "reports": cached.reports if cached else None,
            }
        )
    return templates.TemplateResponse(
        request=request,
        name="detect.html",
        context=_common_context(request, suites=suites, adhoc=None),
    )


@router.post("/text")
def recognize_text(request: Request, text: Annotated[str, Form()]) -> Response:
    """Разовое распознавание произвольного текста из формы."""
    results = recognition.recognize_text(text) if text.strip() else []
    return templates.TemplateResponse(
        request=request,
        name="detect.html",
        context=_common_context(
            request,
            suites=[
                {"name": n, "count": len(d), "done": recognition.cached(n) is not None,
                 "reports": recognition.cached(n).reports if recognition.cached(n) else None}
                for n, d in recognition.suites_documents()
            ],
            adhoc={"text": text, "results": results},
        ),
    )


@router.post("/recognize")
def recognize(suite: Annotated[str, Form()]) -> RedirectResponse:
    recognition.run_suite(suite, force=True)
    log.info("Набор %s перераспознан", suite)
    return RedirectResponse(f"/results?suite={suite}", status_code=303)


@router.post("/rescan")
def rescan() -> RedirectResponse:
    """Перечитать коллекцию и перестроить ПОЯ (после замены файлов)."""
    recognition.reset_cache()
    detector.get_detector.cache_clear()
    return RedirectResponse("/", status_code=303)


@router.get("/results")
def results_page(request: Request, suite: str = "main") -> Response:
    result = _suite_result(suite)
    chart = {
        "labels": [config.METHOD_NAMES[m] for m in config.METHODS],
        "accuracy": [
            round((result.reports[m].accuracy or 0.0) * 100, 2) for m in config.METHODS
        ],
        "time": [round(result.reports[m].time_median_ms, 3) for m in config.METHODS],
    }
    return templates.TemplateResponse(
        request=request,
        name="results.html",
        context=_common_context(
            request,
            suite=suite,
            result=result,
            chart=json.dumps(chart),
            suites=recognition.suites_documents(),
        ),
    )


@router.get("/doc/{doc_id:path}")
def document_page(request: Request, doc_id: str) -> Response:
    suite, stem = _split_doc_id(doc_id)
    result = _suite_result(suite)
    doc = next((d for d in result.documents if d.name == f"{stem}.html"), None)
    if doc is None:
        raise HTTPException(status_code=404, detail="документ не найден")
    visible, doc = corpus.open_document(doc)
    doc_results = [r for r in result.results if r.doc_id == doc.id]
    return templates.TemplateResponse(
        request=request,
        name="document.html",
        context=_common_context(
            request,
            doc=doc,
            doc_results=doc_results,
            visible=visible,
            suite=suite,
        ),
    )


@router.get("/raw/{doc_id:path}")
def document_raw(doc_id: str) -> FileResponse:
    """Активная ссылка на сам документ: отдаёт исходный .html-файл."""
    suite, stem = _split_doc_id(doc_id)
    result = _suite_result(suite)
    doc = next((d for d in result.documents if d.name == f"{stem}.html"), None)
    if doc is None:
        raise HTTPException(status_code=404, detail="документ не найден")
    return FileResponse(doc.path, media_type="text/html", filename=doc.name)


@router.get("/help")
def help_page(request: Request) -> Response:
    return templates.TemplateResponse(
        request=request, name="help.html", context=_common_context(request)
    )


# ---------------------------------------------------------------------------
# Сохранение в файл (требование методички)
# ---------------------------------------------------------------------------
def _attachment(content: str, filename: str, media_type: str) -> Response:
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export.csv")
def export_csv(suite: str = "main") -> Response:
    result = _suite_result(suite)
    buf = io.StringIO()
    writer = csv.writer(buf)
    header = ["suite", "file", "lang_true", "chars", "encoding"]
    for method in config.METHODS:
        header += [f"{method}_lang", f"{method}_distance", f"{method}_ms"]
    writer.writerow(header)
    by_doc: dict[str, dict[str, object]] = {}
    for res in result.results:
        by_doc.setdefault(res.doc_id, {})[res.method] = res
    for doc in result.documents:
        row = [doc.suite, doc.name, doc.lang_true, doc.chars, doc.encoding]
        for method in config.METHODS:
            res = by_doc.get(doc.id, {}).get(method)
            row += [res.lang or "", round(res.distance, 6), round(res.elapsed_ms, 3)] if res else ["", "", ""]
        writer.writerow(row)
    return _attachment(buf.getvalue(), f"lab2-{suite}.csv", "text/csv; charset=utf-8")


@router.get("/export.json")
def export_json(suite: str = "main") -> Response:
    result = _suite_result(suite)
    payload = {
        "suite": suite,
        "documents": [
            {
                "id": d.id,
                "file": d.name,
                "lang_true": d.lang_true,
                "chars": d.chars,
                "encoding": d.encoding,
                "results": {
                    r.method: {
                        "lang": r.lang,
                        "distance": r.distance,
                        "elapsed_ms": r.elapsed_ms,
                        "ranked": list(r.ranked),
                        "error": r.error,
                    }
                    for r in result.results
                    if r.doc_id == d.id
                },
            }
            for d in result.documents
        ],
        "reports": {m: _report_payload(result.reports[m]) for m in config.METHODS},
        "pairs": [dataclasses.asdict(p) for p in result.pairs],
    }
    return _attachment(
        json.dumps(payload, ensure_ascii=False, indent=2),
        f"lab2-{suite}.json",
        "application/json; charset=utf-8",
    )


@router.get("/export.txt")
def export_txt(suite: str = "main") -> Response:
    result = _suite_result(suite)
    lines = [
        f"Распознавание языка текста — набор {suite}",
        f"Документов: {len(result.documents)}",
        "",
    ]
    for method in config.METHODS:
        report = result.reports[method]
        acc = f"{report.accuracy * 100:.1f}%" if report.accuracy is not None else "—"
        lines += [
            f"Метод: {config.METHOD_NAMES[method]}",
            f"  точность {acc} ({report.correct} из {report.total}), "
            f"медиана времени {report.time_median_ms:.3f} мс, сбоев {report.errors}",
        ]
        for lang in config.LANGS:
            correct, total = report.per_lang.get(lang, (0, 0))
            lines.append(f"    {config.LANG_NAMES[lang]:12s} {correct}/{total}")
        lines.append("")
    lines.append("Пары методов (совпадение ответов / точности / медианы времени):")
    for pair in result.pairs:
        lines.append(
            f"  {pair.first} vs {pair.second}: {pair.agreement * 100:.1f}% / "
            f"{(pair.accuracy_first or 0) * 100:.1f}% и {(pair.accuracy_second or 0) * 100:.1f}% / "
            f"{pair.time_first_ms:.3f} и {pair.time_second_ms:.3f} мс"
        )
    lines += ["", "Документы:"]
    by_doc: dict[str, dict[str, object]] = {}
    for res in result.results:
        by_doc.setdefault(res.doc_id, {})[res.method] = res
    for doc in result.documents:
        preds = []
        for method in config.METHODS:
            res = by_doc.get(doc.id, {}).get(method)
            mark = "✓" if res and res.lang == doc.lang_true else "✗"
            preds.append(f"{method}={res.lang}{mark}" if res else f"{method}=—")
        lines.append(f"  {doc.name} ({doc.chars} зн., {doc.encoding}): {', '.join(preds)}")
    return _attachment("\n".join(lines) + "\n", f"lab2-{suite}.txt", "text/plain; charset=utf-8")


# ---------------------------------------------------------------------------
# JSON API
# ---------------------------------------------------------------------------
@router.get("/api/status")
def api_status() -> dict:
    return {
        "suites": {name: len(docs) for name, docs in recognition.suites_documents()},
        "model": str(config.MODEL_PATH),
        "model_exists": config.MODEL_PATH.exists(),
        "train": {lang: str(config.TRAIN_PATH / f"{lang}.txt") for lang in config.LANGS},
    }


@router.get("/api/results")
def api_results(suite: str = "main") -> dict:
    result = _suite_result(suite)
    return {
        "suite": suite,
        "reports": {m: _report_payload(result.reports[m]) for m in config.METHODS},
        "pairs": [dataclasses.asdict(p) for p in result.pairs],
        "documents": [
            {
                "id": d.id,
                "file": d.name,
                "lang_true": d.lang_true,
                "chars": d.chars,
                "url": f"/doc/{d.id}",
                "raw_url": f"/raw/{d.id}",
                "preds": {
                    r.method: r.lang
                    for r in result.results
                    if r.doc_id == d.id
                },
            }
            for d in result.documents
        ],
    }
