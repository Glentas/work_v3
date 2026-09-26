"""Оркестрация перевода: анализ -> трансфер -> статистика, частотный список, сессии.

Собирает результат, требуемый ТЗ:
* перевод входного текста на выходной язык;
* количество слов во входном тексте и количество переведённых слов;
* грамматическая информация (теги частей речи и их расшифровка — лр. №3);
* вкладка 1: упорядоченный по частоте список слов с переводами и грамматикой;
* вкладка 2: данные для дерева синтаксического разбора предложений.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime

from . import analysis, config, db, dictionary, transfer
from .domain import (
    FreqRow,
    SentenceData,
    SessionInfo,
    Stats,
    TextData,
    TranslationResult,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Вкладка 1: частотный список слов (функциональность лр. №1 весеннего семестра)
# ---------------------------------------------------------------------------
def build_freq_rows(text_data: TextData, domain: str) -> list[FreqRow]:
    """Список слов текста, упорядоченный по частоте встречаемости.

    Для каждой леммы: словоформы, частота, часть речи, тег Penn Treebank и
    его расшифровка, синтаксическая роль и её расшифровка, перевод.
    """
    forms: dict[str, Counter] = {}
    freq: Counter = Counter()
    tags: dict[str, Counter] = {}
    deps: dict[str, Counter] = {}
    pos_of: dict[str, str] = {}

    for sent in text_data.sentences:
        for tok in sent.tokens:
            if tok.kind != "word":
                continue
            lemma = tok.lemma
            freq[lemma] += 1
            forms.setdefault(lemma, Counter())[tok.word.lower()] += 1
            tags.setdefault(lemma, Counter())[(tok.tag, tok.tag_ru)] += 1
            deps.setdefault(lemma, Counter())[(tok.dep, tok.dep_ru)] += 1
            pos_of.setdefault(lemma, tok.pos)

    rows: list[FreqRow] = []
    for lemma, count in freq.items():
        pos = pos_of[lemma]
        tag, tag_ru = tags[lemma].most_common(1)[0][0]
        dep, dep_ru = deps[lemma].most_common(1)[0][0]
        entry = dictionary.lookup(lemma, pos, domain)
        rows.append(
            FreqRow(
                lemma=lemma,
                forms=[w for w, _ in forms[lemma].most_common()],
                freq=count,
                pos=pos,
                pos_ru=dictionary_pos_ru(pos),
                tag=tag,
                tag_ru=tag_ru,
                dep=dep,
                dep_ru=dep_ru,
                translation=entry.target if entry else "",
                in_dict=entry is not None,
            )
        )
    rows.sort(key=lambda r: (-r.freq, r.lemma))
    return rows


def dictionary_pos_ru(pos: str) -> str:
    from . import grammar
    return grammar.pos_rus(pos)


# ---------------------------------------------------------------------------
# Перевод текста
# ---------------------------------------------------------------------------
def translate_text(text: str, name: str = "", mode: str = "transfer") -> TranslationResult:
    """Полный цикл машинного перевода текста."""
    if mode not in config.MODES:
        mode = "transfer"
    text_data, parse_seconds = analysis.parse_text(text)
    domain = dictionary.detect_domain(text)

    translated_ids: set[tuple[int, int]] = set()
    unknown: list[str] = []
    articles = 0
    for sent in text_data.sentences:
        tr_text, tr_ids, sent_unknown, sent_articles = transfer.translate_sentence(
            sent, domain, mode
        )
        sent.translation = tr_text
        translated_ids.update((sent.id, tid) for tid in tr_ids)
        unknown.extend(sent_unknown)
        articles += sent_articles

    word_tokens = sum(
        1 for sent in text_data.sentences for tok in sent.tokens if tok.kind == "word"
    )
    digits = sum(
        1 for sent in text_data.sentences for tok in sent.tokens if tok.kind == "digit"
    )
    translated_words = len(translated_ids)

    unique_unknown: list[str] = []
    seen = set()
    for lemma in unknown:
        if lemma not in seen:
            seen.add(lemma)
            unique_unknown.append(lemma)

    denom = max(1, word_tokens - articles)
    coverage = translated_words / denom

    started = datetime.now()
    translated_text = " ".join(s.translation for s in text_data.sentences if s.translation)

    result = TranslationResult(
        name=name or f"Перевод {started.strftime('%Y-%m-%d %H:%M')}",
        created_at=started.isoformat(timespec="seconds"),
        mode=mode,
        domain=domain,
        source_text=text.strip(),
        translated_text=translated_text,
        stats=Stats(
            total_words=word_tokens,
            translated_words=translated_words,
            digits=digits,
            articles=articles,
            unknown_total=len(unknown),
            unknown=unique_unknown,
            coverage=coverage,
            sentences=len(text_data.sentences),
            duration_ms=round(parse_seconds * 1000, 1),
            dict_size=dictionary.count_entries(),
        ),
        sentences=text_data.sentences,
        freq=build_freq_rows(text_data, domain),
    )
    return result


# ---------------------------------------------------------------------------
# Сессии перевода (таблица sessions)
# ---------------------------------------------------------------------------
def save_session(result: TranslationResult) -> int:
    with db.connect() as conn, db.transaction(conn):
        cur = conn.execute(
            "INSERT INTO sessions (name, mode, domain, created_at, source_text, result_json)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (result.name, result.mode, result.domain, result.created_at,
             result.source_text, result.model_dump_json()),
        )
    return int(cur.lastrowid)


def load_session(session_id: int) -> TranslationResult | None:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT result_json FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
    if row is None:
        return None
    return TranslationResult.model_validate_json(row["result_json"])


def list_sessions() -> list[SessionInfo]:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id, name, mode, domain, created_at, result_json FROM sessions ORDER BY id DESC"
        ).fetchall()
    sessions = []
    for row in rows:
        try:
            result = TranslationResult.model_validate_json(row["result_json"])
            stats = result.stats
        except Exception:  # повреждённая запись — показываем пустую статистику
            stats = Stats()
        sessions.append(
            SessionInfo(
                id=row["id"], name=row["name"], mode=row["mode"], domain=row["domain"],
                created_at=row["created_at"], stats=stats,
            )
        )
    return sessions


def delete_session(session_id: int) -> bool:
    with db.connect() as conn, db.transaction(conn):
        cur = conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    return cur.rowcount > 0


def rename_session(session_id: int, name: str) -> bool:
    result = load_session(session_id)
    if result is None:
        return False
    result.name = name
    with db.connect() as conn, db.transaction(conn):
        conn.execute(
            "UPDATE sessions SET name = ?, result_json = ? WHERE id = ?",
            (name, result.model_dump_json(), session_id),
        )
    return True


def unknown_words_of(result: TranslationResult) -> list[tuple[str, str]]:
    """Неизвестные слова сессии для утилиты пополнения словаря: (слово, часть речи)."""
    pos_by_lemma: dict[str, str] = {}
    for sent in result.sentences:
        for tok in sent.tokens:
            if tok.kind == "word":
                pos_by_lemma.setdefault(tok.lemma, tok.pos)
    return [(lemma, pos_by_lemma.get(lemma, "")) for lemma in result.stats.unknown]


def samples() -> list[dict]:
    """Демонстрационные тексты предметных областей варианта 7."""
    items = []
    if config.SAMPLES_PATH.exists():
        for path in sorted(config.SAMPLES_PATH.glob("*.txt")):
            text = path.read_text(encoding="utf-8")
            first_line = text.strip().splitlines()[0] if text.strip() else path.stem
            items.append({"name": path.stem, "title": first_line[:80], "chars": len(text)})
    return items


def sample_text(name: str) -> str | None:
    path = config.SAMPLES_PATH / f"{name}.txt"
    if path.exists() and path.parent == config.SAMPLES_PATH:
        return path.read_text(encoding="utf-8")
    return None
