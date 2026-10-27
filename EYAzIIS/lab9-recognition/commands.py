"""Сопоставление распознанной фразы со списком операций.

Операции двух видов:
  • управляющие команды (help/read/stop/next/prev/first/list) — из data/commands.json;
  • открытие конкретного сочинения по имени собственному (Faust, Kafka, …) — из
    data/essays.json.

Сопоставление устойчиво к ошибкам распознавания: нормализация (регистр,
пунктуация, умлауты), поиск подстрок и нечёткое сравнение слов (Левенштейн ≤ 1).
"""
import json
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(BASE, "data", "commands.json"), encoding="utf-8") as fh:
    _commands = json.load(fh)

with open(os.path.join(BASE, "data", "essays.json"), encoding="utf-8") as fh:
    _essays = json.load(fh)["essays"]

_UMLAUTS = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "é": "e", "è": "e", "ê": "e"}


def normalize(text, fold=False):
    """Нижний регистр, замена умлаутов (опц.), только буквы/цифры/пробелы."""
    text = (text or "").lower().strip()
    if fold:
        for a, b in _UMLAUTS.items():
            text = text.replace(a, b)
    text = "".join(ch if (ch.isalnum() or ch.isspace()) else " " for ch in text)
    return re.sub(r"\s+", " ", text).strip()


def levenshtein(a, b):
    if a == b:
        return 0
    if not a or not b:
        return max(len(a), len(b))
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _hit(keyword, text_n, text_f):
    """True, если ключевое слово встретилось (подстрока или нечётко по словам)."""
    kn = normalize(keyword)
    kf = normalize(keyword, fold=True)
    if not kn:
        return False
    if kn in text_n or kf in text_f:
        return True
    # нечёткое сравнение отдельных слов (для длинных слов)
    if len(kn) >= 4:
        for w in text_n.split():
            if len(w) >= 4 and levenshtein(w, kn) <= 1:
                return True
        for w in text_f.split():
            if len(w) >= 4 and levenshtein(w, kf) <= 1:
                return True
    return False


def supported_languages():
    return [lang for lang in _commands if isinstance(_commands[lang], list)]


def get_commands(lang):
    return _commands.get(lang, [])


def get_essays():
    return _essays


def match(text, lang):
    """Возвращает операцию {action, title, ...} или None."""
    text_n = normalize(text)
    text_f = normalize(text, fold=True)
    if not text_n:
        return None

    # 1) управляющие команды
    for cmd in get_commands(lang):
        for kw in cmd.get("keywords", []):
            if _hit(kw, text_n, text_f):
                return {"action": cmd["action"], "title": cmd["title"], "source": "command"}

    # 2) открытие сочинения по имени собственному
    for e in _essays:
        for kw in e.get("keywords", []):
            if _hit(kw, text_n, text_f):
                return {"action": "open", "title": e["title"], "essay_id": e["id"], "source": "entity"}

    return None
