"""Веб-слой: страницы, активные ссылки, экспорт, печать, справка, форма текста."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app import config, recognition
from app.main import app

FR_BODY = "La forêt près de la rivière est très belle, les chênes et les cèdres poussent côte à côte. " * 8
EN_BODY = "The forest near the river is very beautiful, the oaks and the cedars grow side by side today. " * 8


def _html(body: str, lang_attr: str = "") -> str:
    attr = lang_attr or "fr"
    return (
        f'<html lang="{attr}"><head><meta charset="utf-8"><title>t</title></head>'
        f"<body><nav>x</nav><article><p>{body}</p></article><footer>f</footer></body></html>"
    )


@pytest.fixture()
def client(tmp_path):
    test_dir = config.TEST_PATH
    test_dir.mkdir(parents=True, exist_ok=True)
    (test_dir / "fr_01.html").write_text(_html(FR_BODY), encoding="utf-8")
    (test_dir / "en_01.html").write_text(_html(EN_BODY, "en"), encoding="utf-8")
    # документ с НАМЕРЕННО неверным атрибутом lang: содержимое французское
    (test_dir / "fr_02.html").write_text(_html(FR_BODY, "en"), encoding="utf-8")
    recognition.reset_cache()
    with TestClient(app=app) as c:
        yield c
    recognition.reset_cache()


def test_home_lists_suites(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "main" in response.text


def test_results_page_has_active_links_and_stats(client):
    response = client.get("/results?suite=main")
    assert response.status_code == 200
    assert 'href="/doc/main/fr_01"' in response.text      # активная ссылка на документ
    assert 'href="/raw/main/fr_01"' in response.text      # ссылка на исходный файл
    assert "window.print()" in response.text              # средство распечатки
    assert "/export.csv?suite=main" in response.text      # средство сохранения


def test_results_page_shows_all_methods(client):
    response = client.get("/results?suite=main")
    for name in config.METHOD_NAMES.values():
        assert name in response.text


def test_document_page_shows_distances(client):
    response = client.get("/doc/main/fr_01")
    assert response.status_code == 200
    assert "Расстояни" in response.text or "расстояни" in response.text
    assert "Французский" in response.text


def test_raw_serves_original_html(client):
    response = client.get("/raw/main/fr_01")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "La forêt" in response.text


def test_lang_attribute_is_ignored(client):
    """Язык определяется по содержимому, а не по атрибуту lang разметки:
    у fr_02.html атрибут lang="en", а текст французский."""
    client.post("/recognize", data={"suite": "main"})
    payload = client.get("/api/results?suite=main").json()
    doc = next(d for d in payload["documents"] if d["file"] == "fr_02.html")
    assert doc["lang_true"] == "fr"
    assert doc["preds"]["ngram"] == "fr"
    assert doc["preds"]["alphabet"] == "fr"


def test_export_csv(client):
    response = client.get("/export.csv?suite=main")
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    lines = response.text.strip().splitlines()
    assert lines[0].startswith("suite,file,lang_true")
    assert len(lines) == 4  # заголовок + 3 документа
    assert "fr_01.html" in response.text


def test_export_json(client):
    response = client.get("/export.json?suite=main")
    payload = json.loads(response.text)
    assert payload["suite"] == "main"
    assert {"ngram", "alphabet", "neural"} <= set(payload["reports"])
    assert len(payload["documents"]) == 3


def test_export_txt(client):
    response = client.get("/export.txt?suite=main")
    assert response.status_code == 200
    assert "Метод:" in response.text
    assert "Пары методов" in response.text


def test_help_page(client):
    response = client.get("/help")
    assert response.status_code == 200
    assert "Как работать с системой" in response.text
    assert "fastText" in response.text


def test_adhoc_text_recognition(client):
    response = client.post("/text", data={"text": FR_BODY})
    assert response.status_code == 200
    assert "Французский" in response.text


def test_missing_suite_returns_404(client):
    response = client.get("/results?suite=nope")
    assert response.status_code == 404
