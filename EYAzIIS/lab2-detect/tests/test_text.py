"""Шаг 1: кодировки, HTML-сущности, служебные теги."""

from __future__ import annotations

from pathlib import Path

from app import text

FR = "La forêt près de Genève est très belle: les chênes et les cèdres."


def _html_file(tmp_path: Path, raw: bytes) -> Path:
    path = tmp_path / "doc.html"
    path.write_bytes(raw)
    return path


def _wrap(body: bytes, charset: str | None) -> bytes:
    meta = f'<meta charset="{charset}">'.encode() if charset else b""
    return (
        b"<html><head>" + meta + b"<title>t</title></head><body>"
        b"<nav><a href='/'>x</a></nav><article><p>" + body +
        b"</p></article><footer>bye</footer></body></html>"
    )


def test_utf8_raw_accents(tmp_path):
    visible, encoding = text.read_html(_html_file(tmp_path, _wrap(FR.encode("utf-8"), "utf-8")))
    assert encoding == "utf-8"
    assert "forêt" in visible and "Genève" in visible


def test_windows_1252_with_meta(tmp_path):
    visible, encoding = text.read_html(
        _html_file(tmp_path, _wrap(FR.encode("windows-1252"), "windows-1252"))
    )
    assert encoding == "windows-1252"
    assert "forêt" in visible


def test_latin1_without_meta(tmp_path):
    visible, encoding = text.read_html(_html_file(tmp_path, _wrap(FR.encode("latin-1"), None)))
    assert "forêt" in visible          # перебор кодировок нашёл верную


def test_html_entities_decoded(tmp_path):
    """Без декодирования сущностей алфавитный метод потерял бы диакритику."""
    body = b"La for&ecirc;t pr&egrave;s de Gen&egrave;ve est tr&egrave;s belle."
    visible, _ = text.read_html(_html_file(tmp_path, _wrap(body, None)))
    assert "forêt" in visible and "très" in visible


def test_service_tags_removed_and_spaces_collapsed(tmp_path):
    raw = _wrap("un   texte\n\navec   espaces".encode("utf-8"), "utf-8")
    visible, _ = text.read_html(_html_file(tmp_path, raw))
    assert "nav" not in visible and "bye" not in visible
    assert visible == "un texte avec espaces"


def test_letter_counts_ignore_digits_and_punctuation():
    counts = text.letter_counts("chat 42! CHAT.")
    assert counts["c"] == 2 and counts["h"] == 2 and "4" not in counts
