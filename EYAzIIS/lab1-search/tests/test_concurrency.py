"""Проверки параллельной работы — целевой сценарий сервера в локальной сети.

К системе одновременно подключаются несколько клиентов: одни выполняют поиск,
другие ставят отметки релевантности. Отдельно проверяется переиндексация
во время клиентских записей.

Эти тесты ловят ошибки, которые не проявляются при последовательных запросах:
передачу sqlite-соединения между потоками пула FastAPI и потерю коллекции
при сбое переиндексации.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient

from app.db import connect, index_info, mark_relevance
from app.domain import SearchParams
from app.indexer import build_index
from app.main import app


@pytest.fixture(scope="module")
def client(sample_index):
    with TestClient(app) as test_client:
        yield test_client


def test_connection_survives_thread_handoff(sample_index):
    """Соединение открывается, используется и закрывается в разных потоках.

    Именно так работает зависимость FastAPI: ``__enter__`` выполняется в одном
    потоке пула, обработчик — в другом, ``__exit__`` — в третьем. Без
    ``check_same_thread=False`` закрытие соединения падает с
    ``sqlite3.ProgrammingError``, причём только при реальной нагрузке.
    """
    state: dict = {}
    stack = ExitStack()

    def open_connection():
        state["conn"] = stack.enter_context(connect())

    def use_connection():
        state["count"] = state["conn"].execute(
            "SELECT COUNT(*) FROM documents"
        ).fetchone()[0]

    def close_connection():
        stack.close()

    for step in (open_connection, use_connection, close_connection):
        thread = threading.Thread(target=step)
        thread.start()
        thread.join()
        assert thread is not None

    assert state["count"] == 5


def test_concurrent_search_requests(client):
    """Поиск из нескольких потоков одновременно."""
    urls = [
        "/api/search?q=cat&all_words=false&limit=5",
        "/api/search?q=cat+dog&all_words=true",
        "/api/search?q=bird&all_words=false",
        "/api/search?q=cat+-dog&all_words=false",
        "/api/status",
        "/metrics",
        "/search?q=cat&all_words=false",
    ]

    def call(index: int) -> int:
        return client.get(urls[index % len(urls)]).status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(call, range(48)))

    assert codes == [200] * 48


def test_concurrent_relevance_marking(client, doc_id_by_name, clean_evaluations):
    """Несколько клиентов одновременно размечают разные запросы."""
    doc_ids = list(doc_id_by_name.values())
    queries = [f"cat {index}" for index in range(6)]

    def mark(query: str) -> int:
        params = {"q": query, "all_words": False, "date_start": "", "date_end": ""}
        for doc_id in doc_ids[:3]:
            response = client.post(
                "/api/relevance",
                json={"params": params, "doc_id": doc_id, "relevant": True},
            )
            assert response.status_code == 200
        return client.post("/api/save-metrics", json=params).status_code

    with ThreadPoolExecutor(max_workers=6) as pool:
        codes = list(pool.map(mark, queries))

    assert codes == [200] * len(queries)

    summary = client.get("/api/metrics/summary").json()
    assert summary["total_queries"] == len(queries)
    assert len(summary["avg_pr_curve"]) == 11

    for query in queries:
        client.post(
            "/api/deselect-all",
            json={"q": query, "all_words": False, "date_start": "", "date_end": ""},
        )


def test_reindex_during_client_writes(sample_index):
    """Переиндексация во время записей клиентов не теряет коллекцию.

    До исправления сбой приводил к ``OperationalError: database is locked``
    в середине удаления таблиц, и в базе оставалось ноль документов.
    """
    errors: list[str] = []
    stop = threading.Event()

    def writer(index: int) -> None:
        params = SearchParams(q=f"cat {index}", all_words=False)
        while not stop.is_set():
            try:
                with connect() as conn:
                    mark_relevance(conn, params, [1, 2], True)
            except Exception as exc:  # noqa: BLE001 — собираем любые сбои
                errors.append(f"{type(exc).__name__}: {exc}")

    threads = [
        threading.Thread(target=writer, args=(index,), daemon=True)
        for index in range(4)
    ]
    for thread in threads:
        thread.start()

    try:
        stats = build_index()
    finally:
        stop.set()
        for thread in threads:
            thread.join(timeout=5)

    assert stats.documents == 5
    assert not errors, f"клиенты получили ошибки: {errors[:3]}"

    with connect() as conn:
        assert index_info(conn)["documents"] == 5
