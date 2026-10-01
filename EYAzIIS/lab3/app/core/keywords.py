# -*- coding: utf-8 -*-
"""Реферат в виде списка ключевых слов (иерархический, в виде дерева).

Список наиболее информативных слов и словосочетаний
(именных групп), возможно иерархический:
    лазер
        лазерный луч
        синий лазер
Построение:
  * базовый вес слова - TF*IDF (шаг 1 методички);
  * словосочетания извлекаются внутри пунктуационных блоков (не склеиваются
    слова из разных частей предложения);
  * устойчивые словосочетания (члены почти всегда встречаются вместе)
    объединяются в составной корень (victor + hugo -> «victor hugo»);
  * потомки корня: словосочетания, содержащие корень, плюс семантически
    близкие термины (косинусная близость нейросетевых эмбеддингов).
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from .neural import NeuralBackend, cosine

MAX_N = 3          # максимальная длина словосочетания
ROOTS = 8          # корней дерева
CHILDREN_NG = 4    # словосочетаний-потомков на корень
CHILDREN_SEM = 3   # семантических потомков на корень
SEM_THRESHOLD = 0.45
DEDUP_THRESHOLD = 0.80
COOC_THRESHOLD = 0.80   # доля совместной встречаемости для составного корня

CHUNK_RE = re.compile(r"[,;:()!\?…\"'«»—–-]+")


@dataclass
class KeywordNode:
    term: str
    weight: float
    count: int
    kind: str = "root"     # root | phrase | semantic
    children: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "term": self.term,
            "weight": round(self.weight, 4),
            "count": self.count,
            "kind": self.kind,
            "children": [c.as_dict() for c in self.children],
        }


def extract_ngrams(tokens: list[str], max_n: int = MAX_N) -> list[tuple[str, ...]]:
    grams = []
    for n in range(1, max_n + 1):
        for i in range(len(tokens) - n + 1):
            grams.append(tuple(tokens[i:i + n]))
    return grams


def sentence_chunks(sentence) -> list[list[str]]:
    """Список блоков значимых слов, разделённых пунктуацией."""
    if not sentence.tokens:
        return []
    from .tokenizer import tokenize_words
    allowed = set(sentence.tokens)
    chunks = []
    for piece in CHUNK_RE.split(sentence.text):
        toks = [w for w in tokenize_words(piece) if w in allowed]
        if toks:
            chunks.append(toks)
    return chunks


def build_keyword_tree(doc, extraction, backend: NeuralBackend | None,
                       roots: int = ROOTS) -> list[KeywordNode]:
    base = extraction.base_weights
    tf_doc = extraction.tf_doc

    # словосочетания: последовательные значимые слова внутри пунктац. блока
    ng_counts: Counter = Counter()
    for s in doc.sentences:
        for chunk in sentence_chunks(s):
            ng_counts.update(extract_ngrams(chunk))

    ng_weight = {}
    for gram, cnt in ng_counts.items():
        if len(gram) == 1:
            continue
        ng_weight[" ".join(gram)] = cnt * sum(base.get(t, 0.0) for t in gram)

    # --- составные корни: биграммы с почти постоянной совместной встречаемостью
    merged: dict[str, list[str]] = {}     # представитель -> члены группы
    member_of: dict[str, str] = {}        # термин -> представитель группы
    bigrams = [(g, c) for g, c in ng_counts.items() if len(g) == 2]
    bigrams.sort(key=lambda x: x[1], reverse=True)
    for gram, cnt in bigrams:
        a, b = gram
        if a in member_of or b in member_of:
            continue
        if cnt >= COOC_THRESHOLD * min(tf_doc.get(a, 0), tf_doc.get(b, 0)):
            rep = f"{a} {b}"
            merged[rep] = [a, b]
            member_of[a] = rep
            member_of[b] = rep

    # --- кандидаты в корни: вершины TF*IDF + составные термины;
    #     члены составных групп отдельно не берутся
    candidates: list[tuple[str, float, list[str]]] = []
    for t, w in base.items():
        if w > 0 and t not in member_of:
            candidates.append((t, w, [t]))
    for rep, members in merged.items():
        if min(tf_doc.get(m, 0) for m in members) >= 3:
            candidates.append((rep, sum(base.get(m, 0.0) for m in members),
                               members))
    candidates.sort(key=lambda x: x[1], reverse=True)
    unigrams = sorted(((t, w) for t, w in base.items() if w > 0),
                      key=lambda x: x[1], reverse=True)

    root_terms: list[str] = []
    root_members: dict[str, list[str]] = {}
    pool = candidates[:40]
    if backend is not None and pool:
        embs = backend.embed([label for label, _, _ in pool])
        chosen_idx: list[int] = []
        for i, (label, w, members) in enumerate(pool):
            if len(chosen_idx) >= roots:
                break
            if all(cosine(embs[i], embs[j]) < DEDUP_THRESHOLD
                   for j in chosen_idx):
                chosen_idx.append(i)
                root_terms.append(label)
                root_members[label] = members
    else:
        for label, w, members in pool[:roots]:
            root_terms.append(label)
            root_members[label] = members

    tree: list[KeywordNode] = []
    used_phrases: set[str] = set()
    for r in root_terms:
        members = root_members.get(r, r.split())
        node = KeywordNode(
            term=r,
            weight=sum(base.get(m, 0.0) for m in members),
            count=min(tf_doc.get(m, 0) for m in members),
            kind="root")
        # потомки-словосочетания, содержащие любой член корня
        cand = [(ph, w) for ph, w in ng_weight.items()
                if set(ph.split()) & set(members)
                and set(ph.split()) != set(members)
                and ph not in used_phrases and ph != r]
        cand.sort(key=lambda x: x[1], reverse=True)
        for ph, w in cand[:CHILDREN_NG]:
            used_phrases.add(ph)
            node.children.append(KeywordNode(
                term=ph, weight=w, count=ng_counts[tuple(ph.split())],
                kind="phrase"))
        # семантические потомки (нейросетевая близость)
        if backend is not None:
            sem_pool = [t for t, _ in unigrams[:60]
                        if t not in members and t not in root_terms
                        and t not in member_of]
            if sem_pool:
                em = backend.embed([members[0]] + sem_pool)
                sims = sorted(((cosine(em[0], em[i + 1]), t)
                               for i, t in enumerate(sem_pool)), reverse=True)
                n_sem = 0
                for sim, t in sims:
                    if n_sem >= CHILDREN_SEM:
                        break
                    if sim >= SEM_THRESHOLD:
                        node.children.append(KeywordNode(
                            term=t, weight=base.get(t, 0.0),
                            count=tf_doc.get(t, 0), kind="semantic"))
                        n_sem += 1
        tree.append(node)
    tree.sort(key=lambda nd: nd.weight, reverse=True)
    return tree
