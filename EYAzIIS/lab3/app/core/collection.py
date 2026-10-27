# -*- coding: utf-8 -*-
"""Загрузка тестовой коллекции и построение индекса |DB|, df(t)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from .extraction import CorpusIndex, build_index
from .tokenizer import Document, build_document

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "..", "data")
COLLECTION_DIR = os.path.join(DATA_DIR, "collection")
UPLOADS_DIR = os.path.join(DATA_DIR, "uploads")


@dataclass
class Collection:
    meta: list = field(default_factory=list)
    docs: dict = field(default_factory=dict)          # id -> Document
    references: dict = field(default_factory=dict)    # id -> эталонный реферат
    index: CorpusIndex | None = None

    def get(self, doc_id: str) -> Document:
        return self.docs[doc_id]


_collection: Collection | None = None


def load_collection(refresh: bool = False) -> Collection:
    global _collection
    if _collection is not None and not refresh:
        return _collection
    meta_path = os.path.join(COLLECTION_DIR, "meta.json")
    coll = Collection()
    if os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as f:
            coll.meta = json.load(f)
        for m in coll.meta:
            with open(os.path.join(COLLECTION_DIR, m["file"]),
                      encoding="utf-8") as f:
                text = f.read()
            coll.docs[m["id"]] = build_document(
                m["id"], m["title"], m["lang"], m["domain"],
                m["source_url"], text)
            ref_path = os.path.join(COLLECTION_DIR, m["reference_file"])
            if os.path.exists(ref_path):
                with open(ref_path, encoding="utf-8") as f:
                    coll.references[m["id"]] = f.read()
    coll.index = build_index(list(coll.docs.values()))
    _collection = coll
    return coll


def detect_lang(text: str) -> str:
    """Простой детектор fr/en по служебным словам."""
    from .stopwords import STOPWORDS
    words = set(__import__("re").findall(r"[a-zA-Zà-ÿÀ-ÿ']+", text.lower()))
    fr_hits = len(words & STOPWORDS["fr"])
    en_hits = len(words & STOPWORDS["en"])
    # уникальные маркеры языков
    fr_markers = {"le", "la", "les", "des", "une", "est", "dans", "pour",
                  "par", "sur", "avec", "qui", "que", "ainsi", "œuvre"}
    en_markers = {"the", "of", "and", "in", "to", "a", "an", "is", "are",
                  "was", "were", "for", "on", "with", "which", "their"}
    fr_score = len(words & fr_markers)
    en_score = len(words & en_markers)
    if fr_score == en_score:
        return "fr" if fr_hits >= en_hits else "en"
    return "fr" if fr_score > en_score else "en"
