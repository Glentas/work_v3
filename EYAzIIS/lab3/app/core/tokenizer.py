# -*- coding: utf-8 -*-
"""Токенизация документов: абзацы, предложения, слова.

Формирует структуры данных для вычисления весов:
  |D|  - число символов в документе D;
  BD(Si) - количество символов до Si в D;
  |P|  - количество символов в абзаце P, содержащем Si;
  BP(Si) - количество символов до Si в абзаце.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .stopwords import get_stopwords

# Слово = последовательность букв (латиница + диакритика fr/en), допускаем дефис.
# Апостроф считается разделителем (французская элизия: l'homme -> l, homme).
WORD_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿŒœÆæÇç]+(?:-[A-Za-zÀ-ÖØ-öø-ÿ]+)*")

# Аббревиатуры и инициалы, после которых точка не завершает предложение.
ABBREV = {
    "mr", "mrs", "ms", "dr", "prof", "st", "fig", "eq", "cf", "etc", "vs",
    "v", "al", "chap", "pp", "vol", "inc", "ltd", "jr", "sr", "gen", "gov",
    "col", "capt", "lt", "ft", "approx", "dept", "est", "avg", "no",
    "m", "mme", "mm", "pr", "éd", "ed", "e.g", "i.e", "p", "n°",
}
ABBREV_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(a) for a in sorted(ABBREV, key=len, reverse=True)) + r")\.(?=\s)",
    re.IGNORECASE,
)
INITIAL_RE = re.compile(r"\b[A-Za-zÀ-Ý]\.(?=\s?[A-ZÀ-Ý])")

# Граница предложения: завершающая пунктуация + пробел + начало нового слова
# с заглавной буквы (либо конец текста).
SENT_BOUND_RE = re.compile(r"[.!?…]+[\"')\]»”]*\s+")
SENT_START_OK = re.compile(r"[\"'«(\[]?[A-ZÀ-ÖØ-Þ0-9]")


@dataclass
class Sentence:
    index: int                 # порядковый номер в документе
    text: str                  # исходный текст предложения
    doc_offset: int            # BD(Si): символов до Si в документе
    par_index: int             # индекс абзаца
    par_offset: int            # BP(Si): символов до Si в абзаце
    tokens: list = field(default_factory=list)      # значимые слова (после фильтров)
    all_tokens: list = field(default_factory=list)  # все слова (нижний регистр)


@dataclass
class Paragraph:
    index: int
    text: str
    length: int                # |P|
    sentences: list = field(default_factory=list)


@dataclass
class Document:
    id: str
    title: str
    lang: str
    domain: str
    source_url: str
    text: str
    paragraphs: list = field(default_factory=list)
    sentences: list = field(default_factory=list)

    @property
    def length(self) -> int:   # |D|
        return len(self.text)


def protect_abbreviations(text: str) -> str:
    text = ABBREV_RE.sub(lambda m: m.group(0)[:-1] + "\x01", text)
    text = INITIAL_RE.sub(lambda m: m.group(0)[:-1] + "\x01", text)
    return text


def restore_abbreviations(text: str) -> str:
    return text.replace("\x01", ".")


def split_sentences(par_text: str) -> list[str]:
    """Разбивает абзац на предложения с учётом аббревиатур."""
    protected = protect_abbreviations(par_text)
    parts: list[str] = []
    last = 0
    for m in SENT_BOUND_RE.finditer(protected):
        end = m.end()
        rest = protected[end:]
        if not rest.strip():
            continue  # конец абзаца
        if SENT_START_OK.match(rest):
            parts.append(protected[last:m.end()])
            last = m.end()
    tail = protected[last:]
    if tail.strip():
        parts.append(tail)
    out = []
    for p in parts:
        p = restore_abbreviations(p).strip()
        # абзац может содержать переносы строк внутри - нормализуем пробелы
        p = re.sub(r"\s+", " ", p)
        if len(p) >= 2:
            out.append(p)
    return out


def tokenize_words(text: str) -> list[str]:
    return [w.lower() for w in WORD_RE.findall(text)]


def is_content_word(word: str, lang: str, stops: set | None = None) -> bool:
    """Не учитываются стоп-слова, числа, слова < 2 символов
    и слова письменности, не соответствующей языку документа."""
    if stops is None:
        stops = get_stopwords(lang)
    if len(word) < 2:
        return False
    if any(ch.isdigit() for ch in word):
        return False
    if word in stops:
        return False
    if not WORD_RE.fullmatch(word):
        return False
    return True


def build_document(doc_id: str, title: str, lang: str, domain: str,
                   source_url: str, text: str) -> Document:
    """Полный разбор текста: абзацы -> предложения -> слова, с offsets."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\x01", ".")
    # абзацы = непустые блоки строк
    raw_blocks = [b.strip() for b in re.split(r"\n+", text) if b.strip()]
    doc = Document(id=doc_id, title=title, lang=lang, domain=domain,
                   source_url=source_url, text="\n".join(raw_blocks))
    stops = get_stopwords(lang)
    sent_idx = 0
    doc_offset_cursor = 0
    for pi, block in enumerate(raw_blocks):
        par = Paragraph(index=pi, text=block, length=len(block))
        # позиция абзаца в собранном тексте документа
        par_doc_start = doc.text.index(block, doc_offset_cursor)
        doc_offset_cursor = par_doc_start + len(block)
        off_in_par = 0
        for s_text in split_sentences(block):
            # найдём предложение внутри абзаца (после нормализации пробелов)
            pos = block.find(s_text, off_in_par)
            if pos < 0:
                pos = off_in_par
            s = Sentence(
                index=sent_idx,
                text=s_text,
                doc_offset=par_doc_start + pos,
                par_index=pi,
                par_offset=pos,
            )
            s.all_tokens = tokenize_words(s_text)
            s.tokens = [w for w in s.all_tokens if is_content_word(w, lang, stops)]
            par.sentences.append(s)
            doc.sentences.append(s)
            sent_idx += 1
            off_in_par = pos + len(s_text)
        doc.paragraphs.append(par)
    return doc
