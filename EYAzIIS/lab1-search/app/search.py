from __future__ import annotations

import logging
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field

from . import config
from .db import connect
from .domain import Hit, SearchOutcome, SearchParams
from .text import QueryTerms, make_snippet, parse_query

log = logging.getLogger(__name__)


def _placeholders(count: int) -> str:
    return ",".join("?" * count)


@dataclass(frozen=True, slots=True)
class Retrieval:
    """Результат логического отбора и ранжирования (без текстов документов).

    Пустой выдаче соответствует значение по умолчанию — все поля-контейнеры
    пусты, поэтому отдельный конструктор «пустого результата» не нужен.
    """

    query: QueryTerms = field(default_factory=QueryTerms)
    ranked: list[int] = field(default_factory=list)
    score: dict[int, float] = field(default_factory=dict)
    matched: dict[int, list[str]] = field(default_factory=dict)
    mode: str = "and"                    # фактическая логика: "and" или "or"
    fallback: bool = False               # сработала ли стратегия с отказами
    known: list[str] = field(default_factory=list)     # термины, найденные в словаре
    unknown: list[str] = field(default_factory=list)   # термины, отсутствующие в словаре


def search(
    params: SearchParams, *, offset: int = 0, limit: int | None = None
) -> SearchOutcome:
    """Выполняет поиск и формирует страницу выдачи.

    Сниппеты строятся только для документов текущей страницы, поэтому
    стоимость запроса не зависит от общего числа найденных документов.
    """
    with connect() as conn:
        retrieval = retrieve(conn, params)
        window = (
            retrieval.ranked[offset:]
            if limit is None
            else retrieval.ranked[offset : offset + limit]
        )
        hits = _build_hits(conn, retrieval, window, offset)

    return SearchOutcome(
        hits=hits,
        total=len(retrieval.ranked),
        doc_ids=tuple(retrieval.ranked),
        mode=retrieval.mode,
        fallback=retrieval.fallback,
        known_terms=tuple(retrieval.known),
        unknown_terms=tuple(retrieval.unknown),
    )


def ranked_doc_ids(params: SearchParams) -> tuple[int, ...]:
    """Полный ранжированный список идентификаторов — вход для оценки качества."""
    with connect() as conn:
        return tuple(retrieve(conn, params).ranked)


# ---------------------------------------------------------------------------
# Логический отбор
# ---------------------------------------------------------------------------
def retrieve(conn: sqlite3.Connection, params: SearchParams) -> Retrieval:
    """Отбирает документы по булеву условию и упорядочивает их по релевантности."""
    query = parse_query(params.q)
    if query.is_empty:
        return Retrieval(query=query)

    term_ids = _lookup_term_ids(conn, query.include_stems + query.exclude_stems)
    known = [stem for stem in query.include_stems if stem in term_ids]
    unknown = [stem for stem in query.include_stems if stem not in term_ids]
    known_words = _display(query, known)
    unknown_words = _display(query, unknown)

    if not known:
        return Retrieval(query=query, unknown=unknown_words)

    postings = _fetch_postings(conn, [term_ids[stem] for stem in known])
    mode, fallback, candidates = _select(params.all_words, postings, unknown)

    candidates = _exclude(candidates, conn, query, term_ids)
    candidates = _filter_by_date(candidates, conn, params)

    if not candidates:
        return Retrieval(query=query, known=known_words, unknown=unknown_words)

    score, matched = _accumulate_weights(postings, candidates)
    ranked = _rank(candidates, score, matched)[: config.MAX_RESULTS]

    return Retrieval(
        query=query,
        ranked=ranked,
        score=score,
        matched=matched,
        mode=mode,
        fallback=fallback,
        known=known_words,
        unknown=unknown_words,
    )


def _select(
    all_words: bool, postings: dict[str, dict[int, float]], unknown: list[str]
) -> tuple[str, bool, set[int]]:
    """Определяет фактическую логику отбора и множество документов-кандидатов.

    Возвращает тройку (режим, сработал ли отказ, кандидаты).
    """
    union = set().union(*postings.values()) if postings else set()

    if not all_words:
        return "or", False, union

    # Терминов нет в словаре коллекции — конъюнкция заведомо пуста,
    # пересечение можно не вычислять.
    conjunction = set() if unknown else _intersect(postings)

    if conjunction:
        return "and", False, conjunction

    if config.ENABLE_FALLBACK and union:
        return "or", True, union

    return "and", False, conjunction


def _intersect(postings: dict[str, dict[int, float]]) -> set[int]:
    """Пересечение списков постингов, начиная с самого короткого."""
    ordered = sorted(postings.values(), key=len)
    result = set(ordered[0])
    for posting in ordered[1:]:
        result &= posting.keys()
        if not result:
            break
    return result


def _accumulate_weights(
    postings: dict[str, dict[int, float]], candidates: set[int]
) -> tuple[dict[int, float], dict[int, list[str]]]:
    """Считает для каждого документа сумму весов A_i^j и набор совпавших терминов."""
    score: dict[int, float] = defaultdict(float)
    matched: dict[int, list[str]] = defaultdict(list)

    for term, posting in postings.items():
        for doc_id, weight in posting.items():
            if doc_id in candidates:
                score[doc_id] += weight
                matched[doc_id].append(term)

    return dict(score), dict(matched)


def _rank(
    candidates: set[int], score: dict[int, float], matched: dict[int, list[str]]
) -> list[int]:
    """Упорядочивает документы по убыванию релевантности (см. докстринг модуля)."""
    return sorted(
        candidates,
        key=lambda doc_id: (
            -len(matched.get(doc_id, ())),
            -score.get(doc_id, 0.0),
            doc_id,
        ),
    )


def _exclude(
    candidates: set[int],
    conn: sqlite3.Connection,
    query: QueryTerms,
    term_ids: dict[str, int],
) -> set[int]:
    """Исключает документы, содержащие запрещённые термины (операция NOT)."""
    if not candidates:
        return candidates

    excluded_ids = [term_ids[stem] for stem in query.exclude_stems if stem in term_ids]
    if not excluded_ids:
        return candidates

    rows = conn.execute(
        f"SELECT DISTINCT doc_id FROM postings WHERE term_id IN ({_placeholders(len(excluded_ids))})",
        excluded_ids,
    )
    return candidates - {row["doc_id"] for row in rows}


def _filter_by_date(
    candidates: set[int], conn: sqlite3.Connection, params: SearchParams
) -> set[int]:
    """Ограничивает выдачу диапазоном дат добавления документов."""
    if not candidates:
        return candidates

    conditions, values = [], []
    if params.date_start:
        conditions.append("date >= ?")
        values.append(params.date_start)
    if params.date_end:
        conditions.append("date <= ?")
        values.append(params.date_end)

    if not conditions:
        return candidates

    rows = conn.execute(
        f"SELECT id FROM documents WHERE {' AND '.join(conditions)}", values
    )
    return candidates & {row["id"] for row in rows}


# ---------------------------------------------------------------------------
# Вспомогательное
# ---------------------------------------------------------------------------
def _lookup_term_ids(conn: sqlite3.Connection, stems: list[str]) -> dict[str, int]:
    unique = list(dict.fromkeys(stems))
    if not unique:
        return {}

    rows = conn.execute(
        f"SELECT id, term FROM terms WHERE term IN ({_placeholders(len(unique))})",
        unique,
    )
    return {row["term"]: row["id"] for row in rows}


def _fetch_postings(
    conn: sqlite3.Connection, term_ids: list[int]
) -> dict[str, dict[int, float]]:
    """Загружает списки постингов запрошенных терминов одним обращением к базе."""
    if not term_ids:
        return {}

    rows = conn.execute(
        f"""
        SELECT t.term AS term, p.doc_id AS doc_id, p.weight AS weight
        FROM postings p
        JOIN terms t ON t.id = p.term_id
        WHERE p.term_id IN ({_placeholders(len(term_ids))})
        """,
        term_ids,
    )

    postings: dict[str, dict[int, float]] = defaultdict(dict)
    for row in rows:
        postings[row["term"]][row["doc_id"]] = row["weight"]
    return dict(postings)


def _display(query: QueryTerms, stems: list[str]) -> list[str]:
    """Возвращает исходные написания терминов для показа пользователю."""
    return [query.include[stem][0] for stem in stems if stem in query.include]


def _build_hits(
    conn: sqlite3.Connection, retrieval: Retrieval, window: list[int], offset: int
) -> list[Hit]:
    """Формирует элементы выдачи для текущего окна пагинации."""
    if not window:
        return []

    rows = conn.execute(
        f"SELECT id, title, text, date, keywords FROM documents WHERE id IN ({_placeholders(len(window))})",
        window,
    )
    documents = {row["id"]: row for row in rows}

    hits: list[Hit] = []
    for index, doc_id in enumerate(window):
        document = documents.get(doc_id)
        if document is None:
            continue

        matched_stems = set(retrieval.matched.get(doc_id, ()))
        hits.append(
            Hit(
                doc_id=doc_id,
                position=offset + index + 1,
                title=document["title"],
                snippet_html=make_snippet(
                    document["text"], matched_stems, config.SNIPPET_LENGTH
                ),
                rank=retrieval.score.get(doc_id, 0.0),
                matched_count=len(matched_stems),
                matched_words=_matched_words(retrieval.query, matched_stems),
                keywords=document["keywords"],
                date=document["date"],
            )
        )

    return hits


def _matched_words(query: QueryTerms, matched_stems: set[str]) -> tuple[str, ...]:
    """Слова запроса, присутствующие в документе (требование методички к выдаче)."""
    words = {
        original for stem in matched_stems for original in query.include.get(stem, ())
    }
    return tuple(sorted(words, key=str.lower))
