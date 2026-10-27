# -*- coding: utf-8 -*-
"""Веб-приложение «Автоматическое реферирование документов» (вариант 7).

FastAPI + Jinja2. Метод: sentence extraction (формуды методички) +
нейросетевой метод (замена технологии OSTIS).
"""
from __future__ import annotations

import html
import os
import time
import uuid

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .core import neural
from .core.collection import (COLLECTION_DIR, UPLOADS_DIR, Collection,
                              detect_lang, load_collection)
from .core.stopwords import DOMAIN_NAMES, LANG_NAMES
from .core.summarizer import SummaryOutput, summarize_document, summarize_text

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="Автоматическое реферирование документов",
              description="Лабораторная работа, вариант 7: "
                          "sentence extraction + нейросетевой метод")
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")),
          name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
templates.env.globals["LANG_NAMES"] = LANG_NAMES
templates.env.globals["DOMAIN_NAMES"] = DOMAIN_NAMES

RESULTS: dict[str, SummaryOutput] = {}
UPLOADS: dict[str, dict] = {}


@app.on_event("startup")
def startup():
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    coll = load_collection()
    # прогрев нейросетевого бэкенда (трансформер или skip-gram)
    neural.get_backend([d.text for d in coll.docs.values()])


def _collection() -> Collection:
    return load_collection()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, error: str = ""):
    coll = _collection()
    return templates.TemplateResponse(
        request, "index.html",
        {"meta": coll.meta, "error": error,
         "backend": neural.get_backend([]).name})


@app.post("/summarize")
async def summarize(
    request: Request,
    source: str = Form(...),                 # collection | upload | paste
    doc_id: str = Form(""),
    file: UploadFile | None = File(None),
    text: str = Form(""),
    title: str = Form(""),
    lang: str = Form("auto"),
    domain: str = Form("cs"),
    n_sentences: int = Form(10),
    use_neural: str = Form("on"),
):
    coll = _collection()
    n_sentences = max(1, min(int(n_sentences), 50))
    use_neural_flag = use_neural == "on"
    backend = neural.get_backend([d.text for d in coll.docs.values()]) \
        if use_neural_flag else None

    if source == "collection":
        if doc_id not in coll.docs:
            raise HTTPException(404, "Документ не найден в коллекции")
        doc = coll.docs[doc_id]
        out = summarize_document(doc, coll.index, n=n_sentences,
                                 use_neural=use_neural_flag, backend=backend,
                                 doc_in_index=True)
    elif source == "upload":
        if file is None or not file.filename:
            return RedirectResponse("/?error=Выберите+файл+для+загрузки",
                                    status_code=303)
        raw = (await file.read()).decode("utf-8", errors="replace")
        did = "up_" + uuid.uuid4().hex[:8]
        os.makedirs(UPLOADS_DIR, exist_ok=True)
        with open(os.path.join(UPLOADS_DIR, did + ".txt"), "w",
                  encoding="utf-8") as f:
            f.write(raw)
        det_lang = lang if lang in LANG_NAMES else detect_lang(raw)
        UPLOADS[did] = {"title": title or file.filename,
                        "lang": det_lang, "domain": domain}
        out = summarize_text(raw, title or file.filename, det_lang, domain,
                             coll.index, n=n_sentences,
                             use_neural=use_neural_flag, backend=backend,
                             doc_id=did)
    else:  # paste
        if not text.strip():
            return RedirectResponse("/?error=Введите+текст+документа",
                                    status_code=303)
        did = "up_" + uuid.uuid4().hex[:8]
        det_lang = lang if lang in LANG_NAMES else detect_lang(text)
        UPLOADS[did] = {"title": title or "Введённый документ",
                        "lang": det_lang, "domain": domain}
        with open(os.path.join(UPLOADS_DIR, did + ".txt"), "w",
                  encoding="utf-8") as f:
            f.write(text)
        out = summarize_text(text, title or "Введённый документ", det_lang,
                             domain, coll.index, n=n_sentences,
                             use_neural=use_neural_flag, backend=backend,
                             doc_id=did)

    rid = "r_" + uuid.uuid4().hex[:10]
    RESULTS[rid] = out
    return RedirectResponse(f"/result/{rid}", status_code=303)


def _source_links(out: SummaryOutput) -> dict:
    local = f"/document/{out.doc_id}"
    return {"local": local, "original": out.source_url or None}


@app.get("/result/{rid}", response_class=HTMLResponse)
async def result(request: Request, rid: str):
    out = RESULTS.get(rid)
    if out is None:
        raise HTTPException(404, "Результат не найден (перезапустите обработку)")
    return templates.TemplateResponse(
        request, "result.html",
        {"out": out, "rid": rid, "links": _source_links(out)})


@app.get("/result/{rid}/download")
async def download(rid: str, fmt: str = "txt"):
    out = RESULTS.get(rid)
    if out is None:
        raise HTTPException(404, "Результат не найден")
    safe_title = "".join(c for c in out.title if c.isalnum() or c in " -_")[:60]
    if fmt == "txt":
        body = render_txt(out)
        media = "text/plain; charset=utf-8"
        ext = "txt"
    elif fmt == "html":
        body = render_html(out)
        media = "text/html; charset=utf-8"
        ext = "html"
    else:
        raise HTTPException(400, "Неизвестный формат")
    return Response(
        content=body, media_type=media,
        headers={"Content-Disposition":
                 f'attachment; filename="referat_{safe_title}.{ext}"'})


def render_txt(out: SummaryOutput) -> str:
    lines = [f"РЕФЕРАТ ДОКУМЕНТА: {out.title}",
             f"Язык: {LANG_NAMES.get(out.lang, out.lang)}; "
             f"область: {DOMAIN_NAMES.get(out.domain, out.domain)}",
             f"Источник: {out.source_url or '/document/' + out.doc_id}",
             f"Нейросетевой бэкенд: {out.neural_backend}"
             f"{' (применён)' if out.neural_used else ' (отключён)'}",
             f"Время обработки: {out.elapsed_ms:.0f} мс; "
             f"сжатие: {out.compression:.1%}",
             "",
             "1. КЛАССИЧЕСКИЙ РЕФЕРАТ",
             ""]
    for i, s in enumerate(out.sentences, 1):
        lines.append(f"{i}. {s['text']}")
    lines += ["", "2. РЕФЕРАТ В ВИДЕ СПИСКА КЛЮЧЕВЫХ СЛОВ", ""]
    for node in out.keywords:
        lines.append(f"- {node['term']}  (TF-IDF={node['weight']:.2f}, "
                     f"частота={node['count']})")
        for ch in node["children"]:
            mark = "~" if ch["kind"] == "semantic" else "-"
            lines.append(f"    {mark} {ch['term']}  "
                         f"(вес={ch['weight']:.2f}, частота={ch['count']})")
    return "\n".join(lines) + "\n"


def render_html(out: SummaryOutput) -> str:
    e = html.escape
    parts = [
        "<!DOCTYPE html><html lang='ru'><head><meta charset='utf-8'>",
        f"<title>Реферат: {e(out.title)}</title>",
        "<style>body{font-family:Georgia,serif;max-width:800px;margin:40px auto;"
        "line-height:1.55}h1{font-size:1.5em}h2{font-size:1.2em;margin-top:2em}"
        "li{margin:.4em 0}ul.tree{list-style:none}ul.tree ul{list-style:none;"
        "padding-left:1.4em;border-left:1px dashed #999}.meta{color:#555;"
        "font-size:.9em}</style></head><body>",
        f"<h1>Реферат документа «{e(out.title)}»</h1>",
        f"<p class='meta'>Язык: {LANG_NAMES.get(out.lang, out.lang)}; "
        f"область: {DOMAIN_NAMES.get(out.domain, out.domain)}<br>"
        f"Источник: <a href='{e(out.source_url or '')}'>"
        f"{e(out.source_url or 'локальная копия')}</a><br>"
        f"Предложений в реферате: {len(out.sentences)}; "
        f"сжатие: {out.compression:.1%}; время: {out.elapsed_ms:.0f} мс</p>",
        "<h2>1. Классический реферат</h2><ol>",
    ]
    parts += [f"<li>{e(s['text'])}</li>" for s in out.sentences]
    parts.append("</ol><h2>2. Реферат в виде списка ключевых слов</h2><ul class='tree'>")
    for node in out.keywords:
        parts.append(f"<li><b>{e(node['term'])}</b>")
        if node["children"]:
            parts.append("<ul>")
            for ch in node["children"]:
                parts.append(f"<li>{e(ch['term'])}</li>")
            parts.append("</ul>")
        parts.append("</li>")
    parts.append("</ul></body></html>")
    return "\n".join(parts)


@app.get("/document/{did}", response_class=HTMLResponse)
async def document(request: Request, did: str):
    coll = _collection()
    if did in coll.docs:
        doc = coll.docs[did]
        meta = next((m for m in coll.meta if m["id"] == did), None)
        title, lang, domain, src = doc.title, doc.lang, doc.domain, doc.source_url
        text = doc.text
        chars = meta["chars"] if meta else doc.length
    elif did in UPLOADS:
        info = UPLOADS[did]
        path = os.path.join(UPLOADS_DIR, did + ".txt")
        if not os.path.exists(path):
            raise HTTPException(404, "Файл не найден")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        title, lang, domain, src = info["title"], info["lang"], info["domain"], ""
        chars = len(text)
    else:
        raise HTTPException(404, "Документ не найден")
    return templates.TemplateResponse(
        request, "document.html",
        {"did": did, "title": title, "lang": lang, "domain": domain,
         "src": src, "text": text, "chars": chars})


@app.get("/help", response_class=HTMLResponse)
async def help_page(request: Request):
    return templates.TemplateResponse(request, "help.html", {})


@app.get("/api/collection")
async def api_collection():
    coll = _collection()
    return {"documents": coll.meta, "db_size": coll.index.db_size}


@app.get("/api/summarize/{doc_id}")
async def api_summarize(doc_id: str, n: int = 10, use_neural: bool = True):
    coll = _collection()
    if doc_id not in coll.docs:
        raise HTTPException(404, "Документ не найден")
    backend = neural.get_backend([d.text for d in coll.docs.values()])
    out = summarize_document(coll.docs[doc_id], coll.index, n=n,
                             use_neural=use_neural, backend=backend,
                             doc_in_index=True)
    rid = "r_" + uuid.uuid4().hex[:10]
    RESULTS[rid] = out
    return {"result_id": rid,
            "sentences": out.sentences,
            "keywords": out.keywords,
            "elapsed_ms": out.elapsed_ms,
            "neural_backend": out.neural_backend}


@app.get("/health")
async def health():
    return {"status": "ok",
            "backend": neural.get_backend([]).name,
            "collection_size": len(_collection().docs)}
