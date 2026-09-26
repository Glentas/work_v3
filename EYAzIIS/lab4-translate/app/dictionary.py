"""Двуязычный словарь системы: таблица БД, поиск, утилита пополнения.

Словарь хранится в SQLite (таблица ``entries``): это и есть «таблица БД» из
ТЗ, для которой требуется утилита автоматического пополнения/корректировки.

* поиск эквивалента учитывает часть речи и предметную область текста
  (медицина / критика искусства / общая лексика) — экстралингвистические
  знания о ПрО, как в СМП, основанных на знаниях;
* утилита пополнения (``replenish``) автоматически создаёт записи для
  неизвестных слов с пометкой «не проверено» и предложением перевода
  (транслитерация для терминов и имён собственных);
* корректировка — правка записей через интерфейс, а также массовый
  импорт/экспорт CSV.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from datetime import datetime

from . import config, db
from .domain import DictEntry

log = logging.getLogger(__name__)

#: Порядок поиска части речи: точное совпадение, затем близкие классы.
#: Для VERB добавлен ADJ: причастные формы (randomized, controlled) spaCy
#: помечает глаголом, а в словаре они хранятся прилагательными.
_POS_FALLBACKS: dict[str, tuple[str, ...]] = {
    "VERB": ("VERB", "AUX", "ADJ", ""),
    "AUX": ("AUX", "VERB", ""),
    "NOUN": ("NOUN", "PROPN", "ADJ", "NUM", ""),
    "PROPN": ("PROPN", "NOUN", "ADJ", ""),
    "NUM": ("NUM", "NOUN", ""),
    "PRON": ("PRON", "DET", ""),
    "ADJ": ("ADJ", ""),
    "ADV": ("ADV", ""),
}

_cache: dict[tuple[str, str, str], DictEntry] | None = None


# ---------------------------------------------------------------------------
# Грамматическая информация: компактный текстовый формат <-> dict
# ---------------------------------------------------------------------------
def parse_gram(text: str) -> dict:
    """Разбирает компактную запись грамматики из TSV/CSV.

    Формат: ``m,anim,gpl:врачей,pair:осмотреть,forms:pastm=шёл;pastf=шла``.
    Ключи: m/f/n — род; anim — одушевлённость; inv — неизменяемость;
    impf/pf — вид глагола; pair — парный вид; pp — краткое причастие;
    pl/gpl — формы множественного числа; gov — управление (падеж);
    comp/sup — степени сравнения; forms — явные словоформы.
    """
    gram: dict = {}
    forms: dict[str, str] = {}
    for part in (text or "").split(","):
        part = part.strip()
        if not part:
            continue
        if part in ("m", "f", "n"):
            gram["gender"] = part
        elif part == "anim":
            gram["anim"] = True
        elif part == "inv":
            gram["inv"] = True
        elif part == "adjdecl":
            gram["adjdecl"] = True   # существительное склоняется как прилагательное
        elif part in ("impf", "pf"):
            gram["aspect"] = part
        elif ":" in part:
            key, _, value = part.partition(":")
            key, value = key.strip(), value.strip()
            if key == "forms":
                for pair in value.split(";"):
                    form_key, _, form_value = pair.partition("=")
                    if form_key.strip() and form_value.strip():
                        forms[form_key.strip()] = form_value.strip()
            elif key and value:
                gram[key] = value
    if forms:
        gram["forms"] = forms
    return gram


def serialize_gram(gram: dict) -> str:
    """Обратная сборка компактной записи грамматической информации."""
    parts: list[str] = []
    if gram.get("gender"):
        parts.append(gram["gender"])
    if gram.get("anim"):
        parts.append("anim")
    if gram.get("inv"):
        parts.append("inv")
    if gram.get("aspect"):
        parts.append(gram["aspect"])
    if gram.get("adjdecl"):
        parts.append("adjdecl")
    for key in ("pair", "pp", "pl", "gpl", "gov", "comp", "sup", "compattr"):
        if gram.get(key):
            parts.append(f"{key}:{gram[key]}")
    forms = gram.get("forms") or {}
    if forms:
        parts.append("forms:" + ";".join(f"{k}={v}" for k, v in forms.items()))
    return ",".join(parts)


# ---------------------------------------------------------------------------
# Преобразование строк БД
# ---------------------------------------------------------------------------
def _row_to_entry(row) -> DictEntry:
    try:
        gram = json.loads(row["gram"] or "{}")
    except json.JSONDecodeError:
        gram = parse_gram(row["gram"] or "")
    return DictEntry(
        id=row["id"],
        source=row["source"],
        pos=row["pos"] or "",
        target=row["target"] or "",
        gram=gram,
        domain=row["domain"] or "general",
        verified=int(row["verified"]),
        note=row["note"] or "",
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Кэш и чтение
# ---------------------------------------------------------------------------
def invalidate_cache() -> None:
    global _cache
    _cache = None


def _entries_index() -> dict[tuple[str, str, str], DictEntry]:
    """Индекс всех записей (source, pos, domain) -> DictEntry; кэшируется."""
    global _cache
    if _cache is None:
        index: dict[tuple[str, str, str], DictEntry] = {}
        with db.connect() as conn:
            rows = conn.execute("SELECT * FROM entries").fetchall()
        for row in rows:
            entry = _row_to_entry(row)
            index[(entry.source, entry.pos, entry.domain)] = entry
        _cache = index
        log.info("Словарь загружен в кэш: %d записей", len(index))
    return _cache


def all_entries() -> list[DictEntry]:
    return list(_entries_index().values())


def count_entries(domain: str | None = None) -> int:
    entries = _entries_index().values()
    if domain:
        return sum(1 for e in entries if e.domain == domain)
    return len(_entries_index())


def count_unverified() -> int:
    return sum(1 for e in _entries_index().values() if not e.verified)


def get_entry(entry_id: int) -> DictEntry | None:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
    return _row_to_entry(row) if row else None


def list_entries(query: str = "", pos: str = "", domain: str = "",
                 verified: str = "", limit: int = 1000) -> list[DictEntry]:
    """Отбор записей для страницы словаря (поиск + фильтры)."""
    sql = "SELECT * FROM entries WHERE 1=1"
    params: list[object] = []
    if query:
        sql += " AND (source LIKE ? OR target LIKE ? OR note LIKE ?)"
        like = f"%{query}%"
        params += [like, like, like]
    if pos:
        sql += " AND pos = ?"
        params.append(pos)
    if domain:
        sql += " AND domain = ?"
        params.append(domain)
    if verified in ("0", "1"):
        sql += " AND verified = ?"
        params.append(int(verified))
    sql += " ORDER BY verified, source LIMIT ?"
    params.append(limit)
    with db.connect() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    return [_row_to_entry(row) for row in rows]


# ---------------------------------------------------------------------------
# Поиск эквивалентов
# ---------------------------------------------------------------------------
def lookup(lemma: str, pos: str = "", domain_pref: str = "general") -> DictEntry | None:
    """Перевод леммы с учётом части речи и предметной области.

    Приоритет: запись предметной области текста -> общая лексика -> запись
    другой предметной области (лучше перевод из смежного словаря, чем дырка);
    при несовпадении части речи пробуются близкие классы (VERB/AUX/ADJ,
    NOUN/PROPN).
    """
    index = _entries_index()
    lemma = (lemma or "").lower().strip()
    if not lemma:
        return None
    domains = [domain_pref, "general"] if domain_pref != "general" else ["general"]
    pos_variants = _POS_FALLBACKS.get((pos or "").upper(), (pos or "", ""))
    for candidate_pos in pos_variants:
        for domain in domains:
            entry = index.get((lemma, candidate_pos, domain))
            if entry is not None:
                return entry
    # Другая предметная область (например, имена собственные из art-словаря).
    others = [d for d in config.DOMAINS if d not in domains]
    for candidate_pos in pos_variants:
        for domain in others:
            entry = index.get((lemma, candidate_pos, domain))
            if entry is not None:
                return entry
    # Последний шанс: запись без указания части речи.
    for domain in (*domains, *others):
        entry = index.get((lemma, "", domain))
        if entry is not None:
            return entry
    return None


def lookup_form(word: str, pos: str = "", domain_pref: str = "general") -> DictEntry | None:
    """Поиск по словоформе (если лемма не найдена — например, у имён собственных)."""
    return lookup(word.lower().strip(), pos, domain_pref)


def lookup_phrase(lemmas: list[str], start: int, domain_pref: str = "general") -> tuple[DictEntry, int] | None:
    """Поиск оборота (пословно-оборотный перевод): самое длинное совпадение.

    Возвращает (запись, длина оборота в токенах) или None.
    """
    index = _entries_index()
    best: tuple[DictEntry, int] | None = None
    max_len = min(len(lemmas) - start, 5)
    for size in range(max_len, 1, -1):
        candidate = " ".join(lemmas[start:start + size])
        for domain in ({domain_pref, "general"} if domain_pref != "general" else {"general"}):
            for pos in ("PHRASE", "VERB", "NOUN", "ADJ", "ADV", ""):
                entry = index.get((candidate, pos, domain))
                if entry is not None and entry.target:
                    best = (entry, size)
                    break
            if best:
                break
        if best:
            break
    return best


# ---------------------------------------------------------------------------
# Запись: добавление, корректировка, удаление
# ---------------------------------------------------------------------------
def add_entry(source: str, pos: str, target: str, gram: dict | None = None,
              domain: str = "general", verified: int = 1, note: str = "") -> DictEntry | None:
    source = source.lower().strip()
    if not source:
        return None
    now = _now()
    with db.connect() as conn, db.transaction(conn):
        try:
            cur = conn.execute(
                "INSERT INTO entries (source, pos, target, gram, domain, verified, note, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (source, (pos or "").upper(), target.strip(),
                 json.dumps(gram or {}, ensure_ascii=False), domain, int(verified), note, now, now),
            )
        except Exception:
            # UNIQUE(source, pos, domain): запись уже есть — обновляем перевод.
            conn.execute(
                "UPDATE entries SET target = ?, gram = ?, verified = ?, note = ?, updated_at = ?"
                " WHERE source = ? AND pos = ? AND domain = ?",
                (target.strip(), json.dumps(gram or {}, ensure_ascii=False),
                 int(verified), note, now, source, (pos or "").upper(), domain),
            )
            cur = conn.execute(
                "SELECT id FROM entries WHERE source = ? AND pos = ? AND domain = ?",
                (source, (pos or "").upper(), domain),
            )
        entry_id = cur.lastrowid or conn.execute(
            "SELECT id FROM entries WHERE source = ? AND pos = ? AND domain = ?",
            (source, (pos or "").upper(), domain),
        ).fetchone()["id"]
    invalidate_cache()
    entry = get_entry(int(entry_id))
    return entry


def update_entry(entry_id: int, source: str, pos: str, target: str,
                 gram: dict | None = None, domain: str = "general",
                 verified: int = 1, note: str = "") -> bool:
    with db.connect() as conn, db.transaction(conn):
        cur = conn.execute(
            "UPDATE entries SET source = ?, pos = ?, target = ?, gram = ?, domain = ?,"
            " verified = ?, note = ?, updated_at = ? WHERE id = ?",
            (source.lower().strip(), (pos or "").upper(), target.strip(),
             json.dumps(gram or {}, ensure_ascii=False), domain, int(verified),
             note, _now(), entry_id),
        )
    invalidate_cache()
    return cur.rowcount > 0


def delete_entry(entry_id: int) -> bool:
    with db.connect() as conn, db.transaction(conn):
        cur = conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
    invalidate_cache()
    return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Утилита автоматического пополнения словаря
# ---------------------------------------------------------------------------
#: Практическая транслитерация англо-латыни в кириллицу для терминов.
_TRANSLIT_DIGRAPHS = [
    ("tion", "ция"), ("sion", "зия"), ("tial", "циаль"), ("cial", "циаль"),
    ("ough", "о"), ("ight", "айт"), ("ch", "ч"), ("sh", "ш"), ("th", "т"),
    ("ph", "ф"), ("ck", "к"), ("qu", "кв"), ("wh", "в"), ("ee", "и"),
    ("ea", "и"), ("oo", "у"), ("ou", "у"), ("oi", "ой"), ("ay", "ей"),
    ("ey", "и"), ("au", "о"), ("ai", "ей"), ("ei", "ей"), ("ia", "ия"),
    ("ct", "кт"), ("ll", "лл"), ("mm", "мм"), ("ss", "сс"), ("rr", "рр"),
]

_TRANSLIT_SINGLE = {
    "a": "а", "b": "б", "c": "к", "d": "д", "e": "е", "f": "ф", "g": "г",
    "h": "х", "i": "и", "j": "дж", "k": "к", "l": "л", "m": "м", "n": "н",
    "o": "о", "p": "п", "r": "р", "s": "с", "t": "т", "u": "у", "v": "в",
    "w": "в", "x": "кс", "y": "и", "z": "з",
}


def transliterate(word: str) -> str:
    """Приблизительная транслитерация английского слова в кириллицу.

    Используется утилитой пополнения как *предложение* перевода для
    интернациональных терминов (therapy -> терапия) и имён собственных;
    запись помечается «не проверено» и ждёт корректировки пользователем.
    """
    text = word.lower()
    result: list[str] = []
    i = 0
    while i < len(text):
        for size in (5, 4, 3, 2):
            chunk = text[i:i + size]
            for src, dst in _TRANSLIT_DIGRAPHS:
                if len(src) == size and chunk == src:
                    result.append(dst)
                    i += size
                    break
            else:
                continue
            break
        else:
            ch = text[i]
            if ch == "c" and i + 1 < len(text) and text[i + 1] in "eiy":
                result.append("ц")
            elif ch.isalpha():
                result.append(_TRANSLIT_SINGLE.get(ch, ch))
            elif ch == "-":
                result.append("-")
            i += 1
    translit = "".join(result)
    # Термины на -y после «гласная + согласная»: therapy -> терапия,
    # biology -> биология (в остальных случаях -y -> -и: happy -> хэппи).
    lowered = text
    if (len(lowered) > 3 and lowered.endswith("y")
            and lowered[-2] not in "aeiouy" and lowered[-3] in "aeiouy"):
        translit += "я"
    if word[:1].isupper():
        translit = translit.capitalize()
    return translit


#: Части речи, для которых транслитерация — разумное предложение перевода.
_TRANSLIT_POS = {"PROPN", "NOUN", "X"}


def suggest_translation(word: str, pos: str = "") -> str:
    """Предложение перевода для неизвестного слова (пустая строка = нет идеи)."""
    if (pos or "").upper() in _TRANSLIT_POS or word[:1].isupper():
        return transliterate(word)
    return ""


def replenish(unknown_words: list[tuple[str, str]], domain: str = "general") -> int:
    """Автоматическое пополнение словаря неизвестными словами.

    ``unknown_words`` — пары (лемма/словоформа, часть речи). Создаются
    записи с proposed-переводом и флагом verified=0 («требует проверки»).
    Возвращает число новых записей.
    """
    created = 0
    seen: set[tuple[str, str]] = set()
    for word, pos in unknown_words:
        key = (word.lower().strip(), (pos or "").upper())
        if not key[0] or key in seen:
            continue
        seen.add(key)
        if lookup(key[0], key[1], domain_pref=domain) is not None:
            continue
        suggestion = suggest_translation(word, pos)
        entry_domain = domain if domain in config.DOMAINS else "general"
        result = add_entry(
            source=key[0], pos=key[1], target=suggestion,
            gram={}, domain=entry_domain, verified=0,
            note="добавлено утилитой пополнения",
        )
        if result is not None:
            created += 1
    return created


# ---------------------------------------------------------------------------
# Массовая корректировка: CSV импорт/экспорт и посев из TSV
# ---------------------------------------------------------------------------
_CSV_COLUMNS = ["source", "pos", "target", "gram", "domain", "note", "verified"]


def export_csv() -> str:
    """Экспорт всего словаря в CSV (Unicode, разделитель «;» — для Excel)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(_CSV_COLUMNS)
    for entry in sorted(all_entries(), key=lambda e: (e.domain, e.pos, e.source)):
        writer.writerow([
            entry.source, entry.pos, entry.target, serialize_gram(entry.gram),
            entry.domain, entry.note, entry.verified,
        ])
    return buffer.getvalue()


def import_csv(text: str) -> tuple[int, int]:
    """Импорт/корректировка словаря из CSV. Возвращает (добавлено, обновлено)."""
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    if reader.fieldnames is None or "source" not in reader.fieldnames:
        reader = csv.DictReader(io.StringIO(text))
    added = updated = 0
    for row in reader:
        source = (row.get("source") or "").strip().lower()
        if not source:
            continue
        pos = (row.get("pos") or "").strip().upper()
        domain = (row.get("domain") or "general").strip()
        if domain not in config.DOMAINS:
            domain = "general"
        existing = _entries_index().get((source, pos, domain))
        gram = parse_gram(row.get("gram") or "")
        note = (row.get("note") or "").strip()
        try:
            verified = int(row.get("verified") or 1)
        except ValueError:
            verified = 1
        target = (row.get("target") or "").strip()
        if existing is None:
            add_entry(source, pos, target, gram, domain, verified, note)
            added += 1
        else:
            update_entry(existing.id or 0, source, pos, target, gram, domain, verified, note)
            updated += 1
    invalidate_cache()
    return added, updated


def seed_from_tsv(path=None) -> int:
    """Посев словаря из data/seed_dictionary.tsv (идемпотентно).

    Формат TSV: source, pos, target, gram, domain, note. Записи вставляются
    одной транзакцией; повторяющиеся ключи (source, pos, domain) пропускаются.
    Возвращает число добавленных записей.
    """
    path = path or config.SEED_DICTIONARY_PATH
    if not path.exists():
        log.warning("Файл посева словаря не найден: %s", path)
        return 0
    existing = {(e.source, e.pos, e.domain) for e in all_entries()}
    now = _now()
    added = 0
    with db.connect() as conn, db.transaction(conn), \
            open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            columns = line.split("\t")
            if len(columns) < 3:
                continue
            source = columns[0].strip().lower()
            pos = columns[1].strip().upper()
            target = columns[2].strip()
            gram_text = columns[3].strip() if len(columns) > 3 else ""
            domain = columns[4].strip() if len(columns) > 4 else "general"
            note = columns[5].strip() if len(columns) > 5 else ""
            if domain not in config.DOMAINS:
                domain = "general"
            key = (source, pos, domain)
            if key in existing:
                continue
            existing.add(key)
            conn.execute(
                "INSERT INTO entries (source, pos, target, gram, domain, verified, note,"
                " created_at, updated_at) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)",
                (source, pos, target,
                 json.dumps(parse_gram(gram_text), ensure_ascii=False),
                 domain, note, now, now),
            )
            added += 1
    invalidate_cache()
    log.info("Посев словаря: добавлено %d записей", added)
    return added


# ---------------------------------------------------------------------------
# Определение предметной области текста
# ---------------------------------------------------------------------------
def detect_domain(text: str) -> str:
    """ПрО текста по ключевым словам: med / art / general (знания о ПрО).

    Достаточно одного характерного слова: приоритет области влияет только на
    выбор перевода многозначных слов, общая лексика используется в любом
    случае (словарный поиск с fallback в general).
    """
    words = {w.strip(".,;:!?()\"'").lower() for w in (text or "").split()}
    scores = {
        domain: len(words & keywords)
        for domain, keywords in config.DOMAIN_KEYWORDS.items()
    }
    best = max(scores, key=lambda d: scores[d])
    return best if scores[best] >= 1 else "general"
