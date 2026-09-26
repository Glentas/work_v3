"""Страницы системы, JSON API и экспорт результатов.

Маршруты:
* ``/``              — перевод текста (ввод, файл, режим, демо-тексты);
* ``/results``       — результаты сессии: перевод, статистика, вкладка 1
                       (частотный список) и вкладка 2 (дерево разбора);
* ``/history``       — сохранённые сессии перевода;
* ``/dictionary``    — словарь: просмотр, корректировка, утилита
                       автоматического пополнения, импорт/экспорт CSV;
* ``/export.txt``    — сохранение результатов в TXT (Unicode);
* ``/api/translate`` — JSON API перевода;
* ``/help``          — справка.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from . import analysis, config, db, dictionary, exporter, translator, tree
from .domain import TranslationResult

log = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory=str(config.BASE_DIR / "templates"))


# ---------------------------------------------------------------------------
# Вспомогательные
# ---------------------------------------------------------------------------
def _common_context(request: Request, **extra) -> dict:
    context = {
        "app_title": config.APP_TITLE,
        "app_variant": config.APP_VARIANT,
        "mode_names": config.MODE_NAMES,
        "domain_names": config.DOMAIN_NAMES,
        "domains": config.DOMAINS,
        "source_lang": config.SOURCE_LANG_NAME,
        "target_lang": config.TARGET_LANG_NAME,
    }
    context.update(extra)
    return context


def _require_session(session_id: int) -> TranslationResult:
    result = translator.load_session(session_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Сессия перевода #{session_id} не найдена")
    return result


def _resolve_text(text: str | None, file: UploadFile | None, sample: str | None) -> str:
    """Текст перевода: загруженный файл -> поле ввода -> демо-текст."""
    if file is not None and file.filename:
        raw = file.file.read()
        for encoding in ("utf-8-sig", "utf-8", "cp1251", "latin-1"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise HTTPException(status_code=400, detail="Не удалось определить кодировку файла")
    if text and text.strip():
        return text
    if sample:
        sample_text = translator.sample_text(sample)
        if sample_text is not None:
            return sample_text
    return ""


# ---------------------------------------------------------------------------
# Главная страница: перевод
# ---------------------------------------------------------------------------
@router.get("/")
def home(request: Request, sample: str = "", error: str = "") -> Response:
    text = translator.sample_text(sample) or ""
    return templates.TemplateResponse(
        request=request,
        name="translate.html",
        context=_common_context(
            request,
            samples=translator.samples(),
            prefill=text,
            prefill_sample=sample,
            spacy_ok=analysis.available(),
            dict_total=dictionary.count_entries(),
            dict_by_domain={d: dictionary.count_entries(d) for d in config.DOMAINS},
            unverified=dictionary.count_unverified(),
            error=error,
        ),
    )


@router.post("/translate")
def translate(
    request: Request,
    text: Annotated[str, Form()] = "",
    name: Annotated[str, Form()] = "",
    mode: Annotated[str, Form()] = "transfer",
    sample: Annotated[str, Form()] = "",
    file: Annotated[UploadFile | None, File()] = None,
) -> Response:
    if not analysis.available():
        return RedirectResponse(
            "/?error=Модель+spaCy+не+загружена:+выполните+python+scripts/download_model.py",
            status_code=303,
        )
    source = _resolve_text(text, file, sample)
    if not source.strip():
        return RedirectResponse("/?error=Введите+текст+для+перевода", status_code=303)
    if len(source) > config.MAX_TEXT_CHARS:
        return RedirectResponse(
            f"/?error=Текст+слишком+большой+(максимум+{config.MAX_TEXT_CHARS}+символов)",
            status_code=303,
        )
    result = translator.translate_text(source, name=name.strip(), mode=mode)
    session_id = translator.save_session(result)
    log.info("Сессия #%d: %d слов, покрытие %.1f%%", session_id,
             result.stats.total_words, result.stats.coverage * 100)
    return RedirectResponse(f"/results?id={session_id}", status_code=303)


# ---------------------------------------------------------------------------
# Результаты: перевод, вкладка 1 (частотный список), вкладка 2 (дерево)
# ---------------------------------------------------------------------------
@router.get("/results")
def results(request: Request, id: int, tab: str = "list", sent: int = 0) -> Response:
    result = _require_session(id)
    if tab not in ("list", "tree"):
        tab = "list"
    sent_index = max(0, min(sent, len(result.sentences) - 1)) if result.sentences else 0
    sentence = result.sentences[sent_index] if result.sentences else None
    return templates.TemplateResponse(
        request=request,
        name="results.html",
        context=_common_context(
            request,
            result=result,
            session_id=id,
            tab=tab,
            sent=sent_index,
            sentence=sentence,
            tree_svg=tree.tree_svg(sentence.tokens) if sentence else "",
            tree_text=tree.tree_text(sentence.tokens) if sentence else "",
            token_rows=tree.token_rows(sentence.tokens) if sentence else [],
            unknown_words=translator.unknown_words_of(result),
        ),
    )


@router.get("/history")
def history(request: Request) -> Response:
    return templates.TemplateResponse(
        request=request,
        name="history.html",
        context=_common_context(request, sessions=translator.list_sessions()),
    )


@router.post("/history/delete")
def history_delete(id: Annotated[int, Form()]) -> RedirectResponse:
    translator.delete_session(id)
    return RedirectResponse("/history", status_code=303)


# ---------------------------------------------------------------------------
# Словарь: просмотр, корректировка, утилита пополнения, CSV
# ---------------------------------------------------------------------------
@router.get("/dictionary")
def dictionary_page(
    request: Request,
    q: str = "",
    pos: str = "",
    domain: str = "",
    verified: str = "",
    edit: int = 0,
    msg: str = "",
) -> Response:
    entries = dictionary.list_entries(query=q, pos=pos, domain=domain, verified=verified)
    editing = dictionary.get_entry(edit) if edit else None
    sessions = []
    for session in translator.list_sessions():
        unknown = len(session.stats.unknown)
        if unknown:
            sessions.append({"id": session.id, "name": session.name, "unknown": unknown})
    return templates.TemplateResponse(
        request=request,
        name="dictionary.html",
        context=_common_context(
            request,
            entries=entries,
            editing=editing,
            filters={"q": q, "pos": pos, "domain": domain, "verified": verified},
            total=dictionary.count_entries(),
            by_domain={d: dictionary.count_entries(d) for d in config.DOMAINS},
            unverified=dictionary.count_unverified(),
            replenish_sessions=sessions,
            msg=msg,
            serialize_gram=dictionary.serialize_gram,
        ),
    )


@router.post("/dictionary/add")
def dictionary_add(
    source: Annotated[str, Form()],
    pos: Annotated[str, Form()] = "",
    target: Annotated[str, Form()] = "",
    gram: Annotated[str, Form()] = "",
    domain: Annotated[str, Form()] = "general",
    note: Annotated[str, Form()] = "",
) -> RedirectResponse:
    if not source.strip() or not target.strip():
        return RedirectResponse("/dictionary?msg=Заполните+источник+и+перевод", status_code=303)
    dictionary.add_entry(source, pos, target, dictionary.parse_gram(gram), domain, 1, note)
    return RedirectResponse(f"/dictionary?msg=Запись+«{source.strip()}»+добавлена&q={source.strip()}",
                            status_code=303)


@router.post("/dictionary/update")
def dictionary_update(
    id: Annotated[int, Form()],
    source: Annotated[str, Form()],
    pos: Annotated[str, Form()] = "",
    target: Annotated[str, Form()] = "",
    gram: Annotated[str, Form()] = "",
    domain: Annotated[str, Form()] = "general",
    note: Annotated[str, Form()] = "",
    verified: Annotated[int, Form()] = 1,
) -> RedirectResponse:
    try:
        dictionary.update_entry(id, source, pos, target, dictionary.parse_gram(gram),
                                domain, verified, note)
    except sqlite3.IntegrityError:
        return RedirectResponse(
            "/dictionary?msg=Запись+с+таким+ключом+(источник,+ч.р.,+область)+уже+есть",
            status_code=303,
        )
    return RedirectResponse("/dictionary?msg=Запись+обновлена", status_code=303)


@router.post("/dictionary/delete")
def dictionary_delete(id: Annotated[int, Form()]) -> RedirectResponse:
    dictionary.delete_entry(id)
    return RedirectResponse("/dictionary?msg=Запись+удалена", status_code=303)


@router.post("/dictionary/verify")
def dictionary_verify(id: Annotated[int, Form()]) -> RedirectResponse:
    entry = dictionary.get_entry(id)
    if entry:
        dictionary.update_entry(entry.id or id, entry.source, entry.pos, entry.target,
                                entry.gram, entry.domain, 1, entry.note)
    return RedirectResponse("/dictionary?verified=0&msg=Запись+подтверждена", status_code=303)


@router.post("/dictionary/replenish")
def dictionary_replenish(
    session_id: Annotated[int, Form()] = 0,
    text: Annotated[str, Form()] = "",
    domain: Annotated[str, Form()] = "general",
) -> RedirectResponse:
    """Утилита автоматического пополнения словаря неизвестными словами."""
    if not analysis.available():
        return RedirectResponse("/dictionary?msg=Модель+spaCy+не+загружена", status_code=303)
    unknown: list[tuple[str, str]] = []
    if session_id:
        result = _require_session(session_id)
        unknown = translator.unknown_words_of(result)
    elif text.strip():
        result = translator.translate_text(text, name="Анализ для пополнения словаря")
        unknown = translator.unknown_words_of(result)
    if not unknown:
        return RedirectResponse("/dictionary?msg=Неизвестных+слов+не+найдено", status_code=303)
    if domain == "auto":
        domain = result.domain
    created = dictionary.replenish(unknown, domain)
    return RedirectResponse(
        f"/dictionary?verified=0&msg=Добавлено+записей:+{created}+(требуют+проверки)",
        status_code=303,
    )


@router.get("/dictionary/export.csv")
def dictionary_export() -> Response:
    content = "\ufeff" + dictionary.export_csv()  # BOM: Unicode для Excel/Блокнота
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="dictionary.csv"'},
    )


@router.post("/dictionary/import")
def dictionary_import(file: Annotated[UploadFile, File()]) -> RedirectResponse:
    raw = file.file.read()
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        return RedirectResponse("/dictionary?msg=Не+удалось+прочитать+CSV", status_code=303)
    added, updated = dictionary.import_csv(text)
    return RedirectResponse(
        f"/dictionary?msg=Импорт+CSV:+добавлено+{added},+обновлено+{updated}", status_code=303
    )


# ---------------------------------------------------------------------------
# Экспорт и печать результатов (TXT в кодировке Unicode)
# ---------------------------------------------------------------------------
@router.get("/export.txt")
def export_txt(id: int) -> Response:
    result = _require_session(id)
    content = "\ufeff" + exporter.build_txt(result)  # utf-8-sig — Unicode для Блокнота
    filename = exporter.txt_filename(result)
    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export.json")
def export_json(id: int) -> Response:
    result = _require_session(id)
    return Response(
        content=result.model_dump_json(indent=2),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="perevod_{id}.json"'},
    )


# ---------------------------------------------------------------------------
# JSON API
# ---------------------------------------------------------------------------
@router.post("/api/translate")
def api_translate(payload: dict) -> dict:
    """JSON API: перевод без сохранения сессии (для интеграции и тестов)."""
    text = (payload.get("text") or "").strip()
    mode = payload.get("mode") or "transfer"
    if not text:
        raise HTTPException(status_code=400, detail="пустой текст")
    if not analysis.available():
        raise HTTPException(status_code=503, detail="модель spaCy не загружена")
    result = translator.translate_text(text, name="api", mode=mode)
    return result.model_dump()


@router.get("/api/dictionary")
def api_dictionary(q: str = "", pos: str = "", domain: str = "") -> dict:
    entries = dictionary.list_entries(query=q, pos=pos, domain=domain, limit=100)
    return {
        "total": dictionary.count_entries(),
        "entries": [e.model_dump() for e in entries],
    }


# ---------------------------------------------------------------------------
# Справка
# ---------------------------------------------------------------------------
@router.get("/help")
def help_page(request: Request) -> Response:
    from .grammar import DEP_MAP, POS_MAP, TAG_MAP
    return templates.TemplateResponse(
        request=request,
        name="help.html",
        context=_common_context(
            request,
            tag_map=TAG_MAP,
            dep_map=DEP_MAP,
            pos_map=POS_MAP,
            spacy_ok=analysis.available(),
            dict_total=dictionary.count_entries(),
        ),
    )
