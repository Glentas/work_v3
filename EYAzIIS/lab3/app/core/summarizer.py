# -*- coding: utf-8 -*-
"""Оркестрация: полный конвейер построения реферата документа."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from . import neural
from .extraction import (CorpusIndex, analyze, build_index, extend_index,
                         select_sentences)
from .keywords import KeywordNode, build_keyword_tree
from .tokenizer import Document, build_document


@dataclass
class SummaryOutput:
    doc_id: str
    title: str
    lang: str
    domain: str
    source_url: str
    n_requested: int
    sentences: list = field(default_factory=list)      # dict: index/text/weight/posd/posp/score
    keywords: list = field(default_factory=list)       # dict-дерево
    neural_backend: str = ""
    neural_used: bool = False
    elapsed_ms: float = 0.0
    doc_chars: int = 0
    summary_chars: int = 0
    n_sentences_doc: int = 0

    @property
    def compression(self) -> float:
        return self.summary_chars / self.doc_chars if self.doc_chars else 0.0

    def summary_text(self) -> str:
        return " ".join(s["text"] for s in self.sentences)


def summarize_document(doc: Document, base_index: CorpusIndex,
                       n: int = 10, use_neural: bool = True,
                       backend: neural.NeuralBackend | None = None,
                       doc_in_index: bool = False) -> SummaryOutput:
    t0 = time.perf_counter()
    idx = base_index if doc_in_index else extend_index(base_index, doc)
    extraction = analyze(doc, idx)

    if use_neural and backend is not None and backend.name != "none":
        picker = lambda scored, k: neural.mmr_select(scored, k, backend)
    else:
        picker = None
    chosen = select_sentences(extraction.scored, n, neural_rerank=picker)

    out = SummaryOutput(
        doc_id=doc.id, title=doc.title, lang=doc.lang, domain=doc.domain,
        source_url=doc.source_url, n_requested=n,
        neural_backend=backend.name if backend else "none",
        neural_used=bool(use_neural and backend and backend.name != "none"),
        doc_chars=doc.length, n_sentences_doc=len(doc.sentences),
    )
    for sc in chosen:
        out.sentences.append({
            "index": sc.sentence.index,
            "text": sc.sentence.text,
            "weight": sc.weight,
            "posd": sc.posd,
            "posp": sc.posp,
            "score": sc.score,
        })
    tree = build_keyword_tree(doc, extraction,
                              backend if out.neural_used else None)
    out.keywords = [node.as_dict() for node in tree]
    out.summary_chars = len(out.summary_text())
    out.elapsed_ms = (time.perf_counter() - t0) * 1000
    return out


def summarize_text(text: str, title: str, lang: str, domain: str,
                   base_index: CorpusIndex, n: int = 10,
                   use_neural: bool = True,
                   backend: neural.NeuralBackend | None = None,
                   doc_id: str = "user") -> SummaryOutput:
    doc = build_document(doc_id, title, lang, domain, "", text)
    return summarize_document(doc, base_index, n=n, use_neural=use_neural,
                              backend=backend, doc_in_index=False)
