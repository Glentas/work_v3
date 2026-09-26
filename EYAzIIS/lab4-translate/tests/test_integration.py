"""Интеграционные тесты: полные пользовательские сценарии через HTTP.

Проверяют требования ТЗ сквозным образом: перевод (ввод/файл/демо-текст),
вкладки результатов, статистика, экспорт TXT Unicode и печать, история,
утилита пополнения и корректировки словаря, CSV, JSON API.
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client(spacy_required):
    with TestClient(app) as test_client:
        yield test_client


def _translate(client, text, name="integration", mode="transfer"):
    response = client.post(
        "/translate", data={"text": text, "name": name, "mode": mode},
        follow_redirects=False,
    )
    assert response.status_code == 303
    return response.headers["location"].split("=")[1]


# ---------------------------------------------------------------------------
# Вход: текст, файл (разные кодировки), демо-текст, ограничения
# ---------------------------------------------------------------------------
def test_input_plain_text(client):
    sid = _translate(client, "The doctor examined the patient.", "ввод текста")
    page = client.get(f"/results?id={sid}")
    assert "Врач осмотрел пациента" in page.text


def test_input_uploaded_file_utf8(client):
    files = {"file": ("doc.txt", io.BytesIO("Smoking causes cancer.".encode("utf-8")), "text/plain")}
    response = client.post("/translate", data={"text": "", "name": "файл utf-8", "mode": "transfer"},
                           files=files, follow_redirects=False)
    assert response.status_code == 303
    page = client.get(response.headers["location"])
    assert "Курение вызывает рак" in page.text


def test_input_uploaded_file_cp1251(client):
    text = "The patient received the therapy at the hospital."
    files = {"file": ("doc.txt", io.BytesIO(text.encode("cp1251")), "text/plain")}
    response = client.post("/translate", data={"text": "", "name": "файл cp1251"},
                           files=files, follow_redirects=False)
    assert response.status_code == 303
    page = client.get(response.headers["location"])
    assert "пациент" in page.text.lower()


def test_input_sample_field(client):
    response = client.post("/translate", data={"text": "", "sample": "med_01", "name": "демо"},
                           follow_redirects=False)
    assert response.status_code == 303
    page = client.get(response.headers["location"])
    assert "Клиническое" in page.text or "клиническ" in page.text.lower()


def test_input_empty_redirects_with_error(client):
    response = client.post("/translate", data={"text": "   ", "name": "", "mode": "transfer"},
                           follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/?error=")


def test_input_too_long_redirects_with_error(client):
    response = client.post("/translate", data={"text": "word " * 100000, "name": ""},
                           follow_redirects=False)
    assert response.status_code == 303
    assert "error" in response.headers["location"]


def test_literal_mode_through_form(client):
    sid = _translate(client, "The doctor examined the patient.", "пословный", mode="literal")
    page = client.get(f"/results?id={sid}")
    assert "Прямой (пословно-оборотный)" in page.text
    assert "осматривать" in page.text


# ---------------------------------------------------------------------------
# Результаты: статистика, вкладки, печать, экспорт
# ---------------------------------------------------------------------------
def test_results_statistics_visible(client):
    sid = _translate(client, "The doctor examined the patient. Many results were published.",
                     "статистика")
    page = client.get(f"/results?id={sid}").text
    assert "Слов в тексте" in page and "Переведено слов" in page
    assert "покрытие" in page
    assert "Неизвестных слов" in page


def test_results_tab1_frequency_list(client):
    sid = _translate(client, "The doctor examined the patient. The patient recovered.",
                     "вкладка1")
    page = client.get(f"/results?id={sid}&tab=list").text
    assert "Вкладка 1" in page
    assert "упорядоченный по частоте встречаемости" in page
    # грамматическая информация: теги и расшифровка (лр. №3)
    assert "VBD" in page and "Глагол, прошедшее время" in page
    assert "nsubj" in page and "Именное подлежащее" in page
    # перевод слова
    assert "врач" in page


def test_results_tab2_tree_and_sentence_switch(client):
    sid = _translate(client, "The doctor examined the patient. The patient recovered.",
                     "вкладка2")
    page0 = client.get(f"/results?id={sid}&tab=tree&sent=0")
    assert "Вкладка 2" in page0.text
    assert "<svg" in page0.text
    assert "Дерево синтаксического разбора" in page0.text
    assert "Структура дерева" in page0.text
    assert "Таблица токенов" in page0.text
    assert "examined" in page0.text

    page1 = client.get(f"/results?id={sid}&tab=tree&sent=1")
    assert "recovered" in page1.text

    # выход за диапазон —Sentence index ограничивается, без падения
    page_clamped = client.get(f"/results?id={sid}&tab=tree&sent=999")
    assert page_clamped.status_code == 200


def test_results_print_button(client):
    sid = _translate(client, "The doctor examined the patient.", "печать")
    page = client.get(f"/results?id={sid}").text
    assert "window.print()" in page
    assert "Печать" in page


def test_export_txt_unicode_bom_and_sections(client):
    sid = _translate(client, "The doctor examined the patient. The zqqomega device works.",
                     "экспорт")
    response = client.get(f"/export.txt?id={sid}")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert response.content.startswith(b"\xef\xbb\xbf")     # UTF-8 BOM = Unicode
    assert "attachment" in response.headers["content-disposition"]
    text = response.content.decode("utf-8-sig")
    assert "ПЕРЕВОД (РУССКИЙ)" in text
    assert "Врач осмотрел пациента" in text
    assert "СПИСОК СЛОВ ПО ЧАСТОТЕ ВСТРЕЧАЕМОСТИ" in text
    assert "Количество слов во входном тексте" in text
    assert "Количество переведённых слов" in text
    assert "zqqomega" in text
    assert "ДЕРЕВЬЯ СИНТАКСИЧЕСКОГО РАЗБОРА" in text


def test_export_json(client):
    sid = _translate(client, "The doctor examined the patient.", "json")
    response = client.get(f"/export.json?id={sid}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["translated_text"]
    assert payload["stats"]["total_words"] == 5
    assert payload["freq"][0]["freq"] >= 1
    assert payload["sentences"][0]["tokens"][0]["tag_ru"]


def test_export_404_for_missing_session(client):
    assert client.get("/export.txt?id=999999").status_code == 404
    assert client.get("/results?id=999999").status_code == 404


# ---------------------------------------------------------------------------
# История сессий
# ---------------------------------------------------------------------------
def test_history_and_delete(client):
    sid = _translate(client, "The doctor examined the patient.", "история-тест")
    page = client.get("/history").text
    assert "история-тест" in page
    response = client.post("/history/delete", data={"id": sid}, follow_redirects=False)
    assert response.status_code == 303
    assert client.get(f"/results?id={sid}").status_code == 404


# ---------------------------------------------------------------------------
# Словарь: утилита пополнения и корректировка (требование ТЗ)
# ---------------------------------------------------------------------------
def test_replenish_from_session_then_correct(client):
    sid = _translate(client, "The zzalpha instrument measured the zzbeta level.", "replenish")
    response = client.post("/dictionary/replenish",
                           data={"session_id": sid, "text": "", "domain": "auto"},
                           follow_redirects=False)
    assert response.status_code == 303
    page = client.get("/dictionary?verified=0").text
    assert "zzalpha" in page and "zzbeta" in page
    assert "требует проверки" in page

    from app import dictionary
    entry = dictionary.lookup("zzalpha", "NOUN", "med") or dictionary.lookup("zzalpha", "NOUN")
    assert entry is not None and entry.verified == 0
    assert entry.target  # предложение перевода (транслитерация)

    # корректировка: правка перевода и подтверждение
    client.post("/dictionary/update", data={
        "id": entry.id, "source": entry.source, "pos": entry.pos,
        "target": "альфа-прибор", "gram": "m", "domain": entry.domain,
        "note": "проверено оператором", "verified": "1"})
    fixed = dictionary.get_entry(entry.id)
    assert fixed.target == "альфа-прибор" and fixed.verified == 1

    # после корректировки слово переводится
    sid2 = _translate(client, "The zzalpha instrument works.", "after fix")
    page2 = client.get(f"/results?id={sid2}").text
    assert "альфа-прибор" in page2

    # удаление
    client.post("/dictionary/delete", data={"id": entry.id})
    assert dictionary.get_entry(entry.id) is None
    other = dictionary.lookup("zzbeta", "NOUN", "med") or dictionary.lookup("zzbeta", "NOUN")
    if other:
        client.post("/dictionary/delete", data={"id": other.id})


def test_replenish_from_new_text(client):
    response = client.post("/dictionary/replenish",
                           data={"session_id": "0", "text": "The qqgamma scope is new.",
                                 "domain": "med"},
                           follow_redirects=False)
    assert response.status_code == 303
    assert "Добавлено" in response.headers["location"] or "msg=" in response.headers["location"]
    from app import dictionary
    entry = dictionary.lookup("qqgamma", "NOUN", "med")
    assert entry is not None and entry.verified == 0
    dictionary.delete_entry(entry.id)


def test_replenish_nothing_new(client):
    response = client.post("/dictionary/replenish",
                           data={"session_id": "0", "text": "The doctor examined the patient.",
                                 "domain": "auto"},
                           follow_redirects=False)
    assert response.status_code == 303
    assert "msg=" in response.headers["location"]


def test_dictionary_edit_form_page(client):
    from app import dictionary
    entry = dictionary.lookup("doctor", "NOUN", "med") or dictionary.lookup("doctor", "NOUN")
    assert entry is not None
    page = client.get(f"/dictionary?edit={entry.id}")
    assert page.status_code == 200
    assert f'Правка записи #{entry.id}' in page.text
    assert "врач" in page.text


def test_dictionary_update_duplicate_key_graceful(client):
    from app import dictionary
    a = dictionary.add_entry("dupkey1", "NOUN", "первый", {}, "general")
    b = dictionary.add_entry("dupkey2", "NOUN", "второй", {}, "general")
    # правка b в ключ a — конфликт UNIQUE не должен ронять сервер
    response = client.post("/dictionary/update", data={
        "id": b.id, "source": "dupkey1", "pos": "NOUN", "target": "конфликт",
        "gram": "", "domain": "general", "note": "", "verified": "1"},
        follow_redirects=False)
    assert response.status_code == 303
    dictionary.delete_entry(a.id)
    dictionary.delete_entry(b.id)


def test_csv_export_import_roundtrip(client):
    from app import dictionary
    entry = dictionary.add_entry("csvroundtrip", "NOUN", "исходный перевод", {"gender": "m"},
                                 "general", 1, "заметка")
    exported = client.get("/dictionary/export.csv")
    assert exported.status_code == 200
    content = exported.content.decode("utf-8-sig")
    assert "csvroundtrip" in content and "исходный перевод" in content

    patched = content.replace("исходный перевод", "изменённый перевод")
    files = {"file": ("dict.csv", io.BytesIO(patched.encode("utf-8")), "text/csv")}
    response = client.post("/dictionary/import", files=files, follow_redirects=False)
    assert response.status_code == 303
    updated = dictionary.get_entry(entry.id)
    assert updated.target == "изменённый перевод"
    assert updated.gram.get("gender") == "m"   # грамматика пережила roundtrip
    assert updated.note == "заметка"
    dictionary.delete_entry(entry.id)


# ---------------------------------------------------------------------------
# JSON API
# ---------------------------------------------------------------------------
def test_api_translate_both_modes(client):
    response = client.post("/api/translate", json={"text": "The doctor examined the patient.",
                                                   "mode": "transfer"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["translated_text"] == "Врач осмотрел пациента."
    assert payload["stats"]["total_words"] == 5
    assert payload["domain"] in ("general", "med", "art")

    response = client.post("/api/translate", json={"text": "The doctor examined the patient.",
                                                   "mode": "literal"})
    assert response.json()["mode"] == "literal"


def test_api_translate_empty_400(client):
    assert client.post("/api/translate", json={"text": ""}).status_code == 400


def test_api_dictionary(client):
    response = client.get("/api/dictionary?q=doctor")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] > 100
    assert any(e["source"] == "doctor" for e in payload["entries"])
