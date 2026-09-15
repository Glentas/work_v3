#!/usr/bin/env python3
"""Нарезка исходников в тренировочный набор, тестовую коллекцию и стресс-наборы.

Из corpus/sources/ получаются:
  corpus/train/{fr,en}.txt   — по ~100 Кб (требование методички: 20–120 Кб);
  corpus/test/*.html         — 100 документов, видимый текст ровно DOC_CHARS знаков;
  corpus/stress/*/*.html     — «сложные» наборы для сравнения методов;
  corpus/test/manifest.json  — происхождение каждого документа (для отчёта и тестов).

Правила обрезки:
* размер измеряется по ВИДИМОМУ тексту, а не по байтам разметки;
* окно берётся ровно заданной длины и с обоих концов по границе слова
  (функция cut_exact), поэтому все документы коллекции одинакового размера;
* тренировочные и тестовые тексты берутся из разных статей.

Использование:
    python scripts/make_test_docs.py
"""

from __future__ import annotations

import json
import random
import re
import unicodedata
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCES_DIR = PROJECT_ROOT / "corpus" / "sources"
TRAIN_DIR = PROJECT_ROOT / "corpus" / "train"
TEST_DIR = PROJECT_ROOT / "corpus" / "test"
STRESS_DIR = PROJECT_ROOT / "corpus" / "stress"

TRAIN_BYTES = 100 * 1024        # 100 Кб на язык, внутри допустимых 20–120 Кб
DOCS_PER_LANG = 50              # 100 документов основной коллекции
STRESS_PER_LANG = 20
DOC_CHARS = 2000                # ~1 страница А4 видимого текста
SHORT_CHARS = 300
# Видимый текст документа = заголовок <h1>Document fr-01</h1> + пробел + абзац.
# Длина заголовка одинакова у всех документов, поэтому тело режется на
# DOC_CHARS - TITLE_PAD знаков, и СУММАРНЫЙ видимый текст равен ровно DOC_CHARS.
TITLE_PAD = len("Document fr-01") + 1
CP1252_COUNT = 4                # столько французских документов пишем в windows-1252

HTML_TEMPLATE = """<!doctype html>
<html lang="{lang}">
<head>
<meta charset="{charset}">
<title>Document {tag}</title>
<meta name="description" content="test document for language detection lab">
</head>
<body>
<header><nav><a href="/">Accueil</a> | <a href="/cat">Category</a> | <a href="/help">Aide</a></nav></header>
<article>
<h1>Document {tag}</h1>
<p>{body}</p>
</article>
<footer><p>Copyright 2026 — contact@example.com — all rights reserved</p></footer>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Нарезка
# ---------------------------------------------------------------------------
def cut_exact(stream: str, size: int) -> str | None:
    """Окно ровно `size` знаков, оба конца — по границе слова.

    Ищем конец слова, отстоящий ровно на `size` от начала слова: в сплошном
    потоке такое окно находится за несколько попыток.
    """
    for match in re.finditer(r"\S+", stream):
        end = match.end()
        start = end - size
        if start < 0:
            continue
        # оба конца — по границе слова: ни ведущих, ни хвостовых пробелов
        at_word_start = (start == 0 and stream[0] != " ") or (
            start > 0 and stream[start - 1] == " " and stream[start] != " "
        )
        if at_word_start and stream[end - 1] != " ":
            return stream[start:end]
    return None


def windows(stream: str, size: int, count: int) -> list[str]:
    """Последовательные непересекающиеся окна заданного размера."""
    out: list[str] = []
    offset = 0
    while len(out) < count and offset + size <= len(stream):
        window = cut_exact(stream[offset:], size)
        if window is None:
            break
        out.append(window)
        offset += len(window) + 1
    return out


def load_stream(lang: str, split: str) -> str:
    """Склейка всех исходников набора в один поток с одиночными пробелами."""
    root = SOURCES_DIR / lang / split
    parts = [p.read_text(encoding="utf-8") for p in sorted(root.glob("*.txt"))]
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


# ---------------------------------------------------------------------------
# Искажения стресс-наборов
# ---------------------------------------------------------------------------
def make_typos(text: str, rng: random.Random) -> str:
    """Перестановка соседних букв в части слов (опечатки)."""
    words = text.split(" ")
    for i, word in enumerate(words):
        if len(word) > 4 and rng.random() < 0.25:
            j = rng.randrange(1, len(word) - 1)
            words[i] = word[: j - 1] + word[j] + word[j - 1] + word[j + 1 :]
    return " ".join(words)


def make_mixed(fr_text: str, en_text: str, rng: random.Random) -> str:
    """Вкрапления предложений другого языка в основной текст."""
    base = fr_text.split(". ")
    other = [s for s in en_text.split(". ") if len(s) > 30]
    out: list[str] = []
    for sentence in base:
        out.append(sentence)
        if other and rng.random() < 0.3:
            out.append(other[rng.randrange(len(other))])
    return ". ".join(out)


def make_ascii(text: str) -> str:
    """Диакритика удалена, ВЕРХНИЙ РЕГИСТР (транслитерационный стресс)."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.upper()


# ---------------------------------------------------------------------------
# Сборка
# ---------------------------------------------------------------------------
def write_html(path: Path, body: str, lang: str, tag: str, encoding: str = "utf-8") -> None:
    charset = encoding
    html = HTML_TEMPLATE.format(lang=lang, charset=charset, tag=tag, body=body)
    path.write_bytes(html.encode(encoding))


def main() -> None:
    rng = random.Random(42)                      # воспроизводимость коллекции
    manifest: list[dict] = []

    TRAIN_DIR.mkdir(parents=True, exist_ok=True)
    TEST_DIR.mkdir(parents=True, exist_ok=True)
    STRESS_DIR.mkdir(parents=True, exist_ok=True)

    for lang in ("fr", "en"):
        train_stream = load_stream(lang, "train")
        test_stream = load_stream(lang, "test")

        # --- тренировочный набор: обрезка по байтам UTF-8, по границе слова ---
        head = train_stream.encode("utf-8")[:TRAIN_BYTES].decode("utf-8", "ignore")
        head = head[: head.rfind(" ")]
        (TRAIN_DIR / f"{lang}.txt").write_text(head, encoding="utf-8")
        print(f"train/{lang}.txt: {len(head.encode('utf-8')) / 1024:.1f} Кб")

        # --- основная коллекция: окна ровно DOC_CHARS знаков -----------------
        body_chars = DOC_CHARS - TITLE_PAD
        for i, window in enumerate(windows(test_stream, body_chars, DOCS_PER_LANG), 1):
            tag = f"{lang}-{i:02d}"
            encoding = "windows-1252" if (lang == "fr" and i <= CP1252_COUNT) else "utf-8"
            write_html(TEST_DIR / f"{lang}_{i:02d}.html", window, lang, tag, encoding)
            manifest.append({
                "file": f"{lang}_{i:02d}.html", "suite": "main", "lang": lang,
                "chars": len(window) + TITLE_PAD, "encoding": encoding,
                "source": sorted(p.name for p in (SOURCES_DIR / lang / "test").glob("*.txt")),
            })

        # --- стресс-наборы ----------------------------------------------------
        other_stream = load_stream("en" if lang == "fr" else "fr", "test")
        suites = {
            "short": lambda t, o: windows(t, SHORT_CHARS - TITLE_PAD, STRESS_PER_LANG),
            "typos": lambda t, o: [make_typos(w, rng) for w in windows(t, body_chars, STRESS_PER_LANG)],
            "mixed": lambda t, o: [make_mixed(w, o, rng) for w in windows(t, body_chars, STRESS_PER_LANG)],
            "ascii": lambda t, o: [make_ascii(w) for w in windows(t, body_chars, STRESS_PER_LANG)],
        }
        for suite, builder in suites.items():
            folder = STRESS_DIR / suite
            folder.mkdir(parents=True, exist_ok=True)
            for i, body in enumerate(builder(test_stream, other_stream), 1):
                tag = f"{lang}-{i:02d}"
                write_html(folder / f"{lang}_{i:02d}.html", body, lang, tag)
                manifest.append({
                    "file": f"{suite}/{lang}_{i:02d}.html", "suite": suite,
                    "lang": lang, "chars": len(body) + TITLE_PAD, "encoding": "utf-8",
                })

    (TEST_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    sizes = [m["chars"] for m in manifest if m["suite"] == "main"]
    print(f"test/: {len(sizes)} документов, знаков видимого текста: {min(sizes)}..{max(sizes)}")
    print("готово: corpus/train, corpus/test, corpus/stress")


if __name__ == "__main__":
    main()
