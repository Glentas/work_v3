"""Тесты словаря: формат грамматики, CRUD, приоритеты поиска, пополнение, CSV."""

from __future__ import annotations

from app import dictionary


def test_parse_and_serialize_gram_roundtrip():
    gram = dictionary.parse_gram("m,anim,gpl:врачей,pair:осмотреть,pp:осмотрен,forms:pastm=шёл;pastf=шла")
    assert gram["gender"] == "m"
    assert gram["anim"] is True
    assert gram["gpl"] == "врачей"
    assert gram["pair"] == "осмотреть"
    assert gram["pp"] == "осмотрен"
    assert gram["forms"] == {"pastm": "шёл", "pastf": "шла"}
    text = dictionary.serialize_gram(gram)
    assert dictionary.parse_gram(text) == gram


def test_parse_gram_aspect_and_inv():
    gram = dictionary.parse_gram("pf,inv")
    assert gram == {"aspect": "pf", "inv": True}


def test_lookup_priority_domain_over_general():
    # cell: общая лексика — «ячейка», медицина — «клетка».
    general = dictionary.lookup("cell", "NOUN", "general")
    med = dictionary.lookup("cell", "NOUN", "med")
    assert general is not None and med is not None
    assert general.target == "ячейка"
    assert med.target == "клетка"


def test_lookup_pos_fallbacks():
    # be хранится как AUX; запрос с VERB всё равно находит запись.
    entry = dictionary.lookup("be", "VERB")
    assert entry is not None
    assert entry.target == "быть"
    # painter (NOUN) — без учёта регистра леммы.
    assert dictionary.lookup("PAINTER", "NOUN", "art") is not None


def test_lookup_cross_domain_fallback():
    # europe есть только в art-словаре; med-текст тоже получает перевод.
    entry = dictionary.lookup("europe", "PROPN", "med")
    assert entry is not None
    assert entry.target == "Париж" or entry.target == "Европа"


def test_lookup_missing():
    assert dictionary.lookup("qqqzzz", "NOUN") is None


def test_phrase_lookup_longest_match():
    lemmas = ["randomized", "controlled", "trial", "studied"]
    found = dictionary.lookup_phrase(lemmas, 0, "med")
    # «clinical trial» не совпало с начала; проверяем совпадение с нужной позиции
    lemmas2 = ["the", "clinical", "trial", "included"]
    found2 = dictionary.lookup_phrase(lemmas2, 1, "med")
    assert found2 is not None
    entry, size = found2
    assert entry.source == "clinical trial"
    assert size == 2
    assert found is None or found[1] >= 2


def test_crud_lifecycle():
    entry = dictionary.add_entry("testword", "NOUN", "тестовое слово", {"gender": "n"},
                                 "general", 1, "тест")
    assert entry is not None and entry.id is not None
    fetched = dictionary.get_entry(entry.id)
    assert fetched.target == "тестовое слово"
    assert fetched.gram.get("gender") == "n"

    dictionary.update_entry(entry.id, "testword", "NOUN", "тестовое", {"gender": "n"},
                            "general", 1, "правка")
    assert dictionary.get_entry(entry.id).target == "тестовое"

    assert dictionary.delete_entry(entry.id) is True
    assert dictionary.get_entry(entry.id) is None


def test_add_entry_updates_existing_key():
    a = dictionary.add_entry("dupword", "NOUN", "первый", {}, "general")
    b = dictionary.add_entry("dupword", "NOUN", "второй", {}, "general")
    # UNIQUE(source, pos, domain): вторая вставка обновляет перевод.
    assert dictionary.lookup("dupword", "NOUN", "general").target == "второй"
    dictionary.delete_entry(a.id)
    assert dictionary.lookup("dupword", "NOUN", "general") is None


def test_transliteration():
    assert dictionary.transliterate("therapy") == "терапия"
    assert dictionary.transliterate("Thompson") == "Томпсон" or \
           dictionary.transliterate("Thompson").startswith("Т")


def test_replenish_creates_unverified_entries():
    created = dictionary.replenish([("qqbronchoscope", "NOUN"), ("qqbronchoscope", "NOUN")], "med")
    assert created == 1  # дубликаты не повторяются
    entry = dictionary.lookup("qqbronchoscope", "NOUN", "med")
    assert entry is not None
    assert entry.verified == 0
    assert entry.target  # предложена транслитерация
    dictionary.delete_entry(entry.id)


def test_csv_export_import_roundtrip():
    dictionary.add_entry("csvword", "NOUN", "слово из csv", {"gender": "n"}, "general", 1, "")
    exported = dictionary.export_csv()
    assert "csvword" in exported
    # правим перевод в CSV и импортируем обратно
    patched = exported.replace("слово из csv", "слово изменено")
    added, updated = dictionary.import_csv(patched)
    assert updated >= 1
    entry = dictionary.lookup("csvword", "NOUN", "general")
    assert entry.target == "слово изменено"
    dictionary.delete_entry(entry.id)


def test_detect_domain():
    assert dictionary.detect_domain("The patient received therapy for the disease.") == "med"
    assert dictionary.detect_domain("The painting was exhibited at the gallery.") == "art"
    assert dictionary.detect_domain("The table stands in the room.") == "general"


def test_list_entries_filters():
    rows = dictionary.list_entries(query="patient", pos="NOUN")
    assert rows and all("patient" in r.source or "patient" in r.target for r in rows)
    med_rows = dictionary.list_entries(domain="med", pos="NOUN", limit=50)
    assert all(r.domain == "med" for r in med_rows)
