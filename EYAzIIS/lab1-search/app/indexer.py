from __future__ import annotations

import logging
import math
import time
from collections import Counter
from dataclasses import dataclass, field

from . import config
from .collector import RawDocument, collect_documents
from .db import connect, reset_all, transaction
from .text import analyze

log = logging.getLogger(__name__)

#: Размер порции для пакетной вставки в SQLite.
_INSERT_CHUNK = 5000


@dataclass(frozen=True, slots=True)
class IndexStats:
    """Сводка о построенном индексе — для журнала и страницы состояния."""

    documents: int = 0
    terms: int = 0
    postings: int = 0
    seconds: float = 0.0

    @property
    def is_empty(self) -> bool:
        return self.documents == 0

    def describe(self) -> str:
        return (
            f"{self.documents} документов, {self.terms} терминов, "
            f"{self.postings} постингов за {self.seconds:.2f} с"
        )


@dataclass(slots=True)
class ParsedDocument:
    """Документ с готовым поисковым образом."""

    raw: RawDocument
    doc_id: int
    term_freq: Counter[str]     # Q_i^j по каждому термину
    words: int                  # число значимых слов в документе


@dataclass(slots=True)
class Analysis:
    """Результат разбора коллекции."""

    documents: list[ParsedDocument] = field(default_factory=list)
    doc_freq: Counter[str] = field(default_factory=Counter)   # P_i
    display_form: dict[str, str] = field(default_factory=dict)  # стемма -> показываемое слово

    @property
    def total(self) -> int:
        return len(self.documents)


@dataclass(frozen=True, slots=True)
class Dictionary:
    """Словарь терминов с весами."""

    idf: dict[str, float]           # B_i
    term_ids: dict[str, int]
    display_form: dict[str, str]
    total_docs: int                 # N


def build_index() -> IndexStats:
    """Полностью перестраивает индекс по содержимому каталога коллекции."""
    started = time.perf_counter()

    documents = collect_documents(config.COLLECTION_PATH)
    if not documents:
        log.warning("Коллекция пуста: %s", config.COLLECTION_PATH)
        with connect() as conn, transaction(conn):
            reset_all(conn)
        return IndexStats(seconds=time.perf_counter() - started)

    analysis = analyze_documents(documents)
    dictionary = build_dictionary(analysis)
    stats = write_index(analysis, dictionary)

    log.info("Индекс построен: %s", stats.describe())
    return IndexStats(
        documents=stats.documents,
        terms=stats.terms,
        postings=stats.postings,
        seconds=time.perf_counter() - started,
    )


def analyze_documents(documents: list[RawDocument]) -> Analysis:
    """Разбирает тексты: частоты терминов в документах и документные частоты."""
    analysis = Analysis()

    for doc_id, raw in enumerate(documents, start=1):
        term_freq: Counter[str] = Counter()

        for original, term in analyze(raw.text):
            term_freq[term] += 1
            _remember_display_form(analysis.display_form, term, original)

        analysis.documents.append(
            ParsedDocument(
                raw=raw,
                doc_id=doc_id,
                term_freq=term_freq,
                words=sum(term_freq.values()),
            )
        )
        analysis.doc_freq.update(term_freq.keys())

    return analysis


def _remember_display_form(forms: dict[str, str], term: str, original: str) -> None:
    """Запоминает написание термина для показа пользователю"""
    current = forms.get(term)
    if current is None or (not current[0].isupper() and original[0].isupper()):
        forms[term] = original


def build_dictionary(analysis: Analysis) -> Dictionary:
    """Строит словарь: инверсные частоты B_i и идентификаторы терминов."""
    total_docs = analysis.total

    # Термин, встречающийся во всех документах, получает B_i = 0:
    # он не влияет на порядок выдачи, но по-прежнему участвует в логическом
    # отборе документов, что соответствует модели поиска из методички.
    idf = {
        term: math.log(total_docs / df) for term, df in analysis.doc_freq.items()
    }

    # Алфавитный порядок делает идентификаторы терминов детерминированными.
    term_ids = {
        term: index for index, term in enumerate(sorted(analysis.doc_freq), start=1)
    }

    return Dictionary(
        idf=idf,
        term_ids=term_ids,
        display_form=analysis.display_form,
        total_docs=total_docs,
    )


def write_index(analysis: Analysis, dictionary: Dictionary) -> IndexStats:
    """Записывает документы, словарь и postings одной атомарной транзакцией."""
    idf, term_ids = dictionary.idf, dictionary.term_ids

    doc_rows = [
        (
            document.doc_id,
            document.raw.title,
            document.raw.text,
            document.raw.path,
            document.raw.date,
            document.raw.time,
            document.words,
            keywords_of(document, idf, dictionary.display_form),
        )
        for document in analysis.documents
    ]

    term_rows = [
        (term_ids[term], term, df, idf[term])
        for term, df in analysis.doc_freq.items()
    ]

    posting_rows = [
        (term_ids[term], document.doc_id, freq, freq * idf[term])
        for document in analysis.documents
        for term, freq in document.term_freq.items()
    ]

    with connect() as conn, transaction(conn):
        reset_all(conn)
        _insert_many(
            conn,
            """
            INSERT INTO documents (id, title, text, path, date, time, words, keywords)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            doc_rows,
        )
        _insert_many(
            conn,
            "INSERT INTO terms (id, term, df, idf) VALUES (?, ?, ?, ?)",
            term_rows,
        )
        _insert_many(
            conn,
            "INSERT INTO postings (term_id, doc_id, tf, weight) VALUES (?, ?, ?, ?)",
            posting_rows,
        )

    return IndexStats(
        documents=len(doc_rows), terms=len(term_rows), postings=len(posting_rows)
    )


def keywords_of(
    document: ParsedDocument, idf: dict[str, float], display_form: dict[str, str]
) -> str:
    """Ключевые слова документа — термины с наибольшим весом A_i^j (формула 1.6)."""
    ranked = sorted(
        document.term_freq.items(),
        key=lambda item: (item[1] * idf[item[0]], item[0]),
        reverse=True,
    )
    return ", ".join(
        display_form.get(term, term) for term, _ in ranked[: config.TOP_KEYWORDS]
    )


def _insert_many(conn, sql: str, rows: list[tuple]) -> None:
    """Пакетная вставка порциями, чтобы не раздувать память на больших коллекциях."""
    for start in range(0, len(rows), _INSERT_CHUNK):
        conn.executemany(sql, rows[start : start + _INSERT_CHUNK])
