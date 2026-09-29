# -*- coding: utf-8 -*-
"""Загрузка тестовой коллекции документов из многоязычной Wikipedia.

Вариант 7: языки - французский и английский; предметные области -
научные статьи по computer science и сочинения по литературе.

Методичка допускает формирование коллекции на основании многоязычных
текстов из Wikipedia и других тематических ресурсов. Домен «сочинения
по литературе» представлен аналитическими текстами о литературных
произведениях (жанр литературоведческого эссе/критики).

Каждый документ нормализуется к одинаковому размеру (~10 страниц А4,
TARGET_CHARS символов); вводная часть статьи (lead) сохраняется отдельно
как эталонный реферат для оценки качества (ROUGE).
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "..", "data", "collection")
TARGET_CHARS = 18000  # ~10 страниц А4 по 1800 символов

SOURCES = [
    ("en_cs_ml",     "en", "cs",  "Machine learning",
     "https://en.wikipedia.org/wiki/Machine_learning"),
    ("en_cs_ann",    "en", "cs",  "Artificial neural network",
     "https://en.wikipedia.org/wiki/Artificial_neural_network"),
    ("fr_cs_app",    "fr", "cs",  "Apprentissage automatique",
     "https://fr.wikipedia.org/wiki/Apprentissage_automatique"),
    ("fr_cs_rnn",    "fr", "cs",  "Réseau de neurones artificiels",
     "https://fr.wikipedia.org/wiki/R%C3%A9seau_de_neurones_artificiels"),
    ("en_lit_ham",   "en", "lit", "Hamlet",
     "https://en.wikipedia.org/wiki/Hamlet"),
    ("en_lit_pp",    "en", "lit", "Pride and Prejudice",
     "https://en.wikipedia.org/wiki/Pride_and_Prejudice"),
    ("fr_lit_mis",   "fr", "lit", "Les Misérables",
     "https://fr.wikipedia.org/wiki/Les_Mis%C3%A9rables"),
    ("fr_lit_bov",   "fr", "lit", "Madame Bovary",
     "https://fr.wikipedia.org/wiki/Madame_Bovary"),
]

UA = {"User-Agent": "LabSummarizer/1.0 (educational lab work; contact: student)"}


def _fetch_api_json(url: str) -> dict:
    """Запрос к Wikipedia API; при блокировке сети - через прокси r.jina.ai."""
    attempts = [(url, UA)]
    attempts.append(("https://r.jina.ai/" + url,
                     {"User-Agent": "Mozilla/5.0"}))
    last_err = None
    for u, headers in attempts:
        try:
            req = urllib.request.Request(u, headers=headers)
            with urllib.request.urlopen(req, timeout=90) as r:
                body = r.read().decode("utf-8", "replace")
            i = body.find('{"batchcomplete')
            if i >= 0:
                body = body[i:body.rfind("}") + 1]
            return json.loads(body)
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(2)
    raise RuntimeError(f"не удалось получить {url}: {last_err}")


def fetch_extract(lang: str, title: str) -> str:
    url = (f"https://{lang}.wikipedia.org/w/api.php?action=query&format=json"
           f"&prop=extracts&explaintext=1&redirects=1&titles="
           + urllib.parse.quote(title))
    data = _fetch_api_json(url)
    pages = data["query"]["pages"]
    page = next(iter(pages.values()))
    return page["extract"]


def clean_text(raw: str) -> str:
    lines = []
    for ln in raw.split("\n"):
        ln = ln.rstrip()
        if re.match(r"^=+.*=+$", ln.strip()):      # заголовки секций
            continue
        if not ln.strip():
            continue
        ln = re.sub(r"\[\d+\]", "", ln)             # остатки сносок
        ln = re.sub(r"\[note \d+\]", "", ln)
        ln = re.sub(r"\s+", " ", ln).strip()
        if ln:
            lines.append(ln)
    return "\n".join(lines)


def split_lead(raw: str) -> tuple[str, str]:
    """lead = текст до первого заголовка '=='; body = остальное."""
    m = re.search(r"^==\s.*\s==\s*$", raw, flags=re.MULTILINE)
    if m:
        return raw[:m.start()], raw[m.end():]
    parts = raw.split("\n\n", 1)
    return (parts[0], parts[1]) if len(parts) == 2 else (raw, "")


def cut_to_size(body: str, target: int = TARGET_CHARS) -> str:
    """Обрезка по границе предложения ближе всего к target (сверху)."""
    if len(body) <= target:
        return body
    cut = body[:target + 500]
    # ближайшая граница предложения после target
    best = None
    for m in re.finditer(r"[.!?…][\"')\]»]*\s", body[target - 200:target + 500]):
        pos = target - 200 + m.end()
        if best is None or abs(pos - target) < abs(best - target):
            best = pos
    if best is None:
        best = target
    return body[:best].strip()


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    meta = []
    for doc_id, lang, domain, title, url in SOURCES:
        path_txt = os.path.join(OUT_DIR, f"{doc_id}.txt")
        path_ref = os.path.join(OUT_DIR, f"{doc_id}.ref.txt")
        if os.path.exists(path_txt) and os.path.exists(path_ref):
            print(f"[skip] {doc_id}")
        else:
            print(f"[fetch] {lang}/{title}")
            raw = fetch_extract(lang, title)
            lead, body = split_lead(raw)
            lead = clean_text(lead)
            body = cut_to_size(clean_text(body))
            if len(body) < 4000:
                print(f"  ! слишком короткое тело: {len(body)}")
            with open(path_txt, "w", encoding="utf-8") as f:
                f.write(body)
            with open(path_ref, "w", encoding="utf-8") as f:
                f.write(lead)
            time.sleep(1)
        with open(path_txt, encoding="utf-8") as f:
            n_chars = len(f.read())
        meta.append({
            "id": doc_id, "lang": lang, "domain": domain,
            "title": title, "source_url": url,
            "file": f"{doc_id}.txt", "reference_file": f"{doc_id}.ref.txt",
            "chars": n_chars,
        })
        print(f"  ok: {doc_id}, {n_chars} символов")
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print("collection ready:", len(meta), "docs")


if __name__ == "__main__":
    sys.exit(main())
