import math
from collections import Counter, defaultdict

from . import config
from .collector import collect_documents
from .text import process_text
from .db import get_conn


def index_all() -> None:
    conn = get_conn()

    # Полная переиндексация.
    # Старые документы, запросы и оценки удаляются,
    # так как после переиндексации идентификаторы документов меняются.
    # ВАЖНО: удаляем сначала дочерние таблицы (с внешними ключами), потом родительские!
    conn.execute("DELETE FROM postings")
    conn.execute("DELETE FROM relevance_marks")
    conn.execute("DELETE FROM query_metrics")
    conn.execute("DELETE FROM queries")
    conn.execute("DELETE FROM documents")
    conn.execute("DELETE FROM terms")
    
    conn.execute(
        """
        UPDATE metrics_summary
        SET total_queries = 0,
            sum_recall = 0,
            sum_precision = 0,
            sum_avg_prec = 0,
            sum_p5 = 0,
            sum_p10 = 0,
            sum_r_prec = 0,
            sum_pr_curve = '[]'
        WHERE id = 1
        """
    )
    conn.commit()

    docs = collect_documents(config.COLLECTION_PATH)
    n_docs = len(docs)

    if n_docs == 0:
        conn.close()
        return

    doc_freq = defaultdict(int)
    term_original = {}
    parsed_docs = []

    for doc in docs:
        pairs = process_text(doc["text"])
        tf = Counter(stem for _, stem in pairs)

        for stem in tf:
            doc_freq[stem] += 1

        for original, stem in pairs:
            if stem not in term_original:
                term_original[stem] = original

        parsed_docs.append((doc, tf))

    term_rows = []
    idf = {}

    for term, df in doc_freq.items():
        value = math.log(n_docs / df)
        idf[term] = value
        term_rows.append((term, df, value))

    conn.executemany(
        "INSERT INTO terms (term, df, idf) VALUES (?, ?, ?)",
        term_rows
    )
    conn.commit()

    term_ids = {
        row["term"]: row["id"]
        for row in conn.execute("SELECT id, term FROM terms")
    }

    post_rows = []

    for doc, tf in parsed_docs:
        cur = conn.execute(
            """
            INSERT INTO documents (title, text, path, date, time, keywords)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                doc["title"],
                doc["text"],
                doc["path"],
                doc["date"],
                doc["time"],
                "",
            )
        )
        doc_id = cur.lastrowid

        top_terms = sorted(
            tf.items(),
            key=lambda item: item[1] * idf[item[0]],
            reverse=True
        )[:config.TOP_KEYWORDS]

        keywords = ", ".join(
            term_original.get(stem, stem)
            for stem, _ in top_terms
        )

        conn.execute(
            "UPDATE documents SET keywords = ? WHERE id = ?",
            (keywords, doc_id)
        )

        for stem, count in tf.items():
            weight = count * idf[stem]
            post_rows.append(
                (term_ids[stem], doc_id, count, weight)
            )

    conn.executemany(
        "INSERT INTO postings (term_id, doc_id, tf, weight) VALUES (?, ?, ?, ?)",
        post_rows
    )

    conn.commit()
    conn.close()