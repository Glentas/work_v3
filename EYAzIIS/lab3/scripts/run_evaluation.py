# -*- coding: utf-8 -*-
"""Тестирование системы и оценка результатов (для отчёта).

Для каждого документа тестовой коллекции строится реферат и вычисляются:
  * ROUGE-1 / ROUGE-2 (F-мера) против эталонного реферата (lead-абзац статьи);
  * полнота покрытия ключевых терминов (top-20 TF-IDF документа в реферате);
  * семантическая адекватность: косинусная близость нейросетевых эмбеддингов
    реферата и полного документа;
  * степень сжатия и затраченное время.
Результаты агрегируются по языкам и предметным областях -> report/results.json.
Сравнение режимов: sentence extraction без нейросети и с нейросетевым
уточнением (MMR).
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from app.core import neural                                  # noqa: E402
from app.core.collection import load_collection             # noqa: E402
from app.core.summarizer import summarize_document          # noqa: E402
from app.core.tokenizer import tokenize_words               # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "report", "results.json")
N_SENT = 10


def ngrams(tokens, n):
    return [tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)]


def rouge_n(hyp: str, ref: str, n: int) -> float:
    h = ngrams(tokenize_words(hyp), n)
    r = ngrams(tokenize_words(ref), n)
    if not h or not r:
        return 0.0
    from collections import Counter
    ch, cr = Counter(h), Counter(r)
    overlap = sum(min(ch[g], cr[g]) for g in cr)
    prec = overlap / len(h)
    rec = overlap / len(r)
    if prec + rec == 0:
        return 0.0
    return 2 * prec * rec / (prec + rec)


def coverage(summary_text: str, doc, top_k: int = 20) -> float:
    from app.core.extraction import analyze
    from app.core.collection import load_collection as lc
    idx = lc().index
    ex = analyze(doc, idx)
    top = sorted(ex.base_weights.items(), key=lambda x: x[1], reverse=True)[:top_k]
    summ_tokens = set(tokenize_words(summary_text))
    hit = sum(1 for t, _ in top if t in summ_tokens)
    return hit / top_k


def redundancy(summary_sentences: list[str], backend) -> float:
    """Средний попарный косинус предложений реферата (меньше = разнообразнее)."""
    if len(summary_sentences) < 2:
        return 0.0
    em = backend.embed(summary_sentences)
    tot, cnt = 0.0, 0
    for i in range(len(em)):
        for j in range(i + 1, len(em)):
            tot += neural.cosine(em[i], em[j])
            cnt += 1
    return tot / cnt if cnt else 0.0


def main():
    coll = load_collection()
    backend = neural.get_backend([d.text for d in coll.docs.values()])
    print("neural backend:", backend.name)
    rows = []
    for m in coll.meta:
        doc = coll.docs[m["id"]]
        ref = coll.references.get(m["id"], "")
        for mode in ("extraction", "extraction+neural"):
            t0 = time.perf_counter()
            out = summarize_document(doc, coll.index, n=N_SENT,
                                     use_neural=(mode == "extraction+neural"),
                                     backend=backend, doc_in_index=True)
            elapsed = (time.perf_counter() - t0) * 1000
            stext = out.summary_text()
            row = {
                "doc_id": m["id"], "lang": m["lang"], "domain": m["domain"],
                "title": m["title"], "mode": mode,
                "rouge1": round(rouge_n(stext, ref, 1), 4),
                "rouge2": round(rouge_n(stext, ref, 2), 4),
                "coverage": round(coverage(stext, doc), 4),
                "adequacy": round(neural.doc_similarity(backend, stext,
                                                        doc.text), 4),
                "redundancy": round(redundancy([s["text"] for s in out.sentences],
                                               backend), 4),
                "compression": round(out.compression, 4),
                "elapsed_ms": round(elapsed, 1),
                "n_sentences": len(out.sentences),
            }
            rows.append(row)
            print(f"{m['id']:12s} {mode:18s} R1={row['rouge1']:.3f} "
                  f"R2={row['rouge2']:.3f} cov={row['coverage']:.2f} "
                  f"adeq={row['adequacy']:.3f} red={row['redundancy']:.3f} "
                  f"t={row['elapsed_ms']:.0f}ms")
    # агрегация
    agg = defaultdict(list)
    for r in rows:
        agg[(r["lang"], r["domain"], r["mode"])].append(r)
        agg[("all", "all", r["mode"])].append(r)
    summary = {}
    for (lang, dom, mode), rs in sorted(agg.items()):
        summary[f"{lang}/{dom}/{mode}"] = {
            k: round(sum(r[k] for r in rs) / len(rs), 4)
            for k in ("rouge1", "rouge2", "coverage", "adequacy",
                      "redundancy", "compression", "elapsed_ms")
        }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"rows": rows, "summary": summary,
                   "backend": backend.name, "n_sentences": N_SENT},
                  f, ensure_ascii=False, indent=2)
    print("\n=== Сводка (среднее) ===")
    for k, v in summary.items():
        print(f"{k:45s} R1={v['rouge1']:.3f} R2={v['rouge2']:.3f} "
              f"cov={v['coverage']:.2f} adeq={v['adequacy']:.3f} "
              f"red={v['redundancy']:.3f} t={v['elapsed_ms']:.0f}ms")
    print("saved:", OUT)


if __name__ == "__main__":
    main()
