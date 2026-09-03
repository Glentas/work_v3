from collections import defaultdict

from . import config
from .db import get_conn
from .text import parse_query, highlight_snippet


def perform_search(params, limit=None, offset=0, include_text=True):
    """
    Логический поиск с последующим ранжированием.

    Возвращает:
        (результаты, общее количество)

    Если include_text=False, результаты являются списком document_id.
    """
    include_terms, exclude_terms = parse_query(params.q)

    include_stems = list(include_terms.keys())
    exclude_stems = list(exclude_terms.keys())

    if not include_stems:
        return [], 0

    conn = get_conn()

    placeholders = ",".join("?" for _ in include_stems)
    rows = conn.execute(
        f"SELECT id, term FROM terms WHERE term IN ({placeholders})",
        include_stems
    ).fetchall()

    term_id_map = {row["term"]: row["id"] for row in rows}
    present_include = [stem for stem in include_stems if stem in term_id_map]

    if params.all_words and len(present_include) < len(include_stems):
        conn.close()
        return [], 0

    if not present_include:
        conn.close()
        return [], 0

    include_ids = [term_id_map[stem] for stem in present_include]
    placeholders = ",".join("?" for _ in include_ids)

    postings = conn.execute(
        f"SELECT term_id, doc_id, weight FROM postings WHERE term_id IN ({placeholders})",
        include_ids
    ).fetchall()

    doc_terms = defaultdict(set)
    doc_weight = defaultdict(float)

    for row in postings:
        doc_terms[row["doc_id"]].add(row["term_id"])
        doc_weight[row["doc_id"]] += row["weight"]

    if params.all_words:
        required = set(include_ids)
        candidates = {
            doc_id
            for doc_id, terms in doc_terms.items()
            if required.issubset(terms)
        }
    else:
        candidates = set(doc_terms.keys())

    if exclude_stems:
        placeholders_ex = ",".join("?" for _ in exclude_stems)
        ex_rows = conn.execute(
            f"SELECT id FROM terms WHERE term IN ({placeholders_ex})",
            exclude_stems
        ).fetchall()

        ex_ids = [row["id"] for row in ex_rows]

        if ex_ids:
            placeholders_ex_ids = ",".join("?" for _ in ex_ids)
            ex_docs_rows = conn.execute(
                f"SELECT doc_id FROM postings WHERE term_id IN ({placeholders_ex_ids})",
                ex_ids
            ).fetchall()

            ex_docs = {row["doc_id"] for row in ex_docs_rows}
            candidates -= ex_docs

    if params.date_start or params.date_end:
        conditions = []
        values = []

        if params.date_start:
            conditions.append("date >= ?")
            values.append(params.date_start)

        if params.date_end:
            conditions.append("date <= ?")
            values.append(params.date_end)

        sql = f"SELECT id FROM documents WHERE {' AND '.join(conditions)}"
        date_rows = conn.execute(sql, values).fetchall()
        date_docs = {row["id"] for row in date_rows}
        candidates &= date_docs

    if not candidates:
        conn.close()
        return [], 0

    ranked = sorted(
        candidates,
        key=lambda doc_id: (len(doc_terms[doc_id]), doc_weight[doc_id]),
        reverse=True
    )

    if len(ranked) > config.MAX_RESULTS:
        ranked = ranked[:config.MAX_RESULTS]

    total = len(ranked)

    if limit is None:
        page = ranked[offset:]
    else:
        page = ranked[offset:offset + limit]

    if not include_text:
        conn.close()
        return page, total

    placeholders_docs = ",".join("?" for _ in page)
    doc_rows = conn.execute(
        f"""
        SELECT id, title, text, date, keywords
        FROM documents
        WHERE id IN ({placeholders_docs})
        """,
        page
    ).fetchall()

    docs_map = {row["id"]: row for row in doc_rows}

    term_id_to_stem = {
        term_id: stem
        for stem, term_id in term_id_map.items()
    }

    term_id_to_originals = {
        term_id_map[stem]: include_terms[stem]
        for stem in present_include
    }

    results = []

    for doc_id in page:
        doc = docs_map.get(doc_id)
        if not doc:
            continue

        tids = doc_terms[doc_id]

        matched_stems = {
            term_id_to_stem[tid]
            for tid in tids
            if tid in term_id_to_stem
        }

        matched_words = []
        for tid in tids:
            matched_words.extend(term_id_to_originals.get(tid, []))

        matched_words = sorted(set(matched_words))

        snippet_html = highlight_snippet(
            doc["text"],
            matched_stems,
            config.SNIPPET_LENGTH
        )

        results.append(
            {
                "doc_id": doc_id,
                "title": doc["title"],
                "snippet_html": snippet_html,
                "rank": doc_weight[doc_id],
                "date": doc["date"],
                "keywords": doc["keywords"],
                "matched_words": matched_words,
            }
        )

    conn.close()
    return results, total