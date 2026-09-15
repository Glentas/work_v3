"""Коллекция: одинаковый размер документов, сканирование папок, обрезка."""

from __future__ import annotations

from pathlib import Path

from app import config, corpus
from scripts.make_test_docs import cut_exact

REAL_TEST_DIR = Path(__file__).resolve().parent.parent / "corpus" / "test"

STREAM = (
    "un deux trois quatre cinq six sept huit neuf dix " * 40
).strip()


def test_cut_exact_returns_requested_length():
    window = cut_exact(STREAM, 120)
    assert window is not None
    assert len(window) == 120


def test_cut_exact_ends_and_starts_at_word_boundaries():
    window = cut_exact(STREAM, 120)
    assert window[0] != " " and window[-1] != " "
    assert not window.startswith(" ") and not window.endswith(" ")


def test_consecutive_windows_have_no_edge_spaces():
    """Регрессия: окно, начинающееся ровно с начала подстроки, не должно
    получать ведущий пробел — иначе размер видимого текста «плывёт»."""
    from scripts.make_test_docs import windows

    got = windows(STREAM, 120, 5)
    assert len(got) == 5
    for window in got:
        assert len(window) == 120
        assert window[0] != " " and window[-1] != " "


def test_scan_suite_reads_language_from_filename(tmp_path):
    (tmp_path / "fr_01.html").write_text("<p>bonjour</p>", encoding="utf-8")
    (tmp_path / "en_02.html").write_text("<p>hello</p>", encoding="utf-8")
    (tmp_path / "xx_03.html").write_text("<p>???</p>", encoding="utf-8")
    docs = corpus.scan_suite(tmp_path, "unit")
    assert [d.name for d in docs] == ["en_02.html", "fr_01.html"]
    assert {d.lang_true for d in docs} == {"fr", "en"}


def test_open_document_fills_chars_and_encoding(tmp_path):
    path = tmp_path / "fr_01.html"
    path.write_text(
        "<html><head><meta charset='utf-8'></head><body>"
        "<nav>x</nav><article><p>" + "bonjour " * 10 + "</p></article></body></html>",
        encoding="utf-8",
    )
    doc = corpus.scan_suite(tmp_path, "unit")[0]
    visible, filled = corpus.open_document(doc)
    assert filled.encoding == "utf-8"
    assert filled.chars == len(visible) == len(("bonjour " * 10).strip())


def test_real_collection_documents_have_equal_size():
    """Требование методички: входные документы одинакового размера."""
    if not REAL_TEST_DIR.exists():
        import pytest

        pytest.skip("тестовая коллекция не собрана")
    docs = corpus.scan_suite(REAL_TEST_DIR, "main")
    sizes = {len(corpus.open_document(d)[0]) for d in docs}
    assert len(sizes) == 1
    assert sizes.pop() == config.DOC_CHARS
