"""Тесты веб-интерфейса и экспорта (httpx TestClient)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client(spacy_required):
    with TestClient(app) as test_client:
        yield test_client


def test_home_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Перевод текста" in response.text
    assert "Демонстрационные тексты" in response.text


def test_help_page(client):
    response = client.get("/help")
    assert response.status_code == 200
    assert "трансфер" in response.text.lower()
    assert "Penn Treebank" in response.text


def test_dictionary_page(client):
    response = client.get("/dictionary")
    assert response.status_code == 200
    assert "entries" in response.text
    assert "Утилита автоматического пополнения" in response.text


def test_history_page(client):
    response = client.get("/history")
    assert response.status_code == 200


def test_translate_flow_and_results_tabs(client):
    response = client.post(
        "/translate",
        data={"text": "The doctor examined the patient. Many results were published.",
              "name": "web-тест", "mode": "transfer"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith("/results?id=")
    session_id = location.split("=")[1]

    page = client.get(location)
    assert page.status_code == 200
    assert "Врач осмотрел пациента" in page.text
    # Вкладка 1: частотный список с грамматикой.
    assert "Список слов, упорядоченный по частоте" in page.text
    assert "Существительное" in page.text

    # Вкладка 2: дерево разбора.
    tree_page = client.get(f"/results?id={session_id}&tab=tree&sent=0")
    assert tree_page.status_code == 200
    assert "<svg" in tree_page.text
    assert "Дерево синтаксического разбора" in tree_page.text
    assert "Таблица токенов" in tree_page.text

    # История содержит сессию.
    history = client.get("/history")
    assert "web-тест" in history.text


def test_export_txt_unicode(client):
    response = client.post(
        "/translate",
        data={"text": "The doctor examined the patient.", "name": "export-тест",
              "mode": "transfer"},
        follow_redirects=False,
    )
    session_id = response.headers["location"].split("=")[1]
    export = client.get(f"/export.txt?id={session_id}")
    assert export.status_code == 200
    # Кодировка Unicode: UTF-8 с BOM.
    assert export.content.startswith(b"\xef\xbb\xbf")
    text = export.content.decode("utf-8-sig")
    assert "ПЕРЕВОД" in text
    assert "Врач осмотрел пациента" in text
    assert "СПИСОК СЛОВ ПО ЧАСТОТЕ ВСТРЕЧАЕМОСТИ" in text
    assert "Количество слов во входном тексте" in text
    assert "ДЕРЕВЬЯ СИНТАКСИЧЕСКОГО РАЗБОРА" in text


def test_export_json(client):
    response = client.post(
        "/translate",
        data={"text": "The patient received the therapy.", "name": "json-тест"},
        follow_redirects=False,
    )
    session_id = response.headers["location"].split("=")[1]
    export = client.get(f"/export.json?id={session_id}")
    assert export.status_code == 200
    payload = export.json()
    assert payload["stats"]["total_words"] > 0
    assert payload["freq"]


def test_api_translate(client):
    response = client.post("/api/translate", json={"text": "Smoking causes cancer.", "mode": "transfer"})
    assert response.status_code == 200
    payload = response.json()
    assert "вызывает" in payload["translated_text"].lower()
    assert payload["stats"]["coverage"] > 0


def test_dictionary_replenish_and_correction(client):
    # 1. Перевод с неизвестным словом.
    response = client.post(
        "/translate",
        data={"text": "The qqzertol device was examined.", "name": "replenish-тест"},
        follow_redirects=False,
    )
    session_id = response.headers["location"].split("=")[1]

    # 2. Утилита пополнения создаёт запись с пометкой «не проверено».
    response = client.post(
        "/dictionary/replenish",
        data={"session_id": session_id, "text": "", "domain": "auto"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    page = client.get("/dictionary?verified=0")
    assert "qqzertol" in page.text
    assert "требует проверки" in page.text

    # 3. Корректировка: правка перевода и подтверждение записи.
    from app import dictionary
    entry = dictionary.lookup("qqzertol", "NOUN", "med") or dictionary.lookup("qqzertol", "NOUN", "general")
    assert entry is not None and entry.verified == 0
    client.post("/dictionary/update", data={
        "id": entry.id, "source": "qqzertol", "pos": "NOUN",
        "target": "квертоловый прибор", "gram": "m", "domain": entry.domain,
        "note": "", "verified": "1",
    })
    fixed = dictionary.get_entry(entry.id)
    assert fixed.target == "квертоловый прибор"
    assert fixed.verified == 1

    # 4. Удаление записи.
    client.post("/dictionary/delete", data={"id": entry.id})
    assert dictionary.get_entry(entry.id) is None


def test_dictionary_add_and_search(client):
    client.post("/dictionary/add", data={
        "source": "webtestword", "pos": "NOUN", "target": "вебтест",
        "gram": "m", "domain": "general", "note": "",
    })
    page = client.get("/dictionary?q=webtestword")
    assert "webtestword" in page.text
    assert "вебтест" in page.text

    from app import dictionary
    entry = dictionary.lookup("webtestword", "NOUN")
    assert entry is not None
    dictionary.delete_entry(entry.id)


def test_sample_prefill(client):
    response = client.get("/?sample=med_01")
    assert response.status_code == 200
    assert "Clinical trial of a new drug" in response.text


def test_404_session(client):
    response = client.get("/results?id=999999")
    assert response.status_code == 404
