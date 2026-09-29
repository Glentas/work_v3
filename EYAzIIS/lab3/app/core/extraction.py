# -*- coding: utf-8 -*-
"""Классический экстрактивный реферат методом sentence extraction.

Строго по методичке:
  1. Базовый вес слова: TF*IDF.  Учитываются только значимые слова
     (без стоп-слов, чисел и слов чужой письменности).
  2. Вес предложения Si = произведение функций:
         W(Si) = Posd(Si) * Posp(Si) * Score(Si),
     где
         Posd(Si) = 1 - BD(Si)/|D|          (положение в документе)
         Posp(Si) = 1 - BP(Si)/|P|          (положение в абзаце)
         Score(Si) = sum_{t in Si} tf(t, Si) * w(t, D)   (модифицированный TFIDF)
         w(t, D) = 0.5 * (1 + tf(t, D)/tf_max(D)) * log(|DB|/df(t))
  3. Генерация: выбор N предложений с наибольшим весом
     в последовательности, в которой они идут в тексте (рекомендуется N = 10).
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field

from .tokenizer import Document, Sentence


@dataclass
class CorpusIndex:
    """Индекс коллекции: df(t) - количество документов с термином t, |DB|."""
    df: dict = field(default_factory=dict)
    db_size: int = 0

    def idf(self, term: str) -> float:
        df = self.df.get(term, 0)
        if df <= 0:
            df = 1
        return math.log(self.db_size / df)


def build_index(docs: list[Document]) -> CorpusIndex:
    idx = CorpusIndex(db_size=len(docs))
    for d in docs:
        seen = {t for s in d.sentences for t in s.tokens}
        for t in seen:
            idx.df[t] = idx.df.get(t, 0) + 1
    return idx


def extend_index(idx: CorpusIndex, doc: Document) -> CorpusIndex:
    """Добавить документ в индекс (для загруженных пользователем текстов)."""
    new = CorpusIndex(df=dict(idx.df), db_size=idx.db_size + 1)
    seen = {t for s in doc.sentences for t in s.tokens}
    for t in seen:
        new.df[t] = new.df.get(t, 0) + 1
    return new


@dataclass
class SentenceScore:
    sentence: Sentence
    posd: float
    posp: float
    score: float
    weight: float
    terms: list  # (term, tf_in_sent, w_term)


@dataclass
class ExtractionResult:
    doc: Document
    tf_doc: dict
    tf_max: float
    base_weights: dict   # базовый вес слова TF*IDF (для ключевых слов)
    scored: list         # list[SentenceScore] по порядку текста


def analyze(doc: Document, idx: CorpusIndex) -> ExtractionResult:
    """Шаги 1-2 методички: веса слов и веса предложений."""
    tf_doc: Counter = Counter()
    for s in doc.sentences:
        tf_doc.update(s.tokens)
    tf_max = max(tf_doc.values()) if tf_doc else 1

    # модифицированный TFIDF: w(t, D) = 0.5*(1 + tf(t,D)/tf_max(D)) * log(|DB|/df(t))
    w_term = {}
    for t, tf in tf_doc.items():
        w_term[t] = 0.5 * (1.0 + tf / tf_max) * idx.idf(t)

    # базовый вес слова TF*IDF (для реферата в виде списка ключевых слов)
    base_weights = {t: tf * idx.idf(t) for t, tf in tf_doc.items()}

    scored: list[SentenceScore] = []
    for s in doc.sentences:
        tf_sent: Counter = Counter(s.tokens)
        score = sum(tf_sent[t] * w_term.get(t, 0.0) for t in tf_sent)
        posd = 1.0 - s.doc_offset / max(doc.length, 1)
        posp = 1.0 - s.par_offset / max(doc.paragraphs[s.par_index].length, 1) \
            if doc.paragraphs else 1.0
        weight = posd * posp * score
        scored.append(SentenceScore(
            sentence=s, posd=posd, posp=posp, score=score, weight=weight,
            terms=[(t, tf_sent[t], w_term.get(t, 0.0)) for t in tf_sent],
        ))
    return ExtractionResult(doc=doc, tf_doc=dict(tf_doc), tf_max=float(tf_max),
                            base_weights=base_weights, scored=scored)


def select_sentences(scored: list[SentenceScore], n: int = 10,
                     neural_rerank=None) -> list[SentenceScore]:
    """Шаг 3 методички: генерация реферата.

    По умолчанию - N предложений с наибольшим весом в порядке следования
    в тексте. Если передан neural_rerank (функция MMR-отбора на нейросетевых
    эмбеддингах, замена технологии OSTIS), используется нейросетевое
    уточнение выбора с защитой от семантических повторов.
    """
    if neural_rerank is not None:
        chosen = neural_rerank(scored, n)
    else:
        ranked = sorted(scored, key=lambda x: x.weight, reverse=True)
        chosen = [sc for sc in ranked[:n] if sc.weight > 0]
        if not chosen:  # вырожденный случай: берём первые предложения
            chosen = scored[:n]
    chosen = sorted(chosen, key=lambda sc: sc.sentence.index)
    return chosen[:n]
